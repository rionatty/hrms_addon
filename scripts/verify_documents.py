"""Verify the documents an employee must hold, without a bench:

    python scripts/verify_documents.py

Alerts, Documents & Notifications, case 1: rule-based alerts for document
expiry — the national ID, driving permits, work permits. Contract and
probation expiry are already watched (verify_contracts.py,
verify_probation.py); this is the rest.

It also covers the user-defined fields of Organisation & System Setup case
10 — SACCO membership, union membership, PPE size and the plant cost
centre — because they live on the same tab as the flags the document rules
read.

  1  when a document runs out, and when somebody is told
  2  who has to hold what
  3  the paper: the type, the row, and the tab they sit on
  4  the glue reads and writes fields that exist
  5  wiring: seeded, validated, chased, and a way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import glob
import importlib.util
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
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
D = load("document_rules")
C = load("contract_rules")
hooks = hooks_dict()
print("loaded document_rules.py without Frappe")

# ── 1. Running out, and being told ────────────────────────────────────
if D.THRESHOLDS != (90, 30, 7, 0):
    fail.append("the ladder is three months, a month, a week, the day: %s" % (D.THRESHOLDS,))
# A contract is watched a year out because renewal is a decision; a permit
# is watched three months out because renewal is a queue. The ladders
# differ on purpose, but "running out" must mean the same number of days
# in both, or a report built from the two would contradict itself.
if max(D.THRESHOLDS) != C.EXPIRING_DAYS:
    fail.append("running out means %s days for a contract and %s for a document"
                % (C.EXPIRING_DAYS, max(D.THRESHOLDS)))
if D.DEFAULT_NOTICE_DAYS != C.EXPIRING_DAYS:
    fail.append("and the default notice must be the same: %s vs %s"
                % (D.DEFAULT_NOTICE_DAYS, C.EXPIRING_DAYS))

if D.status_of("2026-12-31", "2026-06-01", 90) != D.VALID:
    fail.append("six months out is valid")
if D.status_of("2026-08-01", "2026-06-01", 90) != D.EXPIRING:
    fail.append("two months out, on ninety days' notice, is running out")
if D.status_of("2026-05-01", "2026-06-01", 90) != D.EXPIRED:
    fail.append("a month past is expired")
if D.status_of(None, "2026-06-01", 90, number="CM123") != D.VALID:
    fail.append("a document that does not run out is valid while it is held")
if D.status_of(None, "2026-06-01", 90) != D.MISSING:
    fail.append("nothing held and nothing dated is missing")
if D.days_left("2026-06-08", "2026-06-01") != 7:
    fail.append("a week is seven days")

if D.threshold_crossed("2026-08-30", "2026-06-01") != 90:
    fail.append("ninety days out crosses the first threshold")
if D.threshold_crossed("2026-12-31", "2026-06-01") is not None:
    fail.append("and further out crosses none")
# a document first seen inside several thresholds raises one alert
if D.threshold_crossed("2026-06-05", "2026-06-01") != 7:
    fail.append("four days out crosses the nearest, which is a week: one alert, not three")
if D.threshold_crossed("2026-06-05", "2026-06-01", already=7) is not None:
    fail.append("and the same threshold does not go twice")
if D.threshold_crossed("2026-06-01", "2026-06-01", already=7) != 0:
    fail.append("but the day it goes is its own alert")
if D.threshold_crossed("2026-05-01", "2026-06-01") is not None:
    fail.append("an expired document is not chased again: it is a different problem")
if D.expired_today("2026-05-31", "2026-06-01") is not True:
    fail.append("a document that went yesterday went yesterday")

# a type with its own notice is chased from there down
due = D.chase([{"expires_on": "2026-07-01", "notice_days": 30, "alerted_at": None},
               {"expires_on": "2026-06-20", "notice_days": 60, "alerted_at": None},
               {"expires_on": "2027-01-01", "notice_days": 30, "alerted_at": None}],
              "2026-06-01")
if [row["expires_on"] for row in due] != ["2026-06-20", "2026-07-01"]:
    fail.append("the soonest to run out is chased first, and what is not due is left: %s" % due)
if due[0]["threshold"] != 30:
    fail.append("nineteen days out on sixty days' notice is at the thirty-day rung: %s" % due[0])
print("running out: the same ladder a contract is chased on, each rung crossed once")

# ── 2. Who holds what ─────────────────────────────────────────────────
if D.APPLIES_TO[0] != D.EVERYBODY:
    fail.append("a type applies to everybody unless it says otherwise")
if not D.required_for(None, {}):
    fail.append("a type with nothing said applies to everybody")
if not D.required_for(D.EVERYBODY, {}):
    fail.append("and so does one that says so")
if D.required_for(D.FOREIGN, {}):
    fail.append("a work permit is not asked of a Ugandan")
if not D.required_for(D.FOREIGN, {"is_foreign": 1}):
    fail.append("but it is of somebody who needs one")
if D.required_for(D.DRIVERS, {"is_foreign": 1}):
    fail.append("a driving permit is asked of drivers, not of foreigners")
if not D.required_for(D.MACHINE, {"operates_machinery": 1}):
    fail.append("a medical certificate is asked of machine operators")

absent = D.missing([("National ID (NIN)", D.EVERYBODY), ("Work Permit", D.FOREIGN)],
                   {"National ID (NIN)": "CM123"})
if absent != ["Work Permit"]:
    fail.append("what is required and not held is named: %s" % absent)

good = {"document_type": "Work Permit", "number": "WP/2026/114", "issued_on": "2026-01-01",
        "expires_on": "2027-01-01", "expires_required": 1}
expect("a complete document", D.document_errors(good))
expect("a document with no number", D.document_errors(dict(good, number=None)),
       "no number on it")
expect("one that runs out before it was issued",
       D.document_errors(dict(good, expires_on="2025-06-01")), "before it was issued")
expect("one that runs out with no date", D.document_errors(dict(good, expires_on=None)),
       "Say when")

expect("a proper type", D.type_errors({"document_name": "Work Permit", "applies_to": D.FOREIGN,
                                       "expires": 1, "notice_days": 90}))
expect("a type nobody is told about", D.type_errors(
    {"document_name": "Work Permit", "expires": 1, "notice_days": 0}), "needs a notice period")
expect("a type that applies to nobody real", D.type_errors(
    {"document_name": "Work Permit", "applies_to": "Everybody"}), "A type applies to")

seeded = {row[0] for row in D.SEEDED_TYPES}
for name in ("National ID (NIN)", "Work Permit", "Driving Permit"):
    if name not in seeded:
        fail.append("test case 1 names %s" % name)
print("who holds what: a permit asked of the people who need one, and of nobody else")

# ── 3. The paper ──────────────────────────────────────────────────────
kind = fields_of(doctype("Employee Document Type"))
for fieldname in ("document_name", "applies_to", "expires", "notice_days", "mandatory",
                  "enabled"):
    if fieldname not in kind:
        fail.append("the document type has no %s" % fieldname)
if set((kind.get("applies_to", {}).get("options") or "").split("\n")) != set(D.APPLIES_TO):
    fail.append("the type's list and the rules' must be the same: %s" % kind.get("applies_to"))

row = fields_of(doctype("Employee Document"))
for fieldname in ("document_type", "number", "issued_on", "expires_on", "status", "days_left",
                  "attachment", "alerted_at"):
    if fieldname not in row:
        fail.append("a document row has no %s" % fieldname)
for fieldname in ("status", "days_left", "alerted_at"):
    if not row.get(fieldname, {}).get("read_only"):
        fail.append("%s is worked out, not typed" % fieldname)
if not row.get("alerted_at", {}).get("no_copy"):
    fail.append("an amended employee must not inherit somebody else's alert history")

employee = custom_fields("Employee")
for fieldname in ("custom_documents", "custom_documents_status", "custom_is_foreign",
                  "custom_drives", "custom_operates_machinery"):
    if fieldname not in employee:
        fail.append("Employee has no %s" % fieldname)
if employee.get("custom_documents", {}).get("options") != "Employee Document":
    fail.append("the documents are a table of Employee Document")
# Organisation & System Setup, case 10
for fieldname in ("custom_sacco_member", "custom_union_member", "custom_ppe_size",
                  "custom_plant_cost_centre"):
    if fieldname not in employee:
        fail.append("Organisation case 10 asks for %s" % fieldname)
if employee.get("custom_plant_cost_centre", {}).get("options") != "Cost Center":
    fail.append("the plant cost centre is a real Cost Center")
if "attendance_device_id" in employee:
    fail.append("the biometric ID is Frappe HR's own field; do not add a second")
print("the paper: the type, the row, the flags, and the fields case 10 asks for")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "documents.py")
known = set(kind) | set(row) | set(employee) | {"doctype", "name", "docstatus", "employee",
                                                "company", "flags"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update"):
        continue
    if fieldname not in known:
        fail.append("documents.py reads or writes %s, which is on neither document" % fieldname)
for needle, why in (
    ("rules.status_of(", "where a document stands comes from the rules"),
    ("rules.chase(", "and so does what is due to be chased"),
    ("rules.document_errors(", "and what a row must carry"),
    ("rules.required_for(", "and who has to hold one"),
    ("rules.missing(", "and what is not held at all"),
    ("alerted_at", "a threshold crossed is remembered, so one alert goes, not four"),
    ("people.hr_officers(", "HR are told"),
    ("user_id", "and so is the employee themselves"),
):
    if needle not in glue:
        fail.append("documents.py: %s (%r not found)" % (why, needle))
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_document_type",
                  "employee_document_type.py")
if "    def validate(self):\n        documents.type_validate(self)" not in controller:
    fail.append("the document type controller must hand validate to documents.type_validate")
report_py = read("hrms_addon", "hrms_addon", "report", "document_expiry", "document_expiry.py")
if "frappe.get_list(" not in report_py:
    fail.append("the report reads through Frappe's permissions (get_list, not get_all)")
for needle in ("rules.status_of(", "rules.missing(", "rules.required_for("):
    if needle not in report_py:
        fail.append("the report and the form must agree: %r not found" % needle)
print("glue: the status worked out, the chasing remembered, the report agreeing")

# ── 5. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.documents.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("the document types must be seeded on every migrate")
if "hrms_addon.hrms_addon.documents.daily" not in \
        hooks.get("scheduler_events", {}).get("daily", []):
    fail.append("a document running out needs the daily job")
if hooks.get("doc_events", {}).get("Employee", {}).get("validate") \
        != "hrms_addon.hrms_addon.documents.employee_validate":
    fail.append("each document's status is worked out on the employee's own form")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Employee Document Type", "Document Expiry"):
    if name not in nav:
        fail.append("%s has no way in" % name)
if '"Document Expiry": "Employee"' not in nav:
    fail.append("the expiry report must say which document it is for")
report = json.load(open(os.path.join(APP, "report", "document_expiry", "document_expiry.json"),
                        encoding="utf-8"))
if report.get("ref_doctype") != "Employee" or report.get("is_standard") != "Yes":
    fail.append("the expiry report is a standard report on the employee")
print("wiring: seeded, validated on the form, chased daily, with a way in")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL DOCUMENT CHECKS PASSED")
