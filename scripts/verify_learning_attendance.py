"""Verify attendance and scheduling (the LMS rebuild, 18 Nov 2026), without a bench:

    python scripts/verify_learning_attendance.py

  1  the rules: a session's days and hours, late, Frappe HR's Present or Absent from the day rows, seats and the
     waiting list, clashes of venue, trainer and employee, a code at the sign-in table, the figures
  2  the paper: Training Attendance, Training Venue and the waiting list carry what the rules and the glue name;
     the session's custom fields ship in the fixtures and hooks
  3  the glue and the wiring: rows written in bulk, Frappe HR kept in step, the sign-in page and the report
"""
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("-", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


R = load("learning_attendance_rules")
D, DT = datetime.date, datetime.datetime

# ── 1. The rules ──────────────────────────────────────────────────────
check("a session's days: from its first to its last", R.session_days("2026-11-20 08:00:00", "2026-11-22 12:00:00")
      == [D(2026, 11, 20), D(2026, 11, 21), D(2026, 11, 22)]
      and R.session_days("2026-11-20 08:00:00", None) == [D(2026, 11, 20)] and R.session_days(None, None) == [])
check("at most a month of days", len(R.session_days("2026-01-01 08:00:00", "2026-12-31 08:00:00")) == R.MOST_DAYS)
check("a day's window: the session's hours on that day",
      R.day_window("2026-11-20 08:00:00", "2026-11-22 12:00:00", "2026-11-21")
      == (DT(2026, 11, 21, 8, 0), DT(2026, 11, 21, 12, 0)))
check("late: signed in more than the minutes allowed after it began",
      R.is_late(DT(2026, 11, 21, 8, 0), DT(2026, 11, 21, 8, 16), 15)
      and not R.is_late(DT(2026, 11, 21, 8, 0), DT(2026, 11, 21, 8, 15), 15))
check("the hours from in to out; nought without both", R.hours_between("08:00:00", "12:30:00") == 4.5
      and R.hours_between("08:00", None) == 0 and R.hours_between("12:00", "08:00") == 0)
check("Frappe HR's Present when they came on any day, Absent once every day is marked and they came on none",
      R.event_attendance(["Absent", "Late"]) == "Present" and R.event_attendance(["Absent", "No-show"]) == "Absent"
      and R.event_attendance(["Excused"]) == "Absent" and R.event_attendance(["Absent", "Invited"]) is None
      and R.event_attendance([]) is None)
check("a mark on Frappe HR's grid becomes a day's status", R.from_event("Present") == "Attended"
      and R.from_event("Absent") == "Absent" and R.from_event(None) is None)
check("seats: none left, some left, no limit", R.seats_left(20, 25) == 0 and R.seats_left(20, 5) == 15
      and R.seats_left(0, 5) is None and R.admit(20, 20) == "Waiting" and R.admit(20, 19) == "Registered"
      and R.admit(None, 500) == "Registered")
WAIT = [{"employee": "B", "status": "Waiting", "requested_on": "2026-11-02 10:00:00", "idx": 2},
        {"employee": "A", "status": "Waiting", "requested_on": "2026-11-01 10:00:00", "idx": 1},
        {"employee": "C", "status": "Withdrawn", "requested_on": "2026-10-01 10:00:00", "idx": 3}]
check("the waiting move up the earliest first, as many as there are seats; the withdrawn never",
      [row["employee"] for row in R.next_in(WAIT, 1)] == ["A"] and [row["employee"] for row in R.next_in(WAIT, 5)]
      == ["A", "B"] and R.next_in(WAIT, 0) == [])
check("nobody registers for a session closed, cancelled or started",
      R.registration_errors({"docstatus": 1}, D(2026, 11, 18)) == ["This session is closed."]
      and R.registration_errors({"docstatus": 0, "event_status": "Cancelled"}, D(2026, 11, 18))
      and R.registration_errors({"docstatus": 0, "start_time": "2026-11-17 08:00:00"}, D(2026, 11, 18))
      == ["This session has started."]
      and not R.registration_errors({"docstatus": 0, "start_time": "2026-11-18 08:00:00"}, D(2026, 11, 18)))
check("two sessions overlap only when one starts before the other ends",
      R.overlap("2026-11-20 08:00", "2026-11-20 10:00", "2026-11-20 09:59", "2026-11-20 11:00")
      and not R.overlap("2026-11-20 08:00", "2026-11-20 10:00", "2026-11-20 10:00", "2026-11-20 11:00"))
check("a trainer is known by employee, else email, else name",
      R.trainer_keys([{"employee": "E1", "trainer_email": "x@y"}, {"trainer_email": " A@B.com "},
                      {"trainer_name": "Outside Trainer"}]) == {"E1", "a@b.com", "outside trainer"})
SESSION = {"name": "S1", "start": "2026-11-20 08:00:00", "end": "2026-11-20 12:00:00", "venue": "Hall A",
           "trainers": {"E9"}, "employees": {"E1", "E2"}}
OTHERS = [
    {"name": "S2", "start": "2026-11-20 11:00:00", "end": "2026-11-20 13:00:00", "venue": "hall a", "trainers": {"X"},
     "employees": {"E2"}},
    {"name": "S3", "start": "2026-11-20 09:00:00", "end": "2026-11-20 10:00:00", "venue": "Hall B", "trainers": {"E9"},
     "employees": set()},
    {"name": "S4", "start": "2026-11-20 13:00:00", "end": "2026-11-20 14:00:00", "venue": "Hall A", "trainers": {"E9"},
     "employees": {"E1"}},
    SESSION,
]
check("clashes: the venue, the trainer and each employee, only where the times overlap, never with itself",
      R.clashes(SESSION, OTHERS) == {"venue": ["S2"], "trainer": ["S3"], "employees": {"E2": ["S2"]}},
      R.clashes(SESSION, OTHERS))
LINES = [{"course": "Fire", "date": "2026-12-03", "start_time": "07:00", "end_time": "09:00", "venue": "Hall A",
          "trainer": "Ann"},
         {"course": "PPE", "date": "2026-12-03", "start_time": "08:00", "end_time": "10:00", "venue": "Hall A",
          "trainer": "Ben"},
         {"course": "5S", "date": "2026-12-03", "start_time": "09:00", "end_time": "11:00", "venue": "Hall B",
          "trainer": "Ben"},
         {"course": "Lean", "date": "2026-12-04", "venue": "Hall A", "trainer": "Ann"}]
check("schedule lines sharing a venue or a trainer at the same time", R.line_clashes(LINES)
      == [("Fire", "PPE", "venue"), ("PPE", "5S", "trainer")], R.line_clashes(LINES))
check("a code: a QR code's employee, a link's, or the number typed", R.code_of("EMP:LPL-0042") == "LPL-0042"
      and R.code_of("https://x/app/training-sign-in?employee=E7&x=1") == "E7" and R.code_of(" 1834 ") == "1834"
      and R.code_of("") == "")
check("an employee signs themselves in from half an hour before until the end, on a day of the session",
      R.own_window("2026-11-20 08:00:00", "2026-11-21 12:00:00", "2026-11-21 07:35:00")
      and not R.own_window("2026-11-20 08:00:00", "2026-11-21 12:00:00", "2026-11-21 07:20:00")
      and not R.own_window("2026-11-20 08:00:00", "2026-11-21 12:00:00", "2026-11-21 12:01:00")
      and not R.own_window("2026-11-20 08:00:00", "2026-11-21 12:00:00", "2026-11-22 09:00:00"))
ROWS = [{"employee": "A", "status": "Attended", "hours": 4, "days": 2}, {"employee": "A", "status": "Late", "hours": 3,
                                                                        "days": 2},
        {"employee": "B", "status": "Attended", "hours": 4, "days": 2}, {"employee": "B", "status": "Absent", "days": 2},
        {"employee": "C", "status": "No-show", "days": 2}, {"employee": "C", "status": "Absent", "days": 2},
        {"employee": "D", "status": "Excused", "days": 2}, {"employee": "D", "status": "Excused", "days": 2},
        {"employee": "E", "status": "Registered", "days": 2}, {"employee": "E", "status": "Invited", "days": 2}]
FIG = R.figures(ROWS)
check("the figures: invited, registered, attended, late, absent days, excused, no-shows, the rates and the hours",
      (FIG["invited"], FIG["registered"], FIG["attended"], FIG["late"], FIG["absent"], FIG["excused"], FIG["no_show"],
       FIG["attendance_rate"], FIG["no_show_rate"], FIG["completion_rate"], FIG["hours"])
      == (5, 3, 2, 1, 2, 1, 1, 50.0, 25.0, 20.0, 11.0), FIG)

# ── 2. The paper ──────────────────────────────────────────────────────
attendance = fields("Training Attendance")
for field in ("training_event", "training_program", "session_date", "day_number", "employee", "employee_name",
              "status", "time_in", "time_out", "hours", "method", "marked_by", "marked_on", "branch", "department",
              "work_section", "supervisor", "supervisor_confirmed", "confirmed_by", "confirmed_on", "remarks"):
    check("Training Attendance has %s" % field, field in attendance)
options = lambda spec, field: [value for value in spec[field]["options"].split("\n") if value]  # noqa: E731
check("its statuses are the rules'", options(attendance, "status") == list(R.STATUSES))
check("its methods are the rules'", options(attendance, "method") == list(R.METHODS))
spec = doctype("Training Attendance")
check("a row per employee per session per day: named at random, imported in bulk",
      spec.get("autoname") == "hash" and spec.get("allow_import") == 1)
check("the employee's own rows only, for them", any(row["role"] == "Employee" and row.get("if_owner")
                                                    for row in spec["permissions"]))
check("the supervisor may confirm", any(row["role"] == "Supervisor" and row.get("write") for row in spec["permissions"]))
venue = fields("Training Venue")
check("a venue: its name, plant, seats and whether it is in use",
      {"venue_name", "branch", "capacity", "is_active", "facilities"} <= set(venue))
waiting = fields("Training Event Waitlist")
check("the waiting list's statuses are the rules'", options(waiting, "status") == list(R.WAITLIST_STATUSES)
      and doctype("Training Event Waitlist").get("istable") == 1)
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
event = {row["fieldname"]: row for row in custom if row["dt"] == "Training Event"}
HOOKS = read("hrms_addon", "hooks.py")
for field in ("custom_venue", "custom_capacity", "custom_seats_left", "custom_allow_walk_in", "custom_registered",
              "custom_attended", "custom_attendance_rate", "custom_no_show_rate", "custom_waitlist"):
    check("Training Event has %s, shipped" % field, field in event and '"Training Event-%s"' % field in HOOKS)
check("the venue follows the location; the waiting list is its table",
      event["custom_venue"]["insert_after"] == "location" and event["custom_venue"]["options"] == "Training Venue"
      and event["custom_waitlist"]["options"] == "Training Event Waitlist")
check("the figures the glue writes after the session is held may change then",
      all(event[field].get("allow_on_submit") for field in ("custom_seats_left", "custom_registered", "custom_attended",
                                                            "custom_attendance_rate", "custom_no_show_rate")))

# ── 3. The glue and the wiring ────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_attendance.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("the rules decide", all(name in GLUE for name in ("rules.session_days(", "rules.event_attendance(",
                                                        "rules.clashes(", "rules.admit(", "rules.next_in(",
                                                        "rules.is_late(", "rules.figures(", "rules.code_of(")))
