"""Verify the salary advance against Luuka's own rules, without a bench:

    python scripts/verify_salary_advance.py

The rules are in the minutes of 16 and 20 July 2026 (Human Resource,
Reward and Compensation): §4.9 for the salary advance, §4.4 for the
leave advance beside it. Every one of them is a setting on Advance
Settings, and advance_rules.DEFAULTS is what each is until Luuka changes it.

  1  the defaults are the minutes' own numbers, and the page agrees
  2  the day: the 15th, or the working day before; and the run a request joins
  3  the attendance: absences since the 26th, off-duty days not counted
  4  who qualifies, each rule with its own reason, each one a switch
  5  the amount: 40% of gross, the Per Meter standard rate, 60% for leave
  6  the glue reads the settings and watches the day
  7  the fields, the page, the patch and the way in
"""
import importlib.util
import datetime
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def expect(label, errors, needle=None):
    if needle is None:
        if errors:
            fail.append("%s: expected no reason, got %s" % (label, errors))
    elif not any(needle in error for error in errors):
        fail.append("%s: expected a reason containing %r, got %s" % (label, needle, errors))


V = load("advance_rules")
D = datetime.date
print("loaded advance_rules.py without Frappe")

# ── 1. The minutes' own numbers ───────────────────────────────────────
for key, value, why in (
    ("salary_percent", 40.0, "§4.9: the salary advance is 40% of gross salary"),
    ("per_meter_amount", 110000.0, "§4.9: a standard rate of UGX 110,000 for the Per Meter category"),
    ("salary_processing_day", 15, "§4.9: processed on the 15th of each month"),
    ("salary_move_before", 1, "§4.9: a weekend or public holiday moves it before that date"),
    ("salary_max_absent_days", 3, "§4.9: not absent for more than three days"),
    ("salary_off_duty_not_absent", 1, "§4.9: the Off-Duty Forms are checked against the absences"),
    ("salary_not_on_leave", 1, "§4.9: employees on leave are removed"),
    ("salary_no_bank_loan", 1, "§4.9: have no bank loan"),
    ("salary_regular_only", 1, "§4.9: applicable only to regular employees"),
    ("salary_min_months", 0, "the minutes set no service rule for the salary advance"),
    ("salary_instalments", 1, "it is recovered from the same month's pay"),
    ("leave_percent", 60.0, "§4.4: the Accounts Manager calculates 60% of gross salary"),
    ("leave_per_meter_months", 2, "§4.4: the average of the previous two months' gross"),
    ("leave_more_than_days", 19, "§4.4: those taking more than 19 accrued days of leave"),
    ("leave_no_loans", 1, "§4.4: no existing bank or company loans"),
    ("special_percent", 50.0, "LPL/HR/21: no more than half a month's gross"),
    ("special_max_instalments", 3, "LPL/HR/21: recovered in at most three months"),
):
    if V.DEFAULTS.get(key) != value:
        fail.append("%s should default to %r — %s (it is %r)" % (key, value, why, V.DEFAULTS.get(key)))

spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", "advance_settings", "advance_settings.json"))
page = {f["fieldname"]: f for f in spec["fields"]}
if not spec.get("issingle"):
    fail.append("Advance Settings is one page for the company, a Single")
for key, value in V.DEFAULTS.items():
    if key not in page:
        fail.append("Advance Settings has no field for %s, so it cannot be changed without a developer" % key)
        continue
    stated = page[key].get("default")
    if stated is None or float(stated) != float(value):
        fail.append("Advance Settings shows %s as %r but the rules default it to %r — the page and "
                    "the rules would disagree until somebody saved it" % (key, stated, value))
extra = sorted(fn for fn, f in page.items()
               if f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")
               and fn not in V.DEFAULTS and fn != "not_regular_types")
if extra:
    fail.append("Advance Settings has fields the rules never read: %s" % extra)
if page.get("not_regular_types", {}).get("fieldtype") != "Table MultiSelect":
    fail.append("who is not regular is a list of Employment Types, picked on the page")
print("defaults: the minutes' own numbers, and the page shows the same ones")

# a stored nought is a nought
merged = V.settings_from({"salary_max_absent_days": "0", "salary_percent": "35", "salary_move_before": "0"})
if merged["salary_max_absent_days"] != 0:
    fail.append("a saved nought must stay nought: 'no absence at all' is a real policy")
