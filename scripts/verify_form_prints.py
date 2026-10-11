"""Checks the attendance and leave print outs without a bench.

    python scripts/verify_form_prints.py

Luuka's own papers, printed from the documents that replaced them:

  Off Duty Request Form    LPL/HR/25   Off Duty Request
  Overtime Request Form    LPL/HR/14   Overtime Request
  Gate Pass Slip                       Gate Pass
  Leave Application Form   LPL/HR/15   Leave Application (Frappe HR's)
  Leave Advance Form                   Leave Advance
  the register             LPL/HR/07   the Attendance Board's Print Register

  1  each is a standard Jinja print of this app and the one its document
     opens with
  2  each says what the paper says, prints only fields its document has,
     and escapes what somebody typed
  3  each compiles and renders on a document, read by jinja_subset.py as
     Frappe's Jinja reads it, with nothing left undefined
  4  the overtime form is the floor's paper and carries no pay
  5  the register is drawn from what the board already holds

Frappe HR's own fields are read from FRAPPE_APPS_ROOT (default ../ERPNext).
"""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def doctype(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    if os.path.exists(path):
        return json.load(io.open(path, encoding="utf-8"))
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(io.open(hits[0], encoding="utf-8"))
    return {}


CUSTOM = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
SETTERS = json.loads(read("hrms_addon", "fixtures", "property_setter.json"))


def fields_of(name):
    own = {f["fieldname"]: f for f in doctype(name).get("fields", [])}
    own.update({row["fieldname"]: row for row in CUSTOM if row.get("dt") == name})
    return own


def hooks_dict():
    out = {}
    for node in ast.parse(read("hrms_addon", "hooks.py")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


_spec = importlib.util.spec_from_file_location("jinja_subset", os.path.join(REPO, "scripts", "jinja_subset.py"))
jinja_subset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jinja_subset)

PEOPLE = {"sup@luuka": "Denis Wanyama", "hod@luuka": "Agnes Nanyonga", "hrm@luuka": "Samuel Kato",
          "hro@luuka": "Harriet Ojok", "pm@luuka": "Peter Mugisha", "am@luuka": "Ruth Namara"}
EMPLOYEES = {"E1": {"employee_name": "John Okello", "first_name": "John", "last_name": "Okello"},
             "E2": {"employee_name": "Sam Wafula", "first_name": "Sam", "last_name": "Wafula"}}


def _get_value(kind, name, field):
    return PEOPLE.get(name) if kind == "User" else (EMPLOYEES.get(name) or {}).get(field)


utils = type("utils", (), {"format_date": staticmethod(lambda value: str(value)),
                           "format_datetime": staticmethod(lambda value, fmt=None: str(value)[:16])})
db = type("db", (), {"get_value": staticmethod(_get_value),
                     "get_single_value": staticmethod(lambda kind, field: "/files/luuka.png")})
frappe = type("frappe", (), {"utils": utils, "db": db})

OFF_DUTY = {
    "name": "HR-ODR-0012", "badge_no": "101", "request_date": "2026-10-08", "employee_name": "John <Okello>",
    "department": "Production - LPL", "section": "Extrusion", "off_date": "2026-10-12", "reason": "A burial.",
    "kind": "Compassionate", "supervisor_by": "sup@luuka", "supervisor_on": "2026-10-08",
    "supervisor_remarks": "Cover arranged.", "manager_by": "hod@luuka", "manager_on": "2026-10-09",
    "manager_remarks": None, "hr_by": "hrm@luuka", "hr_on": "2026-10-09", "hr_remarks": "Granted.",
    "status": "Approved"}
OVERTIME = {
    "name": "HR-OTR-0031", "overtime_date": "2026-10-10", "section": "Extrusion", "total_hours": 5.5,
    "reason": "Rush order.", "requested_by": "E2", "requested_on": "2026-10-09", "status": "Authorised",
    "authorised_by": "pm@luuka", "authorised_on": "2026-10-09", "authority_remarks": "For the run.",
    "coupons_casual": 1, "coupons_permanent": 1, "coupons_issued": 1, "coupons_by": "hro@luuka",
    "coupons_on": "2026-10-10", "total_cost": 987654, "multiplier": 1.5,
    "employees": [{"employee_name": "John Okello", "section": "Extrusion", "hours": 3, "employment": "Casual",
                   "hourly_rate": 4321, "amount": 12963},
                  {"employee_name": "Brian <Okot>", "section": "Printing", "hours": 2.5, "employment": "Permanent",
                   "hourly_rate": 4321, "amount": 10802}]}
GATE_PASS = {
    "name": "HR-GP-0044", "pass_date": "2026-10-09", "employee_name": "John Okello", "department": "Production - LPL",
    "section": "Extrusion", "out_time": "2026-10-09 14:00:00", "expected_return": "2026-10-09 16:00:00",
    "reason": "Clinic.", "authorised_by": "sup@luuka", "authorised_on": "2026-10-09", "authority_remarks": None,
    "actual_return": "2026-10-09 15:30:00", "hours_away": 1.5}
LEAVE = {
    "name": "HR-LAP-0210", "employee": "E1", "employee_name": "John Okello", "department": "Production - LPL",
    "custom_work_section": "Extrusion", "custom_date_of_appointment": "2023-01-09", "total_leave_days": 21,
    "from_date": "2026-11-02", "to_date": "2026-11-22", "leave_type": "Annual Leave",
    "description": "As planned.", "custom_salary_requested_in_advance": 1, "posting_date": "2026-10-09",
    "custom_last_leave_from": "2026-03-02", "custom_last_leave_to": "2026-03-06", "custom_last_leave_days": 5,
    "custom_last_leave_type": "Sick Leave", "custom_balance_before": 21, "custom_balance_after": 0,
    "custom_sick_balance_before": 9, "custom_sick_balance_after": 9, "custom_hro_by": "hro@luuka",
    "custom_hro_on": "2026-10-10", "custom_leave_status": "Approved", "custom_supervisor_by": "sup@luuka",
    "custom_supervisor_on": "2026-10-09", "custom_supervisor_remarks": "Cover arranged.",
    "custom_hod_by": "hod@luuka", "custom_hod_on": "2026-10-10", "custom_hod_remarks": None,
    "custom_hr_by": "hro@luuka", "custom_hr_on": "2026-10-10", "custom_hr_remarks": None,
    "custom_advance_amount": 600000, "custom_accounts_by": "am@luuka", "custom_accounts_on": "2026-10-12"}
ADVANCE = {
    "name": "HR-LVA-0009", "posting_date": "2026-10-10", "employee": "E1", "employee_name": "John Okello",
    "department": "Production - LPL", "branch": "Kawempe", "leave_type": "Annual Leave", "leave_days": 21,
    "from_date": "2026-11-02", "to_date": "2026-11-22", "leave_application": "HR-LAP-0210", "status": "Paid",
    "pay_category": "Monthly", "gross_pay": 1000000, "allowed_amount": 600000, "amount": 600000,
    "instalments": 2, "first_deduction": "2026-11-25", "eligibility_remarks": None, "outstanding": 300000,
    "recoveries": [{"payroll_date": "2026-11-25", "amount": 300000, "recovered": 1},
                   {"payroll_date": "2026-12-25", "amount": 300000, "recovered": 0}],
    "accounts_manager_by": "am@luuka", "accounts_manager_on": "2026-10-12", "accounts_manager_remarks": None,
    "paid_on": "2026-10-12"}

# name: (document, its tables, what the paper says, a document, what the print of it reads)
PRINTS = {
    "Off Duty Request Form": ("Off Duty Request", (), [
        "Reference: LPL/HR/25", "Issue Date: 24/4/2017", "EMPLOYEES OFF-DUTY REQUEST FORM", "Badge No.",
        "Absent Date on:", "Paid/Ungranted/Compensation/Annual leave/Compassionate:", "Supervisor",
        "Section Manager", "Remarks for Human Resource Manager:"], OFF_DUTY, [
        "Badge No. 101", "Name: John &lt;Okello&gt;", "Absent Date on: 2026-10-12", "A burial.", "Compassionate",
        "Denis Wanyama Supervisor &nbsp; 2026-10-08 Cover arranged.", "Agnes Nanyonga Section Manager",
        "Granted.", "Samuel Kato Human Resource Manager", "Approved Decision"]),
    "Overtime Request Form": ("Overtime Request", ("Overtime Request Employee",), [
        "Doc No: LPL/HR/14", "Issue Date: 31.07.2017", "OVERTIME REQUEST FORM", "<th>NAMES</th>", "SECTION",
        "DURATION", "Employment", "Requesting officer:", "AUTHORISED BY:",
        "HR USE ONLY: Please provide food coupon to:", "Casuals", "Permanent Staff"], OVERTIME, [
        "1 John Okello Extrusion 3 hrs Casual", "2 Brian &lt;Okot&gt; Printing 2.5 hrs Permanent", "Total 5.5 hrs",
        "Requesting officer: Sam Wafula", "AUTHORISED BY: Peter Mugisha", "Casuals 1", "Permanent Staff 1",
        "Coupons issued by Harriet Ojok on 2026-10-10."]),
    "Gate Pass Slip": ("Gate Pass", (), [
        "GATE PASS", "Time out:", "Expected back:", "Authorised by", "Employee's signature", "At the gate",
        "Security officer, name and signature"], GATE_PASS, [
        "No: HR-GP-0044", "Name: John Okello", "Time out: 2026-10-09 14:00", "Expected back: 2026-10-09 16:00",
        "Clinic.", "Denis Wanyama Authorised by", "Back 2026-10-09 15:30", "Away 1.5 hours."]),
    "Leave Application Form": ("Leave Application", (), [
        "Doc Ref. No: LPL/HR/15", "Initial Issue Date: 24/4/2017", "LEAVE APPLICATION FORM",
        "Part 1: To be filled by applicant", "Date of appointment:", "No. of leave days applied for",
        "Type of Leave: (Please tick)", "Maternity/Paternity Leave:", "(Attach Medical Certificate)",
        "(Precise Reason)", "Leave without Pay:", "Salary Requested in Advance:", "Employee's signature",
        "Part 2: To be filled by Human Resource/ Administration Officer", "Dates when last leave was taken: From",
        "Net Balance of Leave due", "Net Balance of sick leave entitlement", "Signature (HRO)", "Part 3: Approval",
        "Signed by: Manager in line: Name", "Head of Dept: Name", "Comments:", "Approved By: Name",
        "Part 4: Accounts Officer", "Salary Advance/Loan", "Ugshs"], LEAVE, [
        "Surname: Okello First Name: John Dept. Production - LPL Section Extrusion",
        "No. of leave days applied for 21 Leave Start Date 2026-11-02 Leave End Date 2026-11-22",
        "Annual Leave: &#10003;", "From 2026-03-02 To 2026-03-06 No of Days 5 type of leave Sick Leave",
        "Net Balance of Leave due 21 days before the leave", "Net Balance of leave due 0 days after the leave",
        "Signature (HRO) Harriet Ojok Date 2026-10-10", "Manager in line: Name Denis Wanyama",
        "Head of Dept: Name Agnes Nanyonga", "Approved By: Name Harriet Ojok", "Salary Advance/Loan 600,000 Ugshs",
        "Signature Ruth Namara Date 2026-10-12"]),
    "Leave Advance Form": ("Leave Advance", ("Leave Advance Recovery",), [
        "LEAVE ADVANCE", "Gross pay (UGX)", "Most that may be advanced (UGX)", "Amount advanced (UGX)",
        "Recovery from salary", "Outstanding", "Accounts Manager", "Received by the employee, signature and date"],
        ADVANCE, [
        "No: HR-LVA-0009", "Employee John Okello", "Leave Annual Leave, 21 days",
        "From, to 2026-11-02 to 2026-11-22", "Gross pay (UGX) 1,000,000", "Amount advanced (UGX) 600,000",
        "2 month(s), from 2026-11-25", "1 2026-11-25 300,000 Yes", "2 2026-12-25 300,000", "Outstanding 300,000",
        "Ruth Namara Accounts Manager", "Paid on 2026-10-12."]),
}
MACROS = ("v(", "day(", "clock(", "who(", "person(", "num(", "zero(", "money(")
NUMERIC = {"Int", "Float", "Percent", "Currency", "Check", "Table"}
STANDARD = {"name", "docstatus", "doctype", "idx", "parent"}
hooks = hooks_dict()
listed = {name for entry in hooks.get("fixtures", []) if isinstance(entry, dict)
          for flt in entry.get("filters", []) for name in (flt[2] if isinstance(flt[2], list) else [flt[2]])}


def text_of(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S))).strip()


