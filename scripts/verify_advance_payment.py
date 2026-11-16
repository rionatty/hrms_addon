"""Checks for the salary advance run's bank file as Luuka's own ADVANCE_PAYMENT workbook (Luuka, 16 Nov 2026, sending
their ADVANCE_PAYMENT NOVEMBER 2026 workbook: "this is the bank file").

Runs without a bench: advance_payment_rules.py on its own, the workbook read back with openpyxl and as the zip it is.
Every person and number here is made up.

    python scripts/verify_advance_payment.py
"""
import importlib.util
import io
import os
import sys
import types
import zipfile

import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else "   <- %s" % (detail,))
    if not condition:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["hrms_addon.hrms_addon." + name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
B = load("bank_file_rules")
A = load("advance_payment_rules")
print("loaded advance_payment_rules.py without Frappe")


def line(employee, name, amount, mode="Bank", bank=None, branch=None, code=None, account=None, department=None,
         qualifies=1, include=1):
    return {"employee": employee, "employee_name": name, "amount": amount, "salary_mode": mode, "bank_name": bank,
            "bank_branch": branch, "bank_code": code, "bank_ac_no": account, "department": department,
            "qualifies": qualifies, "include": include}


LINES = [
    line("EMP347", "Ben Two", 455555.2, bank="ALPHA BANK (BRANCH)", code="010101", account="1000000347"),
    line("EMP1088", "Cy Three", 300000, bank="Alpha Bank", branch="Main Street", code="040404",
         account="4000001088123"),
    line("EMP12000", "Fay Cash", 120000, mode="Cash", department="PIB Department - LPL"),
    line("EMP111", "Ann One", 599000, bank="ALPHA BANK(BRANCH)", code="010101", account="1000 000 111"),
    line("EMP409", "Dee Four", 250000, bank="Beta Bank", code=20202, account="02000000000409"),
    line("EMP11000", "Gus Cash", 130000, mode="Cash", department="PP Department - LPL"),
    line("EMP700", "=Zed Formula", 1000, bank="Gamma Bank", code="030303", account=None),
    line("EMP500", "Eve Long", 120000, bank="Gamma Bank", code="030303", account="3000000000000500"),
    line("EMP1500", "Hal Cash", 180000, mode=None, department="PIB Department - LPL"),
    line("EMP600", "Not Qualifying", 99000, bank="Gamma Bank", code="030303", account="555", qualifies=0),
    line("EMP601", "Not Ticked", 99000, bank="Gamma Bank", code="030303", account="556", include=0),
    line("EMP602", "Nothing To Pay", 0, bank="Gamma Bank", code="030303", account="557"),
]

# ── 1. The rules ──────────────────────────────────────
check([item["employee"] for item in A.paid(LINES)] == ["EMP347", "EMP1088", "EMP12000", "EMP111", "EMP409",
                                                       "EMP11000", "EMP700", "EMP500", "EMP1500"],
      "the run pays the lines that qualify, are ticked to pay and have something to pay")
check(len(A.by_bank(LINES)) == 6 and [item["employee"] for item in A.in_cash(LINES)] == ["EMP12000", "EMP11000",
                                                                                         "EMP1500"],
      "by bank: Salary Mode Bank; in cash: the rest, one with no mode and no account among them")
check([A.digits(value) for value in ("010101", "202020", 20202, "1000 000 111", "3000000000000500", "", None, "A12",
                                     "123456789012345")]
      == ["010101", 202020, 20202, 1000000111, "3000000000000500", None, None, "A12", 123456789012345],
      "a code or an account a number, as Luuka's file has them, unless a nought leads it or it is too long for "
      "Excel to hold whole")
check([A.department(name) for name in ("PIB Department - LPL", "PP Department - LPL", "Administration - LPT",
                                       "Human Resources Department", None)]
      == ["PIB", "PP", "ADMINISTRATION", "HUMAN RESOURCES", ""],
      "the department as their cash report writes it: PIB, PP")
body = A.bank_rows(LINES)
check(body == [(1, "EMP111", "ANN ONE", "ALPHA BANK(BRANCH)", "010101", 1000000111, 599000.0),
               (2, "EMP347", "BEN TWO", "ALPHA BANK (BRANCH)", "010101", 1000000347, 455555.2),
               (3, "EMP1088", "CY THREE", "ALPHA BANK(MAIN STREET)", "040404", 4000001088123, 300000.0),
               (4, "EMP409", "DEE FOUR", "BETA BANK", 20202, "02000000000409", 250000.0),
               (5, "EMP500", "EVE LONG", "GAMMA BANK", "030303", "3000000000000500", 120000.0),
               (6, "EMP700", "=ZED FORMULA", "GAMMA BANK", "030303", None, 1000.0)],
      "by bank however its bracket is spaced, then by payroll number as a number (EMP111 before EMP347 before EMP1088); "
      "the bank with its branch; an account missing is left blank", body)
cash = A.cash_rows(LINES)
check(cash == [(1, "EMP1500", "HAL CASH", "PIB", 180000.0), (2, "EMP12000", "FAY CASH", "PIB", 120000.0),
               (3, "EMP11000", "GUS CASH", "PP", 130000.0)],
      "the cash report: by department, then by payroll number", cash)
check(A.title("November") == "SALARY ADVANCE CASH REPORT FOR NOVEMBER"
      and A.file_name("November", 2026) == "ADVANCE_PAYMENT NOVEMBER 2026",
      "the cash report's title and the file's name, as theirs")
print("rules: who is paid, by bank or in cash, the order, the codes and accounts, the departments")

# ── 2. The workbook ───────────────────────────────────
content = A.workbook("November", body, cash)
book = openpyxl.load_workbook(io.BytesIO(content))
check(book.sheetnames == ["ADVANCE_PAYMENT", "CASH REPORT"] and book.active.title == "ADVANCE_PAYMENT",
      "two sheets, as theirs: the bank's, then the cash report", book.sheetnames)
sheet, report = book["ADVANCE_PAYMENT"], book["CASH REPORT"]
values = [[cell.value for cell in row] for row in sheet.iter_rows(min_row=1, max_row=12, max_col=7)]
check(values[0] == list(A.HEADER) and [tuple(row) for row in values[1:7]] == [
    (1, "EMP111", "ANN ONE", "ALPHA BANK(BRANCH)", "010101", 1000000111, 599000),
    (2, "EMP347", "BEN TWO", "ALPHA BANK (BRANCH)", "010101", 1000000347, 455555.2),
    (3, "EMP1088", "CY THREE", "ALPHA BANK(MAIN STREET)", "040404", 4000001088123, 300000),
    (4, "EMP409", "DEE FOUR", "BETA BANK", 20202, "02000000000409", 250000),
    (5, "EMP500", "EVE LONG", "GAMMA BANK", "030303", "3000000000000500", 120000),
    (6, "EMP700", "=ZED FORMULA", "GAMMA BANK", "030303", None, 1000)],
      "the headings, then a line each", values[:7])
check(values[7] == ["TOTAL", None, None, None, None, None, "=SUM(G2:G7)"] and values[8] == [None] * 7
      and values[9] == [None] * 7 and values[10] == [None, None, None, None, None, " CASH", "='CASH REPORT'!F9"]
      and values[11] == [None, None, None, None, None, "GRAND TOTAL", "=G8+G11"]
      and "A8:F8" in [str(merged) for merged in sheet.merged_cells.ranges],
      "TOTAL across A to F, then two rows down CASH from the cash report's total, and GRAND TOTAL, as formulas",
      values[7:])
check(sheet["C7"].data_type == "s" and sheet["C7"].value == "=ZED FORMULA", "a name that starts with = is a name")
# every cell written, but those the TOTAL's merge hides (B8:F8), which keep no font of their own
written = [(row, column) for row in range(1, 9) for column in range(1, 8) if not (row == 8 and 2 <= column <= 6)]
written += [(11, 6), (11, 7), (12, 6), (12, 7)]
check(all(sheet.cell(row=row, column=column).font.name == "Verdana" and sheet.cell(row=row, column=column).font.sz == 10
          for row, column in written)
      and all(cell.font.b for cell in sheet[1]) and not sheet["A2"].font.b and sheet["A8"].font.b and sheet["G8"].font.b
      and not sheet["F11"].font.b and sheet["F12"].font.b and sheet["G12"].font.b,
      "Verdana 10, the headings, the TOTAL and the GRAND TOTAL in bold, as theirs")
check(all(sheet.cell(row=row, column=column).border.left.style == "thin" for row in range(1, 8) for column in range(1, 8))
      and all(sheet.cell(row=8, column=column).border.top.style == "medium" for column in range(1, 8))
      and sheet["F11"].border.left.style is None and sheet["G12"].border.left.style is None,
      "thin borders on the lines, a heavy one round the TOTAL, none below")
check(all(sheet.cell(row=row, column=7).number_format == A.MONEY for row in list(range(2, 9)) + [11, 12])
      and sheet["E2"].alignment.horizontal == "left" and sheet["F2"].alignment.horizontal == "left"
      and sheet["A8"].alignment.horizontal == "center",
      "amounts as money, code and account to the left, TOTAL centred")
check(sheet["F2"].number_format == A.WHOLE and sheet["F4"].number_format == A.WHOLE and sheet["E5"].number_format == A.WHOLE
      and sheet["E2"].number_format == "General" and sheet["F5"].number_format == "General",
      "a code or account kept as a number shows every digit (General writes 13 digits as 4E+12); text stays text",
      (sheet["F4"].number_format, sheet["E2"].number_format))
check({letter: sheet.column_dimensions[letter].width for letter, _ in A.WIDTHS} == dict(A.WIDTHS),
      "the columns their width")
xml = zipfile.ZipFile(io.BytesIO(content)).read("xl/worksheets/sheet1.xml").decode("utf-8")
check(xml.endswith('<ignoredErrors><ignoredError sqref="E2:F7" numberStoredAsText="1"/></ignoredErrors></worksheet>'),
      "a code or account kept as text is text on purpose: no green corner on them")
cash_values = [[cell.value for cell in row] for row in report.iter_rows(min_row=4, max_row=9, min_col=2, max_col=6)]
check(cash_values[0][0] == "SALARY ADVANCE CASH REPORT FOR NOVEMBER" and "B4:F4" in [str(m) for m in report.merged_cells.ranges]
      and cash_values[1] == list(A.CASH_HEADER)
      and [tuple(row) for row in cash_values[2:5]] == [(1, "EMP1500", "HAL CASH", "PIB", 180000),
                                                      (2, "EMP12000", "FAY CASH", "PIB", 120000),
                                                      (3, "EMP11000", "GUS CASH", "PP", 130000)]
      and cash_values[5] == ["TOTAL", None, None, None, "=SUM(F6:F8)"] and "B9:E9" in [str(m) for m in report.merged_cells.ranges],
      "the cash report: its title across B to F on the fourth row, headings, a line each, TOTAL", cash_values)
check(report["B4"].font.b and report["B4"].alignment.horizontal == "center" and all(cell.font.b for cell in report[5][1:6])
      and report["B6"].border.left.style == "thin" and report["B9"].border.top.style == "medium"
      and report["F9"].font.b and report["F6"].number_format == A.MONEY
      and {letter: report.column_dimensions[letter].width for letter, _ in A.CASH_WIDTHS} == dict(A.CASH_WIDTHS),
      "and in their look")
empty = openpyxl.load_workbook(io.BytesIO(A.workbook("December", [], [])))
check(empty["ADVANCE_PAYMENT"]["A2"].value == "TOTAL" and empty["ADVANCE_PAYMENT"]["G2"].value == 0
      and empty["ADVANCE_PAYMENT"]["G5"].value == "='CASH REPORT'!F6" and empty["ADVANCE_PAYMENT"]["G6"].value == "=G2+G5"
      and empty["CASH REPORT"]["B6"].value == "TOTAL" and empty["CASH REPORT"]["F6"].value == 0
      and "ignoredErrors" not in zipfile.ZipFile(io.BytesIO(A.workbook("December", [], []))).read(
          "xl/worksheets/sheet1.xml").decode("utf-8"),
      "nobody by bank or in cash: totals of nought, never a sum of nothing")
print("the workbook: both sheets, the totals as formulas, their look")

# ── 3. The run's Bank File button ─────────────────────
script = io.open(os.path.join(APP, "doctype", "salary_advance_processing", "salary_advance_processing.js"),
                 encoding="utf-8").read()
button = script.split('frm.add_custom_button(__("Bank File"), () => {', 1)[1].split("\n\t\t\t});", 1)[0] \
    if 'frm.add_custom_button(__("Bank File"), () => {' in script else ""
check("if (!found || !(found.rows || found.cash)) return;" in button
      and 0 < button.find("window.open(") < button.find("if ((found.blank || []).length) {")
      and "found.blank.map((line) => frappe.utils.escape_html(line))" in button,
      "the run's Bank File downloads when anyone is paid, by bank or in cash, then says whose bank details are "
      "blank, each line escaped")
print("the form: the Bank File button")

print()
if fail:
    print("FAILURES:")
    for item in fail:
        print("  -", item)
    sys.exit(1)
print("ALL ADVANCE PAYMENT CHECKS PASSED")
