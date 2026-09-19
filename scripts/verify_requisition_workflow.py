"""Checks for the Job Requisition approval workflow, run without a bench.

requisition_approval.py imports nothing from Frappe, so it is loaded here
directly and every path through it is exercised: submit, each approval,
rejection at a sign-only step and at a decision step, revision after
rejection, and an attempt to type an approval in by hand.

It also cross-checks the definition against the fixtures and upstream
Frappe/HRMS: every stamped field exists, is read-only and has the right
type; every status value is a real Job Requisition status; every role,
state style and permission type is valid; and the hooks, form script and
patch are wired to things that exist. Picking the Job Title fills the Job
Description tab from that Job Title's JD, with only the parts the careers
page may show, and never over what someone wrote without asking.

Branches: the route after the HR Manager is walked for every Position
Category with the real condition strings (administrative straight to the
Executive Director, the others through the branch General Manager, exactly
one Approve holding at each step); the requisition carries its Branch and
the Department's category, the Job Opening its Branch, Luuka's three
branches are seeded, and Frappe only tells approvers who may open the
document (so Branch User Permissions route each step to its branch).

Needs ../ERPNext/{frappe,erpnext,hrms} (or FRAPPE_APPS_ROOT) for the
upstream cross-checks.

    python scripts/verify_requisition_workflow.py
"""
import glob
import importlib.util
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(rel):
    return open(os.path.join(REPO, rel), encoding="utf-8").read()


