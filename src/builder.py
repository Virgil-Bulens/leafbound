"""EPUB3 assembly via ebooklib."""
import logging
import re
from datetime import datetime, timezone

from ebooklib import epub

from .assets import ImageItems, ImageStats
from .extract import ArticleMetadata

logger = logging.getLogger(__name__)

_WPM = 238


def build_epub(
    body_html: str,
    metadata: ArticleMetadata,
    image_stats: ImageStats,
    image_items: ImageItems,
    config,
) -> bytes:
    """Assemble and return EPUB3 bytes."""
    reading_minutes = max(1, round(metadata.word_count / _WPM))
    reading_time_str = f"{reading_minutes} min read"

    book = epub.EpubBook()
    book.set_identifier(_make_identifier(metadata))
    book.set_title(metadata.title or "Untitled")
    book.set_language("en")

    if metadata.author:
        book.add_author(metadata.author)
    if metadata.date:
        book.add_metadata("DC", "date", metadata.date)
    if metadata.description:
        book.add_metadata("DC", "description", metadata.description)

    book.add_metadata("DC", "subject", reading_time_str)
    book.add_metadata(None, "meta", "", {"name": "reading-time", "content": reading_time_str})

    css_content = _default_css()
    css_item = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=css_content.encode(),
    )
    book.add_item(css_item)

    for fname, (img_bytes, mime) in image_items.items():
        img_item = epub.EpubItem(
            uid=fname.replace("/", "-").replace(".", "-"),
            file_name=fname,
            media_type=mime,
            content=img_bytes,
        )
        book.add_item(img_item)

    chapter = epub.EpubHtml(title=metadata.title or "Article", file_name="article.xhtml", lang="en")
    chapter.content = _wrap_html(body_html, metadata, reading_time_str)
    chapter.add_item(css_item)
    book.add_item(chapter)

    book.toc = (epub.Link("article.xhtml", metadata.title or "Article", "article"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    import io
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def _wrap_html(body_html: str, metadata: ArticleMetadata, reading_time: str) -> str:
    title = metadata.title or "Article"
    author_line = f'<p class="author">{metadata.author}</p>' if metadata.author else ""
    date_line = f'<p class="date">{metadata.date}</p>' if metadata.date else ""
    return (
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
        f"<head>"
        f'<meta charset="utf-8"/>'
        f"<title>{title}</title>"
        f'<link rel="stylesheet" type="text/css" href="style/main.css"/>'
        f"</head>"
        f"<body>"
        f"<header>"
        f"<h1>{title}</h1>"
        f"{author_line}"
        f"{date_line}"
        f'<p class="reading-time">{reading_time}</p>'
        f"</header>"
        f"<article>{body_html}</article>"
        f"</body>"
        f"</html>"
    )


def _make_identifier(metadata: ArticleMetadata) -> str:
    if metadata.title:
        slug = re.sub(r"[^a-z0-9]+", "-", metadata.title.lower()).strip("-")[:60]
        return f"leafbound-{slug}"
    return f"leafbound-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _default_css() -> str:
    return """
body {
    font-family: Georgia, serif;
    font-size: 1em;
    line-height: 1.6;
    margin: 1em 2em;
    color: #222;
}
h1, h2, h3, h4, h5, h6 {
    font-family: Helvetica, Arial, sans-serif;
    line-height: 1.2;
}
header {
    margin-bottom: 2em;
    border-bottom: 1px solid #ccc;
    padding-bottom: 1em;
}
header h1 {
    font-size: 1.6em;
    margin-bottom: 0.2em;
}
.author, .date, .reading-time {
    font-size: 0.85em;
    color: #666;
    margin: 0.1em 0;
}
img {
    max-width: 100%;
    height: auto;
}
table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.9em;
}
th, td {
    border: 1px solid #ccc;
    padding: 4px 8px;
}
blockquote {
    border-left: 3px solid #ccc;
    margin-left: 0;
    padding-left: 1em;
    color: #555;
}
pre, code {
    font-family: monospace;
    font-size: 0.9em;
    background: #f5f5f5;
    padding: 0.2em 0.4em;
}
pre {
    padding: 1em;
    overflow-x: auto;
}
"""


def output_filename(metadata: ArticleMetadata) -> str:
    """Derive output filename from article title."""
    if metadata.title:
        slug = re.sub(r"\s+", "-", metadata.title.lower())
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        slug = slug[:80].strip("-")
        if slug:
            return f"{slug}.epub"
    return f"{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S')}.epub"
