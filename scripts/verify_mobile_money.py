"""Checks for the payroll's mobile money file: those paid in cash through mobile money, in the team's own TO BANK
REPORT (Luuka, 13 Nov 2026: "some employee have cash paymebt through mobile moneny ist necessary that the bank file
should be only bank account employee. on the payroll this bank file for casuals as attached").

Runs without a bench: mobile_money_rules.py on its own, mobile_money.py on a stand-in site, the workbook read back with
openpyxl, the button read as text. Every person and number here is made up.

    python scripts/verify_mobile_money.py
"""
import datetime
import importlib.util
import io
import os
import sys
import types

import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
D = datetime.date
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else "   <- %s" % (detail,))
    if not condition:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["hrms_addon.hrms_addon." + name] = module
    return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
R = load("mobile_money_rules")
print("loaded mobile_money_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────
check(R.title(D(2026, 11, 5), D(2026, 11, 11), weekly=True)
      == "TO BANK REPORT FOR THE PERIOD 05TH TO 11TH NOVEMBER, WEEK TWO.",
      "the title as the team's own: the period, the month said once, the week of the month it ends in",
      R.title(D(2026, 11, 5), D(2026, 11, 11), weekly=True))
check(R.title(D(2026, 10, 29), D(2026, 11, 4), weekly=True)
      == "TO BANK REPORT FOR THE PERIOD 29TH OCTOBER TO 04TH NOVEMBER, WEEK ONE."
      and R.title(D(2026, 11, 26), D(2026, 12, 2), weekly=True)
      == "TO BANK REPORT FOR THE PERIOD 26TH NOVEMBER TO 02ND DECEMBER, WEEK ONE."
      and R.title(D(2026, 11, 19), D(2026, 11, 25), weekly=True).endswith("WEEK FOUR.")
      and R.title(D(2026, 10, 26), D(2026, 11, 25)) == "TO BANK REPORT FOR THE PERIOD 26TH OCTOBER TO 25TH NOVEMBER.",
      "a week across two months names both; the week ending on the 25th is the fourth; a month's has no week")
check([R._day(D(2026, 11, day)) for day in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30)]
      == ["01ST", "02ND", "03RD", "04TH", "11TH", "12TH", "13TH", "21ST", "22ND", "23RD", "30TH"],
      "the days as the team writes them")
check([R.phone(value) for value in ("0783 296 108", "783296108", "+256 783 296108", 256783296108, 783296108,
                                    "0783-296-108")] == [(783296108, 256783296108)] * 6,
      "a Wages Phone Number as the bank takes it, however it was written: nine digits, and 256 before them")
check([R.phone(value) for value in (None, "", "  ")] == [None] * 3
      and [R.phone(value) for value in ("12345", "0083296108", "2567832961080", "abc", "123783296108")] == [False] * 5,
      "no number is none; one that is not a phone number is said")
check(R.shillings(11141.5) == 11142 and R.shillings(11141.49) == 11141 and R.shillings(None) == 0,
      "the amounts in whole shillings, half a shilling up")
lines = [
    {"employee": "LPC90001", "employee_name": "Ann Example", "amount": 19282.5, "salary_mode": "Cash",
     "phone": "0783296108", "registered_name": "Ann Example", "first_name": "Ann", "last_name": "Example"},
    {"employee": "LPC90002", "employee_name": "Ben Sample", "amount": 11141, "salary_mode": None,
     "phone": "772000111", "registered_name": "Carol Sample", "first_name": "Ben", "middle_name": "Two",
     "last_name": "Sample"},
    {"employee": "LPC90003", "employee_name": "Dan Bank", "amount": 50000, "salary_mode": "Bank",
     "bank_ac_no": "0123", "phone": "0700000001"},
    {"employee": "LPC90004", "employee_name": "Eve Cash", "amount": 9000, "salary_mode": "Cash", "phone": ""},
    {"employee": "LPC90005", "employee_name": "Fay Cheque", "amount": 8000, "salary_mode": "Cheque",
     "phone": "0700000002"},
    {"employee": "LPC90006", "employee_name": "Gus Nothing", "amount": 0, "salary_mode": "Cash", "phone": "0700000003"},
    {"employee": "LPC90007", "employee_name": "Hal Account", "amount": 7000, "salary_mode": None, "bank_ac_no": "99",
     "phone": "0700000004"},
    {"employee": "LPC90008", "employee_name": "=Ivy Formula", "amount": 11141, "salary_mode": "Cash",
     "phone": "256701000002"},
]
check([line["employee"] for line in R.lines_to_pay(lines)] == ["LPC90001", "LPC90002", "LPC90004", "LPC90008"],
      "the file pays those paid in cash, or with no salary mode and no account, with something to pay: a phone or none")
