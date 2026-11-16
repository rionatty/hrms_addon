# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A salary advance run's bank file, as Luuka's own ADVANCE_PAYMENT workbook (salary_advances.bank_file; checks:
scripts/verify_advance_payment.py). No Frappe import.

Luuka, 16 Nov 2026, sending their "ADVANCE_PAYMENT NOVEMBER 2026" workbook: "this is the bank file".

  ADVANCE_PAYMENT  those paid by bank: Sr. No., Payroll No., Employee Name, Bank Name, Bank Code, Bank Account No.,
                   Advance Amount; by bank, then by payroll number; then TOTAL, and below it CASH (the cash report's
                   total) and GRAND TOTAL, as formulas, as theirs
  CASH REPORT      those paid any other way: SALARY ADVANCE CASH REPORT FOR <MONTH>; SNO, EMP NO, EMP NAME,
                   DEPARTMENT, AMOUNT; TOTAL

The lines are those the run pays: they qualify, are ticked to pay, and have something to pay. Who is paid by bank, the
bank as written with its branch, and the code are bank_file_rules', as the payroll's file. A code or an account number
is a number, as theirs, unless a nought leads it or it is too long for Excel to hold whole: then it is text, and Excel
is told so on purpose. One paid by bank with no account number, bank or code is in the file with that cell blank, and
the check says so (Luuka, 13 Nov 2026: "if moble phone/ bank account ist should be blank on that employee").
"""

import io
import re

from hrms_addon.hrms_addon import bank_file_rules as bank

SHEET, CASH_SHEET = "ADVANCE_PAYMENT", "CASH REPORT"
HEADER = ("Sr. No.", "Payroll No.", "Employee Name", "Bank Name", "Bank Code", "Bank Account No.", "Advance Amount")
CASH_HEADER = ("SNO", "EMP NO", "EMP NAME", "DEPARTMENT", "AMOUNT")
# as Luuka's own file looks
FONT, SIZE = "Verdana", 10
WIDTHS = (("A", 8.6), ("B", 9.6), ("C", 38.6), ("D", 37.6), ("E", 13.7), ("F", 22.4), ("G", 26.9))
CASH_WIDTHS = (("C", 11.4), ("D", 23.3), ("E", 17.6), ("F", 11.4))
MONEY = "#,##0.00"
WHOLE = "0"
# the cash report's title row, its headings on the next, its lines from the one after
CASH_TITLE_ROW = 4
# the longest number Excel holds to the last digit
LONGEST_NUMBER = 15


def paid(lines):
    """The lines the run pays: they qualify, are ticked to pay, and have something to pay."""
    return [line for line in lines or ()
            if line.get("qualifies") and line.get("include") and round(bank.number(line.get("amount")), 2) > 0]


def by_bank(lines):
    return [line for line in paid(lines) if bank.paid_by_bank(line)]


def in_cash(lines):
    return [line for line in paid(lines) if not bank.paid_by_bank(line)]


def digits(value):
    """A code or an account number as Luuka's file has it: a number, unless a nought leads it or it is too long for
    Excel to hold whole, then text; nothing for nothing."""
    text = bank.compact(value)
    if not text:
        return None
    if text.isdigit() and not text.startswith("0") and len(text) <= LONGEST_NUMBER:
        return int(text)
    return text


def _payroll_number(employee):
    """EMP111 before EMP347 before EMP1088: the number in a payroll number."""
    found = re.findall(r"\d+", str(employee or ""))
    return int(found[0]) if found else -1


def _bank_alone(line):
    """The bank without its branch, however the bracket is spaced: ABSA BANK (BRANCH) and ABSA BANK(BRANCH) are one."""
    return bank.clean(bank.clean(line.get("bank_name")).upper().split("(", 1)[0])


def department(name):
    """PIB from "PIB Department - LPL": the department as Luuka's cash report writes it."""
    text = re.sub(r"\s+-\s+[^-]+$", "", bank.clean(name))
    return re.sub(r"\s+department$", "", text, flags=re.IGNORECASE).upper()


def _amount(line):
    return round(bank.number(line.get("amount")), 2)


def bank_rows(lines):
    """[(Sr. No., Payroll No., Employee Name, Bank Name, Bank Code, Bank Account No., Advance Amount)], by bank, then by
    payroll number, as Luuka's file runs."""
    ordered = sorted(by_bank(lines), key=lambda line: (_bank_alone(line), _payroll_number(line.get("employee")),
                                                       bank.clean(line.get("employee"))))
    return [(number, bank.clean(line.get("employee")), bank.clean(line.get("employee_name")).upper(),
             bank.bank_label(line.get("bank_name"), line.get("bank_branch")) or None, digits(line.get("bank_code")),
             digits(line.get("bank_ac_no")), _amount(line))
            for number, line in enumerate(ordered, 1)]


