"""Checks for a member of staff hired through recruitment, run without a
bench.

internal_hire_rules.py imports nothing from Frappe, so it is loaded
directly: an application is linked to an employee only when exactly one
active record matches; a new job title is a Position Change, the same job
title elsewhere a Transfer, and nothing to change is nothing. It also checks
the glue (the link on a new application, Create Employee refused for staff,
the move made from the offer, the one already made found), the Position
Change's new plant and department applied and put back, the fields, the Job
Offer's form script, Time to Hire's joining date, and against Frappe HR
(../ERPNext, or FRAPPE_APPS_ROOT) what the move rests on.

    python scripts/verify_internal_hires.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def function(source, name):
    """A function's text, up to the first line not inside it."""
    start = source.index("def %s(" % name)
    depth = start - (source.rfind(chr(10), 0, start) + 1)
    lines = source[start:].split(chr(10))
    kept = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= depth:
            break
        kept.append(line)
    return chr(10).join(kept)


R = load("internal_hire_rules")
print("loaded internal_hire_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
for rows, wanted in (
        ([{"name": "E1", "status": "Active"}], "E1"),
        ([{"name": "E1", "status": "Active"}, {"name": "E1", "status": "Active"}], "E1"),
        ([{"name": "E1", "status": "Active"}, {"name": "E2", "status": "Active"}], None),
        ([{"name": "E1", "status": "Left"}], None),
        ([{"name": "E1", "status": "Left"}, {"name": "E2", "status": "Active"}], "E2"),
        ([], None), (None, None)):
    if R.employee_match(rows) != wanted:
        fail.append("employee_match(%r) should be %r, is %r" % (rows, wanted, R.employee_match(rows)))
staff = {"designation": "Machine Operator", "branch": "Kawempe", "department": "Production"}
for target, wanted, kind in (
        ({"designation": "Shift Supervisor", "branch": "Kawempe", "department": "Production"},
         {"designation": ("Machine Operator", "Shift Supervisor")}, R.POSITION_CHANGE),
        ({"designation": "Shift Supervisor", "branch": "Namanve", "department": None},
         {"designation": ("Machine Operator", "Shift Supervisor"), "branch": ("Kawempe", "Namanve")}, R.POSITION_CHANGE),
        ({"designation": "Machine Operator", "branch": "Matugga", "department": "Production"},
         {"branch": ("Kawempe", "Matugga")}, R.TRANSFER),
        ({"designation": "Machine Operator", "branch": "", "department": "Maintenance"},
         {"department": ("Production", "Maintenance")}, R.TRANSFER),
        ({"designation": "Machine Operator", "branch": "Kawempe", "department": "Production"}, {}, None),
        ({}, {}, None)):
    moves = R.changes(staff, target)
    if moves != wanted or R.move_kind(moves) != kind:
        fail.append("moving %r to %r: %r by %r, expected %r by %r" % (staff, target, moves, R.move_kind(moves), wanted,
                                                                       kind))
rows = R.transfer_rows({"designation": ("A", "B"), "branch": (None, "Namanve"), "department": ("Production", "Stores")})
if rows != [{"property": "Branch", "fieldname": "branch", "current": "", "new": "Namanve"},
            {"property": "Department", "fieldname": "department", "current": "Production", "new": "Stores"}]:
    fail.append("the Transfer's rows are the branch and the department, as Frappe HR writes them: %s" % rows)
print("the rules: the one active employee, the kind of move, the Transfer's rows")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "internal_hires.py")
link = function(glue, "link_employee")
if 'if doc.is_new() and not doc.get("custom_employee"):' not in link \
        or "rules.employee_match(cv_screening.employees_like(doc, limit=5))" not in link:
    fail.append("a new application, and only a new one, is linked to the one employee it points to")
refuse = function(glue, "refuse_new_employee")
if 'frappe.db.get_value("Employee", staff, "status") == "Active"' not in refuse or "frappe.throw(" not in refuse:
    fail.append("Create Employee is refused for an applicant on the staff")
