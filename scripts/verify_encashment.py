"""Verify leave encashment, without a bench:

    python scripts/verify_encashment.py

The minutes of 16 and 20 July 2026 (Reward and Compensation, §4.5): an
employee required to work during their approved leave applies for the
leave to be paid; only accumulated days are paid, Management set the
limit; the immediate Supervisor, HR, the General Manager and the Executive
Director approve it, it goes back to HR, and the Accounts Manager processes
it, the amount worked out from the salary and the days.

  1  the rules: what an application says, what Management may change, a
     day's pay
  2  the chain: walked end to end, every desk stamped, a refusal never paid
  3  the fields: every stamp and remark on Frappe HR's own Leave Encashment
  4  the glue reads and writes fields that exist, and prices the days only
     where Frappe HR could not
  5  wiring: the doc events, the form script, the workflow and the earning
     component on migrate, the leave type that may be encashed

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


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"),
                         recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


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


R, W = load("encashment_rules"), load("encashment_approval")
hooks = hooks_dict()
print("loaded encashment_rules.py and encashment_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
ok = {"employee": "HR-EMP-00100", "days": 5, "balance": 12, "reason": "Recalled for the Mbale order"}
expect("five accumulated days, worked through", R.application_errors(ok))
expect("no days", R.application_errors(dict(ok, days=0)), "how many leave days")
expect("more than is accumulated", R.application_errors(dict(ok, days=13)), "Only the accumulated leave")
expect("no reason", R.application_errors(dict(ok, reason=" ")), "why the leave was worked")
worked = dict(ok, leave_employee="HR-EMP-00100", leave_status="Approved", leave_days=7)
expect("the leave worked through, named", R.application_errors(worked))
expect("somebody else's leave", R.application_errors(dict(worked, leave_employee="HR-EMP-00999")),
       "employee's own")
expect("a leave never approved", R.application_errors(dict(worked, leave_status=None)), "approved leave")
expect("more days than the leave had", R.application_errors(dict(worked, leave_days=3)),
       "the leave worked through was 3")
expect("Management cutting the days", R.management_errors({"days": 3, "requested": 5}))
expect("anyone raising them", R.management_errors({"days": 6, "requested": 5}), "no more than that")
expect("cut to nothing", R.management_errors({"days": 0, "requested": 5}), "how many leave days")
if R.per_day(1300000) != 50000 or R.amount(1300000, 5) != 250000:
    fail.append("a day's pay is the gross over 26 working days: %s" % R.per_day(1300000))
if R.WORKING_DAYS_A_MONTH != load("settlement_rules").WORKING_DAYS_A_MONTH:
    fail.append("leave is encashed at the same day's pay as untaken leave on a final settlement")
print("encashment: the application, Management's limit, a day's pay")

# ── 2. The chain ──────────────────────────────────────────────────────
walked, state, seen = [W.DRAFT], W.DRAFT, set()
while state not in seen:
    seen.add(state)
    forward = [t for t in W.TRANSITIONS if t["state"] == state
               and t["action"] in (W.SUBMIT, W.APPROVE, W.FORWARD, W.PROCESS)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != [W.DRAFT, W.PENDING_SUPERVISOR, W.PENDING_HR, W.PENDING_GM, W.PENDING_ED, W.APPROVED,
              W.PENDING_ACCOUNTS, W.PROCESSED]:
    fail.append("the minutes' chain: Supervisor, HR, General Manager, Executive Director, back to HR, "
                "then the Accounts Manager: %s" % walked)
if set(W.STAMPS) != set(W.PENDING_STATES) or set(W.ROLE_WAITING) != set(W.PENDING_STATES):
    fail.append("every desk the application passes is stamped, and knows whose it is")
if W.ROLE_WAITING[W.APPROVED] != "HR User" or W.ROLE_WAITING[W.PENDING_ACCOUNTS] != "Accounts Manager":
    fail.append("it goes back to HR, then to the Accounts Manager in Finance")
docstatus = {row["state"]: row.get("doc_status", "0") for row in W.STATES}
if docstatus[W.PROCESSED] != "1":
    fail.append("processed is submitted: that is when Frappe HR pays it through the payroll")
if docstatus[W.REJECTED] != "0":
    fail.append("a refused encashment is never submitted, since a submitted one is paid")
for state in (W.PENDING_SUPERVISOR, W.PENDING_HR, W.PENDING_GM, W.PENDING_ED, W.PENDING_ACCOUNTS):
    if not [t for t in W.TRANSITIONS if t["state"] == state and t["action"] == W.RETURN]:
        fail.append("%s can send the application back" % state)
expect("returned without saying why", W.step_errors(W.PENDING_GM, W.DRAFT, {}), "Return Remarks")
expect("refused without saying why", W.step_errors(W.PENDING_ED, W.REJECTED, {}),
       "Executive Director's remarks")
if any(W.compute_stamps(W.PENDING_ED, W.DRAFT, "x", "2026-10-09", {"custom_hr_by": "a"}).values()):
    fail.append("a return clears every signature")
if W.next_states(W.PENDING_ED, ("General Manager",)) or W.next_states(W.PENDING_ACCOUNTS, ("HR User",)):
    fail.append("nobody may act on a desk that is not theirs")
if set(W.MANAGEMENT) != {W.PENDING_GM, W.PENDING_ED}:
    fail.append("Management, who set the limit, are the General Manager and the Executive Director")
print("the chain: walked end to end, every desk stamped, a refusal never paid")

# ── 3. The fields ─────────────────────────────────────────────────────
custom = [row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
          if row["dt"] == "Leave Encashment"]
fields = {row["fieldname"]: row for row in custom}
upstream = {f["fieldname"]: f for f in (upstream_doctype("Leave Encashment") or {}).get("fields", [])}
if not upstream:
    fail.append("Frappe HR no longer ships Leave Encashment, which this is built on")
for fieldname in list(W.ALL_STAMP_FIELDS) + [f for f, _who in W.REMARK_FIELDS.values()] + [
        W.STATUS_FIELD, "custom_return_remarks", "custom_branch", "custom_leave_application", "custom_reason",
        "custom_days_requested", "custom_per_day"]:
    if fieldname not in fields:
        fail.append("Leave Encashment has no %s" % fieldname)
for fieldname in list(W.ALL_STAMP_FIELDS) + [W.STATUS_FIELD, "custom_days_requested", "custom_per_day"]:
    if not (fields.get(fieldname) or {}).get("read_only"):
        fail.append("Leave Encashment.%s is stamped or worked out, not typed" % fieldname)
states = {row["state"] for row in W.STATES}
options = set((fields.get(W.STATUS_FIELD) or {}).get("options", "").split("\n"))
if states - options:
    fail.append("%s must offer every state: %s" % (W.STATUS_FIELD, sorted(states - options)))
if "status" not in upstream or W.STATUS_FIELD == "status":
    fail.append("Frappe HR's own status is theirs (Unpaid, Paid): the chain writes beside it")
if (fields.get("custom_branch") or {}).get("fetch_from") != "employee.branch":
    fail.append("the application is routed by the employee's plant")
print("the fields: every desk's stamp and remarks on Frappe HR's own form")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "encashments.py")
known = set(fields) | set(upstream) | {"workflow_state", "docstatus", "name", "doctype"}
for fieldname in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "db_set", "get_doc_before_save"):
        continue
    if fieldname not in known:
        fail.append("encashments.py reads or writes Leave Encashment.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.application_errors(", "what an application says is judged by the rules"),
    ("rules.management_errors(", "and so is what Management may change"),
    ("rules.per_day(", "a day's pay is worked out by them"),
    ('if flt(doc.get("encashment_amount")) > 0:', "a per-day amount on the salary structure is Frappe HR's to use"),
    ('doc.custom_days_requested = flt(doc.get("encashment_days"))', "what was asked for is kept as it left the employee"),
):
    if needle not in glue:
        fail.append("encashments.py: %s (%r not found)" % (why, needle))
print("glue: the rules followed, the days priced only where Frappe HR could not")

# ── 5. Wiring ─────────────────────────────────────────────────────────
events = (hooks.get("doc_events") or {}).get("Leave Encashment") or {}
for event, handler in (("validate", "encashment_validate"), ("on_submit", "encashment_on_submit"),
                       ("on_cancel", "encashment_on_cancel")):
    if events.get(event) != "hrms_addon.hrms_addon.encashments.%s" % handler:
        fail.append("Leave Encashment's %s must run encashments.%s" % (event, handler))
if (hooks.get("doctype_js") or {}).get("Leave Encashment") != "public/js/leave_encashment.js":
    fail.append("the form script is Leave Encashment's doctype_js")
if "hrms_addon.hrms_addon.encashments.setup_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the workflow and the earning component are set up after every migrate")
listed = [name for entry in hooks.get("fixtures") or [] if isinstance(entry, dict)
          and entry.get("dt") == "Custom Field" for name in entry["filters"][0][2]]
for row in custom:
    if row["name"] not in listed:
        fail.append("hooks.py fixtures must list %s" % row["name"])
leave = read("hrms_addon", "hrms_addon", "leave.py")
if '"allow_encashment": 1' not in leave or "max_encashable_leaves" in leave:
    fail.append("annual leave may be encashed, with no fixed maximum: Management set the limit")
if "ensure_earning_component()" not in glue or '"Leave Type", filters={"allow_encashment": 1}' not in glue:
    fail.append("Frappe HR refuses to submit an encashment with no earning component: one is set")
workspace = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "workspace", "leaves", "leaves.json")
if not os.path.exists(workspace) or "Leave Encashment" not in open(workspace, encoding="utf-8").read():
    fail.append("Frappe HR no longer lists Leave Encashment on its Leaves page")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Leave Encashment" in carded or "Leave Encashment" in sidebarred:
    fail.append("Leave Encashment is Frappe HR's own and already on their Leaves page: leave it there")
print("wiring: the doc events, the form script, the workflow on migrate, the leave type")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LEAVE ENCASHMENT CHECKS PASSED")
