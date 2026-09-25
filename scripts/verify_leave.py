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
# leave days as Frappe HR's Leave Application counts them: holidays out
HOLIDAYS = ["2027-03-07", "2027-03-08"]
if L.leave_days("2027-03-01", "2027-03-10", HOLIDAYS) != 8:
    fail.append("a Sunday and a public holiday inside a leave are not leave days")
if L.leave_days("2027-03-01", "2027-03-10", HOLIDAYS, include_holidays=True) != 10:
    fail.append("unless the leave type counts holidays as leave")
if L.leave_days("2027-03-10", "2027-03-01", HOLIDAYS) != 0:
    fail.append("a leave that ends before it starts takes nothing")
if L.end_after("2027-03-01", 8, HOLIDAYS) != datetime.date(2027, 3, 10):
    fail.append("eight leave days from 1 March, over a Sunday and a holiday, end on the 10th")
if L.end_after("2027-03-01", 8, HOLIDAYS, include_holidays=True) != datetime.date(2027, 3, 8):
    fail.append("counting the holidays, they end on the 8th")
if L.end_after("2027-03-01", 0) is not None:
    fail.append("no days, no end")
if L.balance_after(21, 5) != 16:
    fail.append("Part 2: the balance after is the balance before less the days taken")

expect("a plan with nobody on it", L.plan_errors({"year": 2027, "rows": []}), "at least one employee")
expect("a row with no dates yet", L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello"}]}),
       "Okello has no planned dates")
expect("a plan with no year", L.plan_errors({"rows": [{"employee": "E1", "planned_from": "2027-02-01",
                                                       "planned_to": "2027-02-05", "available_days": 21}]}),
       "which year")
SPLIT = [{"employee": "E1", "employee_name": "Okello", "planned_from": "2027-02-01", "planned_to": "2027-02-10",
          "planned_days": 10, "available_days": 21},
         {"employee": "E1", "employee_name": "Okello", "planned_from": "2027-06-01", "planned_to": "2027-06-11",
          "planned_days": 11, "available_days": 21}]
expect("a leave split in two parts that fit", L.plan_errors({"year": 2027, "rows": SPLIT}))
expect("parts that overlap",
       L.plan_errors({"year": 2027, "rows": [SPLIT[0], dict(SPLIT[1], planned_from="2027-02-08")]}),
       "overlaps: 1 Feb 2027 to 10 Feb 2027 and 8 Feb 2027 to 11 Jun 2027")
expect("parts that share a day",
       L.plan_errors({"year": 2027, "rows": [SPLIT[0], dict(SPLIT[1], planned_from="2027-02-10")]}),
       "overlaps: 1 Feb 2027 to 10 Feb 2027 and 10 Feb 2027 to 11 Jun 2027")
expect("parts that together are more than available",
       L.plan_errors({"year": 2027, "rows": [SPLIT[0], dict(SPLIT[1], planned_days=12)]}),
       "22 day(s), 21 available")
expect("planned outside the year",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2026-12-20", "planned_to": "2026-12-24",
                                              "available_days": 21}]}),
       "outside 2027")
expect("more days than they have",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-03-05",
                                              "planned_days": 30, "available_days": 21}]}),
       "30 day(s), 21 available")
expect("a plan that adds up",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-02-21",
                                              "planned_days": 21, "available_days": 21}]}))
expect("with nothing on record, the plan waits for the leave policy or allocation",
       L.plan_errors({"year": 2027, "rows": [{"employee": "E1", "employee_name": "Okello",
                                              "planned_from": "2027-02-01", "planned_to": "2027-02-05",
                                              "planned_days": 5}]}),
       "Okello has no annual leave on record for 2027")

