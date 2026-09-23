"""Verify penalty deductions, without a bench:

    python scripts/verify_penalties.py

The minutes of 16 and 20 July 2026 (Reward and Compensation, §4.11): the
supervisor reports the case to the HR Officer, who hears it with the
employee and the supervisor; if the employee is found liable, instalments
are agreed and they sign the Employee Deduction Consent (LPL/HR/39); the HR
Manager forwards it to the Executive Director, who approves it, and it goes
back to the HR Officer — and the payroll takes it.

  1  the rules: the report, the hearing, the agreement, the consent and
     the declaration the employee signs
  2  the DocType carries the case, LPL/HR/39 and the schedule
  3  the glue reads and writes fields that exist, and recovers through
     Frappe HR's own Additional Salary as a loan does
  4  the signatures: the chain walked end to end, every desk stamped
  5  what the payroll took comes back on its own: the Salary Slip marks
     each month recovered, for loans, advances and penalties alike
  6  wiring: the workflow on migrate, the final settlement, the way in

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
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"),
                         recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


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


R, W = load("penalty_rules"), load("penalty_approval")
hooks = hooks_dict()
print("loaded penalty_rules.py and penalty_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
report = {"employee": "HR-EMP-00100", "kind": "Damage", "incident_date": "2026-10-02",
          "details": "Dropped the 45 cm roll; the core cracked", "today": "2026-10-03"}
expect("a report that says what happened", R.report_errors(report))
expect("no kind", R.report_errors(dict(report, kind=None)), "property loss, damage or other")
expect("no date", R.report_errors(dict(report, incident_date=None)), "when it happened")
expect("a date to come", R.report_errors(dict(report, incident_date="2026-10-09")), "after today")
expect("nothing described", R.report_errors(dict(report, details=" ")), "lost or damaged")

heard = {"hearing_on": "2026-10-05 10:00:00", "hearing_record": "<p>He agreed the roll fell.</p>",
         "employee_heard": 1, "supervisor_heard": 1, "finding": "Liable", "amount": 300000,
         "instalments": 3, "effective_from": "2026-10-25"}
expect("a hearing that found him liable and agreed the instalments", R.hearing_errors(heard))
expect("no record of it", R.hearing_errors(dict(heard, hearing_record="<p><br></p>")), "what was said")
expect("no finding", R.hearing_errors(dict(heard, finding=None)), "found liable")
expect("the employee not heard", R.hearing_errors(dict(heard, employee_heard=0)), "heard before")
expect("the supervisor absent", R.hearing_errors(dict(heard, supervisor_heard=0)), "supervisor")
expect("no amount agreed", R.hearing_errors(dict(heard, amount=0)), "how much")
expect("no instalments agreed", R.hearing_errors(dict(heard, instalments=0)), "equal instalments")
expect("no month agreed", R.hearing_errors(dict(heard, effective_from=None)), "from when")
expect("a deduction dated before the hearing", R.hearing_errors(dict(heard, effective_from="2026-09-25")),
       "before the hearing")
expect("cleared, with the hearing held and written",
       R.hearing_errors(dict(heard, finding="Not Liable", employee_heard=0, amount=0)))

consent = {"liability": "The cracked core of a 45 cm roll", "reason": "Damage", "amount": 300000,
           "instalments": 3, "effective_from": "2026-10-25", "consent": 1, "by_employee": True}
expect("the employee signs it themselves", R.consent_errors(consent))
expect("no liability", R.consent_errors(dict(consent, liability="")), "Liability")
expect("no reason", R.consent_errors(dict(consent, reason="")), "Reason")
expect("not signed", R.consent_errors(dict(consent, consent=0)), "signs the Employee Deduction Consent")
expect("HR recording it with no signed form", R.consent_errors(dict(consent, by_employee=False)),
       "attach the LPL/HR/39")
expect("HR recording it with the form", R.consent_errors(dict(consent, by_employee=False,
                                                               signed_form="/files/lpl-hr-39.pdf")))
words = R.declaration({"employee_name": "John Okello", "amount": 300000, "instalments": 3,
                       "effective_from": "2026-10-25", "liability": "the cracked core of a 45 cm roll",
                       "year": 2026})
for needle in ("I, John Okello, do hereby agree to a salary deduction of UGX 300,000 in 3 equal",
               "effective 25 October 2026", "Luuka Plastics Ltd in respect of the cracked core",
               "in the year 2026", "recovered in lump sum from my terminal benefits"):
    if needle not in words:
        fail.append("the declaration says what LPL/HR/39 says: %r is missing from %r" % (needle, words))
if R.extent(300000, 3) != "UGX 100,000 a month for 3 month(s)" or R.extent(0, 3) is not None:
    fail.append("the extent of the deduction, in words: %s" % R.extent(300000, 3))
if R.penalty_status(1, "Liable", 300000, 100000) != R.RECOVERING \
        or R.penalty_status(1, "Liable", 300000, 300000) != R.RECOVERED \
        or R.penalty_status(1, "Not Liable", 0, 0) != R.NOT_LIABLE \
        or R.penalty_status(1, "Liable", 300000, 0, rejected=True) != R.REJECTED \
        or R.penalty_status(0, "Liable", 300000, 0) != R.DRAFT \
        or R.penalty_status(2, "Liable", 300000, 0) != R.CANCELLED:
    fail.append("where a penalty stands: recovering, recovered, not liable, refused, a draft, cancelled")
if R.age("1990-03-04", "2026-03-03") != 35 or R.age("1990-03-04", "2026-03-04") != 36:
    fail.append("LPL/HR/39 asks the age: a year is not turned until the birthday")
print("penalties: the report, the hearing, the agreement, the consent, the declaration")

# ── 2. The DocType ────────────────────────────────────────────────────
penalty = fields_of(doctype("Employee Penalty"))
for fieldname in ("employee", "employee_name", "badge_no", "gender", "age", "section", "designation",
                  "kind", "incident_date", "details", "estimated_value", "evidence", "reported_by",
                  "hearing_on", "employee_heard", "supervisor_heard", "hearing_record", "finding",
                  "heard_by", "amount", "instalments", "effective_from", "monthly_instalment",
                  "extent_of_deduction", "recovery_component", "liability", "reason", "declaration",
                  "consent", "signed_form", "consent_by", "hrm_by", "ed_by", "sent_by", "return_remarks",
                  "repayments", "recovered_amount", "outstanding", "approval_status", "status"):
    if fieldname not in penalty:
        fail.append("Employee Penalty has no %s, which the minutes or LPL/HR/39 ask for" % fieldname)
for fieldname in ("age", "monthly_instalment", "extent_of_deduction", "declaration", "recovered_amount",
                  "outstanding", "approval_status", "status", "reported_by", "heard_by", "consent_by",
                  "hrm_by", "ed_by", "sent_by"):
    if not (penalty.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Penalty.%s is worked out or stamped, not typed" % fieldname)
if (penalty.get("repayments") or {}).get("options") != "Loan Repayment":
    fail.append("the instalments are the loan's own schedule table, Loan Repayment")
if (penalty.get("status") or {}).get("options", "").split("\n") != [
        R.DRAFT, R.RECOVERING, R.RECOVERED, R.NOT_LIABLE, R.REJECTED, R.CANCELLED]:
    fail.append("Employee Penalty.status must offer exactly the penalty's own lifecycle")
if (penalty.get("kind") or {}).get("options", "").split("\n") != list(R.KINDS):
    fail.append("Employee Penalty.kind offers the kinds the rules know")
if (penalty.get("finding") or {}).get("options", "").split("\n") != [""] + list(R.FINDINGS):
    fail.append("Employee Penalty.finding offers the findings the rules know, and starts empty")
spec = doctype("Employee Penalty")
if not spec.get("is_submittable"):
    fail.append("a penalty being recovered is a submitted document")
roles = {row["role"] for row in spec.get("permissions", [])}
for role in ("Supervisor", "HR User", "HR Manager", "Executive Director", "Employee"):
    if role not in roles:
        fail.append("%s works on the penalty and needs rights on it" % role)
for row in spec.get("permissions", []):
    if row["role"] == "Employee" and row.get("create"):
        fail.append("an employee does not report their own penalty")
    if row["role"] in ("HR User", "Executive Director") and not row.get("submit"):
        fail.append("%s ends a case (sent to payroll, cleared or refused), which submits it" % row["role"])
print("the penalty: the report, the hearing, LPL/HR/39, the schedule")

# ── 3. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "penalties.py")
repayment = fields_of(doctype("Loan Repayment"))
known = set(penalty) | set(repayment) | {"workflow_state", "docstatus", "name", "employee", "company"}
for fieldname in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"doc\.(\w+)\b", glue))):
    if fieldname in ("doctype", "get", "set", "append", "db_set", "flags", "get_doc_before_save",
                     "check_permission", "insert", "submit", "cancel", "save"):
        continue
    if fieldname not in known:
        fail.append("penalties.py reads or writes Employee Penalty.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.report_errors(", "the supervisor's report is judged by the rules"),
    ("rules.hearing_errors(", "and the hearing"),
    ("rules.consent_errors(", "and LPL/HR/39"),
    ("rules.declaration(", "the declaration is worded by them"),
    ("loan_rules.repayment_schedule(", "the instalments are a loan's schedule"),
    ("Additional Salary", "the payroll takes each instalment, nobody keeps a list"),
    ("_is_the_employee(doc)", "a consent HR record for the employee needs the signed form"),
):
    if needle not in glue:
        fail.append("penalties.py: %s (%r not found)" % (why, needle))
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_penalty", "employee_penalty.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        penalties.penalty_%s(self)" % (method, method) not in controller:
        fail.append("the Employee Penalty controller must hand %s to penalties.penalty_%s" % (method, method))
print("glue: the rules followed, the loan's schedule, the payroll taking the deduction")

# ── 4. The signatures ─────────────────────────────────────────────────
walked, state, seen = [W.DRAFT], W.DRAFT, set()
while state not in seen:
    seen.add(state)
    forward = [t for t in W.TRANSITIONS if t["state"] == state
               and t["action"] in (W.REPORT, W.FIND_LIABLE, W.CONSENT, W.FORWARD, W.APPROVE, W.SEND)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != [W.DRAFT, W.PENDING_HEARING, W.PENDING_CONSENT, W.PENDING_HRM, W.PENDING_ED,
              W.PENDING_HR_OFFICER, W.RECOVERING]:
    fail.append("the minutes' chain: supervisor, hearing, the employee's consent, the HR Manager, the "
                "Executive Director, back to the HR Officer: %s" % walked)
if set(W.STAMPS) != set(W.ORDER) or set(W.ROLE_WAITING) != set(W.PENDING_STATES):
    fail.append("every desk the penalty passes is stamped, and knows whose it is")
if W.ROLE_WAITING[W.PENDING_HEARING] != "HR User" or W.ROLE_WAITING[W.PENDING_HRM] != "HR Manager" \
        or W.ROLE_WAITING[W.PENDING_ED] != "Executive Director":
    fail.append("the HR Officer hears it, the HR Manager forwards it, the Executive Director approves it")
if [t["allowed"] for t in W.TRANSITIONS if t["state"] == W.DRAFT] != ["Supervisor", "HR User", "HR Manager"]:
    fail.append("the immediate supervisor reports the case (or HR for them)")
if (W.CLEAR, W.NOT_LIABLE) not in W.next_states(W.PENDING_HEARING, ("HR User",)):
    fail.append("a hearing can clear the employee")
if W.next_states(W.PENDING_CONSENT, ("Employee",)) != [(W.CONSENT, W.PENDING_HRM),
                                                       (W.DISPUTE, W.PENDING_HEARING)]:
    fail.append("the employee signs, or disputes it back to the hearing: %s"
                % W.next_states(W.PENDING_CONSENT, ("Employee",)))
if W.next_states(W.PENDING_ED, ("HR Manager",)) or W.next_states(W.PENDING_HRM, ("Employee",)):
    fail.append("nobody may act on a desk that is not theirs")
expect("sent back without saying why", W.step_errors(W.PENDING_ED, W.PENDING_HEARING, {}), "Return Remarks")
expect("disputed without saying why", W.step_errors(W.PENDING_CONSENT, W.PENDING_HEARING, {}),
       "does not agree")
expect("refused without saying why", W.step_errors(W.PENDING_ED, W.REJECTED, {}),
       "Executive Director's remarks")
expect("asked to consent with no finding of liability",
       W.step_errors(W.PENDING_HEARING, W.PENDING_CONSENT, {"finding": "Not Liable"}), "finding is Liable")
expect("cleared while found liable", W.step_errors(W.PENDING_HEARING, W.NOT_LIABLE, {"finding": "Liable"}),
       "Not Liable")
signed = {"reported_by": "sup", "heard_by": "hro", "consent_by": "emp", "hrm_by": "hrm"}
back = W.compute_stamps(W.PENDING_ED, W.PENDING_HEARING, "ed", "2026-10-09", signed)
if back.get("reported_by") != "sup" or any(back.get(f) for f in ("heard_by", "consent_by", "hrm_by", "ed_by")):
    fail.append("sent back to the hearing, the report stands and every signature after it is given again: %s"
                % back)
forward = W.compute_stamps(W.PENDING_ED, W.PENDING_HR_OFFICER, "ed", "2026-10-09", signed)
if forward.get("ed_by") != "ed" or forward.get("hrm_by") != "hrm":
    fail.append("the Executive Director's approval is stamped, and the earlier signatures kept")
states = {row["state"] for row in W.STATES}
options = set((penalty.get("approval_status") or {}).get("options", "").split("\n"))
if states - options:
    fail.append("Employee Penalty.approval_status must offer every state: %s" % sorted(states - options))
for row in W.STATES:
    if row["state"] in (W.RECOVERING, W.NOT_LIABLE, W.REJECTED) and row.get("doc_status") != "1":
        fail.append("%s ends the case: it is submitted" % row["state"])
print("signatures: the chain walked end to end, every desk stamped, the returns that send it back")

# ── 5. What the payroll took ──────────────────────────────────────────
recover = read("hrms_addon", "hrms_addon", "recoveries.py")
events = hooks.get("doc_events") or {}
slip = events.get("Salary Slip") or {}
if slip.get("on_submit") != "hrms_addon.hrms_addon.recoveries.slip_on_submit" \
        or slip.get("on_cancel") != "hrms_addon.hrms_addon.recoveries.slip_on_cancel":
    fail.append("the Salary Slip marks what it took, and a cancelled one unmarks it")
for doctype_name, module in (("Employee Loan", "loans"), ("Employee Penalty", "penalties"),
                             ("Employee Advance", "advances")):
    if '"%s": %s.refresh_recovered' % (doctype_name, module) not in recover:
        fail.append("recoveries.py brings the %s up to date" % doctype_name)
    source = read("hrms_addon", "hrms_addon", module + ".py")
    if "def refresh_recovered(name):" not in source:
        fail.append("%s.py says what it has recovered once a month is marked" % module)
if "hrms_addon.hrms_addon.recoveries.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("what a slip took before this was installed is caught up daily")
if '@frappe.whitelist(methods=["POST"])\ndef catch_up_for(' not in recover:
    fail.append("the forms' Mark Recovered button calls a whitelisted method")
for script, doctype_name in (("hrms_addon/hrms_addon/doctype/employee_loan/employee_loan.js", "Employee Loan"),
                             ("hrms_addon/public/js/employee_advance.js", "Employee Advance"),
                             ("hrms_addon/hrms_addon/doctype/employee_penalty/employee_penalty.js",
                              "Employee Penalty")):
    source = read(*script.split("/"))
    if "Mark Recovered" in source and "hrms_addon.hrms_addon.recoveries.catch_up_for" not in source:
        fail.append("%s's Mark Recovered button must call recoveries.catch_up_for" % doctype_name)
for module in ("loans", "advances"):
    source = read("hrms_addon", "hrms_addon", module + ".py")
    for name in re.findall(r"xcall\(\"hrms_addon\.hrms_addon\.%s\.(\w+)\"" % module,
                           read("hrms_addon", "hrms_addon", "doctype", "employee_loan", "employee_loan.js")
                           + read("hrms_addon", "public", "js", "employee_advance.js")):
        if "@frappe.whitelist" not in source.split("def %s(" % name)[0].rsplit("\n\n\n", 1)[-1]:
            fail.append("%s.%s is called from a form, so it must be whitelisted" % (module, name))
if "Salary Detail" not in recover or '"docstatus": 1' not in recover:
    fail.append("a month is recovered when a submitted slip carries its deduction")
print("recoveries: the slip marks what it took, for loans, advances and penalties alike")

# ── 6. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.penalties.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the penalty workflow must be built after every migrate")
settle = load("settlement_rules")
if "Penalties Outstanding" not in settle.RECEIVABLES:
    fail.append("LPL/HR/39: what is still owed on a penalty comes out of the terminal benefits")
found = settle.suggest({"gross_pay": 1000000, "penalties_outstanding": 200000})
if {"component": "Penalties Outstanding", "amount": 200000.0} not in found["receivables"]:
    fail.append("the settlement suggests the penalty still owed: %s" % found["receivables"])
if "penalties.owed(employee)" not in read("hrms_addon", "hrms_addon", "settlements.py"):
    fail.append("the settlement reads what the employee still owes on penalties")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Employee Penalty" not in carded or "Employee Penalty" not in sidebarred:
    fail.append("the Employee Penalty needs a way in")
if not upstream_doctype("Additional Salary"):
    fail.append("Frappe HR no longer ships Additional Salary, which the recovery is built on")
print("wiring: the workflow on migrate, the final settlement, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL PENALTY CHECKS PASSED")