def cash_rows(lines):
    """[(SNO, EMP NO, EMP NAME, DEPARTMENT, AMOUNT)], by department, then by payroll number."""
    ordered = sorted(in_cash(lines), key=lambda line: (department(line.get("department")),
                                                       _payroll_number(line.get("employee")),
                                                       bank.clean(line.get("employee"))))
    return [(number, bank.clean(line.get("employee")), bank.clean(line.get("employee_name")).upper(),
             department(line.get("department")) or None, _amount(line))
            for number, line in enumerate(ordered, 1)]


def title(month):
    return "SALARY ADVANCE CASH REPORT FOR %s" % bank.clean(month).upper()


def file_name(month, year):
    return " ".join(part for part in ("ADVANCE_PAYMENT", bank.clean(month).upper(), bank.clean(year)) if part)


def workbook(month, body, cash):
    """The file as .xlsx bytes: the bank's sheet, then the cash report, in Luuka's own look."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    report = book.create_sheet(CASH_SHEET)
    thin, medium = Side(style="thin"), Side(style="medium")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    heavy = Border(left=medium, right=medium, top=medium, bottom=medium)
    plain, bold = Font(name=FONT, size=SIZE), Font(name=FONT, size=SIZE, bold=True)
    left, centre = Alignment(horizontal="left"), Alignment(horizontal="center")

    def put(target, row, column, value, font=plain, border=box, align=None, number_format=None, formula=False):
        cell = target.cell(row=row, column=column, value=value)
        if isinstance(value, str) and not formula:
            cell.data_type = "s"  # a name that starts with = is a name, never a formula
        cell.font = font
        if border:
            cell.border = border
        if align:
            cell.alignment = align
        if number_format:
            cell.number_format = number_format
        return cell

    # the cash report first, so the bank's sheet knows where its total is
    put(report, CASH_TITLE_ROW, 2, title(month), bold, None, centre)
    report.merge_cells(start_row=CASH_TITLE_ROW, start_column=2, end_row=CASH_TITLE_ROW, end_column=6)
    for column, heading in enumerate(CASH_HEADER, 2):
        put(report, CASH_TITLE_ROW + 1, column, heading, bold)
    first = CASH_TITLE_ROW + 2
    for row, values in enumerate(cash, first):
        for column, value in enumerate(values, 2):
            put(report, row, column, value, number_format=MONEY if column == 6 else None)
    cash_total = first + len(cash)
    put(report, cash_total, 2, "TOTAL", bold, heavy, centre)
    for column in (3, 4, 5):
        put(report, cash_total, column, None, bold, heavy)
    report.merge_cells(start_row=cash_total, start_column=2, end_row=cash_total, end_column=5)
    put(report, cash_total, 6, "=SUM(F%d:F%d)" % (first, cash_total - 1) if cash else 0, bold, heavy,
        number_format=MONEY, formula=True)
    for letter, width in CASH_WIDTHS:
        report.column_dimensions[letter].width = width

    for column, heading in enumerate(HEADER, 1):
        put(sheet, 1, column, heading, bold)
    for row, values in enumerate(body, 2):
        for column, value in enumerate(values, 1):
            # a code or account kept as a number shows every digit: in General, Excel writes 13 digits as 9.03E+12
            put(sheet, row, column, value, align=left if column in (5, 6) else None,
                number_format=MONEY if column == 7 else WHOLE if column in (5, 6) and isinstance(value, int) else None)
    total = len(body) + 2
    put(sheet, total, 1, "TOTAL", bold, heavy, centre)
    for column in range(2, 7):
        put(sheet, total, column, None, bold, heavy)
    sheet.merge_cells(start_row=total, start_column=1, end_row=total, end_column=6)
    put(sheet, total, 7, "=SUM(G2:G%d)" % (total - 1) if body else 0, bold, heavy, number_format=MONEY,
        formula=True)
    put(sheet, total + 3, 6, " CASH", border=None, align=left)
    put(sheet, total + 3, 7, "='%s'!F%d" % (CASH_SHEET, cash_total), border=None, number_format=MONEY, formula=True)
    put(sheet, total + 4, 6, "GRAND TOTAL", bold, None, left)
    put(sheet, total + 4, 7, "=G%d+G%d" % (total, total + 3), bold, None, number_format=MONEY, formula=True)
    for letter, width in WIDTHS:
        sheet.column_dimensions[letter].width = width
    book.active = 0
    content = io.BytesIO()
    book.save(content)
    content = content.getvalue()
    if body:
        # the codes and account numbers kept as text are text on purpose: no green corner on them
        content = bank.text_on_purpose(content, "E2:F%d" % (total - 1))
    return content