out = R.left_out(lines)
check(out == {"bank": [lines[2], lines[6]], "cheque": [lines[4]]},
      "and leaves out those paid by bank (in the Bank File) and by cheque, each said", out)
body = R.rows(lines)
check(body == [(1, "LPC90004", None, None, 9000, "CASH", "EVE", "EVE CASH"),
               (2, "LPC90002", 772000111, 256772000111, 11141, "SAMPLE", "BEN TWO", "CAROL SAMPLE"),
               (3, "LPC90008", 701000002, 256701000002, 11141, "FORMULA", "=IVY", "=IVY FORMULA"),
               (4, "LPC90001", 783296108, 256783296108, 19283, "EXAMPLE", "ANN", "ANN EXAMPLE")],
      "each line as the team's sheet has it, the smallest amount first: the phone both ways, or blank where there is "
      "none, the amount in shillings, surname and first names in capitals, the name the phone is registered in, else "
      "their own", body)
said = R.blank_lines(R.blanks([dict(lines[0], phone="12345"), lines[1], lines[3], lines[2]]))
check(said == ["Telephone left blank in the file:", "No Wages Phone Number: Eve Cash (LPC90004).",
               "Wages Phone Number not a phone number: Ann Example (LPC90001). Put the nine digits, or 0 and the nine, "
               "on their employee record."],
      "whose phone is left blank is said: those with none, then those whose number is not one (Luuka, 13 Nov 2026: "
      "\"if moble phone/ bank account ist should be blank on that employee\")", said)
check(R.blank_lines([]) == [] and R.blanks([lines[1], lines[2], lines[7]]) == [],
      "nothing said when every phone paid is a phone")
check(R.rows([dict(lines[0], phone="12345")])[0][2:5] == (None, None, 19283),
      "a number that is not one is left blank, never guessed, and the person still paid")
check(not any(dash in " ".join(said) for dash in (" - ", "\u2013", "\u2014")), "plain words, no dashes", said)
print("rules: the title, the phones, who is paid this way, whose phone is blank, each line as the team writes it")

# ── 2. The workbook ───────────────────────────────────
book = openpyxl.load_workbook(io.BytesIO(R.workbook(R.title(D(2026, 11, 5), D(2026, 11, 11), True), body)))
sheet = book.active
values = [[cell.value for cell in row] for row in sheet.iter_rows()]
check(sheet.title == "Sheet1" and values[0][0] == "TO BANK REPORT FOR THE PERIOD 05TH TO 11TH NOVEMBER, WEEK TWO."
      and "A1:H1" in [str(merged) for merged in sheet.merged_cells.ranges]
      and values[1] == list(R.HEADER),
      "the title across the top, then the team's headings", values[:2])
check(values[2:6] == [list(row) for row in body]
      and values[6][:5] == ["TOTAL AMOUNT", None, None, None, 50565]
      and "A7:D7" in [str(merged) for merged in sheet.merged_cells.ranges],
      "a line each, then TOTAL AMOUNT across the first four columns and the sum under AMOUNT", values[2:])
check(isinstance(values[3][2], int) and isinstance(values[3][3], int) and isinstance(values[3][4], int)
      and sheet["C4"].number_format == "0" and sheet["E4"].number_format == R.AMOUNT_FORMAT
      and sheet["E7"].number_format == R.AMOUNT_FORMAT,
      "the phones and the amount are numbers, as the bank's own file has them, the amounts in whole shillings")
check(values[2][2] is None and values[2][3] is None and values[2][4] == 9000
      and sheet["C3"].border.left.style == "thin" and sheet["D3"].border.left.style == "thin",
      "a phone left blank is an empty cell, boxed like the rest, the amount beside it still paid")
check(sheet["G5"].data_type == "s" and sheet["G5"].value == "=IVY" and sheet["H5"].value == "=IVY FORMULA",
      "a name that starts with = is a name, never a formula")
merged_away = {(1, column) for column in range(2, 9)} | {(7, column) for column in range(2, 5)}
check(all(sheet.cell(row=row, column=column).font.name == "Verdana" and sheet.cell(row=row, column=column).font.sz == 14
          and sheet.cell(row=row, column=column).border.left.style == "thin"
          for row in range(1, 8) for column in range(1, 9) if (row, column) not in merged_away)
      and sheet["A1"].font.b and sheet["A2"].font.b and sheet["A7"].font.b and sheet["E7"].font.b
      and not sheet["A3"].font.b and sheet["A1"].alignment.horizontal == "center",
      "its look is the team's: Verdana 14, thin borders on every cell, the title, headings and total in bold")
check({letter: sheet.column_dimensions[letter].width for letter in "ABCDEFGH"} == dict(R.WIDTHS)
      and all(sheet.row_dimensions[row].height == R.ROW_HEIGHT for row in range(1, 8)),
      "and its columns and rows the team's size")