def printed(name, values):
    folder = name.lower().replace(" ", "_")
    html = json.load(io.open(os.path.join(APP, "print_format", folder, folder + ".json"), encoding="utf-8"))["html"]
    return jinja_subset.compile_template(html)({"doc": jinja_subset.wrap(values), "frappe": frappe})


for name, (doc_type, tables, needles, sample, reads) in PRINTS.items():
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "print_format", folder, folder + ".json")
    if not os.path.exists(path):
        fail.append("the %s print format is not there" % name)
        continue
    spec = json.load(io.open(path, encoding="utf-8"))
    if (spec.get("doc_type"), spec.get("print_format_type"), spec.get("standard"), spec.get("custom_format"),
            spec.get("module"), spec.get("name")) != (doc_type, "Jinja", "Yes", 1, "HRMS Addon", name):
        fail.append("%s is a standard Jinja print format of this app for the %s" % (name, doc_type))
    if not os.path.exists(os.path.join(APP, "print_format", folder, "__init__.py")):
        fail.append("%s has no __init__.py, so it is not packaged" % name)
    # the print its document opens with
    own_json = os.path.join(APP, "doctype", doc_type.lower().replace(" ", "_"),
                            doc_type.lower().replace(" ", "_") + ".json")
    if os.path.exists(own_json):
        if doctype(doc_type).get("default_print_format") != name:
            fail.append("%s prints as %s unless another is chosen (default_print_format)" % (doc_type, name))
    else:
        key = "%s-main-default_print_format" % doc_type
        setter = next((row for row in SETTERS if row["name"] == key), {})
        if (setter.get("property"), setter.get("value"), setter.get("doc_type")) \
                != ("default_print_format", name, doc_type) or key not in listed:
            fail.append("%s is Frappe HR's: it prints as %s by a property setter hooks.py lists" % (doc_type, name))
    html = spec.get("html") or ""
    for needle in needles:
        if needle not in html:
            fail.append("%s does not say %r, which the paper does" % (name, needle))
    own = fields_of(doc_type)
    rows = {}
    for table in tables:
        rows.update(fields_of(table))
    for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html))):
        if fieldname not in own and fieldname not in STANDARD:
            fail.append("%s prints doc.%s, which the %s does not have" % (name, fieldname, doc_type))
    for fieldname in sorted(set(re.findall(r"\brow\.(\w+)", html))):
        if fieldname not in rows and fieldname not in STANDARD:
            fail.append("%s prints row.%s, which none of its tables has" % (name, fieldname))
    # what somebody typed goes out escaped: through one of the macros, or | e
    for expression in re.findall(r"\{\{-?(.*?)-?\}\}", html, flags=re.S):
        text = expression.strip()
        if text.startswith(MACROS) or "| e" in text:
            continue
        for owner, fieldname in re.findall(r"\b(doc|row)\.(\w+)", text):
            field = (own if owner == "doc" else rows).get(fieldname) or {}
            if field.get("fieldtype") not in NUMERIC:
                fail.append("%s prints %s.%s unescaped: use v()" % (name, owner, fieldname))
    # nobody's pay level decides what a form shows: these documents have no such field
    secret = sorted(fieldname for fieldname in set(re.findall(r"\b(?:doc|row)\.(\w+)", html))
                    if ((own.get(fieldname) or rows.get(fieldname) or {}).get("permlevel")))
    if secret:
        fail.append("%s prints %s, which not everybody who may print it may read" % (name, ", ".join(secret)))
    try:
        page = printed(name, sample)
    except Exception as error:  # noqa: BLE001
        fail.append("%s does not compile or render: %s" % (name, error))
        continue
    left = sorted(set(re.findall(r"\{\{ [\w.]+ \}\}", page)))
    if left:
        fail.append("%s leaves %s undefined on a document" % (name, ", ".join(left)))
    if '<img src="/files/luuka.png"' not in page:
        fail.append("%s carries the company's logo from the branding settings" % name)
    text = text_of(page)
    for needle in reads:
        if needle not in text:
            fail.append("%s should read %r: %s" % (name, needle, text))
