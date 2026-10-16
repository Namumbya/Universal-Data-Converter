# Universal Data Converter

Convert CSV, Excel, JSON, XML, Markdown, PDF, and Word files in the browser.

Upload a file, preview it, and download CSV, Excel, JSON, XML, Markdown, PDF, or Word. A Word or Markdown file can be downloaded as a PDF or Word document of the full text. Sample files are in [samples](samples).

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer.

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

- PDF table extraction is best-effort and does not read scanned pages. At most 25 pages are scanned. Pages with no table are kept as text. A PDF download keeps the first 2,000 rows of each table.
- CSV and Excel cells that look like formulas (`=`, `+`, `@`, or a minus sign that is not a number) are prefixed with `'` so the spreadsheet does not run them.
- Word and Excel files that would expand past 200 MB are refused.
- A workbook downloaded as CSV is a zip with one CSV per sheet. Markdown keeps every sheet in one file.
- Markdown to CSV, Excel, JSON, XML, or Markdown keeps pipe tables only (`| column |` and a `| --- |` row). Markdown to PDF or Word keeps the whole document: headings, lists, prose, code, and tables.
- Output formats include Markdown (.md), PDF (.pdf), and Word (.docx). Word to PDF and Markdown to PDF or Word preview and download the document itself. PDF to Word keeps the extracted tables. A PDF that mixes tables and prose keeps both: the tables, and the text from pages that have none.
