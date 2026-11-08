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

# the kinds of loan a site starts with, as the patch makes them
TYPES = {row["loan_type_name"]: row for row in R.seed_types({})}
CAR, STUDY, OTHER, SACCO, BANK = (TYPES[name] for name in ("Car Loan", "Study Loan", "Other", "SACCO Loan",
                                                           "Bank Loan"))
if [(row["processed_by"], row.get("admin_only"), row.get("max_instalments")) for row in TYPES.values()] != [
        ("Company", 1, 12), ("Company", 1, 12), ("Company", 1, 12), ("SACCO", 0, 12), ("Bank", 0, 0)]:
    fail.append("the company's three kinds for the administration team, a SACCO loan and a bank loan for anybody, "
                "the bank's over as many months as it gives: %s" % TYPES)
if any(R.type_from(row)["share_of_net"] != 50 for row in TYPES.values()):
    fail.append("every kind holds the instalments to half the net pay (Luuka, 5 Nov 2026)")

ok = {"status": "Active", "date_of_joining": "2024-01-01", "today": "2026-09-21", "gross_pay": 1000000,
      "net_pay": 800000, "monthly": 333334, "amount": 2000000, "outstanding": 0, "instalments": 6,
      "purpose": "School fees", "category": "Administrative", "loan_type": "Other"}
expect("an employee who qualifies", R.eligibility_errors(ok, OTHER))
expect("someone who left", R.eligibility_errors(dict(ok, status="Left"), OTHER), "active employee")
expect("someone just joined", R.eligibility_errors(dict(ok, date_of_joining="2026-08-01"), OTHER),
       "month(s) of service")
expect("more than three months' gross", R.eligibility_errors(dict(ok, amount=5000000), OTHER), "most that may be lent")
expect("an earlier loan still owed", R.eligibility_errors(dict(ok, outstanding=120000), OTHER), "still owed")
expect("another request waiting", R.eligibility_errors(dict(ok, waiting="HR-LOAN-2026-00001"), OTHER),
       "HR-LOAN-2026-00001, is waiting for approval")
expect("recovered over too long", R.eligibility_errors(dict(ok, instalments=24), OTHER), "at most 12")
expect("no purpose", R.eligibility_errors(dict(ok, purpose=""), OTHER), "what the loan is for")
expect("nothing asked for", R.eligibility_errors(dict(ok, amount=0), OTHER), "how much")
expect("somebody from production", R.eligibility_errors(dict(ok, category="Non-Administrative"), OTHER),
       "administration team")
expect("somebody whose department says nothing", R.eligibility_errors(dict(ok, category=None), OTHER),
       "not marked Administrative")
car = dict(ok, loan_type="Car Loan", amount=30000000, instalments=12, monthly=2500000, net_pay=6000000)
expect("a car loan of UGX 30 million, whatever the gross", R.eligibility_errors(car, CAR))
expect("a car loan over it", R.eligibility_errors(dict(car, amount=30000001), CAR), "at most UGX 30,000,000")
study = dict(ok, loan_type="Study Loan", amount=9000000, instalments=12, monthly=750000, net_pay=1600000,
             fee_structure="/files/fees.pdf", course_fee=9000000)
expect("a study loan with its fees, over three months' gross", R.eligibility_errors(study, STUDY))
expect("a study loan with no fee structure", R.eligibility_errors(dict(study, fee_structure=None), STUDY),
       "fee structure")
expect("a study loan with no course fees typed", R.eligibility_errors(dict(study, course_fee=0), STUDY),
       "Enter the Course Fees")
expect("a study loan above its course fees", R.eligibility_errors(dict(study, amount=9000001), STUDY),
       "at most the course fees, UGX 9,000,000")
expect("a study loan below its course fees", R.eligibility_errors(dict(study, amount=4500000), STUDY))
expect("a loan Luuka do not offer", R.eligibility_errors(dict(ok, loan_type="Holiday Loan"), None),
       "Holiday Loan is not a kind of loan Luuka give")
expect("no kind chosen", R.eligibility_errors(dict(ok, loan_type=None), None), "Choose the kind of loan")
expect("a kind no longer given", R.eligibility_errors(ok, dict(OTHER, disabled=1)), "Other loans are no longer given")
expect("no pay on record, for a loan worked out from it", R.eligibility_errors(dict(ok, gross_pay=0), OTHER),
       "no gross pay on record")