print("the five forms: each a standard print its document opens with, in the paper's words, on fields that exist, "
      "escaped, rendered")

# ── the overtime form is the floor's paper ────────────────────────────
overtime_html = json.load(io.open(os.path.join(APP, "print_format", "overtime_request_form",
                                               "overtime_request_form.json"), encoding="utf-8"))["html"]
for fieldname in ("hourly_rate", "amount", "total_cost", "multiplier", "payable_hours", "worked_hours"):
    if re.search(r"\b(?:doc|row)\.%s\b" % fieldname, overtime_html):
        fail.append("the Overtime Request Form prints %s: it goes to the floor, and carries no pay" % fieldname)
page = text_of(printed("Overtime Request Form", OVERTIME))
for figure in ("4321", "4,321", "12963", "987654", "987,654"):
    if figure in page:
        fail.append("the Overtime Request Form shows a pay figure (%s)" % figure)
refused = text_of(printed("Overtime Request Form", dict(OVERTIME, status="Rejected", coupons_issued=0,
                                                       authority_remarks="The order was cancelled.")))
if "NOT AUTHORISED: Peter Mugisha" not in refused or "AUTHORISED BY:" in refused \
        or "The order was cancelled." not in refused or "Coupons issued" in refused:
    fail.append("a refused overtime sheet prints as not authorised, by whom and why: %s" % refused)