def load_rules():
    path = os.path.join(REPO, "hrms_addon", "hrms_addon", "requisition_approval.py")
    spec = importlib.util.spec_from_file_location("requisition_approval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it really has no Frappe import
    return module


def upstream_doctype(doctype):
    folder = doctype.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


rules = load_rules()
print("loaded requisition_approval.py without Frappe")

# ── 1. Shape of the workflow ─────────────────────────────────────────
state_names = list(dict.fromkeys(s["state"] for s in rules.STATES))
edit_rows = [(s["state"], s["allow_edit"]) for s in rules.STATES]
if len(edit_rows) != len(set(edit_rows)):
    fail.append("a state lists the same edit role twice")
if rules.STATES[0]["state"] != rules.DRAFT:
    fail.append("the first state row must be Draft: Frappe starts new documents in the first state")
for name in state_names:
    rows = [s for s in rules.STATES if s["state"] == name]
    if len({(s["status"], s["style"], s["send_email"]) for s in rows}) != 1:
        fail.append("the rows of state %s disagree on status, style or send_email" % name)
    if name != rules.DRAFT and len(rows) != 1:
        fail.append("only Draft may have a row per role; %s has %d" % (name, len(rows)))
    quiet = name in (rules.DRAFT, rules.REJECTED)
    if bool(rows[0]["send_email"]) == quiet:
        fail.append("%s must %s" % (name, "not send email: its next action is open to every requester role, "
                                          "so all of them would be emailed" if quiet
                                    else "send email: its approver needs telling"))
draft_editors = sorted(s["allow_edit"] for s in rules.STATES if s["state"] == rules.DRAFT)
if draft_editors != sorted(rules.REQUESTER_ROLES):
    fail.append("every requester role must be able to edit a Draft; Draft is editable by %s" % draft_editors)
for t in rules.TRANSITIONS:
    for key in ("state", "next_state"):
        if t[key] not in state_names:
            fail.append("transition %s -> %s uses unknown state %r" % (t["state"], t["next_state"], t[key]))
    if t["action"] not in rules.ACTIONS:
        fail.append("transition uses unknown action %r" % t["action"])

by_state = {}
for t in rules.TRANSITIONS:
    by_state.setdefault(t["state"], []).append(t)

chain = [step["state"] for step in rules.APPROVAL_CHAIN]
submit = by_state.get(rules.DRAFT, [])
if {(t["action"], t["next_state"]) for t in submit} != {(rules.SUBMIT, chain[0])} \
        or sorted(t["allowed"] for t in submit) != sorted(rules.REQUESTER_ROLES):
    fail.append("Draft must only allow Submit for Approval -> %s, once for each requester role %s"
                % (chain[0], list(rules.REQUESTER_ROLES)))
for index, step in enumerate(rules.APPROVAL_CHAIN):
    # Approve leads to the next step; before a step some requisitions skip
    # (the General Manager), one Approve leads into it and one past it, on
    # the step's own opposite conditions
    following = rules.APPROVAL_CHAIN[index + 1] if index + 1 < len(chain) else None
    if following and following.get("skip_if"):
        after = chain[index + 2] if index + 2 < len(chain) else rules.APPROVED
        approvals = [(rules.APPROVE, following["state"], step["role"], following["only_if"]),
                     (rules.APPROVE, after, step["role"], following["skip_if"])]
    else:
        approvals = [(rules.APPROVE, following["state"] if following else rules.APPROVED, step["role"], "")]
    got = sorted((t["action"], t["next_state"], t["allowed"], t.get("condition") or "") for t in by_state.get(step["state"], []))
    want = sorted(approvals + [(rules.REJECT, rules.REJECTED, step["role"], "")])
    if got != want:
        fail.append("%s transitions %s, expected %s" % (step["state"], got, want))
if by_state.get(rules.APPROVED):
    fail.append("Approved must be final")
revise = by_state.get(rules.REJECTED, [])
if {(t["action"], t["next_state"]) for t in revise} != {(rules.REVISE, rules.DRAFT)} \
        or sorted(t["allowed"] for t in revise) != sorted(rules.REQUESTER_ROLES):
    fail.append("Rejected must only allow Revise -> Draft, once for each requester role")

# every non-final state is reachable from Draft
reachable, frontier = {rules.DRAFT}, [rules.DRAFT]
while frontier:
    for t in by_state.get(frontier.pop(), []):
        if t["next_state"] not in reachable:
            reachable.add(t["next_state"])
            frontier.append(t["next_state"])
unreachable = set(state_names) - reachable
if unreachable:
    fail.append("unreachable states: %s" % sorted(unreachable))
print("workflow shape: %d states, %d transitions, all reachable" % (len(state_names), len(rules.TRANSITIONS)))

# ── 1b. The route by the Department's Position Category ──────────────
# Frappe evaluates each transition's condition with the requisition as `doc`
# (frappe/model/workflow.py is_transition_condition_satisfied) and offers the
# transitions that hold. Walking the chain with the real condition strings,
# exactly one Approve must hold at every step, for every category.
spec = importlib.util.spec_from_file_location("org_rules", os.path.join(REPO, "hrms_addon", "hrms_addon", "org_rules.py"))
org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(org)  # no Frappe import either


def approvals_that_hold(state, category):
    doc = types.SimpleNamespace(custom_position_category=category)
    return [t["next_state"] for t in by_state.get(state, []) if t["action"] == rules.APPROVE
            and (not t.get("condition") or eval(t["condition"], {"__builtins__": {}}, {"doc": doc}))]


for category in (*org.POSITION_CATEGORIES, None, ""):
    state, walked = chain[0], []
    while state != rules.APPROVED and len(walked) <= len(chain):
        walked.append(state)
        targets = approvals_that_hold(state, category)
        if len(targets) != 1:
            fail.append("exactly one Approve must apply at %s for a %r department, %d do: %s" % (state, category, len(targets), targets))
            break
        state = targets[0]
    if walked != rules.route(category):
        fail.append("a %r department's requisition goes %s, but route() says %s" % (category, walked, rules.route(category)))
if rules.ADMINISTRATIVE != org.ADMINISTRATIVE or rules.ADMINISTRATIVE not in org.POSITION_CATEGORIES:
    fail.append("the workflow's Administrative must be the Department's category %r" % org.ADMINISTRATIVE)
admin_route, other_route = rules.route(org.ADMINISTRATIVE), rules.route(org.NON_ADMINISTRATIVE)
if rules.GM_STATE in admin_route or admin_route[-2:] != [rules.HRM_STATE, chain[-1]]:
    fail.append("an administrative department's requisition goes HR Manager -> Executive Director: %s" % admin_route[-3:])
if other_route[-3:] != [rules.HRM_STATE, rules.GM_STATE, chain[-1]]:
    fail.append("the others go HR Manager -> General Manager -> Executive Director: %s" % other_route[-3:])
if rules.route(None) != other_route or rules.route("") != other_route:
    fail.append("a requisition with no category must take the longer route, through the General Manager")
for condition in {step.get(key) for step in rules.APPROVAL_CHAIN for key in ("only_if", "skip_if")} - {None}:
    if "doc.%s" % rules.CATEGORY_FIELD not in condition:
        fail.append("the condition %r must read the requisition's %s" % (condition, rules.CATEGORY_FIELD))
gm = next((step for step in rules.APPROVAL_CHAIN if step["state"] == rules.GM_STATE), {})
if gm.get("role") != "General Manager" or "General Manager" not in rules.NEW_ROLES:
    fail.append("the General Manager step is for the General Manager role, which the workflow creates")
print("route: administrative HR Manager -> Executive Director; the others through the General Manager; one Approve applies at each step")

# ── 2. Stamp fields match the fixtures ───────────────────────────────
custom = {f["fieldname"]: f for f in json.loads(read("hrms_addon/fixtures/custom_field.json")) if f["dt"] == rules.DOCTYPE}
for step in rules.APPROVAL_CHAIN:
    stamp = step["stamp"]
    for key, fieldtype in (("user", "Link"), ("date", "Date"), ("decision", "Select")):
        fn = stamp.get(key)
        if not fn:
            continue
        f = custom.get(fn)
        if not f:
            fail.append("%s stamps %r, which is not a Job Requisition custom field" % (step["state"], fn))
            continue
        if f["fieldtype"] != fieldtype:
            fail.append("%s is %s, expected %s" % (fn, f["fieldtype"], fieldtype))
        if key == "user" and f.get("options") != "User":
            fail.append("%s should link to User" % fn)
        if not f.get("read_only"):
            fail.append("%s must be read-only: only the workflow may fill it" % fn)
        if key == "decision":
            options = [o for o in f.get("options", "").split("\n") if o]
            for outcome in ("approved", "rejected"):
                if stamp[outcome] not in options:
                    fail.append("%s: %r is not one of its options %s" % (fn, stamp[outcome], options))

approvals_tab_fields = set()
in_approvals = False
order = next(json.loads(s["value"]) for s in json.loads(read("hrms_addon/fixtures/property_setter.json"))
             if s["name"] == "Job Requisition-main-field_order")
for fn in order:
    if fn == "custom_approvals_tab":
        in_approvals = True
        continue
    if in_approvals and fn in custom and custom[fn]["fieldtype"] == "Tab Break":
        break
    if in_approvals and fn in custom and custom[fn]["fieldtype"] not in ("Section Break", "Column Break"):
        approvals_tab_fields.add(fn)
if approvals_tab_fields != set(rules.ALL_STAMP_FIELDS):
    fail.append("Approvals tab fields and stamp fields differ: only on tab %s, only stamped %s"
                % (sorted(approvals_tab_fields - set(rules.ALL_STAMP_FIELDS)),
                   sorted(set(rules.ALL_STAMP_FIELDS) - approvals_tab_fields)))
print("stamp fields: %d, each exists, read-only, correctly typed, and exactly the Approvals tab" % len(rules.ALL_STAMP_FIELDS))

# ── 3. Upstream cross-checks ─────────────────────────────────────────
if os.path.isdir(APPS_ROOT):
    jr = upstream_doctype(rules.DOCTYPE)
    status_options = next(f["options"].split("\n") for f in jr["fields"] if f["fieldname"] == "status")
    for s in rules.STATES:
        if s["status"] not in status_options:
            fail.append("state %s sets status %r, not a Job Requisition status %s" % (s["state"], s["status"], status_options))
    approved_row = next(s for s in rules.STATES if s["state"] == rules.APPROVED)
    if approved_row["status"] != "Open & Approved":
        fail.append("Approved must set status 'Open & Approved' — HRMS only offers Create Job Opening then")

    styles = next(f["options"].split("\n") for f in upstream_doctype("Workflow State")["fields"] if f["fieldname"] == "style")
    for s in rules.STATES:
        if s["style"] not in styles:
            fail.append("state %s style %r not in %s" % (s["state"], s["style"], styles))

    known_roles = set(rules.NEW_ROLES)
    for app in ("frappe", "erpnext", "hrms"):
        for p in glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", "*", "*.json"), recursive=True):
            try:
                known_roles.update(perm.get("role") for perm in json.load(open(p, encoding="utf-8")).get("permissions") or [])
            except Exception:
                pass
    used_roles = {s["allow_edit"] for s in rules.STATES} | {t["allowed"] for t in rules.TRANSITIONS}
    used_roles |= {role for grants in rules.PERMISSIONS.values() for role in grants}
    for role in sorted(used_roles - known_roles):
        fail.append("role %r is neither created by this app nor present upstream" % role)
    for role in rules.NEW_ROLES:
        if role in known_roles - set(rules.NEW_ROLES):
            fail.append("role %r already exists upstream — do not create it" % role)

    perm_fields = {f["fieldname"] for f in upstream_doctype("Custom DocPerm")["fields"]}
    for doctype, grants in rules.PERMISSIONS.items():
        if upstream_doctype(doctype) is None:
            fail.append("permission target doctype %r not found upstream" % doctype)
        for role, ptypes in grants.items():
            for ptype in ptypes:
                if ptype not in perm_fields:
                    fail.append("%s/%s: %r is not a permission type" % (doctype, role, ptype))
    # Whoever can create a requisition must be able to edit and submit its
    # Draft, or the form locks its own author out ("This form is not
    # editable due to a Workflow").
    creators = {p["role"] for p in jr.get("permissions", []) if p.get("create")}
    creators |= {role for role, ptypes in rules.PERMISSIONS["Job Requisition"].items() if "create" in ptypes}
    locked_out = sorted(creators - set(rules.REQUESTER_ROLES))
    if locked_out:
        fail.append("%s can create a requisition but cannot edit or submit its Draft: add them to REQUESTER_ROLES" % locked_out)
    cannot_create = sorted(set(rules.REQUESTER_ROLES) - creators)
    if cannot_create:
        fail.append("requester roles %s cannot create a requisition" % cannot_create)
    if "send_email" not in {f["fieldname"] for f in upstream_doctype("Workflow Document State")["fields"]}:
        fail.append("Workflow Document State has no send_email field upstream")

    approver_roles = {step["role"] for step in rules.APPROVAL_CHAIN} - {"HR Manager"}
    for role in approver_roles:
        if "write" not in rules.PERMISSIONS["Job Requisition"].get(role, ()):
            fail.append("%s approves but has no write on Job Requisition — approving saves the document" % role)
    print("upstream: statuses, state styles, roles and permission types all valid")
else:
    print("upstream cross-checks SKIPPED (no %s)" % APPS_ROOT)

# ── 4. Behaviour ─────────────────────────────────────────────────────
USER, TODAY = "approver@example.com", "2026-09-16"
empty = {f: None for f in rules.ALL_STAMP_FIELDS}
supervisor, pending_po = rules.APPROVAL_CHAIN[0]["state"], rules.APPROVAL_CHAIN[1]["state"]
hrm, ed = rules.HRM_STATE, rules.APPROVAL_CHAIN[-1]["state"]


def check(label, got, expected):
    diffs = {k: (got.get(k), v) for k, v in expected.items() if got.get(k) != v}
    extra = {k: got[k] for k in got if k not in expected and got[k] not in (None, "")}
    if diffs or extra:
        fail.append("%s: wrong stamps %s unexpected %s" % (label, diffs, extra))


forged = dict(empty, custom_ed=USER, custom_ed_decision="Recruitment Approved", custom_ed_date=TODAY)
check("new document ignores posted approvals", rules.compute_stamp_values(None, rules.DRAFT, USER, TODAY, forged), empty)
check("submit stamps nothing", rules.compute_stamp_values(rules.DRAFT, supervisor, USER, TODAY, empty), empty)

walked = dict(empty)
expected = dict(empty)
states = [rules.DRAFT] + [s["state"] for s in rules.APPROVAL_CHAIN] + [rules.APPROVED]
for index in range(1, len(states) - 1):
    step = rules.APPROVAL_CHAIN[index - 1]
    walked = rules.compute_stamp_values(states[index], states[index + 1], "user%d" % index, TODAY, walked)
    expected[step["stamp"]["user"]] = "user%d" % index
    expected[step["stamp"]["date"]] = TODAY
    if step["stamp"].get("decision"):
        expected[step["stamp"]["decision"]] = step["stamp"]["approved"]
    check("approve at %s" % step["state"], walked, expected)
if walked.get("custom_hrm_decision") != "Recruitment Authorized" or walked.get("custom_ed_decision") != "Recruitment Approved":
    fail.append("full approval did not record both decisions")

check("reject at sign-only step stamps nothing",
      rules.compute_stamp_values(supervisor, rules.REJECTED, USER, TODAY, empty), empty)
after_super = dict(empty, custom_supervisor="sup", custom_supervisor_date=TODAY)
check("reject at HR Manager records Not Authorized",
      rules.compute_stamp_values(hrm, rules.REJECTED, USER, TODAY, after_super),
      dict(after_super, custom_hrm=USER, custom_hrm_date=TODAY, custom_hrm_decision="Not Authorized"))
check("reject at Executive Director records Not Approved",
      rules.compute_stamp_values(ed, rules.REJECTED, USER, TODAY, empty),
      dict(empty, custom_ed=USER, custom_ed_date=TODAY, custom_ed_decision="Not Approved"))
check("revise after rejection clears every approval",
      rules.compute_stamp_values(rules.REJECTED, rules.DRAFT, USER, TODAY, walked), empty)
# An administrative department's requisition goes from the HR Manager
# straight to the Executive Director: no General Manager stamp
check("an administrative requisition passes the General Manager by",
      rules.compute_stamp_values(hrm, ed, "hrm", TODAY, after_super),
      dict(after_super, custom_hrm="hrm", custom_hrm_date=TODAY, custom_hrm_decision="Recruitment Authorized"))
check("the General Manager's approval is recorded",
      rules.compute_stamp_values(rules.GM_STATE, ed, "gm", TODAY, empty), dict(empty, custom_gm="gm", custom_gm_date=TODAY))
check("a General Manager's rejection records nothing (a sign-only step)",
      rules.compute_stamp_values(rules.GM_STATE, rules.REJECTED, "gm", TODAY, empty), empty)
if not rules.recommended_salary_missing(hrm, rules.GM_STATE, None):
    fail.append("authorizing on to the General Manager without a Recommended Salary must be blocked too")

# The caller writes back EVERY returned value, so a hand-edited stamp in a
# plain save (no state change) is reverted to what the database held.
stored = dict(empty, custom_supervisor="sup", custom_supervisor_date=TODAY)
result = rules.compute_stamp_values(pending_po, pending_po, USER, TODAY, stored)
check("plain save keeps the database values", result, stored)
if set(result) != set(rules.ALL_STAMP_FIELDS):
    fail.append("compute_stamp_values must return every stamp field so tampering is overwritten")

if not rules.recommended_salary_missing(hrm, ed, None):
    fail.append("authorizing without a Recommended Salary must be blocked")
if rules.recommended_salary_missing(hrm, ed, 850000):
    fail.append("authorizing with a Recommended Salary must be allowed")
if rules.recommended_salary_missing(hrm, rules.REJECTED, None):
    fail.append("rejecting must not require a Recommended Salary")
if rules.recommended_salary_missing(supervisor, pending_po, None):
    fail.append("the salary rule must only apply at the HR Manager step")
print("behaviour: submit, %d approvals, rejections, the administrative short cut, revise, tamper, salary rule all correct"
      % len(rules.APPROVAL_CHAIN))

# ── 5. Wiring ────────────────────────────────────────────────────────
hooks = read("hrms_addon/hooks.py")
glue = read("hrms_addon/hrms_addon/job_requisition.py")
js = read("hrms_addon/public/js/job_requisition.js")

for event in ("before_validate", "validate"):
    if '"%s": "hrms_addon.hrms_addon.job_requisition.%s"' % (event, event) not in hooks:
        fail.append("hooks.py doc_events does not wire %s" % event)
    if "def %s(doc, method=None)" % event not in glue:
        fail.append("job_requisition.py has no %s(doc, method=None)" % event)
if '"hrms_addon.hrms_addon.job_requisition.setup_on_migrate"' not in hooks or "def setup_on_migrate(" not in glue:
    fail.append("setup_on_migrate is not wired into after_migrate")
if hooks.count("\ndoc_events = ") != 1:
    fail.append("doc_events must be assigned exactly once in hooks.py (a second assignment replaces the first)")

block = re.search(r"^doctype_js = \{(.*?)^\}", hooks, re.S | re.M)
m = re.search(r'"Job Requisition": "([^"]+)"', block.group(1)) if block else None
if not m or not os.path.exists(os.path.join(REPO, "hrms_addon", m.group(1))):
    fail.append("doctype_js for Job Requisition does not point at an existing file")

for method in re.findall(r'xcall\("hrms_addon\.hrms_addon\.job_requisition\.(\w+)"', js):
    if not re.search(r"@frappe\.whitelist\(\)\s*\ndef %s\(" % method, glue):
        fail.append("form script calls %s, which is not a whitelisted function" % method)
if "links_area" in js or "custom_connections_html" in js:
    fail.append("form script must leave the Connections list in its own tab")
builder = read("hrms_addon/hrms_addon/workflows.py")
if '"send_email": row["send_email"]' not in builder or '"update_value", "send_email")' not in builder:
    fail.append("workflows.py must write and compare send_email, or existing workflows keep emailing on drafts")
if "workflows.setup_on_migrate(rules, " not in glue or "from hrms_addon.hrms_addon import workflows" not in glue:
    fail.append("job_requisition.setup_on_migrate must build the workflow with workflows.py from requisition_approval")
stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", js, flags=re.S)
for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
    if stripped.count(op) != stripped.count(cl):
        fail.append("job_requisition.js: unbalanced %s%s" % (op, cl))

patch_lines = [l.strip() for l in read("hrms_addon/patches.txt").splitlines()
               if l.strip() and not l.strip().startswith(("#", "["))]
if not patch_lines:
    fail.append("patches.txt lists no patches")
for dotted in patch_lines:
    rel = os.path.join(*dotted.split(".")) + ".py"
    if not os.path.exists(os.path.join(REPO, rel)):
        fail.append("patch %s has no file %s" % (dotted, rel))
    elif "def execute(" not in read(rel):
        fail.append("patch %s has no execute()" % dotted)
    package = os.path.join(REPO, *dotted.split(".")[:-1], "__init__.py")
    if not os.path.exists(package):
        fail.append("patch package for %s is missing __init__.py" % dotted)
print("wiring: doc events, after_migrate, form script, whitelisted call and patch all resolve")

# ── 6. The Job Description tab, from the Job Title's JD ──────────────
custom_fields = {f["name"]: f for f in json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))}
careers = read("hrms_addon/hrms_addon/careers.py")
jd_fields = re.search(r"^JD_FIELDS = \(([^)]*)\)", glue, re.M)
jd_field_names = re.findall(r'"(\w+)"', jd_fields.group(1)) if jd_fields else []
if jd_field_names != ["description", "custom_reporting_line", "custom_subordinates"]:
    fail.append("JD_FIELDS must be the Job Description tab's Responsibilities, Reporting Line and Subordinates: %s" % jd_field_names)