expect("a car loan's ceiling needs no gross", R.eligibility_errors(dict(car, gross_pay=0), CAR))
if R.limit_for_type(CAR, 500000) != 30000000 or R.limit_for_type(STUDY, 500000) is not None \
        or R.limit_for_type(STUDY, 500000, course_fee=7200000) != 7200000 \
        or R.limit_for_type(OTHER, 500000) != 1500000 or R.limit_for_type(BANK, 500000) is not None:
    fail.append("the ceiling follows the type: 30 million, the course fees, three months' gross, or none for a bank")
if R.limit_for_type(dict(CAR, max_amount=20000000), 500000) != 20000000 \
        or R.limit_for_type(dict(OTHER, max_amount=1000000), 500000) != 1000000:
    fail.append("the ceiling the form shows is the one Luuka set on the type, the lower of the two where both are")

# what one earns: the instalments at most half the net pay (item 24)
expect("an instalment of half the net pay", R.eligibility_errors(dict(ok, monthly=400000), OTHER))
expect("one shilling over it", R.eligibility_errors(dict(ok, monthly=400001), OTHER),
       "more than 50% of the net pay of UGX 800,000")
expect("what goes to the banks taken off first", R.eligibility_errors(dict(ok, monthly=300001, committed=100000), OTHER),
       "once the UGX 100,000 a month going to bank loans is taken off")
expect("within it, the banks' part taken off", R.eligibility_errors(dict(ok, monthly=300000, committed=100000), OTHER))
expect("no salary slip to measure it against", R.eligibility_errors(dict(ok, net_pay=None), OTHER), "no salary slip")
expect("a type with no cap needs no slip", R.eligibility_errors(dict(ok, net_pay=None), dict(OTHER, share_of_net=0)))
expect("the share Luuka set on the type", R.eligibility_errors(dict(ok, monthly=300000), dict(OTHER, share_of_net=30)),
       "more than 30% of the net pay")
expect("nothing to measure before the months are set", R.eligibility_errors(dict(ok, monthly=0, net_pay=None), OTHER))

# the types: what the minutes' Loan Settings held becomes each type's own
seeded = {row["loan_type_name"]: row for row in R.seed_types({
    "car_loan_max": "20000000", "admin_only": 0, "min_months": 12, "other_allowed": 0, "car_max_instalments": 48,
    "other_max_instalments": 6, "other_months_of_gross": 1, "default_rate": "5"})}
if (seeded["Car Loan"]["max_amount"], seeded["Car Loan"]["max_instalments"], seeded["Other"]["disabled"],
        seeded["Other"]["months_of_gross"], seeded["Other"]["max_instalments"], seeded["Study Loan"]["course_fees"],
        seeded["Car Loan"]["admin_only"], seeded["Study Loan"]["min_months"], seeded["Car Loan"]["default_rate"],
        seeded["SACCO Loan"]["default_rate"], seeded["Bank Loan"]["min_months"]) != (
        20000000, 48, 1, 1, 6, 1, 0, 12, 5, 0, 12):
    fail.append("the types take what Loan Settings held for each kind, so nothing a site set is lost: %s" % seeded)
tight_car = seeded["Car Loan"]
expect("the car loan's ceiling from the settings", R.eligibility_errors(dict(car, amount=25000000), tight_car),
       "at most UGX 20,000,000")
expect("a car loan over four years when the settings allow it",
       R.eligibility_errors(dict(car, amount=18000000, instalments=48, monthly=375000), tight_car))
expect("everybody may borrow when the settings open it",
       R.eligibility_errors(dict(car, amount=18000000, category="Non-Administrative"), tight_car))
expect("the months of service the settings ask",
       R.eligibility_errors(dict(car, amount=100, date_of_joining="2026-01-01"), tight_car),
       "after 12 month(s) of service")
expect("no other loans when the settings said so", R.eligibility_errors(dict(ok, amount=1000000), seeded["Other"]),
       "Other loans are no longer given")
expect("a bank loan: anybody, the bank's months, no ceiling of Luuka's",
       R.eligibility_errors(dict(ok, loan_type="Bank Loan", amount=50000000, instalments=60, monthly=400000,
                                 category="Non-Administrative"), BANK))
expect("a SACCO loan's months", R.eligibility_errors(dict(ok, loan_type="SACCO Loan", instalments=13,
                                                          category="Non-Administrative"), SACCO),
       "A SACCO loan is recovered over at most 12 month(s)")