# clashes: more of one department off together than the plan allows
TEAM = [{"employee": "A", "employee_name": "Ann", "department": "Extrusion", "planned_from": "2027-03-01",
         "planned_to": "2027-03-05"},
        {"employee": "B", "employee_name": "Ben", "department": "Extrusion", "planned_from": "2027-03-03",
         "planned_to": "2027-03-08"},
        {"employee": "C", "employee_name": "Cy", "department": "Extrusion", "planned_from": "2027-03-04",
         "planned_to": "2027-03-04"},
        {"employee": "D", "employee_name": "Dee", "department": "Stores", "planned_from": "2027-03-01",
         "planned_to": "2027-03-31"}]
found = L.clashes(TEAM, 2)
if [(clash["department"], clash["from"], clash["to"], clash["most"], clash["names"]) for clash in found] != \
        [("Extrusion", datetime.date(2027, 3, 4), datetime.date(2027, 3, 4), 3, ["Ann", "Ben", "Cy"])]:
    fail.append("three of Extrusion off on 4 March is a clash when two is the most: %s" % found)
if L.clash_lines(found, 2) != ["Extrusion: 3 off on 4 Mar 2027, more than 2 (Ann, Ben, Cy)."]:
    fail.append("and the plan says so plainly: %s" % L.clash_lines(found, 2))
TWICE = TEAM + [{"employee": "E", "employee_name": "Eve", "department": "Extrusion", "planned_from": "2027-03-08",
                  "planned_to": "2027-03-09"}]
if [(clash["from"].day, clash["to"].day) for clash in L.clashes(TWICE, 1)] != [(3, 5), (8, 8)]:
    fail.append("two clashes in one department with a day between them are two: %s" % L.clashes(TWICE, 1))
if L.clashes(TEAM, 1)[0]["to"] != datetime.date(2027, 3, 5) or L.clashes(TEAM, 0):
    fail.append("a clash runs while too many are off; no limit, no clash")
if "from 3 Mar 2027 to 5 Mar 2027" not in L.clash_lines(L.clashes(TEAM, 1), 1)[0]:
    fail.append("a clash over several days gives its first and last day")

# where a planned leave stands
for application, day, status in (
    (None, "2027-02-28", L.PLANNED),
    (None, "2027-03-02", L.NOT_APPLIED),
    ({"docstatus": 0, "status": "Open", "to_date": "2027-03-10"}, "2027-03-02", L.APPLIED),
    ({"docstatus": 1, "status": "Approved", "to_date": "2027-03-10"}, "2027-03-05", L.APPLIED),
    ({"docstatus": 1, "status": "Approved", "to_date": "2027-03-10"}, "2027-03-11", L.TAKEN),
    ({"docstatus": 1, "status": "Rejected", "to_date": "2027-03-10"}, "2027-03-11", L.NOT_APPLIED),
    ({"docstatus": 2, "status": "Cancelled", "to_date": "2027-03-10"}, "2027-02-20", L.PLANNED),
    (None, "2027-03-01", L.PLANNED),
    ({"docstatus": 1, "status": "Approved", "to_date": "2027-03-10"}, "2027-03-10", L.APPLIED),
):
    if L.plan_row_status("2027-03-01", day, application) != status:
        fail.append("a leave planned from 1 March, on %s with %s, is %s: got %s"
                    % (day, application, status, L.plan_row_status("2027-03-01", day, application)))

# the months of a year's plan
if L.month_days("2027-01-25", "2027-02-03", 2027, ["2027-01-31"]) != {1: 6, 2: 3}:
    fail.append("a leave over two months counts its days in each: %s"
                % L.month_days("2027-01-25", "2027-02-03", 2027, ["2027-01-31"]))
counts = L.adherence([{"department": "Extrusion", "leave_status": L.TAKEN, "moved": True},
                      {"department": "Extrusion", "leave_status": L.NOT_APPLIED},
                      {"department": "Stores", "leave_status": "odd"}])
if (counts["Extrusion"]["planned"], counts["Extrusion"][L.TAKEN], counts["Extrusion"][L.NOT_APPLIED],
        counts["Extrusion"]["moved"], counts["Stores"][L.PLANNED]) != (2, 1, 1, 1, 1):
    fail.append("how a plan was kept to, by department: %s" % counts)