js_fields = re.search(r"^const HA_JD_FIELDS = \[([^\]]*)\];", js, re.M)
if not js_fields or re.findall(r'"(\w+)"', js_fields.group(1)) != jd_field_names:
    fail.append("job_requisition.js must fill the fields the server fills (HA_JD_FIELDS = JD_FIELDS)")
for name in ("Job Requisition-custom_reporting_line", "Job Requisition-custom_subordinates", "Designation-custom_jd_reports_to",
             "Designation-custom_jd_reporting_lines"):
    if name not in custom_fields:
        fail.append("custom field %s, which the Job Description tab fill reads or writes, does not exist" % name)
if (custom_fields.get("Job Requisition-custom_reporting_line") or {}).get("options") \
        != (custom_fields.get("Designation-custom_jd_reports_to") or {}).get("options"):
    fail.append("the requisition's Reporting Line and the JD's Reports To must link to the same DocType")
requisition_json = upstream_doctype("Job Requisition")
if requisition_json and next((f for f in requisition_json["fields"] if f["fieldname"] == "description"), {}).get("fieldtype") != "Text Editor":
    fail.append("HRMS's Job Requisition.description is no longer a Text Editor: recheck requisition_description's HTML")
body = glue.split("def get_job_description(")[-1].split("\ndef ")[0]
if 'frappe.has_permission("Job Requisition", "write", throw=True)' not in body or "return job_description_for(designation)" not in body:
    fail.append("get_job_description must check the user may write requisitions before reading the Job Title for them")
