"""Tests for src/extract.py"""
from src.extract import ArticleMetadata, _jsonld, _og, extract

ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Test Article Title</title>
  <meta property="og:title" content="OG Title"/>
  <meta property="og:description" content="OG Description"/>
  <meta property="article:published_time" content="2024-03-01"/>
  <meta name="author" content="Meta Author"/>
  <script type="application/ld+json">
  {
    "@type": "NewsArticle",
    "headline": "JSON-LD Headline",
    "author": {"@type": "Person", "name": "LD Author"},
    "datePublished": "2024-03-01"
  }
  </script>
</head>
<body>
  <h1>Main Heading</h1>
  <p>This is a substantial article body with enough words to be useful.
  The quick brown fox jumps over the lazy dog repeatedly in this paragraph.
  We need sufficient content for readability to extract properly.</p>
  <p>Second paragraph adds more context and depth to the article content here.</p>
</body>
</html>"""


def test_extract_returns_tuple(simple_html):
    metadata, body = extract(simple_html, "https://example.com")
    assert isinstance(metadata, ArticleMetadata)
    assert body is None or isinstance(body, str)


def test_extract_gets_og_title(simple_html):
    metadata, body = extract(simple_html, "https://example.com")
    assert metadata.title == "OG Test Article"


def test_extract_gets_og_author(simple_html):
    metadata, _ = extract(simple_html, "https://example.com")
    assert metadata.author == "Jane Doe"


def test_extract_jsonld_priority_over_og():
    # JSON-LD headline is preferred over og:title (og:title often has site-name suffix)
    metadata, _ = extract(ARTICLE_HTML, "https://example.com")
    assert metadata.title == "JSON-LD Headline"


def test_extract_jsonld_author_fallback():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type":"Article","author":{"name":"LD Person"}}</script>
    </head><body><p>""" + " ".join(["word"] * 50) + """</p></body></html>"""
    metadata, _ = extract(html, "https://example.com")
    assert metadata.author == "LD Person"


def test_extract_date_from_og(simple_html):
    metadata, _ = extract(simple_html, "https://example.com")
    assert metadata.date == "2024-01-15"


def test_extract_word_count(simple_html):
    metadata, _ = extract(simple_html, "https://example.com")
    assert metadata.word_count > 0


def test_extract_empty_html():
    metadata, body = extract("", "https://example.com")
    assert body is None


def test_extract_body_is_html_string(simple_html):
    _, body = extract(simple_html, "https://example.com")
    if body is not None:
        assert "<" in body


def test_og_missing_returns_empty():
    from lxml import etree
    tree = etree.fromstring(b"<html><head></head><body></body></html>", etree.HTMLParser())
    assert _og(tree, "title") == ""


def test_jsonld_non_article_ignored():
    from lxml import etree
    html = b"""<html><head>
    <script type="application/ld+json">{"@type":"WebPage","name":"page"}</script>
    </head><body></body></html>"""
    tree = etree.fromstring(html, etree.HTMLParser())
    assert _jsonld(tree) == {}


def test_jsonld_article_parsed():
    from lxml import etree
    html = b"""<html><head>
    <script type="application/ld+json">{"@type":"Article","headline":"LD Title"}</script>
    </head><body></body></html>"""
    tree = etree.fromstring(html, etree.HTMLParser())
    jld = _jsonld(tree)
    assert jld.get("headline") == "LD Title"


def test_extract_description():
    metadata, _ = extract(ARTICLE_HTML, "https://example.com")
    assert metadata.description == "OG Description"
