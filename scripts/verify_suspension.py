"""Employee suspension (Disciplinary Grievancy, test case 6, and Luuka's
Suspension Letter), checked without a bench.

suspension_rules.py and suspension_approval.py are loaded without Frappe
and their rules run; the doctype, the print, the glue and the places it
reaches (the disciplinary case, the leave form, leave accrual, the
attendance register, the appraisal round, the employee's connections, the
menus) are read as files.
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


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


def body_of(source, name):
    start = source.index("\ndef %s(" % name)
    rest = source[start + 1:]
    end = rest.index("\ndef ", 1) if "\ndef " in rest[1:] else len(rest)
    return rest[:end]


R, A = load("suspension_rules"), load("suspension_approval")
D = load("discipline_rules")
print("loaded suspension_rules.py, suspension_approval.py and discipline_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
day = datetime.date
for start, days in (("2026-10-07", 3), ("2026-12-30", 5), ("2026-10-07", 1), ("2026-10-07", 0), (None, 3)):
    if R.suspension_dates(start, days) != D.suspension_dates(start, days):
        fail.append("suspension_dates(%r, %r): the record counts the days as the disciplinary case does" % (start, days))
if R.suspension_dates("2026-10-07", 3) != {"from": day(2026, 10, 7), "to": day(2026, 10, 9),
                                          "report_back": day(2026, 10, 10)}:
    fail.append("three days from the 7th run to the 9th, back on the 10th: %s" % R.suspension_dates("2026-10-07", 3))
if R.days_between("2026-12-30", "2027-01-02") != [day(2026, 12, 30), day(2026, 12, 31), day(2027, 1, 1), day(2027, 1, 2)] \
        or R.days_between("2026-10-09", "2026-10-07") != []:
    fail.append("days_between: every day, both ends in, over the year's end; none when the end comes first")
for spans, wanted in ((("2026-10-07", "2026-10-09", "2026-10-09", "2026-10-11"), True),
                      (("2026-10-07", "2026-10-09", "2026-10-10", "2026-10-12"), False),
                      (("2026-10-07", "2026-10-09", "2026-10-01", "2026-10-31"), True),
                      (("2026-10-07", None, "2026-10-01", "2026-10-31"), False)):
    if R.overlaps(*spans) != wanted:
        fail.append("overlaps%r: want %r" % (spans, wanted))
GOOD = {"employee": "HR-EMP-00100", "nature_of_offence": "Late coming", "days": 3, "from_date": "2026-10-07",
        "date_of_joining": "2023-01-09", "employee_status": "Active"}
expect("a suspension as Luuka writes it", R.suspension_errors(GOOD))
expect("nothing filled in", R.suspension_errors({}), "Choose the employee", "nature of the offence",
       "how many days", "the day the suspension starts")
expect("too long", R.suspension_errors(dict(GOOD, days=R.MAX_DAYS + 1)), "at most %d days" % R.MAX_DAYS)
expect("before joining", R.suspension_errors(dict(GOOD, from_date="2023-01-01")), "before the employee joined")
expect("after leaving", R.suspension_errors(dict(GOOD, relieving_date="2026-10-01")), "leaves before")
expect("someone who has left", R.suspension_errors(dict(GOOD, employee_status="Left")), "has left")
expect("days already a suspension", R.suspension_errors(dict(GOOD, clashes=["LPL-SUS-2026-0001"])),
       "already a suspension: LPL-SUS-2026-0001")
if R.leave_type_for(1) != R.UNPAID_LEAVE or R.leave_type_for(0) != R.PAID_LEAVE:
    fail.append("leave_type_for: without pay is the unpaid type, with pay the paid one")
if R.LEAVE_TYPES[R.UNPAID_LEAVE].get("is_lwp") != 1 or R.LEAVE_TYPES[R.PAID_LEAVE].get("is_lwp") != 0:
    fail.append("the unpaid leave type is leave without pay (is_lwp), the paid one is not")
if not all(values.get("include_holiday") for values in R.LEAVE_TYPES.values()):
    fail.append("every day of the letter is a day of the suspension, a holiday among them (include_holiday)")
DAYS = R.days_between("2026-10-07", "2026-10-10")
plan = R.day_plan(DAYS, {
    day(2026, 10, 8): {"name": "ATT-1", "docstatus": 0, "status": "Absent"},
    day(2026, 10, 9): {"name": "ATT-2", "docstatus": 1, "status": "Absent"},
    day(2026, 10, 10): {"name": "ATT-3", "docstatus": 1, "status": "On Leave", "leave_type": R.UNPAID_LEAVE}})
if plan != {"create": [day(2026, 10, 7)], "update": ["ATT-1"], "kept": [(day(2026, 10, 9), "Absent")]}:
    fail.append("day_plan: a free day is marked, a draft taken over, a submitted day kept and said, one this "
                "marked left alone: %s" % plan)
for today, current, wanted in (("2026-10-06", R.APPROVED, R.APPROVED), ("2026-10-07", R.APPROVED, R.IN_PROGRESS),
                               ("2026-10-09", R.IN_PROGRESS, R.IN_PROGRESS), ("2026-10-10", R.IN_PROGRESS, R.COMPLETED),
                               ("2026-10-20", R.APPROVED, R.COMPLETED), ("2026-10-08", R.CANCELLED, R.CANCELLED)):
    if R.running_status(today, "2026-10-07", "2026-10-10", current) != wanted:
        fail.append("running_status on %s from %s: want %s" % (today, current, wanted))
for args, wanted in (((R.IN_PROGRESS, "Active"), "Suspended"), ((R.IN_PROGRESS, "Left"), None),
                     ((R.COMPLETED, "Suspended"), "Active"), ((R.COMPLETED, "Suspended", True), None),
                     ((R.CANCELLED, "Suspended"), "Active"), ((R.COMPLETED, "Left"), None),
                     ((R.APPROVED, "Active"), None)):
    if R.employee_status_after(*args) != wanted:
        fail.append("employee_status_after%r: want %r" % (args, wanted))
print("rules: the dates the letter prints, what a suspension needs, each day on the attendance, how far it has run")

# ── 2. The workflow ───────────────────────────────────────────────────
states = {row["state"] for row in A.STATES}
spec = doctype("Employee Suspension")
own = fields_of(spec)
status_options = (own.get("status") or {}).get("options", "").split("\n")
if states - set(status_options) or status_options != list(R.STATUSES):
    fail.append("the workflow writes each state into the Status, and the record its own (In Progress, Completed): "
                "every one must be an option: %s" % status_options)
for row in A.STATES:
    wanted = {A.APPROVED: "1", A.CANCELLED: "2"}.get(row["state"])
    if row.get("doc_status") != wanted:
        fail.append("%s: the suspension is %s there" % (row["state"], {"1": "filed", "2": "cancelled", None: "a draft"}[wanted]))
for state, roles, wanted in (
        (A.DRAFT, ["HR User"], [(A.SEND, A.PENDING_HRM)]),
        (A.DRAFT, ["General Manager"], []),
        (A.PENDING_HRM, ["HR Manager"], [(A.APPROVE, A.PENDING_GM), (A.RETURN, A.DRAFT)]),
        (A.PENDING_HRM, ["HR User", "General Manager"], []),
        (A.PENDING_GM, ["General Manager"], [(A.APPROVE, A.APPROVED), (A.RETURN, A.DRAFT)]),
        (A.PENDING_GM, ["HR Manager"], []),
        (A.APPROVED, ["HR Manager"], [(A.CANCEL, A.CANCELLED)]),
        (A.APPROVED, ["HR User", "General Manager"], [])):
    if A.next_states(state, roles) != wanted:
        fail.append("from %s, %s may %s, got %s" % (state, roles, wanted, A.next_states(state, roles)))
if A.ROLE_WAITING != {A.PENDING_HRM: "HR Manager", A.PENDING_GM: "General Manager"}:
    fail.append("the letter is witnessed by the HR Manager, then signed by the General Manager")
if "submit" not in A.PERMISSIONS.get(A.DOCTYPE, {}).get("General Manager", ()):
    fail.append("the General Manager's approval files the suspension: they need submit")
D_ = "2026-10-06"
sent = A.compute_stamps(A.DRAFT, A.PENDING_HRM, "hro@luuka", D_, {})
witnessed = A.compute_stamps(A.PENDING_HRM, A.PENDING_GM, "hrm@luuka", D_, sent)
signed = A.compute_stamps(A.PENDING_GM, A.APPROVED, "gm@luuka", D_, witnessed)
if (signed["prepared_by"], signed["hrm_by"], signed["gm_by"], signed["gm_on"]) != ("hro@luuka", "hrm@luuka", "gm@luuka", D_):
    fail.append("each step stamps who left it and when, keeping the ones before: %s" % signed)
if any(A.compute_stamps(A.PENDING_GM, A.DRAFT, "gm@luuka", D_, witnessed).values()):
    fail.append("a return clears every signature")
expect("returned without a reason", A.step_errors(A.PENDING_HRM, A.DRAFT, {}), "Return Remarks")
expect("returned with one", A.step_errors(A.PENDING_GM, A.DRAFT, {"return_remarks": "Wrong dates."}))
expect("sent with what it lacks", A.step_errors(A.DRAFT, A.PENDING_HRM, {"errors": ["Say how many days"]}),
       "Say how many days")
expect("approved as it is", A.step_errors(A.PENDING_GM, A.APPROVED, {"errors": []}))
for fieldname in A.ALL_STAMP_FIELDS + tuple(A.REMARK_FIELDS.values()) + ("return_remarks", A.STATE_FIELD):
    if fieldname not in own:
        fail.append("the workflow writes Employee Suspension.%s, which it does not have" % fieldname)
for fieldname in A.ALL_STAMP_FIELDS:
    if not (own.get(fieldname, {}).get("read_only") and own.get(fieldname, {}).get("no_copy")):
        fail.append("Employee Suspension.%s is a signature: read-only, never copied" % fieldname)
print("workflow: the HR Officer sends it, the HR Manager witnesses, the General Manager signs; a return says why")

# ── 3. The record ─────────────────────────────────────────────────────
if not (spec.get("is_submittable") and spec.get("autoname") == "naming_series:"):
    fail.append("Employee Suspension: submittable, named by its series")
if (own.get("naming_series") or {}).get("options") != "LPL-SUS-.YYYY.-":
    fail.append("the suspensions are numbered LPL-SUS-YYYY-, as the cases are LPL-DISC-")
for fieldname, fieldtype, source in (("employee_name", "Data", "employee.employee_name"),
                                     ("employee_number", "Data", "employee.employee_number"),
                                     ("department", "Link", "employee.department"),
                                     ("branch", "Link", "employee.branch"),
                                     ("company", "Link", "employee.company")):
    field = own.get(fieldname) or {}
    if field.get("fieldtype") != fieldtype or field.get("fetch_from") != source:
        fail.append("the letter's %s comes from the employee (%s)" % (fieldname, source))
for fieldname in ("to_date", "report_back_on", "days_marked", "status"):
    if not (own.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Suspension.%s is worked out, never typed" % fieldname)
if (own.get("days") or {}).get("default") != str(R.DEFAULT_DAYS) or (own.get("without_pay") or {}).get("default") != "1":
    fail.append("a suspension runs %d days without pay unless changed" % R.DEFAULT_DAYS)
for fieldname in ("acknowledged_on", "signed_letter"):
    if not (own.get(fieldname) or {}).get("allow_on_submit"):
        fail.append("%s is filled in after the letter is issued: allow it on submit" % fieldname)
if spec.get("default_print_format") != "Suspension Letter":
    fail.append("a suspension prints as the Suspension Letter")
gm = next((perm for perm in spec.get("permissions", []) if perm["role"] == "General Manager"), {})
if not (gm.get("submit") and gm.get("write")):
    fail.append("the General Manager signs the suspension: write and submit on a fresh site too")
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_suspension", "employee_suspension.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        suspensions.suspension_%s(self)" % (method, method) not in controller:
        fail.append("the controller hands %s to suspensions.suspension_%s" % (method, method))
form_js = read("hrms_addon", "hrms_addon", "doctype", "employee_suspension", "employee_suspension.js")
for needle, why in (("frappe.datetime.add_days(frm.doc.from_date, days - 1)", "the last day, both ends counted"),
                    ("report_back_on: frappe.datetime.add_days(last, 1)", "and back the day after"),
                    ("if (frm.doc.docstatus !== 0) return;", "never on an approved record")):
    if needle not in form_js:
        fail.append("employee_suspension.js: %s (%r not found)" % (why, needle))
print("the record: the employee's particulars fetched, the dates worked out, the letter's acknowledgement after")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "suspensions.py")
for needle, why in (
        ("rules.suspension_dates(doc.get(\"from_date\"), doc.get(\"days\"))", "the dates by the tested rule"),
        ("approval.step_errors(", "what a step needs, by the tested rule"),
        ('"errors": rules.suspension_errors(_facts(doc)) if new_state != approval.DRAFT else []',
         "the suspension is checked as it goes for signature, and again as it is approved"),
        ("approval.compute_stamps(", "the signatures, by the tested rule"),
        ("rules.overlaps(doc.from_date, doc.to_date, row.from_date, row.to_date)", "one employee, one suspension a day"),
        ('"employee": doc.employee, "docstatus": ["!=", 2],', "against the others not cancelled"),
        ('"name": ["!=", doc.name or ""]}', "never against itself"),
        ("rules.day_plan(days, existing)", "each day as the tested rule says"),
        ('"status": "On Leave", "leave_type": leave_type', "a day marked as leave of the suspension's type"),
        ("rules.leave_type_for(doc.get(\"without_pay\"))", "unpaid, unless it is with pay"),
        ("frappe.flags.mute_messages = True", "without a message for every day"),
        ("frappe.flags.mute_messages = muted", "and the messages back as they were"),
        ("attendance.cancel()", "a cancelled suspension takes its days off the attendance"),
        ('"leave_type": ["in", list(rules.LEAVE_TYPES)]', "only the days a suspension marked"),
        ("rules.employee_status_after(status, current, bool(others))", "the employee's status by the tested rule"),
        ('frappe.db.set_value("Employee", doc.employee, "status", new, update_modified=False)', "and set"),
        ("rules.running_status(day, row.from_date, row.report_back_on, row.status)", "the days as they come"),
        ('{"disciplinary_case": case.name, "docstatus": ["!=", 2]}', "a case raises one suspension"),
        ('case.db_set("employee_suspension", doc.name, update_modified=False)', "and names it"),
        ("people.assign(DOCTYPE, doc.name, users, message)", "the HR Officer is given it to send on"),
        ("people.assign(doc.doctype, doc.name, users, message)", "whoever signs next is given it to do"),
        ("people.withdraw(doc.doctype, doc.name", "and it is off the list of whoever had it"),
        ('people.withdraw(doc.doctype, doc.name, people.hr_officers(branch, doc.get("department")))',
         "sent on, it is off the HR Officer's list"),
        ('workflows.setup_on_migrate(approval, "Employee Suspension workflow")', "the workflow on every migrate")):
    if needle not in glue:
        fail.append("suspensions.py: %s (%r not found)" % (why, needle))
submitted = body_of(glue, "suspension_on_submit")
if "_mark_days(doc)" not in submitted or "_move_employee(doc, status)" not in submitted \
        or submitted.index("_mark_days(doc)") > submitted.index("_move_employee(doc, status)"):
    fail.append("approved, the days are marked, then the employee is suspended")
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
for key, entry, why in (("after_install", "hrms_addon.hrms_addon.suspensions.seed_leave_types",
                         "a fresh site gets the two leave types"),
                        ("after_migrate", "hrms_addon.hrms_addon.suspensions.setup_workflows_on_migrate",
                         "the workflow is built on every migrate")):
    if entry not in (hooks.get(key) or []):
        fail.append("hooks %s: %s" % (key, why))
if "hrms_addon.hrms_addon.suspensions.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the scheduler starts and ends the suspensions every day")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.employee_suspension" not in patches \
        or "suspensions.seed_leave_types()" not in read("hrms_addon", "patches", "v1_0", "employee_suspension.py"):
    fail.append("a site that has the app already gets the leave types by patch")
print("glue: the record checked and signed, its days on the attendance, the employee's status, the daily run")

# ── 5. Where it reaches ───────────────────────────────────────────────
discipline = read("hrms_addon", "hrms_addon", "discipline.py")
on_submit = body_of(discipline, "case_on_submit")
if 'doc.get("outcome") == rules.SANCTIONED and doc.get("rung") == rules.SUSPENSION' not in on_submit \
        or "suspensions.from_case(doc)" not in on_submit:
    fail.append("a case decided at the Suspension rung raises the Employee Suspension")
if '"employee_suspension": ["is", "not set"]' not in body_of(discipline, "_end_suspensions"):
    fail.append("the case's own reminder is only for a suspension with no record of its own")
case_fields = fields_of(doctype("Disciplinary Case"))
if (case_fields.get("employee_suspension") or {}).get("options") != "Employee Suspension" \
        or not case_fields["employee_suspension"].get("read_only"):
    fail.append("the case names the suspension it raised, read-only")
leave = read("hrms_addon", "hrms_addon", "leave.py")
validate = body_of(leave, "application_validate")
if 'doc.get("leave_type") in suspension_rules.LEAVE_TYPES' not in validate \
        or validate.index("suspension_rules.LEAVE_TYPES") > validate.index("leave_accrual.check_application(doc)"):
    fail.append("the leave form refuses the suspension's leave types, before anything else")
accrual = read("hrms_addon", "hrms_addon", "leave_accrual.py")
off_days = body_of(accrual, "_off_days")
if '"status": "On Leave",' not in off_days or '"leave_type": ["in", list(unpaid)]' not in off_days:
    fail.append("leave is not earned on unpaid leave marked on the attendance (a suspension's days)")
if '"status": ["in", ["Active", "Suspended"]]' not in body_of(accrual, "allocate"):
    fail.append("the year's leave policy reaches a suspended employee too")
appraisals = read("hrms_addon", "hrms_addon", "appraisals.py")
if 'STAFF = ["Active", "Suspended"]' not in appraisals or body_of(appraisals, "_employees_for").count(
        '"status": ["in", STAFF]') != 2:
    fail.append("a quarter's appraisals reach a suspended employee too")
AT = load("attendance_rules")
if AT.UNPAID_SUSPENSION != R.UNPAID_LEAVE:
    fail.append("the register knows the suspension's unpaid leave type by its own name")
if AT.register_code({"status": "On Leave", "leave_type": R.UNPAID_LEAVE}) != AT.register_code({"status": "Absent"}) \
        or AT.register_code({"status": "On Leave", "leave_type": R.PAID_LEAVE}) \
        != AT.register_code({"status": "On Leave", "leave_type": "Annual Leave"}):
    fail.append("LPL/HR/07 prints an unpaid suspension day as the absence it is paid as, a paid one as leave")
connections = read("hrms_addon", "hrms_addon", "connections.py")
if 'DISCIPLINE_DOCS = ["Disciplinary Case", "Employee Suspension"]' not in connections \
        or '{"label": _("Discipline"), "items": list(DISCIPLINE_DOCS)}' not in connections:
    fail.append("the employee's connections show their disciplinary cases and suspensions")
navigation = load("navigation_rules")
cards = [links for cards in navigation.CARDS.values() for card, links in cards if card == "Discipline and Safety"]
labels = [link[0] for link in (cards[0] if cards else [])]
if "Employee Suspension" not in labels or labels.index("Employee Suspension") != labels.index("Disciplinary Case") + 1:
    fail.append("Employee Suspension follows Disciplinary Case on its card")
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Employee Suspension" not in sidebarred:
    fail.append("Employee Suspension is in no sidebar")
grouped = [entries for groups in navigation.GROUPS.values() for name, _icon, entries in groups
           if name == "Employee Relations"]
if not grouped or grouped[0][grouped[0].index("Disciplinary Case") + 1:][:1] != ["Employee Suspension"]:
    fail.append("Employee Suspension follows Disciplinary Case in the Employee Relations group")
print("reach: the case raises it, the leave form refuses its types, no leave earned on its days, LPL/HR/07 prints "
      "them A, the round and the year's leave reach the suspended, the employee's connections, the menus")

# ── 6. The letter ─────────────────────────────────────────────────────
_spec = importlib.util.spec_from_file_location("jinja_subset", os.path.join(REPO, "scripts", "jinja_subset.py"))
jinja_subset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jinja_subset)
path = os.path.join(APP, "print_format", "suspension_letter", "suspension_letter.json")
letter = json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}
if (letter.get("doc_type"), letter.get("print_format_type"), letter.get("standard"), letter.get("module")) \
        != ("Employee Suspension", "Jinja", "Yes", "HRMS Addon"):
    fail.append("the Suspension Letter is a standard Jinja print of the Employee Suspension")
html = letter.get("html") or ""
for needle in ("RE: SUSPENSION FROM DUTY", "Please refer to your recent case of", "Management has decided to suspend you",
               "You will report back to the Human Resource Office on", "General Manager",
               "I acknowledge the above disciplinary procedure", "Witness, HRM"):
    if needle not in html:
        fail.append("the Suspension Letter does not say %r, which Luuka's does" % needle)
for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html)) - {"name"}):
    if fieldname not in own:
        fail.append("the Suspension Letter prints doc.%s, which the record does not have" % fieldname)
for expression in re.findall(r"\{\{-?(.*?)-?\}\}", html, flags=re.S):
    text = expression.strip()
    if text.startswith(("v(", "day(", "who(")) or "| e" in text:
        continue
    for fieldname in re.findall(r"\bdoc\.(\w+)", text):
        if (own.get(fieldname) or {}).get("fieldtype") not in ("Int", "Check", "Float"):
            fail.append("the Suspension Letter prints doc.%s unescaped: use v()" % fieldname)
try:
    render = jinja_subset.compile_template(html)
    employee = jinja_subset.wrap({"salutation": "Mr", "first_name": "John"})
    utils = type("utils", (), {"format_date": staticmethod(lambda value: str(value))})
    db = type("db", (), {"get_value": staticmethod(lambda doctype, name, field: "Full " + name),
                         "get_single_value": staticmethod(lambda doctype, field: None)})
    frappe = type("frappe", (), {"utils": utils, "db": db, "get_doc": staticmethod(lambda doctype, name: employee)})
    page = render({"doc": jinja_subset.wrap({
        "date": "2026-10-06", "employee": "E1", "employee_name": "John <Okello>", "employee_number": "LPL1834",
        "department": "Production", "branch": "Kawempe", "nature_of_offence": "Late coming", "days": 3,
        "without_pay": 1, "from_date": "2026-10-07", "to_date": "2026-10-09", "report_back_on": "2026-10-10",
        "company": "Luuka Plastics Limited", "gm_by": "gm@luuka", "hrm_by": None}), "frappe": frappe})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S)))
    for needle in ("Mr John &lt;Okello&gt;", "LPL1834", "Dear John,", "case of Late coming", "for 3 days without pay",
                   "from 2026-10-07 to 2026-10-09", "on 2026-10-10 to resume", "Ms. Luuka Plastics Limited",
                   "Full gm@luuka General Manager"):
        if needle not in text:
            fail.append("the Suspension Letter should read %r: %s" % (needle, text))
except Exception as error:  # noqa: BLE001
    fail.append("the Suspension Letter does not compile or render: %s" % error)
print("the letter: Luuka's own words, the employee's particulars, the days, the day back, the signatures")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL SUSPENSION CHECKS PASSED")
