"""Article body isolation and metadata extraction."""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import trafilatura
from lxml import etree
from readability import Document

logger = logging.getLogger(__name__)

_MIN_BODY_WORDS = 200
_HAS_IMG = re.compile(r"<(img|graphic)\b", re.IGNORECASE)

# Bot/challenge-page detection — fires when title matches AND body is thin
_BOT_TITLE_RE = re.compile(
    r"""
    just\ a\ moment               |   # Cloudflare JS challenge
    attention\ required            |   # Cloudflare access denied
    verifying\ (you\ are\ )?human  |
    access\ denied                 |
    security\ check                |
    ddos.{0,20}protection          |
    please\ (wait|stand\ by)       |
    checking\ your\ browser        |
    enable\ javascript             |
    error\ [-\u2013\u2014]\ \w     |   # "error - substack", "error — site"
    robot.{0,10}check              |
    are\ you\ (a\ )?robot          |
    challenge\ page
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Paywall-page detection
_PAYWALL_RE = re.compile(
    r"subscribe|subscription|sign.?in to read|log.?in to read"
    r"|paid subscriber|premium content|create an account",
    re.IGNORECASE,
)


@dataclass
class ArticleMetadata:
    title: str = ""
    author: str = ""
    date: str = ""
    description: str = ""
    og_image: str = ""
    word_count: int = 0


def extract(html: str, url: str) -> Tuple[ArticleMetadata, Optional[str]]:
    """Extract article body and metadata from raw HTML."""
    body_html: Optional[str] = None
    readable_title = ""

    # Try readability first
    try:
        doc = Document(html)
        candidate = doc.summary(html_partial=True)
        readable_title = doc.title()
        if candidate and _word_count_html(candidate) >= _MIN_BODY_WORDS:
            body_html = candidate
    except Exception as exc:
        logger.debug("readability extraction failed: %s", exc)

    # Fall back to trafilatura HTML extraction if readability is thin
    if body_html is None:
        logger.debug("readability body thin, falling back to trafilatura HTML extraction")
        tf_html = trafilatura.extract(
            html,
            output_format="html",
            include_images=True,
            include_links=False,
        )
        if tf_html:
            body_html = tf_html

    if not body_html:
        return ArticleMetadata(), None

    metadata = _extract_metadata(html, url, readable_title)
    metadata.word_count = _word_count_html(body_html)

    # Detect bot-challenge pages
    if _is_bot_page(metadata.title, metadata.word_count):
        logger.debug("Bot-detection page detected for %s", url)
        return ArticleMetadata(), None

    # Detect paywall pages
    if _is_paywall_page(body_html, metadata.word_count):
        logger.debug("Paywall page detected for %s", url)
        meta = ArticleMetadata()
        meta.title = "__paywall__"
        return meta, None

    # Strip duplicate leading h1
    body_html = _strip_leading_h1(body_html, metadata.title)

    # If the body has no images, prepend the OG image as a hero
    if metadata.og_image and not _HAS_IMG.search(body_html):
        body_html = f'<img src="{metadata.og_image}" alt=""/>\n{body_html}'

    return metadata, body_html


def _is_bot_page(title: str, word_count: int) -> bool:
    return word_count < 120 and bool(_BOT_TITLE_RE.search(title))


def _is_paywall_page(body_html: str, word_count: int) -> bool:
    return word_count < 300 and bool(_PAYWALL_RE.search(body_html[:2000]))


def _word_count_html(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html).split())


def _strip_leading_h1(body_html: str, title: str) -> str:
    """Remove the first <h1> from body if its text matches the article title."""
    if not title:
        return body_html
    try:
        tree = etree.fromstring(
            f"<div>{body_html}</div>".encode(), etree.HTMLParser(encoding="utf-8")
        )
        root = tree.find(".//body/div")
        if root is None:
            root = tree
        for h1 in root.findall(".//h1"):
            h1_text = " ".join(h1.itertext()).strip()
            if _normalise(h1_text) == _normalise(title):
                parent = h1.getparent()
                if parent is not None:
                    parent.remove(h1)
                break
        return etree.tostring(root, encoding="unicode", method="html")
    except Exception as exc:
        logger.debug("_strip_leading_h1 failed: %s", exc)
        return body_html


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _extract_metadata(html: str, url: str, fallback_title: str) -> ArticleMetadata:
    meta = ArticleMetadata()

    try:
        tree = etree.fromstring(html.encode(), etree.HTMLParser(encoding="utf-8"))
    except Exception:
        meta.title = fallback_title
        return meta

    # 1. OpenGraph
    og_title = _og(tree, "title")
    og_author = _og(tree, "author") or _og(tree, "article:author")
    og_date = _og(tree, "article:published_time") or _og(tree, "article:modified_time")
    og_desc = _og(tree, "description")
    og_image = _og(tree, "image")

    # 2. JSON-LD
    jld = _jsonld(tree)

    # 3. Standard meta
    std_desc = _meta_name(tree, "description")
    std_author = _meta_name(tree, "author")

    # 4. Heuristic fallbacks
    h1_text = ""
    h1_els = tree.findall(".//h1")
    if h1_els:
        h1_text = "".join(h1_els[0].itertext()).strip()

    # og_title first: most reliable after _clean_title; jld.headline fallback
    # jld.name is excluded — it's often an SEO description, not the article title
    meta.title = _clean_title(
        og_title
        or jld.get("headline")
        or fallback_title
        or h1_text
        or ""
    )
    meta.author = og_author or _jld_author(jld) or std_author
    meta.date = (
        og_date
        or jld.get("datePublished")
        or jld.get("dateModified")
        or ""
    )
    meta.description = og_desc or std_desc or jld.get("description") or ""
    meta.og_image = og_image or jld.get("image", {}).get("url", "") if isinstance(
        jld.get("image"), dict
    ) else og_image

    return meta


def _clean_title(title: str) -> str:
    """Strip ' | SiteName' suffix. Only pipe separators are stripped —
    em-dashes appear legitimately in article titles and are left alone."""
    if " | " in title:
        head, _ = title.rsplit(" | ", 1)
        if head:
            return head.strip()
    return title


def _og(tree: etree._Element, prop: str) -> str:
    el = tree.find(f'.//meta[@property="og:{prop}"]')
    if el is None:
        el = tree.find(f'.//meta[@property="{prop}"]')
    if el is not None:
        return (el.get("content") or "").strip()
    return ""


def _meta_name(tree: etree._Element, name: str) -> str:
    el = tree.find(f'.//meta[@name="{name}"]')
    if el is not None:
        return (el.get("content") or "").strip()
    return ""


def _jsonld(tree: etree._Element) -> dict:
    for script in tree.findall('.//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text or "")
            if isinstance(data, list):
                data = data[0]
            if isinstance(data, dict) and data.get("@type") in (
                "Article", "NewsArticle", "BlogPosting"
            ):
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _jld_author(jld: dict) -> str:
    author = jld.get("author")
    if not author:
        return ""
    if isinstance(author, dict):
        return author.get("name", "")
    if isinstance(author, list) and author:
        first = author[0]
        if isinstance(first, dict):
            return first.get("name", "")
        return str(first)
    return str(author)
