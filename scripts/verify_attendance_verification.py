"""Each branch verifies its attendance before payroll pays it (attendance_verification.py), checked without a bench.

attendance_verification_rules.py and attendance_verification_approval.py are loaded without Frappe and their rules
run; the doctypes, the glue, the hooks, the forms and the places the lock reaches (overtime, automatic attendance,
deletions, Recreate Salary Slips) are read as files; and what Frappe HR does that the lock and the payroll's wait
stand on is read from its own source.
"""
import datetime
import importlib.util
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read().replace("\r\n", "\n")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(io.open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields_of(spec):
    return {f["fieldname"]: f for f in spec.get("fields", [])}


def check(condition, label, detail=""):
    if not condition:
        fail.append("%s %s" % (label, detail))


def expect(label, got, *needles):
    if not needles:
        check(not got, label + ": expected no errors", got)
        return
    check(len(got) == len(needles), "%s: expected %d error(s)" % (label, len(needles)), got)
    for needle in needles:
        check(any(needle in message for message in got), "%s: expected an error containing %r" % (label, needle), got)


R = load("attendance_verification_rules")
A = load("attendance_verification_approval")
D = datetime.date


def days(first, last):
    return R.days_between(first, last)


# ── 1. The sheet ──────────────────────────────────────────────────────
good = {"company": "LPL", "branch": "Kawempe", "pay_kind": "Monthly", "from_date": "2026-09-26",
        "to_date": "2026-10-25", "period_name": "October 2026", "clashes": []}
expect("a monthly sheet of one payroll month", R.sheet_errors(good))
expect("no company", R.sheet_errors(dict(good, company=None)), "company")
expect("no branch", R.sheet_errors(dict(good, branch="")), "branch")
expect("a payroll neither monthly nor weekly", R.sheet_errors(dict(good, pay_kind="Daily")), "Monthly or Weekly")
expect("no dates", R.sheet_errors(dict(good, to_date=None)), "From and To")
expect("To before From", R.sheet_errors(dict(good, from_date="2026-10-26")), "before From")
expect("a monthly sheet that is not one payroll month", R.sheet_errors(dict(good, period_name=None)), "26th to the 25th")
weekly = dict(good, pay_kind="Weekly", from_date="2026-10-30", to_date="2026-11-05", period_name=None)
expect("a weekly sheet of a week", R.sheet_errors(weekly))
expect("a weekly sheet of 31 days", R.sheet_errors(dict(weekly, from_date="2026-10-06")))
expect("a weekly sheet of 32 days", R.sheet_errors(dict(weekly, from_date="2026-10-05")), "at most 31 days")
expect("another live sheet of the branch on these days", R.sheet_errors(dict(good, clashes=["HR-ATV-2026-00001"])),
       "HR-ATV-2026-00001")
expect("sent the day after its last day", R.ready_errors("2026-10-25", "2026-10-26"))
expect("sent on its last day", R.ready_errors("2026-10-25", "2026-10-25"), "once that day is over")
expect("sent before its last day", R.ready_errors("2026-10-25", "2026-10-20"), "25 Oct 2026")
check(R.title_for("Kawempe", "Monthly", "October 2026", "2026-09-26", "2026-10-25") == "Kawempe, October 2026",
      "a monthly sheet is named by its branch and month")
check(R.title_for("Matugga", "Weekly", None, "2026-10-30", "2026-11-05") == "Matugga, casuals 30 Oct 2026 to 5 Nov 2026",
      "a weekly sheet by its branch and days", R.title_for("Matugga", "Weekly", None, "2026-10-30", "2026-11-05"))
print("the sheet: one payroll month or a week of at most 31 days, one live sheet a branch, sent once its last day is over")

# ── 2. Who is on it ───────────────────────────────────────────────────
staff = {"status": "Active", "salary_structure": True, "date_of_joining": "2020-01-01", "relieving_date": None,
         "custom_pay_category": "Regular"}
casual = dict(staff, custom_pay_category="Weekly")
check(R.on_sheet(staff, "Monthly", "2026-09-26", "2026-10-25"), "a monthly person is on the monthly sheet")
check(R.on_sheet(dict(staff, custom_pay_category=None), "Monthly", "2026-09-26", "2026-10-25"),
      "and so is one with no pay category")
check(R.on_sheet(dict(staff, custom_pay_category="Per Meter"), "Monthly", "2026-09-26", "2026-10-25"),
      "and one paid per meter, who is paid monthly")
check(not R.on_sheet(casual, "Monthly", "2026-09-26", "2026-10-25"), "a casual paid weekly is not on the monthly one")
check(R.on_sheet(casual, "Weekly", "2026-10-30", "2026-11-05"), "but on the weekly one")
check(not R.on_sheet(staff, "Weekly", "2026-10-30", "2026-11-05"), "where a monthly person is not")
# a Per Piece casual is paid by the weekly payroll for their pieces, with no hours (Luuka, 12 Nov 2026: "for per piece
# pay hour is 0 but attendance verification should cater for this"); the weekly structure is assigned to them too
piece = dict(casual, custom_pay_category="Per Piece")
check(R.on_sheet(piece, "Weekly", "2026-10-30", "2026-11-05")
      and R.on_sheet(dict(piece, salary_structure=False), "Weekly", "2026-10-30", "2026-11-05"),
      "a Per Piece casual is on the weekly sheet with the other casuals")
check(not R.on_sheet(piece, "Monthly", "2026-09-26", "2026-10-25"),
      "and never on the monthly one, though the weekly structure is assigned to them")
check(R.by_the_hour(casual) and not R.by_the_hour(piece) and not R.by_the_hour(staff)
      and not R.by_the_hour(dict(staff, custom_pay_category=None)),
      "only a casual paid by the hour has hours to count: a Per Piece casual's are nought")
# a week the plant's Casual Hours Sheets give is theirs on a weekly sheet, as the weekly payroll pays it (Luuka, 12 Nov
# 2026: "validate attendace varies from the casual hour sheet"; "for casuals the attendance verification should be from
# casual hours sheet")
plain = dict.fromkeys(R.FIGURES, 0)
outside = dict(plain, worked=1, hours_worked=10.0, overtime_hours=1.0)
inside = dict(plain, worked=4, half_day=1, absent=1, leave=1, off=1, not_marked=2, hours_worked=36.0, overtime_hours=3.0)
check(R.with_hours_sheet(outside, inside, {"hours": 50, "overtime": 6, "days": 5})
      == dict(plain, worked=6, absent=1, leave=1, off=1, hours_worked=60.0, overtime_hours=7.0),
      "the sheet's hours, overtime and days for the days it gives, not the clock's; their leave, absences and days off "
      "as marked; none of them 'not marked'", R.with_hours_sheet(outside, inside, {"hours": 50, "overtime": 6, "days": 5}))
check(R.with_hours_sheet(outside, inside, {"hours": 40}, inside)
      == dict(plain, worked=5, half_day=1, absent=1, leave=1, off=1, hours_worked=50.0, overtime_hours=1.0),
      "a sheet that gives no days leaves the days worked to the attendance over its days, never its hours",
      R.with_hours_sheet(outside, inside, {"hours": 40}, inside))
# the review of b453383 (12 Nov 2026): weeks that do not line up count no worked day twice and lose none. A sheet's days
# worked count on the verification holding its last day; on the one before, its days add no worked day of their own
check(R.with_hours_sheet(outside, inside, {}, None)
      == dict(plain, worked=1, absent=1, leave=1, off=1, hours_worked=10.0, overtime_hours=1.0),
      "the days of a sheet whose last day falls on the next verification add no days worked here: they are counted there",
      R.with_hours_sheet(outside, inside, {}, None))
week = {"from_date": "2026-10-29", "to_date": "2026-11-04", "people": 461}
check(R.hours_sheet_issue("HR-CHS-1", dict(week, state="Approved"), "2026-10-30", "2026-11-05") is None,
      "an approved sheet leaves nothing to put right")
said = R.hours_sheet_issue("HR-CHS-2", dict(week, state="Draft"), "2026-10-30", "2026-11-05")
check(R.issue_text(said) == "461 casuals, 30 Oct 2026 to 4 Nov 2026: Casual hours not yet sent to the General Manager "
                            "(HR-CHS-2)" and said["employee"] is None and said["reference_doctype"] == "Casual Hours Sheet",
      "one not yet sent is one line for all its casuals, over its days within the sheet's", said)
said = R.hours_sheet_issue("HR-CHS-3", dict(week, state="Pending General Manager", people=1), "2026-10-30", "2026-11-05")
check(R.issue_text(said) == "1 casual, 30 Oct 2026 to 4 Nov 2026: Casual hours waiting for the General Manager (HR-CHS-3)",
      "and one sent waits for the General Manager", R.issue_text(said))
for status in ("Inactive", "Suspended", "Left", "", None):
    check(not R.on_sheet(dict(staff, status=status), "Monthly", "2026-09-26", "2026-10-25"),
          "only the active are on it, not one whose status is %r" % status)
for structure in (False, None, ""):
    check(not R.on_sheet(dict(staff, salary_structure=structure), "Monthly", "2026-09-26", "2026-10-25"),
          "nobody with no salary structure assigned by its last day (%r): the payroll pays nobody else" % structure)
check(not R.on_sheet({key: value for key, value in staff.items() if key != "salary_structure"}, "Monthly",
                     "2026-09-26", "2026-10-25"), "nor one whose structure was never looked up")
# a weekly sheet is every active weekly casual (Luuka, 11 Nov 2026: "the employee should be weekly casuals"): the weekly
# payroll gives a casual the weekly structure itself when it pays them
for structure in (False, None, ""):
    check(R.on_sheet(dict(casual, salary_structure=structure), "Weekly", "2026-10-30", "2026-11-05"),
          "a weekly casual with no salary structure yet (%r) is on the weekly sheet: the weekly payroll gives them "
          "theirs when it pays them" % structure)
check(not R.on_sheet(dict(casual, salary_structure=False, status="Inactive"), "Weekly", "2026-10-30", "2026-11-05")
      and not R.on_sheet(dict(casual, salary_structure=False, date_of_joining="2026-11-06"), "Weekly", "2026-10-30",
                         "2026-11-05"), "though only one active and on the books in its days")
check(not R.on_sheet(dict(staff, status="Left", relieving_date="2026-10-10"), "Monthly", "2026-09-26", "2026-10-25"),
      "not even one who left during it")
check(not R.on_sheet(dict(staff, date_of_joining="2026-10-26"), "Monthly", "2026-09-26", "2026-10-25"),
      "nobody who joins after its last day")
check(R.on_sheet(dict(staff, date_of_joining="2026-10-25"), "Monthly", "2026-09-26", "2026-10-25"),
      "one who joins on its last day is")
check(not R.on_sheet(dict(staff, relieving_date="2026-09-25"), "Monthly", "2026-09-26", "2026-10-25"),
      "nobody whose last day was before its first day")
check(R.on_sheet(dict(staff, relieving_date="2026-10-10"), "Monthly", "2026-09-26", "2026-10-25"),
      "one still active, serving notice to a day within it, is")
check(R.on_sheet(dict(staff, relieving_date="2026-09-26"), "Monthly", "2026-09-26", "2026-10-25"),
      "and one whose last day is its first day")
mixed = [{"employee": "A", "status": "Active"}, {"employee": "L", "status": "Left"}, {"employee": "S", "status": "Suspended"},
         {"employee": "I", "status": "Inactive"}, {"employee": "N", "status": None}]
check([row["employee"] for row in R.payroll_people(mixed)] == ["A"], "a payroll waits only for its active people")
print("who is on it: the branch's active people with a salary structure, on the books for any of its days, paid the "
      "way the sheet pays")

# ── 3. A person's line ────────────────────────────────────────────────
week = days("2026-10-19", "2026-10-25")  # Mon..Sun
# a weekly sheet's Hours Worked (Luuka, 12 Nov 2026: "for weekly add no of hours worked"): the hours the weekly payroll
# pays for the days worked, those marked up to a full day, a day marked with none a full day, a half day half of one
casual_week = R.person_figures(
    dict(staff, custom_pay_category="Weekly"),
    {D(2026, 10, 19): "M", D(2026, 10, 20): "M", D(2026, 10, 21): "N", D(2026, 10, 22): "M", D(2026, 10, 23): "A",
     D(2026, 10, 24): "M", D(2026, 10, 25): "WO"},
    [D(2026, 10, 24)], {D(2026, 10, 21): "Half Day"}, 2, week,
    {D(2026, 10, 19): 10, D(2026, 10, 20): 8, D(2026, 10, 22): 12, D(2026, 10, 23): 9, D(2026, 10, 24): 10}, 10)
check(casual_week["hours_worked"] == 33.0 and casual_week["worked"] == 4,
      "a weekly casual's hours: 10 and 8 as marked, a half day with none 5, 12 marked paid as the full day of 10; not "
      "an absent day's, nor a day the clock saw and nobody marked", casual_week)
check(R.person_figures(staff, {D(2026, 10, 19): "M"}, [], {}, 0, week)["hours_worked"] == 0,
      "a monthly sheet counts no hours")
W = load("weekly_pay_rules")
for status, worked, standard in (("Present", 8, 10), ("Present", 12, 10), ("Present", None, 10), ("Present", 0, 10),
                                 ("Half Day", None, 10), ("Half Day", 4, 10), ("Work From Home", None, 8),
                                 ("Present", "7.5", 10)):
    check(R.day_hours(status, worked, standard) == W.day_hours(status, worked, standard),
          "the sheet's hours of a day are the weekly payroll's (%s, %r, %r)" % (status, worked, standard),
          (R.day_hours(status, worked, standard), W.day_hours(status, worked, standard)))
check("hours_worked" in R.FIGURES and R.totals([casual_week, casual_week])["hours_worked"] == 66.0,
      "the sheet's total Hours Worked is its people's")
codes = {D(2026, 10, 19): "M", D(2026, 10, 20): "N", D(2026, 10, 21): "A", D(2026, 10, 22): "L",
         D(2026, 10, 23): "S", D(2026, 10, 25): "WO"}
line = R.person_figures(staff, codes, [], {D(2026, 10, 19): "Half Day"}, 3.456, week)
check(line == {"worked": 2, "half_day": 1, "absent": 1, "leave": 2, "off": 1, "not_marked": 1, "overtime_hours": 3.46,
              "hours_worked": 0},
      "the Board's letters counted: shifts worked, half days among them, absences, leave and sick, days off, "
      "a day with no letter", line)
line = R.person_figures(staff, dict(codes, **{"2026-10-24": "M"}), ["2026-10-24"], {}, None, week)
check(line["worked"] == 2 and line["not_marked"] == 1 and line["overtime_hours"] == 0,
      "a day the clock saw and nobody marked is not counted worked: it is not marked", line)
check(R.person_figures(staff, {D(2026, 10, 24): "O"}, [], {}, 0, [D(2026, 10, 24)])["off"] == 1,
      "an approved off-duty day is a day off")
joined = dict(staff, date_of_joining="2026-10-22")
line = R.person_figures(joined, codes, [], {}, 0, week)
check(line["worked"] == 0 and line["absent"] == 0 and line["leave"] == 2 and line["not_marked"] == 1,
      "the days before somebody joined are not theirs to count", line)
left = dict(staff, relieving_date="2026-10-20")
check(R.person_figures(left, {}, [], {}, 0, week)["not_marked"] == 2, "nor the days after they left")
print("a line: the Attendance Board's letters, counted over the days the person was on the books")

issues = R.person_issues(dict(staff, employee="E1", employee_name="Ann"), {D(2026, 10, 19): "M", D(2026, 10, 24): "M"},
                         [D(2026, 10, 24)], week)
check([(row["issue"], str(row["from_date"]), str(row["to_date"]), row["days"]) for row in issues] == [
    (R.NOT_MARKED, "2026-10-20", "2026-10-23", 4), (R.CLOCKED, "2026-10-24", "2026-10-24", 1),
    (R.NOT_MARKED, "2026-10-25", "2026-10-25", 1)],
      "what stops it: runs of days not marked, and the days the clock saw, earliest first", issues)
check(all(row["employee"] == "E1" and row["employee_name"] == "Ann" for row in issues), "each line says whose it is")
check(R.person_issues(dict(joined, employee="E2"), {}, [], week)[0]["from_date"] == D(2026, 10, 22),
      "nobody is asked to mark a day before they joined")
text = R.issue_text(issues[0])
check(text == "Ann, 20 Oct 2026 to 23 Oct 2026: Not marked", "a line to put right reads as a sentence", text)
request = R.request_issue({"employee": "E1", "employee_name": "Ann"}, {"name": "HR-LAP-1", "from_date": "2026-10-21",
                                                                        "to_date": "2026-10-21"},
                          R.LEAVE_WAITING, "Leave Application")
check(request["reference_doctype"] == "Leave Application" and request["reference_name"] == "HR-LAP-1"
      and request["days"] == 1 and R.issue_text(request).endswith("(HR-LAP-1)"),
      "a request on its way is a line too, with the request named", request)

stored = [{"employee": "E1", "employee_name": "Ann", "worked": 20, "half_day": 0, "absent": 1, "leave": 0, "off": 4,
           "not_marked": 0, "overtime_hours": 2}]
check(R.changed_people(stored, [dict(stored[0])]) == [], "the same figures read twice: nothing changed")
check(R.changed_people(stored, [dict(stored[0], absent=2)]) == ["Ann"], "a figure that moved names the person")
check(R.changed_people(stored, stored + [{"employee": "E2", "employee_name": "Bob"}]) == ["Bob"],
      "and so does somebody new on it")
check(R.changed_people(stored, []) == ["Ann"], "or somebody gone from it")
check(R.changed_people(stored, [dict(stored[0], overtime_hours=2.0)]) == [], "2 hours and 2.0 hours are the same")
check(R.totals(stored + [dict(stored[0], employee="E2", worked=5)])["worked"] == 25, "the totals add the lines")
print("what stops it: days not marked, days the clock saw, requests on their way; figures read again are compared")

# ── 4. What a verified sheet holds ────────────────────────────────────
sheets = [{"name": "HR-ATV-1", "branch": "Kawempe", "from_date": "2026-09-26", "to_date": "2026-10-25",
           "employees": ["E1", "E2"]},
          {"name": "HR-ATV-2", "branch": "Kawempe", "from_date": "2026-10-30", "to_date": "2026-11-05",
           "employees": ["C1"]}]
spans = R.spans_by_employee(sheets)
check(set(spans) == {"E1", "E2", "C1"} and spans["E1"][0][2] == "HR-ATV-1", "each person's verified days", spans)
check(R.held(spans["E1"], ["2026-10-01", "2026-10-26"]) == [(D(2026, 10, 1), "HR-ATV-1", "Kawempe")],
      "a day of the verified month is held, the next month's is not")
check(R.held(spans["E1"], ["2026-09-25", "2026-09-26", "2026-10-25"]) == [
    (D(2026, 9, 26), "HR-ATV-1", "Kawempe"), (D(2026, 10, 25), "HR-ATV-1", "Kawempe")],
      "its first and last days are held, the day before it is not")
check(R.unverified(spans["C1"], ["2026-10-29", "2026-10-30", "2026-11-05", "2026-11-06"]) == [
    D(2026, 10, 29), D(2026, 11, 6)], "the days no verified sheet covers")
check(R.unverified(spans.get("E9"), ["2026-10-01"]) == [D(2026, 10, 1)], "nobody on a sheet has nothing verified")
message = R.lock_message("Ann", R.held(spans["E1"], ["2026-10-01", "2026-10-02", "2026-10-05"]))
check("Ann" in message and "1 Oct 2026 to 2 Oct 2026, 5 Oct 2026" in message and "HR-ATV-1 (Kawempe)" in message
      and "reopens" in message, "the refusal names the person, the days, the sheet and what to do", message)
print("the lock: a verified day of somebody on the sheet, named with its sheet")

# ── 5. The payroll ────────────────────────────────────────────────────
for value, on in ((None, True), ("", True), ("1", True), (1, True), ("0", False), (0, False), (0.0, False)):
    check(R.gate_on({R.SETTING: value}) is on, "Payroll Settings %r: payroll waits %s" % (value, on))
check(R.gate_on({}) and R.gate_on(None), "a site that never saved the setting waits")
people = [{"employee": "E1", "employee_name": "Ann", "branch": "Kawempe"},
          {"employee": "E2", "employee_name": "Bob", "branch": "Kawempe"},
          {"employee": "E3", "employee_name": "Cy", "branch": "Matugga"},
          {"employee": "E4", "employee_name": "Di", "branch": None}]
gaps = R.payroll_gaps(people, sheets, "2026-09-26", "2026-10-25")
check(set(gaps) == {"Matugga", ""} and [row["employee"] for row in gaps["Matugga"]] == ["E3"]
      and len(gaps["Matugga"][0]["days"]) == 30, "a monthly payroll: everybody on a verified sheet for every day", gaps)
check(not R.payroll_gaps(people[:2], sheets, "2026-09-26", "2026-10-25"), "a branch verified: nothing stops it")
check(R.payroll_gaps(people[:1], sheets, "2026-09-26", "2026-10-26")["Kawempe"][0]["days"] == [D(2026, 10, 26)],
      "one day past the sheet is a day unverified")
weekly_people = [{"employee": "C1", "employee_name": "Cas", "branch": "Kawempe"}]
check(not R.payroll_gaps(weekly_people, sheets, "2026-10-30", "2026-11-05", {"C1": [D(2026, 10, 30), D(2026, 11, 2)]}),
      "a weekly payroll: the days it pays are verified")
late = R.payroll_gaps(weekly_people, sheets, "2026-10-30", "2026-11-05", {"C1": [D(2026, 10, 29), D(2026, 11, 2)]})
check(late and late["Kawempe"][0]["days"] == [D(2026, 10, 29)],
      "a day marked late, before the payroll's Start, needs its own verified sheet", late)
check(not R.payroll_gaps(weekly_people, sheets, "2026-10-30", "2026-11-05", {"C1": []}),
      "somebody a weekly payroll pays no day is not stopped")
lines = R.gaps_message(gaps, {"Matugga": "Pending General Manager"}, {"Kawempe"})
check(lines == ["Matugga: attendance not verified yet (waiting for the General Manager).",
                "No branch: Di. Set their branch, then verify their attendance there."],
      "the payroll's refusal: a line per branch, what its sheet waits for, and nobody without a branch", lines)
check(R.gaps_message({"Matugga": gaps["Matugga"]}, {}, set()) == ["Matugga: attendance not verified yet (not started)."],
      "a branch with no sheet: not started")
check(R.gaps_message({"Matugga": gaps["Matugga"]}, {"Matugga": "Draft"}, set())[0].endswith("(with HR)."),
      "a branch whose sheet is a draft: with HR")
moved = R.gaps_message({"Kawempe": [{"employee": "E7", "employee_name": "New"}]}, {}, {"Kawempe"})
check(moved == ["Kawempe: New not on its verified sheet. The General Manager reopens it, and it is verified again."],
      "a branch verified without somebody who joined or moved in since: reopened and verified again", moved)
many = [{"employee": "E%d" % n, "employee_name": "P%d" % n} for n in range(8)]
check(R.names_text(many) == "P0, P1, P2, P3, P4 and 3 more", "a long list of names is cut short", R.names_text(many))
status = R.branch_lines(people, sheets[:1], {"Matugga": "Draft"}, "2026-09-26", "2026-10-25")
check([(row["branch"], row["people"], row["missing"], row["state"]) for row in status] == [
    ("Kawempe", 2, 0, "Verified"), ("Matugga", 1, 1, "with HR"), ("", 1, 1, "No branch")],
      "the payroll form's line per branch", status)
check(status[0]["sheets"][0]["name"] == "HR-ATV-1", "with the sheet that verified it")
part = R.branch_lines(people[:2] + [{"employee": "E9", "employee_name": "Ed", "branch": "Kawempe"}], sheets[:1], {},
                      "2026-09-26", "2026-10-25")
check(part[0]["state"] == "Not all on the verified sheet" and part[0]["missing"] == 1,
      "a verified branch with somebody missing says so", part)
print("the payroll: everybody it pays on a verified sheet for every day it pays them, or the branches named")

# ── 6. A new weekly sheet's days ──────────────────────────────────────
check(R.weekly_dates("2026-10-29", None, "2026-11-06") == (D(2026, 10, 30), D(2026, 11, 5)),
      "on from the branch's last weekly sheet to yesterday")
check(R.weekly_dates(None, "2026-10-28", "2026-11-06") == (D(2026, 10, 29), D(2026, 11, 5)),
      "else on from the last weekly payroll")
check(R.weekly_dates(None, None, "2026-11-06") == (D(2026, 10, 30), D(2026, 11, 5)), "else the last seven days")
check(R.weekly_dates("2026-11-05", None, "2026-11-06") == (D(2026, 11, 5), D(2026, 11, 5)),
      "never starting after yesterday")
check(R.days_text([D(2026, 10, 1), D(2026, 10, 2), D(2026, 10, 9)]) == "1 Oct 2026 to 2 Oct 2026, 9 Oct 2026",
      "days read as runs")
check(R.runs([]) == [] and R.days_between("2026-10-02", "2026-10-01") == [], "nothing from nothing")
print("a weekly sheet runs on from the last")

# ── 7. The steps ──────────────────────────────────────────────────────
spec = doctype("Attendance Verification")
fields = fields_of(spec)
options = fields["status"]["options"].split("\n")
check(all(row["status"] in options for row in A.STATES), "every state is a Status option", options)
check(all(not row["send_email"] for row in A.STATES), "no state emails a role: the branch's people are told by name")
check({row["state"] for row in A.STATES if row.get("doc_status") == "1"} == {A.VERIFIED}, "Verified submits")
check({row["state"] for row in A.STATES if row.get("doc_status") == "2"} == {A.REOPENED}, "Reopened cancels")
moves = {(row["state"], row["action"], row["next_state"], row["allowed"]) for row in A.TRANSITIONS}
check(moves == {
    (A.DRAFT, A.SEND, A.PENDING_GM, "HR User"), (A.DRAFT, A.SEND, A.PENDING_GM, "HR Manager"),
    (A.PENDING_GM, A.VERIFY, A.VERIFIED, "General Manager"), (A.PENDING_GM, A.VERIFY, A.VERIFIED, "HR Manager"),
    (A.PENDING_GM, A.RETURN, A.DRAFT, "General Manager"), (A.PENDING_GM, A.RETURN, A.DRAFT, "HR Manager"),
    (A.VERIFIED, A.REOPEN, A.REOPENED, "General Manager"), (A.VERIFIED, A.REOPEN, A.REOPENED, "HR Manager")},
      "HR sends, the General Manager (or the HR Manager standing in) verifies, returns or reopens", moves)
check(A.next_states(A.DRAFT, ["HR User"]) == [(A.SEND, A.PENDING_GM)] and not A.next_states(A.PENDING_GM, ["HR User"]),
      "HR may not verify")
check(set(A.ACTIONS) == {row["action"] for row in A.TRANSITIONS}, "every action is used")
perms = {row["role"]: row for row in spec["permissions"]}
for row in A.STATES:
    check(perms.get(row["allow_edit"], {}).get("write"), "%s edits %s: it may write" % (row["allow_edit"], row["state"]))
check(perms["General Manager"].get("submit") and perms["General Manager"].get("cancel"),
      "the General Manager's Verify submits and Reopen cancels")
check(not perms["HR User"].get("submit") and not perms["HR User"].get("cancel"), "HR neither submits nor cancels")
check(perms["Payroll Officer"].get("read") and not perms["Payroll Officer"].get("write"), "payroll reads it")
check(A.PERMISSIONS == {A.DOCTYPE: {"General Manager": ("read", "write", "submit", "cancel", "print", "report")}},
      "and the site grants the General Manager the same")

ready = {"people": 3, "issues": [], "changed": [], "sheet_errors": []}
expect("sent with nothing to put right", A.step_errors(A.DRAFT, A.PENDING_GM, ready))
expect("sent with a day not marked", A.step_errors(A.DRAFT, A.PENDING_GM, dict(ready, issues=["Ann, 1 Oct: Not marked"])),
       "Put these right first, then Get Attendance again: Ann, 1 Oct: Not marked")
expect("sent with nobody on it", A.step_errors(A.DRAFT, A.PENDING_GM, dict(ready, people=0)), "Nobody is on this sheet")
expect("sent before its last day is over", A.step_errors(A.DRAFT, A.PENDING_GM,
                                                         dict(ready, sheet_errors=["The sheet runs to 25 Oct"])),
       "The sheet runs to 25 Oct")
expect("verified as sent", A.step_errors(A.PENDING_GM, A.VERIFIED, ready))
expect("verified after the attendance moved", A.step_errors(A.PENDING_GM, A.VERIFIED, dict(ready, changed=["Ann"])),
       "changed after these figures were read (Ann)")
expect("verified with something new to put right",
       A.step_errors(A.PENDING_GM, A.VERIFIED, dict(ready, issues=["Bob, 3 Oct: Leave waiting for approval"])),
       "Put these right first")
expect("sent while the attendance moves is fine: it is read again as it goes",
       A.step_errors(A.DRAFT, A.PENDING_GM, dict(ready, changed=["Ann"])))
expect("returned without a word", A.step_errors(A.PENDING_GM, A.DRAFT, {}), "Return Remarks")
expect("returned with what to put right", A.step_errors(A.PENDING_GM, A.DRAFT, {"return_remarks": "Kato's 3rd"}))
expect("saved where it stands", A.step_errors(A.DRAFT, A.DRAFT, dict(ready, issues=["x"])))
long = A.step_errors(A.DRAFT, A.PENDING_GM, dict(ready, issues=["line %d" % n for n in range(25)]))
check("and 15 more" in long[0] and "line 9" in long[0] and "line 10" not in long[0],
      "a long list of what to put right is cut short", long)

now = "2026-10-26 09:00"
stamps = A.compute_stamps(A.DRAFT, A.PENDING_GM, "hro@luuka", now, {})
check(stamps["prepared_by"] == "hro@luuka" and stamps["prepared_on"] == now and not stamps["verified_by"],
      "sent: HR's signature", stamps)
stamps = A.compute_stamps(A.PENDING_GM, A.VERIFIED, "gm@luuka", now, stamps)
check(stamps["prepared_by"] == "hro@luuka" and stamps["verified_by"] == "gm@luuka", "verified: the GM's too", stamps)
check(A.compute_stamps(A.PENDING_GM, A.DRAFT, "gm@luuka", now, stamps) == dict.fromkeys(A.ALL_STAMP_FIELDS),
      "returned: the signatures go, as the sheet is read again")
check(A.compute_stamps(A.DRAFT, A.DRAFT, "x", now, {"prepared_by": "a"})["prepared_by"] == "a", "a save keeps them")
check(A.compute_stamps(None, A.DRAFT, "x", now, {"prepared_by": "a"}) == dict.fromkeys(A.ALL_STAMP_FIELDS),
      "a new sheet has none")
print("the steps: HR sends, the General Manager verifies or returns with a reason, and reopens")

# ── 8. The doctypes ───────────────────────────────────────────────────
check(spec["is_submittable"] == 1 and spec["autoname"] == "HR-ATV-.YYYY.-.#####" and spec["title_field"] == "title",
      "the sheet is submittable, numbered and titled")
check(spec["field_order"] == [f["fieldname"] for f in spec["fields"]], "its field order is its fields")
for name in ("company", "branch", "pay_kind", "from_date", "to_date"):
    check(fields[name].get("reqd"), "%s is required" % name)
check(fields["pay_kind"]["options"].split("\n") == list(R.KINDS), "Payroll is Monthly or Weekly")
check(fields["employees"]["options"] == "Attendance Verification Employee" and fields["employees"].get("read_only")
      and fields["issues"]["options"] == "Attendance Verification Issue" and fields["issues"].get("read_only"),
      "both tables are filled by the sheet, not typed")
for name in ("total_" + field for field in R.FIGURES):
    check(name in fields and fields[name].get("read_only"), "the sheet totals %s" % name)
for name in ("people", "issues_count", "read_on", *A.ALL_STAMP_FIELDS, "reopened_by", "reopened_on", "return_remarks",
             "workflow_state", "amended_from", "pay_period"):
    check(name in fields, "the sheet has %s" % name)
for name in ("status", "people", "issues_count", "read_on", "employees", "issues", *A.ALL_STAMP_FIELDS, "reopened_by",
             "reopened_on", "return_remarks"):
    check(fields[name].get("no_copy"), "an amended sheet starts without %s" % name)
row_fields = fields_of(doctype("Attendance Verification Employee"))
check(set(row_fields) == {"employee", "employee_name", "department", *R.FIGURES}, "a line holds the figures", row_fields)
check(row_fields["employee"].get("search_index"), "the lock finds a person's lines by an index")
check(sum(f.get("columns", 0) for f in row_fields.values() if f.get("in_list_view")) <= 10, "the line fits the grid")
issue_fields = fields_of(doctype("Attendance Verification Issue"))
sample = R.issue_row({"employee": "E", "employee_name": "N"}, "2026-10-01", "2026-10-02", R.NOT_MARKED, "Leave Application",
                     "HR-LAP-1")
check(set(sample) == set(issue_fields), "a line to put right is what the table holds", (set(sample), set(issue_fields)))
check(sum(f.get("columns", 0) for f in issue_fields.values() if f.get("in_list_view")) <= 10, "and fits the grid")
print("the doctypes: the sheet, its lines, what to put right")

# ── 9. The glue, the hooks, the forms ─────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "attendance_verification.py")
hooks = read("hrms_addon", "hooks.py")
controller = read("hrms_addon", "hrms_addon", "doctype", "attendance_verification", "attendance_verification.py")
for event in ("validate", "before_submit", "on_submit", "before_cancel", "on_cancel"):
    name = {"validate": "sheet_validate"}.get(event, "sheet_" + event)
    check("    def %s(self):\n        attendance_verification.%s(self)" % (event, name) in controller,
          "the sheet's %s runs the glue" % event)
    check("\ndef %s(doc" % name in glue, "the glue has %s" % name)
for doctype_name, events in (
        ("Attendance", {"before_validate": "refuse_attendance", "before_cancel": "refuse_attendance",
                        "before_update_after_submit": "refuse_attendance", "on_trash": "refuse_attendance"}),
        ("Leave Application", {"before_submit": "refuse_leave", "before_cancel": "refuse_leave"}),
        ("Attendance Request", {"before_submit": "refuse_attendance_request",
                                "before_cancel": "refuse_attendance_request"}),
        ("Off Duty Request", {"before_submit": "refuse_off_duty", "before_cancel": "refuse_off_duty"}),
        ("Late Arrival Notice", {"before_submit": "refuse_late_notice"}),
        ("Salary Slip", {"before_submit": "slip_before_submit"})):
    block = re.search(r'\n    "%s": \{\n(.*?)\n    \},' % re.escape(doctype_name), hooks, re.S)
    check(block, "hooks.py has a %s block" % doctype_name)
    for event, function in events.items():
        check(block and '"%s": "hrms_addon.hrms_addon.attendance_verification.%s"' % (event, function) in block.group(1),
              "%s %s runs %s" % (doctype_name, event, function))
        check("\ndef %s(doc, method=None):" % function in glue, "the glue has %s" % function)
check(len(re.findall(r'\n    "Attendance": \{', hooks)) == 1, "one Attendance block in doc_events")
check('"hrms_addon.hrms_addon.attendance_verification.PayrollEntryVerified"]' in hooks
      and "class PayrollEntryVerified:" in glue, "the payroll waits for the branches (extend_doctype_class)")
check('"hrms_addon.hrms_addon.attendance_verification.ShiftTypeVerified"]' in hooks and "class ShiftTypeVerified:" in glue,
      "auto attendance leaves verified days alone (extend_doctype_class)")
check('"hrms_addon.hrms_addon.attendance_verification.setup_workflows_on_migrate",' in hooks
      and 'workflows.setup_on_migrate(approval, "Attendance Verification workflow")' in glue, "the workflow is built on migrate")
check('"Payroll Settings-custom_branches_verify_attendance",' in hooks, "the setting ships as a fixture")
setting = [row for row in json.load(io.open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
           if row["name"] == "Payroll Settings-custom_branches_verify_attendance"]
check(setting and setting[0]["fieldname"] == R.SETTING and setting[0]["fieldtype"] == "Check"
      and setting[0]["default"] == "1", "Payroll Settings: on unless unticked", setting)
mixin = glue[glue.index("class PayrollEntryVerified:"):glue.index("\ndef slip_before_submit")]
for method, whitelisted in (("before_submit", False), ("create_salary_slips", True), ("submit_salary_slips", True)):
    found = re.search(r"((?:    @frappe\.whitelist\(methods=\[\"POST\"\]\)\n)?)    def %s\(self\):\n(.*?)return super\(\)\.%s\(\)"
                      % (method, method), mixin, re.S)
    check(found and "refuse_payroll(self)" in found.group(2), "the payroll's %s waits for the branches" % method)
    check(found and bool(found.group(1)) == whitelisted, "%s stays callable from the form as Frappe HR's is" % method)
people_fn = glue[glue.index("\ndef _people(doc):"):glue.index("\ndef _holidays(")]
check('row["salary_structure"] = row.name in assigned' in people_fn
      and "_assigned([row.name for row in found], doc.company, doc.to_date)" in people_fn
      and '"docstatus": 1, "company": company, "employee": ["in", employees], "from_date": ["<=", last]}' in people_fn,
      "the sheet's people are those with a submitted salary structure of its company from its last day or before")
check("frappe.flags.get(\"via_payroll_entry\")" in glue, "a slip its payroll submits is not checked twice")
for method in ("weekly_dates", "payroll_branches"):
    check(re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % method, glue), "the form calls %s" % method)
js = read("hrms_addon", "hrms_addon", "doctype", "attendance_verification", "attendance_verification.js")
check("\t\tha_verify_pages(frm);\n\t\tha_verify_hours_column(frm);" in js
      and "\tpay_kind(frm) {\n\t\tha_verify_header(frm);\n\t\tha_verify_hours_column(frm);" in js
      and 'const hide = frm.doc.pay_kind === "Weekly" ? 0 : 1;' in js
      and 'grid.set_column_disp_in_list_view("hours_worked", !hide);' in js
      and "if (!grid || !grid.set_column_disp_in_list_view) return;" in js,
      "the Hours Worked column shows on a weekly sheet only, as it opens and as Payroll changes; a Frappe without the "
      "grid's own switch shows it always")
row_spec = fields_of(doctype("Attendance Verification Employee"))
sheet_spec = doctype("Attendance Verification")
hours_field = row_spec.get("hours_worked") or {}
total_field = fields_of(sheet_spec).get("total_hours_worked") or {}
check(hours_field.get("fieldtype") == "Float" and hours_field.get("in_list_view") == 1 and hours_field.get("read_only")
      and doctype("Attendance Verification Employee")["field_order"].index("hours_worked")
      == doctype("Attendance Verification Employee")["field_order"].index("worked") + 1,
      "each person's Hours Worked, beside the days worked", hours_field)
check(total_field.get("fieldtype") == "Float" and total_field.get("read_only")
      and total_field.get("depends_on") == "eval:doc.pay_kind=='Weekly'"
      and sheet_spec["field_order"].index("total_hours_worked") == sheet_spec["field_order"].index("total_worked") + 1,
      "the sheet's Hours Worked, among its figures, on a weekly sheet", total_field)
read_fn = glue[glue.index("\ndef _read(doc):"):glue.index("\ndef _full_day(")]
check('weekly = doc.get("pay_kind") == rules.WEEKLY' in read_fn and "standard = _full_day() if weekly else None" in read_fn
      and 'hours = {day: row.get("working_hours") for day, row in (marked.get(line["employee"]) or {}).items()} \\\n'
          "            if weekly and rules.by_the_hour(person) else None" in read_fn
      and "days, hours, standard)" in read_fn
      and 'return flt(output_pay.settings().get("standard_hours")) or output_rules.STANDARD_HOURS' in glue,
      "the hours are a weekly sheet's, from each day's Working Hours, a full day as the weekly payroll takes it; a Per "
      "Piece casual's are nought")
check("casual_hours.for_verification([employee for employee in employees if rules.by_the_hour(found[employee])],"
      in read_fn and "start, end)" in read_fn
      and 'sorted(given.get("counted") or ()))' in read_fn
      and "figures = rules.with_hours_sheet(figures, inside, given, counted)" in read_fn
      and 'line["clock"], open_days)' in read_fn
      and "rules.hours_sheet_issue(name, sheet, start, end)" in read_fn
      and "if day not in covered), open_days, hours, standard)" in read_fn,
      "a weekly sheet takes the Casual Hours Sheets for its casuals paid by the hour: their figures, the days worked "
      "per sheet, no day of theirs 'not marked', no overtime the attendance carries on them, and a line for a sheet "
      "not yet approved")
check("\tfrom_date(frm) {\n\t\tha_verify_week_end(frm);\n\t}," in js
      and 'if (frm.doc.docstatus !== 0 || frm.doc.pay_kind !== "Weekly" || !frm.doc.from_date) return;' in js
      and "const to = frappe.datetime.add_days(frm.doc.from_date, 6);" in js
      and "frm.set_value({ from_date: dates.from_date, to_date: dates.to_date });" in js,
      "a weekly draft's To follows the From picked, the seventh day from it; the days handed to a new weekly sheet are "
      "written From first, so the To handed over stands (smoke_verification_week_form.py)")
check('"hrms_addon.hrms_addon.attendance_verification.weekly_dates"' in js
      and '"hrms_addon.hrms_addon.payroll_months.open_months"' in js, "the sheet's form asks the glue and the months")
check('frm.add_custom_button(__("Get Attendance"), () => frm.save())' in js
      and "!frappe.workflow.is_read_only(frm.doctype, frm.docname)" in js,
      "Get Attendance reads the figures again, for whoever may save the sheet now")
check('const HA_VERIFY_TABLES = ["employees", "issues"];' in js and "		ha_verify_pages(frm);\n" in js
      and '.on("change.ha_verify_pages", show)' in js and "\t\t\t\tha_verify_one_page(pages);\n" in js,
      "both tables show their page buttons whenever they have rows, 1 of 1 on one page"
      " (smoke_verification_pages.py)")
payroll_js = read("hrms_addon", "public", "js", "payroll_entry.js")
check('"hrms_addon.hrms_addon.attendance_verification.payroll_branches"' in payroll_js
      and "ha_payroll_attendance(frm);" in payroll_js and '"custom ha-attendance-verification"' in payroll_js,
      "the payroll form shows each branch")
print("the glue, the hooks and the forms are wired")

# ── 9b. Mark Attendance: the days nobody marked, from the sheet ──────
# Luuka, 8 Nov 2026: "add button to mark attendance and it only filter by those number of employee and those dates"
SEP = datetime.date(2026, 9, 26)
issues = [
    {"employee": "E1", "employee_name": "Amina", "from_date": SEP, "to_date": SEP + datetime.timedelta(days=1),
     "issue": R.NOT_MARKED},
    {"employee": "E1", "employee_name": "Amina", "from_date": SEP + datetime.timedelta(days=3),
     "to_date": SEP + datetime.timedelta(days=3), "issue": R.CLOCKED},
    {"employee": "E2", "employee_name": "Brian", "from_date": SEP, "to_date": SEP, "issue": R.NOT_MARKED},
    {"employee": "E2", "employee_name": "Brian", "from_date": SEP, "to_date": SEP + datetime.timedelta(days=4),
     "issue": R.LEAVE_WAITING, "reference_name": "HR-LAP-1"},
]
to_mark = R.days_to_mark(issues)
check(sorted(to_mark) == ["E1", "E2"] and to_mark["E1"]["days"] == [SEP, SEP + datetime.timedelta(days=1),
                                                                    SEP + datetime.timedelta(days=3)]
      and to_mark["E1"]["clocked"] == [SEP + datetime.timedelta(days=3)] and to_mark["E2"]["days"] == [SEP],
      "the days to mark: each person's days nobody marked, those the clock saw among them; a request waiting is not "
      "a day to mark", to_mark)
check(R.chosen_days(to_mark, ["E1", "E2"], [SEP]) == [("E1", SEP), ("E2", SEP)],
      "the people and the days picked, where the sheet has nothing marked", R.chosen_days(to_mark, ["E1", "E2"], [SEP]))
check(R.chosen_days(to_mark, ["E1", "E9"], [SEP, SEP + datetime.timedelta(days=2), "2026-09-29"])
      == [("E1", SEP), ("E1", SEP + datetime.timedelta(days=3))],
      "nobody off the sheet and no day it does not list, whatever is sent, a day as text or a date")
check(R.chosen_days(to_mark, [], [SEP]) == [] and R.chosen_days(to_mark, ["E1"], []) == [], "nothing picked, nothing marked")
check(R.mark_errors("Present", None) == [] and R.mark_errors("Absent", "Casual Leave") == []
      and R.mark_errors("Half Day", None) == [], "Present, Absent, a Half Day with or without its leave")
check(R.mark_errors("On Leave", None) == ["Pick the leave type."] and R.mark_errors("On Leave", "Casual Leave") == [],
      "leave needs its leave type")
check(R.mark_errors("On Leave", "Nope", False) == ["There is no leave type Nope."], "and one the site has")
check(R.mark_errors("Holiday", None) and R.MARK_STATUSES == ("Present", "Absent", "Half Day", "On Leave",
                                                            "Work From Home"),
      "only what Attendance takes", R.MARK_STATUSES)
check(R.mark_summary(1, []) == ["1 day marked."] and R.mark_summary(44, []) == ["44 days marked."],
      "what marking did, in a line")
said = R.mark_summary(3, [R.mark_problem("Amina", SEP, "Attendance for Amina is already marked")] * 22)
check(said[:3] == ["3 days marked.", "22 not marked:", "Amina, 26 Sep 2026: Attendance for Amina is already marked"]
      and said[-1] == "and 2 more." and len(said) == 2 + R.MARK_PROBLEMS_SHOWN + 1,
      "and the days not marked, why, the first twenty", said[-3:])
mark = glue[glue.index("\ndef _with_hr("):glue.index("\n# ── 3. A verified day does not change")]
for needle, why in (
    ('doc.check_permission("write")', "marking needs the sheet writable"),
    ("if doc.docstatus != 0 or (doc.get(approval.STATE_FIELD) or approval.DRAFT) != approval.DRAFT:",
     "and with HR: not while the General Manager has it, nor once verified"),
    ('frappe.has_permission(ATTENDANCE, "create") and frappe.has_permission(ATTENDANCE, "submit")',
     "by somebody who may mark attendance"),
    ('found = sorted(rules.days_to_mark(_read(doc)["issues"]).values(),', "the days offered are the sheet's own, read now"),
    ('picked = rules.chosen_days(rules.days_to_mark(_read(doc)["issues"]), frappe.parse_json(employees) or [],',
     "the days marked are read again too, and only those picked are marked"),
    ("if len(picked) <= MARK_AT_ONCE:\n        return _mark(doc.name, status, leave_type, picked)",
     "a few at once"),
    ('job_id="hrms_addon_verification_mark::%s" % doc.name,\n                         deduplicate=True,',
     "more in the background, one job per sheet"),
    ("why = _(\"No such employee.\") if not person else attendance_upload._mark_day(",
     "each day marked as Upload Attendance marks one, a failure taking nothing else with it"),
    ("if read_again:\n        try:\n            doc.save()", "the sheet reads its figures again once they are marked"),
):
    check(needle in mark, "mark: %s" % why)
check(re.search(r"@frappe\.whitelist\(\)\ndef days_to_mark\(name\):", glue)
      and re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef mark_days\(name, status, employees=None, days=None, '
                    r'leave_type=None\):', glue), "the form calls days_to_mark, and mark_days by POST")
check('MARK_JOB = "hrms_addon.hrms_addon.attendance_verification.mark_job"' in glue and "\ndef mark_job(" in glue,
      "the background job is the glue's own")
button = js[js.index("function ha_verify_mark_button(frm) {"):js.index("function ha_verify_mark(frm) {")]
check("\t\tha_verify_mark_button(frm);" in js.split("refresh(frm) {")[1].split("\n\t},")[0],
      "the sheet's refresh draws Mark Attendance")
check('const with_hr = doc.docstatus === 0 && (doc.workflow_state || "Draft") === "Draft";' in button
      and "if (frm.is_new() || !with_hr || !cint(doc.total_not_marked)) return;" in button
      and "if (frappe.workflow.is_read_only(frm.doctype, frm.docname)) return;" in button,
      "the button shows on a saved sheet with HR that has days nobody marked")
check('HA_VERIFY_MARK + "days_to_mark"' in js and 'HA_VERIFY_MARK + "mark_days"' in js
      and 'const HA_VERIFY_MARK = "hrms_addon.hrms_addon.attendance_verification.";' in js,
      "the dialog asks the glue for the days, and marks them through it")
check("if (values.leave_type && HA_VERIFY_LEAVE.includes(values.status)) args.leave_type = values.leave_type;" in js,
      "an empty leave type is left out, as Frappe refuses an empty string")
check("label: `${frappe.utils.escape_html(person.employee_name)} (${person.days.length})`," in js,
      "a name in the dialog's list is escaped: Frappe's MultiCheck writes a label in as HTML")
print("Mark Attendance: the sheet's own people and days nobody marked, nothing else")

# ── 10. What else writes attendance ───────────────────────────────────
overtime = read("hrms_addon", "hrms_addon", "overtime.py")
send = overtime[overtime.index("\ndef send("):overtime.index("\ndef take_back(")]
check(send.index("attendance_verification.verified_messages(") < send.index('frappe.db.set_value("Attendance"')
      and "    if locked:\n        return stopped(locked)\n" in send, "overtime is stopped before it writes a verified day")
take = overtime[overtime.index("\ndef take_back("):overtime.index("\ndef waiting(")]
check(take.index("attendance_verification.verified_messages(") < take.index('frappe.db.set_value("Attendance"')
      and '    if locked:\n        frappe.throw("<br>".join(locked), title=_("Overtime Request"))\n' in take,
      "and not taken off one either")
attendance = read("hrms_addon", "hrms_addon", "attendance.py")
auto = attendance[attendance.index("\ndef _mark_automatic("):attendance.index("\ndef _chase_open_passes(")]
check(auto.index("if attendance_verification.verified(employee.name, day):\n            continue\n")
      < auto.index("attendance.insert()"), "automatic attendance skips a verified day")
deletions = read("hrms_addon", "hrms_addon", "attendance_deletions.py")
check("used.setdefault(record.name, VERIFICATION)" in deletions and deletions.count("_reasons(records, on_slips, links, day)") == 2,
      "a deletion keeps a verified day, counted and when it deletes")
recreate = read("hrms_addon", "hrms_addon", "payroll_entries.py")
check(recreate.index("attendance_verification.refuse_payroll(run)") < recreate.index("frappe.enqueue(REMAKE"),
      "Recreate Salary Slips waits for the branches too")
navigation = read("hrms_addon", "hrms_addon", "navigation_rules.py")
check(navigation.count('"Attendance Verification"') >= 3, "the sheet is on the menus")
print("overtime, automatic attendance, deletions and Recreate Salary Slips respect a verified day")

# ── 11. What Frappe HR does that this stands on ───────────────────────
hrms = os.path.join(APPS_ROOT, "hrms", "hrms")
if os.path.isdir(hrms):
    def upstream(*parts):
        return io.open(os.path.join(hrms, *parts), encoding="utf-8").read().replace("\r\n", "\n")

    entry_py = upstream("payroll", "doctype", "payroll_entry", "payroll_entry.py")
    picks = entry_py[entry_py.index("def get_filtered_employees("):entry_py.index("def set_filter_conditions(")]
    check("(SalaryStructureAssignment.docstatus == 1)" in picks
          and "(filters.end_date >= SalaryStructureAssignment.from_date)" in picks,
          "Frappe HR's payroll pays those with a submitted salary structure from its end date or before, "
          "as the sheet lists them")
    leave = upstream("hr", "doctype", "leave_application", "leave_application.py")
    update = leave[leave.index("\tdef create_or_update_attendance("):leave.index("\tdef cancel_attendance(")]
    check(re.search(r'doc\.db_set\(\s*\{\s*"status": status', update)
          and 'frappe.db.set_value("Attendance", name, "docstatus", 2)' in leave,
          "Frappe HR rewrites a leave's attendance without saving it: the leave itself is refused")
    request = upstream("hr", "doctype", "attendance_request", "attendance_request.py")
    check("doc.db_set(" in request, "and so does an attendance request")
    marking = upstream("hr", "doctype", "attendance", "attendance.py")
    mark = marking[marking.index("\ndef mark_attendance("):]
    mark = mark[:mark.index("\ndef ", 1)]
    check("except (DuplicateAttendanceError, OverlappingShiftAttendanceError):" in mark,
          "auto attendance's absence marking catches only duplicates: a refusal would stop the run, hence the filter")
    checkin = upstream("hr", "doctype", "employee_checkin", "employee_checkin.py")
    link = checkin[checkin.index("\ndef mark_attendance_and_link_log("):]
    check("except frappe.ValidationError as e:" in link,
          "while a punch's refusal is caught and the punch set aside with the reason")
    shift = upstream("hr", "doctype", "shift_type", "shift_type.py")
    check("def get_dates_for_attendance(self, employee" in shift and "self.get_dates_for_attendance(employee)" in shift,
          "absences are marked on the days get_dates_for_attendance gives")
    entry = upstream("payroll", "doctype", "payroll_entry", "payroll_entry.py")
    check("frappe.flags.via_payroll_entry = True" in entry and "except frappe.ValidationError:\n\t\t\t\t\tunsubmitted.append"
          in entry, "a payroll's run sets via_payroll_entry and passes over a slip that refuses: checked up front instead")
    check("\tdef before_submit(self):" in entry and "\tdef on_submit(self):\n\t\tself.set_status(update=True, status=\"Submitted\")"
          "\n\t\tself.create_salary_slips()" in entry, "submitting a payroll makes its slips")
    print("Frappe HR, read from its own source: what the lock and the payroll's wait stand on")
else:
    print("Frappe HR's source not found at %s: its part is not checked" % hrms)

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL ATTENDANCE VERIFICATION CHECKS PASSED")
