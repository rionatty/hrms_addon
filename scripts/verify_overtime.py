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
  5  wiring: no type made on migrate, the buttons whitelisted, the way in

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
# Luuka's standard working day is 8 hours (21 Oct 2026): Payroll Settings'
# Hours in a Pay Day, which the overtime slip divides by too, sets every
# shift's hour alike
eight = R.priced([{"employee": "E1", "hours": 2}, {"employee": "E2", "hours": 2}], {"E1": 1040000, "E2": 1040000},
                 R.WEEKDAY, standards={"E1": 8, "E2": 10}, days=26, day_hours=8)
if [row["hourly_rate"] for row in eight["rows"]] != [5000.0, 5000.0]:
    fail.append("an eight-hour pay day prices every shift's hour alike, 1,040,000 / 208: %s"
                % [row["hourly_rate"] for row in eight["rows"]])
if R.hours_per_month(10, 26, 8) != 208.0 or R.hours_per_month(10, 26, 0) != 260.0:
    fail.append("the pay day's hours stand over the shift's; at 0 the shift's own")
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
# gross of UGX 500,000 and 1.5x below it, here on two of Luuka's own types
TYPES = {"Overtime 1.5": {"standard_multiplier": 1.5, "employees": ["HIGH", "LOW"]},
         "Overtime 1": {"standard_multiplier": 1.0, "custom_gross_above": 500000, "employees": ["HIGH", "LOW"]}}
costed = R.priced([{"employee": "HIGH", "hours": 2}, {"employee": "LOW", "hours": 2}],
                  {"HIGH": 400000, "LOW": 260000}, R.WEEKDAY, TYPES, {"HIGH": 2600000, "LOW": 260000})
rows = {row["employee"]: row for row in costed["rows"]}
if rows["HIGH"]["multiplier"] != 1.0 or rows["LOW"]["multiplier"] != 1.5:
    fail.append("each person on a request is priced under the type their own gross puts them in, not their base: %s"
                % {k: v["multiplier"] for k, v in rows.items()})
if rows["HIGH"]["hourly_rate"] != R.hourly_rate(400000):
    fail.append("while an hour of their pay is worked out of the base")
if (rows["HIGH"]["overtime_type"], rows["LOW"]["overtime_type"]) != ("Overtime 1", "Overtime 1.5"):
    fail.append("and each line names that type, which goes onto their attendance for the Overtime Slip: %s"
                % {k: v["overtime_type"] for k, v in rows.items()})
# none is named or made here (Luuka, 21 Oct 2026: "dont predefine any overtime type you should pick from the
# one assigned")
for gone in ("TYPE_NAMES", "HIGHER_EARNERS", "GROSS_THRESHOLD", "HIGHER_EARNER_MULTIPLIER", "type_name_for",
             "gross_lines", "component_for_rate", "works_from_base", "below_the_act", "missing_type_error",
             "NOT_FOR_THE_DAY"):
    if hasattr(R, gone):
        fail.append("overtime_rules.%s is gone: no Overtime Type is named or made, a person's is the one that lists "
                    "them" % gone)
# the day does not choose the type: a person's own pays each kind of day at its own rate
own = {"Overtime 3": {"standard_multiplier": 1.5, "applicable_for_weekend": 1, "weekend_multiplier": 2.0,
                      "applicable_for_public_holiday": 1, "public_holiday_multiplier": 3.0,
                      "employees": ["E1", "E2", "E3"]}}
days = R.priced([{"employee": name, "hours": 2} for name in ("E1", "E2", "E3")],
                {"E1": 1040000, "E2": 1040000, "E3": 1040000}, R.WEEKDAY, own,
                kinds={"E2": R.REST_DAY, "E3": R.PUBLIC_HOLIDAY})
if [(row["overtime_type"], row["multiplier"]) for row in days["rows"]] != [
        ("Overtime 3", 1.5), ("Overtime 3", 2.0), ("Overtime 3", 3.0)]:
    fail.append("each person's own type pays a weekday, a rest day and a public holiday at its own rates: %s"
                % [(row["overtime_type"], row["multiplier"]) for row in days["rows"]])
print("the day: read, not typed, and priced at the person's own type's rate, or the Act's floor")

# who an Overtime Type is for: the employees it lists, and no one else (Luuka, 21 Oct 2026: "dont
# autoallocate overtime is is not assigned on the overtime"; "dont predefine any overtime type you should pick
# from the one assigned"), the departments it is not paid to, its gross line
LISTS = {"Overtime 1.5": {"standard_multiplier": 1.5, "employees": ["E1", "E2"]},
         "Overtime 1": {"standard_multiplier": 1.0, "custom_gross_above": 500000, "employees": ["E1", "E2"],
                        "excluded_departments": ["Stores - LPL"]},
         "Special Overtime": {"standard_multiplier": 1.25, "employees": ["E7", "E8"]},
         "Drivers Overtime": {"standard_multiplier": 1.1, "custom_gross_above": 300000, "employees": ["E8"]},
         "Night shift overtime": {"standard_multiplier": 1.5, "employees": ["E6"]},
         # a type that lists nobody is nobody's
         "Open Overtime": {"standard_multiplier": 1.5}}
