"""Image download, Pillow processing, and table/SVG rasterization."""
import io
import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.request import Request, urlopen

from lxml import etree
from PIL import Image

logger = logging.getLogger(__name__)

_MAX_WORKERS = 4
_IMAGE_TIMEOUT = 10
_IMAGE_RETRIES = 1
_PLACEHOLDER_STYLE = (
    "display:block;padding:8px;border:1px solid #ccc;"
    "background:#f9f9f9;font-size:0.8em;color:#666;word-break:break-all;"
)


@dataclass
class ImageStats:
    embedded: int = 0
    placeholders: int = 0


# Maps epub-relative filename -> (bytes, mime_type)
ImageItems = dict[str, Tuple[bytes, str]]


def process_assets(
    body_html: str,
    base_url: str,
    config,
    used_browser: bool,
) -> Tuple[str, ImageStats, ImageItems]:
    """Download/process images and rasterize tables and SVGs.

    Returns (body_html, stats, image_items) where image_items maps
    epub-relative filenames to (bytes, mime) for inclusion in the manifest.
    """
    stats = ImageStats()
    image_items: ImageItems = {}
    tree = etree.fromstring(f"<div>{body_html}</div>".encode(), etree.HTMLParser(encoding="utf-8"))
    root = tree.find(".//body/div")
    if root is None:
        root = tree

    # Rasterize tables and SVGs first
    root = _rasterize_elements(root, base_url, config, used_browser, image_items, stats)

    # Convert trafilatura <graphic> tags to <img>
    for el in root.findall(".//graphic"):
        _graphic_to_img(el, base_url)

    # Normalise all img elements: resolve srcset → src
    for el in root.findall(".//img"):
        _normalise_img_src(el, base_url)

    # Process images
    img_els = root.findall(".//img")
    if img_els:
        fetched: dict[int, Optional[Tuple[bytes, str]]] = {}
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fetch_image, _resolve_url(el.get("src", ""), base_url)): (i, el)
                for i, el in enumerate(img_els)
                if el.get("src")
            }
            for future in as_completed(futures):
                idx, el = futures[future]
                try:
                    fetched[idx] = future.result(timeout=_IMAGE_TIMEOUT + 1)
                except Exception as exc:
                    logger.debug("Image future error: %s", exc)
                    fetched[idx] = None

        cumulative_bytes = 0
        max_bytes = config.max_image_size_mb * 1024 * 1024

        for i, el in enumerate(img_els):
            if not el.get("src"):
                continue
            original_src = el.get("src", "")
            result = fetched.get(i)
            if result is None:
                _replace_with_placeholder(el, original_src, "Failed to load")
                stats.placeholders += 1
                continue

            img_bytes, mime = result
            if cumulative_bytes + len(img_bytes) > max_bytes:
                _replace_with_placeholder(el, original_src, "Image cap reached")
                stats.placeholders += 1
                continue

            cumulative_bytes += len(img_bytes)
            ext = "jpg" if mime == "image/jpeg" else "png"
            fname = f"images/img-{len(image_items):04d}.{ext}"
            image_items[fname] = (img_bytes, mime)
            el.set("src", fname)
            el.attrib.pop("srcset", None)
            el.attrib.pop("srcSet", None)
            el.attrib.pop("loading", None)
            stats.embedded += 1

    result_html = etree.tostring(root, encoding="unicode", method="html")
    return result_html, stats, image_items


def _graphic_to_img(el: etree._Element, base_url: str) -> None:
    """Convert a trafilatura <graphic> element to a standard <img> element."""
    src = el.get("src", "")
    if not src:
        return
    img = etree.Element("img")
    img.set("src", _resolve_url(src, base_url))
    alt = el.get("alt", "") or el.get("title", "")
    if alt:
        img.set("alt", alt)
    img.set("style", "max-width:100%;height:auto;")
    parent = el.getparent()
    if parent is not None:
        idx = list(parent).index(el)
        parent.remove(el)
        parent.insert(idx, img)


def _normalise_img_src(el: etree._Element, base_url: str) -> None:
    """If an img has no usable src, resolve one from srcset/srcSet."""
    src = el.get("src", "")
    # Skip data URIs and already-good srcs
    if src.startswith(("http://", "https://")):
        return

    # Try srcset / srcSet (BBC and others use camelCase in raw HTML)
    for attr in ("srcset", "srcSet"):
        srcset = el.get(attr, "")
        if not srcset:
            continue
        best = _best_srcset_url(srcset)
        if best:
            el.set("src", _resolve_url(best, base_url))
            el.attrib.pop(attr, None)
            return

    # Clear placeholder/grey srcs that can't be fetched
    if src and not src.startswith(("http://", "https://", "data:")):
        el.attrib.pop("src", None)


