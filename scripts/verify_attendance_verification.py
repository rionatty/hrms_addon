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
staff = {"status": "Active", "date_of_joining": "2020-01-01", "relieving_date": None, "custom_pay_category": "Regular"}
casual = dict(staff, custom_pay_category="Weekly")
check(R.on_sheet(staff, "Monthly", "2026-09-26", "2026-10-25"), "a monthly person is on the monthly sheet")
check(R.on_sheet(dict(staff, custom_pay_category=None), "Monthly", "2026-09-26", "2026-10-25"),
      "and so is one with no pay category")
check(R.on_sheet(dict(staff, custom_pay_category="Per Meter"), "Monthly", "2026-09-26", "2026-10-25"),
      "and one paid per meter, who is paid monthly")
check(not R.on_sheet(casual, "Monthly", "2026-09-26", "2026-10-25"), "a casual paid weekly is not on the monthly one")
check(R.on_sheet(casual, "Weekly", "2026-10-30", "2026-11-05"), "but on the weekly one")
check(not R.on_sheet(staff, "Weekly", "2026-10-30", "2026-11-05"), "where a monthly person is not")
for status in ("Inactive", "Suspended", "Left", "", None):
    check(not R.on_sheet(dict(staff, status=status), "Monthly", "2026-09-26", "2026-10-25"),
          "only the active are on it, not one whose status is %r" % status)
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
print("who is on it: the branch's active people on the books for any of its days, paid the way the sheet pays")

# ── 3. A person's line ────────────────────────────────────────────────
week = days("2026-10-19", "2026-10-25")  # Mon..Sun
codes = {D(2026, 10, 19): "M", D(2026, 10, 20): "N", D(2026, 10, 21): "A", D(2026, 10, 22): "L",
         D(2026, 10, 23): "S", D(2026, 10, 25): "WO"}
line = R.person_figures(staff, codes, [], {D(2026, 10, 19): "Half Day"}, 3.456, week)
check(line == {"worked": 2, "half_day": 1, "absent": 1, "leave": 2, "off": 1, "not_marked": 1, "overtime_hours": 3.46},
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
check("frappe.flags.get(\"via_payroll_entry\")" in glue, "a slip its payroll submits is not checked twice")
for method in ("weekly_dates", "payroll_branches"):
    check(re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % method, glue), "the form calls %s" % method)
js = read("hrms_addon", "hrms_addon", "doctype", "attendance_verification", "attendance_verification.js")
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
