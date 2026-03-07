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


def process_assets(
    body_html: str,
    base_url: str,
    config,
    used_browser: bool,
) -> Tuple[str, ImageStats]:
    """Download/process images and rasterize tables and SVGs. Returns modified HTML and stats."""
    stats = ImageStats()
    tree = etree.fromstring(f"<div>{body_html}</div>".encode(), etree.HTMLParser())
    root = tree.find(".//body/div")
    if root is None:
        root = tree

    # Rasterize tables and SVGs first
    root = _rasterize_elements(root, base_url, config, used_browser)

    # Process images
    img_els = root.findall(".//img")
    if img_els:
        embedded_data: dict[int, Optional[Tuple[bytes, str]]] = {}
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fetch_image, _resolve_url(el.get("src", ""), base_url)): (i, el)
                for i, el in enumerate(img_els)
                if el.get("src")
            }
            for future in as_completed(futures):
                idx, el = futures[future]
                try:
                    result = future.result(timeout=_IMAGE_TIMEOUT + 1)
                    embedded_data[idx] = result
                except Exception as exc:
                    logger.debug("Image future error: %s", exc)
                    embedded_data[idx] = None

        cumulative_bytes = 0
        max_bytes = config.max_image_size_mb * 1024 * 1024

        for i, el in enumerate(img_els):
            if not el.get("src"):
                continue
            original_src = el.get("src", "")
            result = embedded_data.get(i)
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
            data_uri = _to_data_uri(img_bytes, mime)
            el.set("src", data_uri)
            el.attrib.pop("srcset", None)
            el.attrib.pop("loading", None)
            stats.embedded += 1

    result_html = etree.tostring(root, encoding="unicode", method="html")
    return result_html, stats


def _rasterize_elements(
    root: etree._Element, base_url: str, config, used_browser: bool
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
                    _rasterize_one(page, el, el_type, config)
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("Rasterization error: %s", exc)

    return root


def _rasterize_one(page, el: etree._Element, el_type: str, config) -> None:
    """Screenshot a single element and replace it with an <img>."""
    try:
        el_html = etree.tostring(el, encoding="unicode", method="html")
        wrapper_html = (
            f'<!DOCTYPE html><html><body style="margin:0;padding:8px;background:white;">'
            f"{el_html}</body></html>"
        )
        page.set_content(wrapper_html, timeout=config.timeout_seconds * 1000)
        selector = el_type
        element_handle = page.query_selector(selector)
        if element_handle is None:
            return
        png_bytes = element_handle.screenshot(type="png")
        if not png_bytes:
            return

        # 2x resolution: re-render at double width
        data_uri = _to_data_uri(png_bytes, "image/png")
        img = etree.Element("img")
        img.set("src", data_uri)
        img.set("alt", f"Rendered {el_type}")
        img.set("style", "max-width:100%;height:auto;")

        parent = el.getparent()
        if parent is not None:
            idx = list(parent).index(el)
            parent.remove(el)
            parent.insert(idx, img)
    except Exception as exc:
        logger.debug("Failed to rasterize %s: %s", el_type, exc)


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


def _to_data_uri(data: bytes, mime: str) -> str:
    import base64
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


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