for label, got, want in (
    ("the one type that lists them", R.person_type(260000, LISTS, "E6", "Extrusion - LPL"),
     ("Night shift overtime", None)),
    ("listed on two, under the line: the one without it", R.person_type(260000, LISTS, "E1", "Extrusion - LPL"),
     ("Overtime 1.5", None)),
    ("above the line: the one with it", R.person_type(900000, LISTS, "E1", "Extrusion - LPL"), ("Overtime 1", None)),
    ("at exactly the line: not above it, as the minutes say", R.person_type(500000, LISTS, "E1", "Extrusion - LPL"),
     ("Overtime 1.5", None)),
    ("with no gross known, never a type with a line", R.person_type(None, LISTS, "E1", "Extrusion - LPL"),
     ("Overtime 1.5", None)),
    ("above the line in a department the lined type is not paid to: the other",
     R.person_type(900000, LISTS, "E2", "Stores - LPL"), ("Overtime 1.5", None)),
    ("listed on two: the one whose line their gross is above",
     R.person_type(400000, LISTS, "E8", "Transport - LPL"), ("Drivers Overtime", None)),
    ("listed on two, under one's line: the other, never one that does not list them",
     R.person_type(200000, LISTS, "E8", "Transport - LPL"), ("Special Overtime", None)),
    ("of several lines, the highest their gross is above",
     R.person_type(1200000, {"A": {"employees": ["E5"]}, "B": {"custom_gross_above": 500000, "employees": ["E5"]},
                             "C": {"custom_gross_above": 1000000, "employees": ["E5"]}}, "E5", None), ("C", None)),
    ("listed only under a line their gross is not above: none, and the line said",
     R.person_type(500000, {"Overtime 1": {"custom_gross_above": 500000, "employees": ["E5"]}}, "E5", None),
     (None, "Overtime 1 is for a monthly gross above 500,000.")),
    ("of two such lines, the nearest is said",
     R.person_type(100000, {"B": {"custom_gross_above": 900000, "employees": ["E5"]},
                            "A": {"custom_gross_above": 500000, "employees": ["E5"]}}, "E5", None),
     (None, "A is for a monthly gross above 500,000.")),
    ("two types with nothing between them: said, not guessed",
     R.person_type(260000, {"Overtime 3": {"employees": ["E5"]}, "Overtime 1": {"employees": ["E5"]}}, "E5", None),
     (None, "Overtime 1 and Overtime 3 list them. Keep them on one.")),
    ("nor two with the same line their gross is above",
     R.person_type(900000, {"B": {"custom_gross_above": 500000, "employees": ["E5"]},
                            "A": {"custom_gross_above": 500000, "employees": ["E5"]}, "C": {"employees": ["E5"]}},
                   "E5", None), (None, "A and B list them. Keep them on one.")),
    ("somebody no type lists is paid under none, and told so",
     R.person_type(260000, LISTS, "E9", "Extrusion - LPL"), (None, R.NOT_LISTED)),
    ("not even under a type that lists nobody", R.person_type(260000, {"Open Overtime": {}}, "E9", None),
     (None, R.NOT_LISTED)),
    ("nor on a site with no types", R.person_type(260000, {}, "E9", None), (None, R.NOT_LISTED)),
    ("with no types given at all, nobody's eligibility is judged, and no type is named",
     R.person_type(None, None), (None, None)),
):
    if got != want:
        fail.append("who a type is for: %s: %s, not %s" % (label, got, want))
if R.NOT_LISTED != "no Overtime Type lists them. Add them on a type's Eligibility tab.":
    fail.append("somebody no type lists is told where to add them: %s" % R.NOT_LISTED)
closed = {"Overtime 1.5": {"standard_multiplier": 1.5, "employees": ["E1", "E2"],
                           "excluded_departments": ["Stores - LPL"]},
          "Overtime 1": {"standard_multiplier": 1.0, "custom_gross_above": 500000, "employees": ["E1"]},
          "Special Overtime": {"standard_multiplier": 1.25, "employees": ["E7"]},
          "Open Overtime": {"standard_multiplier": 1.5}}
if R.person_type(260000, closed, "E2", "Stores - LPL") != (None, "Overtime 1.5 is not paid to Stores - LPL."):
    fail.append("a department every type of theirs leaves out has no overtime, and is told which type: %s"
                % (R.person_type(260000, closed, "E2", "Stores - LPL"),))
if R.person_type(260000, closed, "E7", "Extrusion - LPL") != ("Special Overtime", None):
    fail.append("and the types that list somebody are open to them")
judged = R.priced([{"employee": "E2", "employee_name": "Ben", "hours": 2}, {"employee": "E7", "hours": 2},
                   {"employee": "E1", "hours": 2}, {"employee": "E9", "employee_name": "Nine", "hours": 2}],
                  {"E2": 260000, "E7": 260000, "E1": 260000, "E9": 260000}, R.WEEKDAY,
                  closed, {"E2": 260000, "E7": 260000, "E1": 900000, "E9": 260000}, None, None,
                  {"E2": "Stores - LPL", "E7": "Extrusion - LPL", "E1": "Extrusion - LPL", "E9": "Extrusion - LPL"})
