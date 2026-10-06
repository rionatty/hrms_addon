"""Next Steps on every form (next_steps.py, next_steps_rules.py,
public/js/hrms_addon_next_steps.js), checked without a bench.

Every step of the process map is checked against the doctypes as the site
has them (this app's JSON, Frappe HR's and ERPNext's, and this app's Custom
Fields): the field, table or back link it follows exists and points the
right way, so a step can never quietly lead nowhere.
"""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


CUSTOM = json.load(io.open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
_specs = {}


def doctype(name):
    """A doctype's JSON, this app's first, then Frappe HR's, ERPNext's and
    Frappe's; None where none has it."""
    if name in _specs:
        return _specs[name]
    folder = name.lower().replace(" ", "_").replace("-", "_")
    hits = glob.glob(os.path.join(APP, "doctype", folder, folder + ".json"))
    for app in ("hrms", "erpnext", "frappe"):
        hits = hits or glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"),
                                 recursive=True)
    _specs[name] = json.load(io.open(hits[0], encoding="utf-8")) if hits else None
    return _specs[name]


def fields(name):
    spec = doctype(name) or {}
    out = {f["fieldname"]: f for f in spec.get("fields", [])}
    out.update({f["fieldname"]: f for f in CUSTOM if f.get("dt") == name})
    return out


def link(name, fieldname, target):
    field = fields(name).get(fieldname) or {}
    return field.get("fieldtype") == "Link" and field.get("options") == target


def table(name, fieldname):
    field = fields(name).get(fieldname) or {}
    return field.get("options") if field.get("fieldtype") in ("Table", "Table MultiSelect") else None


R = load("next_steps_rules")
print("loaded next_steps_rules.py without Frappe")

# ── 1. Every step leads somewhere real ────────────────────────────────
if not os.path.isdir(APPS_ROOT):
    fail.append("the upstream apps are not at %s: set FRAPPE_APPS_ROOT" % APPS_ROOT)
for source, steps in R.STEPS.items():
    if not doctype(source):
        fail.append("%s: no such doctype" % source)
        continue
    if doctype(source).get("istable"):
        fail.append("%s is a table: its rows have no form to carry Next Steps" % source)
    seen = set()
    for step in steps:
        if len(step) not in (2, 3):
            fail.append("%s: a step is (doctype, relation[, label]): %r" % (source, step))
            continue
        target, relation = step[0], step[1]
        if (target, relation) in seen:
            fail.append("%s: the step to %s by %s twice" % (source, target, relation))
        seen.add((target, relation))
        if not doctype(target):
            fail.append("%s -> %s: no such doctype" % (source, target))
            continue
        try:
            kind, parts = R.parse(relation)
        except ValueError as error:
            fail.append("%s -> %s: %s" % (source, target, error))
            continue
        where = "%s -> %s (%s)" % (source, target, relation)
        if kind == "field" and not link(source, parts[0], target):
            fail.append("%s: %s.%s is not a link to %s" % (where, source, parts[0], target))
        elif kind == "rows":
            child = table(source, parts[0])
            if not child:
                fail.append("%s: %s has no table %s" % (where, source, parts[0]))
            elif not link(child, parts[1], target):
                fail.append("%s: %s.%s is not a link to %s" % (where, child, parts[1], target))
        elif kind == "back" and not link(target, parts[0], source):
            fail.append("%s: %s.%s is not a link to %s" % (where, target, parts[0], source))
        elif kind == "back_rows":
            child = table(target, parts[0])
            if not child:
                fail.append("%s: %s has no table %s" % (where, target, parts[0]))
            elif not link(child, parts[1], source):
                fail.append("%s: %s.%s is not a link to %s" % (where, child, parts[1], source))
        elif kind == "via":
            own, theirs = fields(source).get(parts[0]) or {}, fields(target).get(parts[1]) or {}
            if own.get("fieldtype") != "Link" or theirs.get("fieldtype") != "Link" \
                    or own.get("options") != theirs.get("options"):
                fail.append("%s: %s.%s and %s.%s are not links to the same doctype" % (
                    where, source, parts[0], target, parts[1]))
for relation, wanted in (("field:separation", ("field", ("separation",))),
                         ("rows:employees.position_change", ("rows", ("employees", "position_change"))),
                         ("via:onboarding=onboarding", ("via", ("onboarding", "onboarding")))):
    if R.parse(relation) != wanted:
        fail.append("parse(%r) should be %r" % (relation, wanted))
for bad in ("separation", "rows:employees", "via:onboarding", "next:x", "field:"):
    try:
        R.parse(bad)
        fail.append("parse(%r) should be refused" % bad)
    except ValueError:
        pass