if R.max_instalments(tight_car) != 48 or R.max_instalments(OTHER) != 12 or R.max_instalments(BANK) != 0:
    fail.append("each kind of loan is recovered within its own months")
expect("types that stand", [error for row in TYPES.values() for error in R.type_errors(row)])
expect("a type that does not", R.type_errors(dict(OTHER, processed_by="A Friend", max_amount=-1, share_of_net=120,
                                                  default_rate=-1)),
       "Say who lends", "cannot be negative", "between 0 and 100%", "A rate cannot be negative")
expect("a loan the payroll takes back over no set months", R.type_errors(dict(SACCO, max_instalments=0)),
       "within a set number of months")
if R._kind("SACCO Loan") != "SACCO loan" or R._kind("Car Loan") != "car loan" or R._kind("Other") != "loan" \
        or R._kind("Emergency") != "emergency loan":
    fail.append("a type's name reads as a kind of loan in a sentence")

# the settings: what holds for every loan
if R.settings_from({}) != R.DEFAULTS or R.settings_from({"payroll_day": "28"})["payroll_day"] != 28 \
        or set(R.DEFAULTS) != {"payroll_day", "missed_grace_days"}:
    fail.append("Loan Settings keep the payroll day and the grace before a missed month, over the defaults")
expect("settings that stand", R.settings_errors(R.DEFAULTS))
expect("settings that do not", R.settings_errors(dict(R.DEFAULTS, payroll_day=40, missed_grace_days=-1)),
       "1 to 31", "cannot be negative")

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
if R.DEFAULTS["payroll_day"] != 26:
    fail.append("Luuka process the payroll on the 26th: each repayment falls on it")
for asked, paid, first in (("2026-09-21", None, "2026-10-26"), ("2026-09-26", None, "2026-10-26"),
                           ("2026-12-20", None, "2027-01-26"), ("2026-09-21", "2026-10-25", "2026-10-26"),
                           ("2026-09-21", "2026-10-31", "2026-11-26"), ("2026-09-21", "2026-11-30", "2026-12-26"),
                           ("2026-09-21", "2026-08-25", "2026-10-26")):
    if str(R.first_month(asked, paid)) != first:
        fail.append("a request of %s, paid through %s, starts on %s, not %s" % (asked, paid, first,
                                                                                R.first_month(asked, paid)))
if str(R.first_month("2026-09-21", None, 28)) != "2026-10-28" or str(R.first_month("2027-01-10", None, 31)) \
        != "2027-02-28":
    fail.append("a request starts on the payroll day Luuka set, the month's last where it has fewer days")
expect("a payroll day that is not a day of the month", R.settings_errors(dict(R.DEFAULTS, payroll_day=32)),
       "day of the month")
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
expect("no amount", R.consent_errors(dict(consent, amount=0)), "amount lent")
expect("no instalments", R.consent_errors(dict(consent, instalments=0)), "how many months")
expect("no date", R.consent_errors(dict(consent, effective_from=None)), "first repayment")
expect("not consented", R.consent_errors(dict(consent, consent=0)), "has not consented")
expect("paid out and consented, it runs", R.run_errors(dict(consent, paid="2026-10-01")))
expect("not paid out, it does not", R.run_errors(consent), "Record Payment")
recorded = {"processed_by": "Bank", "bank": "Stanbic Bank", "account_no": "9030001234567", "amount": 20000000,
            "instalments": 36, "monthly": 720000, "first_repayment": "2026-12-15"}
expect("a bank loan put on record: no consent, no payment", R.run_errors(recorded))
expect("a bank loan with nothing of the bank's", R.run_errors({"processed_by": "Bank"}), "which bank",
       "account at that bank", "amount the bank lends", "how many months", "monthly instalment", "first repayment")
if str(R.runs_until("2026-12-15", 36)) != "2029-11-15" or R.runs_until("2026-12-15", 0) is not None \
        or R.runs_until(None, 12) is not None:
    fail.append("a bank loan runs until its last instalment's month")
if R.bank_loan_ended("2029-11-15", "2029-11-15") or not R.bank_loan_ended("2029-11-15", "2029-11-16") \
        or R.bank_loan_ended(None, "2030-01-01"):
    fail.append("a bank loan ends the day after its last instalment, not before")