for needle, why in (
    ("jd_rules.requisition_description(careers.posting_details_of(jd))",
     "must write the Responsibilities from the careers page's parts of the JD only (HRMS copies them onto the public Job Opening)"),
    ('values["custom_reporting_line"] = jd.get("custom_jd_reports_to") or ""', "must take the Reporting Line from the JD's Reports To"),
    ('jd.get("custom_jd_reporting_lines"),', "must take the Subordinates from the JD's Reporting Relationships"),
    ('frappe.get_all("JD Relationship Type", order_by="creation asc", pluck="name")', "must order the subordinates as HR orders relationship types"),
    ('if doc.is_new() and doc.get("designation") and not any(_has_content(doc.get(field)) for field in JD_FIELDS):\n'
     "        doc.update(job_description_for(doc.designation))",
     "must fill only a new requisition's empty Job Description tab, never what someone wrote or cleared"),
    ('or "<img" in value.lower()', "must count a pasted image as content"),
):
    if needle not in glue:
        fail.append("job_requisition.py %s" % why)
if not re.search(r"def posting_details_of\(designation\):\n(?:.*\n)*?    return jd_rules\.posting_details\(", careers) \
        or 'return posting_details_of(frappe.get_doc("Designation", designation))' not in careers:
    fail.append("careers.posting_details_of must be exactly what the careers page shows, so the requisition says no more")