# moving one planned leave
MOVE = {"year": 2027, "new_from": "2027-07-01", "new_to": "2027-07-10", "new_days": 8, "available": 21,
        "others": [("2027-02-01", "2027-02-10", 10)], "reason": "Family wedding"}
expect("a move that fits", L.change_errors(MOVE))
expect("a move with nothing on record", L.change_errors(dict(MOVE, available=0)), "No annual leave on record")
expect("a move with no reason", L.change_errors(dict(MOVE, reason=" ")), "why the leave is moving")
expect("a move out of the year", L.change_errors(dict(MOVE, new_from="2026-12-30", new_to="2026-12-31")),
       "fall in 2027")
expect("a move onto the other part", L.change_errors(dict(MOVE, new_from="2027-02-05")),
       "overlap the leave planned from 1 Feb 2027 to 10 Feb 2027")
expect("a move ending on the other part's first day",
       L.change_errors(dict(MOVE, new_from="2027-01-25", new_to="2027-02-01")), "overlap the leave planned")
expect("a move starting on the other part's last day",
       L.change_errors(dict(MOVE, new_from="2027-02-10", new_to="2027-02-12")), "overlap the leave planned")
expect("a move to more days than available", L.change_errors(dict(MOVE, new_days=12)), "22 day(s) planned")
expect("a move of a leave already applied for", L.change_errors(dict(MOVE, applied=True)), "Cancel that application")
expect("a move ending before it starts", L.change_errors(dict(MOVE, new_to="2027-06-01")), "ends before it starts")

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
# the minutes of 16 and 20 July 2026, §4.3
for kind, days, why in (
    ("Maternity Leave", 60, "maternity is 60 days"),
    ("Paternity Leave", 4, "paternity is 4"),
    ("Sick Leave", 60, "sick leave is 60 days at full pay"),
    ("Sick Leave (Half Pay)", 120, "and 120 more at half pay, on a hospital document"),
    ("Compassionate Leave", 4, "compassionate leave is 4 days"),
    ("Leave Without Pay", 60, "and without pay at most 60"),
):
    if L.LEAVE_DAYS.get(kind) != days:
        fail.append("%s should be set up with %s days: %s (it has %r)" % (kind, days, why, L.LEAVE_DAYS.get(kind)))
if L.LEAVE_DAYS.get("Annual Leave") != 0:
    fail.append("Annual Leave must carry no maximum: Frappe HR refuses an allocation over a type's "
                "maximum and cuts carried-forward days back to it, so a cap of 21 would block the 28 "
                "and 30 the minutes reserve for particular people and eat the carry-forward")
if L.ANNUAL_OPTIONS != (21, 28, 30):
    fail.append("annual leave is 21, 28 or 30 days")
if "Sick Leave (Half Pay)" not in L.EXTRA_TYPES or "Sick Leave (Half Pay)" not in L.NEEDS_CERTIFICATE:
    fail.append("half-pay sick leave is its own type, and it needs the hospital's document")
if L.HALF_PAY_FRACTION != 0.5:
    fail.append("and it pays half")
seed = read("hrms_addon", "hrms_addon", "leave.py").split("def leave_type_values(")[1].split("\ndef ")[0]
for needle, why in (("is_ppl", "half-pay leave is Frappe HR's partially paid leave"),
                    ("fraction_of_daily_salary_per_leave", "paid at its fraction"),
                    ("max_continuous_days_allowed", "unpaid leave is limited by the length of one leave"),
                    ("maximum_carry_forwarded_leaves", "and annual leave carries forward with no maximum")):
    if needle not in seed:
        fail.append("leave_type_values: %s" % why)
