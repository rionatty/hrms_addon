"""Verify attendance and shift management, without a bench:

    python scripts/verify_attendance.py

Luuka clock in on ZKTeco machines and keep a paper register beside them,
because the machines are unreliable (Manufacturing Excellence 4.2 and 4.3,
Reward & Compensation 4.2). This covers both halves:

  1  the cycle, the codes and the day: the month runs 26 to 25, a cell of
     LPL/HR/07 says which shift was worked or why it was not, and a shift
     is twelve hours with two of them overtime
  2  the three forms: LPL/HR/25 off duty, LPL/HR/14 overtime, the gate pass
  3  reading a ZKTeco machine: what a punch means, the face read twice, the
     direction where the machine did not say, and the badge nobody owns
  4  the DocTypes carry the paper and the machine
  5  the glue reads and writes fields that exist, here and upstream, and
     the driver is optional
  6  wiring: the doc events, the workflow on migrate, the jobs, the way in

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
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
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


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
A, Z, O = load("attendance_rules"), load("zkteco_rules"), load("off_duty_approval")
print("loaded attendance_rules.py, zkteco_rules.py and off_duty_approval.py without Frappe")

# ── 1. The cycle, the codes and the day ───────────────────────────────
if (A.CYCLE_START_DAY, A.CYCLE_END_DAY) != (26, 25):
    fail.append("both minutes say the month runs from the 26th to the 25th")
if A.cycle_window(2026, 3) != (datetime.date(2026, 2, 26), datetime.date(2026, 3, 25)):
    fail.append("the cycle ending in March 2026 runs 26 Feb to 25 Mar: %s" % (A.cycle_window(2026, 3),))
if A.cycle_window(2026, 1) != (datetime.date(2025, 12, 26), datetime.date(2026, 1, 25)):
    fail.append("January's cycle opens in the previous year: %s" % (A.cycle_window(2026, 1),))
if A.cycle_window(2026, 3)[0].day != 26:
    fail.append("a cycle opens on the 26th")
if A.cycle_of("2026-02-26") != (2026, 3) or A.cycle_of("2026-02-25") != (2026, 2):
    fail.append("the 26th belongs to the month after; the 25th closes its own")
if A.cycle_of("2026-12-26") != (2027, 1):
    fail.append("26 December belongs to January of the next year: %s" % (A.cycle_of("2026-12-26"),))
days = A.cycle_days(2026, 3)
if days[0] != datetime.date(2026, 2, 26) or days[-1] != datetime.date(2026, 3, 25):
    fail.append("the register's columns run from the 26th to the 25th: %s to %s" % (days[0], days[-1]))
if len(days) != 28:
    fail.append("the cycle ending March 2026 has 28 days, not %d" % len(days))
if len(A.cycle_days(2026, 4)) != 31:
    fail.append("the cycle ending April 2026 has 31 days, not %d" % len(A.cycle_days(2026, 4)))

for facts, code, why in (
    ({"status": "Present", "shift": "Day Shift"}, A.DAY_SHIFT, "a day worked is M"),
    ({"status": "Present", "shift": "Night Shift"}, A.NIGHT_SHIFT, "a night worked is N"),
    ({"status": "Present"}, A.DAY_SHIFT, "no shift named reads as the day"),
    ({"status": "Absent"}, A.ABSENT, "absent is A"),
    ({"status": "On Leave", "leave_type": "Sick Leave"}, A.SICK, "sick leave is S"),
    ({"status": "On Leave", "leave_type": "Annual Leave"}, A.LEAVE, "other leave is L"),
    ({"status": "Half Day", "shift": "Night"}, A.NIGHT_SHIFT, "a half day is still a day at work"),
    ({"off_duty": 1, "status": "Absent"}, A.OFF_DUTY, "an approved off duty is O, not an absence"),
    ({"holiday": 1}, A.WEEKLY_OFF, "a holiday with no attendance is WO"),
    ({}, "", "nothing known prints nothing"),
):
    got = A.register_code(facts)
    if got != code:
        fail.append("%s: expected %r, got %r" % (why, code, got))
if set(A.CODES) != {"M", "N", "A", "S", "WO", "L", "O"}:
    fail.append("the register's codes are the two documents' own: %s" % (A.CODES,))

ROWS = [
    {"employment": "Permanent", "days": {days[0]: A.DAY_SHIFT, days[1]: A.NIGHT_SHIFT}},
    {"employment": "Casual", "days": {days[0]: A.DAY_SHIFT, days[1]: A.ABSENT}},
    {"employment": "Casual", "days": {days[0]: A.NIGHT_SHIFT, days[1]: A.NIGHT_SHIFT}},
]
counted = A.tallies(ROWS, days[:2])
if counted["Permanents Day"][days[0]] != 1 or counted["Casuals Day"][days[0]] != 1:
    fail.append("the footer counts permanents and casuals apart on the day shift: %s" % counted)
if counted["Casuals Night"][days[0]] != 1 or counted["Permanents Night"][days[0]] != 0:
    fail.append("and on the night shift: %s" % counted)
if counted["Total number of staff in Night shift"][days[1]] != 2:
    fail.append("the night total counts everyone on nights: %s" % counted["Total number of staff in Night shift"])
if set(A.TALLIES) != {"Permanents Day", "Casuals Day", "Permanents Night", "Casuals Night"}:
    fail.append("LPL/HR/07 tallies exactly those four: %s" % (A.TALLIES,))

if (A.FULL_SHIFT_HOURS, A.OVERTIME_IN_SHIFT, A.STANDARD_HOURS) != (12.0, 2.0, 10.0):
    fail.append("a shift is twelve hours inclusive of two of overtime (Reward & Compensation 4.2)")
if A.overtime_hours(12) != 2.0 or A.overtime_hours(10) != 0.0 or A.overtime_hours(8) != 0.0:
    fail.append("overtime starts past the tenth hour: %s" % A.overtime_hours(12))
if A.overtime_hours(None) != 0.0:
    fail.append("nothing worked is no overtime, never a crash")
if A.late_minutes("07:20", "07:00") != 20 or A.late_minutes("07:20", "07:00", grace=30) != 0:
    fail.append("lateness is counted past the grace: %s" % A.late_minutes("07:20", "07:00", grace=30))
if A.late_minutes("06:50", "07:00") != 0:
    fail.append("arriving early is not late")
if A.early_minutes("16:30", "17:00") != 30 or A.early_minutes("17:10", "17:00") != 0:
    fail.append("leaving early is counted, leaving late is not: %s" % A.early_minutes("16:30", "17:00"))
print("the cycle 26 to 25, the register's codes and tallies, the twelve-hour shift")

# ── 2. The three forms ────────────────────────────────────────────────
if A.OFF_DUTY_KINDS != ("Paid", "Ungranted", "Compensation", "Annual Leave", "Compassionate"):
    fail.append("LPL/HR/25 offers exactly its five: %s" % (A.OFF_DUTY_KINDS,))
OFF = {"employee": "HR-EMP-1", "off_date": "2026-03-04", "reason": "Family matter", "kind": "Paid",
       "date_of_joining": "2024-01-01"}
expect("an off-duty request", A.off_duty_errors(OFF))
expect("no date", A.off_duty_errors(dict(OFF, off_date=None)), "date the employee will be absent")
expect("no reason", A.off_duty_errors(dict(OFF, reason=" ")), "reason for the day off")
expect("no classification", A.off_duty_errors(dict(OFF, kind=None)), "how the day is treated")
expect("a day before joining", A.off_duty_errors(dict(OFF, off_date="2023-01-01")), "before the employee joined")

OT = {"overtime_date": "2026-03-04", "requested_by": "HR-EMP-2", "section": "Extrusion",
      "employees": [{"employee": "HR-EMP-1", "hours": 3, "employment": "Casual"},
                    {"employee": "HR-EMP-3", "hours": 2, "employment": "Permanent"}]}
expect("an overtime request", A.overtime_errors(OT))
expect("nobody listed", A.overtime_errors(dict(OT, employees=[])), "List the employees")
expect("no requesting officer", A.overtime_errors(dict(OT, requested_by=None)), "requesting officer")
expect("someone listed twice",
       A.overtime_errors(dict(OT, employees=OT["employees"] + [OT["employees"][0]])), "is listed twice")
expect("no duration", A.overtime_errors(dict(OT, employees=[{"employee": "HR-EMP-1"}])), "duration in hours")
expect("longer than a shift",
       A.overtime_errors(dict(OT, employees=[{"employee": "HR-EMP-1", "hours": 20}])), "longer than a full shift")
if A.coupons(OT["employees"]) != {"Permanent": 1, "Casual": 1}:
    fail.append("the food coupons are counted per employment kind: %s" % A.coupons(OT["employees"]))
if A.COUPON_KINDS != ("Permanent", "Casual"):
    fail.append("LPL/HR/14 issues coupons to casuals and permanent staff")

GP = {"employee": "HR-EMP-1", "pass_date": "2026-03-04", "out_time": "2026-03-04 14:00:00",
      "expected_return": "2026-03-04 16:00:00", "reason": "Clinic"}
expect("a gate pass", A.gate_pass_errors(GP))
expect("no time out", A.gate_pass_errors(dict(GP, out_time=None)), "time the employee leaves")
expect("no reason", A.gate_pass_errors(dict(GP, reason="")), "reason for leaving")
expect("back before leaving", A.gate_pass_errors(dict(GP, expected_return="2026-03-04 13:00:00")),
       "must be after the time of leaving")
print("the three forms: off duty, overtime with its coupons, the gate pass")

# ── 3. Reading a ZKTeco machine ───────────────────────────────────────
if Z.PUNCH_DIRECTION[Z.CHECK_IN] != Z.IN or Z.PUNCH_DIRECTION[Z.CHECK_OUT] != Z.OUT:
    fail.append("punch 0 is a check in and punch 1 a check out")
if Z.PUNCH_DIRECTION[Z.OVERTIME_IN] != Z.IN or Z.PUNCH_DIRECTION[Z.BREAK_OUT] != Z.OUT:
    fail.append("overtime in goes in; a break out goes out")
if Z.direction_of(Z.UNDECIDED) is not None:
    fail.append("a machine that said nothing decides nothing")
if Z.direction_of(Z.CHECK_IN, Z.DIRECTION_OUT) != Z.OUT:
    fail.append("a door that only releases overrides whatever was pressed")
if Z.direction_of(Z.CHECK_OUT, Z.DIRECTION_IN) != Z.IN:
    fail.append("and a door that only admits")
if Z.direction_of("nonsense") is not None:
    fail.append("a punch code that is not a number decides nothing, never a crash")
if Z.DEVICE_DIRECTIONS != (Z.DIRECTION_BOTH, Z.DIRECTION_IN, Z.DIRECTION_OUT):
    fail.append("a device faces one of three ways: %s" % (Z.DEVICE_DIRECTIONS,))

base = datetime.datetime(2026, 3, 2, 7, 0, 0)
TWICE = [
    {"device_user_id": "101", "time": base, "punch": Z.UNDECIDED, "device": "Gate A"},
    {"device_user_id": "101", "time": base + datetime.timedelta(seconds=30), "punch": Z.UNDECIDED, "device": "Gate B"},
    {"device_user_id": "101", "time": base + datetime.timedelta(hours=12), "punch": Z.UNDECIDED, "device": "Gate A"},
]
clean = Z.dedupe(TWICE)
if len(clean) != 2:
    fail.append("a face read twice within %ds is one arrival, even across machines: %s"
                % (Z.DOUBLE_READ_SECONDS, len(clean)))
if len(Z.dedupe(TWICE, per_device=True)) != 3:
    fail.append("per_device keeps a reading from each machine, for sites whose machines stand apart")
if len(Z.dedupe(TWICE, within=1)) != 3:
    fail.append("a shorter window keeps both readings")
if [row["device_user_id"] for row in Z.dedupe(list(reversed(TWICE)))] != ["101", "101"]:
    fail.append("the punches come back in time order whatever order they were read in")
resolved = Z.resolve(clean)
if [row["log_type"] for row in resolved] != [Z.IN, Z.OUT]:
    fail.append("unmarked punches alternate, starting with IN: %s" % [row["log_type"] for row in resolved])
if Z.resolve(clean, opening={"101": Z.IN})[0]["log_type"] != Z.OUT:
    fail.append("someone already inside goes out first")
told = Z.resolve([{"device_user_id": "9", "time": base, "punch": Z.CHECK_OUT, "device": "X"}])
if told[0]["log_type"] != Z.OUT:
    fail.append("a machine that said which way is believed")
oneway = Z.resolve([{"device_user_id": "9", "time": base, "punch": Z.CHECK_IN, "device": "X"}],
                   {"X": Z.DIRECTION_OUT})
if oneway[0]["log_type"] != Z.OUT:
    fail.append("the door wins over the button")
if Z.worked_hours(resolved) != 12.0:
    fail.append("in at seven and out at seven is twelve hours: %s" % Z.worked_hours(resolved))
if Z.worked_hours([{"log_type": Z.IN, "time": base}]) is not None:
    fail.append("an arrival with no departure is no hours, not zero")
if len(Z.pairs(Z.resolve(Z.dedupe([
        {"device_user_id": "1", "time": base, "punch": Z.CHECK_IN, "device": "X"},
        {"device_user_id": "1", "time": base + datetime.timedelta(hours=4), "punch": Z.CHECK_IN, "device": "X"},
])))) != 2:
    fail.append("two arrivals with no departure between them are two open pairs")

if Z.since(None, base, days=7) != base - datetime.timedelta(days=7):
    fail.append("a machine that never synced is read from a few days back")
if Z.since("2026-03-01 06:00:00", base) != datetime.datetime(2026, 3, 1, 6, 0, 0):
    fail.append("otherwise from just after the last sync")
push, unknown = Z.to_push(clean, known_badges={"101"})
if (len(push), len(unknown)) != (2, 0):
    fail.append("a known badge is pushed")
push, unknown = Z.to_push(clean, known_badges=set())
if (len(push), len(unknown)) != (0, 2):
    fail.append("a badge nobody owns is reported, not dropped: %s" % ((len(push), len(unknown)),))
if len(Z.to_push(clean, since_moment=base)[0]) != 1:
    fail.append("nothing already synced is pushed again")

DEV = {"device_name": "Kawempe Gate", "host": "192.168.1.50", "port": 4370, "direction": Z.DIRECTION_BOTH}
expect("a machine", Z.device_errors(DEV))
expect("no host", Z.device_errors(dict(DEV, host=" ")), "IP address")
expect("no port", Z.device_errors(dict(DEV, port=None)), "port")
expect("a port out of range", Z.device_errors(dict(DEV, port=70000)), "between 1 and 65535")
expect("a port that is not a number", Z.device_errors(dict(DEV, port="abc")), "between 1 and 65535")
expect("no direction", Z.device_errors(dict(DEV, direction=None)), "which way the machine faces")
print("the machine: punch codes, the face read twice, the direction, the badge nobody owns")

# ── 4. The DocTypes ───────────────────────────────────────────────────
PAPER = {
    "Attendance Device": ("device_name", "enabled", "host", "port", "comm_key", "direction", "branch",
                          "double_read_seconds", "first_pull_days", "last_sync", "last_status", "last_error",
                          "serial_number", "skip_auto_attendance"),
    "Attendance Device Log": ("device", "device_user_id", "punch_time", "employee", "log_type", "punch",
                              "punch_meaning", "status", "employee_checkin", "error", "pulled_on"),
    "Off Duty Request": ("employee", "badge_no", "department", "section", "off_date", "reason", "kind",
                         "supervisor_remarks", "manager_remarks", "hr_remarks", "status", "workflow_state",
                         "return_remarks", *O.ALL_STAMP_FIELDS),
    "Overtime Request": ("overtime_date", "section", "employees", "requested_by", "total_hours",
                         "authorised_by", "authorised_on", "coupons_permanent", "coupons_casual",
                         "coupons_issued", "status"),
    "Overtime Request Employee": ("employee", "section", "hours", "employment"),
    "Gate Pass": ("employee", "pass_date", "out_time", "expected_return", "actual_return", "reason",
                  "hours_away", "authorised_by", "status"),
}
for name, wanted in PAPER.items():
    spec = doctype(name)
    if not spec:
        fail.append("%s is not there" % name)
        continue
    fields = fields_of(spec)
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the paper or the machine asks for" % (name, fieldname))
for name in ("Off Duty Request", "Overtime Request", "Gate Pass"):
    if not doctype(name).get("is_submittable"):
        fail.append("%s must be submittable: it is approved, and cancelling undoes it" % name)
device = fields_of(doctype("Attendance Device"))
if (device.get("direction") or {}).get("options", "").split("\n") != list(Z.DEVICE_DIRECTIONS):
    fail.append("Attendance Device.direction must offer exactly %s" % (Z.DEVICE_DIRECTIONS,))
if (device.get("comm_key") or {}).get("fieldtype") != "Password":
    fail.append("the machine's communication key is a Password field, not plain Data")
if (device.get("port") or {}).get("default") != "4370":
    fail.append("ZKTeco machines listen on 4370 by default")
log = fields_of(doctype("Attendance Device Log"))
if (log.get("status") or {}).get("options", "").split("\n") != ["Pending", "Pushed", "Duplicate",
                                                                "Unknown Employee", "Failed"]:
    fail.append("a log row says what became of it: %s" % (log.get("status") or {}).get("options"))
for fieldname in ("employee", "log_type", "punch_meaning", "status", "employee_checkin", "error"):
    if not (log.get(fieldname) or {}).get("read_only"):
        fail.append("Attendance Device Log.%s is written by the pull, not typed" % fieldname)
off = fields_of(doctype("Off Duty Request"))
if (off.get("kind") or {}).get("options", "").split("\n") != list(A.OFF_DUTY_KINDS):
    fail.append("Off Duty Request.kind must offer exactly LPL/HR/25's five")
employment = fields_of(doctype("Overtime Request Employee")).get("employment") or {}
if employment.get("options", "").split("\n") != ["Permanent", "Casual"]:
    fail.append("LPL/HR/14's Employment column is Permanent or Casual")
employee = all_fields("Employee")
# Section is not an Employee field: it duplicates Department and was
# removed, so the forms carry their own, defaulted from the department
if "custom_section" in employee:
    fail.append("Employee.custom_section is back: Section duplicates Department")
for fieldname in ("attendance_device_id", "custom_automatic_attendance"):
    if fieldname not in employee:
        fail.append("the Employee has no %s, which attendance needs" % fieldname)
if "attendance_device_id" not in fields_of(upstream_doctype("Employee") or {}):
    fail.append("Frappe HR no longer carries Employee.attendance_device_id: the badge has nowhere to live")
print("the forms, the machine and its log, and the badge on the Employee")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "attendance.py")
drivers = read("hrms_addon", "hrms_addon", "devices.py")
own = {name: fields_of(doctype(name)) for name in PAPER}


def body_of(source, name):
    start = source.index("\ndef %s(" % name)
    rest = source[start + 1:]
    end = rest.index("\ndef ", 1) if "\ndef " in rest[1:] else len(rest)
    return rest[:end]


checkin = fields_of(upstream_doctype("Employee Checkin") or {})
for fieldname in ("employee", "log_type", "time", "device_id", "skip_auto_attendance", "attendance"):
    if checkin and fieldname not in checkin:
        fail.append("the pull writes Employee Checkin.%s, which Frappe HR no longer has" % fieldname)
attendance = fields_of(upstream_doctype("Attendance") or {})
for fieldname in ("employee", "attendance_date", "status", "shift", "leave_type", "working_hours"):
    if attendance and fieldname not in attendance:
        fail.append("the register reads Attendance.%s, which Frappe HR no longer has" % fieldname)
if not re.search(r"def add_log_based_on_employee_field",
                 open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "employee_checkin",
                                   "employee_checkin.py"), encoding="utf-8").read()
                 if os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "employee_checkin",
                                                "employee_checkin.py")) else "def add_log_based_on_employee_field"):
    fail.append("Frappe HR's add_log_based_on_employee_field is gone: the pull has nothing to push to")

for needle, why in (
    ("rules.dedupe(", "the face read twice is collapsed by the rules"),
    ("rules.resolve(", "and the direction worked out by them"),
    ("rules.since(", "a pull starts where the last one stopped"),
    ("add_log_based_on_employee_field", "the punch is pushed through Frappe HR's own API"),
    ("from zk import ZK", "the driver is the pyzk one"),
    ("except ImportError:", "and it is optional: a site without it still runs"),
    ('log.db_set({"status": "Pushed"', "a punch that landed is marked"),
    ('"status": "Unknown Employee"', "a badge nobody owns is reported, not dropped"),
    ('"status": "Failed"', "and one that would not push is kept to try again"),
    ("def retry_failed(", "the punches that never landed can be pushed again"),
    ("connection.disable_device()", "nobody punches while the machine is being read"),
    ("def _disconnect(", "and the machine is always let go"),
):
    if needle not in drivers:
        fail.append("devices.py: %s (%r not found)" % (why, needle))
if "_driver()" not in body_of(drivers, "_connect"):
    fail.append("devices.py must ask for the driver only when a machine is really being reached")
if "from zk import" in drivers.split("def _driver(")[0]:
    fail.append("the driver must not be imported at the top of devices.py: a site without it would not install")
for needle, why in (
    ("rules.off_duty_errors(", "the off-duty request is judged by the rules"),
    ("rules.overtime_errors(", "and the overtime request"),
    ("rules.gate_pass_errors(", "and the gate pass"),
    ("rules.coupons(", "the food coupons are counted by the rules"),
    ("rules.cycle_window(", "the register is bounded by the 26-to-25 cycle"),
    ("rules.register_code(", "each cell comes from the rules"),
    ("rules.tallies(", "and the footer"),
    ("approval.compute_stamps(", "the two signatures are stamped by the workflow"),
    ("custom_automatic_attendance", "top management is marked present without punching"),
    ("def _chase_open_passes(", "a gate pass nobody closed is chased"),
):
    if needle not in glue:
        fail.append("attendance.py: %s (%r not found)" % (why, needle))
for name, module, source in (("authorise_overtime", "attendance", glue), ("reject_overtime", "attendance", glue),
                             ("issue_coupons", "attendance", glue), ("record_return", "attendance", glue),
                             ("pull", "devices", drivers), ("test_connection", "devices", drivers),
                             ("retry_failed", "devices", drivers)):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, source):
        fail.append("%s.%s changes something: a whitelisted POST method" % (module, name))
for name, source in (("register", glue), ("unknown_badges", drivers)):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, source):
        fail.append("%s must be whitelisted for the form" % name)
for name, source in (("authorise_overtime", glue), ("issue_coupons", glue), ("record_return", glue)):
    if "doc.check_permission(" not in body_of(source, name):
        fail.append("attendance.%s must check the caller may act on the document" % name)
if 'doc.check_permission("write")' not in body_of(drivers, "pull"):
    fail.append("devices.pull reaches a machine and writes check-ins: it must check the caller first")
if "frappe.has_permission" not in body_of(drivers, "retry_failed"):
    fail.append("devices.retry_failed pushes check-ins: it must check the caller first")
print("the glue: the rules followed, the driver optional, every button checked and whitelisted")

# ── 6. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "hrms_addon.hrms_addon.attendance.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must build the off-duty workflow")
scheduler = hooks.get("scheduler_events") or {}
for job in ("hrms_addon.hrms_addon.attendance.daily", "hrms_addon.hrms_addon.devices.daily"):
    if job not in (scheduler.get("daily") or []):
        fail.append("the scheduler must run %s" % job)
if "hrms_addon.hrms_addon.devices.pull_all" not in (scheduler.get("hourly") or []):
    fail.append("the machines must be read hourly, or attendance waits a day")
for name, module, prefix, methods in (
        ("off_duty_request", "attendance", "off_duty", ("validate", "on_submit", "on_cancel")),
        ("overtime_request", "attendance", "overtime", ("validate", "on_submit", "on_cancel")),
        ("gate_pass", "attendance", "gate_pass", ("validate", "on_submit", "on_cancel")),
        ("attendance_device", "devices", "device", ("validate",)),
        ("attendance_device_log", "devices", "log", ("validate",))):
    controller = open(os.path.join(APP, "doctype", name, name + ".py"), encoding="utf-8").read()
    for method in methods:
        if "    def %s(self):\n        %s.%s_%s(self)" % (method, module, prefix, method) not in controller:
            fail.append("the %s controller must hand %s to %s.%s_%s" % (name, method, module, prefix, method))
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
for name in PAPER:
    if doctype(name).get("istable"):
        continue
    if name not in carded:
        fail.append("%s is on no workspace card" % name)
    if name not in sidebarred:
        fail.append("%s is in no sidebar" % name)
if "Shift & Attendance" not in navigation.CARDS:
    fail.append("the forms belong on Frappe HR's own attendance page")
if not os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "workspace", "shift_&_attendance",
                                   "shift_&_attendance.json")):
    fail.append("Frappe HR no longer ships the Shift & Attendance workspace")
conn = read("hrms_addon", "hrms_addon", "connections.py")
for name in ("Off Duty Request", "Gate Pass"):
    if name not in conn:
        fail.append("%s must show on the Employee's Connections" % name)

# the off-duty signatures
route = [O.DRAFT, O.PENDING_SUPERVISOR, O.PENDING_MANAGER, O.PENDING_HRM, O.APPROVED]
walked, state = [O.DRAFT], O.DRAFT
while True:
    forward = [t for t in O.TRANSITIONS if t["state"] == state and t["action"] in (O.SUBMIT, O.APPROVE)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != route:
    fail.append("LPL/HR/25 is signed by the Supervisor then the Section Manager, then HR: %s" % walked)
if set(O.STAMPS) != set(O.PENDING_STATES) or set(O.REMARK_FIELDS) != set(O.PENDING_STATES):
    fail.append("every signature block on LPL/HR/25 is stamped: %s" % sorted(O.STAMPS))
for state in O.PENDING_STATES:
    if not [t for t in O.TRANSITIONS if t["state"] == state and t["action"] == O.REJECT]:
        fail.append("%s must be able to refuse the day off" % state)
    if not [t for t in O.TRANSITIONS if t["state"] == state and t["action"] == O.RETURN]:
        fail.append("%s must be able to return it" % state)
expect("returned without saying why", O.step_errors(O.PENDING_MANAGER, O.DRAFT, {}), "Return Remarks")
expect("refused without saying why", O.step_errors(O.PENDING_HRM, O.REJECTED, {}), "HR Manager's remarks")
if any(O.compute_stamps(O.PENDING_HRM, O.DRAFT, "x", "2026-03-04", {"supervisor_by": "a"}).values()):
    fail.append("a return clears every signature")
if set(O.ROLE_WAITING) != set(O.PENDING_STATES):
    fail.append("every pending state must know whose desk it is on")
print("wiring: the workflow on migrate, the hourly pull, the daily jobs, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL ATTENDANCE CHECKS PASSED")