if merged["salary_percent"] != 35.0 or merged["salary_move_before"] != 0:
    fail.append("what was saved stands over the default")
if V.settings_from({})["salary_percent"] != 40.0:
    fail.append("and anything never saved takes the minutes' number")
expect("a percentage of nought", V.settings_errors({"salary_percent": 0}), "more than 0")
expect("a processing day that some months do not have", V.settings_errors({"salary_processing_day": 31}),
       "every month")
expect("settings as they come", V.settings_errors({}))

# ── 2. The day ────────────────────────────────────────────────────────
for year, month, closed, expected, why in (
    (2026, 9, (), D(2026, 9, 15), "the 15th of September 2026 is a Tuesday"),
    (2026, 8, (), D(2026, 8, 14), "a Saturday 15th moves to the Friday"),
    (2026, 11, (), D(2026, 11, 13), "a Sunday 15th moves past the Saturday to the Friday"),
    (2026, 10, ("2026-10-15",), D(2026, 10, 14), "a public holiday on the 15th moves it back a day"),
    (2026, 10, ("2026-10-15", "2026-10-14"), D(2026, 10, 13), "and keeps going until a working day"),
):
    got = V.processing_date(year, month, None, closed)
    if got != expected:
        fail.append("processing_date(%d-%02d) is %s, expected %s: %s" % (year, month, got, expected, why))
if V.processing_date(2026, 8, {"salary_move_before": 0}) != D(2026, 8, 15):
    fail.append("with the move switched off, the day is the day")
if V.processing_date(2026, 9, {"salary_processing_day": 10}) != D(2026, 9, 10):
    fail.append("the day is a setting")

if V.request_deadline(D(2026, 9, 15)) != D(2026, 9, 12):
    fail.append("requests close three days before the run by default")
if V.run_for("2026-09-12") != D(2026, 9, 15):
    fail.append("a request on the closing day is in time")
if V.run_for("2026-09-13") != D(2026, 10, 15):
    fail.append("a late request waits for the next run rather than being turned away")
if V.run_for("2026-12-20") != D(2027, 1, 15):
    fail.append("and December's late ones join January's")
if V.run_for("2026-09-13", {"salary_request_days_before": 0}) != D(2026, 9, 15):
    fail.append("how early requests close is a setting")

if V.payroll_period("2026-09-15") != (D(2026, 8, 26), D(2026, 9, 25)):
    fail.append("the 15th of September is in the period that runs 26 August to 25 September")
if V.payroll_period("2026-09-26") != (D(2026, 9, 26), D(2026, 10, 25)):
    fail.append("from the 26th the days belong to the next period")
if V.payroll_period("2026-01-15")[0] != D(2025, 12, 26):
    fail.append("January's period opens in December")

if V.held_until("2026-09-15", "2026-09-14") is None:
    fail.append("a salary advance does not go to Finance before the day it is processed")
if V.held_until("2026-09-15", "2026-09-15") is not None:
    fail.append("but it does on the day")
if V.held_until("2026-09-15", "2026-09-14", {"salary_hold_until_processing": 0}) is not None:
    fail.append("and holding it is a setting")

# the request: one application, paid month after month while it is active
expect("a request with no employee", V.request_errors({"first_month": "2026-09-01"}), "Select the employee")
expect("a request with no first month", V.request_errors({"employee": "E1"}), "month the advance starts")
expect("a request that ends before it starts", V.request_errors(
    {"employee": "E1", "first_month": "2026-10-01", "until_month": "2026-09-01"}), "before the first month")
expect("a request whose last month has passed", V.request_errors(
    {"employee": "E1", "first_month": "2026-07-01", "until_month": "2026-08-01", "today": "2026-09-08"}),
    "already passed")
expect("a request whose last month is this month", V.request_errors(
    {"employee": "E1", "first_month": "2026-09-01", "until_month": "2026-09-01", "today": "2026-09-08"}))
expect("a request for a negative amount", V.request_errors(
    {"employee": "E1", "first_month": "2026-09-01", "amount": -5}), "negative")
expect("a request with no last month runs until it is stopped", V.request_errors(
    {"employee": "E1", "first_month": "2026-09-01"}))
expect("a request for one month", V.request_errors(
    {"employee": "E1", "first_month": "2026-09-08", "until_month": "2026-09-01"}))
