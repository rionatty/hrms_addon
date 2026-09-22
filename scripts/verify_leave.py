"""Verify leave management and the three advances, without a bench:

    python scripts/verify_leave.py

Luuka's revised flow charts 4.1 (Leave Management), 4.2 (Leave Advance)
and 4.10 (Salary Advance), and the paper they run on: LPL/HR/15 the leave
application and LPL/HR/21 the special advance.

  1  the leave rules: the five kinds, the plan, the balances, the horizons
  2  the advance rules: who qualifies, the ceiling, the instalments, the
     two sanctions LPL/HR/21 carries
  3  the DocTypes carry the paper, here and upstream
  4  the glue reads and writes fields that exist
  5  the signatures: each chain walked end to end, every block stamped
  6  wiring: the doc events, the workflows on migrate, the jobs, the seed,
     the way in

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


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def all_fields(name):
    spec = doctype(name) or upstream_doctype(name)
    return dict(fields_of(spec), **custom_fields(name))


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


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
L, V = load("leave_rules"), load("advance_rules")
LA, LP, AA = load("leave_approval"), load("leave_plan_approval"), load("advance_approval")
hooks = hooks_dict()
print("loaded leave_rules.py, advance_rules.py and the three approval modules without Frappe")

# ── 1. The leave rules ────────────────────────────────────────────────
if L.LEAVE_TYPES != ("Annual Leave", "Maternity Leave", "Paternity Leave", "Sick Leave",
                     "Compassionate Leave", "Leave Without Pay"):
    fail.append("LPL/HR/15 offers exactly five kinds of leave (maternity and paternity on one line): %s"
                % (L.LEAVE_TYPES,))
for kind in ("Maternity Leave", "Paternity Leave", "Sick Leave"):
    if not L.needs_certificate(kind):
        fail.append("%s is taken on a medical certificate (LPL/HR/15)" % kind)
if L.needs_certificate("Annual Leave"):
    fail.append("annual leave asks for no certificate")
if not L.needs_reason("Compassionate Leave"):
    fail.append("compassionate leave asks for the precise reason")

if L.year_window(2027) != (datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)):
    fail.append("a plan year runs January to December")
if L.days_between("2026-10-01", "2026-10-05") != 5:
    fail.append("both ends of a leave are counted, as the form counts them")
if L.days_between("2026-10-05", "2026-10-01") != 0:
    fail.append("a leave that ends before it starts covers no days")
if L.end_for("2026-10-01", 5) != datetime.date(2026, 10, 5):
    fail.append("five days from the 1st ends on the 5th")
if L.balance_after(21, 5) != 16:
    fail.append("Part 2: the balance after is the balance before less the days taken")

expect("a plan with nobody on it", L.plan_errors({"year": 2027, "rows": []}), "at least one employee")
expect("a plan with no year", L.plan_errors({"rows": [{"employee": "E1", "planned_from": "2027-02-01",
                                                       "planned_to": "2027-02-05"}]}), "which year")
expect("the same employee twice",
       L.plan_errors({"year": 2027, "rows": [
           {"employee": "E1", "employee_name": "Okello", "planned_from": "2027-02-01", "planned_to": "2027-02-05"},
           {"employee": "E1", "employee_name": "Okello", "planned_from": "2027-06-01", "planned_to": "2027-06-05"}]}),
       "on the plan twice")
expect("planned outside the year",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2026-12-20", "planned_to": "2026-12-24"}]}),
       "outside 2027")
expect("more days than the dates cover",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-02-05",
                                              "planned_days": 10}]}),
       "the dates cover")
expect("more days than they are owed",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-03-05",
                                              "entitlement_days": 21}]}),
       "entitled to")
expect("a plan that adds up",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-02-21",
                                              "planned_days": 21, "entitlement_days": 21}]}))

expect("sick leave with no certificate",
       L.application_errors({"leave_type": "Sick Leave", "from_date": "2026-10-01", "to_date": "2026-10-03"}),
       "medical certificate")
expect("compassionate leave with no reason",
       L.application_errors({"leave_type": "Compassionate Leave", "from_date": "2026-10-01",
                             "to_date": "2026-10-03"}),
       "precise reason")
expect("more days than are left",
       L.application_errors({"leave_type": "Annual Leave", "from_date": "2026-10-01", "to_date": "2026-10-10",
                             "total_leave_days": 10, "balance_before": 4}),
       "Leave Without Pay")
expect("unpaid leave beyond the balance",
       L.application_errors({"leave_type": "Leave Without Pay", "from_date": "2026-10-01",
                             "to_date": "2026-10-10", "total_leave_days": 10, "balance_before": 0}))
expect("a leave that ends before it starts",
       L.application_errors({"leave_type": "Annual Leave", "from_date": "2026-10-10", "to_date": "2026-10-01"}),
       "ends before it starts")

if L.DUE_HORIZONS != (30, 14, 7):
    fail.append("a planned leave is told a month, a fortnight and a week before: %s" % (L.DUE_HORIZONS,))
if L.due_alerts("2026-11-01", "2026-09-01") != []:
    fail.append("nothing is said two months out")
if L.due_alerts("2026-11-01", "2026-10-05") != [30]:
    fail.append("inside the month but outside the fortnight, only the month's notice goes")
if L.due_alerts("2026-11-01", "2026-10-05", sent="30") != []:
    fail.append("nobody is told the same thing twice")
if L.due_alerts("2026-11-01", "2026-10-20") != [30, 14]:
    fail.append("inside the fortnight, both notices are due at once")
if L.due_alerts("2026-11-01", "2026-10-28") != [30, 14, 7]:
    fail.append("a plan seen late gets one notice covering every horizon reached")
if L.due_alerts("2026-11-01", "2026-11-02") != []:
    fail.append("a leave already begun is no longer due")
if L.record_alerts("7", [30, 14]) != "30,14,7":
    fail.append("what was told is remembered, largest first")
if not L.advance_wanted({"salary_requested_in_advance": 1}) or L.advance_wanted({}):
    fail.append("step 7 turns on the form's own Salary Requested in Advance")
if L.leave_stage(1, "2026-10-01", "2026-10-05", "2026-10-03") != L.ON_LEAVE:
    fail.append("an employee inside their dates is on leave")
if L.leave_stage(1, "2026-10-01", "2026-10-05", "2026-10-06") != L.REPORTED_BACK:
    fail.append("once the last day has passed the employee is due back")
if L.leave_stage(0, "2026-10-01", "2026-10-05", "2026-10-03") is not None:
    fail.append("a draft application is not leave yet")
print("leave: the five kinds, the plan, the balances of Part 2, the horizons, the report back")

# ── 2. The advance rules ──────────────────────────────────────────────
if V.ADVANCE_TYPES != ("Leave Advance", "Salary Advance", "Special Advance"):
    fail.append("Luuka take three kinds of advance: %s" % (V.ADVANCE_TYPES,))
if set(AA.CONDITIONS) != set(V.ADVANCE_TYPES):
    fail.append("the workflow must route every kind of advance")
for kind in V.ADVANCE_TYPES:
    if kind not in AA.CONDITIONS[kind]:
        fail.append("the %s condition must name it" % kind)
if V.months_served("2026-01-15", "2026-04-14") != 2:
    fail.append("a month is not served until the day of the month comes round")
if V.months_served("2026-01-15", "2026-04-15") != 3:
    fail.append("three months served on the fifteenth")
if V.limit_for(1000000) != 500000:
    fail.append("the ceiling is half a month's gross")

# These are LPL/HR/21's rules — half a month's gross, three months' service,
# recovered in at most three — so they are asked of the special advance.
# They were once asked of the salary advance too, which the minutes (§4.9)
# say is 40% of gross, recovered from the same month's pay, with no service
# rule at all: scripts/verify_salary_advance.py pins those.
ok = {"advance_type": "Special Advance", "status": "Active", "date_of_joining": "2025-01-01",
      "today": "2026-09-21", "gross_pay": 1000000, "amount": 300000, "outstanding": 0, "instalments": 2}
expect("an employee who qualifies", V.eligibility_errors(ok))
expect("someone who left", V.eligibility_errors(dict(ok, status="Left")), "active employee")
expect("someone just joined", V.eligibility_errors(dict(ok, date_of_joining="2026-08-01")), "month(s) of service")
expect("more than half the gross", V.eligibility_errors(dict(ok, amount=900000)), "most that may be advanced")
expect("an advance still owed", V.eligibility_errors(dict(ok, outstanding=50000)), "still owed")
expect("recovered over too long", V.eligibility_errors(dict(ok, instalments=6)), "at most 3")
expect("no amount", V.eligibility_errors(dict(ok, amount=0)), "how much")

schedule = V.recovery_schedule(100000, 3, "2026-10-31")
if len(schedule) != 3 or round(sum(amount for _m, amount in schedule), 2) != 100000:
    fail.append("the instalments must add back to the whole: %s" % (schedule,))
if [month.month for month, _a in schedule] != [10, 11, 12]:
    fail.append("the instalments run month by month from the first: %s" % (schedule,))
odd = V.recovery_schedule(100, 3, "2026-10-31")
if [a for _m, a in odd] != [33.33, 33.33, 33.34]:
    fail.append("the rounding goes on the last instalment: %s" % (odd,))
if V.recovery_schedule(0, 3, "2026-10-31") != []:
    fail.append("nothing is recovered from nothing")
if V.outstanding(100000, 40000) != 60000:
    fail.append("what is outstanding is what was not yet recovered")
if V.outstanding(100000, 150000) != 0:
    fail.append("an over-recovery leaves nothing outstanding, not a negative")
if V.advance_status(1, 0, 100000, 0) != V.APPROVED:
    fail.append("approved and not yet paid")
if V.advance_status(1, 100000, 100000, 0) != V.PAID:
    fail.append("paid and nothing recovered yet")
if V.advance_status(1, 100000, 100000, 40000) != V.RECOVERING:
    fail.append("part recovered")
if V.advance_status(1, 100000, 100000, 100000) != V.RECOVERED:
    fail.append("fully recovered")

if V.sanctioned(200000, 150000, 300000) != 150000:
    fail.append("the lower of the two sanctions stands (LPL/HR/21)")
if V.sanctioned(None, None, 300000) != 300000:
    fail.append("nothing sanctioned yet means what was asked for")
expect("the Section Head sanctioning more than was asked",
       V.sanction_errors({"amount": 100000, "section_head_amount": 200000}), "Section Head sanctioned more")
expect("paying more than was sanctioned",
       V.sanction_errors({"amount": 300000, "section_head_amount": 150000, "paid_amount": 200000}),
       "only UGX 150,000 was sanctioned")
expect("a sanction that holds",
       V.sanction_errors({"amount": 300000, "section_head_amount": 150000, "ed_amount": 150000,
                          "paid_amount": 150000}))
print("advances: who qualifies, the ceiling, the instalments, LPL/HR/21's two sanctions")

# ── 3. The DocTypes carry the paper ───────────────────────────────────
for name, wanted in (
    ("Annual Leave Plan", ("year", "company", "employees", "status", "total_employees", "total_days",
                           "hod_by", "hod_on", "hr_by", "hr_on", "return_remarks", "informed_on",
                           "informed_count")),
    ("Annual Leave Plan Employee", ("employee", "entitlement_days", "planned_from", "planned_to",
                                    "planned_days", "leave_application", "informed", "alerts_sent")),
    ("Advance Recovery", ("payroll_date", "amount", "additional_salary", "recovered")),
):
    fields = fields_of(doctype(name))
    if not fields:
        fail.append("%s is not there" % name)
        continue
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the leave process asks for" % (name, fieldname))
for name, fieldname in (("Annual Leave Plan", "total_days"), ("Annual Leave Plan", "status"),
                        ("Annual Leave Plan Employee", "informed"), ("Advance Recovery", "recovered")):
    if not (fields_of(doctype(name)).get(fieldname) or {}).get("read_only"):
        fail.append("%s.%s is worked out, not typed" % (name, fieldname))

# LPL/HR/15 on Frappe HR's own Leave Application
if not upstream_doctype("Leave Application"):
    fail.append("Frappe HR's Leave Application is not where it was: LPL/HR/15 is built on it")
theirs = custom_fields("Leave Application")
for fieldname in ("custom_work_section", "custom_date_of_appointment", "custom_medical_certificate",
                  "custom_salary_requested_in_advance", "custom_advance", "custom_plan",
                  "custom_last_leave_type", "custom_last_leave_from", "custom_last_leave_to",
                  "custom_last_leave_days", "custom_balance_before", "custom_balance_after",
                  "custom_sick_balance_before", "custom_sick_balance_after", "custom_hro_by", "custom_hro_on",
                  "custom_leave_status", "custom_supervisor_remarks", "custom_supervisor_by",
                  "custom_hod_remarks", "custom_hod_by", "custom_hr_remarks", "custom_hr_by",
                  "custom_return_remarks", "custom_advance_amount", "custom_accounts_by",
                  "custom_reported_back", "custom_reported_back_on"):
    if fieldname not in theirs:
        fail.append("Leave Application has no %s, which LPL/HR/15 asks for" % fieldname)
for fieldname in ("custom_balance_after", "custom_sick_balance_after", "custom_leave_status",
                  "custom_supervisor_by", "custom_hod_by", "custom_hr_by", "custom_advance_amount"):
    if not (theirs.get(fieldname) or {}).get("read_only"):
        fail.append("Leave Application.%s is worked out, not typed" % fieldname)
if "custom_advance_type" in theirs:
    fail.append("the advance belongs on the Employee Advance, not the leave form")
status_options = (theirs.get("custom_leave_status") or {}).get("options", "").split("\n")
for state in (LA.DRAFT, LA.PENDING_SUPERVISOR, LA.PENDING_HOD, LA.PENDING_HR, LA.APPROVED, LA.REJECTED):
    if state not in status_options:
        fail.append("Leave Application.custom_leave_status must offer %r" % state)

# the three advances on Frappe HR's own Employee Advance
if not upstream_doctype("Employee Advance"):
    fail.append("Frappe HR's Employee Advance is not where it was: the advances are built on it")
advance = custom_fields("Employee Advance")
for fieldname in ("custom_advance_type", "custom_badge_no", "custom_work_section",
                  "custom_date_of_appointment", "custom_gross_pay", "custom_outstanding_before",
                  "custom_leave_application", "custom_reason", "custom_advance_status", "custom_qualifies",
                  "custom_limit", "custom_eligibility_remarks", "custom_attendance_confirmed",
                  "custom_section_head_amount", "custom_ed_amount", "custom_approved_amount",
                  "custom_instalments", "custom_first_recovery_month", "custom_recoveries",
                  "custom_recovered_amount", "custom_outstanding", "custom_consent", "custom_paid_on"):
    if fieldname not in advance:
        fail.append("Employee Advance has no %s, which Luuka's advances ask for" % fieldname)
if (advance.get("custom_advance_type") or {}).get("options", "").split("\n") != list(V.ADVANCE_TYPES):
    fail.append("Employee Advance.custom_advance_type must offer exactly Luuka's three advances")
if (advance.get("custom_recoveries") or {}).get("options") != "Advance Recovery":
    fail.append("the instalments are a table of Advance Recovery")
for fieldname in ("custom_qualifies", "custom_limit", "custom_gross_pay", "custom_outstanding_before",
                  "custom_recovered_amount", "custom_outstanding", "custom_advance_status"):
    if not (advance.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Advance.%s is worked out, not typed" % fieldname)
print("the paper: the plan and its rows, LPL/HR/15 on their leave form, LPL/HR/21 on their advance")

# ── 4. The glue reads fields that exist ───────────────────────────────
glue_leave = read("hrms_addon", "hrms_addon", "leave.py")
leave_fields = all_fields("Leave Application")
plan_fields = fields_of(doctype("Annual Leave Plan"))
for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue_leave))
                        | set(re.findall(r"doc\.(custom_\w+)\b", glue_leave))):
    if fieldname not in leave_fields:
        fail.append("leave.py reads or writes Leave Application.%s, which does not exist" % fieldname)
glue_advances = read("hrms_addon", "hrms_addon", "advances.py")
advance_fields = all_fields("Employee Advance")
for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue_advances))
                        | set(re.findall(r"doc\.(custom_\w+)\b", glue_advances))):
    if fieldname not in advance_fields:
        fail.append("advances.py reads or writes Employee Advance.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.plan_errors(", "a plan is judged by the rules"),
    ("rules.application_errors(", "and so is an application"),
    ("rules.due_alerts(", "the horizons come from the rules"),
    ("rules.record_alerts(", "and what was told is remembered"),
    ("rules.balance_after(", "Part 2's balances come from the rules"),
    ("rules.advance_wanted(", "step 7 turns on the form's own tick"),
    ("approval.upstream_status(", "Frappe HR's own status is kept in step"),
):
    if needle not in glue_leave:
        fail.append("leave.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("rules.eligibility_errors(", "who may take an advance is judged by the rules"),
    ("rules.recovery_schedule(", "and the instalments worked out by them"),
    ("rules.sanction_errors(", "and the two sanctions checked by them"),
    ("rules.outstanding(", "and what is still owed"),
    ("Additional Salary", "an instalment is taken through the payroll, not by hand"),
):
    if needle not in glue_advances:
        fail.append("advances.py: %s (%r not found)" % (why, needle))
for name in ("inform_employees", "raise_advance"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue_leave):
        fail.append("leave.%s changes something: a whitelisted POST method" % name)
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef from_leave\(', glue_advances):
    fail.append("advances.from_leave changes something: a whitelisted POST method")
for glue, name in ((glue_leave, "leave.py"), (glue_advances, "advances.py")):
    if 'check_permission(' not in glue:
        fail.append("%s: a whitelisted method must check the caller may act" % name)
print("glue: fields that exist here and upstream, the rules followed, the buttons whitelisted")

# ── 5. The signatures ─────────────────────────────────────────────────
def walk(module, start, forward_actions, condition=None):
    walked, state = [start], start
    seen = set()
    while state not in seen:
        seen.add(state)
        forward = [t for t in module.TRANSITIONS if t["state"] == state and t["action"] in forward_actions
                   and (condition is None or t.get("condition") in (None, condition))]
        if not forward:
            break
        state = forward[0]["next_state"]
        walked.append(state)
    return walked


route = walk(LA, LA.DRAFT, (LA.SUBMIT, LA.APPROVE))
if route != [LA.DRAFT, LA.PENDING_SUPERVISOR, LA.PENDING_HOD, LA.PENDING_HR, LA.APPROVED]:
    fail.append("LPL/HR/15 is signed by the Manager in line, the HOD, then the HR Officer: %s" % route)
if set(LA.STAMPS) != set(LA.PENDING_STATES) or set(LA.REMARK_FIELDS) != set(LA.PENDING_STATES):
    fail.append("every signature block of Part 3 is stamped: %s" % sorted(LA.STAMPS))
for state in LA.PENDING_STATES:
    for action, what in ((LA.REJECT, "refuse"), (LA.RETURN, "return")):
        if not [t for t in LA.TRANSITIONS if t["state"] == state and t["action"] == action]:
            fail.append("%s must be able to %s the application" % (state, what))
expect("returned without saying why", LA.step_errors(LA.PENDING_HOD, LA.DRAFT, {}), "Return Remarks")
expect("refused without saying why", LA.step_errors(LA.PENDING_HR, LA.REJECTED, {}), "HR Officer's remarks")
expect("approved before Part 2 is filled in", LA.step_errors(LA.PENDING_HR, LA.APPROVED, {}), "Part 2")
expect("approved with Part 2 filled in",
       LA.step_errors(LA.PENDING_HR, LA.APPROVED, {"custom_balance_before": 21}))
if any(LA.compute_stamps(LA.PENDING_HR, LA.DRAFT, "x", "2026-03-04",
                         {"custom_supervisor_by": "a"}).values()):
    fail.append("a return clears every signature on the leave form")
if LA.upstream_status(LA.PENDING_HOD) != "Open" or LA.upstream_status(LA.APPROVED) != "Approved":
    fail.append("Frappe HR's own status stays Open until the chain decides")
if set(LA.ROLE_WAITING) != set(LA.PENDING_STATES):
    fail.append("every pending state must know whose desk it is on")

plan_route = walk(LP, LP.DRAFT, (LP.SUBMIT, LP.APPROVE))
if plan_route != [LP.DRAFT, LP.PENDING_HOD, LP.PENDING_HR, LP.APPROVED]:
    fail.append("the plan is approved by the HODs then the HR Officer: %s" % plan_route)
expect("a plan returned without saying why", LP.step_errors(LP.PENDING_HOD, LP.DRAFT, {}), "Return Remarks")

for kind, wanted in (
    (V.LEAVE_ADVANCE, [AA.DRAFT, AA.PENDING_ACCOUNTS_MANAGER, AA.PENDING_PAYROLL, AA.PENDING_FINANCE, AA.PAID]),
    (V.SALARY_ADVANCE, [AA.DRAFT, AA.PENDING_HR, AA.PENDING_PAYROLL, AA.PENDING_FINANCE, AA.PAID]),
    (V.SPECIAL_ADVANCE, [AA.DRAFT, AA.PENDING_SECTION_HEAD, AA.PENDING_ED, AA.PENDING_FINANCE, AA.PAID]),
):
    walked = walk(AA, AA.DRAFT, (AA.SUBMIT, AA.APPROVE, AA.PAY), AA.CONDITIONS[kind])
    if walked != wanted:
        fail.append("the %s goes %s, not %s" % (kind, wanted, walked))
    if list(AA.route(kind)) != wanted:
        fail.append("advance_approval.route(%r) must say the same: %s" % (kind, AA.route(kind)))
if set(AA.STAMPS) != set(AA.PENDING_STATES) or set(AA.REMARK_FIELDS) != set(AA.PENDING_STATES):
    fail.append("every desk an advance passes is stamped: %s" % sorted(AA.STAMPS))
if set(AA.ROLE_WAITING) != set(AA.PENDING_STATES):
    fail.append("every pending state must know whose desk it is on")
expect("payroll passing it on without setting the amount",
       AA.step_errors(AA.PENDING_PAYROLL, AA.PENDING_FINANCE, {"instalments": 1}), "amount approved")
expect("payroll passing it on without saying how it comes back",
       AA.step_errors(AA.PENDING_PAYROLL, AA.PENDING_FINANCE, {"approved_amount": 100000}), "how many months")
expect("payroll doing both",
       AA.step_errors(AA.PENDING_PAYROLL, AA.PENDING_FINANCE, {"approved_amount": 100000, "instalments": 2}))
expect("the HR Officer passing a salary advance on unchecked",
       AA.step_errors(AA.PENDING_HR, AA.PENDING_PAYROLL, {}), "attendance and leave")
expect("the Section Head signing without an amount",
       AA.step_errors(AA.PENDING_SECTION_HEAD, AA.PENDING_ED, {}), "amount sanctioned")
if AA.next_states(AA.DRAFT, ("HR User",), V.LEAVE_ADVANCE) != [(AA.SUBMIT, AA.PENDING_ACCOUNTS_MANAGER)]:
    fail.append("a leave advance leaves Draft for the Accounts Manager")
if AA.next_states(AA.DRAFT, ("HR User",), V.SPECIAL_ADVANCE) != [(AA.SUBMIT, AA.PENDING_SECTION_HEAD)]:
    fail.append("a special advance leaves Draft for the Section Head")
if AA.next_states(AA.PENDING_PAYROLL, ("Employee",), V.SALARY_ADVANCE):
    fail.append("nobody may act on a desk that is not theirs")
print("signatures: each chain walked end to end, every block stamped, the junctions conditional")

# ── 6. Wiring ─────────────────────────────────────────────────────────
events = hooks.get("doc_events", {})
for dt, methods in (("Leave Application", ("validate", "on_submit", "on_cancel")),
                    ("Employee Advance", ("validate", "on_submit", "on_cancel"))):
    for method in methods:
        if not (events.get(dt) or {}).get(method):
            fail.append("%s has no %s hook" % (dt, method))
for path in ("hrms_addon.hrms_addon.leave.setup_workflows_on_migrate",
             "hrms_addon.hrms_addon.advances.setup_workflows_on_migrate"):
    if path not in (hooks.get("after_migrate") or []):
        fail.append("%s must run after every migrate" % path)
for path in ("hrms_addon.hrms_addon.leave.daily", "hrms_addon.hrms_addon.advances.daily"):
    if path not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
        fail.append("%s must run daily: the charts both draw system monitoring" % path)
if "hrms_addon.hrms_addon.leave.seed_leave_types" not in (hooks.get("after_install") or []):
    fail.append("a fresh install seeds the five kinds of leave")
if "seed_leave_types()" not in read("hrms_addon", "patches", "v1_0", "seed_leave.py"):
    fail.append("and so does the patch, on a site that has the app already")
if "hrms_addon.patches.v1_0.seed_leave" not in read("hrms_addon", "patches.txt"):
    fail.append("the seed patch must be listed in patches.txt")
for dt in ("Leave Application", "Employee Advance"):
    if dt not in (hooks.get("doctype_js") or {}):
        fail.append("%s needs its form script" % dt)
controller = read("hrms_addon", "hrms_addon", "doctype", "annual_leave_plan", "annual_leave_plan.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        leave.plan_%s(self)" % (method, method) not in controller:
        fail.append("the Annual Leave Plan controller must hand %s to leave.plan_%s" % (method, method))
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Annual Leave Plan" not in carded or "Annual Leave Plan" not in sidebarred:
    fail.append("the Annual Leave Plan needs a way in")
if "Leaves" not in navigation.CARDS:
    fail.append("the plan belongs on Frappe HR's own leave page")
if not os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "workspace", "leaves", "leaves.json")):
    fail.append("Frappe HR no longer ships the Leaves workspace")
if "Leave Application" in carded or "Leave Application" in sidebarred:
    fail.append("Leave Application is Frappe HR's own and already on their page: leave their entry alone")
# The advance is listed again on the Loans page this app makes, because
# LPL/HR/21 calls it a loan and it is recovered like one. That is an
# addition, not a move: merge_links only clears our links from the page it
# is merging, so their own Expenses entry is untouched.
for where in (navigation.CARDS, navigation.SIDEBAR):
    for page, rows in where.items():
        if page in navigation.PAGE_LABELS:
            continue
        listed = ([link[1] for _card, links in rows for link in links] if where is navigation.CARDS
                  else [row[1] for row in rows])
        if "Employee Advance" in listed:
            fail.append("Employee Advance is Frappe HR's own: it belongs on their page and ours, "
                        "not added to a third (%s)" % page)
print("wiring: the doc events, the two workflows on migrate, the daily jobs, the seed, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LEAVE AND ADVANCE CHECKS PASSED")