if R.unique(["A", None, "B", "A", "", "C"]) != ["A", "B", "C"] or R.label_of(("Journal Entry", "field:x", "Write-off")) \
        != "Write-off" or R.label_of(("Journal Entry", "field:x")) != "Journal Entry":
    fail.append("unique keeps the first of each and drops blanks; a step's label is its own, else the doctype")
print("map: %d forms, %d steps, each one checked against the doctypes"
      % (len(R.STEPS), sum(len(steps) for steps in R.STEPS.values())))

# ── 2. The chains the processes depend on ─────────────────────────────
CHAINS = (
    ("Disciplinary Case", "Employee Separation"), ("Disciplinary Case", "Employee Suspension"),
    ("Disciplinary Case", "Employee Penalty"), ("Employee Separation", "Clearance Form"),
    ("Employee Separation", "Exit Interview"), ("Employee Separation", "Full and Final Statement"),
    ("Clearance Form", "Full and Final Statement"), ("Job Requisition", "Job Opening"),
    ("Job Opening", "Job Applicant"), ("Job Applicant", "Interview"), ("Job Applicant", "Job Offer"),
    ("Interview Report", "Job Offer"), ("Job Offer", "Employee Onboarding"),
    ("Employee Onboarding", "Probation Evaluation"), ("Employee Onboarding", "Employee Contract"),
    ("Probation Evaluation", "Employee Contract"), ("Appraisal", "Performance Review"),
    ("Performance Review", "Employee Position Change"), ("Performance Review", "Performance Improvement Plan"),
    ("Talent Review", "Talent Placement"), ("Talent Placement", "Talent Program"),
    ("Training Requisition", "Training Event"), ("Training Event", "Training Feedback"),
    ("Training Event", "Training Result"), ("Leave Application", "Leave Advance"),
    ("Salary Advance Request", "Employee Advance"), ("Employee Loan", "Journal Entry"),
    ("Safety Incident", "Employee Separation"), ("Off Duty Request", "Attendance"))
for source, target in CHAINS:
    if not any(step[0] == target for step in R.STEPS.get(source, ())):
        fail.append("%s has no Next Step to %s" % (source, target))
print("chains: from the decided case to the exit, the requisition to the contract, the appraisal to its outcome")

# ── 3. The server ─────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "next_steps.py")
for needle, why in (
        ("@frappe.whitelist()\ndef get_next_steps(doctype, name):", "the form asks the server"),
        ('doc.check_permission("read")', "only of a document the user may read"),
        ('if not frappe.has_permission(target, "read"):', "and only steps to documents they may read"),
        ('frappe.get_list(target, filters={"name": ["in", names], "docstatus": ["!=", 2]},',
         "each name through their own permissions, and none cancelled"),
        ("names[:rules.LIMIT]", "at most the limit at once"),
        ('"filters": filters or {"name": ["in", names[:rules.LIMIT]]}', "and the filter that lists them"),
        ("rules.parse(relation)", "each relation as the tested rule reads it"),
        ('frappe.get_meta(target).get_field(table).options', "a back row read from the doctype's own table")):
    if needle not in glue:
        fail.append("next_steps.py: %s (%r not found)" % (why, needle))

# ── 4. The form ───────────────────────────────────────────────────────
script = read("hrms_addon", "public", "js", "hrms_addon_next_steps.js")
for needle, why in (
        ('$(document).on("form-refresh", (event, frm) => hrms_addon.next_steps.show(frm));',
         "one handler serves every form"),
        ("frappe.boot.hrms_addon_next_steps", "only the forms with steps ask the server"),
        ("frm.is_new()", "never a form not saved yet"),
        ("frm.__ha_next_steps !== token", "a slower answer for an earlier refresh is dropped"),
        ('__("Next Steps")', "the buttons sit in one Next Steps group"),
        ('frappe.set_route("Form", step.doctype, step.names[0]);', "one document opens its form"),
        ("frappe.route_options = step.filters;", "several open their list, filtered")):
    if needle not in script:
        fail.append("hrms_addon_next_steps.js: %s (%r not found)" % (why, needle))
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "/assets/hrms_addon/js/hrms_addon_next_steps.js" not in (hooks.get("app_include_js") or []):
    fail.append("hooks.app_include_js loads hrms_addon_next_steps.js on every desk page")
theme = read("hrms_addon", "hrms_addon", "theme.py")
if "bootinfo.hrms_addon_next_steps = sorted(next_steps_rules.STEPS)" not in theme:
    fail.append("the session boot names the forms with Next Steps (theme.boot_session)")
print("form: one handler for every form, the Next Steps group, a form for one document and a list for several")

print()
if fail:
    print("FAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("ALL NEXT STEPS CHECKS PASSED")