ACTIVE = {"status": V.REQUEST_ACTIVE, "approved_on": "2026-09-10", "first_month": "2026-09-01",
          "until_month": "2026-12-01"}
for request, on, joined, why in (
    (ACTIVE, "2026-09-15", True, "an active request approved in time is paid in its first month"),
    (ACTIVE, "2026-11-13", True, "and in the months after it, without applying again"),
    (ACTIVE, "2026-12-15", True, "up to and including its last month"),
    (dict(ACTIVE, until_month="2026-10-01"), "2026-11-13", False, "but not after its last month"),
    (dict(ACTIVE, first_month="2026-10-01"), "2026-09-15", False, "nor before its first"),
    (dict(ACTIVE, approved_on="2026-09-13"), "2026-09-15", False, "approved after requests close, it waits"),
    (dict(ACTIVE, approved_on="2026-09-13"), "2026-10-14", True, "for the next month"),
    (dict(ACTIVE, status=V.REQUEST_STOPPED), "2026-10-14", False, "a stopped request is not paid"),
    (dict(ACTIVE, status=V.REQUEST_ENDED), "2026-10-14", False, "nor an ended one"),
    (dict(ACTIVE, approved_on=None), "2026-09-15", False, "nor one never approved"),
    (dict(ACTIVE, until_month=None), "2027-06-15", True, "with no last month it carries on"),
):
    if V.joins_run(request, on)[0] is not joined:
        fail.append("joins_run: %s (%s)" % (why, V.joins_run(request, on)))
if "12 Sep 2026" not in (V.joins_run(dict(ACTIVE, approved_on="2026-09-13"), "2026-09-15")[1] or ""):
    fail.append("a late request says when requests closed")
if V.joins_run(dict(ACTIVE, approved_on="2026-09-13"), "2026-09-15",
               {"salary_request_days_before": 0})[0] is not True:
    fail.append("the closing day for requests is a setting")

# the amount on each line
for entitlement, requested, paid, why in (
    (400000, 0, 400000, "nothing in particular asked for: the full amount allowed"),
    (400000, 250000, 250000, "less asked for: what was asked"),
    (400000, 500000, 400000, "more asked for: no more than allowed"),
    (None, 250000, 0, "no gross pay on record: nothing paid"),
    (0, 250000, 0, "nothing allowed: nothing paid"),
):
    if V.line_amount(entitlement, requested) != paid:
        fail.append("line_amount: %s (%s)" % (why, V.line_amount(entitlement, requested)))

# what holds the run back
READY = {"processing_date": "2026-09-15", "today": "2026-09-15", "unconfirmed": [], "included": 2,
         "bank_account": "Stanbic - LPL", "payment_method": "Cheque", "reference_no": "004512",
         "reference_date": "2026-09-15"}
expect("a run ready to go", V.run_errors(READY))
expect("a run before its day", V.run_errors(dict(READY, today="2026-09-14")), "processed on 15 Sep 2026")
expect("a run with a plant not confirmed", V.run_errors(dict(READY, unconfirmed=["Kawempe"])), "Kawempe")
expect("a run paying nobody", V.run_errors(dict(READY, included=0)), "Nobody in this run")
expect("a run with no account to pay from", V.run_errors(dict(READY, bank_account=None)), "account")
expect("a run with no payment method", V.run_errors(dict(READY, payment_method=None)), "payment method")
expect("a cheque with no number", V.run_errors(dict(READY, reference_no=None)), "reference number")
expect("a transfer with no date", V.run_errors(dict(READY, payment_method="Bank Transfer",
                                                    reference_date=None)), "reference number")
expect("cash needs no reference", V.run_errors(dict(READY, payment_method="Cash", reference_no=None,
                                                    reference_date=None)))
print("the day: the 15th or the working day before, the run a request joins, and the hold")

# ── 3. The attendance ─────────────────────────────────────────────────
ABSENT = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
if V.days_absent(ABSENT, ["2026-09-02", "2026-09-04"]) != 3:
    fail.append("an approved off-duty day recorded as absent is not an absence (§4.9)")
if V.days_absent(ABSENT, ["2026-09-02"], {"salary_off_duty_not_absent": 0}) != 5:
    fail.append("and not counting them is a setting")
if V.days_absent(ABSENT + ["2026-09-01"]) != 5:
    fail.append("a day is counted once however many records say it")
