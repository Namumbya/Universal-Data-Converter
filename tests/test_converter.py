import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import pytest

import converter
from converter import Table, export_tables, load_tables

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def test_sample_csv_round_trips_to_json_and_xml():
    tables, warnings = load_tables((SAMPLES / "sample.csv").read_bytes(), ".csv")

    assert warnings == []
    assert tables[0].frame["name"].tolist() == ["Alice", "Bob", "Carol"]

    payload = json.loads(export_tables(tables, "JSON").data)
    assert payload[1]["name"] == "Bob"
    assert payload[1]["amount"] == 9.0

    xml_export = export_tables(tables, "XML")
    ET.fromstring(xml_export.data)
    reloaded, _ = load_tables(xml_export.data, ".xml")
    assert reloaded[0].frame["name"].tolist() == ["Alice", "Bob", "Carol"]
    assert reloaded[0].frame["amount"].tolist() == ["10.5", "9.0", "12.75"]


def test_semicolon_and_tab_delimiters_are_detected():
    tables, warnings = load_tables(b"id;name;amount\n1;Alice;10.5\n", "csv")
    assert tables[0].frame.loc[0, "name"] == "Alice"
    assert any(";" in warning for warning in warnings)

    tabbed, _ = load_tables(b"id\tname\n1\tAda\n", ".csv")
    assert tabbed[0].frame.loc[0, "name"] == "Ada"


def test_csv_encodings():
    bom, _ = load_tables("name\nAdèle\n".encode("utf-8-sig"), ".csv")
    assert bom[0].frame.loc[0, "name"] == "Adèle"

    latin, _ = load_tables("name,city\nAda,Café\n".encode("cp1252"), ".csv")
    assert latin[0].frame.loc[0, "city"] == "Café"


def test_sample_json_and_json_shapes():
    tables, _ = load_tables((SAMPLES / "sample.json").read_bytes(), ".json")
    assert tables[0].frame["name"].tolist() == ["Alice", "Bob"]

    columns, _ = load_tables(json.dumps({"id": [1, 2], "name": ["A", "B"]}).encode(), ".json")
    assert columns[0].frame["name"].tolist() == ["A", "B"]

    nested, _ = load_tables(json.dumps({"user": {"id": 1, "name": "Ada"}}).encode(), ".json")
    assert nested[0].frame.loc[0, "user.name"] == "Ada"

    lines, warnings = load_tables(
        b'{"id": 1, "name": "Ada"}\nnot-json\n{"id": 2, "name": "Bea"}\n',
        ".json",
    )
    assert lines[0].frame["name"].tolist() == ["Ada", "Bea"]
    assert warnings


def test_sample_xml_reads_nested_records_not_an_empty_column():
    tables, warnings = load_tables((SAMPLES / "sample.xml").read_bytes(), ".xml")

    assert warnings == []
    frame = tables[0].frame
    assert frame["name"].tolist() == ["Alice", "Bob"]
    assert frame["amount"].tolist() == ["10.5", "9.0"]
    assert "item" not in frame.columns or frame["name"].notna().all()


def test_xml_attributes_become_columns():
    raw = b"""<root>
      <item id="1"><name>Ada</name></item>
      <item id="2"><name>Bea</name></item>
    </root>"""
    tables, _ = load_tables(raw, ".xml")
    frame = tables[0].frame
    assert frame["name"].tolist() == ["Ada", "Bea"]
    assert frame["@id"].tolist() == ["1", "2"]


def test_xml_export_uses_legal_tags_and_omits_missing_values():
    frame = pd.DataFrame(
        [{"First Name": "Alice", "1amount": 10, "a/b": "x", "note": float("nan")}]
    )
    exported = export_tables([Table("Data", frame)], "XML")
    ET.fromstring(exported.data)

    reloaded, _ = load_tables(exported.data, ".xml")
    row = reloaded[0].frame.iloc[0]
    assert row["First_Name"] == "Alice"
    assert row["f_1amount"] == "10"
    assert row["a_b"] == "x"
    assert row["note"] == ""


