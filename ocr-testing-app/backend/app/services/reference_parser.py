"""
Excel/CSV reference data parser.

Parses reference data files into a list of field dictionaries.

Supports two formats:
- 3-column (legacy): field_name, raw_value, resolved_value
- 5-column (new):    page, section, field, raw_value, resolved_value
  The new format uses classifier field names (e.g., "date_of_birth") as field_name
  for direct matching against classification results.

Auto-detection: if column A header contains "page" (case-insensitive),
the file is parsed as 5-column format.
"""
import io
import csv
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _extract_checked_value(raw_value: str) -> str:
    """Extract the checked value from a checkbox-style string.

    Examples:
        "▢ M  ☑ F" -> "F"
        "☑ Yes  ▢ No" -> "Yes"
        "☑ White  ▢ Black  ▢ Hispanic" -> "White"
    """
    # Find text after ☑ before next ▢ or end
    match = re.search(r"☑\s*([^▢☑]+)", raw_value)
    if match:
        return match.group(1).strip()
    return raw_value.strip()


def _is_5_column_format(headers) -> bool:
    """Detect if the file uses the new 5-column format.
    Check if the first header contains 'page' (case-insensitive).
    """
    if not headers or len(headers) < 5:
        return False
    first_header = str(headers[0]).strip().lower() if headers[0] else ""
    return first_header in ("page", "page_number", "page_num", "pg")


def _parse_row_5col(row) -> Dict[str, str]:
    """Parse a row in 5-column format: page, section, field, raw_value, resolved_value."""
    page = str(row[0]).strip() if row[0] is not None else ""
    section = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
    field_name = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
    raw_value = str(row[3]).strip() if len(row) > 3 and row[3] is not None else ""
    resolved_value = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""

    if not field_name:
        return None

    # Strip leading * (required field marker)
    if field_name.startswith("*"):
        field_name = field_name.lstrip("*").strip()

    # Skip rows where both raw and resolved are empty
    if not raw_value and not resolved_value:
        return None

    # Auto-resolve checkbox values
    if not resolved_value and "☑" in raw_value:
        resolved_value = _extract_checked_value(raw_value)

    if not resolved_value:
        resolved_value = raw_value

    return {
        "page": page,
        "section": section,
        "field_name": field_name,
        "raw_value": raw_value,
        "resolved_value": resolved_value,
    }


def _parse_row_3col(row) -> Dict[str, str]:
    """Parse a row in legacy 3-column format: field_name, raw_value, resolved_value."""
    field_name = str(row[0]).strip() if row[0] is not None else ""
    if not field_name:
        return None

    # Strip leading *
    if field_name.startswith("*"):
        field_name = field_name.lstrip("*").strip()

    raw_value = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
    resolved_value = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""

    if not raw_value and not resolved_value:
        return None

    if not resolved_value and "☑" in raw_value:
        resolved_value = _extract_checked_value(raw_value)

    if not resolved_value:
        resolved_value = raw_value

    return {
        "field_name": field_name,
        "raw_value": raw_value,
        "resolved_value": resolved_value,
    }


def parse_reference_excel(file_bytes: bytes) -> List[Dict[str, str]]:
    """Parse reference data from an Excel (.xlsx) file.

    Auto-detects 3-column (legacy) vs 5-column (new) format.
    Returns list of dicts with at minimum: {field_name, raw_value, resolved_value}
    and optionally: {page, section} for the 5-column format.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active

    # Read header row to detect format
    headers = []
    for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
        headers = list(row)
        break

    is_5col = _is_5_column_format(headers)
    logger.info(f"Excel reference format: {'5-column (page/section/field)' if is_5col else '3-column (legacy)'}")

    fields = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not any(cell is not None for cell in row):
            continue

        parsed = _parse_row_5col(row) if is_5col else _parse_row_3col(row)
        if parsed:
            fields.append(parsed)

    wb.close()
    logger.info(f"Parsed {len(fields)} reference fields from Excel")
    return fields


def parse_reference_csv(file_bytes: bytes) -> List[Dict[str, str]]:
    """Parse reference data from a CSV file.

    Auto-detects 3-column (legacy) vs 5-column (new) format.
    """
    text = file_bytes.decode("utf-8-sig")  # Handle BOM
    reader = csv.reader(io.StringIO(text))

    # Read header
    headers = None
    for row in reader:
        headers = row
        break

    if not headers:
        return []

    is_5col = _is_5_column_format(headers)
    logger.info(f"CSV reference format: {'5-column (page/section/field)' if is_5col else '3-column (legacy)'}")

    fields = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue

        parsed = _parse_row_5col(row) if is_5col else _parse_row_3col(row)
        if parsed:
            fields.append(parsed)

    logger.info(f"Parsed {len(fields)} reference fields from CSV")
    return fields


def parse_reference_file(file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
    """Parse reference data from either Excel or CSV based on filename."""
    if filename.lower().endswith((".xlsx", ".xls")):
        return parse_reference_excel(file_bytes)
    elif filename.lower().endswith(".csv"):
        return parse_reference_csv(file_bytes)
    else:
        raise ValueError(f"Unsupported reference file format: {filename}. Use .xlsx or .csv")