for needle, why in (
    ("designation(frm) {\n\t\tif (frm.doc.designation) {\n\t\t\tha_fill_job_description(frm);", "must fill the tab when the Job Title is picked"),
    ('.xcall("hrms_addon.hrms_addon.job_requisition.get_job_description", { designation })', "must ask the server for the Job Title's JD"),
    ("if (frm.doc.designation !== designation) {", "must ignore an answer for a Job Title since changed"),
    ("if (ha_jd_blank(frm) || ha_jd_as_filled(frm)) {\n\t\t\t\tfill();\n\t\t\t} else {\n\t\t\t\tfrappe.confirm(",
     "must ask before replacing what someone wrote"),
    ("if (frm.is_new() && frm.doc.designation && ha_jd_blank(frm)) {", "must fill on refresh only a new requisition with an empty tab"),
    ("new DOMParser().parseFromString(", "must read the tab's HTML inertly"),
    ('body.querySelectorAll("img, video, iframe, object, embed").length', "must count a pasted image as content"),
):
    if needle not in js:
        fail.append("job_requisition.js %s" % why)
if re.search(r"\$\([^)]*\)\s*\.html\(", js):
    fail.append("job_requisition.js must not parse the tab's HTML with jQuery, which loads its images and runs their handlers")
print("job description tab: the Job Title's JD fills it (public parts only), asks before replacing, new requisitions filled on save")

