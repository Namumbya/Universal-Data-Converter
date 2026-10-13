# Universal Data Converter

Convert CSV, Excel, JSON, XML, Markdown, and PDF tables in the browser.

Upload a file, preview the table, and download CSV, Excel, JSON, XML, or Markdown. Sample files are in [samples](samples).

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