seen = [(row["employee"], row["overtime_type"], row["multiplier"], row["amount"] > 0) for row in judged["rows"]]
if seen != [("E2", None, 0.0, False), ("E7", "Special Overtime", 1.25, True), ("E1", "Overtime 1", 1.0, True),
            ("E9", None, 0.0, False)]:
    fail.append("a request is priced by who each type is for: nobody is given a type that does not list them: %s"
                % seen)
if R.eligibility_errors(judged["rows"]) != [
        "Ben is not eligible for this overtime: Overtime 1.5 is not paid to Stores - LPL.",
        "Nine is not eligible for this overtime: no Overtime Type lists them. Add them on a type's Eligibility tab."]:
    fail.append("and those no type is open to are named, with why: %s" % R.eligibility_errors(judged["rows"]))
expect("costing somebody no type is open to", R.cost_check_errors(
    {"status": "Authorised", "rows": judged["rows"], "unpriced": [], "not_eligible": R.eligibility_errors(judged["rows"])}),
    "Ben is not eligible for this overtime", "Nine is not eligible for this overtime")
if R.attendance_update({"hours": 2}, "Special Overtime", 10, hours=1.5) != {
        "overtime_type": "Special Overtime", "actual_overtime_duration": 1.5, "standard_working_hours": 10.0}:
    fail.append("the attendance carries the type chosen for the person, so the Overtime Slip pays under it")
print("eligibility: a type's own employees, the departments it leaves out, and its gross line")

# ── 2. Pricing a request, and the two gates ───────────────────────────
rows = [{"employee": "HR-EMP-1", "employee_name": "A", "hours": 3},
        {"employee": "HR-EMP-2", "employee_name": "B", "hours": 2}]
costed = R.priced(rows, {"HR-EMP-1": 1040000, "HR-EMP-2": 520000}, R.WEEKDAY)
if costed["total"] != 18000.0 + 6000.0:
    fail.append("the request totals its rows: %s" % costed["total"])
if [row["multiplier"] for row in costed["rows"]] != [1.5, 1.5] or any(row["overtime_type"] for row in costed["rows"]):
    fail.append("with no types given, at the Act's floor for the day, under no type")
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

# what an employee's requests still wait for
waits = R.waiting([
    {"name": "OT-3", "overtime_date": "2026-09-10", "hours": 2, "status": "Costed"},
    {"name": "OT-1", "overtime_date": "2026-09-03", "hours": 3, "status": "Requested"},
    {"name": "OT-2", "overtime_date": "2026-09-05", "hours": 1.5, "status": "Authorised"},
    {"name": "OT-4", "overtime_date": "2026-09-12", "hours": 2, "status": "Sent to Payroll"},
    {"name": "OT-5", "overtime_date": "2026-09-13", "hours": 2, "status": "Rejected"},
    {"name": "OT-6", "overtime_date": "2026-09-14", "hours": 2, "status": "Cancelled"},
    {"name": "OT-0", "overtime_date": "2026-09-01", "hours": 4, "status": None}])
if [(row["name"], row["status"], row["next"]) for row in waits] != [
        ("OT-0", "Draft", "Submit"), ("OT-1", "Requested", "Approval by the authorising officer"),
        ("OT-2", "Authorised", "Approval by HR"), ("OT-3", "Costed", "Send to Payroll")]:
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
if R.attendance_update({"hours": 3}, "Overtime 1.5", hours=1.5)["actual_overtime_duration"] != 1.5 \
        or R.attendance_update({"hours": 3}, "Overtime 1.5")["actual_overtime_duration"] != 3.0:
    fail.append("the attendance carries the hours paid, or those authorised where nothing else is said")
own_day = R.priced([{"employee": "E1", "hours": 2}, {"employee": "E2", "hours": 2}],
                   {"E1": 1040000, "E2": 1040000}, R.WEEKDAY, kinds={"E2": R.REST_DAY})
if [(row["day_kind"], row["multiplier"]) for row in own_day["rows"]] != [
        (R.WEEKDAY, R.ACT_MULTIPLIERS[R.WEEKDAY]), (R.REST_DAY, R.ACT_MULTIPLIERS[R.REST_DAY])]:
    fail.append("one person's rest day is another's working day, and each is priced as their own: %s"
                % [(row["day_kind"], row["multiplier"]) for row in own_day["rows"]])

# ── the approval: the Actions menu, as every other request ──────────────
W = load("overtime_approval")
if (W.DOCTYPE, W.WORKFLOW_NAME, W.STATE_FIELD) != ("Overtime Request", "Overtime Request", "workflow_state"):
    fail.append("the workflow is the Overtime Request's own, on Frappe's state field")
if set(W.ACTIONS) != {"Submit", "Approve", "Return", "Reject", "Cancel"}:
    fail.append("its actions are those every other request has: %s" % (W.ACTIONS,))
if [W.docstatus_of(state) for state in (W.DRAFT, W.REQUESTED, W.AUTHORISED, W.COSTED, W.SENT, W.REJECTED, W.CANCELLED)] \
        != [0, 0, 0, 1, 1, 1, 2]:
    fail.append("a request is a draft until HR approve it, which submits it; refused it is submitted as a record")
if {row["state"] for row in W.STATES} != set(R.STATUSES) or any(row["status"] != row["state"] for row in W.STATES):
    fail.append("every state is a status the request can read, and writes that status: %s"
                % sorted({row["state"] for row in W.STATES} ^ set(R.STATUSES)))