if [message for message in R.run_errors({}) if "LPL/" in message or "(" in message]:
    fail.append("what stops a loan running is said in plain words, not form numbers: %s" % R.run_errors({}))

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
capped = dict(terms, monthly=225000, net_pay=900000, share=25)
expect("terms within the cap on the instalment", R.terms_errors(capped))
expect("terms over it", R.terms_errors(dict(capped, monthly=225001)), "more than 25% of the net pay")
expect("over it once the banks' part is off", R.terms_errors(dict(capped, monthly=200000, committed=25001)),
       "going to bank loans")
expect("a bank's first month, whatever the payroll has paid",
       R.terms_errors(dict(terms, processed_by="Bank", paid_through="2026-11-30")))

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
                             "recovery_component", "processed_by", "lent_up_to_fees", "net_pay", "bank_instalments",
                             "bank_name", "bank_branch", "bank_account_no", "runs_until")),
    ("Loan Repayment", repayment, ("payroll_date", "principal", "interest", "total", "additional_salary",
                                   "recovered", "reference_type", "reference_name", "months_left", "missed_told",
                                   "remarks")),
    ("Loan Settings", settings, tuple(R.DEFAULTS) + ("loan_account",)),
    ("Employee Loan Type", fields_of(doctype("Employee Loan Type")),
     tuple(R.TYPE_DEFAULTS) + ("loan_type_name", "component", "description")),
):
    if not have:
        fail.append("%s is not there" % name)
    for fieldname in wanted:
        if have and fieldname not in have:
            fail.append("%s has no %s, which the loan process asks for" % (name, fieldname))
fee = loan.get("course_fee") or {}
if fee.get("fieldtype") != "Currency" or fee.get("depends_on") != "eval:doc.lent_up_to_fees" \
        or fee.get("mandatory_depends_on") != "eval:doc.lent_up_to_fees" \
        or fee.get("read_only_depends_on") != (loan.get("loan_amount") or {}).get("read_only_depends_on"):
    fail.append("a study loan's Course Fees are asked for with it, and locked with the amount once it leaves Draft")
loans_source = read("hrms_addon", "hrms_addon", "loans.py")
if '"course_fee"' not in loans_source.split("ASKED = ")[1].split(chr(10))[0] \
        or '"course_fee": doc.get("course_fee")' not in body(loans_source, "_facts") \
        or 'course_fee=doc.get("course_fee")' not in body(loans_source, "_fill_money"):
    fail.append("the Course Fees reach the eligibility check and the Maximum Loan Amount, and cannot change after Draft")
if not doctype("Loan Settings").get("issingle"):
    fail.append("Loan Settings are one set for the site")
for key, value in R.DEFAULTS.items():
    if float((settings.get(key) or {}).get("default") or 0) != float(value):
        fail.append("Loan Settings.%s starts where the rules do, at %s" % (key, value))
