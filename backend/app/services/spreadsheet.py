"""Shared helpers for the CSV and Excel exports.

Every export cell goes through safe_cell so a name like "=HYPERLINK(...)"
is stored as text and never runs as a formula when the file is opened.
"""

from datetime import UTC, datetime
from io import BytesIO

from fastapi import Response
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DATE_FORMAT = "yyyy-mm-dd hh:mm"
FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_cell(value):
    """Prefix text that a spreadsheet would read as a formula with '."""
    if isinstance(value, str) and value.lstrip().startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def excel_datetime(value: str | datetime | None) -> datetime | None:
    """A report timestamp as a naive UTC datetime, which Excel can store."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def _excel_value(value):
    value = safe_cell(value)
    if isinstance(value, str):
        # openpyxl refuses control characters, so drop them rather than fail.
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def new_workbook() -> Workbook:
    """An empty workbook; add_sheet adds every sheet, in order."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    return workbook


def add_sheet(workbook: Workbook, title: str, header: list[str], rows) -> Worksheet:
    """Add a sheet with a bold header row; datetimes get a date format."""
    sheet = workbook.create_sheet(title)

    sheet.append([_excel_value(value) for value in header])
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in rows:
        sheet.append([_excel_value(value) for value in row])

    for column in sheet.iter_cols(min_row=2):
        for cell in column:
            if isinstance(cell.value, datetime):
                cell.number_format = DATE_FORMAT

    sheet.freeze_panes = "A2"
    return sheet


def add_key_value_sheet(workbook: Workbook, title: str, pairs) -> Worksheet:
    """A two-column "Field / Value" sheet for report summaries."""
    sheet = add_sheet(workbook, title, ["Field", "Value"], pairs)
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 40
    return sheet


def xlsx_response(workbook: Workbook, filename: str) -> Response:
    output = BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