make = function(glue, "make_internal_move")
for needle, why in (
        ('offer.check_permission("read")', "for whoever may read the offer"),
        ("employee, moves, kind = _move_for(offer)", "the moves from the offer"),
        ("if not kind:", "nothing to change is said"),
        ("doc = frappe.new_doc(kind)", "a new document, not saved"),
        ('"change_type": "Promotion"', "a Position Change starts as a promotion"),
        ('"new_designation": offer.designation', "to the offer's job title"),
        ('"job_offer": offer.name', "the Position Change names its offer"),
        ('"new_branch": moves.get("branch", (None, None))[1]', "and its new plant"),
        ('"custom_job_offer": offer.name', "the Transfer names its offer"),
        ('doc.append("transfer_details", row)', "the Transfer's rows")):
    if needle not in make:
        fail.append("make_internal_move: %s" % why)
move_for = function(glue, "_move_for")
if '"branch": offer.get("custom_branch")' not in move_for \
        or 'frappe.db.get_value("Job Opening", opening, "department")' not in move_for:
    fail.append("the target is the offer's job title and branch, and the opening's department")
found = function(glue, "get_internal_move")
if '((rules.POSITION_CHANGE, "job_offer"), (rules.TRANSFER, "custom_job_offer"))' not in found \
        or '"docstatus": ["!=", 2]' not in found:
    fail.append("the move already made for the offer, a cancelled one aside")
