# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The bank file: the Excel file Finance sends the bank to pay a payroll, a
leave advance run likewise (Luuka, 6 Nov 2026: "bank file should be in this
format", with their own file as the pattern).

THE FILE

  Six columns, headed as the bank takes them: Emp ID, Employee Name, Bank
  Name, Bank_Code, Account Number, Net Payable Amount. No title and no total
  row: the first row is the heading, every other row a person.

  One row for each person paid by bank with something to pay, sorted by bank
  and then by name, names and banks in capitals. Bank Name is the bank, with
  the employee's bank branch in brackets when there is one, as Luuka's own
  file writes it: BANK(BRANCH).

  The code and the account number are text, so a leading zero stays (a code
  such as 010101; a dfcu account has fourteen digits and may begin with 0),
  and Excel is told they are text on purpose, so it shows no green corner on
  them. The amount is a number, shown 1,234,567.00.

WHO IS IN IT

  Paid by bank: Salary Mode Bank, or no Salary Mode but an account number.
  Cash and Cheque are paid another way and are not in it. Nor is anybody
  with nothing to pay.

WHAT IS LEFT BLANK, AND WHAT STOPS IT

  A person paid by bank with no account number, no bank or no bank code. A
  payroll's file has them, with what is missing left blank (Luuka, 13 Nov
  2026: "if moble phone/ bank account ist should be blank on that
  employee"); an advance run's file is not made at all. Either way the
  message names them, and the bank codes by bank, since one code set on the
  bank mends everybody at that bank.

The bank code is the employee's own, else the one set once on their bank in
the Bank list (bank_file.py reads both).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_bank_file.py runs it without a bench.
"""

import io
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

HEADER = ("Emp ID", "Employee Name", "Bank Name", "Bank_Code", "Account Number", "Net Payable Amount")
SHEET = "Sheet1"

BANK = "Bank"

# as Luuka's own file looks: a small plain font, every cell boxed
FONT = "Tahoma"
SIZE = 8
ROW_HEIGHT = 10.5
WIDTHS = (("A", 9), ("B", 31.3), ("C", 26.7), ("D", 9.6), ("E", 26.9), ("F", 17.1))
AMOUNT_FORMAT = "#,##0.00"
TEXT_FORMAT = "@"
# the columns written as text: Emp ID to Account Number
TEXT_COLUMNS = 5
CODE_COLUMN, ACCOUNT_COLUMN, AMOUNT_COLUMN = 4, 5, 6

NO_ACCOUNT = "no account"
NO_BANK = "no bank"
NO_CODE = "no code"

# how many names a message lists before it says how many more
SHOWN = 10


def clean(value):
    """Text with its spaces tidied; nothing for nothing."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def compact(value):
    """A code or an account number: no spaces at all."""
    return "".join(clean(value).split())


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def bank_label(bank_name, branch=None):
    """The bank in capitals, the branch in brackets after it: ALPHA BANK(CITY SQUARE).
    A bank already written with a bracket keeps its own."""
    bank, branch = clean(bank_name).upper(), clean(branch).upper()
    if not bank:
        return ""
    if branch and "(" not in bank:
        return "%s(%s)" % (bank, branch)
    return bank


def bank_code(own_code, banks_code=None):
    """The employee's own bank code, else their bank's."""
    return compact(own_code) or compact(banks_code)


def paid_by_bank(line):
    """Salary Mode Bank; or none at all, with an account number to pay into."""
    mode = clean(line.get("salary_mode"))
    if mode:
        return mode == BANK
    return bool(compact(line.get("bank_ac_no")))


def to_pay(lines):
    """The lines the file pays: by bank, something to pay."""
    return [line for line in lines or () if paid_by_bank(line) and round(number(line.get("amount")), 2) > 0]


def not_by_bank(lines):
    """(paid another way, unknown): the people with something to pay whom
    the file leaves out. Unknown is no Salary Mode and no account number."""
    other, unknown = [], []
    for line in lines or ():
        if round(number(line.get("amount")), 2) <= 0 or paid_by_bank(line):
            continue
        (other if clean(line.get("salary_mode")) else unknown).append(line)
    return other, unknown


def problems(lines):
    """[(what, line)] for each line the bank could not pay: no account
    number, no bank, no bank code. One per line, the first that applies."""
    out = []
    for line in to_pay(lines):
        if not compact(line.get("bank_ac_no")):
            out.append((NO_ACCOUNT, line))
        elif not clean(line.get("bank_name")):
            out.append((NO_BANK, line))
        elif not compact(line.get("bank_code")):
            out.append((NO_CODE, line))
    return out


def person(line):
    name, employee = clean(line.get("employee_name")), clean(line.get("employee"))
    if name and employee:
        return "%s (%s)" % (name, employee)
    return name or employee


def people(lines, shown=SHOWN):
    """Some names, and how many more."""
    names = [person(line) for line in lines]
    if len(names) <= shown:
        return ", ".join(names)
    return "%s and %d more" % (", ".join(names[:shown]), len(names) - shown)


# a payroll's file is made with these left blank, and says so (Luuka, 13 Nov 2026: "if moble phone/ bank account
# ist should be blank on that employee"); an advance run's file is not made
REFUSED = "The bank file was not made. These people are paid by bank and the bank needs more."
BLANK = "Left blank in the bank file:"


def problem_lines(found, shown=SHOWN, heading=REFUSED):
    """The message, a line each: who has no account number, who no bank, and
    which banks have no code and for how many."""
    if not found:
        return []
    out = [heading]
    no_account = [line for what, line in found if what == NO_ACCOUNT]
    no_bank = [line for what, line in found if what == NO_BANK]
    if no_account:
        out.append("No account number: %s." % people(no_account, shown))
    if no_bank:
        out.append("No bank: %s." % people(no_bank, shown))
    # one bank however its name is written: the Bank list matches a name whatever its capitals
    by_bank = {}
    for what, line in found:
        if what == NO_CODE:
            bank = clean(line.get("bank_name"))
            by_bank.setdefault(bank.casefold(), (bank, []))[1].append(line)
    for key in sorted(by_bank):
        bank, lines = by_bank[key]
        out.append("No bank code for %s: %d %s. Set it once on the bank in the Bank list, or on each employee." % (
            bank, len(lines), "person" if len(lines) == 1 else "people"))
    return out


def rows(lines):
    """The rows under the heading, one per person paid by bank, sorted by
    bank and then by name."""
    out = []
    for line in to_pay(lines):
        out.append([
            clean(line.get("employee")),
            clean(line.get("employee_name")).upper(),
            bank_label(line.get("bank_name"), line.get("bank_branch")),
            compact(line.get("bank_code")),
            compact(line.get("bank_ac_no")),
            round(number(line.get("amount")), 2),
        ])
    out.sort(key=lambda row: (clean(_bank_of(row[2])), row[1], row[0]))
    return out


def _bank_of(label):
    """The bank alone, without its branch, which orders the file."""
    return label.split("(", 1)[0]


def workbook(body):
    """The file as .xlsx bytes: the heading and the rows, every cell boxed."""
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    side = Side(style="thin", color="000000")
    box = Border(left=side, right=side, top=side, bottom=side)
    plain, bold = Font(name=FONT, size=SIZE), Font(name=FONT, size=SIZE, bold=True)
    right = Alignment(horizontal="right")
    for row_number, values in enumerate([list(HEADER)] + [list(row) for row in body or ()], start=1):
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_number, column=column, value=value)
            cell.font = bold if row_number == 1 else plain
            cell.border = box
            if row_number == 1:
                continue
            if column <= TEXT_COLUMNS:
                # text, always: a name that begins with = is not a formula
                cell.value = clean(value)
                cell.data_type = "s"
                if column in (CODE_COLUMN, ACCOUNT_COLUMN):
                    cell.number_format = TEXT_FORMAT
                if column == ACCOUNT_COLUMN:
                    cell.alignment = right
            elif column == AMOUNT_COLUMN:
                cell.number_format = AMOUNT_FORMAT
        sheet.row_dimensions[row_number].height = ROW_HEIGHT
    for letter, width in WIDTHS:
        sheet.column_dimensions[letter].width = width
    buffer = io.BytesIO()
    book.save(buffer)
    content = buffer.getvalue()
    if body:
        content = text_on_purpose(content, "D2:E%d" % (len(body) + 1))
    return content


def text_on_purpose(content, cells):
    """Excel's green corner on a number kept as text, turned off for the
    code and the account number, which are text on purpose. openpyxl knows
    the element but never writes it, so it goes in last on the sheet, where
    the file's order puts it after everything openpyxl writes."""
    source = zipfile.ZipFile(io.BytesIO(content))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = data.decode("utf-8")
                tag = '<ignoredErrors><ignoredError sqref="%s" numberStoredAsText="1"/></ignoredErrors>' % cells
                text = text.replace("</worksheet>", tag + "</worksheet>", 1)
                data = text.encode("utf-8")
            target.writestr(item, data)
    return out.getvalue()