print("attendance: absences since the 26th, approved off-duty days not held against anyone")

# ── 4. Who qualifies ──────────────────────────────────────────────────
OK = {"advance_type": "Salary Advance", "status": "Active", "employment_type": "Permanent",
      "pay_category": "Monthly", "date_of_joining": "2026-08-01", "gross_pay": 1000000, "amount": 400000,
      "outstanding": 0, "instalments": 1, "processing_date": "2026-09-15", "window_start": "2026-08-26",
      "days_absent": 3, "on_leave": None, "bank_loan": False}
S = V.settings_from({"not_regular_types": ["Casual"]})
expect("a regular employee three days absent, asking 40%", V.eligibility_errors(OK, S))
expect("nobody asks how long a salary advance applicant has served",
       V.eligibility_errors(dict(OK, date_of_joining="2026-09-01"), S))
for label, change, needle in (
    ("four days absent", {"days_absent": 4}, "no more than 3"),
    ("a casual", {"employment_type": "Casual"}, "regular employees"),
    ("on leave on the day", {"on_leave": "HR-LAP-0001"}, "On leave on 15 Sep 2026"),
    ("a bank loan", {"bank_loan": True}, "bank loan"),
    ("an earlier advance still owed", {"outstanding": 50000}, "still owed"),
    ("more than 40% of gross", {"amount": 400001}, "40% of a gross"),
    ("recovered over two months", {"instalments": 2}, "recovered in 1 month"),
    ("somebody who has left", {"status": "Left"}, "active employee"),
    ("nothing asked for", {"amount": 0}, "how much"),
):
    errors = V.eligibility_errors(dict(OK, **change), S)
    expect(label, errors, needle)
    if len(errors) != 1 and label != "nothing asked for":
        fail.append("%s must give its own one reason, not %s" % (label, errors))

# each rule is a switch, and a switched-off rule is silent
for label, change, switch in (
    ("four days absent", {"days_absent": 9}, {"salary_max_absent_days": 9}),
    ("a casual", {"employment_type": "Casual"}, {"salary_regular_only": 0}),
    ("on leave", {"on_leave": "HR-LAP-0001"}, {"salary_not_on_leave": 0}),
    ("a bank loan", {"bank_loan": True}, {"salary_no_bank_loan": 0}),
    ("an earlier advance", {"outstanding": 50000}, {"salary_no_outstanding": 0}),
):
    expect("%s, with the rule switched off" % label,
           V.eligibility_errors(dict(OK, **change), V.settings_from(dict(switch, not_regular_types=["Casual"]))))
expect("no absence allowed at all", V.eligibility_errors(dict(OK, days_absent=1),
                                                        V.settings_from({"salary_max_absent_days": "0"})),
       "no more than 0")

# the leave advance beside it (§4.4)
LEAVE = {"advance_type": "Leave Advance", "status": "Active", "employment_type": "Permanent",
         "pay_category": "Monthly", "gross_pay": 1000000, "amount": 600000, "outstanding": 0,
         "instalments": 1, "leave_days": 21, "bank_loan": False, "company_loan": 0}
expect("a regular employee taking 21 days, asking 60%", V.eligibility_errors(LEAVE, S))
expect("nineteen days of leave", V.eligibility_errors(dict(LEAVE, leave_days=19), S), "more than 19 days")
expect("a company loan still owed", V.eligibility_errors(dict(LEAVE, company_loan=200000), S), "company loan")
expect("a bank loan", V.eligibility_errors(dict(LEAVE, bank_loan=True), S), "bank loan")
expect("more than 60%", V.eligibility_errors(dict(LEAVE, amount=600001), S), "60% of a gross")
print("who qualifies: each of the minutes' conditions its own reason, and each one a switch")

# ── 5. The amount ─────────────────────────────────────────────────────
for args, expected, why in (
    (("Salary Advance", 1000000, "Monthly"), 400000.0, "40% of gross"),
    (("Salary Advance", 1000000, "Per Meter"), 110000.0, "the Per Meter standard rate, whatever the gross"),
    (("Salary Advance", 0, "Per Meter"), 110000.0, "even with no gross on record"),
    (("Salary Advance", 0, "Monthly"), None, "and nothing to work 40% of when there is no gross"),
    (("Leave Advance", 1000000, "Monthly"), 600000.0, "60% of gross for leave"),
    (("Special Advance", 1000000, "Monthly"), 500000.0, "half for the special advance"),
):
    if V.entitled(*args) != expected:
        fail.append("entitled%s is %r, expected %r: %s" % (args, V.entitled(*args), expected, why))