if any(row["send_email"] for row in W.STATES):
    fail.append("no state mails the request: it carries people's hourly pay once it is costed")
for label, got, want in (
    ("a supervisor raises it", W.next_states(W.DRAFT, ["Supervisor"]), [("Submit", W.REQUESTED)]),
    ("an employee cannot", W.next_states(W.DRAFT, ["Employee"]), []),
    ("the officer who carries the section authorises, returns or refuses",
     W.next_states(W.REQUESTED, ["Production Manager"]),
     [("Approve", W.AUTHORISED), ("Return", W.DRAFT), ("Reject", W.REJECTED)]),
    ("a supervisor cannot authorise their own request", W.next_states(W.REQUESTED, ["Supervisor"]), []),
    ("HR approve the cost, return or refuse", W.next_states(W.AUTHORISED, ["HR User"]),
     [("Approve", W.COSTED), ("Return", W.DRAFT), ("Reject", W.REJECTED)]),
    ("the officer cannot approve the cost", W.next_states(W.AUTHORISED, ["Production Manager"]), []),
    ("approved, only the HR Manager cancels it", W.next_states(W.COSTED, ["HR Manager"]), [("Cancel", W.CANCELLED)]),
    ("and nobody refuses it: it is cancelled", W.next_states(W.COSTED, ["HR User", "Production Manager"]), []),
    ("with payroll, the same", W.next_states(W.SENT, ["HR Manager"]), [("Cancel", W.CANCELLED)]),
    ("a refused request goes nowhere", W.next_states(W.REJECTED, ["HR Manager", "Production Manager"]), []),
):
    if got != want:
        fail.append("the Actions menu: %s: %s, not %s" % (label, got, want))
if not [row for row in W.TRANSITIONS if row["next_state"] == W.SENT] == []:
    fail.append("Sent to Payroll is no approval: nobody takes a request there from the Actions menu")
expect("returning it without saying what to put right", W.step_errors(W.REQUESTED, W.DRAFT, {}), "Return Remarks")
expect("returning it with the reason", W.step_errors(W.AUTHORISED, W.DRAFT, {"return_remarks": "Wrong day."}))
expect("the officer refusing without saying why", W.step_errors(W.REQUESTED, W.REJECTED, {"cost_remarks": "x"}),
       "authorising officer's remarks")
expect("HR refusing without saying why", W.step_errors(W.AUTHORISED, W.REJECTED, {"authority_remarks": "x"}),
       "HR's remarks")
expect("refusing with the reason", W.step_errors(W.REQUESTED, W.REJECTED, {"authority_remarks": "No budget."}))
expect("approving needs no remarks", W.step_errors(W.REQUESTED, W.AUTHORISED, {}))
blank = dict.fromkeys(W.ALL_STAMP_FIELDS)
signed = W.compute_stamps(W.REQUESTED, W.AUTHORISED, "pm@luuka", "2026-10-13", blank)
if signed != dict(blank, authorised_by="pm@luuka", authorised_on="2026-10-13"):
    fail.append("authorising signs for it: %s" % signed)
costed_by = W.compute_stamps(W.AUTHORISED, W.COSTED, "hro@luuka", "2026-10-14", signed)
if costed_by != dict(signed, costed_by="hro@luuka", costed_on="2026-10-14"):
    fail.append("HR's approval signs for the cost, and the officer's signature stays: %s" % costed_by)
if W.compute_stamps(W.AUTHORISED, W.DRAFT, "hro@luuka", "2026-10-14", signed) != blank:
    fail.append("a return clears every signature")
if W.compute_stamps(W.REQUESTED, W.REJECTED, "pm@luuka", "2026-10-13", blank)["authorised_by"] != "pm@luuka":
    fail.append("a refusal is signed by whoever decided")
if W.compute_stamps(W.AUTHORISED, W.AUTHORISED, "x", "2026-10-15", dict(signed, authorised_by="typed")) != dict(
        signed, authorised_by="typed") or W.compute_stamps(None, W.DRAFT, "x", "2026-10-15", signed) != blank:
    fail.append("a save that takes no step keeps the signatures as they were; a new request has none")
for label, got, want in (
    ("a draft", W.stage_of(0, "Draft"), (W.DRAFT, 0)),
    ("one waiting to be authorised goes back to a draft at that step", W.stage_of(1, "Requested"), (W.REQUESTED, 0)),
    ("one waiting for the cost check too", W.stage_of(1, "Authorised"), (W.AUTHORISED, 0)),
    ("one costed stays submitted", W.stage_of(1, "Costed"), (W.COSTED, 1)),
    ("one with payroll", W.stage_of(1, "Sent to Payroll"), (W.SENT, 1)),
    ("one refused", W.stage_of(1, "Rejected"), (W.REJECTED, 1)),
    ("one cancelled", W.stage_of(2, "Cancelled"), (W.CANCELLED, 2)),
    ("one submitted with no status", W.stage_of(1, None), (W.REQUESTED, 0)),
):
    if got != want:
        fail.append("a request raised before the workflow: %s: %s, not %s" % (label, got, want))
print("the approval: Submit, Approve by the officer, Approve by HR; Return and Reject with the reason")