check("a session's rows written many at once, never one save each", "frappe.db.bulk_insert(DOCTYPE" in GLUE
      and "ignore_duplicates=True" in GLUE)
check("Frappe HR's own Present or Absent kept in step, what the training rules read",
      'frappe.db.set_value(EVENT_EMPLOYEE, line.name, "attendance", wanted' in GLUE)
check("a held session's change reaches the requirements and the certificate it gives",
      "learning.sync_certificates(training_event)" in GLUE and "learning.refresh_later(changed)" in GLUE)
check("a trainer or a venue booked twice refused while Learning Settings say so; an employee said",
      'if cint(settings().get("block_clashes")):' in GLUE and 'title=_("Booked on Another Session at the Same Time")'
      in GLUE)
check("held: a day nobody marked is a no-show", "rules.NO_SHOW" in GLUE[GLUE.index("def event_on_submit"):])
check("only HR or the session's trainer take its attendance", "def _may_mark(event):" in GLUE
      and GLUE.count("_may_mark(event)") >= 2)
check("an employee registers themselves or HR or their supervisor does", "def _who(employee=None):" in GLUE
      and "You register yourself or your own team." in GLUE)
check("only their supervisor or HR confirm a day", "Only their supervisor or HR confirm it." in GLUE)
for name in ("register", "withdraw", "sessions_today", "roll", "sign_in", "self_sign_in", "mark_many", "confirm"):
    check("%s is whitelisted" % name, re.search(r"@frappe\.whitelist\([^)]*\)\ndef %s\(" % name, GLUE))
