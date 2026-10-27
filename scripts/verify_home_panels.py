"""Checks the desk home's panels under what waits for the user (Luuka, 20 and
21 Oct 2026), without a bench.

    python scripts/verify_home_panels.py

  1  who sees which panel: since the tabs of dashboards (27 Oct 2026) the
     panels stand on their modules' tabs, for the roles dashboards_rules
     gives them, and the two rules modules name the same roles
     (verify_home_dashboards.py checks the tabs, the overview and the
     switches)
  2  each panel's figures: Payroll Readiness's steps by their days, the
     plants, the output against the same days before, the movement without
     the import's stand-in leaving dates, the deadlines, the pipeline and the
     records' health
  3  the rules agree with what they name: the roles, the statuses and the
     options of the doctypes they read
  4  the readers: the user's own permissions, a part that cannot be read
     left out, each window of days, and nothing whitelisted of their own:
     dashboards.py asks for them
  5  the page: each kind of panel drawn, every value from the server
     escaped, the Attendance Board opened on a plant

The rules are loaded without Frappe; Frappe HR's doctypes are read from
FRAPPE_APPS_ROOT (default ../ERPNext).
"""
import ast
import datetime
import glob
import importlib.util
import io
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


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def options(spec, fieldname):
    for field in (spec or {}).get("fields", []):
        if field.get("fieldname") == fieldname:
            return [value for value in (field.get("options") or "").split("\n") if value]
    return []


