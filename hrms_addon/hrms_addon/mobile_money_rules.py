# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a payroll's mobile money file holds, and how it is laid out (mobile_money.py; checks:
scripts/verify_mobile_money.py). No Frappe import.

Luuka, 13 Nov 2026, on a casuals' weekly payroll whose Bank File found nobody paid by bank: "some employee have cash
paymebt through mobile moneny ist necessary that the bank file should be only bank account employee. on the payroll
this bank file for casuals as attached". The file attached is the one the team sends the bank for the casuals' mobile
money: TO BANK REPORT FOR THE PERIOD 05TH TO 11TH NOVEMBER, WEEK TWO.

  title           the sheet's first line: the period, and the week of the month a weekly payroll's ends in
  phone           a Wages Phone Number as the bank takes it: nine digits, and with the country's 256 before them
  lines_to_pay    those paid by mobile money: not by bank or cheque, with a phone number, something to pay
  problems        a phone number that is not one: the file waits for it, as the bank file waits for an account
  rows            each line as the sheet has it, the smallest amount first
  workbook        the sheet, in the team's own look
"""

import datetime
import io
import re
from decimal import ROUND_HALF_UP, Decimal

HEADER = ("SN", "EMP NO", "Telephone", "Telephone", "AMOUNT", "Surname", "Firstname", "Registered Name")
SHEET = "Sheet1"
COUNTRY = "256"
BANK, CHEQUE = "Bank", "Cheque"
FONT, SIZE = "Verdana", 14
ROW_HEIGHT = 19.5
WIDTHS = (("A", 7.3), ("B", 19.7), ("C", 21.6), ("D", 23.3), ("E", 22.0), ("F", 32.9), ("G", 33.3), ("H", 48.1))
AMOUNT_FORMAT = '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-'
NUMBER_FORMAT = "0"
WEEKS = ("ONE", "TWO", "THREE", "FOUR", "FIVE")
MONTHS = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER",
          "NOVEMBER", "DECEMBER")
# the most people named in a message; the rest are counted
SHOWN = 10


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


def _text(value):
    return " ".join(str(value if value is not None else "").split())


def shillings(value):
    """A sum in whole shillings, half a shilling up, as the bank pays it."""
    return int(Decimal(str(_num(value))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _day(day):
    """05TH, 01ST, 22ND: the day of the month as the team writes it."""
    suffix = "TH" if 11 <= day.day % 100 <= 13 else {1: "ST", 2: "ND", 3: "RD"}.get(day.day % 10, "TH")
    return "%02d%s" % (day.day, suffix)


def title(start, end, weekly=False):
    """TO BANK REPORT FOR THE PERIOD 05TH TO 11TH NOVEMBER, WEEK TWO.: the period, the month said once where both
    ends are in it, and for a weekly payroll its week of the month it ends in (the week ending on the 11th is the
    second)."""
    first, last = _date(start), _date(end)
    if not first or not last:
        return "TO BANK REPORT"
    same = (first.year, first.month) == (last.year, last.month)
    period = "%s TO %s %s" % (_day(first) if same else "%s %s" % (_day(first), MONTHS[first.month - 1]), _day(last),
                              MONTHS[last.month - 1])
    if not weekly:
        return "TO BANK REPORT FOR THE PERIOD %s." % period
    return "TO BANK REPORT FOR THE PERIOD %s, WEEK %s." % (period, WEEKS[min((last.day - 1) // 7, len(WEEKS) - 1)])


def phone(value):
    """(the nine digits, the twelve with 256 before them), or None for no number, or False for one that is not a
    phone number: 0783 296 108, 783296108, +256 783 296108 are all (783296108, 256783296108)."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 12 and digits.startswith(COUNTRY):
        digits = digits[3:]
    elif len(digits) == 10 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9 or digits.startswith("0"):
        return False
    return int(digits), int(COUNTRY + digits)


def by_bank(line):
    """Salary Mode Bank; or none, with an account number to pay into (bank_file_rules.paid_by_bank)."""
    mode = _text(line.get("salary_mode"))
    return mode == BANK if mode else bool(_text(line.get("bank_ac_no")))


def by_mobile_money(line):
    """Paid by neither bank nor cheque, with a Wages Phone Number: in cash, through mobile money (Luuka, 13 Nov 2026:
    "some employee have cash paymebt through mobile moneny")."""
    return not by_bank(line) and _text(line.get("salary_mode")) != CHEQUE and phone(line.get("phone")) is not None


def lines_to_pay(lines):
    """The lines the file pays: by mobile money, something to pay."""
    return [line for line in lines or () if by_mobile_money(line) and shillings(line.get("amount")) > 0]


