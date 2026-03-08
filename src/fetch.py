"""Two-stage fetch pipeline: trafilatura first, Playwright fallback."""
import logging
from typing import Optional, Tuple

import trafilatura

from .config import ConversionConfig
from .extract import _BOT_TITLE_RE

logger = logging.getLogger(__name__)

_WORD_THRESHOLD = 200


def fetch(url: str, config: ConversionConfig) -> Tuple[Optional[str], bool]:
    """Fetch URL content. Returns (html, used_browser)."""
    html = _fetch_trafilatura(url)
    if html and _word_count(html) >= _WORD_THRESHOLD:
        logger.debug("Stage 1 fetch succeeded for %s", url)
        return html, False

    logger.debug("Stage 1 insufficient, falling back to Playwright for %s", url)
    browser_html = _fetch_playwright(url, config)
    if browser_html:
        return browser_html, True

    # Return stage-1 result even if thin
    if html:
        logger.debug("Playwright failed, using thin stage-1 result for %s", url)
        return html, False

    return None, False


def _fetch_trafilatura(url: str) -> Optional[str]:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return downloaded
    except Exception as exc:
        logger.debug("trafilatura fetch error for %s: %s", url, exc)
    return None


def _fetch_playwright(url: str, config: ConversionConfig) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=config.headless)
            try:
                page = browser.new_page()
                # Pass 1: navigate without stealth overhead
                html = _playwright_navigate(page, url, config)
                # Pass 2: if we got a bot-challenge page, retry with stealth patches
                if html and _looks_like_bot_page(html):
                    logger.debug("Bot page on pass 1, retrying with stealth for %s", url)
                    try:
                        from playwright_stealth import Stealth
                        Stealth().apply_stealth_sync(page)
                    except ImportError:
                        logger.debug("playwright-stealth not installed, skipping stealth retry")
                    else:
                        html = _playwright_navigate(page, url, config)
                return html
            finally:
                browser.close()
    except Exception as exc:
        logger.debug("Playwright error for %s: %s", url, exc)
        return None


def _playwright_navigate(page, url: str, config: ConversionConfig) -> Optional[str]:
    """Navigate to URL and return page HTML, handling timeout gracefully."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        page.goto(url, wait_until="networkidle", timeout=config.timeout_seconds * 1000)
        return page.content()
    except PlaywrightTimeout:
        logger.debug("Playwright timed out for %s", url)
        try:
            return page.content()
        except Exception:
            return None


def _looks_like_bot_page(html: str) -> bool:
    """Quick heuristic: is this HTML a bot-detection challenge page?"""
    word_count = len(trafilatura.extract(html).split()) if trafilatura.extract(html) else 0
    return word_count < 200 and bool(_BOT_TITLE_RE.search(html))


def _word_count(html: str) -> int:
    # Ensure a full HTML document so trafilatura can parse it
    if not html.lstrip().lower().startswith("<!doctype") and "<html" not in html.lower():
        html = f"<html><body>{html}</body></html>"
    text = trafilatura.extract(html) or ""
    return len(text.split())
