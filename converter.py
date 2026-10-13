"""Convert tabular files between CSV, Excel, JSON, XML, and Markdown.

The functions here do not import Streamlit, so they can be tested on their own.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import pandas as pd
from defusedxml.ElementTree import parse as parse_xml
from defusedxml.common import DefusedXmlException

try:
    import pdfplumber
except ImportError:  # pragma: no cover - exercised when the extra is absent
    pdfplumber = None

SUPPORTED_INPUTS = [".csv", ".xlsx", ".xls", ".json", ".xml", ".pdf", ".md"]
SUPPORTED_OUTPUTS = ["CSV", "Excel (.xlsx)", "JSON", "XML", "Markdown"]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 25
_SNIFF_BYTES = 64 * 1024


@dataclass
class Table:
    name: str
    frame: pd.DataFrame


@dataclass
class Export:
    data: bytes
    mime: str
    extension: str
    note: str = ""


def load_tables(source, suffix: str) -> tuple[list[Table], list[str]]:
    """Read an uploaded file into one or more tables.

    `source` may be raw bytes or a binary file object. `suffix` is the input
    extension, with or without a leading dot.
    """
    data = _read_bytes(source)
    if not data:
        raise ValueError("The file is empty.")

    kind = _normalize_suffix(suffix)
    warnings: list[str] = []
    if kind == ".csv":
        tables = [_csv_table(data, warnings)]
    elif kind in (".xlsx", ".xls"):
        tables = _excel_tables(data)
    elif kind == ".json":
        tables = [_json_table(data, warnings)]
    elif kind == ".xml":
        tables = _xml_tables(data, warnings)
    elif kind == ".pdf":
        tables = _pdf_tables(data, warnings)
    elif kind in {".md", ".markdown"}:
        tables = _markdown_tables(data)
    else:
        supported = ", ".join(SUPPORTED_INPUTS)
        raise ValueError(f"Unsupported input '{kind}'. Use one of: {supported}.")

    if not tables:
        raise ValueError("No tabular data was found in the file.")
    return tables, warnings


def export_tables(tables: list[Table], output: str) -> Export:
    """Serialize tables to the selected output format."""
    if not tables:
        raise ValueError("Nothing to export.")

    kind = _normalize_output(output)
    if kind == "csv":
        return _export_csv(tables)
    if kind == "excel":
        return _export_excel(tables)
    if kind == "json":
        return _export_json(tables)
    if kind == "xml":
        return _export_xml(tables)
    if kind == "markdown":
        return _export_markdown(tables)
    raise ValueError(f"Unsupported output format: {output}")


def _read_bytes(source) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    data = source.read()
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def _normalize_suffix(suffix: str) -> str:
    text = (suffix or "").strip().lower()
    if not text:
        return ""
    return text if text.startswith(".") else f".{text}"


def _normalize_output(output: str) -> str:
    text = (output or "").strip().lower()
    if text == "csv" or text.startswith("csv"):
        return "csv"
    if "excel" in text or text in {"xlsx", "xls"}:
        return "excel"
    if text == "json" or text.startswith("json"):
        return "json"
    if text == "xml" or text.startswith("xml"):
        return "xml"
    if text in {"markdown", "md"} or text.startswith("markdown"):
        return "markdown"
    raise ValueError(f"Unsupported output format: {output}")


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _csv_table(data: bytes, warnings: list[str]) -> Table:
    text = _decode_text(data)
    if not text.strip():
        raise ValueError("The CSV file is empty.")

    kwargs: dict = {}
    sample = text[:_SNIFF_BYTES]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = None
    if dialect is not None:
        kwargs["sep"] = dialect.delimiter
        if dialect.quotechar:
            kwargs["quotechar"] = dialect.quotechar
        if dialect.delimiter != ",":
            warnings.append(f"Detected '{dialect.delimiter}' as the CSV delimiter.")

    try:
        frame = pd.read_csv(io.StringIO(text), **kwargs)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("The CSV file has no rows.") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"Could not parse the CSV file: {exc}") from exc
    return Table("Data", frame)


def _excel_tables(data: bytes) -> list[Table]:
    try:
        workbook = pd.ExcelFile(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Could not read the Excel file: {exc}") from exc
    tables = []
    for sheet in workbook.sheet_names:
        tables.append(Table(str(sheet), workbook.parse(sheet)))
    if not tables:
        raise ValueError("The Excel file has no sheets.")
    return tables


def _json_table(data: bytes, warnings: list[str]) -> Table:
    text = _decode_text(data)
    if not text.strip():
        raise ValueError("The JSON file is empty.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload, skipped = _read_json_lines(text)
        if not payload:
            raise ValueError("Could not parse JSON. Expected a JSON value or one JSON object per line.")
        if skipped:
            warnings.append(f"Skipped {skipped} line(s) that were not valid JSON.")
        else:
            warnings.append("Read the file as JSON Lines.")
    frame = _frame_from_json(payload)
    if frame.empty:
        warnings.append("The JSON value did not contain any rows.")
    return Table("Data", frame)


def _read_json_lines(text: str) -> tuple[list, int]:
    rows = []
    skipped = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            skipped += 1
    return rows, skipped


def _is_sequence(value) -> bool:
    return isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes))


def _frame_from_json(payload) -> pd.DataFrame:
    if isinstance(payload, list):
        if not payload:
            return pd.DataFrame()
        if all(isinstance(item, dict) for item in payload):
            return pd.json_normalize(payload)
        return pd.DataFrame({"value": payload})
    if isinstance(payload, dict):
        values = list(payload.values())
        if values and all(_is_sequence(value) for value in values):
            lengths = {len(value) for value in values}
            if len(lengths) == 1:
                return pd.DataFrame(payload)
        return pd.json_normalize(payload)
    return pd.DataFrame({"value": [payload]})


def _xml_tables(data: bytes, warnings: list[str]) -> list[Table]:
    try:
        root = parse_xml(io.BytesIO(data)).getroot()
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ValueError(f"Could not parse XML: {exc}") from exc

    exported = _tables_from_dataset(root)
    if exported:
        return exported

    groups = _record_groups(root)
    if not groups:
        frame = _flat_xml_frame(root)
        if frame.empty:
            raise ValueError("The XML file has no elements to convert.")
        warnings.append("No repeating records were found. Exported each element as a row.")
        return [Table("Data", frame)]

    largest = max(len(elements) for elements in groups.values())
    if largest == 1:
        chosen = [max(groups.items(), key=lambda item: _richness(item[1][0]))]
    else:
        chosen = [(name, elements) for name, elements in groups.items() if len(elements) >= 2]

    tables = []
    used_names: set[str] = set()
    for name, elements in chosen:
        sheet = name if name not in used_names else _unique_name(name, used_names)
        used_names.add(sheet)
        tables.append(Table(sheet, _rows_to_frame(elements)))
    return tables


def _tables_from_dataset(root: ET.Element) -> list[Table] | None:
    """Read XML written by this app, including one element per sheet."""
    if _local_name(root.tag) != "dataset":
        return None
    tables = []
    for sheet in list(root):
        if _local_name(sheet.tag) != "sheet":
            return None
        rows = [child for child in list(sheet) if _local_name(child.tag) == "row"]
        if not rows:
            continue
        tables.append(Table(sheet.attrib.get("name") or "Data", _rows_to_frame(rows)))
    return tables or None


def _local_name(tag: str) -> str:
    text = str(tag)
    if text.startswith("{"):
        text = text.split("}", 1)[-1]
    return text or "field"


def _record_groups(root: ET.Element) -> dict[str, list[ET.Element]]:
    """Group repeating elements that look like table rows.

    A row is either a parent of leaf tags (`<item><id>1</id></item>`) or a
    leaf with attributes (`<item id="1" name="Ada"/>`). Bare text tags such as
    `<id>1</id>` are not rows, so they are not chosen over the records that
    contain them.
    """
    groups: dict[str, list[ET.Element]] = {}
    for element in root.iter():
        if not _is_record(element):
            continue
        groups.setdefault(_local_name(element.tag), []).append(element)
    return groups


def _is_record(element: ET.Element) -> bool:
    children = list(element)
    if children:
        return all(len(list(child)) == 0 for child in children)
    return len(element.attrib) > 0


def _richness(element: ET.Element) -> int:
    return len(list(element)) + len(element.attrib)


def _rows_to_frame(elements: list[ET.Element]) -> pd.DataFrame:
    rows = []
    for element in elements:
        row: dict[str, str] = {}
        for child in list(element):
            key = _unique_key(_local_name(child.tag), row)
            row[key] = (child.text or "").strip()
        for attr, value in element.attrib.items():
            key = _unique_key(f"@{_local_name(attr)}", row)
            row[key] = value
        rows.append(row)
    return pd.DataFrame(rows)


def _unique_key(key: str, row: dict) -> str:
    if key not in row:
        return key
    index = 2
    while f"{key}_{index}" in row:
        index += 1
    return f"{key}_{index}"


def _flat_xml_frame(root: ET.Element) -> pd.DataFrame:
    rows = []
    for element in root.iter():
        rows.append(
            {
                "tag": _local_name(element.tag),
                "text": (element.text or "").strip(),
                **{f"@{_local_name(key)}": value for key, value in element.attrib.items()},
            }
        )
    return pd.DataFrame(rows)


def _pdf_tables(data: bytes, warnings: list[str]) -> list[Table]:
    if pdfplumber is None:
        warnings.append("PDF support requires pdfplumber. Returning a short text snippet instead.")
        snippet = data[:2000].decode("latin-1", errors="ignore")
        return [Table("Text", pd.DataFrame({"text": [snippet]}))]

    tables: list[Table] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        pages = pdf.pages[:MAX_PDF_PAGES]
        if page_count > MAX_PDF_PAGES:
            warnings.append(f"Scanned the first {MAX_PDF_PAGES} of {page_count} pages.")
        for page_number, page in enumerate(pages, start=1):
            extracted = page.extract_tables() or []
            found = 0
            for grid in extracted:
                frame = _grid_to_frame(grid)
                if frame is None:
                    continue
                found += 1
                tables.append(Table(f"Page{page_number}_Table{found}", frame))
        if tables:
            return tables
        texts = [(page.extract_text() or "") for page in pages[: min(3, len(pages))]]
    warnings.append("No tables were found in the PDF. Exported page text instead.")
    return [Table("Text", pd.DataFrame({"text": texts or [""]}))]


def _grid_to_frame(grid) -> pd.DataFrame | None:
    rows = [list(row) for row in grid or [] if row and any(cell not in (None, "") for cell in row)]
    if not rows:
        return None
    header = rows[0]
    body = rows[1:]
    if _looks_like_header(header) and body:
        columns = _dedupe_headers(header)
        width = len(columns)
        records = [_pad(row, width) for row in body]
        return pd.DataFrame(records, columns=columns)
    width = max(len(row) for row in rows)
    records = [_pad(row, width) for row in rows]
    columns = [f"column_{index}" for index in range(1, width + 1)]
    return pd.DataFrame(records, columns=columns)


def _looks_like_header(row) -> bool:
    values = [cell for cell in row if cell not in (None, "")]
    return bool(values) and all(isinstance(cell, str) for cell in values)


def _dedupe_headers(header) -> list[str]:
    seen: dict[str, int] = {}
    columns = []
    for index, cell in enumerate(header, start=1):
        name = "" if cell is None else str(cell).strip()
        if not name:
            name = f"column_{index}"
        count = seen.get(name, 0) + 1
        seen[name] = count
        columns.append(name if count == 1 else f"{name}_{count}")
    return columns


def _pad(row, width: int) -> list:
    values = list(row[:width])
    if len(values) < width:
        values.extend([None] * (width - len(values)))
    return values


def _markdown_tables(data: bytes) -> list[Table]:
    """Read GitHub-style pipe tables, the same shape MarkItDown writes."""
    lines = _decode_text(data).splitlines()
    tables: list[Table] = []
    heading = "Data"
    used_names: set[str] = set()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip() or "Data"
            index += 1
            continue
        if _is_markdown_table(lines, index):
            header = _split_markdown_row(lines[index])
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_split_markdown_row(lines[index]))
                index += 1
            columns = _dedupe_headers(header)
            width = len(columns)
            frame = pd.DataFrame([_pad(row, width) for row in rows], columns=columns)
            tables.append(Table(_unique_name(heading, used_names), frame))
            heading = "Data"
            continue
        index += 1
    if not tables:
        raise ValueError(
            "No Markdown tables were found. Use a pipe table with a header and a --- separator row."
        )
    return tables


def _is_markdown_table(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or not lines[index].strip().startswith("|"):
        return False
    return _is_markdown_separator(lines[index + 1])


def _is_markdown_separator(line: str) -> bool:
    cells = _split_markdown_row(line) if "|" in line else []
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _export_markdown(tables: list[Table]) -> Export:
    parts = []
    several = len(tables) > 1
    for index, table in enumerate(tables, start=1):
        block = _frame_to_markdown(table.frame)
        if several:
            title = (table.name or f"Sheet{index}").replace("\n", " ").strip() or f"Sheet{index}"
            block = f"# {title}\n\n{block}"
        parts.append(block)
    raw = "\n\n".join(parts).rstrip() + "\n"
    return Export(data=raw.encode("utf-8"), mime="text/markdown", extension="md")


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    columns = ["" if column is None else str(column) for column in frame.columns]
    if not columns:
        return ""
    header = "| " + " | ".join(_markdown_cell(column) for column in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for record in _records(frame):
        values = [
            _markdown_cell("" if record.get(column) is None else record.get(column))
            for column in frame.columns
        ]
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *body])


def _markdown_cell(value) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    return text.replace("\r\n", " ").replace("\n", " ").strip()


def _export_csv(tables: list[Table]) -> Export:
    if len(tables) == 1:
        return Export(
            data=_frame_to_csv_bytes(tables[0].frame),
            mime="text/csv",
            extension="csv",
        )
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table in tables:
            filename = _unique_name(_safe_filename(table.name), used) + ".csv"
            archive.writestr(filename, _frame_to_csv_bytes(table.frame))
    return Export(
        data=buffer.getvalue(),
        mime="application/zip",
        extension="zip",
        note="CSV holds one table, so each sheet was saved as its own CSV inside a zip file.",
    )


def _frame_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")


def _export_excel(tables: list[Table]) -> Export:
    buffer = io.BytesIO()
    used: set[str] = set()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for table in tables:
            sheet = _excel_sheet_name(table.name, used)
            table.frame.to_excel(writer, index=False, sheet_name=sheet)
    return Export(
        data=buffer.getvalue(),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        extension="xlsx",
    )


def _export_json(tables: list[Table]) -> Export:
    records = [_records(table.frame) for table in tables]
    if len(tables) == 1:
        payload = records[0]
    else:
        payload = [{"sheet": table.name, "rows": rows} for table, rows in zip(tables, records)]
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    return Export(data=raw.encode("utf-8"), mime="application/json", extension="json")


def _records(frame: pd.DataFrame):
    if frame.empty and len(frame.columns) == 0:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def _export_xml(tables: list[Table]) -> Export:
    root = ET.Element("dataset")
    for index, table in enumerate(tables, start=1):
        sheet = ET.SubElement(root, "sheet", name=table.name or f"Sheet{index}")
        tags = _xml_tags(list(table.frame.columns))
        for record in _records(table.frame):
            row = ET.SubElement(sheet, "row")
            for tag, column in zip(tags, table.frame.columns):
                cell = ET.SubElement(row, tag)
                value = record.get(column)
                cell.text = "" if value is None else str(value)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return Export(data=xml_bytes, mime="application/xml", extension="xml")


def _xml_tags(columns: list) -> list[str]:
    seen: dict[str, int] = {}
    tags = []
    for column in columns:
        base = _xml_tag(column)
        count = seen.get(base, 0) + 1
        seen[base] = count
        tags.append(base if count == 1 else f"{base}_{count}")
    return tags


def _xml_tag(name) -> str:
    text = "" if name is None else str(name).strip()
    text = re.sub(r"[^A-Za-z0-9_.-]", "_", text)
    text = text.strip("._-") or "field"
    if text.lower().startswith("xml"):
        text = f"f_{text}"
    if not (text[0].isalpha() or text[0] == "_"):
        text = f"f_{text}"
    return text


def _excel_sheet_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[:\\/?*\[\]]", "_", str(name)).strip() or "Sheet"
    return _unique_name(cleaned[:31], used, limit=31)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", str(name)).strip() or "sheet"
    return cleaned[:80]


def _unique_name(name: str, used: set[str], limit: int | None = None) -> str:
    candidate = name or "sheet"
    if candidate not in used:
        used.add(candidate)
        return candidate
    index = 2
    while True:
        suffix = f"_{index}"
        base = candidate
        if limit is not None:
            base = candidate[: max(1, limit - len(suffix))]
        renamed = f"{base}{suffix}"
        if renamed not in used:
            used.add(renamed)
            return renamed
        index += 1
