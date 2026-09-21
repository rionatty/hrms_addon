"""Verify shifts and scheduling, without a bench:

    python scripts/verify_shifts.py

The Shifts & Scheduling sheet of Luuka's revised testing scripts, all four
cases: the shifts themselves (1), assignment by plant and section (2), the
link to attendance and the shift allowance (3), and automatic weekly
rotation with a hold for anybody asked to stay put (4).

  1  the cycle: who is on what this period, and who is held off it
  2  the allowance: counted from the shifts worked, not the roster
  3  the paper carries the cycle, the members and the lines
  4  the glue writes Frappe HR's own Shift Assignments and reads its own
     Attendance, and pays through an Additional Salary
  5  wiring: the seed, the daily roll, the monthly draw, the way in

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


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


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
S = load("shift_rules")
A = load("attendance_rules")
hooks = hooks_dict()
print("loaded shift_rules.py without Frappe")

# ── 1. The cycle ──────────────────────────────────────────────────────
if S.PERIODS != ("Weekly", "Fortnightly", "Monthly"):
    fail.append("a rotation comes round weekly, fortnightly or monthly: %s" % (S.PERIODS,))
if S.PERIOD_DAYS[S.WEEKLY] != 7:
    fail.append("a week is seven days")

SHIFTS = ("Day Shift", "Night Shift", "Off")
START = "2026-06-01"  # a Monday
# test case 4: the shifts come round, a week at a time
if S.shift_on(START, "2026-06-01", SHIFTS) != "Day Shift":
    fail.append("the first week is the first position")
if S.shift_on(START, "2026-06-08", SHIFTS) != "Night Shift":
    fail.append("the next week is the next position")
if S.shift_on(START, "2026-06-15", SHIFTS) != "Off":
    fail.append("and the one after that, the one after")
if S.shift_on(START, "2026-06-22", SHIFTS) != "Day Shift":
    fail.append("with three shifts, week four is back at the start")
if S.shift_on(START, "2026-06-07", SHIFTS) != "Day Shift":
    fail.append("a week is a week: the seventh day is still week one")
# a second crew, staggered
if S.shift_on(START, "2026-06-01", SHIFTS, offset=1) != "Night Shift":
    fail.append("a crew starting a position along is on the next shift")
if S.shift_on(START, "2026-05-25", SHIFTS) != "Day Shift":
    fail.append("before the rotation starts nothing has come round yet")
if S.shift_on(START, "2026-06-01", ()) is not None:
    fail.append("a cycle with no shifts has no position")
if S.periods_between(START, "2026-06-15", S.FORTNIGHTLY) != 1:
    fail.append("a fortnightly rotation turns half as often")

window = S.period_window(START, "2026-06-10")
if str(window["from"]) != "2026-06-08" or str(window["to"]) != "2026-06-14":
    fail.append("the period a day falls in is its own week: %s" % window)

# test case 4's second half: somebody asked to stay put
members = [{"employee": "HR-EMP-1", "offset": 0},
           {"employee": "HR-EMP-2", "offset": 1},
           {"employee": "HR-EMP-3", "offset": 0, "hold_until": "2026-06-30",
            "held_shift": "Day Shift"}]
rows = S.schedule(START, "2026-06-08", members, SHIFTS)
by_employee = {row["employee"]: row for row in rows}
if by_employee["HR-EMP-1"]["shift_type"] != "Night Shift":
    fail.append("the first crew has come round to nights")
if by_employee["HR-EMP-2"]["shift_type"] != "Off":
    fail.append("the second crew is a position ahead")
if by_employee["HR-EMP-3"]["shift_type"] != "Day Shift":
    fail.append("somebody held on days stays on days")
if by_employee["HR-EMP-3"]["rotated"]:
    fail.append("and the roster says they did not rotate")
if not by_employee["HR-EMP-1"]["rotated"]:
    fail.append("while everybody else did")
# and the day the hold runs out, they rejoin where the cycle has got to
after = S.schedule(START, "2026-07-06", members, SHIFTS)
held = {row["employee"]: row for row in after}["HR-EMP-3"]
if not held["rotated"] or held["shift_type"] != S.shift_on(START, "2026-07-06", SHIFTS):
    fail.append("once the hold lapses they rejoin where the cycle is, not where they left it")
if S.due_to_rejoin(members, "2026-07-06") != ["HR-EMP-3"]:
    fail.append("and whose hold has run out is known: %s" % S.due_to_rejoin(members, "2026-07-06"))
if S.due_to_rejoin(members, "2026-06-10"):
    fail.append("nobody rejoins before their date")

good = {"rotation_name": "Kawempe Extrusion", "start_date": START, "period": S.WEEKLY,
        "shifts": [{"shift_type": name} for name in SHIFTS], "members": members}
expect("a complete rotation", S.rotation_errors(good))
expect("a rotation of one", S.rotation_errors(dict(
    good, shifts=[{"shift_type": "Day Shift"}], members=[{"employee": "HR-EMP-1"}])),
    "at least two shifts")
expect("the same shift twice", S.rotation_errors(dict(
    good, shifts=[{"shift_type": "Day Shift"}, {"shift_type": "Day Shift"}])),
    "in the cycle twice")
expect("a rotation with no start", S.rotation_errors(dict(good, start_date=None)),
       "when the rotation starts")
expect("somebody on it twice", S.rotation_errors(dict(good, members=[
    {"employee": "HR-EMP-1"}, {"employee": "HR-EMP-1"}])), "on the rotation twice")
expect("a position that is not in the cycle", S.rotation_errors(dict(good, members=[
    {"employee": "HR-EMP-1", "offset": 5}])), "and the cycle has 3")
expect("a hold with no shift to hold them on", S.rotation_errors(dict(good, members=[
    {"employee": "HR-EMP-1", "hold_until": "2026-06-30"}])), "no shift is named")
print("the cycle: it comes round, it staggers crews, and it holds who was promised")

# ── 2. The allowance ──────────────────────────────────────────────────
due = S.allowance_due({"Night Shift": 12, "Day Shift": 14, "General": 2},
                      {"Night Shift": 10000, "Day Shift": 5000})
if due["total"] != 12 * 10000 + 14 * 5000:
    fail.append("the allowance is the shifts worked at the rate each carries: %s" % due)
if len(due["lines"]) != 2:
    fail.append("a shift with no allowance on it is not a line: %s" % due["lines"])
if S.allowance_due({}, {})["total"] != 0.0:
    fail.append("nothing worked is nothing owed")

lines = [{"shift_type": "Night Shift", "shifts": 12, "rate": 10000, "amount": 120000}]
good = {"employee": "HR-EMP-1", "from_date": "2026-05-26", "to_date": "2026-06-25",
        "lines": lines, "salary_component": "Shift Allowance"}
expect("a complete allowance", S.allowance_errors(good))
expect("an allowance over no cycle", S.allowance_errors(dict(good, from_date=None)),
       "which cycle")
expect("an allowance with nothing on it", S.allowance_errors(dict(good, lines=[])),
       "No shift with an allowance")
expect("an allowance with nothing to pay it on",
       S.allowance_errors(dict(good, salary_component=None)), "which salary component")
print("the allowance: the shifts worked, at what each carries, paid on a component")

# ── 3. The paper ──────────────────────────────────────────────────────
rotation = fields_of(doctype("Shift Rotation"))
for fieldname in ("rotation_name", "branch", "department", "start_date", "period", "status",
                  "shifts", "members", "cycle_length", "last_rolled_on", "this_period_from"):
    if fieldname not in rotation:
        fail.append("the rotation has no %s" % fieldname)
if rotation.get("period", {}).get("options", "").split("\n") != list(S.PERIODS):
    fail.append("the three periods of shift_rules: %s" % rotation.get("period"))
member = fields_of(doctype("Shift Rotation Member"))
for fieldname in ("employee", "offset", "hold_until", "held_shift", "current_shift"):
    if fieldname not in member:
        fail.append("a member row has no %s" % fieldname)
if member.get("held_shift", {}).get("options") != "Shift Type":
    fail.append("a hold is onto Frappe HR's own Shift Type")
position = fields_of(doctype("Shift Rotation Shift"))
if position.get("shift_type", {}).get("options") != "Shift Type":
    fail.append("a position in the cycle is a Shift Type")

allowance = fields_of(doctype("Shift Allowance"))
for fieldname in ("employee", "from_date", "to_date", "lines", "total", "salary_component",
                  "additional_salary", "shifts_worked", "rotation"):
    if fieldname not in allowance:
        fail.append("the allowance has no %s" % fieldname)
if allowance.get("additional_salary", {}).get("options") != "Additional Salary":
    fail.append("the allowance is paid the way everything else in this app reaches payroll")
for fieldname in ("total", "additional_salary", "shifts_worked"):
    if not allowance.get(fieldname, {}).get("read_only"):
        fail.append("%s is worked out, not typed" % fieldname)

# the rate lives on Frappe HR's Shift Type, not on a shadow master here
shift_type = custom_fields("Shift Type")
for fieldname in ("custom_shift_allowance", "custom_allowance_component"):
    if fieldname not in shift_type:
        fail.append("Shift Type has no %s: the rate belongs on the shift" % fieldname)
if shift_type.get("custom_allowance_component", {}).get("options") != "Salary Component":
    fail.append("and it names the component it is paid on")
upstream = fields_of(upstream_doctype("Shift Type"))
for fieldname in ("start_time", "end_time", "enable_auto_attendance"):
    if fieldname not in upstream:
        fail.append("Shift Type has no %s: the shifts are not Frappe HR's after all" % fieldname)
attendance = fields_of(upstream_doctype("Attendance"))
if "shift" not in attendance:
    fail.append("Attendance carries no shift, so nothing could be counted from it")
assignment = fields_of(upstream_doctype("Shift Assignment"))
for fieldname in ("employee", "shift_type", "start_date", "end_date"):
    if fieldname not in assignment:
        fail.append("Shift Assignment has no %s" % fieldname)
print("the paper: the cycle, the members, the lines, and the rate on the shift itself")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "shifts.py")
known = set(rotation) | set(allowance) | {"doctype", "name", "docstatus", "employee", "company",
                                          "flags", "members", "lines", "shifts"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update"):
        continue
    if fieldname not in known:
        fail.append("shifts.py reads or writes %s, which is on neither document" % fieldname)
for needle, why in (
    ("rules.schedule(", "the roster comes from the rules (case 4)"),
    ("rules.rotation_errors(", "and so does what a rotation must carry"),
    ("rules.due_to_rejoin(", "and who rejoins when a hold lapses"),
    ("rules.allowance_due(", "the allowance is worked out by the rules (case 3)"),
    ("ASSIGNMENT", "the rotation writes Frappe HR's own Shift Assignment (case 2)"),
    ('"Attendance"', "and counts from its own Attendance, not from the roster"),
    ("custom_shift_allowance", "the rate is read off the shift"),
    ("Additional Salary", "and paid the way everything else reaches payroll"),
    ("attendance_rules.cycle_window", "over the attendance cycle, 26th to 25th"),
):
    if needle not in glue:
        fail.append("shifts.py: %s (%r not found)" % (why, needle))
for name in ("roll", "draw_allowances"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("shifts.%s changes something: a whitelisted POST method" % name)
if "check_permission(" not in glue:
    fail.append("a whitelisted method must check the caller may act")
for name, prefix, methods in (("shift_rotation", "rotation", ("validate",)),
                              ("shift_allowance", "allowance",
                               ("validate", "on_submit", "on_cancel"))):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    for method in methods:
        if "    def %s(self):\n        shifts.%s_%s(self)" % (method, prefix, method) \
                not in controller:
            fail.append("the %s controller must hand %s to shifts.%s_%s"
                        % (name, method, prefix, method))
print("glue: the rotation writes real assignments, the allowance counts real attendance")

# ── 5. Wiring ─────────────────────────────────────────────────────────
daily = hooks.get("scheduler_events", {}).get("daily", [])
for path in ("hrms_addon.hrms_addon.shifts.daily", "hrms_addon.hrms_addon.shifts.monthly"):
    if path not in daily:
        fail.append("%s must run on the clock" % path)
if "hrms_addon.hrms_addon.shifts.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("Luuka's three shifts must be seeded on every migrate")
if S.SHIFT_HOURS[S.DAY][0] != A.FULL_SHIFT_HOURS:
    fail.append("a production shift is the full twelve hours attendance_rules knows: %s vs %s"
                % (S.SHIFT_HOURS[S.DAY][0], A.FULL_SHIFT_HOURS))
if S.SHIFT_HOURS[S.NIGHT][0] != A.FULL_SHIFT_HOURS:
    fail.append("and so is the night one")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Shift Rotation", "Shift Allowance"):
    if name not in nav:
        fail.append("%s has no way in" % name)
for name in ("shift_rotation", "shift_allowance"):
    if not os.path.exists(os.path.join(APP, "doctype", name, name + ".js")):
        fail.append("%s has no form script" % name)
# the cycle the allowance covers is the register's own
if A.CYCLE_START_DAY != 26 or A.CYCLE_END_DAY != 25:
    fail.append("the attendance cycle moved: the allowance window must move with it")
print("wiring: seeded on migrate, rolled daily, drawn when the cycle closes")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL SHIFT CHECKS PASSED")