for needle in ('"hrms_addon.hrms_addon.learning_attendance.event_validate"',
               '"hrms_addon.hrms_addon.learning_attendance.event_on_update"',
               '"hrms_addon.hrms_addon.learning_attendance.event_on_submit"',
               '"hrms_addon.hrms_addon.learning_attendance.schedule_validate"'):
    check("hooks: %s" % needle, needle in HOOKS)
for folder, controller in (("training_attendance", "attendance_validate"), ("training_venue", "venue_validate")):
    source = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    check("%s calls learning_attendance.%s" % (folder, controller), "learning_attendance.%s(self)" % controller in source)
check("one row per employee per session per day, held by the table's key",
      '"Training Attendance": ("training_event", "employee", "session_date")'
      in read("hrms_addon", "hrms_addon", "learning.py"))
page = json.load(open(os.path.join(APP, "page", "training_sign_in", "training_sign_in.json"), encoding="utf-8"))
check("the sign-in page opens to HR and to trainers (the server checks which sessions)",
      {"HR User", "HR Manager", "Employee"} <= {row["role"] for row in page["roles"]})
PAGE_JS = read("hrms_addon", "hrms_addon", "page", "training_sign_in", "training_sign_in.js")
check("the page signs in by code, scans with the camera where it can, escapes what it shows",
      "sign_in" in PAGE_JS and "frappe.ui.Scanner" in PAGE_JS and "frappe.utils.escape_html" in PAGE_JS)
REPORT = json.load(open(os.path.join(APP, "report", "session_attendance", "session_attendance.json"), encoding="utf-8"))
check("Session Attendance replaces the old report, on the Training Event",
      REPORT["name"] == "Session Attendance" and REPORT["ref_doctype"] == "Training Event"
      and not os.path.exists(os.path.join(APP, "report", "training_attendance")))
check("Session Attendance reads through the user's permissions, by session, employee, department or plant",
      'frappe.get_list("Training Event"' in read("hrms_addon", "hrms_addon", "report", "session_attendance",
                                                 "session_attendance.py")
      and 'VIEWS = ("Session", "Employee", "Department", "Plant")' in read(
          "hrms_addon", "hrms_addon", "report", "session_attendance", "session_attendance.py"))
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Training Attendance", "Training Venue", "Session Attendance", "Training Sign-In"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_attendance: OK")
