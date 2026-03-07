"""Shared fixtures for the Leafbound test suite."""
import pytest

from src import ConversionConfig


@pytest.fixture
def config() -> ConversionConfig:
    return ConversionConfig(timeout_seconds=15, max_image_size_mb=50, headless=True)


@pytest.fixture
def simple_html() -> str:
    return """<!DOCTYPE html>
<html>
<head>
  <title>Test Article</title>
  <meta property="og:title" content="OG Test Article"/>
  <meta property="og:article:author" content="Jane Doe"/>
  <meta property="article:published_time" content="2024-01-15"/>
</head>
<body>
  <h1>Test Article</h1>
  <p>This is a test article with enough content to be meaningful.
  It has multiple sentences covering a variety of topics.
  The quick brown fox jumps over the lazy dog.
  Pack my box with five dozen liquor jugs.
  How vexingly quick daft zebras jump.
  The five boxing wizards jump quickly.</p>
  <p>Second paragraph with more content to ensure we have sufficient word count
  for the extraction pipeline to work correctly in unit tests.</p>
</body>
</html>"""


@pytest.fixture
def html_with_table() -> str:
    return """<!DOCTYPE html>
<html><head><title>Table Article</title></head>
<body>
<h1>Article with Table</h1>
<p>Some introductory text that provides context for the table below.</p>
<table>
  <thead><tr><th>Name</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>Alpha</td><td>1</td></tr>
    <tr><td>Beta</td><td>2</td></tr>
  </tbody>
</table>
<p>More content after the table to fill out the article body.</p>
</body>
</html>"""
