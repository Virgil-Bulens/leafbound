"""Tests for src/assets.py"""
import io
from unittest.mock import MagicMock, patch

from PIL import Image

from src.assets import (
    ImageStats,
    _fetch_image,
    _resolve_url,
    _to_data_uri,
    process_assets,
)


def _make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(128, 64, 32))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(0, 128, 255))
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_resolve_url_absolute():
    assert _resolve_url("https://cdn.example.com/img.jpg", "https://example.com") == "https://cdn.example.com/img.jpg"


def test_resolve_url_relative():
    resolved = _resolve_url("/images/photo.jpg", "https://example.com/article")
    assert resolved == "https://example.com/images/photo.jpg"


def test_resolve_url_empty():
    assert _resolve_url("", "https://example.com") == ""


def test_to_data_uri():
    data = b"hello"
    uri = _to_data_uri(data, "image/jpeg")
    assert uri.startswith("data:image/jpeg;base64,")


def test_fetch_image_returns_jpeg_bytes():
    jpeg = _make_jpeg_bytes()
    with patch("src.assets.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.read.return_value = jpeg
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp

        result = _fetch_image("https://example.com/img.jpg")

    assert result is not None
    img_bytes, mime = result
    assert mime == "image/jpeg"
    assert len(img_bytes) > 0


def test_fetch_image_converts_png_to_jpeg():
    png = _make_png_bytes()
    with patch("src.assets.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.read.return_value = png
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp

        result = _fetch_image("https://example.com/img.png")

    assert result is not None
    _, mime = result
    assert mime == "image/jpeg"


def test_fetch_image_network_error_returns_none():
    from urllib.error import URLError
    with patch("src.assets.urlopen", side_effect=URLError("connection refused")):
        result = _fetch_image("https://example.com/bad.jpg")
    assert result is None


def test_fetch_image_non_http_returns_none():
    result = _fetch_image("data:image/png;base64,abc")
    assert result is None


def test_fetch_image_empty_url_returns_none():
    result = _fetch_image("")
    assert result is None


def test_process_assets_no_images(config):
    html = "<p>No images here, just plain text content.</p>"
    result_html, stats = process_assets(html, "https://example.com", config, False)
    assert isinstance(result_html, str)
    assert stats.embedded == 0
    assert stats.placeholders == 0


def test_process_assets_embeds_image(config):
    jpeg = _make_jpeg_bytes()
    html = '<p>Text</p><img src="https://example.com/photo.jpg" alt="photo"/>'

    with patch("src.assets._fetch_image", return_value=(jpeg, "image/jpeg")):
        result_html, stats = process_assets(html, "https://example.com", config, False)

    assert stats.embedded == 1
    assert stats.placeholders == 0
    assert "data:image/jpeg;base64," in result_html


def test_process_assets_placeholder_on_failure(config):
    html = '<p>Text</p><img src="https://example.com/broken.jpg" alt="broken"/>'

    with patch("src.assets._fetch_image", return_value=None):
        result_html, stats = process_assets(html, "https://example.com", config, False)

    assert stats.placeholders == 1
    assert stats.embedded == 0
    assert "Image unavailable" in result_html


def test_process_assets_respects_size_cap(config):
    config.max_image_size_mb = 0  # 0 MB cap — everything overflows
    jpeg = _make_jpeg_bytes()
    html = '<img src="https://example.com/a.jpg"/>'

    with patch("src.assets._fetch_image", return_value=(jpeg, "image/jpeg")):
        _, stats = process_assets(html, "https://example.com", config, False)

    assert stats.placeholders == 1
    assert stats.embedded == 0


def test_process_assets_returns_image_stats_type(config):
    _, stats = process_assets("<p>text</p>", "https://example.com", config, False)
    assert isinstance(stats, ImageStats)