print("the workbook: the team's TO BANK REPORT, its title, headings, lines, total and look")

# ── 3. The glue, on a stand-in site ───────────────────


class Thrown(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


SITE = {}
frappe = types.ModuleType("frappe")
frappe._ = lambda text, *args, **kwargs: text
frappe._dict = Row
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if not args or not callable(args[0]) else args[0]
frappe.throw = lambda message, title=None, *args, **kwargs: (_ for _ in ()).throw(Thrown(message))
frappe.PermissionError = Thrown


def get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=None, **kwargs):
    SITE.setdefault("reads", []).append((doctype, fields))
    rows = SITE["tables"].get(doctype, [])
    if doctype == "Salary Slip":
        rows = [row for row in rows if row["payroll_entry"] == filters["payroll_entry"]
                and ("docstatus" not in filters or row["docstatus"] == filters["docstatus"])]
    if doctype == "Employee":
        rows = [row for row in rows if row["name"] in filters["name"][1]]
    return [Row({field: row.get(field) for field in (fields or row)}) if doctype == "Employee" else Row(row)
            for row in rows]


frappe.get_all = get_all
frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda field: True)


class Run(Row):
    def check_permission(self, ptype):
        if not SITE.get("may_read", True):
            raise Thrown("no access to the payroll")


frappe.get_doc = lambda doctype, name: Run(SITE["run"])
utils = types.ModuleType("frappe.utils")
utils.cint = lambda value: int(value or 0)
utils.escape_html = lambda text: text
desk = types.ModuleType("frappe.desk")
desk.__path__ = []
desk_utils = types.ModuleType("frappe.desk.utils")
desk_utils.provide_binary_file = lambda name, extension, content: SITE.update(file=(name, extension, content))
bank_file = types.ModuleType("hrms_addon.hrms_addon.bank_file")


def may_see_bank_details():
    if not SITE.get("bank_details", True):
        raise Thrown("Only HR and Payroll may see bank details.")


bank_file.may_see_bank_details = may_see_bank_details
payslip_rules = types.ModuleType("hrms_addon.hrms_addon.payslip_rules")
payslip_rules.slip_for = lambda end, start=None: "05-11 Nov 2026" if start else "Nov 2026"
sys.modules.update({"frappe": frappe, "frappe.utils": utils, "frappe.desk": desk, "frappe.desk.utils": desk_utils,
                    "hrms_addon.hrms_addon.bank_file": bank_file, "hrms_addon.hrms_addon.payslip_rules": payslip_rules})
G = load("mobile_money")


def site(**changes):
    SITE.clear()
    SITE.update(run={"name": "HR-PRUN-TEST", "docstatus": 1, "salary_slips_submitted": 1, "payroll_frequency": "Weekly",
                     "start_date": D(2026, 11, 5), "end_date": D(2026, 11, 11)},
                tables={"Salary Slip": [
                    {"payroll_entry": "HR-PRUN-TEST", "docstatus": 1, "employee": line["employee"],
                     "employee_name": line["employee_name"], "net_pay": line["amount"]} for line in lines] + [
                    {"payroll_entry": "HR-PRUN-TEST", "docstatus": 0, "employee": "LPC90009", "employee_name": "Draft",
                     "net_pay": 100}],
                    "Employee": [{"name": line["employee"], "salary_mode": line.get("salary_mode"),
                                  "bank_ac_no": line.get("bank_ac_no"), "custom_wages_phone": line.get("phone"),
                                  "custom_wages_phone_names": line.get("registered_name"),
                                  "first_name": line.get("first_name"), "middle_name": line.get("middle_name"),
                                  "last_name": line.get("last_name")} for line in lines]})
    SITE.update(changes)


def refused(call):
    try:
        call()
    except Thrown as error:
        return str(error)
    return None


site()
found = G.check("HR-PRUN-TEST")
check(found == {"rows": 4, "bank": 2, "cheque": 1,
                "blank": ["Telephone left blank in the file:", "No Wages Phone Number: Eve Cash (LPC90004)."]},
      "the button says how many the file pays, whose phone is left blank, and who is paid another way", found)
check(("Employee", ["name", "salary_mode", "bank_ac_no", "first_name", "middle_name", "last_name",
                    "custom_wages_phone", "custom_wages_phone_names"]) in SITE["reads"],
      "each one's number and the name it is registered in, from the Mobile Money section of their employee record")
G.download("HR-PRUN-TEST")
name, extension, content = SITE["file"]
sheet = openpyxl.load_workbook(io.BytesIO(content)).active
check(name == "Mobile Money File 05-11 Nov 2026 HR-PRUN-TEST" and extension == "xlsx"
      and sheet["A1"].value == "TO BANK REPORT FOR THE PERIOD 05TH TO 11TH NOVEMBER, WEEK TWO."
      and [sheet.cell(row=row, column=2).value for row in (3, 4, 5, 6)]
      == ["LPC90004", "LPC90002", "LPC90008", "LPC90001"]
      and sheet["C3"].value is None and sheet["E7"].value == 50565,
      "downloaded: the submitted slips' people paid by mobile money, the one with no phone in it with it blank, the "
      "draft's never", (name, sheet["A1"].value))
