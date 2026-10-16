from pathlib import Path

import streamlit as st

from converter import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_INPUTS,
    SUPPORTED_OUTPUTS,
    docx_preview_text,
    docx_to_pdf,
    export_tables,
    load_tables,
    markdown_preview_text,
    markdown_to_docx,
    markdown_to_pdf,
)

_MARKDOWN_SUFFIXES = {".md", ".markdown"}


def _document_output_kind(out_fmt: str) -> str | None:
    text = out_fmt.lower()
    if text.startswith("pdf"):
        return "pdf"
    if text.startswith("word") or "docx" in text:
        return "word"
    return None

ROOT = Path(__file__).resolve().parent
SAMPLES = {
    "CSV": ROOT / "samples" / "sample.csv",
    "JSON": ROOT / "samples" / "sample.json",
    "XML": ROOT / "samples" / "sample.xml",
    "Markdown": ROOT / "samples" / "sample.md",
    "Word": ROOT / "samples" / "sample.docx",
    "PDF": ROOT / "samples" / "sample.pdf",
}
PREVIEW_ROWS = 100


@st.cache_data(show_spinner=False, max_entries=4, ttl=600)
def cached_load(raw: bytes, suffix: str):
    return load_tables(raw, suffix)


@st.cache_data(show_spinner=False, max_entries=4, ttl=600)
def cached_export(raw: bytes, suffix: str, out_fmt: str):
    document_kind = _document_output_kind(out_fmt)
    if document_kind == "pdf" and suffix == ".docx":
        return docx_to_pdf(raw)
    if suffix in _MARKDOWN_SUFFIXES and document_kind == "pdf":
        return markdown_to_pdf(raw)
    if suffix in _MARKDOWN_SUFFIXES and document_kind == "word":
        return markdown_to_docx(raw)
    tables, _warnings = cached_load(raw, suffix)
    return export_tables(tables, out_fmt)


@st.cache_data(show_spinner=False, max_entries=4, ttl=600)
def cached_docx_preview(raw: bytes) -> str:
    return docx_preview_text(raw)


@st.cache_data(show_spinner=False, max_entries=4, ttl=600)
def cached_markdown_preview(raw: bytes) -> str:
    return markdown_preview_text(raw)


class NamedUpload:
    """In-memory file with the attributes the converter and UI expect."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self.size = len(data)
        self._data = data

    def read(self) -> bytes:
        return self._data


st.set_page_config(page_title="Universal Data Converter", page_icon="🔁", layout="wide")
st.title("🔁 Universal Data Converter")
st.caption("Convert CSV, Excel, JSON, XML, Markdown, PDF, and Word files in the browser.")

st.sidebar.header("Settings")
out_fmt = st.sidebar.selectbox("Output format", SUPPORTED_OUTPUTS, index=0)
sample_name = st.sidebar.selectbox("Try a sample", ["None", *SAMPLES.keys()], index=0)
st.sidebar.caption(
    "Uploads are limited to 50 MB. "
    f"Accepted types: {', '.join(SUPPORTED_INPUTS)}."
)
st.sidebar.caption("PDF table extraction is best-effort and does not OCR scanned pages.")

uploaded = st.file_uploader(
    "Upload one or more files",
    type=[item.strip(".") for item in SUPPORTED_INPUTS],
    accept_multiple_files=True,
)

if uploaded and sample_name != "None":
    st.caption("Using the uploaded files. Remove them to load the sample instead.")

sources = list(uploaded or [])
if not sources and sample_name != "None":
    sample_path = SAMPLES[sample_name]
    sources = [NamedUpload(sample_path.name, sample_path.read_bytes())]

if not sources:
    st.info("Upload a file, or pick a sample in the sidebar, to preview it and download a conversion.")
    st.stop()

for index, upload in enumerate(sources):
    suffix = Path(upload.name).suffix.lower()
    st.divider()
    st.subheader(upload.name)

    size = getattr(upload, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        st.error(f"{upload.name} is larger than 50 MB.")
        continue
    if not suffix:
        st.error(f"{upload.name} needs a file extension such as .csv or .xlsx.")
        continue

    raw = upload.getvalue() if hasattr(upload, "getvalue") else upload.read()
    document_kind = _document_output_kind(out_fmt)
    preview_document = (document_kind == "pdf" and suffix == ".docx") or (
        document_kind is not None and suffix in _MARKDOWN_SUFFIXES
    )
    if preview_document:
        tables, warnings = [], []
    else:
        try:
            tables, warnings = cached_load(raw, suffix)
        except Exception as exc:
            st.error(f"Could not read {upload.name}: {exc}")
            continue

    for warning in warnings:
        st.warning(warning)

    with st.expander(f"Preview — {upload.name}", expanded=True):
        if preview_document:
            label = "PDF" if document_kind == "pdf" else "Word file"
            st.caption(f"Preview of the document that will be downloaded as a {label}.")
            preview = cached_docx_preview(raw) if suffix == ".docx" else cached_markdown_preview(raw)
            st.text_area(
                "Document",
                value=preview,
                height=420,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            for table in tables:
                rows, cols = table.frame.shape
                label = table.name if len(tables) > 1 else "Data"
                st.write(f"{label}: {rows} rows × {cols} columns")
                if rows > PREVIEW_ROWS:
                    st.caption(f"Showing the first {PREVIEW_ROWS} of {rows} rows.")
                st.dataframe(table.frame.head(PREVIEW_ROWS), width="stretch")

    try:
        exported = cached_export(raw, suffix, out_fmt)
    except Exception as exc:
        st.error(f"Could not convert {upload.name}: {exc}")
        continue

    stem = Path(upload.name).stem or "converted"
    download_name = f"{stem}.{exported.extension}"
    st.download_button(
        label=f"Download {download_name}",
        data=exported.data,
        file_name=download_name,
        mime=exported.mime,
        width="stretch",
        key=f"download-{index}-{download_name}",
    )
    if exported.note:
        st.caption(exported.note)