# ── 7. Branches: each approval reaches only the requisition's own branch ─
fixtures_cf = {f["name"]: f for f in json.loads(read("hrms_addon/fixtures/custom_field.json"))}
setters = {s["name"]: s for s in json.loads(read("hrms_addon/fixtures/property_setter.json"))}
if tuple(org.BRANCHES) != ("Kawempe", "Namanve", "Matugga") or org.ORG_MASTERS != {"Branch": ("branch", org.BRANCHES)}:
    fail.append("Luuka's branches are Kawempe, Namanve and Matugga, seeded into ERPNext's Branch: %s" % (org.ORG_MASTERS,))
picks = read("hrms_addon/hrms_addon/pick_lists.py")
for needle, why in (
    ("MASTERS = {**jd_rules.MASTERS, **bio_data_rules.BIO_DATA_MASTERS, **org_rules.ORG_MASTERS}", "must seed the branches on a new install"),
    ("def seed_branches():", "must seed the branches on its own, for the patch"),
    ("    seed_masters(org_rules.ORG_MASTERS)", "must seed the branches through seed_masters (adds only what is missing)"),
):
    if needle not in picks:
        fail.append("pick_lists.py %s" % why)
if "hrms_addon.patches.v1_0.seed_branches" not in read("hrms_addon/patches.txt").split("[post_model_sync]")[-1] \
        or not re.search(r"def execute\(\):\n    seed_branches\(\)", read("hrms_addon/patches/v1_0/seed_branches.py")):
    fail.append("existing sites need the branches seeded once: post_model_sync patch seed_branches")