# overtime the clock shows, raised by itself under the type's own rules
for label, got, want in (
    ("two and three quarter hours, counted in half hours", R.clock_hours(2.75, 30, 30), 2.5),
    ("twenty-four minutes, under the half hour that counts", R.clock_hours(0.4, 30, 30), 0.0),
    ("exactly the least that counts", R.clock_hours(0.5, 30, 30), 0.5),
    ("counted to the minute where no step is given", R.clock_hours(1.26, 30, 0), 1.26),
    ("in quarter hours", R.clock_hours(1.26, 0, 15), 1.25),
    ("never past the type's ceiling for a day", R.clock_hours(5.0, 30, 30, 4), 4.0),
    ("no ceiling where the type gives none", R.clock_hours(5.0, 30, 30, 0), 5.0),
    ("nothing from nothing", R.clock_hours(None, 30, 30), 0.0),
    ("nor from less than nothing", R.clock_hours(-2, 0, 0), 0.0),
    ("an hour and fifty-nine minutes is three half hours", R.clock_hours(1.9834, 30, 30), 1.5),
    ("forty-five minutes where an hour is the least that counts, whatever the step", R.clock_hours(0.75, 60, 15), 0.0),
    ("and the full hour does", R.clock_hours(1.0, 60, 15), 1.0),
):
    if got != want:
        fail.append("overtime by the clock: %s: %s, not %s" % (label, got, want))
sheets = R.clock_sheets([
    {"employee": "E1", "employee_name": "Ann", "hours": 2.5, "requester": "S1", "branch": "K", "department": "X", "company": "C"},
    {"employee": "E2", "employee_name": "Ben", "hours": 1, "requester": "S2", "branch": "K", "department": "Y", "company": "C"},
    {"employee": "E3", "employee_name": "Cat", "hours": 1.5, "requester": "S1", "branch": "K", "department": "X", "company": "C"},
    {"employee": "E4", "employee_name": "Dan", "hours": 2, "requester": None, "branch": "K", "department": "X", "company": "C"},
    {"employee": "E5", "employee_name": "Eve", "hours": 0, "requester": "S1", "branch": "K", "department": "X", "company": "C"},
    {"employee": "E6", "employee_name": "Fay", "hours": 1, "requester": "S1", "branch": "K", "department": "Y", "company": "C"}])
if [(sheet["requester"], sheet["department"], [(row["employee"], row["hours"]) for row in sheet["employees"]])
        for sheet in sheets] != [("S1", "X", [("E1", 2.5), ("E3", 1.5)]), ("S2", "Y", [("E2", 1.0)]),
                                 ("S1", "Y", [("E6", 1.0)])]:
    fail.append("a day's overtime by the clock is one request for each requester and section; somebody with nobody "
                "to request it, or nothing to ask for, is on none: %s" % sheets)
if R.clock_sheets(None) != []:
    fail.append("no overtime, no request")
print("from the clock: the least that counts, the step, the ceiling, and a requester on every request")
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
update = R.attendance_update({"hours": 3}, "Overtime 3")
attendance = fields_of(upstream_doctype("Attendance"))
for fieldname in update:
    if fieldname not in attendance:
        fail.append("Attendance has no %s: the overtime slip would never see the hours"
                    % fieldname)