print("the overtime form: the names and the hours, no pay, and a refusal printed as one")

# ── the leave form ticks what was applied for ─────────────────────────
ticks = {"Annual Leave": "Annual Leave: &#10003;", "Maternity Leave": "Maternity/Paternity Leave: &#10003;",
         "Paternity Leave": "Maternity/Paternity Leave: &#10003;", "Sick Leave": "Sick Leave: &#10003;",
         "Sick Leave (Half Pay)": "Sick Leave: &#10003;", "Compassionate Leave": "Compassionate Leave: &#10003;",
         "Leave Without Pay": "Leave without Pay: &#10003;", "Study Leave": "Study Leave: &#10003;"}
LEAVE_RULES = None
_rules = importlib.util.spec_from_file_location("leave_rules", os.path.join(APP, "leave_rules.py"))
LEAVE_RULES = importlib.util.module_from_spec(_rules)
_rules.loader.exec_module(LEAVE_RULES)
for leave_type in LEAVE_RULES.LEAVE_TYPES:
    if leave_type not in ticks:
        fail.append("the leave form has no box for %s, a Leave Type the app seeds" % leave_type)
for leave_type, needle in ticks.items():
    page = text_of(printed("Leave Application Form", dict(LEAVE, leave_type=leave_type, description="A burial.")))
    # exactly one type is ticked, beside the Yes of the advance
    if needle not in page or page.count("&#10003;") != 2:
        fail.append("a leave applied for as %s ticks that box and no other: %s" % (leave_type, page))
    if ("(Precise Reason) A burial." in page) != (leave_type == "Compassionate Leave"):
        fail.append("the precise reason is printed for compassionate leave, and only for it (%s)" % leave_type)
