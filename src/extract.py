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


@dataclass
class ArticleMetadata:
    title: str = ""
    author: str = ""
    date: str = ""
    description: str = ""
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

    return metadata, body_html


def _word_count_html(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html).split())


def _extract_metadata(html: str, url: str, fallback_title: str) -> ArticleMetadata:
    meta = ArticleMetadata()

    try:
        tree = etree.fromstring(html.encode(), etree.HTMLParser())
    except Exception:
        meta.title = fallback_title
        return meta

    # 1. OpenGraph
    og_title = _og(tree, "title")
    og_author = _og(tree, "author") or _og(tree, "article:author")
    og_date = _og(tree, "article:published_time") or _og(tree, "article:modified_time")
    og_desc = _og(tree, "description")

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

    meta.title = (
        og_title
        or jld.get("headline")
        or jld.get("name")
        or fallback_title
        or h1_text
    )
    meta.author = og_author or _jld_author(jld) or std_author
    meta.date = (
        og_date
        or jld.get("datePublished")
        or jld.get("dateModified")
        or ""
    )
    meta.description = og_desc or std_desc or jld.get("description") or ""

    return meta


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