if V.entitled("Leave Advance", 1000000, "Per Meter", None, 800000) != 480000.0:
    fail.append("a Per Meter leave advance is 60% of the average of the last two months (§4.4)")
if V.entitled("Salary Advance", 1000000, "Per Meter", {"per_meter_amount": 0}) != 400000.0:
    fail.append("with no standard rate set, Per Meter staff get the percentage like anyone else")
print("the amount: 40% of gross, the Per Meter standard rate, 60% for leave, half for a special advance")

# ── 6. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "advances.py")


def body(name):
    if ("def %s(" % name) not in glue:
        fail.append("advances.py has no %s" % name)
        return ""
    return glue.split("def %s(" % name)[1].split("\ndef ")[0]


reading = body("settings")
if "get_singles_dict" not in reading or "rules.settings_from(" not in reading:
    fail.append("the settings are read from what was stored and merged over the minutes' numbers, "
                "so a stored nought stays a nought")
for constant in ("limit_for(", "DEFAULT_LIMIT_FRACTION", "MIN_MONTHS_SERVED", "MAX_INSTALMENTS"):
    if constant in body("_fill_money") + body("_facts") + body("_plan_salary"):
        fail.append("the salary advance must be worked out from the settings, not the constant %s" % constant)
validate = body("advance_validate")
if "settings()" not in validate or "_plan_salary(doc, s)" not in validate:
    fail.append("every advance reads the settings once, and a salary advance is planned against them")
plan = body("_plan_salary")
for needle, why in (
    ("rules.run_for(", "the run a request joins follows when it was handed in"),
    ("custom_requested_on", "which is the day it left Draft, not the day somebody started typing"),
    ("rules.payroll_period(", "absences are counted from the start of the payroll period"),
    ("attendance._off_duty_between(", "the approved off-duty days are the ones attendance.py already reads"),
    ("rules.days_absent(", "and taken off the absences by the rule, not by hand"),
    ("_closed_days(", "the public holidays come from the company's own holiday list"),
    ("min(getdate(today()), processed_on)", "until the day, absences are counted to today"),
):
    if needle not in plan:
        fail.append("_plan_salary: %s" % why)
if "Leave Application" not in body("_on_leave") or '"Approved"' not in body("_on_leave"):
    fail.append("on leave means an approved leave application covering the day")
if "custom_has_bank_loan" not in body("_bank_loan") or "custom_bank_loan_until" not in body("_bank_loan"):
    fail.append("a bank loan is read from the employee, and one that has run out no longer counts")
if "_has(" not in body("_bank_loan") or "_has(" not in body("_pay_category"):
    fail.append("the new Employee fields are asked about only once they exist: fixtures sync after patches")

step = body("_check_step")
if "PENDING_PAYROLL" not in step or "PENDING_FINANCE" not in step or "rules.held_until(" not in step:
    fail.append("the Payroll Officer ticks only the qualifying (§4.9): on passing a salary advance "
                "to Finance the eligibility is asked again and the processing date is held to")

# a salary advance is requested once and paid through the monthly run,
# processed the way a payroll is (minutes \u00a74.9)
if 'doc.custom_advance_type == rules.SALARY_ADVANCE and doc.is_new() and not from_run' not in validate \
        or "Salary Advance Request" not in validate:
    fail.append("a salary advance is not raised on the advance form: it comes from the monthly run")
if "_tell_paid(doc, scheduled)" not in body("advance_on_submit") \
        or 'if not doc.get("custom_salary_advance_run")' not in body("advance_on_submit"):
    fail.append("the run tells everyone once, not once for each advance it makes")
AA = load("advance_approval")
process = [t for t in AA.TRANSITIONS if t["action"] == AA.PROCESS]
if not process or any((t["state"], t["next_state"], t["condition"]) != (AA.DRAFT, AA.PAID, AA.FROM_RUN)
                      for t in process) or {t["allowed"] for t in process} != {AA.PAYROLL, AA.HRM}:
    fail.append("the run's advances go from Draft to Paid in one step, by the Payroll Officer or HR Manager")