if update["overtime_type"] != "Overtime 3":
    fail.append("the row carries the person's own type")
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
if "own = 0.0 if why else multiplier_for(day, (types or {}).get(named) if named else None)" not in read(
        "hrms_addon", "hrms_addon", "overtime_rules.py").split("def priced(")[1].split(chr(10) + "def ")[0]:
    fail.append("each line is worth its own type's rate for the person's day (case 1)")
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
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef send_to_payroll\(', glue) \
        or 'doc.check_permission("submit")' not in glue.split("def send_to_payroll(")[1].split(chr(10) + "def ")[0]:
    fail.append("overtime.send_to_payroll changes something: a whitelisted POST method that checks the caller may act")
for gone in ("def cost_check(", "def authorise_overtime(", "def reject_overtime(", "def _let_authorise("):
    if gone in glue or gone in read("hrms_addon", "hrms_addon", "attendance.py"):
        fail.append("%s is gone: the request is approved from the Actions menu, not by a button of its own" % gone)
if "fill_day_and_rate" not in read("hrms_addon", "hrms_addon", "attendance.py"):
    fail.append("the request must learn what day it falls on as it validates")
landed = glue.split("def send(")[1].split(chr(10) + "def ")[0]
if "rules.person_type(grosses.get(row[\"employee\"]), types, row[\"employee\"]," not in landed \
        or "rules.attendance_update(row, named, standard, hours=paid)" not in landed:
    fail.append("the hours land on each attendance under the type that lists the person, or the Overtime Slip pays "
                "them under another")
# no Overtime Type is made, and none is named, here (Luuka, 21 Oct 2026: "dont predefine any overtime type")
for gone in ("def seed_overtime_types(", "def _make_type(", "def _overtime_component(", "def _hourly_components(",
             "def fill_gross_line(", "def warn_below_the_act(", "def type_for(", "def _missing_types(",
             '"doctype": TYPE', "new_doc(TYPE"):
    if gone in glue:
        fail.append("overtime.py makes or names no Overtime Type: %s is gone" % gone)
for name in ("Weekday Overtime", "Rest Day Overtime", "Public Holiday Overtime", "UGX 500,000"):
    if name in code_only(glue) or name in code_only(read("hrms_addon", "hrms_addon", "overtime_rules.py")):
        fail.append("no type is named in the code: %s" % name)
if glue.split("def setup_on_migrate():")[1].strip() != "stamp_untyped()":
    fail.append("the migrate makes no type: it only puts hours sent without one under the one that lists them")
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
if "closed = overtime.fill_day_and_rate(doc) or []" not in raising \
        or "overtime.check_step(doc, errors + closed, notes=closed)" not in raising:
    fail.append("somebody no Overtime Type is open to is refused when the request is raised, and said as the "
                "draft is saved")
stepping_notes = glue.split("def check_step(")[1].split(chr(10) + "def ")[0]
if "if not moved and notes and new == approval.DRAFT:" not in stepping_notes \
        or 'title=_("Not Eligible for Overtime")' not in stepping_notes:
    fail.append("a draft saved with somebody no type lists says so then, not only when it is raised")
# Get Employees: a type's Employees from whole departments (Luuka, 21 Oct 2026)
getting = glue.split("def employees_of_departments(")[1].split(chr(10) + "def ")[0]
for needle, why in (
    ('frappe.has_permission(TYPE, "write", throw=True)', "for those who may change the type"),
    ('frappe.db.get_descendants("Department", name)', "a department takes in those under it"),
    ('"status": "Active"', "active employees only"),
    ('filters["branch"] = branch', "at the plant picked, if one is"),
    ("if row.parent != overtime_type:", "each with the other types that list them already"),
):
    if needle not in getting:
        fail.append("Get Employees: %s (%r not found)" % (why, needle))
if not re.search(r"@frappe\.whitelist\(\)\ndef employees_of_departments\(", glue):
    fail.append("Get Employees can be called from the form")
form = read("hrms_addon", "public", "js", "overtime_type.js")
for needle, why in (
    ('frm.add_custom_button(__("Get Employees")', "the button on the type"),
    ('fieldtype: "Table MultiSelect"', "one department or several"),
    ('"hrms_addon.hrms_addon.overtime.employees_of_departments"', "asked of the method that finds them"),
    ("if (here.has(person.employee))", "somebody the type lists already is not added twice"),
    ("if (person.elsewhere.length && !include_listed)", "nor somebody another type lists, unless asked"),
    ('frm.add_child("custom_employees"', "the rest added to the type's Employees"),
):
    if needle not in form:
        fail.append("Get Employees on the form: %s (%r not found)" % (why, needle))
if (read("hrms_addon", "hooks.py").count('"Overtime Type": "public/js/overtime_type.js"') != 1):
    fail.append("the Overtime Type form loads its script")
if "if closed:\n        return stopped(closed)" not in landed:
    fail.append("and never sent to payroll under a type closed to them since")
# overtime raised from the clock: the rules are the type's own, and the request is somebody's
clock = [custom.get("Overtime Type-%s" % name) or {} for name in (
    "custom_clock_section", "custom_from_clock", "custom_clock_minimum", "custom_clock_cb", "custom_clock_step",
    "custom_clock_requester")]
if [(row.get("fieldtype"), row.get("insert_after")) for row in clock] != [
        ("Section Break", "custom_employees"), ("Check", "custom_clock_section"), ("Int", "custom_from_clock"),
        ("Column Break", "custom_clock_minimum"), ("Int", "custom_clock_cb"), ("Link", "custom_clock_step")]:
    fail.append("the Overtime Type says whether its overtime is raised from the clock, the least that counts, the "
                "step and the requester, each field after the one before: %s"
                % [(row.get("fieldtype"), row.get("insert_after")) for row in clock])
if clock[5].get("options") != "Employee" or (clock[2].get("default"), clock[4].get("default")) != ("30", "30") \
        or clock[1].get("default"):
    fail.append("half an hour counts, in half hours, until HR say otherwise; and nothing is raised until a type is ticked")
for row in clock:
    if '"%s"' % row.get("name") not in read("hrms_addon", "hooks.py"):
        fail.append("hooks fixtures list %s" % row.get("name"))
if (request.get("from_clock") or {}).get("fieldtype") != "Check" or not request["from_clock"].get("read_only"):
    fail.append("a request says whether it was raised from the clock, and nobody types that")
for fieldname in ("custom_from_clock", "custom_clock_minimum", "custom_clock_step", "custom_clock_requester"):
    if '"%s"' % fieldname not in glue.split("def _type_row(")[1].split(chr(10) + "def ")[0]:
        fail.append("a type is read with %s" % fieldname)
rising = glue.split("def raise_from_clock(")[1].split(chr(10) + "def ")[0]
for needle, why in (
    ('if not any(cint((row or {}).get("custom_from_clock")) for row in types.values()):', "nothing is read until a type is ticked"),
    ('"docstatus": 1, "status": rules.PAID_ON, "in_time": ["is", "set"],', "only a day the clock measured, and worked"),
    ('"out_time": ["is", "set"]}', "at both ends"),
    ("marked = [row for row in marked if row.employee not in asked]", "somebody already on a request for the day is left to it"),
    ("rules.person_type(grosses.get(row.employee), types, row.employee, seat.get(\"department\"))[0]",
     "the type is the person's own, by who each type is for"),
    ('if not theirs or not cint(theirs.get("custom_from_clock")):', "and only a type that says so raises it"),
    ("rules.worked_overtime(kind, row.working_hours,", "what the clock shows past the shift"),
    ('rules.clock_hours(worked, theirs.get("custom_clock_minimum"), theirs.get("custom_clock_step"),',
     "counted by the type's own rules"),
    ('theirs.get("maximum_overtime_hours_allowed"))', "up to its ceiling"),
    ('requester = seat.get("reports_to") or theirs.get("custom_clock_requester")',
     "the employee's supervisor requests it, else whoever the type names"),
    ("rules.clock_sheets(lines)", "one request for each requester and section"),
    ('"from_clock": 1,', "marked as raised from the clock"),
    ("doc.set(approval.STATE_FIELD, approval.REQUESTED)", "and waiting for the authorising officer"),
    ("frappe.log_error(title=\"HRMS Addon: overtime by the clock with nobody to request it\"", "somebody left out is said"),
):
    if needle not in rising:
        fail.append("overtime.raise_from_clock: %s" % why)
asked_already = glue.split("def _on_a_request(")[1].split(chr(10) + "def ")[0]
if '"status": ["not in", [approval.REJECTED, approval.CANCELLED]]' not in asked_already:
    fail.append("a refused or cancelled request does not stand in the way of the clock's")
daily_job = read("hrms_addon", "hrms_addon", "attendance.py").split("\ndef daily(")[1].split(chr(10) + "def ")[0]
if "overtime.raise_from_clock()" not in daily_job \
        or daily_job.index("overtime.raise_from_clock()") > daily_job.index("overtime.send_ready()"):
    fail.append("each day the clock's overtime is raised, then the approved overtime sent")
print("glue: the day read, the cost checked, the hours landed, the slip drawn")

for needle, why in (
    ("attendance.shift_hours_of(attendance.shift_on(employee, day), hours)[\"standard\"]",
     "the standard day is the one of the shift worked that day"),
    ("_standard_hours(people_on_it, doc.overtime_date), kinds, _departments(people_on_it),",
     "HR's cost check prices each person on their own shift, and their own kind of day"),
    ("days=pay_days.days_in_month(), day_hours=pay_days.hours_in_day())",
     "over the month's days and the day's hours the Overtime Slip divides by too (Payroll Settings)"),
    ('row.day_kind = found["day_kind"] if row.employee else None', "each line reads the day for its own employee"),
    ('row.overtime_type = found["overtime_type"] if row.employee else None',
     "and carries the Overtime Type that person falls under"),
    ('row.multiplier = found["multiplier"] if row.employee else 0', "and its rate, before anybody signs"),
    ("rules.worked_overtime(theirs, found.working_hours, standard)", "the overtime the clock shows is worked out"),
    ("if (found.in_time and found.out_time) else None", "only for a day the clock measured at both ends"),
    ("paid = rules.payable_hours(row.get(\"hours\"), worked)", "what is paid is the rules' answer"),
    ("rules.attendance_update(row, named, standard, hours=paid)",
     "and that, not what was authorised, goes onto the attendance"),
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
    fail.append("hours sent to payroll without a type are put under one on every migrate")
form = read("hrms_addon", "hrms_addon", "doctype", "overtime_request", "overtime_request.js")
for button in ("Authorise", "Reject", "Check the Cost"):
    if 'add_custom_button(__("%s")' % button in form:
        fail.append("the form has no %s button of its own: that is on the Actions menu" % button)
if "overtime.send_to_payroll" not in form or 'frm.doc.docstatus === 1 && status === "Costed" && frm.has_perm("submit")' not in form:
    fail.append("HR can send an approved request to payroll from its form, which says what stops it")
if "frm.dashboard.set_headline(" in form or "frm.dashboard.clear_headline(" in form:
    fail.append("the form says where the request stands in one line: a headline set after an intro wipes it")
for needle in ('Requested: [__("Waiting for the authorising officer."), "orange"]',
               'Authorised: [__("Authorised. Waiting for HR to approve the cost."), "orange"]'):
    if needle not in form:
        fail.append("a request says on its form whom it waits for (%s)" % needle)
filled = glue.split("def fill_day_and_rate(")[1].split(chr(10) + "def ")[0]
if "doc.overtime_type" in glue or "doc.multiplier" in glue or "rules.priced(" not in filled:
    fail.append("no rate is written on the request's header: the lines are rated by the same rules that cost them")
costing = glue.split("def _cost(")[1].split(chr(10) + "def ")[0]
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
if "return stopped(closed)" in landed and landed.index("return stopped(closed)") > landed.index(
        'frappe.db.set_value("Attendance"'):
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
                    ("rules.person_type(pay.monthly_gross(found.employee, found.attendance_date), types, found.employee,",
                     "under the type that lists the employee")):
    if needle not in stamp:
        fail.append("overtime.stamp_untyped: %s (%r)" % (why, needle))
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
    fail.append("those asked to authorise overtime may: refusing submits the request (%s lack the right)"
                % sorted(asked - may))
if not asked <= set(W.AUTHORISERS) or not set(W.HR) <= {row["role"] for row in request_spec["permissions"] if row.get("submit")}:
    fail.append("and the workflow lets them, as it lets HR approve the cost")
holding = glue.split("def _holders(")[1].split(chr(10) + "def ")[0]
for role in asked:
    if 'people.people_for("%s"' % role not in holding:
        fail.append("overtime is no longer sent to the %s to authorise: see who is, and that they may" % role)
telling = glue.split("def _tell(")[1].split(chr(10) + "def ")[0]
if "_let_act(doc, users)" not in telling or "submit=1" not in glue.split("def _let_act(")[1].split(chr(10) + "def ")[0] \
        or "people.withdraw(doc.doctype, doc.name, held)" not in telling:
    fail.append("whoever holds the request next is told, given it and able to act on it; whoever held it is let off")
stepping = glue.split("def check_step(")[1].split(chr(10) + "def ")[0]
for needle, why in (
    ("before = doc.get_doc_before_save()", "the step is read off what the request was"),
    ("approval.step_errors(old, new, {", "a return or a refusal carries its reason"),
    ("errors = list(raising) + errors", "a request is checked as it is raised, not while it is a draft"),
    ("errors = _cost(doc, old)", "HR's approval costs it"),
    ("approval.compute_stamps(old, new, frappe.session.user, today(), current)", "each step is signed for"),
    ("doc.status = new", "the status reads the stage"),
    ("_tell(doc, old, new)", "and whoever is next is told"),
):
    if needle not in stepping:
        fail.append("overtime.check_step: %s" % why)
raised = read("hrms_addon", "hrms_addon", "attendance.py")
if "overtime.check_step(doc, errors + closed, notes=closed)" not in \
        raised.split("def overtime_validate(")[1].split(chr(10) + "def ")[0]:
    fail.append("the request's validate hands the step to overtime.check_step, with what would stop it being raised")
if "overtime.approved(doc)" not in raised.split("def overtime_on_submit(")[1].split(chr(10) + "def ")[0]:
    fail.append("HR's approval submits the request, and its hours go to payroll from there")
going = glue.split("def approved(")[1].split(chr(10) + "def ")[0]
if "if doc.get(approval.STATE_FIELD) != approval.COSTED:" not in going or "send(doc, quiet=True)" not in going \
        or "getdate(doc.overtime_date) > getdate(today())" not in going:
    fail.append("only an approved request whose day has come is sent, and quietly: what stops it is said, not thrown")
ready = glue.split("def send_ready(")[1].split(chr(10) + "def ")[0]
if '"status": approval.COSTED' not in ready or '"overtime_date": ["<", getdate(today())]' not in ready \
        or "quiet=True" not in ready or "frappe.log_error(" not in ready:
    fail.append("each day the approved requests whose day has passed are sent as their attendance comes in")
if "overtime.send_ready()" not in raised.split("\ndef daily(")[1].split(chr(10) + "def ")[0]:
    fail.append("the daily job sends approved overtime to payroll")
if "return stopped(" not in landed or landed.count("frappe.throw(") != 1 or "if quiet:" not in landed:
    fail.append("what stops the hand-off is thrown, or handed back when it is tried quietly; nothing is written either way")
if "approval.STATE_FIELD: approval.SENT" not in landed:
    fail.append("sent, the request's stage says so as well as its status")
if "workflows.setup_on_migrate(overtime_approval, \"Overtime Request workflow\")" not in raised:
    fail.append("the workflow is built on every migrate")
patch = read("hrms_addon", "patches", "v1_0", "overtime_requests_on_workflow.py")
if "hrms_addon.patches.v1_0.overtime_requests_on_workflow" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]")[-1] or "approval.stage_of(row.docstatus, row.status)" not in patch \
        or '[approval.STATE_FIELD, "is", "not set"]' not in patch or '"docstatus": docstatus' not in patch:
    fail.append("the requests already on the site take their stage on the workflow, once, by a patch")