for fieldname in ("gross_pay", "limit", "outstanding_before", "qualifies", "total_interest", "net_pay",
                  "bank_instalments", "recovered_amount", "outstanding", "approval_status", "status", "disbursed_on",
                  "disbursement_reference", "disbursement_entry", "written_off", "written_off_amount",
                  "written_off_on", "write_off_entry", "witnessed_by", "consent_by", "consent_on", "processed_by",
                  "runs_until"):
    if not (loan.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Loan.%s is worked out or booked, not typed" % fieldname)
# the instalment is worked out, but for a bank's, which Accounts type from its offer
if (loan.get("monthly_instalment") or {}).get("read_only_depends_on") != "eval:doc.processed_by!='Bank'":
    fail.append("Employee Loan.monthly_instalment is worked out, but for a bank loan's")
for fieldname in ("approved_amount", "interest_rate", "first_repayment", "recovery_component"):
    if "Pending Accounts" not in (loan.get(fieldname) or {}).get("read_only_depends_on", ""):
        fail.append("Employee Loan.%s is Accounts' to set, while the loan is with them" % fieldname)
if not (loan.get("effective_from") or {}).get("read_only"):
    fail.append("the consent starts on the first repayment: nobody types it")
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
known = (set(loan) | set(repayment) | set(settings) | je_fields | set(fields_of(doctype("Employee Loan Type")))
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
    ("_terms_changed(doc, before, terms)", "the terms are Accounts' to set"),
    ("doc.witnessed_by = frappe.session.user", "whoever runs the loan witnesses the consent"),
    ("doc.consent_by, doc.consent_on = frappe.session.user, today()", "the consent is stamped by who gives it"),
    ("_tell_back(doc, new_state, old_state)", "the employee is told a request is returned or refused, and why"),
    ("_tell_waiting(doc, new_state)", "whoever acts next is told"),
    ("_asked_changed(doc, before, old_state)", "the request as asked is the employee's while a draft"),
    ("new_state not in (approval.DRAFT, approval.REJECTED)", "a refusal keeps its reason"),
):
    if needle not in step:
        fail.append("the step: %s" % why)
if "_start(doc, s)" not in body(glue, "_build_schedule") or "_first_month(doc, s)" not in body(glue, "_start") \
        or 'rules.on_day(first, s["payroll_day"])' not in body(glue, "_start") \
        or "doc.first_repayment = _first_month(doc, s)" not in step \
        or 'doc.first_repayment = rules.on_day(doc.first_repayment, s["payroll_day"])' not in step:
    fail.append("the schedule falls on the payroll day: on what was asked, then on Accounts' month")
if "@frappe.whitelist()\ndef preview_schedule(" not in glue \
        or "_build_schedule(loan, s)" not in body(glue, "preview_schedule") \
        or "_request_defaults(loan, s, t)" not in body(glue, "preview_schedule"):
    fail.append("the form draws the schedule as a save would")
for name in ("_tell_due", "_tell_missed"):
    if '"parent": ["in", running]' not in body(glue, name):
        fail.append("%s watches the running loans only: every request has a schedule drawn" % name)
if "_request_defaults(doc, s, t)" not in body(glue, "loan_validate") \
        or 'doc.interest_rate = rules.type_from(t or {})["default_rate"]' not in body(glue, "_request_defaults"):
    fail.append("a request starts at the rate Luuka set on its type")
if '"share": rules_of["share_of_net"]' not in body(glue, "_terms_facts") \
        or '"net_pay": doc.flags.get("net_pay")' not in body(glue, "_terms_facts"):
    fail.append("the terms Accounts settle are held to the type's share of the net pay")
if "old_state != approval.PENDING_ACCOUNTS" not in body(glue, "_asked_changed"):
    fail.append("Accounts settle the months at their desk")
if "Workflow Transition" not in body(glue, "_roles_acting"):
    fail.append("whoever acts next is read off the Workflow as set up in the desk")
if "_cancel_untaken(doc)" not in body(glue, "loan_on_cancel") or "already recovered" not in body(glue, "loan_on_cancel"):
    fail.append("a loan part repaid is repaid or written off, not cancelled; one not yet taken loses its deductions")
if "_taken(name)" not in body(glue, "_cancel_untaken"):
    fail.append("a month a slip has taken is left as it is")
if "ensure_loan_account(company)" not in body(glue, "_component") or \
        'frappe.get_doc("Salary Component", component_name)' not in body(glue, "ensure_loan_account"):
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
for handler in ("employee", "posting_date", "loan_amount", "instalments", "approved_amount", "interest_rate",
                "first_repayment"):
    if "\t%s: ha_loan_schedule," % handler not in form:
        fail.append("the form draws the schedule again when %s changes" % handler)
if 'HA_LOANS + "preview_schedule"' not in form:
    fail.append("the form asks the server for the schedule")
if 'set_value("liability"' in form:
    fail.append("the consent's liability is written by the server, from the terms, in one place")
if "_fill_consent(doc)" not in step or "doc.effective_from = doc.first_repayment" not in body(glue, "_fill_consent") \
        or 'startswith(_("Staff loan of "))' not in body(glue, "_fill_consent"):
    fail.append("the consent follows the terms: its liability, and the first repayment it starts on")
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

# ── 6. The kinds of loan, the accounts, the bank, the letter ─────────
kind = doctype("Employee Loan Type")
if (kind.get("autoname"), kind.get("naming_rule")) != ("field:loan_type_name", "By fieldname"):
    fail.append("a loan type is called by its name, which Luuka type")
kind_fields = {row["fieldname"]: row for row in kind.get("fields") or []}
if kind_fields.get("processed_by", {}).get("options") != "Company\nSACCO\nBank" \
        or kind_fields.get("component", {}).get("options") != "Salary Component":
    fail.append("a type says who lends, and which deduction takes it back")
readers = {row.get("role") for row in kind.get("permissions") or [] if row.get("read")}
writers = {row.get("role") for row in kind.get("permissions") or [] if row.get("write")}
if not {"Employee", "HR User", "Accounts User"} <= readers or "Employee" in writers or "HR Manager" not in writers:
    fail.append("anyone asking for a loan may pick a type; HR and Accounts managers keep the list: %s / %s"
                % (readers, writers))
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_loan_type", "employee_loan_type.py")
if "loans.type_validate(self)" not in controller:
    fail.append("a type is checked as it is saved")
loan_json = doctype("Employee Loan")
loan_fields = {row["fieldname"]: row for row in loan_json.get("fields") or []}
pick = loan_fields.get("loan_type") or {}
if (pick.get("fieldtype"), pick.get("options")) != ("Link", "Employee Loan Type") \
        or '"disabled","=",0' not in (pick.get("link_filters") or "").replace(" ", ""):
    fail.append("a loan picks its type from Luuka's list, the ones still given")
lender = loan_fields.get("processed_by") or {}
if lender.get("fetch_from") != "loan_type.processed_by" or not lender.get("read_only"):
    fail.append("who lends comes with the type, not typed on the loan")
if loan_fields.get("monthly_instalment", {}).get("read_only_depends_on") != "eval:doc.processed_by!='Bank'" \
        or loan_fields.get("monthly_instalment", {}).get("read_only"):
    fail.append("a bank loan's instalment is the bank's, typed; any other is worked out")
for name in ("schedule_section", "consent_section", "disbursement_section", "recovery_component"):
    if loan_fields.get(name, {}).get("depends_on") != "eval:doc.processed_by!='Bank'":
        fail.append("a bank loan shows no %s: nothing is paid out or deducted for it" % name)
for name in ("bank_name", "bank_account_no"):
    if loan_fields.get(name, {}).get("mandatory_depends_on") != "eval:doc.processed_by=='Bank'":
        fail.append("a bank loan names its %s, which the letter of undertaking gives" % name)
if set(R.LEGACY) & set(settings):
    fail.append("Loan Settings no longer hold a kind's figures: they are on its type")
patches = read("hrms_addon", "patches.txt")
patch = read("hrms_addon", "patches", "v1_0", "loan_types_from_settings.py")
if "hrms_addon.patches.v1_0.loan_types_from_settings" not in patches.split("[post_model_sync]")[-1] \
        or "rules.seed_types(stored)" not in patch or 'frappe.db.get_singles_dict("Loan Settings")' not in patch \
        or '"processed_by": ["is", "not set"]' not in patch or "frappe.db.exists(TYPE, values" not in patch:
    fail.append("the patch makes the types from Loan Settings after the model is synced, keeps any made, and marks "
                "every earlier loan the company's")
if "doc.processed_by = (t or {}).get(\"processed_by\") or rules.COMPANY" not in body(glue, "loan_validate"):
    fail.append("a loan's lender is its type's")
if "rules.eligibility_errors(_facts(doc), t)" not in body(glue, "_check_eligibility") \
        or '"net_pay": doc.flags.get("net_pay")' not in body(glue, "_facts") \
        or '"committed": doc.get("bank_instalments")' not in body(glue, "_facts"):
    fail.append("who may borrow is judged by the type's rules, the net pay and what goes to banks")
net = body(glue, "_net_pay")
if 'fields=["base_net_pay", "net_pay"], order_by="end_date desc"' not in net or "for docstatus in (1, 0):" not in net:
    fail.append("the net pay is the last slip's, in the company's currency, a draft's where none is submitted")
if "if lender == rules.BANK:" not in body(glue, "_owed_elsewhere") \
        or "(row.processed_by or rules.COMPANY) == lender" not in body(glue, "_owed_elsewhere"):
    fail.append("what is owed is weighed lender by lender, a loan made before the types the company's")
if "row.processed_by == rules.BANK" not in body(glue, "_bank_loans_running"):
    fail.append("the bank instalments are the bank loans' on record")
if "_is_bank(doc)" not in body(glue, "make_journal") or "account = account_for(doc)" not in body(glue, "make_journal"):
    fail.append("nothing is booked for a bank loan; any other is booked on its own account")
if "account = account_for(loan)" not in body(glue, "_on_loan_account"):
    fail.append("an entry is weighed on the loan's own account")
submit = body(glue, "loan_on_submit")
if "_mark_bank_loan(doc.employee)" not in submit or submit.index("_mark_bank_loan(") > submit.index("_make_deductions(doc)"):
    fail.append("a bank loan put on record marks the employee's Bank Loan, and makes no deduction")
if "_mark_bank_loan(doc.employee, exclude=doc.name, ended=doc)" not in body(glue, "loan_on_cancel"):
    fail.append("a bank loan cancelled lets go of the employee's Bank Loan")
marked = body(glue, "_mark_bank_loan")
for needle in ('"custom_has_bank_loan": 1', '"custom_has_bank_loan": 0', 'ended.get("runs_until")'):
    if needle not in marked:
        fail.append("the employee's Bank Loan follows the bank loans on record, and leaves one HR typed: %s" % needle)
if "row.processed_by == rules.BANK" not in body(glue, "_close_repaid") or "_end_bank_loans()" not in body(glue, "daily") \
        or "rules.bank_loan_ended(row.runs_until, today())" not in body(glue, "_end_bank_loans"):
    fail.append("a bank loan owes Luuka nothing all along: it ends with its last month, not at once")
if "or _is_bank(doc)" not in body(glue, "_outstanding") or "_is_bank(doc)" not in body(glue, "refresh_recovered"):
    fail.append("nothing is owed to Luuka on a bank loan, and nothing recovered")
if 'doc.set("repayments", [])' not in body(glue, "_build_schedule") or "return None" not in body(glue, "preview_schedule"):
    fail.append("a bank keeps its own schedule: the loan draws none")
if '"processed_by": _lender(doc)' not in body(glue, "_check_step") \
        or '"account_no": doc.get("bank_account_no")' not in body(glue, "_check_step") \
        or "and not bank" not in body(glue, "_check_step"):
    fail.append("a bank loan runs on the bank's details and terms, on the bank's own day")
if "_is_bank(doc)" not in body(glue, "_fill_consent") or "_is_bank(doc)" not in body(glue, "_tell_waiting"):
    fail.append("a bank loan asks no consent: HR are told to give the bank its letter")
accounts = body(glue, "ensure_loan_account")
for needle in ("for lender, (component_name, _abbr, _what) in COMPONENTS.items():", "loan_account(name, lender)",
               "row.account in _chosen_before(name)", "and not _money_out(name)"):
    if needle not in accounts:
        fail.append("each lender's deduction books to its own account, moved off Employee Advances only once "
                    "nothing paid out from there is owed: %s" % needle)
if '"Employee Loans"' not in glue.split("ACCOUNTS = ")[1].split(chr(10))[0] \
        or '"SACCO Loans"' not in glue.split("ACCOUNTS = ")[1].split(chr(10))[0]:
    fail.append("the company's loans sit on Employee Loans, the SACCO's on SACCO Loans (Luuka, 5 Nov 2026)")
own = body(glue, "_own_account")
if '"default_employee_advance_account"' not in body(glue, "_chosen_before"):
    fail.append("the app moves a deduction only off the accounts it chose itself, the advances or its own")
if '"root_type": "Asset"' not in own or '"Loans and Advances (Assets)", "Current Assets"' not in own \
        or '== "Asset"' not in own:
    fail.append("the loan accounts are asset accounts, made beside the advances or under the current assets")
if "doc.component = None" not in body(glue, "type_validate") or "_component(processed_by=doc.processed_by)" \
        not in body(glue, "type_validate"):
    fail.append("a bank's type has no deduction; any other gets its lender's")
for lender in ('"LR"', '"SLR"'):
    if lender not in glue.split("COMPONENTS = ")[1].split("ACCOUNTS = ")[0]:
        fail.append("each lender has its own deduction component: %s" % lender)
navigation = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if navigation.count('("Employee Loan Type", "Employee Loan Type", DOCTYPE') != 2:
    fail.append("the loan types are on the Loans page and in its sidebar")
register = read("hrms_addon", "hrms_addon", "report", "loan_register", "loan_register.js")
if 'options: "Employee Loan Type"' not in register:
    fail.append("the register filters by Luuka's own types")
form = read("hrms_addon", "hrms_addon", "doctype", "employee_loan", "employee_loan.js")
if 'const bank = frm.doc.processed_by === "Bank";' not in form or "!bank &&" not in form \
        or "if (!bank && frm.doc.docstatus === 1" not in form or '__("Letter of Undertaking")' not in form:
    fail.append("a bank loan's form has the letter, and no payment, repayment, write-off or recovery")

import importlib.util as _util  # noqa: E402

_spec = _util.spec_from_file_location("jinja_subset", os.path.join(REPO, "scripts", "jinja_subset.py"))
jinja_subset = _util.module_from_spec(_spec)
_spec.loader.exec_module(jinja_subset)
letter = json.loads(read("hrms_addon", "hrms_addon", "print_format", "letter_of_undertaking",
                         "letter_of_undertaking.json"))
if (letter.get("doc_type"), letter.get("print_format_type"), letter.get("standard"), letter.get("module"),
        letter.get("name")) != ("Employee Loan", "Jinja", "Yes", "HRMS Addon", "Letter of Undertaking"):
    fail.append("the Letter of Undertaking is a standard Jinja print of the Employee Loan")
html = letter.get("html") or ""
if not html.startswith("{{ print_control(doc) }}"):
    fail.append("the letter carries the control line every print does")
for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html)) - {"name"}):
    if fieldname not in loan_fields and fieldname not in ("company", "posting_date"):
        fail.append("the letter prints doc.%s, which the Employee Loan does not have" % fieldname)
