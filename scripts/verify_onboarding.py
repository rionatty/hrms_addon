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
       "rules_signed_on": "2026-10-01", "bio_data_signed_on": "2026-10-02", "hrm_remarks": ""}
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
expect("send before the bio-data is captured", step(A.ONBOARDING, A.PENDING_HRM, dict(ALL, bio_data_signed_on=None)),
       "Update the Employee from the signed Personal Bio-Data Form")
expect("send with nothing", step(A.ONBOARDING, A.PENDING_HRM, {}),
       "Record the date the Workplace Rules", "Create the Employee")
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
print("fixtures: status, stamps, branch chain and the step fields are what the workflow needs")

# ── 6. Upstream: what the glue relies on ─────────────────────────────
glue = read("hrms_addon", "hrms_addon", "onboarding.py")
eo = upstream_doctype(EO)
if eo:
    eo_all = {f["fieldname"]: f for f in eo["fields"]} | eo_fields
    for name in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"\bdoc\.(\w+)\b", glue))):
        if name in ("get", "set", "name", "docstatus", "get_doc_before_save", "activities", "idx", "flags", "throw"):
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
    print("upstream: the role-holder assignment, reload, task link, Employee back-link and update path all as relied on")
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
          "on_update_after_submit": "after_tasks"}
for event, function in EVENTS.items():
    if events.get(event) != "hrms_addon.hrms_addon.onboarding.%s" % function:
        fail.append("doc_events Employee Onboarding %s must be onboarding.%s" % (event, function))
    if not re.search(r"^def %s\(doc, method=None\):" % function, glue, re.M):
        fail.append("onboarding.%s(doc, method=None) is missing" % function)
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
