"""Checks for the Job Requisition approval workflow, run without a bench.

requisition_approval.py imports nothing from Frappe, so it is loaded here
directly and every path through it is exercised: submit, each approval,
rejection at a sign-only step and at a decision step, revision after
rejection, and an attempt to type an approval in by hand.

It also cross-checks the definition against the fixtures and upstream
Frappe/HRMS: every stamped field exists, is read-only and has the right
type; every status value is a real Job Requisition status; every role,
state style and permission type is valid; and the hooks, form script and
patch are wired to things that exist.

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
state_names = [s["state"] for s in rules.STATES]
if len(state_names) != len(set(state_names)):
    fail.append("duplicate states")
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
if [(t["action"], t["next_state"]) for t in submit] != [(rules.SUBMIT, chain[0])]:
    fail.append("Draft must have exactly one transition: Submit for Approval -> %s" % chain[0])
for index, step in enumerate(rules.APPROVAL_CHAIN):
    expected_next = chain[index + 1] if index + 1 < len(chain) else rules.APPROVED
    got = sorted((t["action"], t["next_state"], t["allowed"]) for t in by_state.get(step["state"], []))
    want = sorted([(rules.APPROVE, expected_next, step["role"]), (rules.REJECT, rules.REJECTED, step["role"])])
    if got != want:
        fail.append("%s transitions %s, expected %s" % (step["state"], got, want))
if by_state.get(rules.APPROVED):
    fail.append("Approved must be final")
if [(t["action"], t["next_state"]) for t in by_state.get(rules.REJECTED, [])] != [(rules.REVISE, rules.DRAFT)]:
    fail.append("Rejected must only allow Revise -> Draft")

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
print("behaviour: submit, 6 approvals, 3 rejections, revise, tamper, salary rule all correct")

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

m = re.search(r'doctype_js = \{"Job Requisition": "([^"]+)"\}', hooks)
if not m or not os.path.exists(os.path.join(REPO, "hrms_addon", m.group(1))):
    fail.append("doctype_js for Job Requisition does not point at an existing file")

for method in re.findall(r'xcall\("hrms_addon\.hrms_addon\.job_requisition\.(\w+)"', js):
    if not re.search(r"@frappe\.whitelist\(\)\s*\ndef %s\(" % method, glue):
        fail.append("form script calls %s, which is not a whitelisted function" % method)
if "custom_connections_html" not in js:
    fail.append("form script does not mount the Connections list")
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

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL WORKFLOW CHECKS PASSED")
