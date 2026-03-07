"""Integration tests — call convert() with real URLs. Slow, requires network."""
from pathlib import Path

import pytest

from src import ConversionConfig, ConversionError, convert


def _urls_by_category() -> dict:
    urls_file = Path(__file__).parent / "urls.txt"
    categories: dict = {}
    current = None
    for line in urls_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            if line.startswith("# ") and not line.startswith("# Leafbound"):
                current = line[2:].split("(")[0].strip()
                categories[current] = []
            continue
        if current is not None:
            categories[current].append(line)
    return categories


_CATEGORIES = _urls_by_category()


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("static-news", []))
def test_static_news(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("substack", []))
def test_substack(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("medium", []))
def test_medium(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("wikipedia-tables", []))
def test_wikipedia_tables(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("svg", []))
def test_svg_articles(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("image-heavy", []))
def test_image_heavy(url):
    cfg = ConversionConfig(timeout_seconds=30)
    epub = convert(url, cfg)
    assert isinstance(epub, bytes)
    assert len(epub) > 1000


@pytest.mark.integration
@pytest.mark.parametrize("url", _CATEGORIES.get("paywall", []))
def test_paywall_graceful(url):
    """Paywalled articles must not crash — either partial EPUB or ConversionError."""
    cfg = ConversionConfig(timeout_seconds=30)
    try:
        epub = convert(url, cfg)
        # If we get bytes, they should be a valid (possibly thin) EPUB
        assert isinstance(epub, bytes)
    except ConversionError:
        pass  # Expected for total extraction failure on paywalled content
