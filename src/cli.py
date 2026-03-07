"""CLI entry point for Leafbound."""
import sys
from pathlib import Path

import click

from . import ConversionError, convert
from .builder import output_filename
from .config import ConversionConfig
from .extract import ArticleMetadata


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

    output_path = Path(output)
    if output_path.is_dir() or not output_path.suffix:
        # Need filename — re-extract metadata for filename derivation

        fname = _derive_filename(url, cfg)
        output_path = output_path / fname if output_path.is_dir() else Path(fname)

    output_path.write_bytes(epub_bytes)

    size_mb = len(epub_bytes) / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb >= 0.1 else f"{len(epub_bytes) / 1024:.0f} KB"

    click.echo(f"output:       {output_path.resolve()}")
    click.echo(f"size:         {size_str}")


def _derive_filename(url: str, cfg: ConversionConfig) -> str:
    """Best-effort filename derivation without a full re-conversion."""
    try:
        from .extract import extract
        from .fetch import fetch

        html, _ = fetch(url, cfg)
        if html:
            metadata, _ = extract(html, url)
            return output_filename(metadata)
    except Exception:
        pass
    from .builder import output_filename as _of
    return _of(ArticleMetadata())


if __name__ == "__main__":
    main()