blank = text_of(printed("Leave Application Form", {"employee": "E2", "employee_name": "Sam Wafula",
                                                  "leave_type": "Annual Leave", "custom_leave_status": "Draft"}))
if "Salary Requested in Advance: Yes &nbsp; &#10003; No" not in blank or "days before the leave" not in blank \
        or re.search(r"Net Balance of [Ll]eave due \d", blank):
    fail.append("a form nobody has filled in yet prints its lines empty, and No for the advance: %s" % blank)
unnamed = text_of(printed("Leave Application Form", dict(LEAVE, employee="E9")))
if "Surname: John Okello First Name: Dept." not in unnamed:
    fail.append("with no surname on record the whole name goes on the surname line, once: %s" % unnamed)
print("the leave form: one box ticked, the reason where the paper asks for it, empty lines left empty")

# ── LPL/HR/07 from the board ──────────────────────────────────────────
board_js = read("hrms_addon", "hrms_addon", "page", "attendance_board", "attendance_board.js")
sheet = board_js.split("hrms_addon.register_sheet = function")[1] if "hrms_addon.register_sheet = function" \
    in board_js else ""
for needle, why in (
    ('this.page.add_menu_item(__("Print Register"), () => this.print_register());', "the board's menu prints it"),
    ("hrms_addon.register_sheet(this.board, {", "from what the board is showing"),
    ("sheet.print();", "to the printer"),
):
    if needle not in board_js:
        fail.append("attendance_board.js: %s (%r not found)" % (why, needle))
for needle, why in (
    ("REV.001 &nbsp; LPL/HR/07", "the sheet's own reference"), ("SHIFT SUPERVISOR'S NAME", "the supervisor's line"),
    ("SHIFT (DAY / NIGHT)", "the shift"), ("PRODUCTION OFFICER / MANAGER'S NAME", "the production officer's line"),
    ("<th class=\"n\">S/NO.</th><th class=\"who\">NAME</th>", "numbered rows by name"),
    ("Total OT (HRS)", "the overtime total"),
    ("CHECKED BY; SUPERVISOR", "who checked it"), ("@page { size: A4 landscape;", "landscape, as the sheet is"),
    ("esc(row.employee_name || row.employee)", "a name is escaped"),
    ("board.register.tallies", "the footer's counts are the board's"),
    ("total_first(one) - total_first(other)", "with the night shift's total above them, as printed"),
    ("board.codes", "and the letters' meanings are the register's own"),
):
    if needle not in sheet:
        fail.append("the register sheet: %s (%r not found)" % (why, needle))
if "frappe.call" in sheet or "xcall" in sheet:
    fail.append("the register sheet asks the server nothing: it prints what the board holds")
print("the register: LPL/HR/07 from the board's own rows, landscape, with the lines that are signed")

print()
if fail:
    print("FAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("ALL FORM PRINT CHECKS PASSED")