patch = read("hrms_addon", "patches", "v1_0", "leave_days_from_minutes.py")
if "FORMER_DAYS" not in patch or "hrms_addon.patches.v1_0.leave_days_from_minutes" not in read("hrms_addon", "patches.txt"):
    fail.append("the live site's leave types are corrected on migrate, but only where they still hold "
                "what the seed first wrote")
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
                           "informed_count", "most_off", "clashes")),
    ("Annual Leave Plan Employee", ("employee", "entitlement_days", "brought_forward", "available_days",
                                    "planned_from", "planned_to", "planned_days", "leave_status",
                                    "leave_application", "informed", "alerts_sent", "not_applied_told",
                                    "original_from", "original_to", "last_change")),
    ("Leave Plan Change", ("plan", "plan_row", "employee", "current_from", "current_to", "new_from", "new_to",
                           "new_days", "reason", "clashes", "supervisor_remarks", "supervisor_by", "hod_remarks",
                           "hod_by", "approval_status")),
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
                        ("Annual Leave Plan", "clashes"), ("Annual Leave Plan Employee", "available_days"),
                        ("Annual Leave Plan Employee", "leave_status"), ("Leave Plan Change", "new_days"),
                        ("Annual Leave Plan Employee", "informed"), ("Advance Recovery", "recovered")):
    if not (fields_of(doctype(name)).get(fieldname) or {}).get("read_only"):
        fail.append("%s.%s is worked out, not typed" % (name, fieldname))

# LPL/HR/15 on Frappe HR's own Leave Application
if not upstream_doctype("Leave Application"):
    fail.append("Frappe HR's Leave Application is not where it was: LPL/HR/15 is built on it")
