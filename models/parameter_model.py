import re
import zipfile
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET


WORKBOOK_PATH = Path(r"C:\Users\Lenovo\Downloads\Parameter_OnProduct.xlsx")
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


GROUP_TITLES = {
    "0": "Initial Conditions (t = 0)",
    "1": "Boundary Conditions",
    "2": "Droplet & Nozzle",
    "3": "Thermophysical Properties",
    "4": "Physical Sub-Models",
    "5": "Numerical Settings",
    "6": "Validation Parameters",
}


@lru_cache(maxsize=1)
def load_parameter_groups():
    rows = _read_parameter_rows()
    groups = {}
    current_section = None

    for row in rows:
        first_cell = row.get("A", "").strip()
        parameter_name = row.get("C", "").strip()

        if first_cell and not parameter_name and _looks_like_section(first_cell):
            current_section = _build_section(first_cell)
            group_key = current_section["group_key"]
            groups.setdefault(
                group_key,
                {
                    "key": group_key,
                    "title": GROUP_TITLES.get(group_key, current_section["title"]),
                    "sections": [],
                },
            )
            groups[group_key]["sections"].append(current_section)
            continue

        if current_section and parameter_name:
            current_value = row.get("F", "").strip()
            unit = row.get("E", "").strip()
            current_section["fields"].append(
                {
                    "name": parameter_name,
                    "unit": unit,
                    "placeholder": current_value,
                    "input_type": _infer_input_type(current_value, unit),
                    "field_name": _field_name(parameter_name),
                }
            )

    return [groups[key] for key in sorted(groups, key=lambda item: int(item))]


def _read_parameter_rows():
    if not WORKBOOK_PATH.exists():
        return []

    with zipfile.ZipFile(WORKBOOK_PATH) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_xml = archive.read("xl/worksheets/sheet1.xml")

    root = ET.fromstring(sheet_xml)
    rows = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        row_data = {}
        for cell in row.findall("a:c", NS):
            column = re.match(r"[A-Z]+", cell.attrib["r"]).group(0)
            row_data[column] = _cell_value(cell, shared_strings)
        rows.append(row_data)
    return rows


def _read_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("a:si", NS):
        strings.append("".join(text.text or "" for text in item.findall(".//a:t", NS)))
    return strings


def _cell_value(cell, shared_strings):
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", NS))

    value = cell.find("a:v", NS)
    if value is None:
        return ""

    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text or ""


def _looks_like_section(value):
    return bool(re.match(r"^\d+(?:\.\d+)?\s*[. ]", value))


def _build_section(value):
    match = re.match(r"^(\d+(?:\.\d+)?)\s*\.?\s*(.+)$", value.strip())
    number = match.group(1)
    title = match.group(2).strip()
    return {
        "number": number,
        "title": title,
        "group_key": number.split(".")[0],
        "fields": [],
    }


def _field_name(parameter_name):
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", parameter_name.lower()).strip("_")
    return slug or "parameter"


def _infer_input_type(current_value, unit):
    normalized = current_value.strip().lower()
    if normalized in {"true", "false", "yes", "no", "on", "off"}:
        return "text"

    simple_number = re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?", normalized)
    if simple_number:
        return "number"

    if unit and unit not in {"-", "--", "—"} and re.match(r"^[-+]?\d+(?:[.,]\d+)?", normalized):
        return "number"

    return "text"
