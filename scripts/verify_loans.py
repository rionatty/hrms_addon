"""Verify the loans application, without a bench:

    python scripts/verify_loans.py

Luuka's revised flow chart 4.4 and its six test cases: the request, the
approvals (set up in the desk), the terms Accounts settle with the
employee, the employee's own consent (LPL/HR/39), the loan paid out, the
monthly deduction the payroll takes, and the monitoring that follows.

  1  the rules: who qualifies (as Loan Settings say), the ceiling, the
     schedule, the terms, the consent, the payment, a month missed
  2  the DocTypes carry the loan, its schedule and its settings
  3  the glue reads and writes fields that exist, recovers through Frappe
     HR's own Additional Salary and books the money through a Journal Entry
  4  the workflow: made once and then set up in the desk; the checks rest on
     the states every set-up keeps; the employee never runs their own loan
  5  wiring: the workflow on migrate, the jobs, the hooks, the patches, the
     reports, the way in

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


def body(source, name):
    return source.split("def %s(" % name)[1].split(chr(10) + "def ")[0] if "def %s(" % name in source else ""


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


def handlers(value):
    return [value] if isinstance(value, str) else list(value or [])


R, W = load("loan_rules"), load("loan_approval")
hooks = hooks_dict()
CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
print("loaded loan_rules.py and loan_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if R.limit_for(1000000) != 3000000:
    fail.append("a loan is at most three months' gross unless the settings say otherwise")
if R.months_served("2026-01-15", "2026-07-14") != 5:
    fail.append("a month is not served until the day of the month comes round")

ok = {"status": "Active", "date_of_joining": "2024-01-01", "today": "2026-09-21", "gross_pay": 1000000,
      "amount": 2000000, "outstanding": 0, "instalments": 6, "purpose": "School fees",
      "category": "Administrative"}
expect("an employee who qualifies", R.eligibility_errors(ok))
expect("someone who left", R.eligibility_errors(dict(ok, status="Left")), "active employee")
expect("someone just joined", R.eligibility_errors(dict(ok, date_of_joining="2026-08-01")), "month(s) of service")
expect("more than three months' gross", R.eligibility_errors(dict(ok, amount=5000000)), "most that may be lent")
expect("an earlier loan still owed", R.eligibility_errors(dict(ok, outstanding=120000)), "still owed")
expect("another request waiting", R.eligibility_errors(dict(ok, waiting="HR-LOAN-2026-00001")),
       "HR-LOAN-2026-00001, is waiting for approval")
expect("recovered over too long", R.eligibility_errors(dict(ok, instalments=24)), "at most 12")
expect("no purpose", R.eligibility_errors(dict(ok, purpose="")), "what the loan is for")
expect("nothing asked for", R.eligibility_errors(dict(ok, amount=0)), "how much")
expect("somebody from production", R.eligibility_errors(dict(ok, category="Non-Administrative")),
       "administration team")
expect("somebody whose department says nothing", R.eligibility_errors(dict(ok, category=None)),
       "not marked Administrative")
car = dict(ok, loan_type="Car Loan", amount=30000000, instalments=12)
expect("a car loan of UGX 30 million, whatever the gross", R.eligibility_errors(car))
expect("a car loan over it", R.eligibility_errors(dict(car, amount=30000001)), "at most UGX 30,000,000")
study = dict(ok, loan_type="Study Loan", amount=9000000, fee_structure="/files/fees.pdf")
expect("a study loan with its fees, over three months' gross", R.eligibility_errors(study))
expect("a study loan with no fee structure", R.eligibility_errors(dict(study, fee_structure=None)), "fee structure")
expect("a loan Luuka do not offer", R.eligibility_errors(dict(ok, loan_type="Holiday Loan")), "not a valid loan type")
expect("no pay on record, for a loan worked out from it", R.eligibility_errors(dict(ok, gross_pay=0)),
       "no gross pay on record")
expect("a car loan's ceiling needs no gross", R.eligibility_errors(dict(car, gross_pay=0)))
if R.limit_for_type("Car Loan", 500000) != 30000000 or R.limit_for_type("Study Loan", 500000) is not None \
        or R.limit_for_type("Other", 500000) != 1500000:
    fail.append("the ceiling follows the kind of loan: 30 million, the course, or three months' gross")
if R.limit_for_type("Car Loan", 500000, settings={"car_loan_max": 20000000}) != 20000000:
    fail.append("the car loan's ceiling the form shows is the one Luuka set")

# the settings: every figure a policy decides
if R.settings_from({}) != R.DEFAULTS or R.settings_from({"admin_only": 0, "car_loan_max": "20000000"})["admin_only"] != 0:
    fail.append("Loan Settings merge over the defaults, a stored nought staying a nought")
tight = {"car_loan_max": 20000000, "admin_only": 0, "min_months": 12, "other_allowed": 0,
         "car_max_instalments": 48, "other_max_instalments": 6, "other_months_of_gross": 1}
expect("the car loan's ceiling from the settings", R.eligibility_errors(dict(car, amount=25000000), tight),
       "at most UGX 20,000,000")
expect("a car loan over four years when the settings allow it",
       R.eligibility_errors(dict(car, amount=18000000, instalments=48), tight))
expect("everybody may borrow when the settings open it",
       R.eligibility_errors(dict(car, amount=18000000, category="Non-Administrative"), tight))
expect("the months of service the settings ask",
       R.eligibility_errors(dict(car, amount=100, date_of_joining="2026-01-01"), tight),
       "after 12 month(s) of service")
expect("no other loans when the settings say so", R.eligibility_errors(dict(ok, amount=1500000), tight),
       "Only car and study loans", "most that may be lent")
expect("an instalment over the share of the gross the settings allow",
       R.eligibility_errors(dict(ok, amount=2000000, instalments=6), {"max_share_of_gross": 25}),
       "more than 25% of the gross pay")
expect("an instalment within it", R.eligibility_errors(dict(ok, amount=1200000, instalments=6),
                                                       {"max_share_of_gross": 25}))
if R.max_instalments("Car Loan", tight) != 48 or R.max_instalments("Other", tight) != 6 \
        or R.max_instalments("Study Loan", tight) != 12:
    fail.append("each kind of loan is recovered within its own months")
expect("settings that stand", R.settings_errors(R.DEFAULTS))
expect("settings that do not", R.settings_errors(dict(R.DEFAULTS, car_max_instalments=0, max_share_of_gross=120,
                                                      default_rate=-1, car_loan_max=-5)),
       "at least one month", "between 0 and 100%", "cannot be negative", "A limit cannot be negative")

# the money
if R.interest_for(1200000, 0, 6) != 0 or R.interest_for(1200000, 10, 6) != 60000:
    fail.append("no interest by default; a flat rate is the whole term's, worked out once")
schedule = R.repayment_schedule(1200000, 0, 6, "2026-10-31")
if len(schedule) != 6 or round(sum(row[1] for row in schedule), 2) != 1200000 \
        or [row[0].month for row in schedule] != [10, 11, 12, 1, 2, 3]:
    fail.append("six repayments, adding back to the whole, month by month over the year's end: %s" % (schedule,))
if [row[1] for row in R.repayment_schedule(100, 0, 3, "2026-10-31")] != [33.33, 33.33, 33.34]:
    fail.append("the rounding goes on the last repayment")
if round(sum(row[3] for row in R.repayment_schedule(1200000, 10, 6, "2026-10-31")), 2) != 1260000:
    fail.append("principal and interest together add back to what is owed")
if R.monthly_instalment(1200000, 0, 6) != 200000 or R.repayment_schedule(0, 0, 6, "2026-10-31") != []:
    fail.append("the monthly instalment is the first repayment; nothing is recovered from nothing")
drawn = R.spread(500000, 0, 4, "2027-01-30", 30)
if [(str(row[0]), row[3]) for row in drawn] != [("2027-01-30", 125000), ("2027-02-28", 125000),
                                                ("2027-03-30", 125000), ("2027-04-30", 125000)]:
    fail.append("drawn again, the months keep the loan's own day, February or not: %s" % drawn)
if str(R.resume_from("2026-12-30", "2027-02-10", 30)) != "2027-02-28" \
        or str(R.resume_from("2026-12-30", "2026-11-05", 30)) != "2027-01-30" \
        or str(R.resume_from("2027-01-30", "2027-02-10", 30)) != "2027-02-28":
    fail.append("a schedule drawn again picks up after the last month, never in a month gone by")
if str(R.on_day("2027-02-10", 31)) != "2027-02-28" or str(R.on_day("2027-03-10", None)) != "2027-03-10":
    fail.append("the loan's day in a short month is its last")
if str(R.resume_from("2027-02-28", "2027-03-01", 30)) != "2027-03-30":
    fail.append("after a short month the schedule is back on the loan's own day")
A = load("advance_rules")
for offset in range(0, 800):
    day = datetime.date(2026, 1, 1) + datetime.timedelta(days=offset)
    if R.period_close(day) != A.payroll_period(day)[1]:
        fail.append("the loan's payroll period closes where the advance's does: not on %s" % day)
        break
for asked, paid, first in (("2026-09-21", None, "2026-10-25"), ("2026-09-26", None, "2026-11-25"),
                           ("2026-12-20", None, "2027-01-25"), ("2026-09-21", "2026-10-25", "2026-11-25"),
                           ("2026-09-21", "2026-10-31", "2026-11-25"), ("2026-09-21", "2026-08-25", "2026-10-25")):
    if str(R.first_month(asked, paid)) != first:
        fail.append("a request of %s, paid through %s, starts on %s, not %s" % (asked, paid, first,
                                                                                R.first_month(asked, paid)))
rows = [{"principal": 200000, "interest": 10000, "recovered": 1}, {"principal": 200000, "interest": 10000,
                                                                     "recovered": 0}]
if R.left(1200000, 60000, rows) != (1000000, 50000):
    fail.append("what is left is what the lines recovered did not take")
if R.split(300000, 750000, 0) != (300000, 0) or R.split(105000, 1000000, 50000) != (100000, 5000) \
        or R.split(2000000, 750000, 0) != (750000, 0):
    fail.append("a payment is split in proportion to what is left of each, never more than is left")
if R.outstanding(1200000, 400000) != 800000:
    fail.append("what is outstanding is what was not yet recovered")
for args, status in (((1, 1200000, 1200000), R.REPAID), ((1, 1200000, 400000), R.RUNNING),
                     ((1, 1200000, 0, True), R.WRITTEN_OFF), ((0, 1200000, 0), R.DRAFT),
                     ((2, 1200000, 0), R.CANCELLED), ((1, 1200000, 0, False, "Rejected"), R.REJECTED),
                     ((0, 1200000, 0, False, "Rejected"), R.REJECTED)):
    if R.loan_status(*args) != status:
        fail.append("a loan %s is %s, not %s" % (args, status, R.loan_status(*args)))

consent = {"liability": "Staff loan", "amount": 1200000, "instalments": 6, "effective_from": "2026-10-31",
           "consent": 1}
expect("a consent that stands (LPL/HR/39)", R.consent_errors(consent))
expect("no liability", R.consent_errors(dict(consent, liability="")), "Liability")
expect("no amount", R.consent_errors(dict(consent, amount=0)), "how much is deducted")
expect("no instalments", R.consent_errors(dict(consent, instalments=0)), "equal instalments")
expect("no date", R.consent_errors(dict(consent, effective_from=None)), "from when")
expect("not consented", R.consent_errors(dict(consent, consent=0)), "employee consents")
expect("paid out and consented, it runs", R.run_errors(dict(consent, paid="2026-10-01")))
expect("not paid out, it does not", R.run_errors(consent), "Record Payment")

terms = {"amount": 2000000, "approved_amount": 1200000, "instalments": 6, "first_repayment": "2026-10-31", "rate": 0}
expect("terms that stand", R.terms_errors(terms))
expect("lending more than was asked for", R.terms_errors(dict(terms, approved_amount=3000000)),
       "only UGX 2,000,000 was asked for")
expect("no amount settled", R.terms_errors(dict(terms, approved_amount=0)), "amount actually being lent")
expect("no months", R.terms_errors(dict(terms, instalments=0)), "how many months")
expect("more months than the kind of loan allows", R.terms_errors(dict(terms, instalments=13, max_instalments=12)),
       "at most 12 month(s)")
expect("no first repayment", R.terms_errors(dict(terms, first_repayment=None)), "which month")
expect("a first repayment in a month already paid", R.terms_errors(dict(terms, paid_through="2026-10-31")),
       "already paid up to 31 Oct 2026")
expect("one after it", R.terms_errors(dict(terms, first_repayment="2026-11-30", paid_through="2026-10-31")))
capped = dict(terms, amount=900000, approved_amount=900000, rate=10, gross_pay=900000, max_share=25)
expect("terms within the cap on the instalment, the interest counted", R.terms_errors(capped))
expect("terms over it", R.terms_errors(dict(capped, instalments=3)), "more than 25% of the gross pay")
expect("over it only by the interest", R.terms_errors(dict(capped, instalments=4)), "more than 25% of the gross pay")

lines = [{"payroll_date": "2027-01-30", "recovered": 0}, {"payroll_date": "2027-02-28", "recovered": 0},
         {"payroll_date": "2027-01-30", "recovered": 1}, {"payroll_date": "2026-12-30", "recovered": 0,
                                                          "missed_told": 1}]
if [row["payroll_date"] for row in R.missed(lines, "2027-02-10", 5)] != ["2027-01-30"] \
        or R.missed(lines, "2027-02-03", 5):
    fail.append("a month is missed some days after it, not taken and not yet told")
print("the rules: who qualifies as Luuka set it, the schedule, the terms, the consent, the payment, a missed month")

# ── 2. The DocTypes ───────────────────────────────────────────────────
if upstream_doctype("Loan"):
    fail.append("the lending app is installed after all: build the staff loan on its Loan instead")
loan = fields_of(doctype("Employee Loan"))
repayment = fields_of(doctype("Loan Repayment"))
settings = fields_of(doctype("Loan Settings"))
for name, have, wanted in (
    ("Employee Loan", loan, ("employee", "loan_amount", "purpose", "gross_pay", "limit", "outstanding_before",
                             "qualifies", "eligibility_remarks", "approved_amount", "interest_rate", "instalments",
                             "first_repayment", "total_interest", "monthly_instalment", "repayments",
                             "recovered_amount", "outstanding", "written_off", "written_off_amount", "written_off_on",
                             "write_off_entry", "written_off_months", "liability", "extent_of_deduction",
                             "effective_from", "consent", "consent_by", "consent_on", "witnessed_by",
                             "disbursed_on", "disbursement_reference", "disbursement_entry", "hod_by", "ed_by",
                             "gm_by", "accounts_by", "return_remarks", "approval_status", "status",
                             "recovery_component")),
    ("Loan Repayment", repayment, ("payroll_date", "principal", "interest", "total", "additional_salary",
                                   "recovered", "reference_type", "reference_name", "months_left", "missed_told",
                                   "remarks")),
    ("Loan Settings", settings, tuple(R.DEFAULTS) + ("loan_account",)),
):
    if not have:
        fail.append("%s is not there" % name)
    for fieldname in wanted:
        if have and fieldname not in have:
            fail.append("%s has no %s, which the loan process asks for" % (name, fieldname))
if not doctype("Loan Settings").get("issingle"):
    fail.append("Loan Settings are one set for the site")
for fieldname in ("gross_pay", "limit", "outstanding_before", "qualifies", "total_interest", "monthly_instalment",
                  "recovered_amount", "outstanding", "approval_status", "status", "disbursed_on",
                  "disbursement_reference", "disbursement_entry", "written_off", "written_off_amount",
                  "written_off_on", "write_off_entry", "witnessed_by", "consent_by", "consent_on"):
    if not (loan.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Loan.%s is worked out or booked, not typed" % fieldname)
for fieldname in ("approved_amount", "interest_rate", "first_repayment", "recovery_component"):
    if "Pending Accounts" not in (loan.get(fieldname) or {}).get("read_only_depends_on", ""):
        fail.append("Employee Loan.%s is Accounts' to set, while the loan is with them" % fieldname)
if not (loan.get("repayments") or {}).get("read_only"):
    fail.append("the schedule is drawn by the system: nobody adds a row by hand")
for fieldname in ("loan_type", "loan_amount", "instalments"):
    if "'Draft'" not in (loan.get(fieldname) or {}).get("read_only_depends_on", ""):
        fail.append("Employee Loan.%s is the employee's while the request is a draft" % fieldname)
if "Pending Accounts" not in (loan.get("instalments") or {}).get("read_only_depends_on", ""):
    fail.append("the months are Accounts' to settle at their desk")
if "30,000,000" in (loan.get("loan_type") or {}).get("description", ""):
    fail.append("the car loan's ceiling is Luuka's to set: the hint cannot name a figure")
if (loan.get("approval_status") or {}).get("fieldtype") != "Data":
    fail.append("a desk set up in the Workflow may be called anything: the approval status is text")
if (loan.get("status") or {}).get("options", "").split("\n") != list(R.STATUSES):
    fail.append("Employee Loan.status must offer exactly the loan's own lifecycle")
if (loan.get("disbursement_entry") or {}).get("options") != "Journal Entry" \
        or (loan.get("write_off_entry") or {}).get("options") != "Journal Entry":
    fail.append("the payment and the write-off are Journal Entries")
if not doctype("Employee Loan").get("is_submittable"):
    fail.append("a running loan is a submitted document")
employee_perm = next((perm for perm in doctype("Employee Loan").get("permissions", []) if perm["role"] == "Employee"), {})
if employee_perm.get("submit"):
    fail.append("an employee does not submit a loan: HR or the Payroll Officer run it")
if not employee_perm.get("report"):
    fail.append("an employee reads their own Loan Statement")
for fieldname in ("total", "additional_salary", "recovered", "reference_name", "months_left", "missed_told"):
    if not (repayment.get(fieldname) or {}).get("read_only"):
        fail.append("Loan Repayment.%s is worked out, not typed" % fieldname)
journal = {row["fieldname"]: row for row in CUSTOM if row.get("dt") == "Journal Entry"}
if (journal.get("custom_employee_loan") or {}).get("options") != "Employee Loan" \
        or set((journal.get("custom_loan_purpose") or {}).get("options", "").split("\n")) != {"", "Payment",
                                                                                         "Repayment", "Write Off"}:
    fail.append("a Journal Entry knows the loan it pays out, repays or writes off")
print("the loan, its schedule, its settings, and the Journal Entry that carries its money")

# ── 3. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "loans.py")
je_fields = set(fields_of(upstream_doctype("Journal Entry"))) | set(journal)
known = (set(loan) | set(repayment) | set(settings) | je_fields
         | {"workflow_state", "docstatus", "name", "employee", "company", "doctype"})
for fieldname in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r"doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "flags", "get_doc_before_save", "check_permission", "insert",
                     "submit", "cancel", "save", "is_new", "update", "as_dict"):
        continue
    if fieldname not in known:
        fail.append("loans.py reads or writes %s, which the loan, its schedule or its entry has not got" % fieldname)
for needle, why in (
    ("rules.eligibility_errors(", "who may take a loan is judged by the rules"),
    ("rules.repayment_schedule(", "the schedule is worked out by them"),
    ("rules.run_errors(", "LPL/HR/39 and the payment are judged by them before the loan runs"),
    ("rules.terms_errors(", "and so are the terms Accounts settle"),
    ("rules.loan_status(", "and where the loan stands"),
    ("Additional Salary", "test case 5: the payroll takes the deduction, nobody keeps a list"),
    ("Salary Detail", "and what it really took is read back"),
):
    if needle not in glue:
        fail.append("loans.py: %s (%r not found)" % (why, needle))
if '"status": rules.RUNNING' not in body(glue, "_owed_elsewhere"):
    fail.append("only a loan running now is owed: a refusal, a cancelled loan or one written off owes nothing")
if "approval.is_pending(" not in body(glue, "_waiting_elsewhere"):
    fail.append("a request waiting at any desk, whatever the desk is called, stands in the way of another")
if 'doc.get("status") != rules.RUNNING' not in body(glue, "loan_on_submit"):
    fail.append("a refusal is submitted too, and takes nothing from the payroll")
step = body(glue, "_check_step")
for needle, why in (
    ("approval.is_pending(new_state)", "leaving the request for any desk, the request is judged"),
    ("_terms_changed(doc, before)", "the terms are Accounts' to set"),
    ("doc.witnessed_by = frappe.session.user", "whoever runs the loan witnesses the consent"),
    ("doc.consent_by, doc.consent_on = frappe.session.user, today()", "the consent is stamped by who gives it"),
    ("_tell_back(doc, new_state, old_state)", "the employee is told a request is returned or refused, and why"),
    ("_tell_waiting(doc, new_state)", "whoever acts next is told"),
    ("_asked_changed(doc, before, old_state)", "the request as asked is the employee's while a draft"),
    ("new_state not in (approval.DRAFT, approval.REJECTED)", "a refusal keeps its reason"),
):
    if needle not in step:
        fail.append("the step: %s" % why)
if "_first_month(doc)" not in body(glue, "_build_schedule") or "doc.first_repayment = _first_month(doc)" not in step:
    fail.append("a request shows its schedule on what was asked; Accounts start from its first month")
for name in ("_tell_due", "_tell_missed"):
    if '"parent": ["in", running]' not in body(glue, name):
        fail.append("%s watches the running loans only: every request has a schedule drawn" % name)
if 'doc.interest_rate = s["default_rate"]' not in body(glue, "loan_validate"):
    fail.append("a request starts at the rate Luuka set")
if '"max_share": s["max_share_of_gross"]' not in body(glue, "_terms_facts"):
    fail.append("the terms Accounts settle are held to the cap on the instalment")
if "old_state != approval.PENDING_ACCOUNTS" not in body(glue, "_asked_changed"):
    fail.append("Accounts settle the months at their desk")
if "Workflow Transition" not in body(glue, "_roles_acting"):
    fail.append("whoever acts next is read off the Workflow as set up in the desk")
if "_cancel_untaken(doc)" not in body(glue, "loan_on_cancel") or "already recovered" not in body(glue, "loan_on_cancel"):
    fail.append("a loan part repaid is repaid or written off, not cancelled; one not yet taken loses its deductions")
if "_taken(name)" not in body(glue, "_cancel_untaken"):
    fail.append("a month a slip has taken is left as it is")
if "ensure_loan_account(company)" not in body(glue, "_component") or \
        '"Salary Component", DEFAULT_COMPONENT' not in body(glue, "ensure_loan_account"):
    fail.append("the repayment component gets its account, or the payroll stops on it")
if '@frappe.whitelist(methods=["POST"])\ndef make_journal(' not in glue:
    fail.append("the form drafts the Journal Entry, by POST only")
for name, needle in (("journal_on_submit", "apply_payment("), ("journal_on_submit", "_write_off("),
                     ("journal_on_cancel", "remove_payment("), ("journal_on_cancel", "_undo_write_off("),
                     ("journal_on_cancel", "Cancel the loan first")):
    if needle not in body(glue, name):
        fail.append("%s: %s" % (name, needle))
if "rules.PAID_DIRECTLY" not in body(glue, "journal_on_submit") or "rules.FINAL_SETTLEMENT" not in \
        body(glue, "settle_on_exit"):
    fail.append("a payment made directly, and one taken in the final settlement, say so on the schedule")
if "_renumber(name)" not in body(glue, "_draw_again"):
    fail.append("a schedule drawn again is numbered in date order")
if "_tell_missed()" not in body(glue, "daily") or "rules.missed(" not in body(glue, "_tell_missed"):
    fail.append("step 6: a month the payroll missed is told")
settlements_glue = read("hrms_addon", "hrms_addon", "settlements.py")
if "loans.settle_on_exit(doc)" not in body(settlements_glue, "settlement_on_submit") \
        or "loans.unsettle_on_exit(doc)" not in body(settlements_glue, "settlement_on_cancel"):
    fail.append("a leaver's final settlement settles their loans, and its cancelling unsettles them")
if '"status": "Running"' not in body(settlements_glue, "_loans"):
    fail.append("the final settlement counts only loans running now")
if '"status": "Running"' not in body(read("hrms_addon", "hrms_addon", "advances.py"), "_company_loan"):
    fail.append("an advance counts only company loans running now")
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_loan", "employee_loan.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        loans.loan_%s(self)" % (method, method) not in controller:
        fail.append("the Employee Loan controller must hand %s to loans.loan_%s" % (method, method))
if "loans.settings_validate(self)" not in read("hrms_addon", "hrms_addon", "doctype", "loan_settings",
                                               "loan_settings.py"):
    fail.append("Loan Settings are checked as they are saved")
form = read("hrms_addon", "hrms_addon", "doctype", "employee_loan", "employee_loan.js")
for purpose in ("Payment", "Repayment", "Write Off"):
    if 'ha_loan_journal(frm, "%s")' % purpose not in form:
        fail.append("the form offers the %s entry" % purpose)
if 'HA_LOANS + "make_journal"' not in form or "frappe.model.sync(" not in form:
    fail.append("the entry is drafted and opened for Accounts")
if "loan_amount(frm)" in form:
    fail.append("the form does not copy the amount asked into the amount lent: that is Accounts'")
print("glue: the rules followed, the payroll taking the deduction, the money booked, what was taken read back")

# ── 4. The workflow ───────────────────────────────────────────────────
if not W.DESK_MANAGED:
    fail.append("who approves a loan is set up in the desk: the workflow is made once and left to Luuka")
workflows = read("hrms_addon", "hrms_addon", "workflows.py")
if 'getattr(rules, "DESK_MANAGED", False)' not in body(workflows, "_ensure_workflow"):
    fail.append("a deploy never writes over a workflow set up in the desk")
walked, state, seen = [W.DRAFT], W.DRAFT, set()
while state not in seen:
    seen.add(state)
    forward = [t for t in W.TRANSITIONS if t["state"] == state and t["action"] in (W.SUBMIT, W.APPROVE, W.RUN)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != [W.DRAFT, W.PENDING_HOD, W.PENDING_ED, W.PENDING_ACCOUNTS, W.PENDING_CONSENT, W.RUNNING]:
    fail.append("a new site starts with the test script's chain, HOD then Executive Director: %s" % walked)
states = {row["state"] for row in W.STATES}
if set(W.FIXED_STATES) - states:
    fail.append("the states the loan's checks rest on are all in the workflow it starts with")
for state in (W.PENDING_HOD, W.PENDING_ED, W.PENDING_ACCOUNTS):
    if state not in W.STAMPS:
        fail.append("%s is stamped" % state)
if W.PENDING_CONSENT in W.STAMPS:
    fail.append("the consent is stamped by who gives it, not by whoever runs the loan")
if set(W.PENDING_STATES) - set(W.ROLE_WAITING):
    fail.append("every pending desk knows whose desk it is when the Workflow cannot say")
for state in W.PENDING_STATES:
    if not [t for t in W.TRANSITIONS if t["state"] == state and t["action"] == W.RETURN]:
        fail.append("%s must be able to send the loan back, which is the chart's \"Approved? No\"" % state)
expect("returned without saying why", W.step_errors(W.PENDING_ED, W.DRAFT, {}), "Return Remarks")
expect("returned from a desk set up in the desk", W.step_errors("Pending Section Head", W.DRAFT, {}),
       "Return Remarks")
expect("refused without saying why", W.step_errors(W.PENDING_ED, W.REJECTED, {}), "Executive Director's remarks")
expect("refused at a desk set up in the desk", W.step_errors("Pending Section Head", W.REJECTED, {}),
       "Return Remarks why the loan is refused")
expect("refused there with its reason", W.step_errors("Pending Section Head", W.REJECTED,
                                                      {"return_remarks": "Not now."}))
if not W.is_pending("Pending Section Head") or W.is_pending(W.DRAFT) or W.is_pending(W.RUNNING) \
        or W.is_pending(W.REJECTED) or W.is_pending(None):
    fail.append("any desk set up in the desk is pending; the request, the loan and the two ends are not")
if any(W.compute_stamps(W.PENDING_ED, W.DRAFT, "x", "2026-03-04", {"hod_by": "a"}).values()):
    fail.append("a return clears every signature")
if W.next_states(W.PENDING_ED, ("Employee",)):
    fail.append("nobody may act on a desk that is not theirs")
if W.next_states(W.PENDING_CONSENT, ("Employee",)) != [(W.RETURN, W.DRAFT)]:
    fail.append("the employee consents on the form, or sends the loan back; they never run it: %s"
                % W.next_states(W.PENDING_CONSENT, ("Employee",)))
if "Employee" in W.RUNNERS or [t for t in W.TRANSITIONS if t["action"] == W.RUN and t["allowed"] == "Employee"]:
    fail.append("chart step 4 is HR's or the Payroll Officer's")
if not [row for row in W.STATES if row["state"] == W.PENDING_CONSENT and row["allow_edit"] == W.HR_OFFICER]:
    fail.append("HR record a consent signed on paper")
print("the workflow: made once, set up in the desk, the checks resting on the states every set-up keeps")

# ── 5. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.loans.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the loan workflow and the component's account are seen to on every migrate")
if "ensure_loan_account()" not in body(glue, "setup_workflows_on_migrate"):
    fail.append("and the component's account with it")
if "hrms_addon.hrms_addon.loans.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("step 6 of the chart is a daily job")
events = (hooks.get("doc_events") or {}).get("Journal Entry") or {}
if "hrms_addon.hrms_addon.loans.journal_on_submit" not in handlers(events.get("on_submit")) \
        or "hrms_addon.hrms_addon.loans.journal_on_cancel" not in handlers(events.get("on_cancel")):
    fail.append("a Journal Entry paying out, repaying or writing off a loan moves the loan")
fixture_names = set(json.dumps(hooks.get("fixtures")).split('"'))
for name in ("Journal Entry-custom_employee_loan", "Journal Entry-custom_loan_purpose"):
    if name not in fixture_names:
        fail.append("the fixtures ship %s" % name)
patches = read("hrms_addon", "patches.txt")
for patch in ("loans_rejected_are_closed", "loans_employee_does_not_run"):
    if "hrms_addon.patches.v1_0.%s" % patch not in patches \
            or not os.path.exists(os.path.join(PACKAGE, "patches", "v1_0", patch + ".py")):
        fail.append("the %s patch is listed and there" % patch)
closing = read("hrms_addon", "patches", "v1_0", "loans_rejected_are_closed.py")
if "loans.close_rejected(doc)" not in closing or "log_error" not in closing:
    fail.append("refusals from before are closed, and any month already taken for one is reported")
running = read("hrms_addon", "patches", "v1_0", "loans_employee_does_not_run.py")
if 'row.allowed == "Employee"' not in running or "approval.HR_OFFICER" not in running:
    fail.append("on the site's workflow only the employee's Run goes and HR's consent comes")
for report, roles in (("loan_statement", {"Employee", "HR User", "Accounts User", "Payroll Officer"}),
                      ("loan_register", {"HR User", "Accounts User", "Payroll Officer"})):
    spec_path = os.path.join(APP, "report", report, report + ".json")
    if not os.path.exists(spec_path):
        fail.append("the %s report is not there" % report)
        continue
    spec = json.load(open(spec_path, encoding="utf-8"))
    if spec.get("ref_doctype") != "Employee Loan" or spec.get("report_type") != "Script Report" \
            or roles - {row["role"] for row in spec.get("roles", [])}:
        fail.append("the %s report reads the loans for %s" % (report, sorted(roles)))
statement = read("hrms_addon", "hrms_addon", "report", "loan_statement", "loan_statement.py")
if 'frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")' not in statement:
    fail.append("an employee's statement is of their own loans")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
for name in ("Employee Loan", "Loan Statement", "Loan Register", "Loan Settings"):
    if name not in carded or name not in sidebarred:
        fail.append("%s needs a way in" % name)
if "Loans" not in [page["label"] for page in navigation.PAGES]:
    fail.append("loan management has a page of its own, which this app makes: Frappe HR has none for lending")
print("wiring: the workflow and the account on migrate, the jobs, the entries' hooks, the patches, the reports")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LOAN CHECKS PASSED")
