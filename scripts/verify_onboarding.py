"""Checks for Employee Onboarding, Luuka's To-Be induction process (blueprint
1.2.4, steps 1 to 4, and the HR Manager's approval), run without a bench.

onboarding_rules.py and onboarding_approval.py import nothing from Frappe, so
they are loaded directly and exercised:

  * the workflow: Draft, Start Onboarding (it submits), Submit for Approval,
    the HR Manager's Approve or Return to HR, Cancel; docstatus never goes
    back, every state is reachable, only the HR Manager's queue emails;
  * each step's checks (a Head of Department, activities and a holiday list
    to start; the signed rules, the Employee and its signed Personal
    Bio-Data Form before the HR Manager; remarks to return) and the HR
    Manager's stamp (recorded on approval, cleared on return, a typed one
    reverts);
  * who gets a task: the onboarding's own HR Officer and Head of Department,
    else the role's holders in its branch (and department), else those who
    serve every branch, never every holder of the role;
  * which template: one made for the Job Title, then the Department, else by
    the department's Position Category;
  * the seeded templates and the Workplace Rules and Regulations (LPL/HR/05).

It also cross-checks the fixtures (every field the glue reads exists; what a
step writes on a submitted onboarding is allow_on_submit; the status field
offers exactly the states' statuses), upstream Frappe HR (the role-holder
assignment worked around, the reload across which the extra assignees are
kept, the Employee linked back by db_set, the update-after-submit path that
runs no validate), the glue, hooks, patches, form scripts and the print
format.

Needs ../ERPNext/{frappe,erpnext,hrms} (or FRAPPE_APPS_ROOT) for the
upstream cross-checks.

    python scripts/verify_onboarding.py
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
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
EO = "Employee Onboarding"
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def upstream_doctype(doctype):
    folder = doctype.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def upstream_source(app, *parts):
    path = os.path.join(APPS_ROOT, app, app, *parts)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


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


rules = load("onboarding_rules")
approval = load("onboarding_approval")
org = load("org_rules")
requisition = load("requisition_approval")
print("loaded onboarding_rules.py and onboarding_approval.py without Frappe")

custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
setters = json.loads(read("hrms_addon", "fixtures", "property_setter.json"))
eo_fields = {f["fieldname"]: f for f in custom if f["dt"] == EO}

# ── 1. Shape of the workflow ─────────────────────────────────────────
A = approval
state_names = list(dict.fromkeys(s["state"] for s in A.STATES))
if state_names != [A.DRAFT, A.ONBOARDING, A.PENDING_HRM, A.APPROVED, A.CANCELLED]:
    fail.append("states %s, expected Draft, Onboarding, Pending HR Manager Approval, Approved, Cancelled" % state_names)
if A.STATES[0]["state"] != A.DRAFT:
    fail.append("the first state row must be Draft: Frappe starts new documents in the first state")
DOCSTATUS = {A.DRAFT: "0", A.ONBOARDING: "1", A.PENDING_HRM: "1", A.APPROVED: "1", A.CANCELLED: "2"}
edit_rows = [(s["state"], s["allow_edit"]) for s in A.STATES]
if len(edit_rows) != len(set(edit_rows)):
    fail.append("a state lists the same edit role twice")
for name in state_names:
    rows = [s for s in A.STATES if s["state"] == name]
    if len({(s["status"], s["style"], s["send_email"], s.get("doc_status", "0")) for s in rows}) != 1:
        fail.append("the rows of state %s disagree on status, style, send_email or doc_status" % name)
    if rows[0].get("doc_status", "0") != DOCSTATUS.get(name):
        fail.append("%s must have doc_status %s, has %s" % (name, DOCSTATUS.get(name), rows[0].get("doc_status", "0")))
    if rows[0]["status"] != name:
        fail.append("%s must write its own name as the Onboarding Status, writes %r" % (name, rows[0]["status"]))
    # the HR Manager's queue is the only one that needs telling; the others'
    # next action is HR's own
    if bool(rows[0]["send_email"]) != (name == A.PENDING_HRM):
        fail.append("%s must %ssend email" % (name, "" if name == A.PENDING_HRM else "not "))
editors = {name: sorted(s["allow_edit"] for s in A.STATES if s["state"] == name) for name in state_names}
for name in (A.DRAFT, A.ONBOARDING, A.APPROVED):
    if editors.get(name) != sorted(A.PREPARERS):
        fail.append("%s must be editable by the preparers %s, is by %s" % (name, list(A.PREPARERS), editors.get(name)))
for name in (A.PENDING_HRM, A.CANCELLED):
    if editors.get(name) != [A.APPROVER]:
        fail.append("%s must be editable by the HR Manager only, is by %s" % (name, editors.get(name)))

EXPECTED = sorted(
    [(A.DRAFT, A.START, A.ONBOARDING, role) for role in A.PREPARERS]
    + [(A.ONBOARDING, A.SUBMIT, A.PENDING_HRM, role) for role in A.PREPARERS]
    + [(A.PENDING_HRM, A.APPROVE, A.APPROVED, A.APPROVER), (A.PENDING_HRM, A.RETURN, A.ONBOARDING, A.APPROVER),
       (A.ONBOARDING, A.CANCEL, A.CANCELLED, A.APPROVER), (A.APPROVED, A.CANCEL, A.CANCELLED, A.APPROVER)]
)
got = sorted((t["state"], t["action"], t["next_state"], t["allowed"]) for t in A.TRANSITIONS)
if got != EXPECTED:
    fail.append("transitions %s, expected %s" % (got, EXPECTED))
for t in A.TRANSITIONS:
    if t.get("condition"):
        fail.append("no onboarding transition depends on a condition: %s" % t)
    if t["action"] not in A.ACTIONS:
        fail.append("transition uses unknown action %r" % t["action"])
    before, after = int(DOCSTATUS.get(t["state"], "9")), int(DOCSTATUS.get(t["next_state"], "9"))
    if after < before or before == 2:
        fail.append("%s -> %s would take the docstatus back (%d -> %d)" % (t["state"], t["next_state"], before, after))
    if t["next_state"] == A.CANCELLED and t["allowed"] != A.APPROVER:
        fail.append("only the HR Manager cancels an onboarding (it deletes its project and tasks)")
reachable, frontier = {A.DRAFT}, [A.DRAFT]
while frontier:
    state = frontier.pop()
    for t in A.TRANSITIONS:
        if t["state"] == state and t["next_state"] not in reachable:
            reachable.add(t["next_state"])
            frontier.append(t["next_state"])
if set(state_names) - reachable:
    fail.append("unreachable states: %s" % sorted(set(state_names) - reachable))
if A.next_states(A.PENDING_HRM, ["HR User"]) or sorted(A.next_states(A.PENDING_HRM, ["HR Manager"])) != sorted(
        [(A.APPROVE, A.APPROVED), (A.RETURN, A.ONBOARDING)]):
    fail.append("only the HR Manager may act on Pending HR Manager Approval")
if A.NEW_ROLES:
    fail.append("the onboarding needs no new role: %s" % (A.NEW_ROLES,))
print("workflow shape: %d states, %d transitions, all reachable, docstatus only forward" % (len(state_names), len(A.TRANSITIONS)))

# ── 2. Each step's checks and the HR Manager's stamp ─────────────────
ALL = {"head_of_department": "hod@luuka", "activities": 4, "holiday_list": "Luuka 2026", "employee": "HR-EMP-00001",
       "rules_signed_on": "2026-10-01", "bio_data_signed_on": "2026-10-02", "hrm_remarks": "",
       "supervisor": "HR-EMP-00042", "supervisor_is_employee": False, "salary_structure": "Luuka Staff 2026",
       "base_salary": 850000, "salary_from": "2026-10-01", "date_of_joining": "2026-10-01", "tax_slab_needed": None,
       "tools_pending": [], "training_required": 0, "training_missing": ["Trainer"]}
step = A.step_errors
expect("start with everything", step(A.DRAFT, A.ONBOARDING, ALL))
expect("start without a Head of Department", step(A.DRAFT, A.ONBOARDING, dict(ALL, head_of_department=None)),
       "Name the Head of Department")
expect("start without activities", step(A.DRAFT, A.ONBOARDING, dict(ALL, activities=0)), "Choose an Employee Onboarding Template")
expect("start without a holiday list", step(A.DRAFT, A.ONBOARDING, dict(ALL, holiday_list=None)), "Choose the Holiday List")
expect("start with nothing", step(None, A.ONBOARDING, {}),
       "Name the Head of Department", "Choose an Employee Onboarding Template", "Choose the Holiday List")
expect("send with everything", step(A.ONBOARDING, A.PENDING_HRM, ALL))
expect("send before the rules are signed", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, rules_signed_on=None)),
       "Record the date the Workplace Rules and Regulations were signed")
expect("send before the Employee exists", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, employee=None, bio_data_signed_on=None)),
       "Create the Employee")
if "Job Applicant (Joining tab) is this candidate" not in " ".join(step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, employee=None))):
    fail.append("the missing-Employee message must say how an Employee made another way is found (its Job Applicant)")
expect("send before the bio-data is captured", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, bio_data_signed_on=None)),
       "Update the Employee from the signed Personal Bio-Data Form")
expect("send with nothing", step(A.ONBOARDING, A.PENDING_HRM, {}),
       "Choose the Supervisor", "Choose the Salary Structure", "Enter the Base salary",
       "Set the date the salary is Effective From", "Record the date the Workplace Rules", "Create the Employee")
# steps 5 to 7 and the training
expect("the new employee as the supervisor", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, supervisor_is_employee=True)),
       "The Supervisor cannot be the new employee.")
expect("no base salary", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, base_salary=0)), "Enter the Base salary")
expect("the salary before the joining date", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, salary_from="2026-09-30")),
       "The salary cannot start before the Date of Joining.")
expect("a structure deducting tax with no slab", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, tax_slab_needed="Luuka Staff 2026")),
       "Choose the Income Tax Slab (Salary section): the Salary Structure Luuka Staff 2026 deducts income tax.")
expect("tools not yet issued", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, tools_pending=["Computer", "PPE"])),
       "Issue the tools of work, or mark them Not Needed, before sending the onboarding to the HR Manager: Computer, PPE.")
expect("a required training not set up", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, training_required=1)),
       "Training is required: fill in the Trainer (Training section)")
expect("training details not needed when no training", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, training_required=0)))
expect("return without remarks", step(A.PENDING_HRM, A.ONBOARDING, dict(ALL, hrm_remarks="   ")), "Write in the HR Manager's Remarks")
expect("return with remarks", step(A.PENDING_HRM, A.ONBOARDING, dict(ALL, hrm_remarks="Salary grade is wrong")))
expect("approve", step(A.PENDING_HRM, A.APPROVED, {}))
expect("cancel", step(A.ONBOARDING, A.CANCELLED, {}))
expect("a save that is not a step", step(A.ONBOARDING, A.ONBOARDING, {}))
expect("a new draft", step(None, A.DRAFT, {}))

USER, TODAY = "hrm@luuka", "2026-10-03"
BY, ON = A.STAMP_FIELDS
STAMPED = {BY: "hrm@luuka", ON: "2026-10-03"}
stamp = A.compute_stamps
for label, got, want in (
    ("a new onboarding starts unstamped", stamp(None, A.DRAFT, USER, TODAY, {BY: "typed@x"}), {BY: None, ON: None}),
    ("approval records the HR Manager and the day", stamp(A.PENDING_HRM, A.APPROVED, USER, TODAY, {}), STAMPED),
    ("a return clears the stamp", stamp(A.PENDING_HRM, A.ONBOARDING, USER, TODAY, STAMPED), {BY: None, ON: None}),
    ("any other save keeps what was stamped", stamp(A.APPROVED, A.APPROVED, "other@x", "2027-01-01", STAMPED), STAMPED),
    ("a typed stamp reverts", stamp(A.ONBOARDING, A.PENDING_HRM, USER, TODAY, {BY: None, ON: None}), {BY: None, ON: None}),
):
    if got != want:
        fail.append("%s: %s, expected %s" % (label, got, want))
print("steps: start, send, return and approve checked; the stamp recorded, cleared and kept")

# ── 3. Who gets a task, and which template ───────────────────────────
R = rules
HOLDERS = [
    {"user": "hod.k.prod@x", "branches": {"Kawempe"}, "departments": {"Production"}},
    {"user": "hod.k.admin@x", "branches": {"Kawempe"}, "departments": {"Administration"}},
    {"user": "hod.kn@x", "branches": {"Kawempe", "Namanve"}, "departments": set()},
    {"user": "hod.m@x", "branches": {"Matugga"}, "departments": {"Production"}},
    {"user": "hod.everywhere@x", "branches": set(), "departments": set()},
]
assign = R.activity_assignees
for label, got, want in (
    ("the named person wins", assign(R.HOD_ROLE, {R.HOD_ROLE: "named@x"}, HOLDERS, "Kawempe", "Production"), ["named@x"]),
    ("another role's named person does not", assign(R.HOD_ROLE, {R.HR_OFFICER_ROLE: "hro@x"}, HOLDERS, "Matugga", "Production"),
     ["hod.m@x"]),
    ("the branch's holders for the department, and those of the branch with no department limit",
     assign(R.HOD_ROLE, {}, HOLDERS, "Kawempe", "Production"), ["hod.k.prod@x", "hod.kn@x"]),
    ("an HOD of two branches serves both", assign(R.HOD_ROLE, {}, HOLDERS, "Namanve", "Production"), ["hod.kn@x"]),
    ("no holder in the branch: those who serve every branch", assign(R.HOD_ROLE, {}, HOLDERS, "Kampala", "Production"),
     ["hod.everywhere@x"]),
    ("nobody at all", assign(R.HOD_ROLE, {}, [], "Kawempe", "Production"), []),
    ("a branch holder limited to other departments does not get it", assign(R.HOD_ROLE, {}, HOLDERS[1:2], "Kawempe", "Production"),
     []),
):
    if got != want:
        fail.append("activity_assignees, %s: %s, expected %s" % (label, got, want))

TEMPLATES = [
    {"name": "T-DEFAULT", "title": R.DEFAULT_TEMPLATE, "company": "Luuka Plastics Limited"},
    {"name": "T-PROD", "title": R.PRODUCTION_TEMPLATE, "company": "Luuka Plastics Limited"},
    {"name": "T-SALES", "title": "Sales Onboarding", "department": "Sales"},
    {"name": "T-OPERATOR", "title": "Operator Onboarding", "department": "Production", "designation": "Machine Operator"},
    {"name": "T-OTHER-CO", "title": "Other company", "company": "Other Co", "department": "Production"},
]
pick = R.pick_template
for label, got, want in (
    ("one made for the Job Title", pick(TEMPLATES, "Luuka Plastics Limited", "Production", "Machine Operator", "Non-Administrative"),
     "T-OPERATOR"),
    ("one made for the Department", pick(TEMPLATES, "Luuka Plastics Limited", "Sales", "Sales Executive", "Non-Administrative"),
     "T-SALES"),
    ("the production one for a non-administrative department",
     pick(TEMPLATES, "Luuka Plastics Limited", "Production", "Supervisor", "Non-Administrative"), "T-PROD"),
    ("the standard one for an administrative department",
     pick(TEMPLATES, "Luuka Plastics Limited", "Finance", "Accountant", "Administrative"), "T-DEFAULT"),
    ("the standard one when the category is unknown", pick(TEMPLATES, "Luuka Plastics Limited", None, None, None), "T-DEFAULT"),
    ("another company's template never", pick(TEMPLATES[4:], "Luuka Plastics Limited", "Production", None, None), None),
    ("a Job Title's template for another department never",
     pick(TEMPLATES[3:4], "Luuka Plastics Limited", "Sales", "Machine Operator", None), None),
    ("nothing to pick", pick([], "Luuka Plastics Limited", "Production", None, "Non-Administrative"), None),
):
    if got != want:
        fail.append("pick_template, %s: %r, expected %r" % (label, got, want))
if set(R.TEMPLATE_BY_CATEGORY) != set(org.POSITION_CATEGORIES) \
        or R.TEMPLATE_BY_CATEGORY.get(org.NON_ADMINISTRATIVE) != R.PRODUCTION_TEMPLATE:
    fail.append("TEMPLATE_BY_CATEGORY must cover exactly org_rules.POSITION_CATEGORIES, production for non-administrative")
print("assignment: named people, branch and department holders, then those serving every branch; templates picked")

# ── 3c. Tools of work and training (steps 6 and 7, "Training Required?") ──
if R.default_tools([("PPE", 1), ("Email account", 1)], [("Computer", 1), ("PPE", 2)]) != [
        {"tool": "PPE", "qty": 2}, {"tool": "Email account", "qty": 1}, {"tool": "Computer", "qty": 1}]:
    fail.append("default_tools: every new employee's tools, then the Job Title's, each once with the larger quantity")
TOOLS = [
    {"tool": "Computer", "provider": "IT", "qty": 1, "status": "", "before_day_one": 1},
    {"tool": "Email account", "provider": "IT", "qty": 1, "status": None, "before_day_one": 0},
    {"tool": "PPE", "provider": "EHS", "qty": 2, "status": "", "before_day_one": 1},
    {"tool": "Log book", "provider": "Department", "qty": 1, "status": "", "before_day_one": 0},
    {"tool": "Airtime", "provider": "HR", "qty": 1, "status": "Requested", "before_day_one": 0},
]
requests = R.tool_requests(TOOLS, {"Department": R.HOD_ROLE, "IT": None})
if [(a["activity_name"], a["role"]) for a in requests] != [
        ("Tools of work from IT", R.HR_OFFICER_ROLE), ("Tools of work from EHS", R.HR_OFFICER_ROLE),
        ("Tools of work from Department", R.HOD_ROLE)]:
    fail.append("tool_requests: one activity per provider not yet asked, to its role (the HR Officer if none): %s"
                % [(a["activity_name"], a["role"]) for a in requests])
it = requests[0]["description"] if requests else ""
if "1 x Computer; 1 x Email account" not in it or "Needed before day 1: Computer." not in it:
    fail.append("tool_requests must list each tool with its quantity and what is needed before day 1: %r" % it)
if any(a["required_for_employee_creation"] or a["begin_on"] or len(a["activity_name"]) > 70 for a in requests):
    fail.append("tool requests begin on day 0, never hold up Create Employee, and fit the task subject")
if R.pending_tools([{"tool": "A", "status": "Issued"}, {"tool": "B", "status": "Not Needed"}, {"tool": "C", "status": "Requested"},
                    {"tool": "D", "status": ""}]) != ["C", "D"]:
    fail.append("pending_tools: everything not Issued or Not Needed")
if R.training_missing({"custom_training_program": "GMP", "custom_trainer_name": "Peter", "custom_training_start": "2026-10-05",
                       "custom_training_days": 2, "custom_training_location": "Kawempe"}) != []:
    fail.append("training_missing: a training with its trainer, start, duration, place and program lacks nothing")
if R.training_missing({"custom_training_scope": "  "}) != ["Trainer", "Training Starts On", "Duration (Days)", "Location",
                                                           "Training Program or Training Scope"]:
    fail.append("training_missing must name every missing detail: %s" % R.training_missing({"custom_training_scope": "  "}))
start, end = R.training_window("2026-10-05", 3)
if (str(start), str(end)) != ("2026-10-05 08:00:00", "2026-10-07 17:00:00"):
    fail.append("training_window: from 08:00 on the first day to 17:00 on the last: %s to %s" % (start, end))
evaluation = R.training_evaluation_activity("2026-10-01", "2026-10-05", 3)
if (evaluation["begin_on"], evaluation["required_for_employee_creation"]) != (7, 0):
    fail.append("the supervisor's evaluation begins as the training ends (day 7 here): %s" % evaluation)
if set(R.PROVIDERS) != {"EHS", "IT", "HR", "Department", "Stores", "Procurement"} or R.PROVIDER_ROLES != {"Department": R.HOD_ROLE}:
    fail.append("the seeded providers are the Tools of Work sheet's; the department's own tools go to its Head of Department")
tool_json = json.load(open(os.path.join(APP, "doctype", "onboarding_tool", "onboarding_tool.json"), encoding="utf-8"))
statuses = next((f.get("options") or "") for f in tool_json["fields"] if f["fieldname"] == "status").split("\n")
if [o for o in statuses if o] != list(R.TOOL_STATUSES):
    fail.append("Onboarding Tool status options must be exactly onboarding_rules.TOOL_STATUSES: %s" % statuses)
for f in tool_json["fields"]:
    if f["fieldname"] in ("status", "serial_no", "issued_on", "remarks", "qty") and not f.get("allow_on_submit"):
        fail.append("Onboarding Tool.%s is filled after the onboarding starts: it must be allow_on_submit" % f["fieldname"])
print("tools of work and training: defaults, one request per provider, what is pending, the training window")

# ── 3b. What still stops the Employee ────────────────────────────────
ACTIVITIES = [
    {"activity_name": "Orientation <b>tour</b>", "required_for_employee_creation": 1, "task": "TASK-2026-00001",
     "task_status": "Open", "assignees": ["Jane O'Hara"]},
    {"activity_name": "Workplace Rules signed", "required_for_employee_creation": 1, "task": "TASK-2026-00002",
     "task_status": "Completed", "assignees": ["Jane O'Hara"]},
    {"activity_name": "Handover to the HOD", "required_for_employee_creation": 1, "task": "TASK-2026-00003",
     "task_status": "Cancelled", "assignees": []},
    {"activity_name": "Bio-data captured", "required_for_employee_creation": 0, "task": "TASK-2026-00004",
     "task_status": "Open", "assignees": []},
    {"activity_name": "Plant visits", "required_for_employee_creation": 1, "task": None, "task_status": None},
]
pending = R.pending_required(ACTIVITIES)
if [a["activity_name"] for a in pending] != ["Orientation <b>tour</b>", "Plant visits"]:
    fail.append("pending_required must list the required activities whose task is not Completed or Cancelled, in order: %s"
                % [a["activity_name"] for a in pending])
message = R.pending_message("HR-EMP-ONB-2026-00001", pending)
for needle, why in (
    ('<a href="/app/employee-onboarding/HR-EMP-ONB-2026-00001">HR-EMP-ONB-2026-00001</a>', "names the onboarding, linked"),
    ('<a href="/app/task/TASK-2026-00001">Orientation &lt;b&gt;tour&lt;/b&gt;</a>: Open, with Jane O&#x27;Hara',
     "each task linked, its status and who has it, escaped"),
    ("<li>Plant visits: no task made, with nobody assigned</li>", "an activity with no task still listed"),
    ("sets its Status to Completed", "says what to do"),
):
    if needle not in message:
        fail.append("pending_message %s: %r not in %r" % (why, needle, message))
for done in ("Workplace Rules signed", "Handover to the HOD", "Bio-data captured", "<b>tour"):
    if done in message:
        fail.append("pending_message must list only what is still open, escaped: %r is in it" % done)
print("what still stops the Employee: the open required tasks, linked, with status and people, escaped")

# ── 4. The seeded templates and the Workplace Rules ──────────────────
if set(R.TEMPLATES) != {R.DEFAULT_TEMPLATE, R.PRODUCTION_TEMPLATE}:
    fail.append("the seeded templates must be the standard and the production one: %s" % sorted(R.TEMPLATES))
standard, production = R.TEMPLATES.get(R.DEFAULT_TEMPLATE, ()), R.TEMPLATES.get(R.PRODUCTION_TEMPLATE, ())
if list(production[:len(standard)]) != list(standard) or len(production) <= len(standard):
    fail.append("the production template is the standard one plus the production activities")
if [a[0] for a in production if a not in standard] != [R.PROCESS_WALKTHROUGH[0], R.PLANT_VISITS[0]]:
    fail.append("production roles add the process walk-through and the plant visits")
if any(branch not in R.PLANT_VISITS[0] for branch in org.BRANCHES):
    fail.append("the plant visits name every branch: %s" % (org.BRANCHES,))
required = [a[0] for a in standard if a[4]]
if required != [R.ORIENTATION[0], R.WORKPLACE_RULES[0], R.HANDOVER[0]]:
    fail.append("orientation, the signed rules and the handover come before Create Employee, nothing else: %s" % required)
if R.BIO_DATA[4]:
    fail.append("the Personal Bio-Data Form is printed from the Employee, so it cannot be required before it exists")
for title, activities in R.TEMPLATES.items():
    names = [a[0] for a in activities]
    if len(names) != len(set(names)):
        fail.append("%s lists an activity twice" % title)
    for index, activity in enumerate(activities):
        row = R.template_activities(title)[index]
        if set(row) != set(R.ACTIVITY_FIELDS) or len(activity) != len(R.ACTIVITY_FIELDS):
            fail.append("%s: activity %r does not give every field %s" % (title, activity[0], R.ACTIVITY_FIELDS))
        if activity[1] not in (R.HR_OFFICER_ROLE, R.HOD_ROLE):
            fail.append("%s: %r goes to %r, neither the HR Officer nor the Head of Department" % (title, activity[0], activity[1]))
        if not (isinstance(activity[2], int) and isinstance(activity[3], int) and activity[2] >= 0 and activity[3] >= 0):
            fail.append("%s: %r must begin on a day and last a whole number of days" % (title, activity[0]))
        # Frappe HR makes "<activity> : <employee name>" the Task's subject, a 140-character Data field
        if len(activity[0]) > 70:
            fail.append("%s: activity name %r is %d characters; with the employee's name it overflows the task subject"
                        % (title, activity[0], len(activity[0])))
if R.HOD_ROLE not in requisition.NEW_ROLES or R.HR_OFFICER_ROLE != "HR User":
    fail.append("the Head of Department role is the requisition workflow's, the HR Officer is HR User")

html = R.WORKPLACE_RULES_HTML
SECTIONS = ("Production Quality Products", "Health and Safety", "House Keeping Practices", "Punishable Offences",
            "Disciplinary Procedures", "Reporting Procedures")
for heading in SECTIONS:
    if "<h4>%s" % heading not in html:
        fail.append("the Workplace Rules must keep the section %r of LPL/HR/05" % heading)
first = html.split("<h4>")[0]
if first.count("<li>") != 13 or "6:45am" not in first:
    fail.append("the first list holds the 13 workplace rules, starting with the 6:45am arrival time")
for tag in ("ol", "ul", "li", "h4"):
    if html.count("<%s>" % tag) != html.count("</%s>" % tag):
        fail.append("the Workplace Rules HTML has unbalanced <%s>" % tag)
if re.search(r"{{|{%|<script|on\w+=", html):
    fail.append("the Workplace Rules are printed as they are: no Jinja, script or handlers in them")
if R.WORKPLACE_RULES_TITLE != "Workplace Rules and Regulations":
    fail.append("the rules' Terms and Conditions title is what the print format looks up")
print("seeds: two templates (%d and %d activities), the Workplace Rules' %d sections"
      % (len(standard), len(production), len(SECTIONS)))

# ── 5. Fixtures ──────────────────────────────────────────────────────
def field(name):
    return eo_fields.get(name) or {}


status = field(A.STATUS_FIELD)
statuses = [o for o in (status.get("options") or "").split("\n") if o]
if statuses != list(dict.fromkeys(s["status"] for s in A.STATES)):
    fail.append("%s must offer exactly the states' statuses in order: %s" % (A.STATUS_FIELD, statuses))
if (status.get("fieldtype"), status.get("default"), status.get("read_only"), status.get("allow_on_submit"),
        status.get("no_copy")) != ("Select", A.DRAFT, 1, 1, 1):
    fail.append("%s must be a read-only Select defaulting to Draft, set after submit, never copied to an amendment"
                % A.STATUS_FIELD)
for name in A.STAMP_FIELDS:
    f = field(name)
    if not (f.get("read_only") and f.get("allow_on_submit") and f.get("no_copy")):
        fail.append("stamp %s must be read-only, allow_on_submit and no_copy" % name)
if (field(A.STAMP_FIELDS[0]).get("fieldtype"), field(A.STAMP_FIELDS[0]).get("options")) != ("Link", "User") \
        or field(A.STAMP_FIELDS[1]).get("fieldtype") != "Date":
    fail.append("the stamp is the HR Manager (Link User) and the day (Date)")
# what a step needs, written on a submitted onboarding
for name in ("custom_rules_signed_on", "custom_signed_workplace_rules", "custom_hrm_remarks"):
    if not field(name).get("allow_on_submit"):
        fail.append("%s is filled after the onboarding starts (submitted): it must be allow_on_submit" % name)
for name in ("custom_hr_officer", "custom_head_of_department"):
    if (field(name).get("fieldtype"), field(name).get("options")) != ("Link", "User"):
        fail.append("%s must be a Link to User: the tasks go to them" % name)
branch = field("custom_branch")
if (branch.get("fieldtype"), branch.get("options"), branch.get("reqd"), branch.get("fetch_from"), branch.get("fetch_if_empty")) \
        != ("Link", "Branch", 1, "job_offer.custom_branch", 1):
    fail.append("Employee Onboarding.custom_branch must be a mandatory Branch, from the Job Offer unless typed")
offer_branch = next((f for f in custom if f["dt"] == "Job Offer" and f["fieldname"] == "custom_branch"), {})
applicant_branch = next((f for f in custom if f["dt"] == "Job Applicant" and f["fieldname"] == "custom_branch"), {})
if (offer_branch.get("options"), offer_branch.get("fetch_from")) != ("Branch", "job_applicant.custom_branch"):
    fail.append("Job Offer.custom_branch must be the candidate's Branch")
if (applicant_branch.get("options"), applicant_branch.get("fetch_from")) != ("Branch", "job_title.location"):
    fail.append("Job Applicant.custom_branch must be the Job Opening's Branch (its location)")
if (field("custom_hrm_approval_section").get("depends_on") or "") != "eval:doc.docstatus==1":
    fail.append("the HR Manager's section shows once the onboarding has started")
print_setter = next((s for s in setters if s["doc_type"] == EO and s["property"] == "default_print_format"), {})
if print_setter.get("value") != "Workplace Rules and Regulations":
    fail.append("an onboarding prints the Workplace Rules and Regulations by default")
# steps 5 to 7 and the training, filled after the start
for name, (fieldtype, options) in {
    "custom_supervisor": ("Link", "Employee"), "custom_tools": ("Table", "Onboarding Tool"),
    "custom_salary_structure": ("Link", "Salary Structure"), "custom_salary_from": ("Date", None),
    "custom_income_tax_slab": ("Link", "Income Tax Slab"), "custom_base_salary": ("Currency", None),
    "custom_variable_pay": ("Currency", None), "custom_salary_structure_assignment": ("Link", "Salary Structure Assignment"),
    "custom_training_required": ("Check", None), "custom_training_program": ("Link", "Training Program"),
    "custom_training_scope": ("Small Text", None), "custom_trainer_name": ("Data", None), "custom_training_start": ("Date", None),
    "custom_training_days": ("Int", None), "custom_training_location": ("Data", None),
    "custom_training_event": ("Link", "Training Event"),
}.items():
    f = field(name)
    if (f.get("fieldtype"), f.get("options") or None) != (fieldtype, options):
        fail.append("Employee Onboarding.%s must be %s %s" % (name, fieldtype, options or ""))
    if not f.get("allow_on_submit"):
        fail.append("Employee Onboarding.%s is filled or set after the onboarding starts: it must be allow_on_submit" % name)
for name in ("custom_salary_structure_assignment", "custom_training_event"):
    if not (field(name).get("read_only") and field(name).get("no_copy")):
        fail.append("Employee Onboarding.%s is set by the approval: read-only and never copied" % name)
for field_name, label in R.TRAINING_DETAILS:
    if field(field_name).get("depends_on") != "custom_training_required":
        fail.append("Employee Onboarding.%s shows only when training is required" % field_name)
print("fixtures: status, stamps, branch chain and the step fields are what the workflow needs")

# ── 6. Upstream: what the glue relies on ─────────────────────────────
glue = read("hrms_addon", "hrms_addon", "onboarding.py")
eo = upstream_doctype(EO)
if eo:
    eo_all = {f["fieldname"]: f for f in eo["fields"]} | eo_fields
    for name in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"\bdoc\.(\w+)\b", glue))):
        if name in ("get", "set", "name", "docstatus", "get_doc_before_save", "activities", "idx", "flags", "throw", "db_set",
                    "append", "as_dict"):
            continue
        if name not in eo_all:
            fail.append("onboarding.py reads Employee Onboarding.%s, which does not exist" % name)
    activity = upstream_doctype("Employee Boarding Activity")
    columns = {f["fieldname"]: f for f in activity["fields"]}
    for name in set(R.ACTIVITY_FIELDS) | {"user", "task"}:
        if name not in columns:
            fail.append("Employee Boarding Activity has no %s upstream" % name)
    if (columns.get("activity_name") or {}).get("fieldtype") != "Data":
        fail.append("activity_name is no longer Data upstream: recheck the 70-character limit")
    perms = {p["role"]: p for p in eo["permissions"]}
    if (perms.get("HR User") or {}).get("submit"):
        fail.append("HR User can submit Employee Onboarding upstream now: the grant in PERMISSIONS is no longer needed")
    if set(A.PERMISSIONS.get(EO, {}).get("HR User", ())) != {"read", "write", "create", "submit"}:
        fail.append("HR User must be granted read, write, create and submit: starting an onboarding submits it")
    styles = next(f["options"].split("\n") for f in upstream_doctype("Workflow State")["fields"] if f["fieldname"] == "style")
    for s in A.STATES:
        if s["style"] not in styles:
            fail.append("state %s style %r not in %s" % (s["state"], s["style"], styles))
    known_roles = set()
    for app in ("frappe", "erpnext", "hrms"):
        for p in glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", "*", "*.json"), recursive=True):
            try:
                known_roles.update(perm.get("role") for perm in json.load(open(p, encoding="utf-8")).get("permissions") or [])
            except Exception:
                pass
    for role in sorted(({s["allow_edit"] for s in A.STATES} | {t["allowed"] for t in A.TRANSITIONS}) - known_roles):
        fail.append("role %r does not exist upstream" % role)

    controller = upstream_source("hrms", "controllers", "employee_boarding_controller.py") or ""
    for needle, why in (
        ("users = [activity.user] if activity.user else []", "Frappe HR assigns the activity's user"),
        ("if activity.role:", "and every holder of its role: why the role is cleared"),
        ("self.reload()\n\t\tself.create_task_and_notify_user()", "on_submit reloads before making the tasks: why the "
                                                                    "extra assignees wait in frappe.flags"),
        ('activity.db_set("task", task.name)', "the task is linked to its row, which after_tasks reads"),
        ("assign_to.add(args)", "the assignee is shared the task read-only: why after_tasks shares write"),
    ):
        if needle not in controller:
            fail.append("Frappe HR's boarding controller changed (%s): %r not found" % (why, needle))
    onboarding_py = upstream_source("hrms", "hr", "doctype", "employee_onboarding", "employee_onboarding.py") or ""
    if "def on_update_after_submit(self):\n\t\tself.create_task_and_notify_user()" not in onboarding_py:
        fail.append("Frappe HR no longer makes the tasks of activities added after the start in on_update_after_submit")
    master = upstream_source("hrms", "overrides", "employee_master.py") or ""
    if 'onboarding.db_set("employee", doc.name)' not in master:
        fail.append("Frappe HR no longer links the new Employee back to its onboarding: the step check reads it")
    # the check our controller replaces: same test, same error, the same two callers
    if "def validate_employee_creation(self):" not in onboarding_py \
            or 'if task_status not in ["Completed", "Cancelled"]:' not in onboarding_py \
            or list(R.DONE_TASK_STATUSES) != ["Completed", "Cancelled"]:
        fail.append("Frappe HR's employee creation check changed: re-read validate_employee_creation before relying on "
                    "DONE_TASK_STATUSES")
    if "class IncompleteTaskError(frappe.ValidationError):" not in onboarding_py:
        fail.append("Frappe HR no longer has IncompleteTaskError, which the listing keeps raising")
    if "doc = frappe.get_doc(\"Employee Onboarding\", source_name)\n\tdoc.validate_employee_creation()" not in onboarding_py:
        fail.append("Create > Employee no longer checks the onboarding through its controller")
    if "onboarding = frappe.get_doc(\"Employee Onboarding\", employee_onboarding[0].name)\n\t\tonboarding.validate_employee_creation()" \
            not in master:
        fail.append("saving an Employee no longer checks its onboarding through the controller")
    # Frappe HR links the Employee only while the tasks are not all done: why link_onboarding exists
    if '"boarding_status": ("!=", "Completed"),' not in master:
        fail.append("Frappe HR changed which onboardings it links a new Employee to: re-check link_onboarding")
    base_document = upstream_source("frappe", "model", "base_document.py") or ""
    if "db_values = frappe.get_doc(self.doctype, self.name).as_dict()" not in base_document:
        fail.append("Frappe's check for changes after submit no longer reads a fresh copy: _link_employee's db_set "
                    "would be refused")
    document = upstream_source("frappe", "model", "document.py") or ""
    if 'elif self._action == "update_after_submit":\n\t\t\tself.run_method("before_update_after_submit")' not in document:
        fail.append("Frappe's update after submit changed: the steps after the start rely on before_update_after_submit")
    assign_to = upstream_source("frappe", "desk", "form", "assign_to.py") or ""
    if "def _add(args=None, *, ignore_permissions=False):" not in assign_to:
        fail.append("frappe.desk.form.assign_to._add(args, ignore_permissions=...) is gone")
    share = upstream_source("frappe", "share.py") or ""
    if not re.search(r"def add_docshare\(\s*doctype, name, user=None, read=1, write=0", share) or "ignore_share_permission" not in share:
        fail.append("frappe.share.add_docshare(doctype, name, user, write=..., flags=...) changed")
    hrms_setup = upstream_source("hrms", "setup.py") or ""
    if '"fieldname": "hr"' not in hrms_setup:
        fail.append("Frappe HR no longer adds the HR flag to Terms and Conditions: the rules are seeded with hr=1")
    # the Training Event the approval books, and the salary structure it submits
    event = upstream_doctype("Training Event")
    event_fields = {f["fieldname"]: f for f in (event or {}).get("fields", [])}
    if event:
        written = set(re.findall(r'^\s+"(\w+)": ', re.search(r'"doctype": "Training Event",(.*?)\n    \}\)', glue, re.S).group(1), re.M))
        for name in sorted(written - {"doctype"}):
            if name not in event_fields:
                fail.append("the training booked sets Training Event.%s, which does not exist upstream" % name)
        for name, f in event_fields.items():
            if f.get("reqd") and name not in written:
                fail.append("Training Event.%s is mandatory upstream and the training booked leaves it out" % name)
        kinds = set((event_fields.get("type") or {}).get("options", "").split("\n"))
        ours = {o for o in (field("custom_training_type").get("options") or "").split("\n") if o}
        if not ours or not ours <= kinds:
            fail.append("the Training Type offered must be Training Event's own kinds: %s" % sorted(ours - kinds))
        if "Scheduled" not in (event_fields.get("event_status") or {}).get("options", ""):
            fail.append("Training Event no longer has the Scheduled status the booking sets")
    assignment = upstream_doctype("Salary Structure Assignment")
    if assignment:
        columns = {f["fieldname"] for f in assignment["fields"]}
        written = set(re.findall(r'^\s+"(\w+)": ', re.search(r"assignment\.update\(\{(.*?)\n    \}\)", glue, re.S).group(1), re.M))
        for name in sorted(written - columns):
            fail.append("the salary drafted sets Salary Structure Assignment.%s, which does not exist upstream" % name)
        ssa_py = upstream_source("hrms", "payroll", "doctype", "salary_structure_assignment", "salary_structure_assignment.py") or ""
        if '{"employee": self.employee, "from_date": self.from_date, "docstatus": 1},' not in ssa_py:
            fail.append("Frappe HR's one-assignment-per-date rule changed: re-check taking up the one HR already made")
        if "def get_tax_component(salary_structure: str)" not in ssa_py:
            fail.append("hrms get_tax_component is gone: the Income Tax Slab check reads it")
    print("upstream: the role-holder assignment, reload, task link, Employee back-link, update path, training and salary")
else:
    eo_all = eo_fields
    print("upstream cross-checks SKIPPED (no %s)" % APPS_ROOT)

# ── 7. The glue ──────────────────────────────────────────────────────
for needle, why in (
    ("activity.user, activity.role = users[0], None", "each activity keeps its first person and loses its role"),
    ("frappe.flags.setdefault(_ASSIGNEES, {})[doc.name] = resolved", "the people resolved wait for the tasks"),
    ("(frappe.flags.get(_ASSIGNEES) or {}).pop(doc.name, {})", "and are taken once"),
    ("for user in users[1:]:\n            _add(", "the others are assigned the task too"),
    ("ignore_permissions=True,\n            )", "without the HR Officer needing share rights"),
    ('add_docshare("Task", activity.task, user, write=1, flags={"ignore_share_permission": True})',
     "everyone the task went to may complete it"),
    ('if not frappe.has_permission("Task", "write", activity.task, user=user):', "shared only where they could not"),
    ('if activity.get("task") or not (activity.role or activity.user):', "only activities not yet tasks are handed out"),
    ("approval.step_errors(old_state, new_state, _facts(doc))", "the step's checks"),
    ("approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current)", "the HR Manager's stamp"),
    ('frappe.db.get_value("Employee", employee, "custom_bio_data_signed_on")', "the Employee's signed bio-data"),
    ('frappe.has_permission("Employee Onboarding", "create", throw=True)', "the form's defaults need create permission"),
    ('frappe.db.exists("Employee Onboarding Template", {"title": title})', "a template HR changed is never overwritten"),
    ('frappe.db.exists("Terms and Conditions", rules.WORKPLACE_RULES_TITLE)', "nor the rules HR revised"),
    ('"hr": 1,', "the rules are HR Terms and Conditions"),
    ("workflows.setup_on_migrate(approval, ", "the workflow is built from onboarding_approval"),
    ("if value and not employee.get(field):", "the placement only fills blanks"),
    ('{"job_applicant": employee.job_applicant, "docstatus": 1, "employee": ("is", "not set")}',
     "an Employee links only its candidate's started onboarding that has none"),
    ('frappe.db.set_value("Employee Onboarding", onboarding, "employee", employee.name, update_modified=False)',
     "the link is written as Frappe HR writes it"),
    ('employee = frappe.db.get_value("Employee", {"job_applicant": doc.job_applicant}, "name")',
     "a step finds an Employee never linked by the candidate"),
    ('doc.db_set("employee", employee, update_modified=False)', "Employee is not allow_on_submit: written to the database"),
    ('if hod in ("Administrator", "Guest"):', "the handover never goes to Administrator"),
    # steps 5 to 7 and what the approval sets off
    ("if new_state != old_state and new_state == approval.PENDING_HRM:\n        _draft_salary(doc)",
     "the salary structure is drafted when the onboarding goes to the HR Manager"),
    ("if new_state != old_state and new_state == approval.APPROVED:\n        _approve(doc)",
     "the approval sets off the rest"),
    ("assignment.flags.ignore_permissions = True\n        assignment.submit()", "the approval submits the salary structure"),
    ("if assignment.docstatus != 0:\n            doc.custom_salary_structure_assignment = assignment.name\n            return assignment",
     "a submitted assignment is never changed"),
    ('"employee": doc.employee, "from_date": doc.custom_salary_from, "docstatus": ["!=", 2]}, "name")',
     "an assignment HR already made for the date is taken, not duplicated (Frappe HR allows one per date)"),
    ('if not frappe.db.exists("Probation Evaluation", {"employee": doc.employee, "docstatus": ["!=", 2]}):\n'
     '        probation.create_evaluation(', "one probation evaluation, however often the approval runs"),
    ('"base": flt(doc.custom_base_salary),', "the base salary goes into the assignment"),
    ("employee.reports_to = doc.custom_supervisor", "the supervisor becomes the Employee's Reports To"),
    ("if row.status == rules.TOOL_ISSUED and (row.tool, doc.name) not in have:", "the issued tools go on the register, once"),
    ("employee.custom_probation_status = probation_rules.ON_PROBATION", "the Employee is on probation"),
    ("reviews.create_reviews(doc.employee, doc.date_of_joining, doc.name, doc.custom_hr_officer)", "the 30-60-90 reviews"),
    ("probation.create_evaluation(doc.employee, probation_end, onboarding=doc.name, hr_officer=doc.custom_hr_officer)",
     "the probation evaluation"),
    ("contracts.draft_for_new_employee(doc.employee, doc.custom_hr_officer, flt(doc.get(\"custom_base_salary\")))",
     "the contract, drafted"),
    ("if doc.get(\"custom_training_required\"):\n        _schedule_training(doc)", "the training, when required"),
    ('activity.update({"user": supervisor_user, "role": None if supervisor_user else rules.HOD_ROLE})',
     "the supervisor evaluates the training (the HOD when the supervisor has no login)"),
    ("for row in rows:\n        row.status = rules.TOOL_REQUESTED", "the tools asked for are Requested"),
    ('if name and frappe.db.get_value("Salary Structure Assignment", name, "docstatus") == 0:\n'
     '        frappe.delete_doc("Salary Structure Assignment", name, ignore_permissions=True)',
     "a cancelled onboarding drops only the draft salary structure"),
    ('filters={"all_staff": 1}', "every new employee's tools are on each onboarding"),
    ('"parentfield": "custom_tools"}', "then the Job Title's own"),
):
    if needle not in glue:
        fail.append("onboarding.py: %s (%r not found)" % (why, needle))


def body_of(name):
    m = re.search(r"^def %s\(.*?(?=^def |^@|\Z)" % name, glue, re.M | re.S)
    return m.group(0) if m else ""


for name in ("validate", "before_update_after_submit"):
    if "_check_step(doc)" not in body_of(name) or "_resolve_assignees(doc)" not in body_of(name):
        fail.append("%s must check the step and hand out new activities" % name)
if "if doc.docstatus == 1:" not in body_of("validate"):
    fail.append("validate hands the activities out only as the onboarding starts (it is submitted)")
for name in ("validate", "before_update_after_submit"):
    body = body_of(name)
    if "_request_tools(doc)" not in body or body.find("_request_tools(doc)") > body.find("_resolve_assignees(doc)"):
        fail.append("%s must ask for the tools before handing the activities out (the requests are activities)" % name)
after_submit_body = body_of("before_update_after_submit")
if after_submit_body.find("_approve(doc)") > after_submit_body.find("_resolve_assignees(doc)"):
    fail.append("the approval adds the training evaluation activity: it must come before the activities are handed out")
after_submit = body_of("before_update_after_submit")
if "_link_employee(doc)" not in after_submit or after_submit.find("_link_employee(doc)") > after_submit.find("_check_step(doc)"):
    fail.append("before_update_after_submit must find the Employee before checking the step")
if not re.search(r"@frappe\.whitelist\(\)\ndef get_onboarding_defaults\(job_applicant, job_offer=None\):", glue):
    fail.append("get_onboarding_defaults must be whitelisted")
server_defaults = re.findall(r'"(\w+)"', (re.search(r"_SERVER_DEFAULTS = \((.*?)\)", glue, re.S) or re.search("()", "")).group(1))
if not server_defaults or "employee_onboarding_template" in server_defaults:
    fail.append("the server fills the defaults but never chooses the template: only the form loads its activities")
print("glue: activities handed out, the others assigned and allowed to complete, steps checked, seeds kept")

# ── 8. Wiring ────────────────────────────────────────────────────────
hooks_src = read("hrms_addon", "hooks.py")
hooks = {}
for node in ast.parse(hooks_src).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
events = (hooks.get("doc_events") or {}).get(EO, {})
EVENTS = {"validate": "validate", "before_update_after_submit": "before_update_after_submit", "on_submit": "after_tasks",
          "on_update_after_submit": "after_tasks", "on_cancel": "on_cancel"}
for event, function in EVENTS.items():
    if events.get(event) != "hrms_addon.hrms_addon.onboarding.%s" % function:
        fail.append("doc_events Employee Onboarding %s must be onboarding.%s" % (event, function))
    if not re.search(r"^def %s\(doc, method=None\):" % function, glue, re.M):
        fail.append("onboarding.%s(doc, method=None) is missing" % function)
if ((hooks.get("doc_events") or {}).get("Employee") or {}).get("on_update") != "hrms_addon.hrms_addon.onboarding.link_onboarding" \
        or not re.search(r"^def link_onboarding\(employee, method=None\):", glue, re.M):
    fail.append("doc_events Employee on_update must be onboarding.link_onboarding(employee, method=None)")
if "hrms_addon.hrms_addon.onboarding.setup_workflow_on_migrate" not in (hooks.get("after_migrate") or []) \
        or "def setup_workflow_on_migrate():" not in glue:
    fail.append("the onboarding workflow must be built on every migrate")
if "hrms_addon.hrms_addon.onboarding.after_install" not in (hooks.get("after_install") or []) \
        or not re.search(r"def after_install\(\):\n    seed_onboarding\(\)", glue):
    fail.append("a fresh install must seed the onboarding (after_install)")
for doctype, path in (("Employee Onboarding", "public/js/employee_onboarding.js"), ("Job Offer", "public/js/job_offer.js")):
    if (hooks.get("doctype_js") or {}).get(doctype) != path or not os.path.exists(os.path.join(REPO, "hrms_addon", path)):
        fail.append("doctype_js %s must be %s, and exist" % (doctype, path))
bio_glue = read("hrms_addon", "hrms_addon", "bio_data.py")
for source in ("Job Offer", "Employee Onboarding"):
    if 'return onboarding.add_placement(employee, "%s", source_name)' % source not in bio_glue:
        fail.append("Create Employee from the %s must add the placement (branch, employment type, offer date)" % source)
override_path = os.path.join(APP, "overrides", "employee_onboarding.py")
override = open(override_path, encoding="utf-8").read() if os.path.exists(override_path) else ""
if (hooks.get("override_doctype_class") or {}).get(EO) != "hrms_addon.hrms_addon.overrides.employee_onboarding.EmployeeOnboarding":
    fail.append("override_doctype_class must give Employee Onboarding the controller that lists the open tasks")
for needle, why in (
    ("from hrms.hr.doctype.employee_onboarding.employee_onboarding import EmployeeOnboarding as HRMSEmployeeOnboarding",
     "it extends Frappe HR's controller"),
    ("class EmployeeOnboarding(HRMSEmployeeOnboarding):", "it extends Frappe HR's controller"),
    ("    def validate_employee_creation(self):", "it replaces the check that names nothing"),
    ("if self.docstatus != 1:", "an onboarding not yet started still refuses"),
    ('frappe.db.get_value("Task", activity.task, ["status", "_assign"])', "each task's status and assignees are read"),
    ("pending = rules.pending_required(activities)", "the tested rule decides what is open"),
    ("rules.pending_message(self.name, pending),\n                IncompleteTaskError,", "the listing keeps Frappe HR's error"),
):
    if needle not in override:
        fail.append("overrides/employee_onboarding.py: %s (%r not found)" % (why, needle))

post = read("hrms_addon", "patches.txt").split("[post_model_sync]")
listed = [line.strip() for line in post[1].splitlines() if line.strip() and not line.startswith("#")] if len(post) == 2 else []
for patch, needles in (
    ("seed_onboarding", ("from hrms_addon.hrms_addon.onboarding import seed_onboarding", "def execute():\n    seed_onboarding()")),
    ("branch_on_applicants_and_offers", ('sync_fixtures("hrms_addon")', "ifnull(applicant.custom_branch, '') = ''",
                                         "ifnull(offer.custom_branch, '') = ''")),
):
    if "hrms_addon.patches.v1_0.%s" % patch not in listed:
        fail.append("%s must be a post_model_sync patch" % patch)
    path = os.path.join(REPO, "hrms_addon", "patches", "v1_0", patch + ".py")
    src = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    for needle in needles:
        if needle not in src:
            fail.append("patch %s: %r not found" % (patch, needle))
branch_patch = read("hrms_addon", "patches", "v1_0", "branch_on_applicants_and_offers.py")
if branch_patch.find("sync_fixtures(") > branch_patch.find("update `tabJob Applicant`"):
    fail.append("the branch patch must sync the fixtures (the new columns) before filling them: migrate imports "
                "fixtures after the patches")

js = read("hrms_addon", "public", "js", "employee_onboarding.js")
for method in re.findall(r'xcall\("hrms_addon\.hrms_addon\.onboarding\.(\w+)"', js):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % method, glue):
        fail.append("employee_onboarding.js calls %s, which is not a whitelisted function" % method)
fields_block = re.search(r"const HA_ONBOARDING_FIELDS = \[(.*?)\];", js, re.S)
js_fields = re.findall(r'"(\w+)"', fields_block.group(1)) if fields_block else []
if sorted(js_fields) != sorted(server_defaults):
    fail.append("the form fills %s, the server %s: they must fill the same fields" % (sorted(js_fields), sorted(server_defaults)))
if eo:
    for name in js_fields + ["employee_onboarding_template", "boarding_begins_on", "date_of_joining"]:
        if name not in eo_all:
            fail.append("employee_onboarding.js sets Employee Onboarding.%s, which does not exist" % name)
for label, src in (("employee_onboarding.js", js), ("job_offer.js", read("hrms_addon", "public", "js", "job_offer.js"))):
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", src, flags=re.S)
    for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
        if stripped.count(op) != stripped.count(cl):
            fail.append("%s: unbalanced %s%s" % (label, op, cl))
print("wiring: doc events, migrate, install, form scripts, Create Employee and patches all resolve")

# ── 9. Workplace Rules and Regulations print (LPL/HR/05) ─────────────
pf_path = os.path.join(APP, "print_format", "workplace_rules_and_regulations", "workplace_rules_and_regulations.json")
pf = json.load(open(pf_path, encoding="utf-8")) if os.path.exists(pf_path) else {}
if (pf.get("doctype"), pf.get("name"), pf.get("doc_type"), pf.get("module"), pf.get("standard"), pf.get("print_format_type"),
        pf.get("custom_format"), pf.get("disabled")) != ("Print Format", "Workplace Rules and Regulations", EO, "HRMS Addon",
                                                        "Yes", "Jinja", 1, 0):
    fail.append("Workplace Rules and Regulations must be a standard, enabled Jinja print format of Employee Onboarding")
page = pf.get("html") or ""
for block in ("for", "if", "macro"):
    if len(re.findall(r"{%-?\s*" + block + r"\b", page)) != len(re.findall(r"{%-?\s*end" + block + r"\b", page)):
        fail.append("the rules print format has unbalanced {%% %s %%} blocks" % block)
if page.count("{{") != page.count("}}") or page.count("{%") != page.count("%}"):
    fail.append("the rules print format has unbalanced {{ }} or {% %}")
if 'frappe.db.get_value("Terms and Conditions", "%s", "terms")' % R.WORKPLACE_RULES_TITLE not in page:
    fail.append("the print format must print the rules HR keeps, the Terms and Conditions %r" % R.WORKPLACE_RULES_TITLE)
flat = re.sub(r"\s+", " ", page)
for needle in ("LPL/HR/05", "WORKPLACE RULES AND REGULATIONS", "Acceptance by the employee",
               "have read and understand the above dos and don'ts and I agree to all of them"):
    if needle not in flat:
        fail.append("the rules print format must carry %r" % needle)
for name in set(re.findall(r"\bdoc\.([a-z_]+)", page)):
    if name not in eo_all:
        fail.append("the rules print format uses Employee Onboarding.%s, which does not exist" % name)
if re.findall(r"{{-?\s*doc\.[a-z_]+", page):
    fail.append("the rules print format must print text through v() so it is escaped")
print("print format: LPL/HR/05 from the rules HR keeps, the acceptance to sign, every field exists")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL ONBOARDING CHECKS PASSED")