RA = load("advance_request_approval")
walked, state = [RA.DRAFT], RA.DRAFT
for action in (RA.SUBMIT, RA.APPROVE):
    state = next(t["next_state"] for t in RA.TRANSITIONS if t["state"] == state and t["action"] == action)
    walked.append(state)
if walked != [RA.DRAFT, RA.PENDING_SUPERVISOR, RA.APPROVED]:
    fail.append("the request goes to the Section In-Charge or Supervisor, who approves it: %s" % walked)
if {t["allowed"] for t in RA.TRANSITIONS if t["state"] == RA.PENDING_SUPERVISOR} != set(RA.SUPERVISORS):
    fail.append("only a supervisor acts on a request waiting for one")
run = read("hrms_addon", "hrms_addon", "salary_advances.py")


def part(name):
    if ("def %s(" % name) not in run:
        fail.append("salary_advances.py has no %s" % name)
        return ""
    return run.split("def %s(" % name)[1].split(chr(10) + "def ")[0]


for needle, why in (
    ("rules.eligibility_errors(", "each line is judged by the same conditions as any salary advance"),
    ("attendance._off_duty_between(", "approved off-duty days are not absences"),
    ("advances._on_leave(", "somebody on leave on the processing date is removed"),
    ("advances._bank_loan(", "and somebody with a bank loan"),
    ("advances._outstanding_elsewhere(", "and somebody still owing an earlier advance"),
    ("rules.joins_run(", "a request joins only the months it covers, approved in time"),
    ("min(getdate(today()), processed_on)", "absences are counted to today until the processing date"),
    ("_paid_this_month(", "nobody is paid twice in a month"),
):
    if needle not in part("_work_out"):
        fail.append("the run's lines: %s" % why)
if "rules.run_errors(" not in part("run_before_submit") or "_work_out(" not in part("run_before_submit"):
    fail.append("the run is held to its day, its plants confirmed, and counted again before it is submitted")
paying = part("run_on_submit")
if "advance.submit()" not in paying or "approval.PAID" not in paying or "_bank_entry(" not in paying:
    fail.append("submitting the run makes each advance, passed for payment, and one bank entry for Finance")
entry = part("_bank_entry")
if '"reference_type": ADVANCE' not in entry or '"is_advance": "Yes"' not in entry:
    fail.append("the bank entry pays each advance against itself, so its recovery follows the payment")
if "people.hr_officers(row.branch)" not in part("_stamp_confirmations"):
    fail.append("a plant is confirmed by its own HR Officer or the HR Manager")
migrate_hooks = read("hrms_addon", "hooks.py").split("after_migrate = [", 1)[-1].split(chr(10) + "]", 1)[0]
if '"hrms_addon.hrms_addon.salary_advances.setup_on_migrate"' not in migrate_hooks:
    fail.append("the request's workflow is built on migrate")
if '"hrms_addon.hrms_addon.salary_advances.daily"' not in read("hrms_addon", "hooks.py"):
    fail.append("requests that have run their course are ended, and the dates are watched, every day")
if "rules.request_deadline(" not in part("_remind") or "run.save()" not in part("_remind"):
    fail.append("the day requests close and the processing date are both watched, and the run counted again")
for name in ("Salary Advance Request", "Salary Advance Processing", "Salary Advance Processing Employee",
             "Salary Advance Plant Confirmation"):
    if not os.path.exists(os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype", name.lower().replace(" ", "_"),
                                       name.lower().replace(" ", "_") + ".json")):
        fail.append("%s is not there" % name)
report = os.path.join(REPO, "hrms_addon", "hrms_addon", "report", "advance_payment_report",
                      "advance_payment_report.py")
if not os.path.exists(report) or '"include": 1, "qualifies": 1' not in open(report, encoding="utf-8").read():
    fail.append("the Advance Payment Report lists who is paid in a run, for Finance")
for form, wanted in (("salary_advance_request", {"stop_request"}),
                     ("salary_advance_processing", {"get_requests"})):
    script = read("hrms_addon", "hrms_addon", "doctype", form, form + ".js")
    calls = re.findall(r'xcall\(\s*"([\w.]+)"', script)
    if {call.rsplit(".", 1)[1] for call in calls} != wanted:
        fail.append("%s.js calls %s, expected %s" % (form, calls, sorted(wanted)))
    for call in calls:
        module, function = call.rsplit(".", 1)
        if module != "hrms_addon.hrms_addon.salary_advances" \
                or ('@frappe.whitelist(methods=["POST"])' + chr(10) + "def %s(" % function) not in run:
            fail.append("%s.js calls %s, which is not a whitelisted POST function" % (form, call))
