"""Verify the loans application, without a bench:

    python scripts/verify_loans.py

Luuka's revised flow chart 4.4 and its six test cases: the request, the
three approvals, the terms Accounts settle with the employee, the
employee's own consent (LPL/HR/39), the monthly deduction the payroll
takes, and the monitoring that follows.

  1  the rules: who qualifies, the ceiling, the schedule, the consent
  2  the DocTypes carry the loan and its schedule
  3  the glue reads and writes fields that exist, and recovers through
     Frappe HR's own Additional Salary rather than a list kept by hand
  4  the signatures: the chain walked end to end, every desk stamped
  5  wiring: the workflow on migrate, the daily job, the way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import datetime
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


R, W = load("loan_rules"), load("loan_approval")
hooks = hooks_dict()
print("loaded loan_rules.py and loan_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if R.limit_for(1000000) != 3000000:
    fail.append("a loan is at most three months' gross")
if R.months_served("2026-01-15", "2026-07-14") != 5:
    fail.append("a month is not served until the day of the month comes round")

ok = {"status": "Active", "date_of_joining": "2024-01-01", "today": "2026-09-21", "gross_pay": 1000000,
      "amount": 2000000, "outstanding": 0, "instalments": 6, "purpose": "School fees",
      "category": "Administrative"}
expect("an employee who qualifies", R.eligibility_errors(ok))
expect("someone who left", R.eligibility_errors(dict(ok, status="Left")), "active employee")
expect("someone just joined", R.eligibility_errors(dict(ok, date_of_joining="2026-08-01")),
       "month(s) of service")
expect("more than three months' gross", R.eligibility_errors(dict(ok, amount=5000000)),
       "most that may be lent")
expect("an earlier loan still owed", R.eligibility_errors(dict(ok, outstanding=120000)), "still owed")
expect("recovered over too long", R.eligibility_errors(dict(ok, instalments=24)), "at most 12")
expect("no purpose", R.eligibility_errors(dict(ok, purpose="")), "what the loan is for")
expect("nothing asked for", R.eligibility_errors(dict(ok, amount=0)), "how much")

if R.interest_for(1200000, 0, 6) != 0:
    fail.append("a staff loan carries no interest by default")
if R.interest_for(1200000, 10, 6) != 60000:
    fail.append("a flat rate is the whole term's interest, worked out once: %s"
                % R.interest_for(1200000, 10, 6))
schedule = R.repayment_schedule(1200000, 0, 6, "2026-10-31")
if len(schedule) != 6:
    fail.append("six months means six repayments")
if round(sum(row[1] for row in schedule), 2) != 1200000:
    fail.append("the principal must add back to the whole: %s" % (schedule,))
if [row[0].month for row in schedule] != [10, 11, 12, 1, 2, 3]:
    fail.append("the repayments run month by month and turn the year: %s" % (schedule,))
odd = R.repayment_schedule(100, 0, 3, "2026-10-31")
if [row[1] for row in odd] != [33.33, 33.33, 33.34]:
    fail.append("the rounding goes on the last repayment: %s" % (odd,))
with_interest = R.repayment_schedule(1200000, 10, 6, "2026-10-31")
if round(sum(row[3] for row in with_interest), 2) != 1260000:
    fail.append("principal and interest together add back to what is owed: %s" % (with_interest,))
if R.monthly_instalment(1200000, 0, 6) != 200000:
    fail.append("the monthly instalment is what the first repayment comes to")
if R.repayment_schedule(0, 0, 6, "2026-10-31") != []:
    fail.append("nothing is recovered from nothing")
if R.outstanding(1200000, 400000) != 800000:
    fail.append("what is outstanding is what was not yet recovered")
if R.loan_status(1, 1200000, 1200000) != R.REPAID:
    fail.append("a loan fully recovered is Repaid")
if R.loan_status(1, 1200000, 400000) != R.RUNNING:
    fail.append("and one part recovered is Running")
if R.loan_status(1, 1200000, 0, written_off=True) != R.WRITTEN_OFF:
    fail.append("one written off says so")
if R.loan_status(0, 1200000, 0) != R.DRAFT:
    fail.append("a draft is a request, not a loan")

consent = {"liability": "Staff loan", "amount": 1200000, "instalments": 6, "effective_from": "2026-10-31",
           "consent": 1}
expect("a consent that stands (LPL/HR/39)", R.consent_errors(consent))
expect("no liability", R.consent_errors(dict(consent, liability="")), "Liability")
expect("no amount", R.consent_errors(dict(consent, amount=0)), "how much is deducted")
expect("no instalments", R.consent_errors(dict(consent, instalments=0)), "equal instalments")
expect("no date", R.consent_errors(dict(consent, effective_from=None)), "from when")
expect("not consented", R.consent_errors(dict(consent, consent=0)), "employee consents")

terms = {"amount": 2000000, "approved_amount": 1200000, "instalments": 6,
         "first_repayment": "2026-10-31", "rate": 0}
expect("terms that stand", R.terms_errors(terms))
expect("lending more than was asked for", R.terms_errors(dict(terms, approved_amount=3000000)),
       "only UGX 2,000,000 was asked for")
expect("no amount settled", R.terms_errors(dict(terms, approved_amount=0)), "amount actually being lent")
expect("no months", R.terms_errors(dict(terms, instalments=0)), "how many months")
expect("no first repayment", R.terms_errors(dict(terms, first_repayment=None)), "which month")
# the minutes of 16 and 20 July 2026, §4.10, and the test script's first
# case: loans are for the administration team; a car loan is at most UGX 30
# million; a study loan is what the course costs
expect("somebody from production", R.eligibility_errors(dict(ok, category="Non-Administrative")),
       "administration team")
expect("somebody whose department says nothing", R.eligibility_errors(dict(ok, category=None)),
       "not marked Administrative")
car = dict(ok, loan_type="Car Loan", amount=30000000, instalments=12)
expect("a car loan of UGX 30 million, whatever the gross", R.eligibility_errors(car))
expect("a car loan over it", R.eligibility_errors(dict(car, amount=30000001)), "at most UGX 30,000,000")
study = dict(ok, loan_type="Study Loan", amount=9000000, fee_structure="/files/fees.pdf")
expect("a study loan with its fees, over three months' gross", R.eligibility_errors(study))
expect("a study loan with no fee structure", R.eligibility_errors(dict(study, fee_structure=None)),
       "fee structure")
expect("a loan Luuka do not offer", R.eligibility_errors(dict(ok, loan_type="Holiday Loan")),
       "not a valid loan type")
if R.limit_for_type("Car Loan", 500000) != 30000000 or R.limit_for_type("Study Loan", 500000) is not None \
        or R.limit_for_type("Other", 500000) != 1500000:
    fail.append("the ceiling follows the kind of loan: 30 million, the course, or three months' gross")
print("loans: who qualifies, the ceiling, the schedule, the consent, the terms")

# ── 2. The DocTypes ───────────────────────────────────────────────────
if upstream_doctype("Loan"):
    fail.append("the lending app is installed after all: build the staff loan on its Loan instead")
for name, wanted in (
    ("Employee Loan", ("employee", "loan_amount", "purpose", "gross_pay", "limit", "outstanding_before",
                       "qualifies", "eligibility_remarks", "approved_amount", "interest_rate",
                       "instalments", "first_repayment", "total_interest", "monthly_instalment",
                       "repayments", "recovered_amount", "outstanding", "written_off", "liability",
                       "extent_of_deduction", "effective_from", "consent", "consent_by", "consent_on",
                       "disbursed_on", "hod_by", "ed_by", "gm_by", "accounts_by", "return_remarks",
                       "approval_status", "status", "recovery_component")),
    ("Loan Repayment", ("payroll_date", "principal", "interest", "total", "additional_salary",
                        "recovered")),
):
    fields = fields_of(doctype(name))
    if not fields:
        fail.append("%s is not there" % name)
        continue
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the loan process asks for" % (name, fieldname))
loan = fields_of(doctype("Employee Loan"))
for fieldname in ("gross_pay", "limit", "outstanding_before", "qualifies", "total_interest",
                  "monthly_instalment", "recovered_amount", "outstanding", "approval_status", "status"):
    if not (loan.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Loan.%s is worked out, not typed" % fieldname)
if (loan.get("repayments") or {}).get("options") != "Loan Repayment":
    fail.append("the schedule is a table of Loan Repayment")
if (loan.get("status") or {}).get("options", "").split("\n") != list(R.STATUSES):
    fail.append("Employee Loan.status must offer exactly the loan's own lifecycle")
if not doctype("Employee Loan").get("is_submittable"):
    fail.append("a running loan is a submitted document")
repayment = fields_of(doctype("Loan Repayment"))
for fieldname in ("total", "additional_salary", "recovered"):
    if not (repayment.get(fieldname) or {}).get("read_only"):
        fail.append("Loan Repayment.%s is worked out, not typed" % fieldname)
print("the loan: the request, the terms, the consent, the schedule")

# ── 3. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "loans.py")
known = set(loan) | set(repayment) | {"workflow_state", "docstatus", "name", "employee", "company"}
for fieldname in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"doc\.(\w+)\b", glue))):
    if fieldname in ("doctype", "get", "set", "append", "db_set", "flags", "get_doc_before_save",
                     "check_permission", "insert", "submit", "cancel", "save"):
        continue
    if fieldname not in known:
        fail.append("loans.py reads or writes Employee Loan.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.eligibility_errors(", "who may take a loan is judged by the rules"),
    ("rules.repayment_schedule(", "the schedule is worked out by them"),
    ("rules.consent_errors(", "LPL/HR/39 is judged by them"),
    ("rules.terms_errors(", "and so are the terms Accounts settle"),
    ("rules.loan_status(", "and where the loan stands"),
    ("Additional Salary", "test case 5: the payroll takes the deduction, nobody keeps a list"),
    ("Salary Detail", "and what it really took is read back"),
):
    if needle not in glue:
        fail.append("loans.py: %s (%r not found)" % (why, needle))
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_loan", "employee_loan.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        loans.loan_%s(self)" % (method, method) not in controller:
        fail.append("the Employee Loan controller must hand %s to loans.loan_%s" % (method, method))
print("glue: the rules followed, the payroll taking the deduction, what it took read back")

# ── 4. The signatures ─────────────────────────────────────────────────
walked, state, seen = [W.DRAFT], W.DRAFT, set()
while state not in seen:
    seen.add(state)
    forward = [t for t in W.TRANSITIONS if t["state"] == state
               and t["action"] in (W.SUBMIT, W.APPROVE, W.RUN)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != [W.DRAFT, W.PENDING_HOD, W.PENDING_ED, W.PENDING_GM, W.PENDING_ACCOUNTS, W.PENDING_CONSENT,
              W.RUNNING]:
    fail.append("the loan goes HOD, Executive Director, General Manager, Accounts, the employee: %s"
                % walked)
if set(W.STAMPS) != set(W.PENDING_STATES) or set(W.REMARK_FIELDS) != set(W.PENDING_STATES):
    fail.append("every desk the loan passes is stamped: %s" % sorted(W.STAMPS))
if set(W.ROLE_WAITING) != set(W.PENDING_STATES):
    fail.append("every pending state must know whose desk it is on")
for state in (W.PENDING_HOD, W.PENDING_ED, W.PENDING_GM):
    if not [t for t in W.TRANSITIONS if t["state"] == state and t["action"] == W.RETURN]:
        fail.append("%s must be able to send the loan back, which is the chart's \"Approved? No\"" % state)
expect("returned without saying why", W.step_errors(W.PENDING_ED, W.DRAFT, {}), "Return Remarks")
expect("refused without saying why", W.step_errors(W.PENDING_GM, W.REJECTED, {}),
       "General Manager's remarks")
if any(W.compute_stamps(W.PENDING_GM, W.DRAFT, "x", "2026-03-04", {"hod_by": "a"}).values()):
    fail.append("a return clears every signature")
if W.next_states(W.PENDING_ED, ("Employee",)):
    fail.append("nobody may act on a desk that is not theirs")
if W.next_states(W.PENDING_CONSENT, ("Employee",)) != [(W.RUN, W.RUNNING), (W.RETURN, W.DRAFT)]:
    fail.append("the employee consents, or sends the loan back: %s"
                % W.next_states(W.PENDING_CONSENT, ("Employee",)))
states = {row["state"] for row in W.STATES}
options = set((loan.get("approval_status") or {}).get("options", "").split("\n"))
if states - options:
    fail.append("Employee Loan.approval_status must offer every state of the workflow: %s"
                % sorted(states - options))
print("signatures: the chain walked end to end, every desk stamped, the return that sends it back")

# ── 5. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.loans.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the loan workflow must be built after every migrate")
if "hrms_addon.hrms_addon.loans.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("step 6 of the chart is a daily job")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Employee Loan" not in carded or "Employee Loan" not in sidebarred:
    fail.append("the Employee Loan needs a way in")
if "Loans" not in navigation.CARDS or "Loans" not in navigation.SIDEBAR:
    fail.append("loan management has a page of its own under HR")
if "Loans" not in [page["label"] for page in navigation.PAGES]:
    fail.append("and this app makes it: Frappe HR has no page for lending")
print("wiring: the workflow on migrate, the daily job, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LOAN CHECKS PASSED")