def left_out(lines):
    """{"bank", "cheque", "no_phone"}: those with something to pay the file leaves out, by why."""
    out = {"bank": [], "cheque": [], "no_phone": []}
    for line in lines or ():
        if shillings(line.get("amount")) <= 0 or by_mobile_money(line):
            continue
        if by_bank(line):
            out["bank"].append(line)
        elif _text(line.get("salary_mode")) == CHEQUE:
            out["cheque"].append(line)
        else:
            out["no_phone"].append(line)
    return out


def person(line):
    return "%s (%s)" % (_text(line.get("employee_name")) or line.get("employee"), line.get("employee"))


def people(lines, shown=SHOWN):
    lines = list(lines or ())
    named = ", ".join(person(line) for line in lines[:shown])
    return named + (" and %d more" % (len(lines) - shown) if len(lines) > shown else "")


def problems(lines):
    """The lines whose Wages Phone Number is not a phone number: the bank could not pay them."""
    return [line for line in lines or () if by_mobile_money(line) and shillings(line.get("amount")) > 0
            and phone(line.get("phone")) is False]


def problem_text(found, shown=SHOWN):
    found = list(found or ())
    if not found:
        return ""
    return ("Wages Phone Number is not a phone number for %s: put the nine digits, or 0 and the nine, on their "
            "employee record." % people(found, shown))


def _names(line):
    """(surname, first names) in capitals: the employee's last name, else the last word of their name."""
    last, first = _text(line.get("last_name")), " ".join(
        part for part in (_text(line.get("first_name")), _text(line.get("middle_name"))) if part)
    if not last:
        words = _text(line.get("employee_name")).split()
        last, first = (words[-1], " ".join(words[:-1])) if len(words) > 1 else (" ".join(words), first)
    return last.upper(), (first or "").upper()


def rows(lines):
    """[(SN, EMP NO, phone, 256 phone, AMOUNT, Surname, Firstname, Registered Name)], the smallest amount first, as the
    team's file is: the lines to pay, each with the name its phone is registered in, else their own."""
    paid = sorted(lines_to_pay(lines), key=lambda line: (shillings(line.get("amount")), str(line.get("employee"))))
    out = []
    for number, line in enumerate(paid, 1):
        local, full = phone(line.get("phone"))
        surname, first = _names(line)
        registered = _text(line.get("registered_name")) or _text(line.get("employee_name"))
        out.append((number, line.get("employee"), local, full, shillings(line.get("amount")), surname, first,
                    registered.upper()))
    return out


def workbook(heading, body):
    """The sheet as the team's own: the title across the top, the headings, a line each, and TOTAL AMOUNT; Verdana
    14, thin borders all round, the amounts in whole shillings."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    plain, bold = Font(name=FONT, size=SIZE), Font(name=FONT, size=SIZE, bold=True)
    left, centre = Alignment(horizontal="left", vertical="center"), Alignment(horizontal="center", vertical="center")
    columns = len(HEADER)

    def put(row, column, value, font=plain, align=left, number_format=None):
        cell = sheet.cell(row=row, column=column)
        cell.value = value
        if isinstance(value, str):
            cell.data_type = "s"  # a name that starts with = is a name, never a formula
        cell.font, cell.alignment, cell.border = font, align, border
        if number_format:
            cell.number_format = number_format
        return cell

    put(1, 1, heading, bold, centre)
    for column in range(2, columns + 1):
        put(1, column, None, bold, centre)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    for column, label in enumerate(HEADER, 1):
        put(2, column, label, bold)
    at = 2
    for at, values in enumerate(body or (), 3):
        for column, value in enumerate(values, 1):
            put(at, column, value, number_format=AMOUNT_FORMAT if column == 5 else NUMBER_FORMAT if column in (2, 3, 4, 8)
                else None)
    total = at + 1
    put(total, 1, "TOTAL AMOUNT", bold, centre)
    for column in (2, 3, 4):
        put(total, column, None, bold, centre)
    sheet.merge_cells(start_row=total, start_column=1, end_row=total, end_column=4)
    put(total, 5, sum(values[4] for values in body or ()), bold, number_format=AMOUNT_FORMAT)
    for column in range(6, columns + 1):
        put(total, column, None, bold)
    for letter, width in WIDTHS:
        sheet.column_dimensions[letter].width = width
    for row in range(1, total + 1):
        sheet.row_dimensions[row].height = ROW_HEIGHT
    content = io.BytesIO()
    book.save(content)
    return content.getvalue()