signer = re.search(r'<p class="who">([^<]*)</p>\s*<p class="who">EXECUTIVE DIRECTOR</p>', html)
if not signer or not signer.group(1).strip().startswith("{{"):
    fail.append("the letter names its signer from Onboarding Settings, never by a name typed into it")
try:
    render = jinja_subset.compile_template(html)
    employee = jinja_subset.wrap({"employee_name": "Amina <Nakato>", "employee_number": "LPL1834",
                                  "designation": "Accountant", "department": "Finance", "branch": "Kawempe",
                                  "date_of_joining": "2019-03-01"})
    utils = type("utils", (), {"format_date": staticmethod(lambda value: str(value))})
    db = type("db", (), {"get_value": staticmethod(lambda doctype, name, field: "Ed " + name),
                         "get_single_value": staticmethod(lambda doctype, field: "HR-EMP-0001"
                                                          if field == "executive_director" else None)})
    frappe_stub = type("frappe", (), {"utils": utils, "db": db,
                                      "get_doc": staticmethod(lambda doctype, name: employee)})
    sample = {"employee": "HR-EMP-0002", "company": "Luuka Test Ltd", "processed_by": "Bank",
              "bank_name": "Stanbic Bank", "bank_branch": "Kawempe", "bank_account_no": "9030001234567",
              "gross_pay": 2500000, "net_pay": 1850000, "approved_amount": 20000000, "loan_amount": 25000000,
              "instalments": 36, "monthly_instalment": 720000, "first_repayment": "2026-12-15",
              "accounts_on": "2026-11-20", "posting_date": "2026-11-08"}
    page = render({"doc": jinja_subset.wrap(sample), "frappe": frappe_stub})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S)))
    for needle in ("2026-11-20", "The Branch Manager Stanbic Bank Kawempe Branch",
                   "LETTER OF UNDERTAKING FOR AMINA &LT;NAKATO&GT;, STAFF NO. LPL1834",
                   "employed by Luuka Test Ltd since 2019-03-01", "our Accountant in Finance at the Kawempe plant",
                   "UGX 2,500,000 gross and UGX 1,850,000 net", "lend the employee UGX 20,000,000",
                   "over 36 months at UGX 720,000 a month", "falling due on 2026-12-15",
                   "into account number 9030001234567 held with you", "without your written consent",
                   "within seven days if the employee leaves", "does not make Luuka Test Ltd a guarantor",
                   "ED HR-EMP-0001 EXECUTIVE DIRECTOR", "HUMAN RESOURCE MANAGER",
                   "I, Amina &lt;Nakato&gt;, agree to Luuka Test Ltd giving this undertaking"):
        if needle not in text:
            fail.append("the Letter of Undertaking should read %r: %s" % (needle, text))
    other = render({"doc": jinja_subset.wrap(dict(sample, processed_by="Company")), "frappe": frappe_stub})
    if "LETTER OF UNDERTAKING FOR" in other or "is for a loan from a bank" not in other:
        fail.append("the letter is for a bank loan only, and says so on any other")
except Exception as error:  # noqa: BLE001
    fail.append("the Letter of Undertaking does not compile or render: %s" % error)
print("the kinds of loan: Luuka's list, who lends, the accounts, the bank kept on record, its letter")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LOAN CHECKS PASSED")
