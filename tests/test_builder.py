"""Tests for src/builder.py"""
import io
import zipfile

from src import ConversionConfig
from src.assets import ImageStats
from src.builder import _make_identifier, build_epub, output_filename
from src.extract import ArticleMetadata


def _make_epub(title="Test Article", author="Test Author", date="2024-01-01",
               word_count=500, body="<p>Hello world</p>") -> bytes:
    metadata = ArticleMetadata(
        title=title, author=author, date=date,
        description="A test article", word_count=word_count,
    )
    stats = ImageStats(embedded=2, placeholders=1)
    cfg = ConversionConfig()
    return build_epub(body, metadata, stats, cfg)


def test_build_epub_returns_bytes():
    result = _make_epub()
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_build_epub_is_valid_zip():
    result = _make_epub()
    buf = io.BytesIO(result)
    assert zipfile.is_zipfile(buf)


def test_build_epub_contains_mimetype():
    result = _make_epub()
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        assert "mimetype" in zf.namelist()
        assert zf.read("mimetype") == b"application/epub+zip"


def test_build_epub_contains_article_xhtml():
    result = _make_epub()
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        names = zf.namelist()
        assert any("article.xhtml" in n for n in names)


def test_build_epub_contains_css():
    result = _make_epub()
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        names = zf.namelist()
        assert any(".css" in n for n in names)


def test_build_epub_title_in_content():
    result = _make_epub(title="My Great Article")
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        for name in zf.namelist():
            if "article.xhtml" in name:
                content = zf.read(name).decode()
                assert "My Great Article" in content
                break


def test_build_epub_reading_time_in_content():
    result = _make_epub(word_count=238)  # exactly 1 min at 238 wpm
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        for name in zf.namelist():
            if "article.xhtml" in name:
                content = zf.read(name).decode()
                assert "1 min read" in content
                break


def test_build_epub_reading_time_rounds():
    result = _make_epub(word_count=2380)  # 10 min
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        for name in zf.namelist():
            if "article.xhtml" in name:
                content = zf.read(name).decode()
                assert "10 min read" in content
                break


def test_output_filename_normal():
    meta = ArticleMetadata(title="Hello World Article")
    fname = output_filename(meta)
    assert fname == "hello-world-article.epub"


def test_output_filename_strips_special_chars():
    meta = ArticleMetadata(title="Hello, World! (2024)")
    fname = output_filename(meta)
    assert ".epub" in fname
    assert "," not in fname
    assert "!" not in fname


def test_output_filename_truncates_long_title():
    meta = ArticleMetadata(title="a" * 200)
    fname = output_filename(meta)
    assert len(fname) <= 85  # 80 chars + ".epub"


def test_output_filename_fallback_no_title():
    meta = ArticleMetadata()
    fname = output_filename(meta)
    assert fname.endswith(".epub")
    assert len(fname) > 5


def test_make_identifier_uses_title():
    meta = ArticleMetadata(title="Test Title")
    uid = _make_identifier(meta)
    assert uid.startswith("leafbound-")
    assert "test-title" in uid


def test_make_identifier_fallback():
    meta = ArticleMetadata()
    uid = _make_identifier(meta)
    assert uid.startswith("leafbound-")


def test_build_epub_no_author_no_crash():
    result = _make_epub(author="")
    assert isinstance(result, bytes)


def test_build_epub_no_date_no_crash():
    result = _make_epub(date="")
    assert isinstance(result, bytes)
