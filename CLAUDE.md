# Leafbound — Claude Code Instructions

## What This Project Is

Leafbound is a local Python CLI tool that converts a web article URL into a self-contained EPUB3 binary optimized for e-reader consumption. It preserves tables, images, and semantic structure that read-later tools strip.

## Non-Negotiable Architectural Rule

The conversion pipeline is a **pure Python library** (`src/`) with no filesystem or network I/O other than what is explicitly passed as parameters. The CLI (`src/cli.py`) is a thin wrapper that resolves config, calls the library, and writes the output file.

The library's public contract is:

```python
def convert(url: str, config: ConversionConfig) -> bytes:
    ...
```

It returns raw EPUB bytes. It does not write files. It does not print to stdout. This interface must not change — it is the seam for Phase 2 web service integration.

## Project Layout

```
src/
├── __init__.py        # exports convert() and ConversionConfig
├── fetch.py           # two-stage fetch pipeline
├── extract.py         # article body + metadata extraction
├── assets.py          # image download, Pillow processing, rasterization
├── builder.py         # EPUB3 assembly via ebooklib
└── cli.py             # CLI entry point via click
tests/
├── urls.txt           # 15 test URLs (do not modify)
├── conftest.py
├── test_fetch.py
├── test_extract.py
├── test_assets.py
├── test_builder.py
└── test_integration.py
.devcontainer/
├── devcontainer.json
├── post-create.sh
└── starship.toml
requirements.txt
requirements-dev.txt
README.md
CLAUDE.md
```

## Tech Stack

| Concern | Library |
|---|---|
| Initial HTTP fetch + extraction | `trafilatura` |
| Article body isolation | `readability-lxml` |
| Headless browser | `playwright` (Chromium only) |
| EPUB assembly | `ebooklib` |
| Image processing | `Pillow` |
| HTML parsing | `lxml` |
| CLI | `click` |
| Linting + formatting | `ruff` |
| Testing | `pytest` |

All versions pinned in `requirements.txt`. Do not add dependencies without updating `requirements.txt`.

## Dev Container

Base image: `mcr.microsoft.com/devcontainers/base:debian-13`

Uses features for setup:
- Python 3.12 (`ghcr.io/devcontainers/features/python`)
- `uv` package manager (`ghcr.io/va-h/devcontainers-features/uv`)
- Git, zsh, Starship prompt, and Claude Code extension

The `postCreateCommand` runs `.devcontainer/postCreate.sh`, which:
1. Configures Starship prompt and zsh plugins (autosuggestions, completions)
2. Sets git config (safe.directory, user.name, user.email)
3. Installs Python dependencies via `uv pip install -r requirements.txt -r requirements-dev.txt --system --no-deps`

Never install packages directly in the running container. Add to `requirements.txt` or `requirements-dev.txt` and rebuild.

## Conversion Pipeline

### Stage 1 — HTTP fetch
Use `trafilatura` to fetch and extract. If the result is below 200 words, proceed to Stage 2.

### Stage 2 — Headless browser fallback
Use Playwright with Chromium. Wait strategy: `networkidle`. Hard timeout: value from `ConversionConfig.timeout_seconds` (default 15). Expose no other Playwright configuration.

### Extraction
Pass the fetched HTML to `readability-lxml` to isolate the article body. Strip everything outside the article: nav, ads, footers, cookie banners, comment sections.

### Metadata extraction
Priority order:
1. OpenGraph tags
2. JSON-LD (`Article` or `NewsArticle` schema)
3. Standard HTML `<meta>` elements
4. Heuristic fallback: first `<h1>` as title, current timestamp as date

Omit fields that cannot be resolved. Do not populate with placeholder values.

### Image handling
- Thread pool: `concurrent.futures.ThreadPoolExecutor`, max 4 workers
- Per-image timeout: 10 seconds
- Retries: 1
- On failure: insert a styled placeholder block with the original `src` URL as visible text and alt attribute
- Track cumulative embedded image size against `ConversionConfig.max_image_size_mb` (default 50)
- Images that would exceed the cap: replace with placeholder, do not abort
- Pillow processing on every image: normalize format (WebP/AVIF → JPEG), strip metadata, re-encode

### Table and SVG rasterization
- Identify `<table>` and `<svg>` elements in the extracted body
- Render each in isolation using Playwright (reuse the existing browser instance if one was opened in Stage 2)
- Screenshot at 2x resolution, PNG format
- Replace the original element in the HTML with an `<img>` pointing to the embedded asset
- This is mandatory — do not pass raw tables or SVGs to ebooklib

### EPUB assembly
- Format: EPUB3
- Default device profile: Kobo / standard EPUB3
- Reading time: compute from word count at 238 wpm, inject as EPUB subtitle and custom metadata field
- Output filename derivation: lowercase title, replace whitespace with hyphens, strip non-alphanumeric characters, truncate to 80 characters, append `.epub`. Fallback: `YYYY-MM-DD-HHmmss.epub`

## ConversionConfig

```python
@dataclass
class ConversionConfig:
    timeout_seconds: int = 15
    max_image_size_mb: int = 50
    headless: bool = True
```

## CLI Flags

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `url` | positional | required | passed directly to `convert()` |
| `--output` | path | cwd | resolved before calling `convert()` |
| `--timeout` | int | 15 | `ConversionConfig.timeout_seconds` |
| `--max-image-size` | int | 50 | `ConversionConfig.max_image_size_mb` |
| `--no-headless` | flag | False | `ConversionConfig.headless = False` |

## Error Handling Rules

- All network operations must have explicit timeouts. No operation may block indefinitely.
- On Playwright timeout: log diagnostic to stderr, return partial EPUB if body text was extracted, raise `ConversionError` if nothing was extracted.
- On total extraction failure: raise `ConversionError` with a clear message. The CLI catches this and exits with code 1.
- On image fetch failure: insert placeholder, continue. Never abort conversion for an image failure.
- No silent failures anywhere in the pipeline.

## Terminal Output Format

After successful conversion, print to stdout:

```
output:       /path/to/article-title.epub
size:         1.2 MB
images:       14 embedded, 2 placeholders
reading time: 8 min
```

On failure, print the error to stderr and exit with code 1.

## Code Quality

- Type hints on all function signatures, no exceptions
- `ruff` for linting and formatting — must pass with zero warnings
- No globals
- No abbreviations except: `url`, `epub`, `svg`, `png`, `html`, `cfg`
- Each module has a single clear responsibility matching its filename

## Testing

Run with `pytest`. The test suite must pass completely before any Phase 1 release.

`tests/urls.txt` contains 15 URLs covering:
- Static news article (2 URLs)
- Substack post (2 URLs)
- Medium article (2 URLs)
- Wikipedia page with complex tables (2 URLs)
- Article with embedded SVG (2 URLs)
- Article with heavy image load (2 URLs)
- Paywalled article — expected graceful failure, not crash (3 URLs)

Do not modify `urls.txt`. If a URL goes dead, flag it and leave the line commented out.

Integration tests call `convert()` directly with real URLs. They are slow and require network access. Mark them with `@pytest.mark.integration` and exclude from the default test run with `-m "not integration"`. CI runs all tests including integration.

## What Not To Do

- Do not add logging via `print()` inside the library — use Python's `logging` module at DEBUG level
- Do not write files inside the library — only the CLI writes files
- Do not add async — the pipeline is synchronous; concurrency is limited to the image thread pool
- Do not add a database, cache, or state persistence of any kind
- Do not add dependencies without updating `requirements.txt`
- Do not catch bare `Exception` — catch specific exceptions and re-raise as `ConversionError` where appropriate
