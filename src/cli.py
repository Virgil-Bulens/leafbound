"""CLI entry point for Leafbound."""
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import click

from . import ConversionError, convert
from .config import ConversionConfig


@click.command()
@click.argument("url")
@click.option("--output", default=".", type=click.Path(), help="Output directory or file path.")
@click.option("--timeout", default=15, type=int, help="Request timeout in seconds.")
@click.option("--max-image-size", default=50, type=int, help="Max cumulative image size in MB.")
@click.option("--no-headless", is_flag=True, default=False, help="Show browser window.")
def main(url: str, output: str, timeout: int, max_image_size: int, no_headless: bool) -> None:
    """Convert a web article URL to EPUB3."""
    cfg = ConversionConfig(
        timeout_seconds=timeout,
        max_image_size_mb=max_image_size,
        headless=not no_headless,
    )

    try:
        epub_bytes = convert(url, cfg)
    except ConversionError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)

    meta = _parse_epub_meta(epub_bytes)

    output_path = Path(output)
    if output_path.is_dir() or not output_path.suffix:
        fname = meta.get("filename") or _fallback_filename()
        output_path = output_path / fname if output_path.is_dir() else Path(fname)

    output_path.write_bytes(epub_bytes)

    size_mb = len(epub_bytes) / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb >= 0.1 else f"{len(epub_bytes) / 1024:.0f} KB"
    embedded = meta.get("images-embedded", "0")
    placeholders = meta.get("images-placeholders", "0")
    reading_time = meta.get("reading-time", "")

    click.echo(f"output:       {output_path.resolve()}")
    click.echo(f"size:         {size_str}")
    click.echo(f"images:       {embedded} embedded, {placeholders} placeholders")
    if reading_time:
        click.echo(f"reading time: {reading_time}")


def _parse_epub_meta(epub_bytes: bytes) -> dict:
    """Extract title and custom metadata from EPUB bytes without re-fetching."""
    result: dict = {}
    try:
        with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            cn_ns = "urn:oasis:names:tc:opendocument:xmlns:container"
            rootfile = container.find(f".//{{{cn_ns}}}rootfile")
            if rootfile is None:
                return result
            opf_path = rootfile.get("full-path", "")
            if not opf_path:
                return result

            opf = ET.fromstring(zf.read(opf_path))
            dc_ns = "http://purl.org/dc/elements/1.1/"
            opf_ns = "http://www.idpf.org/2007/opf"

            title_el = opf.find(f".//{{{dc_ns}}}title")
            if title_el is not None and title_el.text:
                result["filename"] = _title_to_filename(title_el.text)

            for m in opf.findall(f".//{{{opf_ns}}}meta"):
                name = m.get("name", "")
                content = m.get("content", "")
                if name and content:
                    result[name] = content
    except Exception:
        pass
    return result


def _title_to_filename(title: str) -> str:
    import re
    slug = re.sub(r"\s+", "-", title.lower())
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug[:80].strip("-")
    if slug:
        return f"{slug}.epub"
    return _fallback_filename()


def _fallback_filename() -> str:
    from datetime import datetime, timezone
    return f"{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S')}.epub"


if __name__ == "__main__":
    main()
