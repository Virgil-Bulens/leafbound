"""Tests for src/extract.py"""
from src.extract import (
    ArticleMetadata,
    _clean_title,
    _is_bot_page,
    _is_paywall_page,
    _jsonld,
    _og,
    _strip_leading_h1,
    extract,
)

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


def test_extract_og_preferred_over_jsonld_headline():
    # og:title is now preferred because it's the most reliable after _clean_title
    metadata, _ = extract(ARTICLE_HTML, "https://example.com")
    assert metadata.title == "OG Title"


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


# --- _clean_title ---

def test_clean_title_strips_pipe_suffix():
    assert _clean_title("Article Title | HackerNoon") == "Article Title"


def test_clean_title_strips_pipe_publication():
    assert _clean_title("Cuba news story | BBC News") == "Cuba news story"


def test_clean_title_preserves_emdash():
    assert _clean_title("Title — here's what we know") == "Title — here's what we know"


def test_clean_title_no_suffix():
    assert _clean_title("Indonesia to ban social media") == "Indonesia to ban social media"


def test_clean_title_pipe_in_middle_preserved():
    # Only the LAST " | " is checked via rsplit; if head is nonempty it's stripped
    # "A | B | C" → head="A | B", tail="C" → "A | B"
    assert _clean_title("A | B | C") == "A | B"


# --- _strip_leading_h1 ---

def test_strip_leading_h1_removes_matching():
    body = "<h1>My Article</h1><p>Content here.</p>"
    result = _strip_leading_h1(body, "My Article")
    assert "<h1>" not in result
    assert "Content here" in result


def test_strip_leading_h1_case_insensitive():
    body = "<h1>my article</h1><p>Content.</p>"
    result = _strip_leading_h1(body, "My Article")
    assert "<h1>" not in result


def test_strip_leading_h1_no_match_leaves_unchanged():
    body = "<h1>Different Heading</h1><p>Content.</p>"
    result = _strip_leading_h1(body, "My Article")
    assert "<h1>" in result


def test_strip_leading_h1_empty_title():
    body = "<h1>Some Heading</h1><p>Content.</p>"
    result = _strip_leading_h1(body, "")
    assert "<h1>" in result


# --- _is_bot_page ---

def test_is_bot_page_cloudflare():
    assert _is_bot_page("Just a moment...", 50)


def test_is_bot_page_access_denied():
    assert _is_bot_page("Access Denied", 30)


def test_is_bot_page_not_triggered_for_long_body():
    # High word count overrides title match
    assert not _is_bot_page("Just a moment...", 500)


def test_is_bot_page_normal_title():
    assert not _is_bot_page("Indonesia bans social media for under 16s", 50)


def test_is_bot_page_substack_error():
    assert _is_bot_page("error — substack", 20)


# --- _is_paywall_page ---

def test_is_paywall_page_detected():
    body = "<p>Subscribe to read this article. This content is for paid subscribers.</p>"
    assert _is_paywall_page(body, 50)


def test_is_paywall_page_not_triggered_long_body():
    body = ("<p>subscribe</p>" + "<p>" + " ".join(["word"] * 400) + "</p>")
    assert not _is_paywall_page(body, 410)


def test_is_paywall_page_normal_article():
    body = "<p>This is a normal article about technology and innovation.</p>"
    assert not _is_paywall_page(body, 50)
