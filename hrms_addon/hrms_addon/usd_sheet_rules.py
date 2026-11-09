# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A USD payroll in shillings, laid out as Luuka's own expatriate payroll
sheet (Luuka, 10 Nov 2026: "where the UGX values for USD payroll").

One row a salary slip, in the sheet's columns: S/N, EMP.No, NAME, DEPT,
BASIC USD, RATE, NET(SHS), ALLOWANCE, TOTAL NET, GROSS, LST, TOTAL GROSS,
PAYE, NSSF 5%, NSSF 10%, NSSF 15%, ADVANCE, T.D, NETPAY. The shilling
figures are the USD structure's own, worked out in shillings before any
cent is rounded (currency_payroll_rules.gross_up_amounts), so they are
Luuka's to the shilling, where the slip's USD lines times the rate can be a
few shillings off. ADVANCE is what the slip takes back through Additional
Salary (an advance's recovery, a loan's, a penalty), in shillings as it was
recorded. T.D is PAYE, NSSF 5%, LST and ADVANCE; NETPAY is TOTAL GROSS less
T.D, as the sheet has them.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_usd_sheet.py runs it without a bench.
"""

import datetime
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

# (fieldname, label, fieldtype, width, decimals)
COLUMNS = (
    ("idx", "S/N", "Int", 50, 0),
    ("employee", "EMP.No", "Data", 100, None),
    ("employee_name", "NAME", "Data", 220, None),
    ("department", "DEPT", "Data", 120, None),
    ("basic_usd", "BASIC USD", "Float", 100, 2),
    ("rate", "RATE", "Float", 80, 2),
    ("net", "NET(SHS)", "Float", 120, 0),
    ("allowance", "ALLOWANCE", "Float", 110, 0),
    ("total_net", "TOTAL NET", "Float", 120, 0),
    ("gross", "GROSS", "Float", 120, 0),
    ("lst", "LST", "Float", 90, 0),
    ("total_gross", "TOTAL GROSS", "Float", 120, 0),
    ("paye", "PAYE", "Float", 120, 0),
    ("nssf_5", "NSSF 5%", "Float", 110, 0),
    ("nssf_10", "NSSF 10%", "Float", 110, 0),
    ("nssf_15", "NSSF 15%", "Float", 110, 0),
    ("advance", "ADVANCE", "Float", 110, 0),
    ("deductions", "T.D", "Float", 120, 0),
    ("net_pay", "NETPAY", "Float", 120, 0),
)
# the columns the total row leaves empty: a count and a rate add up to nothing
NOT_ADDED = ("idx", "employee", "employee_name", "department", "rate")

MONTHS = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER",
          "NOVEMBER", "DECEMBER")


def columns():
    """The columns, as the form's table takes them."""
    return [{"fieldname": name, "label": label, "fieldtype": fieldtype, "width": width, "precision": decimals}
            for name, label, fieldtype, width, decimals in COLUMNS]


def shilling(value):
    """To the shilling, a half up."""
    value = _num(value)
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def department_label(department, company_abbr=None):
    """The department without the company's abbreviation the site adds to its name."""
    text = (department or "").strip()
    if company_abbr and text.endswith(" - %s" % company_abbr):
        text = text[: -len(" - %s" % company_abbr)]
    return text


def sheet_row(idx, person, figures):
    """One slip's row. person: employee, employee_name, department. figures, in shillings unless said, each as
    worked out before it is rounded: usd (the USD pay, dollars), rate, allowance, gross, lst, paye, employee
    (NSSF 5%), employer (NSSF 10%), advance. Each column is its amount to the shilling, T.D and NETPAY worked out
    from the amounts before they are rounded, as the sheet's are; "exact" keeps those amounts for the total."""
    usd, rate = round(_num(figures.get("usd")), 2), _num(figures.get("rate"))
    net, allowance = usd * rate, _num(figures.get("allowance"))
    gross, lst = _num(figures.get("gross")), _num(figures.get("lst"))
    paye, nssf_5, nssf_10 = _num(figures.get("paye")), _num(figures.get("employee")), _num(figures.get("employer"))
    advance = _num(figures.get("advance"))
    deductions = paye + nssf_5 + lst + advance
    exact = {"basic_usd": usd, "net": net, "allowance": allowance, "total_net": net + allowance, "gross": gross,
             "lst": lst, "total_gross": gross + lst, "paye": paye, "nssf_5": nssf_5, "nssf_10": nssf_10,
             "nssf_15": nssf_5 + nssf_10, "advance": advance, "deductions": deductions,
             "net_pay": gross + lst - deductions}
    row = {"idx": idx, "employee": person.get("employee"), "employee_name": person.get("employee_name"),
           "department": person.get("department"), "rate": rate, "exact": exact}
    for name, value in exact.items():
        row[name] = value if name == "basic_usd" else shilling(value)
    return row


def totals(rows):
    """The total row: every amount added up before it is rounded, as the sheet's SUM is, the count and the rate
    left empty."""
    out = {"employee_name": "TOTAL:"}
    for name, _label, _fieldtype, _width, decimals in COLUMNS:
        if name in NOT_ADDED:
            continue
        total = sum(_num((row.get("exact") or {}).get(name, row.get(name))) for row in rows or ())
        out[name] = round(total, 2) if decimals else shilling(total)
    return out


def shown(rows):
    """The rows as the form shows them, and the total row last."""
    body = [{key: value for key, value in row.items() if key != "exact"} for row in rows or ()]
    return body + [dict(totals(rows), is_total=1)] if body else []


def sheet_title(end_date):
    """USD PAYROLL FOR THE MONTH OF SEPTEMBER 2026: the month the payroll's period ends in."""
    day = _date(end_date)
    return "USD PAYROLL FOR THE MONTH OF %s %d" % (MONTHS[day.month - 1], day.year) if day else "USD PAYROLL"


def workbook(company, title, rows):
    """The sheet as .xlsx bytes: the company and the title above, the columns, a row a slip, the total."""
    book = Workbook()
    sheet = book.active
    sheet.title = "UGX Payroll"
    bold = Font(bold=True)
    side = Side(style="thin", color="000000")
    box = Border(left=side, right=side, top=side, bottom=side)
    sheet.cell(row=1, column=3, value=(company or "").upper()).font = bold
    sheet.cell(row=2, column=3, value=title).font = bold
    header = 4
    for column, (_name, label, _type, width, _decimals) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=header, column=column, value=label)
        cell.font, cell.border = bold, box
        cell.alignment = Alignment(horizontal="center")
        sheet.column_dimensions[cell.column_letter].width = max(8, round(width / 7.5, 1))
    body = list(rows or ())
    for offset, row in enumerate(body + [totals(body)], start=1):
        last = offset == len(body) + 1
        for column, (name, _label, fieldtype, _width, decimals) in enumerate(COLUMNS, start=1):
            value = row.get(name)
            cell = sheet.cell(row=header + offset, column=column, value=value)
            cell.border = box
            if last:
                cell.font = bold
            if fieldtype in ("Float", "Int") and value is not None:
                whole = float(value) == int(float(value))
                cell.number_format = "#,##0" if (decimals == 0 or whole) else "#,##0.00"
            elif fieldtype == "Data":
                # text, always: a name that begins with = is not a formula
                cell.value = "" if value is None else str(value)
                cell.data_type = "s"
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