branch = fixtures_cf.get("Job Requisition-custom_branch") or {}
if (branch.get("fieldtype"), branch.get("options"), branch.get("reqd"), branch.get("fetch_from"), branch.get("fetch_if_empty")) \
        != ("Link", "Branch", 1, "requested_by.branch", 1):
    fail.append("the requisition needs a mandatory Branch, taken from the requester's employee record unless chosen")
category = fixtures_cf.get("Job Requisition-%s" % rules.CATEGORY_FIELD) or {}
if category.get("fetch_from") != "department.%s" % rules.CATEGORY_FIELD or not category.get("read_only"):
    fail.append("the requisition's %s must be the Department's, read-only: the workflow conditions read it" % rules.CATEGORY_FIELD)
department = fixtures_cf.get("Department-%s" % rules.CATEGORY_FIELD) or {}
if department.get("fieldtype") != "Select" or [o for o in (department.get("options") or "").split("\n") if o] != list(org.POSITION_CATEGORIES) \
        or department.get("default") != org.NON_ADMINISTRATIVE or not department.get("reqd"):
    fail.append("each Department needs its Position Category %s, Non-Administrative by default" % (org.POSITION_CATEGORIES,))
if (setters.get("Job Requisition-department-reqd") or {}).get("value") != "1":
    fail.append("Department must be mandatory on the requisition: it picks the route and the department's HOD")
