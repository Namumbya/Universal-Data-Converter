# Universal Data Converter

Convert CSV, Excel, JSON, XML, Markdown, PDF, and Word files in the browser.

Upload a file, preview it, and download CSV, Excel, JSON, XML, Markdown, or PDF. A Word file (`.docx`) can be downloaded as a PDF. Sample files are in [samples](samples).

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 or newer.

```bash
uv sync
uv run streamlit run app.py
```

Open the URL Streamlit prints. Uploads are limited to 50 MB.

## Tests

```bash
uv sync --group dev
uv run pytest
```

## Deploy

On Streamlit Community Cloud, set the main file to `app.py`. Cloud installs the packages in `requirements.txt`.

## Notes

- PDF table extraction is best-effort and does not read scanned pages. At most 25 pages are scanned.
- A workbook downloaded as CSV is a zip with one CSV per sheet. Markdown keeps every sheet in one file.
- Markdown input must be a pipe table (`| column |` and a `| --- |` row).
- Output formats include Markdown (.md), PDF (.pdf), and Word (.docx). Word to PDF keeps the document text and tables. PDF to Word keeps the extracted tables.