for name in ("make_internal_move", "get_internal_move"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("%s is whitelisted" % name)
bio = read("hrms_addon", "hrms_addon", "bio_data.py")
for name, source in (("make_employee_from_job_offer", '"Job Offer", source_name, "job_applicant"'),
                     ("make_employee_from_onboarding", '"Employee Onboarding", source_name, "job_applicant"')):
    body = function(bio, name)
    if "internal_hires.refuse_new_employee(frappe.db.get_value(%s))" % source not in body \
            or body.index("refuse_new_employee") > body.index("make_employee(source_name"):
        fail.append("%s refuses staff before it builds the employee" % name)
hooks = read("hrms_addon", "hooks.py")
validate = hooks.split('"Job Applicant": {', 1)[-1].split("],", 1)[0]
if not (0 <= validate.find("internal_hires.link_employee") < validate.find("cv_screening.applicant_validate")):
    fail.append("hooks.py: the application is linked before it is screened, so its flags say so")
print("glue: the link on a new application, Create Employee refused, the move made or found")

# ── 3. The Position Change moves the plant and department ─────────────
positions = read("hrms_addon", "hrms_addon", "positions.py")
apply = function(positions, "_apply")
if 'if changes_designation and doc.get("new_branch"):\n        update["branch"] = doc.new_branch' not in apply \
        or 'if changes_designation and doc.get("new_department"):\n        update["department"] = doc.new_department' \
        not in apply:
    fail.append("an approved Position Change moves the employee to its new plant and department")
cancel = function(positions, "change_on_cancel")
if 'if doc.get("new_branch") and doc.get("branch"):\n        update["branch"] = doc.branch' not in cancel \
        or 'if doc.get("new_department") and doc.get("department"):\n        update["department"] = doc.department' \
        not in cancel:
    fail.append("cancelling it puts the plant and department back")
change = {f["fieldname"]: f for f in json.loads(read("hrms_addon", "hrms_addon", "doctype", "employee_position_change",
                                                     "employee_position_change.json"))["fields"]}
for fieldname, options in (("new_branch", "Branch"), ("new_department", "Department"), ("job_offer", "Job Offer")):
    if (change.get(fieldname) or {}).get("options") != options:
        fail.append("Employee Position Change has no %s (a link to %s)" % (fieldname, options))
if (change.get("branch") or {}).get("fetch_from") != "employee.branch" \
        or (change.get("department") or {}).get("fetch_from") != "employee.department" \
        or not (change.get("job_offer") or {}).get("read_only"):
    fail.append("the plant and department it holds are the employee's before the move; the offer is set, not typed")
print("position change: the new plant and department, applied and put back")

# ── 4. The fields and the forms ───────────────────────────────────────
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
for name, options in (("Job Applicant-custom_employee", "Employee"), ("Job Offer-custom_employee", "Employee"),
                      ("Employee Transfer-custom_job_offer", "Job Offer")):
    row = custom.get(name) or {}
    if row.get("fieldtype") != "Link" or row.get("options") != options:
        fail.append("%s is a link to %s" % (name, options))
    if '"%s",' % name not in hooks:
        fail.append("hooks.py fixtures must list %s" % name)
if (custom.get("Job Offer-custom_employee") or {}).get("fetch_from") != "job_applicant.custom_employee" \
        or not (custom.get("Job Offer-custom_employee") or {}).get("read_only"):
    fail.append("the offer takes Current Employee from its applicant")
offer_js = read("hrms_addon", "public", "js", "job_offer.js")
for needle, why in (
        ('if (frm.doc.custom_employee) {\n\t\t\tfrm.remove_custom_button(__("Create Employee"));', "no second employee"),
        ("if (frm.doc.custom_employee) {\n\t\t\tha_internal_move(frm);\n\t\t\treturn;", "the move, not the onboarding"),
        ('frappe.xcall(HA_INTERNAL + "get_internal_move", { job_offer: frm.doc.name })', "the move made, or to make"),
        ('frappe.model.open_mapped_doc({ method: HA_INTERNAL + "make_internal_move", frm: frm })', "made from the offer")):
    if needle not in offer_js:
        fail.append("job_offer.js: %s" % why)
tth = read("hrms_addon", "hrms_addon", "report", "time_to_hire", "time_to_hire.py")
if "joined_on = joined.get(offer.job_applicant) or moved.get(offer.name)" not in tth:
    fail.append("Time to Hire: a member of staff joins on their move's date")
print("fields and forms: Current Employee, the offer's Create > Position Change or Transfer")

# ── 5. What Frappe HR must still do ───────────────────────────────────
if UPSTREAM_OK:
    transfer = upstream("hrms", "hr", "doctype", "employee_transfer", "employee_transfer.py")
    if "employee = update_employee_work_history(employee, self.transfer_details, date=self.transfer_date)" \
            not in transfer:
        fail.append("Frappe HR's Employee Transfer no longer applies its rows to the employee: recheck the Transfer")
    history = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "employee_property_history",
                                                           "employee_property_history.json"))["fields"]}
    if not {"property", "fieldname", "current", "new"} <= history:
        fail.append("Frappe HR's property rows changed: recheck transfer_rows")
    utils = upstream("hrms", "hr", "utils.py")
    if "def update_employee_work_history(" not in utils or "setattr(employee, item.fieldname, new_value)" not in utils:
        fail.append("Frappe HR sets the employee's fields from the rows differently now: recheck transfer_rows")
    offer = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "job_offer", "job_offer.json"))["fields"]}
    if not {"job_applicant", "applicant_email", "designation"} <= offer:
        fail.append("Frappe HR's Job Offer changed: recheck the move")
    offer_js = upstream("hrms", "hr", "doctype", "job_offer", "job_offer.js")
    if 'frm.add_custom_button(__("Create Employee"), function () {' not in offer_js:
        fail.append("Frappe HR's Create Employee button changed: recheck that staff are not hired twice")
    mapper = upstream("frappe", "model", "mapper.py")
    mapped = mapper.split("def make_mapped_doc(", 1)[-1].split(chr(10) + "def ", 1)[0]
    if "def make_mapped_doc(" not in mapper or "frappe.is_whitelisted(method)" not in mapped:
        fail.append("Frappe's open_mapped_doc changed: recheck Create > Position Change")
    upstream_note = "checked against Frappe and Frappe HR"
else:
    upstream_note = "Frappe HR not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL INTERNAL HIRE CHECKS PASSED")
