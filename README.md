# Leafbound

Convert any web article URL into a clean, well-formatted EPUB3 file optimized for e-reader consumption.

Leafbound preserves what read-later tools discard: tables, diagrams, images, and semantic structure. It runs entirely locally inside a dev container and produces a self-contained EPUB binary as output.

---

## Requirements

- Docker (for the dev container)
- VS Code with the Dev Containers extension, or any devcontainer-compatible editor

No local Python installation required. Everything runs inside the container.

---

## Getting Started

```bash
# Clone the repository
git clone https://github.com/Virgil-Bulens/leafbound.git
cd leafbound

# Open in VS Code and reopen in container when prompted
code .
```

The container build installs all dependencies and Chromium automatically. Expect the first build to take 3–5 minutes due to Playwright's Chromium binary. Subsequent builds are cached.

Once inside the container, build the CLI:

```bash
uv pip install -e . --system --no-deps
```

Then add the Python bin directory to your PATH if `leafbound` is not found:

```bash
echo 'export PATH="/usr/local/python/3.12.13/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

---

## Usage

```bash
leafbound <url> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `url` | The URL of the article to convert. Must be a fully qualified HTTP or HTTPS URL. |

### Options

| Flag | Default | Description |
|---|---|---|
| `--output PATH` | Current directory | Output file path or directory. If a directory is given, the filename is derived from the article title. |
| `--timeout SECONDS` | `15` | Playwright page load timeout in seconds. Increase for slow sites. |
| `--max-image-size MB` | `50` | Cap on total embedded image size. Images beyond the cap are replaced with placeholder blocks. |
| `--no-headless` | Off | Runs Playwright in non-headless mode. Useful for debugging extraction failures. |

### Examples

```bash
# Basic conversion, output to current directory
leafbound https://example.com/some-article

# Specify output directory
leafbound https://example.com/some-article --output ~/ebooks/

# Specify exact output path
leafbound https://example.com/some-article --output ~/ebooks/article.epub

# Debug a site with a visible browser window
leafbound https://example.com/some-article --no-headless
```

---

## How It Works

Leafbound uses a two-stage extraction pipeline.

**Stage 1 — HTTP fetch**: Fetches the page with a standard HTTP request and runs it through trafilatura and readability-lxml to extract the article body. If the extracted text is below 200 words, the page is treated as JavaScript-rendered and the pipeline falls back to Stage 2.

**Stage 2 — Headless browser**: Playwright loads the page in headless Chromium and waits for `networkidle` (up to the configured timeout). The rendered DOM is then passed to the extraction layer.

After extraction, images are downloaded in parallel (4 concurrent connections, 10-second timeout per image, one retry). Complex tables and SVG elements are rasterized via Playwright at 2x resolution and embedded as images to ensure correct rendering across all e-reader devices.

Metadata — title, author, publication date, source URL — is extracted from OpenGraph tags, JSON-LD structured data, and standard meta elements, in that priority order. The output filename is derived from the article title.

---

## Output

The EPUB3 file includes:

- Article body with preserved formatting
- All images embedded (up to the configured size cap)
- Tables and SVGs rasterized as images
- Populated metadata: title, author, date, source URL
- Reading time estimate (injected as subtitle)

The terminal output after conversion reports: output path, file size, image count, placeholder count (for failed image fetches), and reading time estimate.

---

## Known Limitations

- Sites with aggressive bot detection may block headless browser extraction. `--no-headless` may bypass simple detection; there is no automated workaround for sites that actively fingerprint browser environments.
- Paywalled articles will produce output limited to whatever content is accessible without authentication.
- Table and SVG content is rasterized and therefore non-selectable and non-searchable in e-reader software.

---

## Development

### Project Structure

```
leafbound/
├── .devcontainer/
│   ├── devcontainer.json
├── src/
│   ├── __init__.py
│   ├── fetch.py          # Two-stage fetch pipeline
│   ├── extract.py        # Article body + metadata extraction
│   ├── assets.py         # Image fetch, rasterization, Pillow processing
│   ├── builder.py        # EPUB3 assembly via ebooklib
│   └── cli.py            # CLI entry point
├── tests/
│   ├── urls.txt          # Test suite URL list
│   └── test_conversion.py
├── requirements.txt
└── README.md
```

### Running the Test Suite

```bash
pytest tests/
```

The test suite covers 15 URLs across: static news articles, Substack posts, Medium articles, Wikipedia pages with tables, articles with embedded SVG, and paywalled articles (expected graceful failure). All 15 must pass before a Phase 1 release is considered complete.

### Adding a Dependency

Add it to `requirements.txt` and rebuild the container. Do not install packages directly in the running container — they will not persist across container rebuilds.

---

## Roadmap

| Phase | Target |
|---|---|
| Phase 1 | Local CLI (current) |
| Phase 2 | Web service — HTTP API wrapping the conversion core |
| Phase 3 | Browser extension — Chrome DOM extraction, delegates conversion to Phase 2 API |
| Phase 4 | Mobile app — share sheet integration, delegates to Phase 2 API |

The conversion core (`src/` library) is deliberately isolated from I/O so that Phases 2–4 wrap it without modification.

---

## License

Free for personal and non-commercial use under the
[PolyForm Noncommercial License 1.0.0](LICENSE).
Commercial use requires a separate license.
