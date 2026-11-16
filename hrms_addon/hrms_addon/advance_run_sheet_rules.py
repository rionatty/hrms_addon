# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A salary advance run's lines as a sheet: the Download button on Salary Advance Processing (salary_advances.download;
checks: scripts/verify_advance_run_sheet.py). No Frappe import.

Luuka, 16 Nov 2026, on November's run of 721 lines: "add download functionality".

  rows       a line each, in the run's order, with the columns of the run's table and what the row form holds
  total      the last row: how many the run pays, and how much
  workbook   the sheet: headings, the lines, the total; filters on the headings, the names kept in view
"""

import io

SHEET = "Lines"
# heading, the line's field, column width, kind
COLUMNS = (
    ("No.", "idx", 6, "int"),
    ("Employee", "employee", 14, "text"),
    ("Name", "employee_name", 30, "text"),
    ("Plant", "branch", 18, "text"),
    ("Department", "department", 24, "text"),
    ("Pay Category", "pay_category", 14, "text"),
    ("Gross Pay", "gross_pay", 15, "money"),
    ("Amount", "amount", 15, "money"),
    ("Days Absent", "days_absent", 12, "int"),
    ("Days Not Marked", "days_unmarked", 16, "int"),
    ("Qualifies", "qualifies", 10, "yes"),
    ("Pay", "include", 8, "yes"),
    ("Reason", "remarks", 60, "text"),
    ("Request", "request", 22, "text"),
)
FIELDS = [field for _heading, field, _width, _kind in COLUMNS]
NAME, AMOUNT = FIELDS.index("employee_name"), FIELDS.index("amount")
MONEY = "#,##0.00"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def value(line, field, kind):
    raw = line.get(field)
    if kind == "yes":
        return "Yes" if raw else "No"
    if kind == "money":
        return round(_num(raw), 2)
    if kind == "int":
        return int(_num(raw))
    return " ".join(str(raw).split()) if raw is not None else ""


def paid(lines):
    """The lines the run pays: those that qualify and are ticked to pay."""
    return [line for line in lines or () if line.get("qualifies") and line.get("include")]


def rows(lines):
    return [[value(line, field, kind) for _heading, field, _width, kind in COLUMNS] for line in lines or ()]


def total(lines):
    out = [""] * len(COLUMNS)
    to_pay = paid(lines)
    out[NAME] = "To pay: %d of %d" % (len(to_pay), len(list(lines or ())))
    out[AMOUNT] = round(sum(_num(line.get("amount")) for line in to_pay), 2)
    return out


def file_name(month, year, name):
    return " ".join(str(part) for part in ("Salary Advance", month, year, name) if part)


def workbook(lines):
    """The sheet, as .xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    bold = Font(bold=True)
    body = [[heading for heading, _field, _width, _kind in COLUMNS]] + rows(lines) + [total(lines)]
    last = len(body)
    for row_number, values in enumerate(body, 1):
        for column, item in enumerate(values, 1):
            cell = sheet.cell(row=row_number, column=column, value=item)
            if isinstance(item, str):
                cell.data_type = "s"  # a name that starts with = is a name, never a formula
            if row_number in (1, last):
                cell.font = bold
            elif COLUMNS[column - 1][3] == "money":
                cell.number_format = MONEY
            if COLUMNS[column - 1][1] == "remarks":
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.cell(row=last, column=AMOUNT + 1).number_format = MONEY
    for column, (_heading, _field, width, _kind) in enumerate(COLUMNS, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = "D2"
    sheet.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(COLUMNS)), max(last - 1, 1))
    content = io.BytesIO()
    book.save(content)
    return content.getvalue()
