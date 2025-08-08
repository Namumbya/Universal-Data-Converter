
import io
import json
import csv
import xml.etree.ElementTree as ET
from typing import List, Tuple

import streamlit as st
import pandas as pd

# Optional deps used gracefully
try:
    import pdfplumber  
    HAS_PDF = True
except Exception:
    HAS_PDF = False

st.set_page_config(page_title="Universal Data Converter", page_icon="🔁", layout="wide")
st.title("🔁 Universal Data Converter")
st.caption("Convert CSV, Excel, JSON, XML, and (best-effort) PDF tables to your desired format.")

SUPPORTED_INPUTS = [".csv", ".xlsx", ".xls", ".json", ".xml", ".pdf"]
SUPPORTED_OUTPUTS = ["CSV", "Excel (.xlsx)", "JSON", "XML"]

def _read_csv(file) -> List[pd.DataFrame]:
    df = pd.read_csv(file)
    return [df]

def _read_excel(file) -> List[pd.DataFrame]:
    xls = pd.ExcelFile(file)
    return [xls.parse(sheet_name) for sheet_name in xls.sheet_names]

def _read_json(file) -> List[pd.DataFrame]:
    raw = file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        # Try JSONL
        file.seek(0)
        lines = []
        for line in file:
            try:
                lines.append(json.loads(line))
            except Exception:
                pass
        data = lines

    if isinstance(data, list):
        df = pd.json_normalize(data)
    elif isinstance(data, dict):
        try:
            df = pd.DataFrame(data)
        except Exception:
            df = pd.json_normalize(data)
    else:
        df = pd.DataFrame({"value": [str(data)]})
    return [df]

def _read_xml(file) -> List[pd.DataFrame]:
    try:
        file.seek(0)
        df = pd.read_xml(file)
        return [df]
    except Exception:
        file.seek(0)
        tree = ET.parse(file)
        root = tree.getroot()
        rows = []
        columns = set()
        for child in root.iter():
            if len(list(child)) and all(len(list(c)) == 0 for c in child):
                row = {k.tag: (k.text or "").strip() for k in child}
                rows.append(row)
                columns.update(row.keys())
        if rows:
            df = pd.DataFrame(rows, columns=sorted(columns))
        else:
            flat = []
            for elem in root.iter():
                flat.append({"tag": elem.tag, "text": (elem.text or "").strip(), **elem.attrib})
            df = pd.DataFrame(flat)
        return [df]

def _read_pdf(file) -> List[pd.DataFrame]:
    if not HAS_PDF:
        st.warning("PDF support requires pdfplumber. Returning raw text snippet.")
        return [pd.DataFrame({"text": [file.getvalue()[:2000].decode('latin-1', errors='ignore')]})]
    dfs = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages[:5]:
            tables = page.extract_tables()
            for t in tables or []:
                if not t:
                    continue
                if all(isinstance(x, str) for x in t[0]):
                    header = t[0]
                    rows = t[1:]
                    df = pd.DataFrame(rows, columns=header)
                else:
                    df = pd.DataFrame(t)
                dfs.append(df)
    if not dfs:
        with pdfplumber.open(file) as pdf:
            texts = [page.extract_text() or "" for page in pdf.pages[:3]]
        return [pd.DataFrame({"text": texts})]
    return dfs

def read_file(uploaded_file, suffix: str) -> List[pd.DataFrame]:
    suffix = suffix.lower()
    if suffix == ".csv":
        return _read_csv(uploaded_file)
    if suffix in (".xlsx", ".xls"):
        return _read_excel(uploaded_file)
    if suffix == ".json":
        return _read_json(uploaded_file)
    if suffix == ".xml":
        return _read_xml(uploaded_file)
    if suffix == ".pdf":
        return _read_pdf(uploaded_file)
    raise ValueError(f"Unsupported input: {suffix}")

def df_to_bytes(dfs: List[pd.DataFrame], output: str) -> tuple[bytes, str]:
    output = output.lower()
    if output == "csv":
        buf = io.StringIO()
        dfs[0].to_csv(buf, index=False)
        return buf.getvalue().encode("utf-8"), "text/csv"
    if output.startswith("excel"):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for i, df in enumerate(dfs, start=1):
                df.to_excel(writer, index=False, sheet_name=f"Sheet{i}")
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if output == "json":
        data = [df.to_dict(orient="records") for df in dfs]
        payload = json.dumps(data[0] if len(data) == 1 else data, ensure_ascii=False, indent=2)
        return payload.encode("utf-8"), "application/json"
    if output == "xml":
        root = ET.Element("dataset")
        for idx, df in enumerate(dfs, start=1):
            sheet_el = ET.SubElement(root, "sheet", name=f"Sheet{idx}")
            for row in df.to_dict(orient="records"):
                row_el = ET.SubElement(sheet_el, "row")
                for k, v in row.items():
                    tag = k if isinstance(k, str) and k.strip() else "field"
                    cell = ET.SubElement(row_el, tag)
                    cell.text = "" if v is None else str(v)
        xml_bytes = ET.tostring(root, encoding="utf-8")
        return xml_bytes, "application/xml"
    raise ValueError("Unsupported output format.")

st.sidebar.header("Settings")
st.sidebar.write("Supported inputs: " + ", ".join(SUPPORTED_INPUTS))
out_fmt = st.sidebar.selectbox("Output format", SUPPORTED_OUTPUTS, index=0)

uploaded = st.file_uploader(
    "Upload one or more files",
    type=[s.strip(".") for s in SUPPORTED_INPUTS],
    accept_multiple_files=True,
)

if not uploaded:
    st.info("Upload files to get started. Drag & drop CSV, Excel, JSON, XML, or PDF.")
    st.stop()

for up in uploaded:
    suffix = "." + up.name.split(".")[-1].lower()
    st.divider()
    st.subheader(f"📄 {up.name}")
    try:
        dfs = read_file(up, suffix)
    except Exception as e:
        st.error(f"Could not read file: {e}")
        continue

    with st.expander("Preview", expanded=True):
        for i, df in enumerate(dfs, start=1):
            st.write(f"Sheet {i}" if len(dfs) > 1 else "Data")
            st.dataframe(df.head(100), use_container_width=True)

    try:
        data_bytes, mime = df_to_bytes(dfs, out_fmt)
        default_name = up.name.rsplit(".", 1)[0]
        ext = "csv" if out_fmt == "CSV" else ("xlsx" if out_fmt.startswith("Excel") else ("json" if out_fmt == "JSON" else "xml"))
        st.download_button(
            label=f"⬇️ Download as {out_fmt}",
            data=data_bytes,
            file_name=f"{default_name}.{ext}",
            mime=mime,
            use_container_width=True,
        )
        if out_fmt == "CSV" and len(dfs) > 1:
            st.caption("Note: CSV download includes only the first sheet. Choose Excel to export all sheets.")
    except Exception as e:
        st.error(f"Export failed: {e}")