advance_js = read("hrms_addon", "public", "js", "employee_advance.js")
if 'frm.set_query("advance_account"' not in advance_js or "Please select employee first" in advance_js:
    fail.append("the Advance Account filter no longer warns about an employee that is already chosen")

controller = read("hrms_addon", "hrms_addon", "doctype", "advance_settings", "advance_settings.py")
if "advances.settings_validate(self)" not in controller:
    fail.append("the settings page refuses settings that make no sense")
print("glue: the settings read once, the salary advance planned, held to its day, and watched")

# ── 7. The fields, the patch and the way in ───────────────────────────
rows = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
fields = {(row["dt"], row["fieldname"]): row for row in rows}
category = fields.get(("Employee", "custom_pay_category"))
if not category:
    fail.append("the employee must say how their pay is earned, or a Per Meter advance cannot be told apart")
elif category.get("options", "").split("\n") != list(V.PAY_CATEGORIES):
    fail.append("the employee's Pay Category must offer exactly the categories the rules know: %s"
                % (V.PAY_CATEGORIES,))
for fieldname in ("custom_has_bank_loan", "custom_bank_loan_until"):
    if ("Employee", fieldname) not in fields:
        fail.append("the employee has nowhere to record a bank loan (%s)" % fieldname)
for fieldname in ("custom_processing_date", "custom_period_start", "custom_days_absent",
                  "custom_off_duty_days", "custom_requested_on", "custom_pay_category"):
    row = fields.get(("Employee Advance", fieldname))
    if not row:
        fail.append("the advance must show what it was worked out on (%s)" % fieldname)
    elif not row.get("read_only"):
        fail.append("%s is worked out, not typed, so it is read-only" % fieldname)

hooks = read("hrms_addon", "hooks.py")
for (dt, fieldname) in fields:
    if fieldname.startswith("custom_") and (dt, fieldname) in (
            ("Employee", "custom_pay_category"), ("Employee", "custom_has_bank_loan"),
            ("Employee Advance", "custom_processing_date")):
        if '"%s-%s"' % (dt, fieldname) not in hooks:
            fail.append("%s-%s is not in hooks.py's fixture list, so it is never synced" % (dt, fieldname))

patches = read("hrms_addon", "patches.txt")
if "hrms_addon.patches.v1_0.seed_advance_settings" not in patches:
    fail.append("the settings are saved once on migrate, or the page shows numbers nobody stored")
seed = read("hrms_addon", "patches", "v1_0", "seed_advance_settings.py")
if "has_column" in seed or "get_table_columns" in seed:
    fail.append("Advance Settings is a Single and has no table to ask a column of")
if "casual" not in seed.lower():
    fail.append("the seed puts the casuals on the list of those who are not regular")
if "stored" not in seed:
    fail.append("and leaves a page somebody has already saved exactly as they saved it")

nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if nav.count('"Advance Settings"') < 2:
    fail.append("Advance Settings needs a way in from the Advances card and the sidebar")
print("fields, patch and way in: the employee's pay category and bank loan, the advance's workings")

# "Salary Advance" typed in the search bar found nothing: it is not a
# DocType, it is Frappe HR's Employee Advance with an Advance Type
search = read("hrms_addon", "public", "js", "hrms_addon_search.js")
for kind in ("Salary Advance", "Leave Advance", "Special Advance"):
    if '"%s"' % kind not in search:
        fail.append("the search bar must know %s by name" % kind)
if 'frappe.set_route("List", "Salary Advance Request")' not in search:
    fail.append("Salary Advance opens the requests")
if "make_function_searchable" not in search or "custom_advance_type: kind" not in search:
    fail.append("each advance's name opens the advances of that type, as Frappe's own searchable names do")
if "/assets/hrms_addon/js/hrms_addon_search.js" not in read("hrms_addon", "hooks.py"):
    fail.append("the search names load on every desk page (app_include_js)")
print("the search bar: the three advances by name")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL SALARY ADVANCE CHECKS PASSED")