site(run=dict(SITE["run"], payroll_frequency="Monthly", start_date=D(2026, 10, 26), end_date=D(2026, 11, 25)))
G.download("HR-PRUN-TEST")
check(openpyxl.load_workbook(io.BytesIO(SITE["file"][2])).active["A1"].value
      == "TO BANK REPORT FOR THE PERIOD 26TH OCTOBER TO 25TH NOVEMBER.", "a monthly payroll's has no week")
site()
SITE["tables"]["Employee"][0]["custom_wages_phone"] = "12345"
found = G.check("HR-PRUN-TEST")
check(found["rows"] == 4 and found["blank"][2:] == [
    "Wages Phone Number not a phone number: Ann Example (LPC90001). Put the nine digits, or 0 and the nine, on their "
    "employee record."],
      "a number that is not one no longer stops the file: the check names whose (Luuka, 13 Nov 2026)", found)
G.download("HR-PRUN-TEST")
row = [cell.value for cell in openpyxl.load_workbook(io.BytesIO(SITE["file"][2])).active[6]]
check(row[1:5] == ["LPC90001", None, None, 19283], "and the file has them, the phone blank, still paid", row)
site(bank_details=False)
check("Only HR and Payroll may see bank details." in (refused(lambda: G.check("HR-PRUN-TEST")) or ""),
      "it carries everyone's phone number: only HR and Payroll may have it, as the bank file")
site(run=dict(SITE["run"], salary_slips_submitted=0))
check("Submit the salary slips first" in (refused(lambda: G.download("HR-PRUN-TEST")) or ""),
      "only once the slips are submitted")
site()
for employee in SITE["tables"]["Employee"]:
    employee["custom_wages_phone"] = None
found = G.check("HR-PRUN-TEST")
check(found["rows"] == 4 and found["blank"][1] == "No Wages Phone Number: Ann Example (LPC90001), Ben Sample "
      "(LPC90002), Eve Cash (LPC90004), =Ivy Formula (LPC90008).",
      "nobody with a phone: all of them in it, each named", found)
site()
for employee in SITE["tables"]["Employee"]:
    employee["salary_mode"] = "Cheque" if employee["salary_mode"] == "Cheque" else "Bank"
empty = "Nobody here is paid in cash or by mobile money, so there is no mobile money file."
check(refused(lambda: G.check("HR-PRUN-TEST")) == empty and refused(lambda: G.download("HR-PRUN-TEST")) == empty,
      "and no empty file")
print("the glue: who is in it, what it reads, who may have it, whose phone is blank, what stops it")

# ── 4. The button, and the bank file pointing to it ───
script = io.open(os.path.join(REPO, "hrms_addon", "public", "js", "payroll_entry.js"), encoding="utf-8").read()
check("\t\tha_payroll_bank_file_button(frm);\n\t\tha_payroll_mobile_money_button(frm);" in script
      and 'const HA_PAYROLL_MOBILE_MONEY = "hrms_addon.hrms_addon.mobile_money.";' in script
      and 'frm.add_custom_button(__("Mobile Money File"), () => {' in script
      and 'method: HA_PAYROLL_MOBILE_MONEY + "check"' in script
      and '"/api/method/" + HA_PAYROLL_MOBILE_MONEY + "download?payroll_entry="' in script
      and "if (doc.docstatus !== 1 || !cint(doc.salary_slips_submitted)) return;" in script,
      "the Mobile Money File button beside the Bank File, once the slips are submitted: asked first, then downloaded")
said_js = script.split("function ha_payroll_mobile_money_said(found) {")[1].split("\n}\n")[0]
check("(found.blank || []).forEach((line) => said.push(frappe.utils.escape_html(line)));" in said_js
      and "no_phone" not in script,
      "the form says whose phone is left blank, each line escaped")
glue = io.open(os.path.join(APP, "mobile_money.py"), encoding="utf-8").read()
check(glue.count("@frappe.whitelist()") == 2 and "def check(payroll_entry):" in glue and "def download(payroll_entry):" in glue,
      "the two calls the button makes are the server's")
bank = io.open(os.path.join(APP, "bank_file.py"), encoding="utf-8").read()
check("Nobody here is paid by bank, so there is no bank file. Those paid in cash through mobile \"\n" in bank
      and '"money are in the Mobile Money File."' in bank,
      "a payroll nobody on is paid by bank says where those paid by mobile money are")
print("the form: the button, and the bank file's word to it")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL MOBILE MONEY CHECKS PASSED")