def ours(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream(name):
    folder = name.lower().replace(" ", "_")
    for app in ("hrms", "erpnext", "frappe"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(io.open(hits[0], encoding="utf-8"))
    return {}


def body_of(source, name):
    return source.split("def %s(" % name)[1].split("\ndef ")[0]


R = load("home_panels_rules")
H = load("home_rules")
print("loaded home_panels_rules.py without Frappe")
D = datetime.date

# ── 1. Who sees which ─────────────────────────────────────────────────
DR = load("dashboards_rules")
ALL = ["payroll", "plants", "output", "movement", "deadlines", "recruitment", "data_health"]
check(all(getattr(R, name.upper()) == name for name in ALL), "the seven panels by their keys")
check(all(tuple(getattr(R, name)) == tuple(getattr(DR, name)) for name in (
    "HR_ROLES", "EXECUTIVE_ROLES", "PAYROLL_ROLES", "MONEY_ROLES")), "the two rules modules name the same roles")
WHOSE = {"payroll": R.PAYROLL_ROLES, "plants": R.HR_ROLES + R.EXECUTIVE_ROLES,
         "output": R.PAYROLL_ROLES + R.EXECUTIVE_ROLES, "movement": R.HR_ROLES + R.EXECUTIVE_ROLES,
         "deadlines": R.HR_ROLES, "recruitment": R.HR_ROLES + R.EXECUTIVE_ROLES, "data_health": R.HR_ROLES}
check(all(set(DR.PANELS[key][4]) == set(roles) for key, roles in WHOSE.items()),
      "each stands on its tab for the roles it served on the desk, the pipeline management's too now it has a tab: %s"
      % [key for key, roles in WHOSE.items() if set(DR.PANELS[key][4]) != set(roles)])
check(not any(hasattr(R, name) for name in ("PANELS", "SWITCHES", "switched_on", "panels_for", "places")),
      "and nothing of where they go or whether they are switched on is left here to drift from the tabs")
print("rules: the seven panels, each for the roles it is for, as the tabs place them")

# ── 2. Each panel's figures ───────────────────────────────────────────
START, END = D(2026, 9, 26), D(2026, 10, 25)
NOW = datetime.datetime(2026, 10, 21, 9, 30)


def steps_of(facts, today, now=NOW):
    return {step["key"]: step for step in R.payroll_steps(facts, today, START, END, now)}


GOOD = {"clock": {"enabled": 1, "last_success": "2026-10-26 08:00:00.000000", "error": None, "unplaced": 0},
        "overtime": {"total": 3, "waiting": 0, "approved": 0, "slips": 0},
        "output": {"needed": ["Namanve Per Meter"], "paid": ["Namanve Per Meter"], "unpaid_reports": 0},
        "advances": {"run": "paid", "unposted": 0},
        "drafted": {"entries": [{"name": "PE", "docstatus": 1, "status": "Submitted", "slips_submitted": 1}]},
        "slips": {"entries": [{"name": "PE", "docstatus": 1, "status": "Submitted", "slips_submitted": 1}]},
        "bank": {"entries": [{"name": "PE"}], "paid": 1}}
CLOSED = datetime.datetime(2026, 10, 26, 9, 30)
done = steps_of(GOOD, D(2026, 10, 26), CLOSED)
check(all(step["state"] == "done" for step in done.values()) and [step["key"] for step in R.payroll_steps(
    GOOD, D(2026, 10, 26), START, END, CLOSED)] == [key for key, _label, _after in R.STEPS],
    "every step done is done, in the steps' order: %s" % {key: step["state"] for key, step in done.items()})
check(done["clock"]["note"] == "Read past 25 Oct" and R.payroll_note(list(done.values()), START, END)
      == "26 Sep to 25 Oct · 7 of 7 done",
      "once the period is over, the clock is done when it has read past its last day; the heading counts what is done")
running = steps_of(dict(GOOD, clock=dict(GOOD["clock"], last_success="2026-10-21 08:00:00")), D(2026, 10, 21))
check((running["clock"]["state"], running["clock"]["note"]) == ("open", "Read at 08:00"),
      "while the period runs, the clock read this morning is under way, never done: %s" % running["clock"])
after = steps_of(dict(GOOD, clock=dict(GOOD["clock"], last_success="2026-10-21 08:00:00")), D(2026, 10, 27),
                 datetime.datetime(2026, 10, 27, 9, 0))
check(after["clock"]["state"] == "late" and after["clock"]["note"] == "Not read since 21 Oct 08:00",
      "a clock not read for three hours is late whatever the day: %s" % after["clock"])
short = steps_of(dict(GOOD, clock=dict(GOOD["clock"], unplaced=1)), D(2026, 10, 26), CLOSED)
check(short["clock"]["state"] == "open" and short["clock"]["note"] == "Read past 25 Oct · 1 punch not placed",
      "a punch of the period not placed keeps the clock's step open")
quiet = steps_of(dict(GOOD, clock=dict(GOOD["clock"], last_success="2026-10-21 05:00:00")), D(2026, 10, 21))
check((quiet["clock"]["state"], quiet["clock"]["note"]) == ("late", "Not read since 21 Oct 05:00"),
      "four and a half hours without a read is a failing clock, not only days: %s" % quiet["clock"])
eve = steps_of(dict(GOOD, clock=dict(GOOD["clock"], last_success="2026-10-25 23:00:00")), D(2026, 10, 26),
               datetime.datetime(2026, 10, 26, 1, 0))
check((eve["clock"]["state"], eve["clock"]["note"]) == ("open", "Not read past 25 Oct yet"),
      "a read on the last evening is not past the period: its night shift is still to come in: %s" % eve["clock"])
for label, facts, key, want in (
        ("a report left out of a paid run keeps the runs open",
         dict(GOOD, output={"needed": ["Namanve Per Meter"], "paid": ["Namanve Per Meter"], "unpaid_reports": 1}),
         "output", ("open", "1 of 1 paid · 1 report not in a run")),
        ("a paid advance run with recoveries off the payroll is not done",
         dict(GOOD, advances={"run": "paid", "unposted": 2}), "advances",
         ("open", "The advance run is paid · 2 recoveries not on the payroll")),
        ("one entry of two with its slips submitted is not all of them",
         dict(GOOD, slips={"entries": [{"name": "A", "docstatus": 1, "slips_submitted": 1},
                                       {"name": "B", "docstatus": 1, "slips_submitted": 0}]}),
         "slips", ("open", "Slips made, not yet submitted")),
        ("nor one bank entry of two",
         dict(GOOD, bank={"entries": [{"name": "A"}, {"name": "B"}], "paid": 1}), "bank", ("open", "1 of 2 paid"))):
    got = steps_of(facts, D(2026, 10, 21))[key]
    check((got["state"], got["note"]) == want, "%s: %s" % (label, (got["state"], got["note"])))
blank = {"clock": {"enabled": 1, "last_success": "2026-10-21 08:00:00", "error": "Timed out", "unplaced": 2},
         "overtime": {"total": 2, "waiting": 1, "approved": 0, "slips": 0},
         "output": {"needed": ["Kawempe Hourly", "Namanve Per Meter"], "paid": [], "unpaid_reports": 0},
         "advances": {"run": None, "unposted": 0}, "drafted": {"entries": []}, "slips": {"entries": []},
         "bank": {"entries": [], "paid": 0}}
for today, want in ((D(2026, 10, 21), {"clock": "late", "overtime": "open", "output": "todo", "advances": "todo",
                                       "drafted": "todo", "slips": "todo", "bank": "todo"}),
                    (D(2026, 10, 26), {"clock": "late", "overtime": "open", "output": "todo", "advances": "late",
                                       "drafted": "todo", "slips": "todo", "bank": "todo"}),
                    (D(2026, 10, 28), {"clock": "late", "overtime": "late", "output": "late", "advances": "late",
                                       "drafted": "late", "slips": "todo", "bank": "todo"}),
                    (D(2026, 11, 1), {"clock": "late", "overtime": "late", "output": "late", "advances": "late",
                                      "drafted": "late", "slips": "late", "bank": "late"})):
    got = {key: step["state"] for key, step in steps_of(blank, today).items()}
    check(got == want, "on %s each step is late once past its day, and a failing clock at once: %s" % (today, got))
said = steps_of(blank, D(2026, 10, 21))
check(said["clock"]["note"] == "The last read failed · 2 punches not placed"
      and said["output"]["note"] == "0 of 2 paid · Kawempe Hourly, Namanve Per Meter to go"
      and said["advances"]["note"] == "No advance run this month" and said["drafted"]["note"] == "Not made yet",
      "each step says what stands in its way: %s" % {key: step["note"] for key, step in said.items()})
none = steps_of(dict(GOOD, clock=None, bank={R.UNREADABLE: 1}), D(2026, 10, 21))
check((none["clock"]["state"], none["clock"]["note"], none["bank"]["state"], none["bank"]["note"])
      == ("none", "Not open to you", "none", "Could not be read")
      and R.payroll_note(list(none.values()), START, END) == "26 Sep to 25 Oct · 5 of 5 done",
      "a step the user may not read says so, one that could not be read says that, and neither is counted")
check(steps_of(dict(GOOD, clock=dict(GOOD["clock"], enabled=0)), D(2026, 10, 21))["clock"]["note"]
      == "The clock is not switched on", "a clock not switched on is said")
check(steps_of(dict(GOOD, overtime={"total": 0, "waiting": 0, "approved": 0, "slips": 0}), D(2026, 10, 21))["overtime"]
      == {"key": "overtime", "label": "Overtime approved", "state": "done", "note": "No overtime this period",
          "route": ["List", "Overtime Request"], "filters": {"overtime_date": ["between", ["2026-09-26", "2026-10-25"]]}},
      "no overtime is nothing to do")
check(steps_of(dict(GOOD, output={"needed": ["Namanve Per Meter"], "paid": ["Namanve Per Meter"], "unpaid_reports": 2}),
               D(2026, 10, 21))["output"]["note"] == "1 of 1 paid · 2 reports not in a run",
      "a report left out of a paid run keeps the step open")
failed = steps_of(dict(GOOD, drafted={"entries": [{"name": "PE", "docstatus": 0, "status": "Failed"}]}), D(2026, 10, 21))
check(failed["drafted"]["state"] == "late" and failed["drafted"]["note"] == "A payroll entry failed",
      "a payroll entry that failed is late at once")

rows = R.plants([{"name": "a", "branch": "Kawempe"}, {"name": "b", "branch": "Kawempe"}, {"name": "c", "branch": "Namanve"},
                 {"name": "d"}], {"a": "in", "b": "late", "c": "absent", "d": "on_leave"}, {"a": 2.5, "c": 1.25},
                clocks={"Kawempe": 1, "Namanve": 2}, punched={"Kawempe"})
seats = {row["plant"]: row for row in rows}
check([row["plant"] for row in rows] == ["Namanve", "No plant", "Kawempe"]
      and (seats["Kawempe"]["in"], seats["Kawempe"]["late"], seats["Kawempe"]["band"]) == (2, 1, "good")
      and (seats["Namanve"]["silent"], seats["Namanve"]["band"], seats["Namanve"]["overtime"]) == (True, "overdue", 1.2)
      and (seats["No plant"]["on_leave"], seats["No plant"]["silent"], "options" not in seats["No plant"]) == (1, False, True),
      "each plant's people where they are today, the fewest in first, a silent clock in the red: %s" % rows)
check(R.plants_note(rows) == "4 staff · 2 in" and seats["Kawempe"]["options"] == {"branch": "Kawempe"},
      "the heading counts everybody and those in; a plant opens the board on itself")
unknown = R.plants([{"name": "a", "branch": "Kawempe"}], {}, {"a": 1}, {"Kawempe": 1}, set(), known=False)
check(unknown[0]["in"] is None and unknown[0]["band"] == "none" and not unknown[0]["silent"]
      and R.plants_note(unknown) == "1 staff", "for somebody who may read neither the clock nor the attendance, today is not said")
check(R.overtime_hours([{"employee": "a", "hours": 3, "payable_hours": 2, "sent": True},
                        {"employee": "a", "hours": 1.5, "payable_hours": 0, "sent": False}]) == {"a": 3.5},
      "approved overtime is the hours paid where they are on the attendance, else those authorised")

check(R.same_days_before(D(2026, 9, 26), D(2026, 10, 21)) == (D(2026, 8, 26), D(2026, 9, 20))
      and R.same_days_before(D(2026, 12, 26), D(2027, 1, 3)) == (D(2026, 11, 26), D(2026, 12, 4))
      and R.same_days_before(D(2027, 1, 26), D(2027, 1, 26)) == (D(2026, 12, 26), D(2026, 12, 26)),
      "a period part-way through is set against the same days of the one before, across a year's end")
figures = R.output_figures([{"branch": "Namanve", "section": "Per Meter", "total_output": 700, "total_amount": 350},
                            {"branch": "Namanve", "section": "Per Meter", "total_output": 500, "total_amount": 250},
                            {"branch": "Matugga", "section": "Per Piece", "total_output": 300, "total_amount": 90}])
check(figures == {"Namanve": {"metres": 1200.0, "pieces": 0.0, "pay": 600.0},
                  "Matugga": {"metres": 0.0, "pieces": 300.0, "pay": 90.0}}, "metres and pieces by plant, and their pay")
paid = R.output_rows(figures, {"Namanve": {"metres": 1000.0, "pay": 500.0}}, {}, {}, True)
hidden = R.output_rows(figures, {"Namanve": {"metres": 1000.0, "pay": 500.0}}, {}, {}, False)
check([[figure["label"] for figure in row["figures"]] for row in paid] == [
    ["Pieces", "Output pay", "Overtime", "Overtime cost"], ["Metres", "Output pay", "Overtime", "Overtime cost"]]
      and [[figure["label"] for figure in row["figures"]] for row in hidden] == [["Pieces", "Overtime"], ["Metres", "Overtime"]]
      and paid[1]["figures"][0]["percent"] == 20.0 and paid[1]["figures"][0]["direction"] == "up",
      "each plant's figures, money only for those who may see it: %s" % paid)
check(R.change(5, 0) == {"value": 5.0, "before": 0.0, "direction": "up", "percent": None}
      and R.change(None, None)["direction"] == "same" and R.change(80, 100)["percent"] == -20.0,
      "against nothing before there is no share to say")

people = [
    {"name": "j", "status": "Active", "date_of_joining": "2026-10-03", "creation": "2026-10-03 09:00:00",
     "custom_employee_status": "Active"},
    {"name": "k", "status": "Left", "date_of_joining": "2020-01-01", "relieving_date": "2026-09-30",
     "creation": "2026-10-15 09:00:00", "custom_employee_status": "Resigned"},
    {"name": "l", "status": "Left", "date_of_joining": "2020-01-01", "relieving_date": "2026-06-12",
     "creation": "2020-01-01 09:00:00", "custom_employee_status": "Terminated"},
    {"name": "m", "status": "Inactive", "date_of_joining": "2019-01-01", "creation": "2019-01-01 09:00:00",
     "custom_employee_status": "On Hold"},
    {"name": "n", "status": "Active", "date_of_joining": "2018-01-01", "creation": "2018-01-01 09:00:00"},
    # left more than a year ago, recorded before they went: in no month shown and not in the year's turnover
    {"name": "o", "status": "Left", "date_of_joining": "2015-01-01", "relieving_date": "2025-09-30",
     "creation": "2015-01-01 09:00:00", "custom_employee_status": "Resigned"}]
moved = R.movement(people, {"Active": "Active", "On Hold": "Inactive", "Resigned": "Left", "Terminated": "Left"},
                   D(2026, 10, 21))
check([(month["label"], month["joined"], month["left"]) for month in moved["months"]] == [
    ("May", 0, 0), ("Jun", 0, 1), ("Jul", 0, 0), ("Aug", 0, 0), ("Sep", 0, 0), ("Oct", 1, 0)],
    "joiners and leavers by month; a leaver entered after they had gone (the import's stand-in date) moved "
    "nothing: %s" % moved["months"])
check(moved["turnover"] == {"leavers": 1, "rate": 50.0, "headcount": 2}
      and [(row["label"], row["value"]) for row in moved["statuses"]] == [("Active", 2), ("On Hold", 1)]
      and moved["statuses"][0]["band"] == "good" and moved["statuses"][1]["band"] == "today",
      "the year's leavers against today's headcount, and those on the books by status: %s" % moved)
check(R.left_when({"status": "Left", "relieving_date": "2026-06-12", "creation": "2026-06-12 18:00:00"}) == D(2026, 6, 12)
      and R.left_when({"status": "Active", "relieving_date": "2026-06-12"}) is None,
      "a leaver entered on their last day left that day; somebody still here never left")
check(R.movement_note(moved) == "1 left in 12 months · 2 active", "the heading: the leavers and today's headcount")

TODAY = D(2026, 10, 21)
listed = R.deadlines([
    {"kind": "contract", "day": "2026-12-10", "who": "A", "doctype": "Employee Contract", "docname": "C1"},
    {"kind": "probation", "day": "2026-10-01", "who": "B", "doctype": "Employee", "docname": "E1"},
    {"kind": "document", "day": "2026-10-21", "who": "C", "what": "Work Permit", "doctype": "Employee", "docname": "E2"},
    {"kind": "suspension", "day": "2026-10-22", "who": "D", "doctype": "Employee Suspension", "docname": "S1"},
    {"kind": "nonsense", "day": "2026-10-22", "who": "E"}, {"kind": "contract", "day": None, "who": "F"}], TODAY, shown=3)
check([(row["title"], row["when"], row["band"]) for row in listed["rows"]] == [
    ("Probation ends: B", "overdue by 20 days", "overdue"), ("Work Permit expires: C", "today", "today"),
    ("Back from suspension: D", "tomorrow", "soon")]
      and listed["note"] == "1 probation · 1 contract · 1 suspension · 1 document" and listed["total"] == 4,
      "the longest overdue first, as many as are shown, every kind counted in the heading: %s" % listed)
check([R.due_words(TODAY, D(2026, 10, 20)), R.due_words(TODAY, D(2026, 11, 20))] == ["overdue by 1 day", "in 30 days"]
      and R.due_band(TODAY, D(2026, 10, 28)) == "soon" and R.due_band(TODAY, D(2026, 10, 29)) == "later",
      "a deadline's day said, and its band: soon within the week")
check(R.window(TODAY, 30) == (D(2026, 8, 22), D(2026, 11, 20)) and R.window(TODAY, 14, back=0) == (TODAY, D(2026, 11, 4)),
      "each kind is looked for from sixty days back, still undone, to its days ahead")
check(R.probation_open({"custom_probation_status": "On Probation"}) and R.probation_open({})
      and R.probation_open({"custom_probation_status": "Extended"})
      and not R.probation_open({"custom_probation_status": "Confirmed"})
      and not R.probation_open({"custom_probation_status": "Not Confirmed"}),
      "a probation confirmed or not confirmed is decided; an extended one runs to its new date")

pipe = R.pipeline({"requisitions": 2, "openings": [{"name": "O1", "job_title": "Operator", "posted_on": "2026-08-22 10:00:00"},
                                                   {"name": "O2", "job_title": "Clerk", "posted_on": "2026-10-11"}],
                   "applicants": 5, "shortlisted": 2, "interviewed": 1, "offered": 1, "filled": [30, 50, None],
                   "interviews": [{"name": "I2", "applicant_name": "Bo", "scheduled_on": "2026-10-23"},
                                  {"name": "I1", "applicant_name": "Al", "scheduled_on": "2026-10-21"}]}, TODAY)
check([stage["value"] for stage in pipe["stages"]] == [2, 2, 5, 2, 1, 1]
      and pipe["stages"][2]["filters"] == {"status": ["in", ["Open", "Replied", "Hold"]]},
      "each stage's figure, opening the list behind it")
check([figure.get("text", figure.get("value")) for figure in pipe["figures"]] == ["35 days", "40 days", 2]
      and [(row["title"], row["when"], row["band"]) for row in pipe["rows"]] == [("Al", "today", "today"),
                                                                                  ("Bo", "in 2 days", "soon")]
      and [(row["title"], row["when"], row["band"]) for row in pipe["longest"]] == [("Operator", "open 60 days", "today"),
                                                                                     ("Clerk", "open 10 days", "none")],
      "the openings' days open on average, the time to fill, this week's interviews and the openings open longest: %s"
      % pipe)
check([figure["text"] for figure in R.pipeline({}, TODAY)["figures"][:2]] == ["None open", "None filled yet"]
      and R.days_to_fill("2026-08-01", "2026-09-10") == 40 and R.days_to_fill("2026-09-10", "2026-08-01") is None
      and R.week_of(TODAY) == (D(2026, 10, 19), D(2026, 10, 25)), "nothing open or filled is said plainly")
check(R.pipeline_note({"openings": [1, 2], "applicants": 1}) == "2 openings · 1 applicant", "the heading's line")

health_rows = R.data_health([
    {"name": "a", "employee_name": "Ann Okello", "attendance_device_id": "", "salary_mode": "Bank", "bank_ac_no": " ",
     "custom_nssf_no": "N1", "custom_tin": "T1", "custom_nin": "CM1", "date_of_birth": "2010-01-01",
     "date_of_joining": "2025-01-01"},
    {"name": "b", "employee_name": "Okello Ann", "attendance_device_id": "7", "salary_mode": "Cash", "custom_nssf_no": "",
     "custom_tin": "T2", "custom_nin": "cm 1", "date_of_birth": "2010-01-01", "date_of_joining": "2026-01-01"},
    {"name": "c", "employee_name": "Cy", "custom_automatic_attendance": 1, "custom_nssf_no": "N1", "custom_tin": "",
     "date_of_birth": "1944-12-31", "date_of_joining": "2000-01-01"}], {"a", "c"}, TODAY)
health = {row["key"]: row for row in health_rows}
check([row["key"] for row in health_rows] == ["clock", "bank", "salary", "nssf", "tin", "birth", "twice"]
      and [health[key]["value"] for key in ("clock", "bank", "salary", "nssf", "tin", "birth", "twice")]
      == [1, 1, 1, 1, 1, 2, 3],
      "each check counts those it finds: no clock ID (not one marked present without it), bank pay with no account, no "
      "salary structure, no NSSF, no TIN, a birth date to check, and those maybe listed twice: %s"
      % {key: row["value"] for key, row in health.items()})
check(health["twice"]["filters"] == {"status": "Active", "name": ["in", ["a", "b", "c"]]}
      and health["bank"]["filters"] == {"status": "Active", "salary_mode": "Bank", "bank_ac_no": ["is", "not set"]}
      and health["clock"]["band"] == "overdue" and health["nssf"]["band"] == "today",
      "a check a filter can say opens on it; the rest open on those found; those that stop the pay are red")
quiet = {row["key"] for row in R.data_health([{"name": "a", "salary_mode": "Bank"}], None, TODAY, bank_known=False)}
check("bank" not in quiet and "salary" not in quiet,
      "the bank fields hidden from the user, or the assignments they may not read, find nobody missing them")
check(R.data_health([], set(), TODAY) == [], "a clean list says nothing")
print("figures: payroll's steps by their days, the plants, the output, the movement, the deadlines, the pipeline, the records")

# ── 3. What the rules name ────────────────────────────────────────────
security = load("security_rules")
check(set(R.BANK_ROLES) == set(security.PRIVILEGED_ROLES), "the bank fields' readers are those security_rules grant")
check(set(R.HR_ROLES) == set(H.PEOPLE_ROLES), "HR's panels go to those the home calls HR")
months = re.search(r"MONTHS = \(([^)]*)\)", read("hrms_addon", "hrms_addon", "advance_rules.py")).group(1)
check(tuple(re.findall(r'"(\w+)"', months)) == R.MONTHS
      and options(ours("Output Pay Run"), "month") == list(R.MONTHS)
      and options(ours("Salary Advance Processing"), "month") == list(R.MONTHS),
      "the runs' months are named as the runs name them")
overtime = load("overtime_approval")
check(set(R.OVERTIME_WAITING) == {overtime.DRAFT, overtime.REQUESTED, overtime.AUTHORISED}
      and R.OVERTIME_APPROVED == overtime.COSTED and set(R.OVERTIME_COUNTED) == {overtime.COSTED, overtime.SENT},
      "overtime's stages are the workflow's own")
check(set(R.UNPLACED_PUNCHES) <= set(options(ours("Attendance Device Log"), "status")),
      "a punch not placed is one of the log's own statuses: %s" % options(ours("Attendance Device Log"), "status"))
check(set(R.CONTRACT_UNDECIDED) <= set(options(ours("Employee Contract"), "status"))
      and "Renewed" not in R.CONTRACT_UNDECIDED and "Not Renewed" not in R.CONTRACT_UNDECIDED,
      "an undecided contract is one of the contract's statuses, never one renewed or not renewed")
check(set(R.SUSPENSION_RUNNING) <= set(options(ours("Employee Suspension"), "status")),
      "a suspension running is one of its statuses")
check(R.SETTLEMENT_WAITING == load("settlement_approval").PENDING_PAYROLL,
      "a settlement waiting for payroll is the workflow's Pending Payroll")
probation = load("probation_rules")
check(set(R.DECIDED_PROBATION) <= set(probation.PROBATION_STATUSES), "a decided probation is one of probation's statuses")
check(set(R.APPLYING) | {R.SHORTLISTED} <= set(options(upstream("Job Applicant"), "status"))
      and set(R.INTERVIEWED) | set(R.INTERVIEW_COMING) <= set(options(upstream("Interview"), "status"))
      and R.OFFER_LIVE in options(upstream("Job Offer"), "status")
      and "Pending" in options(upstream("Job Requisition"), "status") and "Open" in options(upstream("Job Opening"), "status"),
      "the pipeline's stages are Frappe HR's own statuses, read from %s" % APPS_ROOT)
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
pay_category = [value for value in (custom.get("Employee-custom_pay_category", {}).get("options") or "").split("\n") if value]
check(set(R.OUTPUT_SECTIONS) <= set(pay_category) and set(R.OUTPUT_SECTIONS) == set(options(ours("Output Pay Run"), "section"))
      and {R.PER_METER, R.PER_PIECE} == set(options(ours("Daily Production Report"), "section")),
      "the ways of being paid by output are the employee's and the run's own")
for field in ("custom_probation_end_date", "custom_probation_status", "custom_employee_status", "custom_pay_category",
              "custom_nssf_no", "custom_tin", "custom_nin", "custom_automatic_attendance", "custom_documents"):
    check("Employee-%s" % field in custom, "Employee has %s" % field)
for name in ("Employee Separation-custom_relieving_date", "Employee Separation-custom_clearance",
             "Full and Final Statement-custom_settlement_status", "Full and Final Statement-custom_payroll_date",
             "Full and Final Statement-custom_additional_salary", "Employee Advance-custom_recoveries"):
    check(name in custom, "the custom field %s is there" % name)
print("names: the roles, the statuses and the fields the rules count by are the site's own")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "home_panels.py")
tree = ast.parse(glue)
check(not re.findall(r"@frappe\.whitelist", glue) and "def panels(" not in glue and "def places(" not in glue
      and "def ensure_switches(" not in glue,
      "no call of their own: the dashboards ask for them (dashboards.py), and the switches are the tabs'")
board = read("hrms_addon", "hrms_addon", "dashboards.py")
check("found = home_panels.READERS[key](self.today, self.money, self.roles)" in board
      and "home._or(None, reader.panel, panel)" in board,
      "each is read through the dashboards' guard, with the user's money and roles: one that cannot be read is "
      "logged and left out")
check(set(re.findall(r"rules\.(\w+): _\w+", glue.split("READERS = {")[1])) == {
    "PAYROLL", "PLANTS", "OUTPUT", "MOVEMENT", "DEADLINES", "RECRUITMENT", "DATA_HEALTH"}, "every panel has its reader")
check("ignore_permissions" not in glue and "frappe.db.sql" not in glue, "nothing is read past the user's permissions")
TABLES = {"Advance Recovery", "Leave Advance Recovery", "Journal Entry Account", "Overtime Request Employee", "Salary Detail",
          "Employee Document", "table"}
everything = re.findall(r"frappe\.get_all\(\s*\n?\s*\"?([\w ]+)\"?", glue)
check(everything and set(everything) <= TABLES,
      "frappe.get_all reads only a table's rows, of records read with the user's permissions: %s" % everything)
listed = set(re.findall(r'frappe\.get_list\(\s*"([\w ]+)"', glue))
mays = set(re.findall(r'_may\("([\w ]+)"\)', glue))
check(listed and listed <= mays | {"Overtime Request", "Job Applicant"},
      "every doctype read is first asked whether the user may read it: %s" % sorted(listed - mays))
check('return bool(frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "read"))' in body_of(glue, "_may"),
      "and whether the site has it")
hooks = read("hrms_addon", "hooks.py")
check("home_panels" not in hooks, "nothing of theirs runs at migrate any more: the tabs' switches do (dashboards.py)")
payroll = body_of(glue, "_payroll")
check("attendance_rules.cycle_window(today.year, today.month)" in payroll
      and "rules.payroll_steps(facts, today, start, end, now_datetime())" in payroll,
      "Payroll Readiness counts the period that ends in this month")
for name in ("_plants", "_output"):
    check("attendance_rules.cycle_window(*attendance_rules.cycle_of(today))" in body_of(glue, name),
          "%s counts the period today is in" % name)
plants_fn = body_of(glue, "_plants")
check("home._marks(" in plants_fn and "home_rules.where_today(" in plants_fn
      and 'known=bool(seen.get("clock") or seen.get("attendance"))' in plants_fn,
      "the plants' day is the home's own, with what the user may read")
check('"status": ["in", list(rules.OVERTIME_COUNTED)]' in body_of(glue, "_overtime_lines")
      and '"docstatus": 1' in body_of(glue, "_overtime_lines"),
      "overtime counts what is approved, never a refused request (submitted too)")
check('if row.status not in ("Rejected", "Cancelled")' in body_of(glue, "_overtime_decided"),
      "nor does a refused request wait for anything")
check('"custom_additional_salary": ["is", "not set"]' not in glue and '"Salary Detail", filters={' in body_of(glue, "_settlements")
      and '"parenttype": "Salary Slip", "docstatus": 1' in body_of(glue, "_settlements"),
      "a settlement the payroll paid is known by the submitted slip that took it")
check("if rules.probation_open(row)" in body_of(glue, "_probations")
      and '"status": ["in", list(rules.CONTRACT_UNDECIDED)]' in body_of(glue, "_contracts"),
      "a decided probation or contract is not a deadline")
check('fields += ["salary_mode", "bank_ac_no"]' in body_of(glue, "_data_health")
      and "bank_known = bool(set(roles or ()) & set(rules.BANK_ROLES))" in body_of(glue, "_data_health"),
      "the bank fields are asked for only by those who may read them")
summary = read("hrms_addon", "hrms_addon", "home.py").split("def summary(")[1].split("\ndef ")[0]
check("desk = _or({\"tabs\": [], \"panels\": []}, dashboards.desk_of, user, view, today)" in summary
      and 'sections.pop("today", None)' in summary and '"panels": desk["panels"],' in summary
      and "if any(item[\"place\"] == dashboards_rules.SECTIONS for item in desk[\"panels\"]):" in summary,
      "the home sends which panels and where; Today gives way to the plants")
check("home_panels" not in summary and "READERS" not in summary,
      "and never their figures, which would hold up the greeting")
print("glue: the readers, with the user's own permissions, each over its own days, asked for by the dashboards")

# ── 5. The page ───────────────────────────────────────────────────────
script = read("hrms_addon", "public", "js", "hrms_addon_home.js")
kinds = set(re.findall(r'return \{"kind": "(\w+)"', glue)) | set(re.findall(r'kind="(\w+)"', glue))
drawn = set(re.findall(r"(\w+): \w+_body,", script.split("const KINDS = {")[1].split("};")[0]))
check(kinds and kinds <= drawn, "every kind of panel these send is drawn: %s of %s" % (sorted(kinds), sorted(drawn)))
check("more_top(data) + panels(data) + sections(data) + more_rows(data)" in script
      and '.filter((item) => item.place === "top")' in script and '.filter((item) => item.place === "row")' in script
      and '.filter((item) => item.place === "sections")' in script.split("function sections(")[1].split("\n\t}\n")[0],
      "each panel of the overview drawn where the server places it")
check("if (!parts[current]) return more_frame(item, wide);" in script and 'return one ? more_panel(one, wide) : "";' in script,
      "a frame while its figures are on their way, nothing where they could not be read")
clicked = script.split('else if (what === "more") {')[1].split("} else if")[0]
check('one[element.getAttribute("data-part") || "rows"]' in clicked
      and 'frappe.set_route("Form", row.doctype, row.docname)' in clicked and "go(row)" in clicked,
      "a row opens its record, else the list or page it names")
check("else if (target.options) frappe.route_options = Object.assign({}, target.options);" in script.split("function go(")[1],
      "a page opens on the options the row gives it")
panel_code = script.split("// ── The panels:")[1].split("// a route the server names")[0]
written = set(re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", panel_code))
served = sorted(expr for expr in written if re.search(r"\b(one|step|plant|figure|month|row|item|change)\.", expr))
bare = [expr for expr in served if not (expr.startswith(("esc(", "count(", "icon(", "hours(", "moved(", "money(", "tall(",
                                                          "STATES[", "Math.round", "body(")) or ".map(esc)" in expr)]
check(len(served) >= 20 and not bare, "every value from the server is escaped, or written as a number, a picture or a "
      "class it names (%d looked at): %s" % (len(served), bare[:3]))
board = read("hrms_addon", "hrms_addon", "page", "attendance_board", "attendance_board.js")
shown = board.split('frappe.pages["attendance-board"].on_page_show')[1]
check("const plant = frappe.route_options && frappe.route_options.branch;" in shown and "frappe.route_options = null;" in shown
      and "wrapper.board.branch.set_value(plant);" in shown,
      "the Attendance Board opens on the plant a row names, and forgets it after")
print("page: each kind drawn where it goes, every value escaped")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL DESK HOME PANEL CHECKS PASSED")
