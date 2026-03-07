"""Tests for src/fetch.py"""
from unittest.mock import patch

from src import ConversionConfig
from src.fetch import _word_count, fetch


def test_word_count_html():
    html = "<p>" + " ".join(["word"] * 250) + "</p>"
    assert _word_count(html) >= 200


def test_word_count_short():
    html = "<p>short text</p>"
    assert _word_count(html) < 200


def test_fetch_returns_tuple():
    with patch("src.fetch._fetch_trafilatura") as mock_stage1:
        mock_stage1.return_value = "<p>" + " ".join(["word"] * 250) + "</p>"
        result = fetch("https://example.com", ConversionConfig())
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_fetch_stage1_sufficient_skips_playwright():
    big_html = "<p>" + " ".join(["word"] * 300) + "</p>"
    with patch("src.fetch._fetch_trafilatura", return_value=big_html), \
         patch("src.fetch._fetch_playwright") as mock_pw:
        html, used_browser = fetch("https://example.com", ConversionConfig())
    assert used_browser is False
    mock_pw.assert_not_called()


def test_fetch_stage1_thin_falls_back_to_playwright():
    thin_html = "<p>short</p>"
    browser_html = "<p>" + " ".join(["word"] * 300) + "</p>"
    with patch("src.fetch._fetch_trafilatura", return_value=thin_html), \
         patch("src.fetch._fetch_playwright", return_value=browser_html):
        html, used_browser = fetch("https://example.com", ConversionConfig())
    assert used_browser is True
    assert html == browser_html


def test_fetch_stage1_none_tries_playwright():
    browser_html = "<p>browser content</p>"
    with patch("src.fetch._fetch_trafilatura", return_value=None), \
         patch("src.fetch._fetch_playwright", return_value=browser_html):
        html, used_browser = fetch("https://example.com", ConversionConfig())
    assert used_browser is True


def test_fetch_both_fail_returns_none():
    with patch("src.fetch._fetch_trafilatura", return_value=None), \
         patch("src.fetch._fetch_playwright", return_value=None):
        html, used_browser = fetch("https://example.com", ConversionConfig())
    assert html is None
    assert used_browser is False


def test_fetch_playwright_fallback_uses_thin_stage1():
    thin_html = "<p>thin</p>"
    with patch("src.fetch._fetch_trafilatura", return_value=thin_html), \
         patch("src.fetch._fetch_playwright", return_value=None):
        html, used_browser = fetch("https://example.com", ConversionConfig())
    assert html == thin_html
    assert used_browser is False
