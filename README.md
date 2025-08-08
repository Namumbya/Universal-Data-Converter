# 🔁 Universal Data Converter (Streamlit)

Convert CSV, Excel, JSON, XML, and (best‑effort) PDF tables into your desired format — right in the browser.

## Features
- Upload **CSV, Excel (.xlsx/.xls), JSON, XML, PDF**
- Convert to **CSV / Excel (.xlsx) / JSON / XML**
- Preview before download
- Multi‑sheet Excel support (exports all sheets to a single .xlsx)
- Best‑effort PDF table extraction via `pdfplumber` (no Java required)

## Quickstart (local)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Cloud)
- Push to GitHub with `app.py` and `requirements.txt`
- Create an app from your repo; set main file to `app.py`

## Notes
- PDF extraction is best‑effort; quality depends on the PDF's structure.
- For complex PDFs or scans, consider dedicated OCR/tabular services. This app will gracefully fallback to text.