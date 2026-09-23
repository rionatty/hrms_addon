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

good = {"status": "Authorised", "rows": costed["rows"], "unpriced": [],
        "cost_centre": "Kawempe - LPL"}
expect("a proper cost check", R.cost_check_errors(good))
expect("costing before the officer signed", R.cost_check_errors(dict(good, status="Requested")),
       "once the authorising officer has signed")
expect("costing with nobody on it", R.cost_check_errors(dict(good, rows=[])), "nobody on the request")
expect("costing somebody with no salary", R.cost_check_errors(dict(good, unpriced=["B"])),
       "no salary on record for B")
expect("costing with no cost centre", R.cost_check_errors(dict(good, cost_centre=None)),
       "which cost centre")

paid = {"status": "Costed", "rows": [dict(row, attendance="HR-ATT-1") for row in rows]}
expect("a proper hand-off", R.payroll_errors(paid))
expect("paying before HR costed it", R.payroll_errors(dict(paid, status="Authorised")),
       "after HR have checked")
expect("paying hours with no attendance to sit on",
       R.payroll_errors(dict(paid, rows=[dict(rows[0], attendance=None)])),
       "no attendance for A")

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
for fieldname in ("day_kind", "overtime_type", "multiplier", "cost_centre", "total_cost",
                  "costed_by", "costed_on", "cost_remarks", "over_the_cap",
                  "sent_to_payroll_on"):
    if fieldname not in request:
        fail.append("the overtime request has no %s" % fieldname)
for fieldname in ("day_kind", "overtime_type", "multiplier", "total_cost", "over_the_cap"):
    if not request.get(fieldname, {}).get("read_only"):
        fail.append("%s is worked out, not typed: it must be read-only" % fieldname)
if request.get("overtime_type", {}).get("options") != "Overtime Type":
    fail.append("the request points at Frappe HR's own Overtime Type")
if request.get("cost_centre", {}).get("options") != "Cost Center":
    fail.append("the cost centre is a real Cost Center (Organisation & Setup, case 9)")
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
print("the paper: the day, the rate, the cost centre, the cost and where it went")

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
if "gross=grosses.get(" not in landed or "lines=lines" not in landed:
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
print("glue: the day read, the cost checked, the hours landed, the slip drawn")

# ── 6. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.overtime.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("the three overtime types must be seeded on every migrate")
if "warn_below_the_act" not in glue:
    fail.append("a rate edited under the Act is said out loud on the deploy")
form = read("hrms_addon", "hrms_addon", "doctype", "overtime_request", "overtime_request.js")
for needle in ("overtime.cost_check", "overtime.send_to_payroll"):
    if needle not in form:
        fail.append("the form has no way to call %s" % needle)
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
