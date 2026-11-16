"""Checks for the Download button on Salary Advance Processing (Luuka, 16 Nov 2026, on November's run of 721 lines:
"add download functionality").

Runs without a bench: advance_run_sheet_rules.py on its own and read back with openpyxl, salary_advances.download
lifted out and run on a stand-in, the button read as text. Every person and number here is made up.

    python scripts/verify_advance_run_sheet.py
"""
import ast
import importlib.util
import io
import os
import sys
import types

import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else "   <- %s" % (detail,))
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


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
S = load("advance_run_sheet_rules")
print("loaded advance_run_sheet_rules.py without Frappe")

LINES = [
    {"idx": 1, "employee": "EMP-001", "employee_name": "Ann  Example", "branch": "Plant A", "department": "Production",
     "pay_category": "Regular", "gross_pay": 800000, "amount": 320000.004, "days_absent": 0, "days_unmarked": 0,
     "qualifies": 1, "include": 1, "remarks": None, "request": "REQ-001"},
    {"idx": 2, "employee": "EMP-002", "employee_name": "Ben Sample", "branch": "Plant B", "department": "Stores",
     "pay_category": "Regular", "gross_pay": 400000, "amount": 160000, "days_absent": None, "days_unmarked": 19,
     "qualifies": 0, "include": 1, "remarks": "Attendance not marked for 19 working day(s)\nsince 26 Oct 2026.",
     "request": "REQ-002"},
    {"idx": 3, "employee": "EMP-003", "employee_name": "=Cy Formula", "branch": None, "department": None,
     "pay_category": "Per Meter", "gross_pay": None, "amount": 110000, "days_absent": 2, "days_unmarked": 0,
     "qualifies": 1, "include": 0, "remarks": "Left out by HR.", "request": "REQ-003"},
]

# ── 1. The rules ──────────────────────────────────────
HEADINGS = ["No.", "Employee", "Name", "Plant", "Department", "Pay Category", "Gross Pay", "Amount", "Days Absent",
            "Days Not Marked", "Qualifies", "Pay", "Reason", "Request"]
check([heading for heading, *_ in S.COLUMNS] == HEADINGS,
      "the run's table columns, and what the row form holds besides; no bank details (the Bank File has them)")
body = S.rows(LINES)
check(body[0] == [1, "EMP-001", "Ann Example", "Plant A", "Production", "Regular", 800000.0, 320000.0, 0, 0, "Yes",
                  "Yes", "", "REQ-001"],
      "a line each, in the run's order: amounts to the cent, Qualifies and Pay as Yes or No", body[0])
check(body[1][8:13] == [0, 19, "No", "Yes", "Attendance not marked for 19 working day(s) since 26 Oct 2026."]
      and body[2][3:7] == ["", "", "Per Meter", 0.0] and body[2][10:12] == ["Yes", "No"],
      "nothing missing reads as a blank or a nought; the reason on one line", (body[1], body[2]))
last = S.total(LINES)
check(last[S.NAME] == "To pay: 1 of 3" and last[S.AMOUNT] == 320000.0 and last.count("") == len(HEADINGS) - 2,
      "the last row: how many the run pays and how much, those that qualify and are ticked to pay only", last)
check(S.total([]) [S.NAME] == "To pay: 0 of 0" and S.rows([]) == [], "an empty run says nought")
check(S.file_name("November", 2026, "SAP-1") == "Salary Advance November 2026 SAP-1",
      "the file is named for the month and the run", S.file_name("November", 2026, "SAP-1"))
print("rules: the columns, a line each, the total, the file's name")

# ── 2. The workbook ───────────────────────────────────
sheet = openpyxl.load_workbook(io.BytesIO(S.workbook(LINES))).active
values = [[cell.value for cell in row] for row in sheet.iter_rows()]
check(sheet.title == "Lines" and values[0] == HEADINGS and len(values) == 5, "the headings, three lines, the total",
      values[:1])
check(values[1][:8] == [1, "EMP-001", "Ann Example", "Plant A", "Production", "Regular", 800000, 320000]
      and values[2][12] == "Attendance not marked for 19 working day(s) since 26 Oct 2026."
      and values[4][2] == "To pay: 1 of 3" and values[4][7] == 320000,
      "read back as written", values[1:])
check(sheet["C4"].data_type == "s" and sheet["C4"].value == "=Cy Formula", "a name that starts with = is a name, never a formula")
check(all(sheet.cell(row=row, column=column).number_format == S.MONEY for row in (2, 3, 4) for column in (7, 8))
      and sheet["H5"].number_format == S.MONEY,
      "Gross Pay and Amount shown as money, the total too")
