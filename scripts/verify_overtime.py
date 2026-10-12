"""Verify overtime, without a bench:

    python scripts/verify_overtime.py

The Overtime Management sheet of Luuka's revised testing scripts, all five
cases: the types and their multipliers (1), capture from attendance (2),
the Supervisor to HOD to HR cost check (3), the feed into payroll (4), and
work on a leave day or public holiday as special overtime (5).

  1  what sort of day it is, and what that is worth
  2  what HR must have before the cost is accepted, and before it is paid
  3  the paper carries the day, the rate, the cost and where it went
  4  the glue reads and writes fields that exist, and really reaches
     Frappe HR's own Overtime Type and Overtime Slip rather than pricing
     the work itself
  5  wiring: the types seeded on migrate, the buttons whitelisted, the way in

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
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
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


R = load("overtime_rules")
A = load("attendance_rules")
hooks = hooks_dict()
print("loaded overtime_rules.py without Frappe")

# ── 1. The day, and what it is worth ──────────────────────────────────
if R.KINDS != ("Weekday", "Rest Day", "Public Holiday", "Leave Day"):
    fail.append("the four kinds of day: %s" % (R.KINDS,))
# the Employment Act's floor (Cap 219, s.53 and s.54)
if R.ACT_MULTIPLIERS[R.WEEKDAY] != 1.5:
    fail.append("overtime on a normal day is one and a half times")
for kind in (R.REST_DAY, R.PUBLIC_HOLIDAY):
    if R.ACT_MULTIPLIERS[kind] != 2.0:
        fail.append("work on a %s is twice" % kind.lower())

if R.kind_of_day({}) != R.WEEKDAY:
    fail.append("an ordinary day is a weekday")
if R.kind_of_day({"is_weekly_off": True}) != R.REST_DAY:
    fail.append("the employee's weekly off is a rest day")
if R.kind_of_day({"on_holiday_list": True}) != R.PUBLIC_HOLIDAY:
    fail.append("a day on their holiday list is a public holiday")
# a public holiday that falls on the weekly off is still their rest day
if R.kind_of_day({"on_holiday_list": True, "is_weekly_off": True}) != R.REST_DAY:
    fail.append("a holiday list carries the weekly offs too: a weekly off is a rest day")
# test case 5: work on a leave day is its own thing, whatever the date is
if R.kind_of_day({"on_leave": True}) != R.LEAVE_DAY:
    fail.append("test case 5: work on a leave day is special overtime")
if R.kind_of_day({"on_leave": True, "on_holiday_list": True}) != R.LEAVE_DAY:
    fail.append("being on leave is read before the calendar is")

# test case 1: the type on the site carries the policy, not this module
if R.multiplier_for(R.WEEKDAY) != 1.5:
    fail.append("with no type on the site the Act's floor stands")
site_type = {"standard_multiplier": 1.75, "applicable_for_weekend": 1, "weekend_multiplier": 2.5,
             "applicable_for_public_holiday": 1, "public_holiday_multiplier": 3.0}
if R.multiplier_for(R.WEEKDAY, site_type) != 1.75:
    fail.append("a weekday reads the type's standard multiplier")
if R.multiplier_for(R.REST_DAY, site_type) != 2.5:
    fail.append("a rest day reads the weekend multiplier")
if R.multiplier_for(R.PUBLIC_HOLIDAY, site_type) != 3.0:
    fail.append("a public holiday reads the holiday multiplier")
if R.multiplier_for(R.LEAVE_DAY, site_type) != 2.5:
    fail.append("a leave day is paid as a rest day")
off = {"standard_multiplier": 1.75, "applicable_for_weekend": 0,
       "applicable_for_public_holiday": 0}
if R.multiplier_for(R.PUBLIC_HOLIDAY, off) != 1.75:
    fail.append("a type that does not separate holidays pays its standard rate on one")
if not R.below_the_act(R.WEEKDAY, 1.25):
    fail.append("a rate under the Act must be noticed")
if R.below_the_act(R.WEEKDAY, 1.5) or R.below_the_act(R.WEEKDAY, None):
    fail.append("the floor itself is not below the floor")

# Luuka's month: 26 days of ten standard hours (attendance_rules)
if R.STANDARD_HOURS_PER_DAY != A.STANDARD_HOURS:
    fail.append("the standard day here and in attendance_rules must be the same: %s vs %s"
                % (R.STANDARD_HOURS_PER_DAY, A.STANDARD_HOURS))
if R.DAYS_PER_MONTH != 26:
    fail.append("the attendance cycle is twenty-six days")
# an hour is divided out of the shift's own standard day
if R.hours_per_month() != R.HOURS_PER_MONTH or R.hours_per_month(0) != 260.0 or R.hours_per_month("x") != 260.0:
    fail.append("a shift that gives no hours is priced on ten standard hours a day")
if R.hours_per_month(8) != 208.0:
    fail.append("an eight-hour day is 208 hours a month")
both = R.priced([{"employee": "E1", "hours": 2}, {"employee": "E2", "hours": 2}], {"E1": 1040000, "E2": 1040000},
                R.WEEKDAY, standards={"E1": 8})
if [row["hourly_rate"] for row in both["rows"]] != [5000.0, 4000.0]:
    fail.append("each person's hour comes out of their own shift's standard day: %s"
                % [row["hourly_rate"] for row in both["rows"]])
if R.hourly_rate(1040000) != 4000.0:
    fail.append("a million and forty thousand over 260 hours is four thousand an hour: %s"
                % R.hourly_rate(1040000))
if R.hourly_rate(None) != 0.0:
    fail.append("no base is no rate, not a crash")
if R.amount(3, 4000, 1.5) != 18000.0:
    fail.append("three hours at four thousand and a half again is eighteen thousand")
if R.amount(3, 0, 1.5) != 0.0:
    fail.append("no rate is no amount")
# the minutes of 16 and 20 July 2026, §4.12: a weekday pays 1x above a
# gross of UGX 500,000 and 1.5x below it; a public holiday 2x
if R.GROSS_THRESHOLD != 500000 or R.HIGHER_EARNER_MULTIPLIER != 1.0:
    fail.append("the line is UGX 500,000, and above it a weekday pays 1x")
BASIC = {"salary_component": "Basic", "formula": "(base * 1)", "amount_based_on_formula": 1}
if not R.works_from_base(BASIC):
    fail.append("Luuka's Basic (base * 1) is what an hour of overtime is worked out of")
for row, why in ((dict(BASIC, formula="BS + MA + CB"), "a formula without the base"),
                 (dict(BASIC, statistical_component=1), "a statistical component"),
                 (dict(BASIC, amount_based_on_formula=0), "an earning not worked out by formula"),
                 (dict(BASIC, formula="baseline * 2"), "a word that only starts with base")):
    if R.works_from_base(row):
        fail.append("not worked out of: %s" % why)
EARNINGS = [{"name": "Basic", "salary_component_abbr": "B"}, {"name": "Overtime", "salary_component_abbr": "OT"},
            {"name": "Overtime 1.5", "salary_component_abbr": "OT_15"},
            {"name": "Overtime 2.0", "salary_component_abbr": "OT_20"}]
for rate, component in ((1.5, "Overtime 1.5"), (2.0, "Overtime 2.0"), (1.0, None)):
    if R.component_for_rate(rate, EARNINGS) != component:
        fail.append("the overtime earning for %sx is %s, not %s" % (rate, component, R.component_for_rate(rate, EARNINGS)))
if R.component_for_rate(2.0, [{"name": "Holiday Pay", "salary_component_abbr": "OT_20"}]) != "Holiday Pay":
    fail.append("an overtime earning is found by its abbreviation too")
if R.component_for_rate(2.0, [{"name": "Allowance 2.0", "salary_component_abbr": "AL2"}]) is not None:
    fail.append("an earning that is not overtime is never an overtime type's")
LINES = {R.HIGHER_EARNERS: 500000}
if R.type_name_for(R.WEEKDAY, 600000, LINES) != R.HIGHER_EARNERS:
    fail.append("a weekday for somebody grossing 600,000 goes under the higher earners' type")
if R.type_name_for(R.WEEKDAY, 500000, LINES) != R.TYPE_NAMES[R.WEEKDAY]:
    fail.append("and one for somebody at exactly 500,000 does not: the minutes say 'above'")
if R.type_name_for(R.PUBLIC_HOLIDAY, 900000, LINES) != R.TYPE_NAMES[R.PUBLIC_HOLIDAY]:
    fail.append("a public holiday pays its own rate whatever the gross")
if R.type_name_for(R.WEEKDAY, None, LINES) != R.TYPE_NAMES[R.WEEKDAY]:
    fail.append("with no gross known, a weekday is an ordinary weekday")
if R.type_name_for(R.WEEKDAY, 600000, {R.HIGHER_EARNERS: 700000}) != R.TYPE_NAMES[R.WEEKDAY]:
    fail.append("the line is the type's: moved to 700,000, a gross of 600,000 is under it")
if R.type_name_for(R.WEEKDAY, 1200000, {R.HIGHER_EARNERS: 500000, "Senior": 1000000}) != "Senior":
    fail.append("with more than one line, the highest one the gross is above")
if R.gross_lines({"A": {"custom_gross_above": 500000}, "B": {"custom_gross_above": 0}, "C": None}) != {"A": 500000.0}:
    fail.append("only the types with a line are lines")
TYPES = {"Weekday Overtime": {"standard_multiplier": 1.5},
         R.HIGHER_EARNERS: {"standard_multiplier": 1.0, "custom_gross_above": 500000}}
costed = R.priced([{"employee": "HIGH", "hours": 2}, {"employee": "LOW", "hours": 2}],
                  {"HIGH": 400000, "LOW": 260000}, R.WEEKDAY, TYPES["Weekday Overtime"], TYPES,
                  {"HIGH": 2600000, "LOW": 260000})
rows = {row["employee"]: row for row in costed["rows"]}
if rows["HIGH"]["multiplier"] != 1.0 or rows["LOW"]["multiplier"] != 1.5:
    fail.append("each person on a request is priced under their own gross's type, not their base: %s"
                % {k: v["multiplier"] for k, v in rows.items()})
if rows["HIGH"]["hourly_rate"] != R.hourly_rate(400000):
    fail.append("while an hour of their pay is worked out of the base")
if R.attendance_update({"hours": 2}, R.WEEKDAY, 10, gross=2600000, lines=LINES)["overtime_type"] != R.HIGHER_EARNERS:
    fail.append("and their attendance carries that type, so the Overtime Slip pays it — not only the "
                "cost check")
print("the day: read, not typed, and priced at the Act's floor or the type's own rate")

# who an Overtime Type is for: the employees it lists, the departments it is not paid to, its gross line
OPEN = {"Weekday Overtime": {"standard_multiplier": 1.5},
        "Rest Day Overtime": {"standard_multiplier": 2.0},
        R.HIGHER_EARNERS: {"standard_multiplier": 1.0, "custom_gross_above": 500000,
                           "excluded_departments": ["Stores - LPL"]},
        "Special Overtime": {"standard_multiplier": 1.25, "employees": ["E7", "E8"]},
        "Drivers Overtime": {"standard_multiplier": 1.1, "custom_gross_above": 300000, "employees": ["E8"]}}
for label, got, want in (
    ("an ordinary weekday", R.person_type(R.WEEKDAY, 260000, OPEN, "E1", "Extrusion - LPL"), ("Weekday Overtime", None)),
    ("above the line", R.person_type(R.WEEKDAY, 900000, OPEN, "E1", "Extrusion - LPL"), (R.HIGHER_EARNERS, None)),
    ("above the line in a department the higher earners' type is not paid to: the ordinary weekday's",
     R.person_type(R.WEEKDAY, 900000, OPEN, "E2", "Stores - LPL"), ("Weekday Overtime", None)),
    ("somebody a type lists is paid under it, whatever the day or their gross",
     R.person_type(R.REST_DAY, 900000, OPEN, "E7", "Extrusion - LPL"), ("Special Overtime", None)),
    ("listed on two: on a weekday the one whose line their gross is above",
     R.person_type(R.WEEKDAY, 400000, OPEN, "E8", "Transport - LPL"), ("Drivers Overtime", None)),
    ("listed on two, under that line: the first of theirs, never one that does not list them",
     R.person_type(R.WEEKDAY, 200000, OPEN, "E8", "Transport - LPL"), ("Drivers Overtime", None)),
    ("a type that lists people is nobody else's, even above its line",
     R.person_type(R.WEEKDAY, 400000, OPEN, "E1", "Extrusion - LPL"), ("Weekday Overtime", None)),
    ("a day's type the site does not have is no matter of eligibility",
     R.person_type(R.PUBLIC_HOLIDAY, 260000, OPEN, "E1", "Extrusion - LPL"), (R.TYPE_NAMES[R.PUBLIC_HOLIDAY], None)),
    ("with nobody and no types, the day's own", R.person_type(R.WEEKDAY, None, None), ("Weekday Overtime", None)),
):
    if got != want:
        fail.append("who a type is for: %s: %s, not %s" % (label, got, want))
closed = dict(OPEN, **{"Weekday Overtime": {"standard_multiplier": 1.5, "excluded_departments": ["Stores - LPL"]},
                       "Rest Day Overtime": {"standard_multiplier": 2.0, "employees": ["E9"]}})
if R.person_type(R.WEEKDAY, 260000, closed, "E2", "Stores - LPL") != (None, "Weekday Overtime is not paid to Stores - LPL."):
    fail.append("a department the day's type is not paid to has no overtime that day, and is told which type: %s"
                % (R.person_type(R.WEEKDAY, 260000, closed, "E2", "Stores - LPL"),))
if R.person_type(R.REST_DAY, 260000, closed, "E1", "Extrusion - LPL") != (
        None, "Rest Day Overtime is only for the employees it lists."):
    fail.append("a day's type that lists people is closed to everybody else")
if R.person_type(R.REST_DAY, 260000, closed, "E9", "Extrusion - LPL") != ("Rest Day Overtime", None):
    fail.append("and open to those it lists")
judged = R.priced([{"employee": "E2", "employee_name": "Ben", "hours": 2}, {"employee": "E7", "hours": 2},
                   {"employee": "E1", "hours": 2}],
                  {"E2": 260000, "E7": 260000, "E1": 260000}, R.WEEKDAY, closed["Weekday Overtime"], closed,
                  {"E2": 260000, "E7": 260000, "E1": 900000}, None, None,
                  {"E2": "Stores - LPL", "E7": "Extrusion - LPL", "E1": "Extrusion - LPL"})
seen = [(row["employee"], row["overtime_type"], row["multiplier"], row["amount"] > 0) for row in judged["rows"]]
if seen != [("E2", None, 0.0, False), ("E7", "Special Overtime", 1.25, True), ("E1", R.HIGHER_EARNERS, 1.0, True)]:
    fail.append("a request is priced by who each type is for: nobody is paid under a type closed to them: %s" % seen)
if R.eligibility_errors(judged["rows"]) != [
        "Ben is not eligible for this overtime: Weekday Overtime is not paid to Stores - LPL."]:
    fail.append("and the one no type is open to is named, with why: %s" % R.eligibility_errors(judged["rows"]))
expect("costing somebody no type is open to", R.cost_check_errors(
    {"status": "Authorised", "rows": judged["rows"], "unpriced": [], "not_eligible": R.eligibility_errors(judged["rows"])}),
    "Ben is not eligible for this overtime")
if R.attendance_update({"hours": 2}, R.WEEKDAY, 10, hours=1.5, named="Special Overtime") != {
        "overtime_type": "Special Overtime", "actual_overtime_duration": 1.5, "standard_working_hours": 10.0}:
    fail.append("the attendance carries the type chosen for the person, so the Overtime Slip pays under it")
print("eligibility: a type's own employees, the departments it leaves out, and its gross line")

# ── 2. Pricing a request, and the two gates ───────────────────────────
rows = [{"employee": "HR-EMP-1", "employee_name": "A", "hours": 3},
        {"employee": "HR-EMP-2", "employee_name": "B", "hours": 2}]
costed = R.priced(rows, {"HR-EMP-1": 1040000, "HR-EMP-2": 520000}, R.WEEKDAY)
if costed["total"] != 18000.0 + 6000.0:
    fail.append("the request totals its rows: %s" % costed["total"])
if costed["multiplier"] != 1.5:
    fail.append("at the day's rate")
if costed["unpriced"]:
    fail.append("both were priced")
unpaid = R.priced(rows, {"HR-EMP-1": 1040000}, R.WEEKDAY)
if unpaid["unpriced"] != ["B"]:
    fail.append("somebody with no salary on record is named, not dropped: %s" % unpaid)
if len(unpaid["rows"]) != 2:
    fail.append("and their row is still shown, at nothing")
holiday = R.priced(rows, {"HR-EMP-1": 1040000, "HR-EMP-2": 520000}, R.PUBLIC_HOLIDAY)
if holiday["total"] <= costed["total"]:
    fail.append("a public holiday costs more than a weekday")

good = {"status": "Authorised", "rows": costed["rows"], "unpriced": []}
expect("a proper cost check", R.cost_check_errors(good))
expect("costing before the officer signed", R.cost_check_errors(dict(good, status="Requested")),
       "once the authorising officer has signed")
expect("costing with nobody on it", R.cost_check_errors(dict(good, rows=[])), "nobody on the request")
expect("costing somebody with no salary", R.cost_check_errors(dict(good, unpriced=["B"])),
       "no salary on record for B")

paid = {"status": "Costed", "rows": [dict(row, attendance="HR-ATT-1") for row in rows]}
expect("a proper hand-off", R.payroll_errors(paid))
expect("paying before HR costed it", R.payroll_errors(dict(paid, status="Authorised")),
       "after HR have checked")
expect("paying hours with no attendance to sit on",
       R.payroll_errors(dict(paid, rows=[dict(rows[0], attendance=None)])),
       "no attendance for A")
expect("paying overtime on a day nobody clocked in",
       R.payroll_errors(dict(paid, rows=[dict(rows[0], attendance="HR-ATT-1", absent=True)])),
       "A did not clock in")
expect("or on a day marked half a day, which the Overtime Slip does not read",
       R.payroll_errors(dict(paid, rows=[dict(rows[0], attendance="HR-ATT-1", status="Half Day"),
                                         dict(rows[1], attendance="HR-ATT-2", status="Present")])),
       "which it does not for A (Half Day)")
slip = open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "overtime_slip", "overtime_slip.py"),
            encoding="utf-8").read() if os.path.isdir(os.path.join(APPS_ROOT, "hrms")) else None
if slip is not None and '"status": "%s",' % R.PAID_ON not in slip.split("def get_attendance_records(")[1].split(
        "\n\tdef ")[0]:
    fail.append("Frappe HR's Overtime Slip no longer reads only an attendance marked %s: see what it reads now"
                % R.PAID_ON)
expect("or clocked in and never out",
       R.payroll_errors(dict(paid, rows=[dict(rows[1], attendance="HR-ATT-2", absent=True, clocked_in=True)])),
       "B clocked in on that day with no clock-out")

# a type the site does not have, and what an employee's requests still wait for
said = R.missing_type_error({"Weekday Overtime", "Rest Day Overtime"})
if said != ("There is no Overtime Type named Rest Day Overtime and Weekday Overtime, so the Overtime Slip could not "
            "pay these hours. Add it under Overtime Type first."):
    fail.append("hours that would go under a type the site does not have are refused, the type named: %s" % said)
waits = R.waiting([
    {"name": "OT-3", "overtime_date": "2026-09-10", "hours": 2, "status": "Costed"},
    {"name": "OT-1", "overtime_date": "2026-09-03", "hours": 3, "status": "Requested"},
    {"name": "OT-2", "overtime_date": "2026-09-05", "hours": 1.5, "status": "Authorised"},
    {"name": "OT-4", "overtime_date": "2026-09-12", "hours": 2, "status": "Sent to Payroll"},
    {"name": "OT-5", "overtime_date": "2026-09-13", "hours": 2, "status": "Rejected"},
    {"name": "OT-6", "overtime_date": "2026-09-14", "hours": 2, "status": "Cancelled"},
    {"name": "OT-0", "overtime_date": "2026-09-01", "hours": 4, "status": None}])
if [(row["name"], row["status"], row["next"]) for row in waits] != [
        ("OT-0", "Draft", "Submit"), ("OT-1", "Requested", "Authorise"), ("OT-2", "Authorised", "Check the Cost"),
        ("OT-3", "Costed", "Send to Payroll")]:
    fail.append("a request not yet with payroll is named with the step it waits for, oldest first; one sent, rejected "
                "or cancelled waits for nothing: %s" % [(row["name"], row["status"], row["next"]) for row in waits])
if waits[2]["hours"] != 1.5 or R.waiting(None) != [] or R.waiting([]) != []:
    fail.append("with its hours; and nothing waits where there is no request")
if set(R.NEXT_STEP) | {"Sent to Payroll", "Rejected", "Cancelled"} != set(R.STATUSES):
    fail.append("every status either waits for a step or is finished: %s" % sorted(R.NEXT_STEP))

# what is paid: the hours authorised, up to what the clock shows
for why, got, want in (
    ("a working day's overtime is what is worked past the standard hours", R.worked_overtime(R.WEEKDAY, 12, 10), 2.0),
    ("on the shift's own standard hours", R.worked_overtime(R.WEEKDAY, 9.5, 8), 1.5),
    ("none where they were not reached", R.worked_overtime(R.WEEKDAY, 9, 10), 0.0),
    ("every hour of a rest day", R.worked_overtime(R.REST_DAY, 6, 10), 6.0),
    ("of a public holiday", R.worked_overtime(R.PUBLIC_HOLIDAY, 5.5, 10), 5.5),
    ("and of a day of leave", R.worked_overtime(R.LEAVE_DAY, 4, 10), 4.0),
    ("no more than was authorised", R.payable_hours(2, 3.5), 2.0),
    ("what the clock shows where it shows less", R.payable_hours(3, 1.5), 1.5),
    ("in full within a quarter of an hour", R.payable_hours(2, 1.75), 2.0),
    ("not beyond it", R.payable_hours(2, 1.74), 1.74),
    ("nothing where the clock shows none", R.payable_hours(2, 0), 0.0),
    ("as authorised where the clock did not measure the day", R.payable_hours(2, None), 2.0),
):
    if got != want:
        fail.append("%s: expected %s, got %s" % (why, want, got))
if R.attendance_update({"hours": 3}, R.WEEKDAY, hours=1.5)["actual_overtime_duration"] != 1.5 \
        or R.attendance_update({"hours": 3}, R.WEEKDAY)["actual_overtime_duration"] != 3.0:
    fail.append("the attendance carries the hours paid, or those authorised where nothing else is said")
own_day = R.priced([{"employee": "E1", "hours": 2}, {"employee": "E2", "hours": 2}],
                   {"E1": 1040000, "E2": 1040000}, R.WEEKDAY, kinds={"E2": R.REST_DAY})
if [(row["day_kind"], row["multiplier"]) for row in own_day["rows"]] != [
        (R.WEEKDAY, R.ACT_MULTIPLIERS[R.WEEKDAY]), (R.REST_DAY, R.ACT_MULTIPLIERS[R.REST_DAY])]:
    fail.append("one person's rest day is another's working day, and each is priced as their own: %s"
                % [(row["day_kind"], row["multiplier"]) for row in own_day["rows"]])
for status in ("Requested", "Authorised", "Costed"):
    expect("refusing overtime that is %s" % status, R.reject_errors(status, "No budget."))
expect("refusing overtime already with the payroll", R.reject_errors("Sent to Payroll", "No budget."),
       "before it reaches the payroll")
expect("refusing a draft", R.reject_errors(None, "No budget."), "before it reaches the payroll")
expect("refusing without saying why", R.reject_errors("Requested", " "), "Say why")
request_line = fields_of(doctype("Overtime Request Employee"))
for fieldname in ("day_kind", "overtime_type", "multiplier", "worked_hours", "clocked", "payable_hours"):
    if not (request_line.get(fieldname) or {}).get("read_only"):
        fail.append("Overtime Request Employee.%s is the system's to fill, and read only" % fieldname)
if (request_line.get("overtime_type") or {}).get("options") != "Overtime Type" \
        or not (request_line.get("overtime_type") or {}).get("in_list_view"):
    fail.append("each line shows the Overtime Type that person falls under, Frappe HR's own")
if (request_line.get("clocked") or {}).get("fieldtype") != "Check" \
        or (request_line.get("worked_hours") or {}).get("fieldtype") != "Float":
    fail.append("a line says whether the clock measured the day: its hours by the clock are a number, which "
                "cannot be left empty")

if not R.over_the_cap(20, 16) or R.over_the_cap(12, 16) or R.over_the_cap(99, 0):
    fail.append("the type's ceiling is compared, and no ceiling is no complaint")
print("the two gates: the cost is checked before it is paid, and nothing is paid unattended")

# ── 3. What goes onto the attendance ──────────────────────────────────
# test cases 2 and 4: Frappe HR's Overtime Slip reads the Attendance row,
# so that is what the authorised hours are written onto
update = R.attendance_update({"hours": 3}, R.PUBLIC_HOLIDAY)
attendance = fields_of(upstream_doctype("Attendance"))
for fieldname in update:
    if fieldname not in attendance:
        fail.append("Attendance has no %s: the overtime slip would never see the hours"
                    % fieldname)
if update["overtime_type"] != R.type_name_for(R.PUBLIC_HOLIDAY):
    fail.append("the row carries the type the day falls under")
if update["actual_overtime_duration"] != 3.0:
    fail.append("and the hours authorised")
slip = fields_of(upstream_doctype("Overtime Slip"))
for fieldname in ("employee", "start_date", "end_date", "overtime_details"):
    if fieldname not in slip:
        fail.append("Overtime Slip has no %s" % fieldname)
details = fields_of(upstream_doctype("Overtime Details"))
for fieldname in ("reference_document", "overtime_type", "overtime_duration"):
    if fieldname not in details:
        fail.append("Overtime Details has no %s" % fieldname)
overtime_type = fields_of(upstream_doctype("Overtime Type"))
for fieldname in ("standard_multiplier", "weekend_multiplier", "public_holiday_multiplier",
                  "overtime_salary_component", "maximum_overtime_hours_allowed"):
    if fieldname not in overtime_type:
        fail.append("Overtime Type has no %s: test case 1 is not theirs after all" % fieldname)
window = R.slip_window("2026-05-26", "2026-06-25")
if window != {"start_date": "2026-05-26", "end_date": "2026-06-25"}:
    fail.append("a slip covers the attendance cycle: %s" % window)
print("capture and payment: Frappe HR's own Attendance, Overtime Type and Overtime Slip")

# ── 4. The paper ──────────────────────────────────────────────────────
request = fields_of(doctype("Overtime Request"))
for fieldname in ("day_kind", "total_cost",
                  "costed_by", "costed_on", "cost_remarks", "over_the_cap",
                  "sent_to_payroll_on"):
    if fieldname not in request:
        fail.append("the overtime request has no %s" % fieldname)
for fieldname in ("day_kind", "total_cost", "over_the_cap"):
    if not request.get(fieldname, {}).get("read_only"):
        fail.append("%s is worked out, not typed: it must be read-only" % fieldname)
# each person is paid at their own rate, under their own type: the sheet has neither (12 Oct 2026, Luuka:
# "where did the multiplier of 1.5 come from ... each employee qualifies for multiplier different")
if "overtime_type" in request or "multiplier" in request:
    fail.append("the request's header names no Overtime Type and no rate: each line carries its own")
# no cost centre is asked for (12 Oct 2026): nothing read it, and payroll posts
# overtime to the employee's own payroll cost centre
if "cost_centre" in request or "cost_centre" in read("hrms_addon", "hrms_addon", "overtime.py") \
        or "cost_centre" in read("hrms_addon", "hrms_addon", "overtime_rules.py") \
        or "cost_centre" in read("hrms_addon", "hrms_addon", "doctype", "overtime_request", "overtime_request.js"):
    fail.append("the cost check asks for no cost centre: the field, the question and the rule are gone")
statuses = (request.get("status", {}).get("options") or "").split("\n")
for status in R.STATUSES:
    if status not in statuses:
        fail.append("the request cannot reach %s" % status)
if statuses.index("Costed") < statuses.index("Authorised"):
    fail.append("the cost is checked after the authority signs, not before")
row = fields_of(doctype("Overtime Request Employee"))
for fieldname in ("hourly_rate", "amount", "attendance"):
    if fieldname not in row:
        fail.append("a name on the request has no %s" % fieldname)
if row.get("attendance", {}).get("options") != "Attendance":
    fail.append("each row remembers the attendance its hours were written onto")
print("the paper: the day, the rate, the cost and where it went")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "overtime.py")
known = set(request) | set(row) | {"doctype", "name", "docstatus", "employee", "company",
                                   "flags", "employees"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update", "name"):
        continue
    if fieldname not in known:
        fail.append("overtime.py reads or writes %s, which is not on the request" % fieldname)
for needle, why in (
    ("rules.kind_of_day(", "what sort of day it is comes from the rules (case 5)"),
    ("rules.multiplier_for(", "and what that is worth (case 1)"),
    ("rules.priced(", "the request is priced for the cost check (case 3)"),
    ("rules.cost_check_errors(", "which has to be complete before HR sign it"),
    ("rules.payroll_errors(", "and complete again before it is paid (case 4)"),
    ("rules.attendance_update(", "the hours go onto the attendance (case 2)"),
    ("Salary Structure Assignment", "an hour of pay comes off the employee's own base"),
    ('"Holiday"', "a public holiday is read from the holiday list, not guessed"),
    ("Leave Application", "and a leave day from the leave itself (case 5)"),
    ("SLIP", "the slip is Frappe HR's, and it is really drawn"),
    ("attendance_rules.cycle_window", "over the attendance cycle it belongs to"),
):
    if needle not in glue:
        fail.append("overtime.py: %s (%r not found)" % (why, needle))
# Nothing here prices the payslip itself: that is the slip's job. The
# prose says so, so the check reads the code with the docstrings taken
# out rather than the file as written.
def code_only(source):
    tree = ast.parse(source)
    lines = source.split("\n")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if not (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            continue
        for number in range(body[0].lineno - 1, body[0].end_lineno):
            lines[number] = ""
    return "\n".join(line.split("#")[0] for line in lines)


body = code_only(glue)
for forbidden, why in (
    ("Additional Salary", "the Overtime Slip writes the Additional Salary, not this module"),
    ("Salary Slip", "and nothing here touches a payslip"),
):
    if forbidden in body:
        fail.append("overtime.py: %s (%r found in the code)" % (why, forbidden))
for name in ("cost_check", "send_to_payroll"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("overtime.%s changes something: a whitelisted POST method" % name)
if glue.count("check_permission(") < 2:
    fail.append("each whitelisted method must check the caller may act")
if "fill_day_and_rate" not in read("hrms_addon", "hrms_addon", "attendance.py"):
    fail.append("the request must learn what day it falls on as it validates")
landed = glue.split("def send_to_payroll(")[1].split(chr(10) + "def ")[0]
if "rules.person_type(theirs, grosses.get(row[\"employee\"]), types, row[\"employee\"]," not in landed \
        or "hours=paid, named=named)" not in landed:
    fail.append("the hours land on each attendance under the type their own gross puts them in, or "
                "the Overtime Slip pays a higher earner one and a half times (minutes §4.12)")
if "rules.HIGHER_EARNERS" not in glue.split("def seed_overtime_types(")[1].split(chr(10) + "def ")[0]:
    fail.append("the higher earners' weekday type is made on migrate")
seeding = glue.split("def seed_overtime_types(")[1].split(chr(10) + "def ")[0]
if "_hourly_components()" not in seeding or '"applicable_salary_component": [' not in glue:
    fail.append("an Overtime Type priced from salary components is refused without them: the seeding gives them")
if "gross_above=rules.GROSS_THRESHOLD" not in seeding \
        or "fill_gross_line()" not in glue.split("def setup_on_migrate(")[1]:
    fail.append("the higher earners' type carries its line, UGX 500,000 until HR move it")
if "pay.monthly_gross(employee, day)" not in glue.split("def _monthly_gross(")[1].split(chr(10) + "def ")[0]:
    fail.append("the line is compared with the gross the salary structure works out, not the base")
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
line_field = custom.get("Overtime Type-custom_gross_above") or {}
if line_field.get("fieldtype") != "Currency" or '"Overtime Type-custom_gross_above"' not in read("hrms_addon", "hooks.py"):
    fail.append("the line is a field on the Overtime Type, synced with the fixtures")
# who a type is for is kept on the type, and read with every type
tab = [custom.get("Overtime Type-%s" % name) or {} for name in (
    "custom_eligibility_tab", "custom_gross_above", "custom_excluded_departments", "custom_employees_section",
    "custom_employees")]
if [(row.get("fieldtype"), row.get("insert_after")) for row in tab] != [
        ("Tab Break", "weekend_multiplier"), ("Currency", "custom_eligibility_tab"),
        ("Table MultiSelect", "custom_gross_above"), ("Section Break", "custom_excluded_departments"),
        ("Table", "custom_employees_section")]:
    fail.append("the Overtime Type has an Eligibility tab: its gross line, the departments it is not paid to, then "
                "the employees it lists, each field after the one before: %s"
                % [(row.get("fieldtype"), row.get("insert_after")) for row in tab])
if (tab[2].get("options"), tab[4].get("options"), tab[0].get("label")) != (
        "Overtime Type Department", "Overtime Type Employee", "Eligibility"):
    fail.append("its tables are the app's own two")
for name in ("custom_eligibility_tab", "custom_excluded_departments", "custom_employees_section", "custom_employees"):
    if '"Overtime Type-%s"' % name not in read("hrms_addon", "hooks.py"):
        fail.append("hooks fixtures list Overtime Type-%s" % name)
listed = fields_of(doctype("Overtime Type Employee"))
left_out = fields_of(doctype("Overtime Type Department"))
if (listed.get("employee", {}).get("options"), listed.get("employee", {}).get("reqd")) != ("Employee", 1) \
        or list(left_out) != ["department"] or left_out["department"].get("options") != "Department":
    fail.append("a type lists employees, and leaves out departments, by link")
reading = glue.split("def _types_for(")[1].split(chr(10) + "def ")[0]
if 'frappe.get_all(TYPE, pluck="name", limit_page_length=0)' not in reading \
        or '("Overtime Type Employee", "employees", "employee")' not in reading \
        or '("Overtime Type Department", "excluded_departments", "department")' not in reading:
    fail.append("every Overtime Type is read with the employees it lists and the departments it leaves out")
rated_by = glue.split("def fill_day_and_rate(")[1].split(chr(10) + "def ")[0]
if "return rules.eligibility_errors(rated)" not in rated_by or "_departments(people_on_it))[\"rows\"]" not in rated_by:
    fail.append("a request's lines are rated by who each type is for, and those no type is open to are reported")
raising = read("hrms_addon", "hrms_addon", "attendance.py").split("def overtime_validate(")[1].split(chr(10) + "def ")[0]
if "closed = overtime.fill_day_and_rate(doc) or []" not in raising or "errors += closed" not in raising:
    fail.append("somebody no Overtime Type is open to is refused when the request is raised")
if "if closed:\n        frappe.throw(" not in landed:
    fail.append("and never sent to payroll under a type closed to them since")
print("glue: the day read, the cost checked, the hours landed, the slip drawn")

for needle, why in (
    ("attendance.shift_hours_of(attendance.shift_on(employee, day), hours)[\"standard\"]",
     "the standard day is the one of the shift worked that day"),
    ("_standard_hours(people_on_it, doc.overtime_date), kinds, _departments(people_on_it))",
     "HR's cost check prices each person on their own shift, and their own kind of day"),
    ('row.day_kind = found["day_kind"] if row.employee else None', "each line reads the day for its own employee"),
    ('row.overtime_type = found["overtime_type"] if row.employee else None',
     "and carries the Overtime Type that person falls under"),
    ('row.multiplier = found["multiplier"] if row.employee else 0', "and its rate, before anybody signs"),
    ("rules.worked_overtime(theirs, found.working_hours, standard)", "the overtime the clock shows is worked out"),
    ("if (found.in_time and found.out_time) else None", "only for a day the clock measured at both ends"),
    ("paid = rules.payable_hours(row.get(\"hours\"), worked)", "what is paid is the rules' answer"),
    ("hours=paid, named=named)", "and that, not what was authorised, goes onto the attendance"),
    ('line.db_set({"day_kind": theirs, "worked_hours": flt(worked), "clocked": 0 if worked is None else 1,',
     "the line says what the clock showed, as a number, and whether it measured the day at all"),
    ('"payable_hours": paid}, update_modified=False)', "and what was paid"),
    ('absent=bool(found) and found.status == "Absent",', "a day that reads absent is told to the rules"),
    ("status=found.status if found else None,", "and what any other day reads"),
    ("if found and row.attendance != found.name:", "the line points at the attendance that stands"),
    ("standards.get(row[\"employee\"]) or attendance_rules.STANDARD_HOURS",
     "and the attendance carries that standard day for the Overtime Slip"),
):
    if needle not in glue:
        fail.append("overtime.py: %s (%r not found)" % (why, needle))

# ── 6. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.overtime.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("the three overtime types must be seeded on every migrate")
if "warn_below_the_act" not in glue:
    fail.append("a rate edited under the Act is said out loud on the deploy")
form = read("hrms_addon", "hrms_addon", "doctype", "overtime_request", "overtime_request.js")
if '["Requested", "Authorised", "Costed"].includes(frm.doc.status)' not in form:
    fail.append("the form offers Reject while the overtime is being decided, and not after")
for needle in ("overtime.cost_check", "overtime.send_to_payroll"):
    if needle not in form:
        fail.append("the form has no way to call %s" % needle)
# the hours reach Frappe HR's slip, or it is said why not
for status, step in R.NEXT_STEP.items():
    if status != "Draft" and 'frm.add_custom_button(__("%s")' % step not in form:
        fail.append("the step a request at %s waits for is a button on its form: %s" % (status, step))
if 'frm.doc.docstatus === 1 && frm.doc.status === "Requested") {\n\t\t\tfrm.set_intro(' not in form \
        or "Waiting to be authorised." not in form:
    fail.append("a requested overtime says on its form that it waits to be authorised")
filled = glue.split("def fill_day_and_rate(")[1].split(chr(10) + "def ")[0]
if "doc.overtime_type" in glue or "doc.multiplier" in glue or "rules.priced(" not in filled:
    fail.append("no rate is written on the request's header: the lines are rated by the same rules that cost them")
costing = glue.split("def cost_check(")[1].split(chr(10) + "def ")[0]
if 'row.get("hours"), (types.get(row.get("overtime_type")) or {}).get("maximum_overtime_hours_allowed"))' not in costing:
    fail.append("the ceiling is checked on each person's hours against their own Overtime Type")
back = glue.split("def take_back(")[1].split(chr(10) + "def ")[0]
for needle, why in (
    ('if not names or not doc.get("sent_to_payroll_on"):', "only what the request itself sent to payroll"),
    ("paid = [slip for slip in slips if stands[slip] == 1]",
     "a submitted Overtime Slip that paid the hours stops the cancel"),
    ("kept = [line for line in slip.get(\"overtime_details\") or [] if line.reference_document not in names]",
     "a draft slip loses the line, and keeps its others"),
    ("slip.total_overtime_duration = sum(flt(line.overtime_duration) for line in kept)", "and its total follows"),
    ('{"overtime_type": None, "actual_overtime_duration": 0}', "and the attendance its overtime, the hours as 0"),
):
    if needle not in back:
        fail.append("overtime.take_back: %s" % why)
if back.index("frappe.throw(") > back.index("slip.save()"):
    fail.append("overtime.take_back refuses before it takes anything back")
cancelled = read("hrms_addon", "hrms_addon", "attendance.py").split("def overtime_on_cancel(")[1].split(chr(10) + "def ")[0]
if "overtime.take_back(doc)" not in cancelled:
    fail.append("a cancelled request takes its hours back off the attendance, or they would still be paid")
if 'values.pop("overtime_type")' in glue:
    fail.append("hours are never written onto an attendance without their Overtime Type: the slip does not read them")
if "    if _missing_types(plans):\n        seed_overtime_types()\n        plans = planned()" not in landed \
        or "frappe.throw(_(rules.missing_type_error(missing))" not in landed:
    fail.append("a type the site does not have is made as the migrate makes it, and the hand-off refused where it cannot be")
elif landed.index("frappe.throw(_(rules.missing_type_error(missing))") > landed.index('frappe.db.set_value("Attendance"'):
    fail.append("the hand-off is refused before anything is written")
note = glue.split("def waiting(")[1].split(chr(10) + "def ")[0]
if not re.search(r"@frappe\.whitelist\(\)\ndef waiting\(employee=None, start_date=None, end_date=None\):", glue):
    fail.append("overtime.waiting is whitelisted, changes nothing, and has no typed argument")
for needle, why in (('frappe.has_permission(REQUEST, "read")', "only for somebody who may read overtime requests"),
                    ("frappe.get_list(REQUEST", "and only the requests they may read"),
                    ('"docstatus": ["<", 2]', "never a cancelled one"),
                    ('"overtime_date": ["between", [getdate(start_date), getdate(end_date)]]', "in the slip's own dates"),
                    ("rules.waiting(", "judged by the rules")):
    if needle not in note:
        fail.append("overtime.waiting: %s (%r)" % (why, needle))
stamp = glue.split("def stamp_untyped(")[1].split(chr(10) + "def ")[0]
for needle, why in (('"overtime_type": ["is", "not set"]', "only an attendance with no type"),
                    ('"actual_overtime_duration": [">", 0]', "that carries overtime"),
                    ('"docstatus": 1, "status": rules.PAID_ON', "submitted and on a day the slip reads"),
                    ('request.status != "Sent to Payroll"', "written by a request that was sent to payroll"),
                    ("if name and frappe.db.exists(TYPE, name):", "and only under a type the site has")):
    if needle not in stamp:
        fail.append("overtime.stamp_untyped: %s (%r)" % (why, needle))
if "stamp_untyped()" not in glue.split("def setup_on_migrate(")[1]:
    fail.append("hours sent while their type was missing are put under it on migrate")
if hooks.get("doctype_js", {}).get("Overtime Slip") != "public/js/overtime_slip.js":
    fail.append("the Overtime Slip's form says what overtime has not reached payroll")
slip_form = read("hrms_addon", "public", "js", "overtime_slip.js")
for needle, why in (('method: "hrms_addon.hrms_addon.overtime.waiting"', "asks overtime.waiting"),
                    ("doc.docstatus !== 0 || !doc.employee || !doc.start_date || !doc.end_date", "once it has all three, on a draft"),
                    ('frappe.ui.form.on("Overtime Slip", {', "on Frappe HR's own form"),
                    ("frappe.utils.escape_html", "escaping what it prints"),
                    ("/app/overtime-request/${encodeURIComponent(row.name)}", "with a way to the request"),
                    ('__("Next: {0}", [cell(__(row.next))])', "and the step it waits for")):
    if needle not in slip_form:
        fail.append("overtime_slip.js: %s (%r)" % (why, needle))
request_spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", "overtime_request", "overtime_request.json"))
asked = {"Production Manager", "Head of Department"}
may = {row["role"] for row in request_spec["permissions"] if row.get("submit")}
if not asked <= may:
    fail.append("those asked to authorise overtime may: the Authorise button asks for the right to submit (%s lack it)"
                % sorted(asked - may))
raised = read("hrms_addon", "hrms_addon", "attendance.py")
submitted = raised.split("def overtime_on_submit(")[1].split(chr(10) + "def ")[0]
for role in asked:
    if 'people.people_for("%s"' % role not in submitted:
        fail.append("overtime is no longer sent to the %s to authorise: see who is, and that they may" % role)
if "_let_authorise(doc, approvers)" not in submitted or "submit=1" not in raised.split("def _let_authorise(")[1].split(
        chr(10) + "def ")[0]:
    fail.append("and whoever is asked on a site whose roles differ is given the right on that request")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if "Overtime Request" not in nav:
    fail.append("the request has no way in")
print("wiring: seeded on migrate, the Act watched, both buttons on the form")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL OVERTIME CHECKS PASSED")