theirs = custom_fields("Leave Application")
for fieldname in ("custom_work_section", "custom_date_of_appointment", "custom_medical_certificate",
                  "custom_salary_requested_in_advance", "custom_advance", "custom_plan", "custom_plan_row",
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
    ("rules.leave_days(", "a plan counts leave days as the Leave Application does"),
    ("rules.end_after(", "and finds the last day over the holidays"),
    ("get_holiday_dates_between_range(", "from Frappe HR's own reading of the employee's holidays"),
    ('"Leave Policy Assignment"', "what an employee has comes from their leave policy before the allocation"),
    ("get_leave_balance_on(", "and what their balance carries into the year"),
    ("rules.clashes(", "too many of one department off together shows"),
    ("rules.change_errors(", "moving a planned leave is judged by the rules"),
    ("rules.plan_row_status(", "each planned leave's status comes from the rules"),
    ("_planned_row_for(", "an application finds its planned leave by its dates"),
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
for name in ("inform_employees", "raise_advance", "get_employees", "apply_from_plan", "request_change"):
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
for name in ("Leave Plan Change", "Leave Schedule", "Leave Plan Adherence"):
    if name not in carded or name not in sidebarred:
        fail.append("%s needs a way in" % name)
daily_body = glue_leave.split("def daily(")[1].split(chr(10) + "def ")[0]
if "_tell_not_applied()" not in daily_body or "_refresh_plan_statuses()" not in daily_body:
    fail.append("every day: a planned leave started with nothing applied for tells HR, and the statuses are kept")
if "workflows.setup_on_migrate(leave_plan_change_approval, " not in \
        glue_leave.split("def setup_workflows_on_migrate(")[1].split(chr(10) + "def ")[0]:
    fail.append("the Leave Plan Change's workflow is built on migrate")
change_controller = read("hrms_addon", "hrms_addon", "doctype", "leave_plan_change", "leave_plan_change.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        leave.change_%s(self)" % (method, method) not in change_controller:
        fail.append("the Leave Plan Change controller must hand %s to leave.change_%s" % (method, method))
plan_spec = doctype("Annual Leave Plan")
if not any(p["role"] == "Employee" and p.get("read") and p.get("report") for p in plan_spec.get("permissions", [])):
    fail.append("employees are shown the plan, and its schedule report")
for report in ("leave_schedule", "leave_plan_adherence"):
    if not os.path.exists(os.path.join(REPO, "hrms_addon", "hrms_addon", "report", report, report + ".py")):
        fail.append("the %s report is not there" % report)
schedule = read("hrms_addon", "hrms_addon", "report", "leave_schedule", "leave_schedule.py")
if "own = leave.own_place(frappe.session.user)" not in schedule:
    fail.append("an employee sees their own plant and department's schedule, as they see the plans")
if (hooks.get("permission_query_conditions") or {}).get("Annual Leave Plan") != \
        "hrms_addon.hrms_addon.leave.plan_query_conditions" or (hooks.get("has_permission") or {}).get(
        "Annual Leave Plan") != "hrms_addon.hrms_addon.leave.plan_has_permission":
    fail.append("an employee is shown the plans of their own plant and department, in the list and opened")
plan_js = read("hrms_addon", "hrms_addon", "doctype", "annual_leave_plan", "annual_leave_plan.js")
for method in ("get_employees", "request_change", "apply_from_plan", "inform_employees"):
    if 'HA_LEAVE + "%s"' % method not in plan_js:
        fail.append("the plan form calls leave.%s" % method)
# Get Employees adds people before their dates are known, and a mandatory
# table starts a new plan with an empty row, which stops the save it makes
# first: the rows and their dates are required when the plan is sent
plan_fields = fields_of(doctype("Annual Leave Plan"))
row_fields = fields_of(doctype("Annual Leave Plan Employee"))
if plan_fields["employees"].get("reqd") or row_fields["planned_from"].get("reqd") or \
        row_fields["planned_to"].get("reqd"):
    fail.append("the plan's rows and their dates are required when it is sent, not on every save")
if "frappe.model.clear_doc(row.doctype, row.name)" not in \
        plan_js.split("function ha_get_employees")[1].split(chr(10) + "function ")[0]:
    fail.append("Get Employees drops an empty row before it saves the plan")
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
# the advance goes onto the payroll when its payment is recorded: Frappe HR
# v16 refuses a deduction for more of an advance than has been paid out
# against it (Additional Salary.validate_employee_advance_return)
additional = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "additional_salary",
                          "additional_salary.py")
if not os.path.exists(additional) or "advance.paid_amount - advance.claimed_amount" not in \
        open(additional, encoding="utf-8").read():
    fail.append("Frappe HR no longer holds a deduction to what was paid out: look at schedule_recovery again")
payment_part = glue_advances.split("def schedule_recovery")[1].split(chr(10) + "def ")[0]
if 'flt(doc.get("paid_amount")) - flt(doc.get("claimed_amount")) - _scheduled(doc.name)' not in payment_part:
    fail.append("the recovery goes onto the payroll only as far as the recorded payment covers it")
if "schedule_recovery(doc)" not in glue_advances.split("def advance_on_submit")[1].split(chr(10) + "def ")[0]:
    fail.append("the Pay step schedules what the recorded payment covers, and no more")
def _handlers(value):
    return [value] if isinstance(value, str) else list(value or [])


for voucher in ("Payment Entry", "Journal Entry"):
    if "hrms_addon.hrms_addon.advances.payment_on_submit" not in _handlers((events.get(voucher) or {}).get("on_submit")) \
            or "hrms_addon.hrms_addon.advances.payment_on_cancel" not in _handlers(
                (events.get(voucher) or {}).get("on_cancel")):
        fail.append("a %s paying an advance puts it on the payroll, and cancelling it takes it off" % voucher)
if "_schedule_paid()" not in glue_advances.split("def daily")[1].split(chr(10) + "def ")[0]:
    fail.append("a paid advance whose payment nothing hooked is put on the payroll by the daily job")
if "ensure_recovery_account()" not in glue_advances.split("def setup_workflows_on_migrate")[1]:
    fail.append("the recovery component credits the employee advance account, so the payroll books it back")
print("the advance and the payroll: scheduled from the recorded payment, booked back against the advance")

print("wiring: the doc events, the two workflows on migrate, the daily jobs, the seed, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LEAVE AND ADVANCE CHECKS PASSED")
