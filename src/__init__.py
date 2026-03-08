import logging

from .assets import process_assets
from .builder import build_epub
from .config import ConversionConfig
from .extract import extract
from .fetch import fetch

logger = logging.getLogger(__name__)


class ConversionError(Exception):
    pass


def convert(url: str, config: ConversionConfig) -> bytes:
    """Convert a web article URL to EPUB3 bytes."""
    html, used_browser = fetch(url, config)
    if not html:
        raise ConversionError(f"Failed to fetch content from {url}")

    metadata, body_html = extract(html, url)
    if not body_html:
        if metadata.title == "__paywall__":
            raise ConversionError(
                "Paywall detected — article content not accessible without authentication."
            )
        raise ConversionError(
            "Bot-detection or challenge page returned — "
            "site may require authentication or block automated access."
            if metadata.title == ""
            else f"Failed to extract article body from {url}"
        )

    body_html, image_stats, image_items = process_assets(body_html, url, config, used_browser)
    epub_bytes = build_epub(body_html, metadata, image_stats, image_items, config)
    return epub_bytes