for name, value in (("Job Opening-location-label", "Branch"), ("Job Opening-location-reqd", "1"),
                    ("Job Opening-location-fetch_from", "job_requisition.custom_branch"), ("Job Opening-location-fetch_if_empty", "1")):
    if (setters.get(name) or {}).get("value") != value:
        fail.append("the Job Opening's Location is its Branch, from the requisition: property setter %s must be %r" % (name, value))
if '"allow_self_approval", "condition")' not in read("hrms_addon/hrms_addon/workflows.py"):
    fail.append("workflows.py must compare transition conditions, or a changed route never reaches a site")
if os.path.isdir(APPS_ROOT):
    def upstream_field(doctype, fieldname):
        return next((f for f in (upstream_doctype(doctype) or {}).get("fields", []) if f["fieldname"] == fieldname), {})

    for doctype, fieldname, options in (("Employee", "branch", "Branch"), ("Job Requisition", "requested_by", "Employee"),
                                        ("Job Requisition", "department", "Department"), ("Job Opening", "location", "Branch")):
        if upstream_field(doctype, fieldname).get("options") != options:
            fail.append("upstream %s.%s is no longer a Link to %s: recheck the branch routing" % (doctype, fieldname, options))
    if upstream_field("Workflow Transition", "condition").get("fieldtype") != "Code":
        fail.append("Frappe's Workflow Transition has no condition any more: recheck the General Manager route")
    workflow_model = open(os.path.join(APPS_ROOT, "frappe", "frappe", "model", "workflow.py"), encoding="utf-8").read()
    if "frappe.safe_eval(transition.condition, get_workflow_safe_globals(), dict(doc=doc.as_dict()))" not in workflow_model:
        fail.append("Frappe evaluates transition conditions differently: recheck the route conditions")
    workflow_action = open(os.path.join(APPS_ROOT, "frappe", "frappe", "workflow", "doctype", "workflow_action", "workflow_action.py"),
                           encoding="utf-8").read()
    if "return has_permission(doctype=doc, user=user)" not in workflow_action \
            or "has_approval_access(user, doc, transition) and user_has_permission(user)" not in workflow_action:
        fail.append("Frappe's workflow no longer tells only the approvers who may open the document: branch routing needs rechecking")
print("branches: Kawempe, Namanve, Matugga seeded; the requisition carries its Branch and the Department's category; "
      "the opening its Branch; Frappe tells only approvers who may open the document")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL WORKFLOW CHECKS PASSED")