# the types the migrate used to make go, once, where nobody uses them
unseeded = read("hrms_addon", "patches", "v1_0", "overtime_types_not_seeded.py")
if "hrms_addon.patches.v1_0.overtime_types_not_seeded" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]")[-1]:
    fail.append("the types the migrate used to make are taken off once, by a patch, after the tables are synced")
for needle, why in (
    ('SEEDED = ("Weekday Overtime", "Rest Day Overtime", "Public Holiday Overtime",\n'
     '          "Weekday Overtime (Above UGX 500,000)")', "the four the migrate made, and only those"),
    ('if frappe.db.exists("Overtime Type Employee", {"parenttype": TYPE, "parent": name}):',
     "one that lists employees is kept"),
    ("frappe.delete_doc(TYPE, name, ignore_permissions=True)", "with Frappe's own check that nothing names it"),
    ("except frappe.LinkExistsError:", "one in use is kept"),
    ('frappe.db.rollback(save_point="seeded_overtime_type")', "and nothing of it is undone"),
):
    if needle not in unseeded:
        fail.append("the seeded types' patch: %s (%r)" % (why, needle))
if (request.get("return_remarks") or {}).get("fieldtype") != "Small Text":
    fail.append("a returned request says what must be put right")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if "Overtime Request" not in nav:
    fail.append("the request has no way in")
print("wiring: no type made on migrate, the seeded ones gone where unused, both buttons on the form")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL OVERTIME CHECKS PASSED")