check(all(cell.font.b for cell in sheet[1]) and all(cell.font.b for cell in sheet[5]) and not sheet["A2"].font.b,
      "the headings and the total in bold")
check(sheet.freeze_panes == "D2" and sheet.auto_filter.ref == "A1:N4",
      "filters on the headings over the lines, the total left out; the names stay in view", (sheet.freeze_panes,
                                                                                            sheet.auto_filter.ref))
check({letter: sheet.column_dimensions[letter].width for letter in "ACM"} == {"A": 6, "C": 30, "M": 60}
      and sheet["M3"].alignment.wrap_text,
      "columns sized, the reason wrapped")
print("the workbook: headings, lines, total, money, filters")

# ── 3. The server call, lifted out and run on a stand-in ──


class Thrown(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def as_dict(self):
        return dict(self)


SITE = {}
frappe = types.ModuleType("frappe")
frappe.throw = lambda message, title=None, *args, **kwargs: (_ for _ in ()).throw(Thrown(message))
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if not args or not callable(args[0]) else args[0]


class Run(Row):
    def check_permission(self, ptype):
        SITE["asked"].append(ptype)
        if not SITE["may_read"]:
            raise Thrown("No permission for Salary Advance Processing")

    def get(self, key, default=None):
        return dict.get(self, key, default)


frappe.get_doc = lambda doctype, name: SITE["docs"][(doctype, name)]
desk = types.ModuleType("frappe.desk")
desk.__path__ = []
desk_utils = types.ModuleType("frappe.desk.utils")
desk_utils.provide_binary_file = lambda filename, extension, content: SITE.update(file=(filename, extension, content))
sys.modules.update({"frappe": frappe, "frappe.desk": desk, "frappe.desk.utils": desk_utils})
source = read("hrms_addon", "hrms_addon", "salary_advances.py")
found = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "download"]
check(len(found) == 1 and any(isinstance(item, ast.Call) and getattr(item.func, "attr", "") == "whitelist"
                              for item in found[0].decorator_list),
      "salary_advances.download is there, and whitelisted")
space = {"frappe": frappe, "_": lambda text: text, "RUN": "Salary Advance Processing"}
exec(compile(ast.Module(body=found, type_ignores=[]), "salary_advances.download", "exec"), space)
download = space["download"]


def site(lines=LINES, may_read=True):
    SITE.clear()
    SITE.update(asked=[], may_read=may_read, docs={("Salary Advance Processing", "SAP-1"): Run(
        name="SAP-1", month="November", year=2026, employees=[Row(line) for line in lines])})


def refused(call):
    try:
        call()
    except Thrown as error:
        return str(error)
    return None


site()
download("SAP-1")
name, extension, content = SITE["file"]
book = openpyxl.load_workbook(io.BytesIO(content)).active
check(SITE["asked"] == ["read"] and (name, extension) == ("Salary Advance November 2026 SAP-1", "xlsx")
      and book["B2"].value == "EMP-001" and book.max_row == 5,
      "Download gives the saved run's lines as Excel, to whoever may read the run", (SITE["asked"], name, extension))
site(lines=[])
check(refused(lambda: download("SAP-1")) == "This run has no lines yet. Get Requests first." and "file" not in SITE,
      "a run with no lines says so, and gives no file")
site(may_read=False)
check("No permission" in (refused(lambda: download("SAP-1")) or "") and "file" not in SITE,
      "and nobody who may not read the run has it")
print("the server call: the saved lines, read permission, no empty file")

# ── 4. The button ─────────────────────────────────────
script = read("hrms_addon", "hrms_addon", "doctype", "salary_advance_processing", "salary_advance_processing.js")
button = script.split("if (!frm.is_new() && (frm.doc.employees || []).length) {", 1)[1].split("\n\t\t}\n", 1)[0] \
    if "if (!frm.is_new() && (frm.doc.employees || []).length) {" in script else ""
check('frm.add_custom_button(__("Download"), () => {' in button
      and 0 < button.find("if (frm.is_dirty()) {") < button.find("window.open(")
      and '"/api/method/hrms_addon.hrms_addon.salary_advances.download?name=" + encodeURIComponent(frm.doc.name)'
      in button,
      "Download on any saved run with lines, draft or submitted; unsaved changes are saved first")
check(script.find('frm.add_custom_button(__("Download")') < script.find("if (frm.doc.docstatus === 1) {"),
      "it does not wait for the run to be submitted")
print("the form: the Download button")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL ADVANCE RUN SHEET CHECKS PASSED")