def _best_srcset_url(srcset: str) -> str:
    """Pick the highest-width URL from a srcset string."""
    best_url = ""
    best_w = -1
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        url = tokens[0]
        width = 0
        if len(tokens) >= 2:
            descriptor = tokens[1]
            if descriptor.endswith("w"):
                try:
                    width = int(descriptor[:-1])
                except ValueError:
                    pass
        if width > best_w:
            best_w = width
            best_url = url
    return best_url


def _rasterize_elements(
    root: etree._Element,
    base_url: str,
    config,
    used_browser: bool,
    image_items: ImageItems,
    stats: ImageStats,
) -> etree._Element:
    """Rasterize <table> and <svg> elements using Playwright screenshots."""
    tables = root.findall(".//table")
    svgs = root.findall(".//svg")
    elements = [(el, "table") for el in tables] + [(el, "svg") for el in svgs]

    if not elements:
        return root

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=config.headless)
            try:
                page = browser.new_page(viewport={"width": 1200, "height": 800})
                for el, el_type in elements:
                    _rasterize_one(page, el, el_type, config, image_items, stats)
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("Rasterization unavailable: %s", exc)
        # Playwright not available — SVGs are not renderable by e-readers, remove them
        for el, el_type in elements:
            if el_type == "svg":
                _remove_element(el)

    return root


# Minimum PNG size for a screenshot to be considered non-blank
_MIN_RASTER_BYTES = 4096


def _rasterize_one(
    page,
    el: etree._Element,
    el_type: str,
    config,
    image_items: ImageItems,
    stats: ImageStats,
) -> None:
    """Screenshot a single element and replace it with an <img>."""
    try:
        el_html = etree.tostring(el, encoding="unicode", method="html")
        wrapper_html = (
            f'<!DOCTYPE html><html><body style="margin:0;padding:8px;background:white;">'
            f"{el_html}</body></html>"
        )
        page.set_content(wrapper_html, timeout=config.timeout_seconds * 1000)
        element_handle = page.query_selector(el_type)
        if element_handle is None:
            if el_type == "svg":
                _remove_element(el)
            return
        png_bytes = element_handle.screenshot(type="png")

        # Blank/empty screenshot — SVG has no visual content
        if not png_bytes or len(png_bytes) < _MIN_RASTER_BYTES:
            if el_type == "svg":
                _remove_element(el)
            return

        fname = f"images/img-{len(image_items):04d}.png"
        image_items[fname] = (png_bytes, "image/png")
        stats.embedded += 1

        img = etree.Element("img")
        img.set("src", fname)
        img.set("alt", "")
        img.set("style", "max-width:100%;height:auto;")

        parent = el.getparent()
        if parent is not None:
            idx = list(parent).index(el)
            parent.remove(el)
            parent.insert(idx, img)
    except Exception as exc:
        logger.debug("Failed to rasterize %s: %s", el_type, exc)
        if el_type == "svg":
            _remove_element(el)


def _remove_element(el: etree._Element) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _fetch_image(url: str) -> Optional[Tuple[bytes, str]]:
    """Fetch and process a single image. Returns (jpeg_bytes, mime) or None."""
    if not url or not url.startswith(("http://", "https://")):
        return None

    for attempt in range(_IMAGE_RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=_IMAGE_TIMEOUT) as resp:
                raw = resp.read()
            img = Image.open(io.BytesIO(raw))
            img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue(), "image/jpeg"
        except Exception as exc:
            logger.debug("Image fetch attempt %d failed for %s: %s", attempt + 1, url, exc)

    return None


def _resolve_url(src: str, base_url: str) -> str:
    if not src:
        return ""
    if src.startswith(("http://", "https://", "data:")):
        return src
    return urllib.parse.urljoin(base_url, src)



def _replace_with_placeholder(el: etree._Element, src: str, reason: str) -> None:
    placeholder = etree.Element("div")
    placeholder.set("style", _PLACEHOLDER_STYLE)
    placeholder.set("role", "img")
    placeholder.set("aria-label", el.get("alt", "Image"))
    placeholder.text = f"[Image unavailable: {reason}] {src}"
    parent = el.getparent()
    if parent is not None:
        idx = list(parent).index(el)
        parent.remove(el)
        parent.insert(idx, placeholder)