def test_xml_with_entity_declaration_is_rejected():
    payload = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY x "boom">]>
    <root><item><name>&x;</name></item></root>"""
    with pytest.raises(ValueError, match="XML"):
        load_tables(payload, ".xml")


def test_excel_sheet_names_survive_excel_json_and_csv_zip():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"name": ["Ada"]}).to_excel(writer, sheet_name="People", index=False)
        pd.DataFrame({"sku": ["A-1"]}).to_excel(writer, sheet_name="Items", index=False)

    tables, _ = load_tables(buffer.getvalue(), ".xlsx")
    assert [table.name for table in tables] == ["People", "Items"]

    excel = export_tables(tables, "Excel (.xlsx)")
    reloaded, _ = load_tables(excel.data, ".xlsx")
    assert [table.name for table in reloaded] == ["People", "Items"]
    assert reloaded[1].frame.loc[0, "sku"] == "A-1"

    payload = json.loads(export_tables(tables, "JSON").data)
    assert payload[0]["sheet"] == "People"
    assert payload[1]["rows"][0]["sku"] == "A-1"

    zipped = export_tables(tables, "CSV")
    assert zipped.extension == "zip"
    with zipfile.ZipFile(io.BytesIO(zipped.data)) as archive:
        assert set(archive.namelist()) == {"People.csv", "Items.csv"}
        assert b"Ada" in archive.read("People.csv")


def test_missing_empty_and_unknown_files():
    with pytest.raises(ValueError, match="empty"):
        load_tables(b"", ".csv")
    with pytest.raises(ValueError, match="Unsupported"):
        load_tables(b"abc", ".txt")
    with pytest.raises(ValueError, match="JSON"):
        load_tables(b"[][]", ".json")


def test_pdf_tables_headers_and_page_cap(monkeypatch):
    class Page:
        def __init__(self, number):
            self.number = number

        def extract_tables(self):
            seen.append(self.number)
            if self.number == 1:
                return [[["id", "id", None], ["1", "2", "x"]]]
            return []

        def extract_text(self):
            return f"page {self.number}"

    class Document:
        pages = [Page(number) for number in range(1, 31)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    seen = []
    monkeypatch.setattr(converter.pdfplumber, "open", lambda *_args, **_kwargs: Document())

    tables, warnings = load_tables(b"%PDF", ".pdf")
    assert seen == list(range(1, 26))
    assert list(tables[0].frame.columns) == ["id", "id_2", "column_3"]
    assert tables[0].frame.iloc[0].tolist() == ["1", "2", "x"]
    assert any("25" in warning for warning in warnings)


def test_pdf_without_tables_exports_text(monkeypatch):
    class Page:
        def extract_tables(self):
            return []

        def extract_text(self):
            return "Hello from the PDF"

    class Document:
        pages = [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(converter.pdfplumber, "open", lambda *_args, **_kwargs: Document())
    tables, warnings = load_tables(b"%PDF", ".pdf")
    assert tables[0].frame.loc[0, "text"] == "Hello from the PDF"
    assert any("No tables" in warning for warning in warnings)


def test_markdown_round_trip_matches_markitdown_tables():
    tables, _ = load_tables((SAMPLES / "sample.csv").read_bytes(), ".csv")
    exported = export_tables(tables, "Markdown")
    text = exported.data.decode("utf-8")
    assert text.startswith("| id | name | amount |")
    assert "| --- | --- | --- |" in text

    reloaded, warnings = load_tables(exported.data, ".md")
    assert warnings == []
    assert reloaded[0].frame["name"].tolist() == ["Alice", "Bob", "Carol"]

    sample, _ = load_tables((SAMPLES / "sample.md").read_bytes(), ".markdown")
    assert sample[0].frame.loc[1, "name"] == "Bob"


def test_markdown_escapes_pipes_and_keeps_multiple_sheets():
    people = Table("People", pd.DataFrame([{"note": "a|b"}]))
    items = Table("Items", pd.DataFrame([{"sku": "A-1"}]))
    exported = export_tables([people, items], "Markdown")
    assert r"a\|b" in exported.data.decode("utf-8")

    reloaded, _ = load_tables(exported.data, ".md")
    assert [table.name for table in reloaded] == ["People", "Items"]
    assert reloaded[0].frame.loc[0, "note"] == "a|b"
    assert reloaded[1].frame.loc[0, "sku"] == "A-1"


def test_output_choices_include_markdown_and_pdf():
    assert "Markdown (.md)" in converter.SUPPORTED_OUTPUTS
    assert "PDF (.pdf)" in converter.SUPPORTED_OUTPUTS
    assert "Word (.docx)" in converter.SUPPORTED_OUTPUTS
    assert ".docx" in converter.SUPPORTED_INPUTS


def test_csv_exports_to_pdf():
    tables, _ = load_tables((SAMPLES / "sample.csv").read_bytes(), ".csv")
    exported = export_tables(tables, "PDF (.pdf)")
    assert exported.extension == "pdf"
    assert exported.data.startswith(b"%PDF")


def test_word_document_converts_to_pdf():
    from docx import Document

    document = Document()
    document.add_heading("Report", level=1)
    document.add_paragraph("Hello from Word")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "name"
    table.rows[0].cells[1].text = "city"
    table.rows[1].cells[0].text = "Ada"
    table.rows[1].cells[1].text = "Paris"
    buffer = io.BytesIO()
    document.save(buffer)
    raw = buffer.getvalue()

    tables, _ = load_tables(raw, ".docx")
    assert tables[0].frame.loc[0, "name"] == "Ada"
    assert tables[0].frame.loc[0, "city"] == "Paris"

    exported = converter.docx_to_pdf(raw)
    assert exported.extension == "pdf"
    assert exported.data.startswith(b"%PDF")
    import pdfplumber

    with pdfplumber.open(io.BytesIO(exported.data)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Hello from Word" in text
    assert "Ada" in text


def test_pdf_and_word_convert_both_ways():
    tables, _ = load_tables((SAMPLES / "sample.csv").read_bytes(), ".csv")
    pdf_export = export_tables(tables, "Word (.docx)")
    assert pdf_export.extension == "docx"
    as_word, _ = load_tables(pdf_export.data, ".docx")
    assert as_word[0].frame["name"].tolist() == ["Alice", "Bob", "Carol"]

    word_pdf = converter.docx_to_pdf((SAMPLES / "sample.docx").read_bytes())
    assert word_pdf.extension == "pdf"
    from_pdf, _ = load_tables(word_pdf.data, ".pdf")
    assert "Alice" in from_pdf[0].frame.astype(str).to_string()
    back_to_word = export_tables(from_pdf, "Word (.docx)")
    reloaded, _ = load_tables(back_to_word.data, ".docx")
    assert "Alice" in reloaded[0].frame.astype(str).to_string()


def test_markdown_without_a_table_is_rejected():
    with pytest.raises(ValueError, match="Markdown"):
        load_tables(b"# Notes\n\nJust a paragraph.\n", ".md")


def test_pdf_without_pdfplumber_explains_the_gap(monkeypatch):
    monkeypatch.setattr(converter, "pdfplumber", None)
    tables, warnings = load_tables(b"%PDF-1.4 hello", ".pdf")
    assert "text" in tables[0].frame.columns
    assert any("pdfplumber" in warning for warning in warnings)
