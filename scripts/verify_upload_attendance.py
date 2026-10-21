"""Checks Upload Attendance without a bench:

    python scripts/verify_upload_attendance.py

Frappe HR v16 deleted its own Upload Attendance (Luuka, 21 Oct 2026: "i
cant find doct type upload attendace"). This app has one again, under the
same name. Its template was a row per employee per day, which made a whole
company over a cycle 103,182 rows and was refused; Luuka: "the system should
be able to accomodate any number of uploads of data". The template is now
the register, LPL/HR/07: a row per employee, a column per day, each day a
letter of the register; and the marking reads the file as it goes, a part at
a time, so a file of any size is never held whole.

  1. the register: who is on it, which days are open to mark, the days
     marked already in their letters, the holidays, and the file as Excel
     opens it; a whole company of 3,300 over a cycle, one row each
  2. the file back: the register, or a row per day (a Data Import file, or
     the days not marked), found by the heading, read as it goes
  3. the days: each letter, status or leave type's name, the leave and the
     shift each comes to on the site, each problem said against its row
  4. the days not marked: a file to put right and import again, as it is
  5. the doctype, the background job and the form, wired as they must be
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import re
import sys
import time

import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(label, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("attendance_upload_rules")
A = load("attendance_rules")
print("loaded attendance_upload_rules.py and attendance_rules.py without Frappe")
D = datetime.date


def raised(run):
    try:
        run()
    except ValueError as error:
        return str(error)
    return None


# ── 1. The register ───────────────────────────────────────────────────
START, END, TODAY = D(2026, 9, 26), D(2026, 10, 25), D(2026, 10, 21)
DAYS = R.period_days(START, END)
check("the period is every day of it, in order: 26 September to 25 October is 30 days",
      len(DAYS) == 30 and DAYS[0] == START and DAYS[-1] == END, len(DAYS))
PEOPLE = [
    {"employee": "LPL001", "employee_name": "Alice Akello", "department": "PE Department - LPT",
     "date_of_joining": D(2020, 1, 6), "relieving_date": None, "holiday_list": "Luuka 2026"},
    {"employee": "LPL002", "employee_name": "Bob Okot", "department": "PE Department - LPT",
     "date_of_joining": "2026-10-10", "relieving_date": None, "holiday_list": "Luuka 2026"},
    {"employee": "LPL003", "employee_name": "Carol Nabirye", "department": "PP Department - LPT",
     "date_of_joining": D(2019, 5, 1), "relieving_date": D(2026, 9, 30), "holiday_list": None},
]
MARKED = {("LPL001", D(2026, 9, 30)): "M", ("LPL001", D(2026, 10, 1)): "A"}
HOLIDAYS = {"Luuka 2026": {D(2026, 10, 9), D(2026, 10, 4)}}
rows = R.register_rows(PEOPLE, DAYS, TODAY, MARKED, HOLIDAYS)
cells = {(row[0], day): cell for row in rows for day, cell in zip(DAYS, row[3])}
check("one row per employee, in the order given, each a cell per day",
      [row[0] for row in rows] == ["LPL001", "LPL002", "LPL003"] and all(len(row[3]) == len(DAYS) for row in rows))
check("a day marked already shows its letter, in grey", cells[("LPL001", D(2026, 9, 30))] == ("M", "marked")
      and cells[("LPL001", D(2026, 10, 1))] == ("A", "marked"))
check("a holiday on the employee's list shows WO", cells[("LPL001", D(2026, 10, 9))] == (R.WEEKLY_OFF, "holiday")
      and cells[("LPL001", D(2026, 10, 4))] == (R.WEEKLY_OFF, "holiday"))
check("a day to fill is blank", cells[("LPL001", D(2026, 10, 2))] == (None, None))
check("a day after today cannot be marked: -", cells[("LPL001", D(2026, 10, 22))] == (R.CLOSED, "closed")
      and cells[("LPL001", D(2026, 10, 25))] == (R.CLOSED, "closed"))
check("nor a day before joining", cells[("LPL002", D(2026, 10, 9))] == (R.CLOSED, "closed")
      and cells[("LPL002", D(2026, 10, 10))] == (None, None))
check("nor a day after leaving", cells[("LPL003", D(2026, 9, 30))] == (None, None)
      and cells[("LPL003", D(2026, 10, 1))] == (R.CLOSED, "closed"))
LEAVES = ["Annual", "Leave Without Pay", "Off Duty", "Sick Leave"]
content = R.build_template(rows, DAYS, LEAVES)
book = openpyxl.load_workbook(io.BytesIO(content))
check("the file has the register and how to fill it", book.sheetnames == [R.SHEET, R.HOW], book.sheetnames)
sheet = book[R.SHEET]
head = [cell.value for cell in sheet[1]]
check("its heading: Employee, Employee Name, Department, then each day as a date",
      head[:3] == ["Employee", "Employee Name", "Department"] and len(head) == 3 + len(DAYS)
      and all(isinstance(value, datetime.datetime) for value in head[3:]) and head[3].date() == START,
      head[:5])
check("the days are headed short, 26-Sep", sheet["D1"].number_format == "dd-mmm", sheet["D1"].number_format)
check("a row per employee under it", sheet.max_row == len(rows) + 1, sheet.max_row)
check("the employee number is kept as text", sheet["A2"].number_format == "@")
check("the letters land in their days", sheet.cell(2, 3 + DAYS.index(D(2026, 9, 30)) + 1).value == "M"
      and sheet.cell(2, 3 + DAYS.index(D(2026, 10, 9)) + 1).value == "WO"
      and sheet.cell(3, 4).value == "-")
rule = sheet.data_validations.dataValidation[0]
check("each day picks from the register's letters, and a leave type's name may be typed over them",
      rule.formula1 == '"M,N,A,L,S,O,P,HD,WFH,WO"' and not rule.showErrorMessage
      and str(rule.sqref) == "D2:%s4" % openpyxl.utils.get_column_letter(3 + len(DAYS)),
      (rule.formula1, rule.showErrorMessage, str(rule.sqref)))
check("the names and the heading stay in view", sheet.freeze_panes == "D2")
how = [row[1] for row in book[R.HOW].iter_rows(values_only=True) if len(row) > 1]
check("how to fill it says each letter, a blank day and the leave types a day may name",
      any("blank is not marked" in str(line) for line in how) and "Present, night shift" in how
      and "Sick Leave" in how, how[:4])
check("the register's letters are LPL/HR/07's own (attendance_rules)",
      {A.DAY_SHIFT, A.NIGHT_SHIFT, A.ABSENT, A.SICK, A.LEAVE, A.OFF_DUTY} <= set(R.CODES)
      and R.WEEKLY_OFF == A.WEEKLY_OFF and R.CODES["M"][2] == R.DAY and R.CODES["N"][2] == R.NIGHT)
company = [{"employee": "LPL%05d" % n, "employee_name": "Person %d" % n, "department": "PE Department - LPT",
            "date_of_joining": D(2020, 1, 1), "relieving_date": None, "holiday_list": None} for n in range(3300)]
began = time.time()
big = R.build_template(R.register_rows(company, R.period_days(D(2026, 8, 26), D(2026, 9, 25)), D(2026, 9, 25), {}),
                       R.period_days(D(2026, 8, 26), D(2026, 9, 25)))
took = time.time() - began
big_rows = list(openpyxl.load_workbook(io.BytesIO(big), read_only=True)[R.SHEET].iter_rows(values_only=True))
check("a whole company of 3,300 over a cycle is 3,300 rows, not 103,182, built in %.1f seconds" % took,
      len(big_rows) == 3301 and len(big_rows[0]) == 34, (len(big_rows), len(big_rows[0])))

# ── 2. The file back ──────────────────────────────────────────────────
check("the register is known by its heading", R.layout_of(content, "x.xlsx") == R.REGISTER)
untouched = list(R.days_in(content, "x.xlsx"))
check("left as it came, only the days marked already are read back: no blank, - or WO day",
      [(r["employee"], r["attendance_date"], r["status"]) for r in untouched] ==
      [("LPL001", D(2026, 9, 30), "M"), ("LPL001", D(2026, 10, 1), "A")], untouched)
filled = openpyxl.load_workbook(io.BytesIO(content))
ws = filled[R.SHEET]


def put(row, day, text):
    ws.cell(row, 3 + DAYS.index(day) + 1, text)


put(2, D(2026, 10, 2), "M")
put(2, D(2026, 10, 3), " a ")
put(3, D(2026, 10, 12), "Sick Leave")
put(4, D(2026, 9, 29), "N")
out = io.BytesIO()
filled.save(out)
back = list(R.days_in(out.getvalue(), "filled.xlsx"))
check("a filled day is read against its row and day, trimmed",
      ("LPL001", D(2026, 10, 3), "a", 2) in [(r["employee"], r["attendance_date"], r["status"], r["row"]) for r in back]
      and ("LPL002", D(2026, 10, 12), "Sick Leave", 3) in [(r["employee"], r["attendance_date"], r["status"], r["row"])
                                                          for r in back], back)
check("each with the day it is under, for the problems to name it", all(r["day"] == r["attendance_date"] for r in back))
check("a generator: the file is read as it goes, never held whole", hasattr(R.days_in(content, "x.xlsx"), "__next__"))
typed = ("Employee,Employee Name,26/09/2026,27/09/2026\nLPL001,Alice,M,\nLPL002,Bob,,A\n").encode()
check("a register with its days typed as text reads too",
      [(r["employee"], r["attendance_date"], r["status"]) for r in R.days_in(typed, "typed.csv")] ==
      [("LPL001", D(2026, 9, 26), "M"), ("LPL002", D(2026, 9, 27), "A")])
csv_file = ("﻿Title line\nID,Employee (employee),Attendance Date (attendance_date),Status (status),"
            "Leave Type (leave_type),Shift (shift)\n,LPL001,2026-10-05,Present,,\n,LPL002,,Absent,,\n"
            ",LPL003,2026-10-06,,,\n\n").encode("utf-8")
taken = list(R.days_in(csv_file, "import.CSV"))
check("a row per day reads too, a Data Import file under a title line: a row with no Status is no day",
      R.layout_of(csv_file, "import.CSV") == R.ROWS and
      [(r["row"], r["employee"], r["attendance_date"], r["status"]) for r in taken] ==
      [(3, "LPL001", "2026-10-05", "Present"), (4, "LPL002", "", "Absent")], taken)
check("a heading is compared without case, (fieldname) or underscores",
      R.heading("Attendance Date (attendance_date)") == R.heading("attendance_date") == "attendance date"
      and R.heading("  STATUS ") == "status")
check("Employee Name is not taken for the Employee", R.header_columns(["Employee Name", "Date", "Status"]) is None
      and R.register_columns(["Employee Name", datetime.datetime(2026, 9, 26)]) is None)
check("no column of numbers is taken for a day", R.register_columns(["Employee", 1, 2, 3]) is None)
check("a file with no Employee column and no days is refused, saying so",
      raised(lambda: R.layout_of(b"Name,When\nAlice,2026-10-05\n", "x.csv")) == R.NO_HEADER
      and raised(lambda: list(R.days_in(b"Name,When\nAlice,2026-10-05\n", "x.csv"))) == R.NO_HEADER)
check("a file that is not a workbook is refused, saying what to save it as",
      raised(lambda: R.layout_of(b"\xd0\xcf\x11\xe0 an old .xls", "x.xls")) == R.NOT_A_SHEET)
check("the heading is looked for near the top only",
      raised(lambda: R.layout_of(("\n" * 12 + "Employee,Attendance Date,Status\nLPL001,2026-10-05,M\n").encode(),
                                 "x.csv")) == R.NO_HEADER)
for given, wanted in (("2026-10-05", D(2026, 10, 5)), ("05/10/2026", D(2026, 10, 5)), ("05-10-2026", D(2026, 10, 5)),
                      ("5.10.2026", D(2026, 10, 5)), ("2026-10-05 00:00:00", D(2026, 10, 5)),
                      (datetime.datetime(2026, 10, 5, 0, 0), D(2026, 10, 5)), (D(2026, 10, 5), D(2026, 10, 5)),
                      (46300, D(2026, 10, 5)), ("31/02/2026", None), ("soon", None), ("", None), (None, None),
                      (12, None), (True, None)):
    check("the date %r reads as %s" % (given, wanted), R.parse_date(given) == wanted, R.parse_date(given))

# ── 3. The days ───────────────────────────────────────────────────────
for said, wanted in (("M", ("Present", None, R.DAY)), ("n", ("Present", None, R.NIGHT)), ("A", ("Absent", None, None)),
                     ("L", ("On Leave", R.ANNUAL, None)), ("S", ("On Leave", R.SICK, None)),
                     ("O", ("On Leave", R.OFF_DUTY, None)), ("hd", ("Half Day", None, None)),
                     ("WFH", ("Work From Home", None, None)), ("present", ("Present", None, None)),
                     ("Leave Without Pay", ("On Leave", "Leave Without Pay", None)),
                     ("sick leave", ("On Leave", "Sick Leave", None))):
    check("a day saying %r is %s" % (said, wanted), R.meaning(said, LEAVES) == wanted, R.meaning(said, LEAVES))
check("anything else is said to be no day of the register",
      raised(lambda: R.meaning("Here", LEAVES)) ==
      "Here is not a day of the register. Use M, N, A, L, S, O, P, HD or WFH, or a leave type's name.")
NAMES = {"leave_types": LEAVES, "shifts": ["Day Shift", "Night Shift"], "annual": "Annual", "off_duty": "Off Duty"}
check("L is the site's annual leave, O its off duty, S its one sick leave",
      R.leave_for(R.ANNUAL, NAMES) == "Annual" and R.leave_for(R.OFF_DUTY, NAMES) == "Off Duty"
      and R.leave_for(R.SICK, NAMES) == "Sick Leave" and R.leave_for("Leave Without Pay", NAMES) == "Leave Without Pay")
check("S is Sick Leave where there are several sick leave types and one is called that",
      R.leave_for(R.SICK, dict(NAMES, leave_types=["Sick Leave", "Sick Leave (Half Pay)"])) == "Sick Leave")
check("and refused where none is, or several and none called Sick Leave, saying to name it",
      "Write the leave type's name in the day instead" in str(raised(lambda: R.leave_for(R.SICK, dict(
          NAMES, leave_types=["Sick (Full)", "Sick (Half)"])))) and "no sick leave type" in str(raised(
          lambda: R.leave_for(R.SICK, dict(NAMES, leave_types=["Annual"])))))
check("L and O refused where the site has no such leave type",
      raised(lambda: R.leave_for(R.ANNUAL, dict(NAMES, annual="Annual Leave"))) ==
      "L is annual leave, and there is no leave type Annual Leave."
      and raised(lambda: R.leave_for(R.OFF_DUTY, dict(NAMES, leave_types=["Annual"]))) ==
      "O is off duty, and there is no leave type Off Duty.")
SHIFTS = ["Day Shift", "Night Shift"]
check("N is the employee's own night shift, else the site's only one",
      R.shift_for(R.NIGHT, "Night Shift (Namanve)", SHIFTS) == "Night Shift (Namanve)"
      and R.shift_for(R.NIGHT, "Day Shift", SHIFTS) == "Night Shift" and R.shift_for(R.NIGHT, None, SHIFTS) == "Night Shift")
check("and refused where the site has none or several, saying to give the employee theirs",
      "Give the employee one as their Default Shift" in str(raised(lambda: R.shift_for(R.NIGHT, None, ["Day Shift"])))
      and raised(lambda: R.shift_for(R.NIGHT, None, ["Night A", "Night B"])) is not None)
check("M is the employee's own day shift, else the site's only one, else the day as it comes",
      R.shift_for(R.DAY, "Day Shift", SHIFTS) == "Day Shift" and R.shift_for(R.DAY, "Night Shift", SHIFTS) == "Day Shift"
      and R.shift_for(R.DAY, None, ["Morning", "Afternoon", "Night Shift"]) is None)
check("a day shift for somebody on nights is refused where the site has several",
      raised(lambda: R.shift_for(R.DAY, "Night Shift", ["Morning", "Afternoon", "Night Shift"])) is not None)
check("P, A and the rest name no shift", R.shift_for(None, "Night Shift", SHIFTS) is None)

EMPLOYEES = {
    "LPL001": {"date_of_joining": D(2020, 1, 6), "relieving_date": None, "status": "Active", "default_shift": "Day Shift"},
    "LPL002": {"date_of_joining": D(2026, 10, 10), "relieving_date": None, "status": "Active", "default_shift": None},
    "LPL003": {"date_of_joining": D(2019, 5, 1), "relieving_date": D(2026, 9, 30), "status": "Left"},
    "LPL004": {"date_of_joining": D(2019, 5, 1), "relieving_date": None, "status": "Inactive"},
    "LPL005": {"date_of_joining": D(2019, 5, 1), "relieving_date": None, "status": "Suspended",
               "default_shift": "Night Shift"},
}
ON_SITE = {("LPL001", D(2026, 9, 30)): ("Present", "HR-ATT-2026-00001", "M"),
           ("LPL001", D(2026, 10, 1)): ("Absent", "HR-ATT-2026-00002", "A"),
           ("LPL005", D(2026, 10, 1)): ("Half Day", "HR-ATT-2026-00003", "N")}
CASES = [
    # (employee, date, what the day says, leave column, shift column, what it comes to)
    ("LPL001", D(2026, 10, 2), "M", None, None, ("Present", None, "Day Shift")),
    ("lpl001", "2026-10-03", " a ", None, None, ("Absent", None, None)),
    ("LPL001", "05/10/2026", "L", None, None, ("On Leave", "Annual", None)),
    ("LPL001", D(2026, 10, 6), "HD", None, None, ("Half Day", None, None)),
    ("LPL001", D(2026, 10, 7), "Sick Leave", None, None, ("On Leave", "Sick Leave", None)),
    ("LPL001", D(2026, 10, 8), "N", None, None, ("Present", None, "Night Shift")),
    ("LPL001", D(2026, 10, 10), "Present", "Annual", "night shift", ("Present", None, "Night Shift")),
    ("LPL001", D(2026, 10, 11), "On Leave", "annual", None, ("On Leave", "Annual", None)),
    ("LPL005", D(2026, 10, 7), "WFH", None, None, ("Work From Home", None, None)),
    ("LPL005", D(2026, 10, 8), "N", None, None, ("Present", None, "Night Shift")),
    ("LPL003", D(2026, 9, 30), "O", None, None, ("On Leave", "Off Duty", None)),
    (None, D(2026, 10, 8), "M", None, None, "No employee on this row."),
    ("LPL999", D(2026, 10, 8), "M", None, None, "No employee LPL999."),
    ("LPL001", None, "M", None, None, "No Attendance Date."),
    ("LPL001", "31/02/2026", "M", None, None, "31/02/2026 is not a date. Write it as 2026-10-05."),
    ("LPL001", D(2026, 10, 12), "Here", None, None,
     "Here is not a day of the register. Use M, N, A, L, S, O, P, HD or WFH, or a leave type's name."),
    ("LPL001", D(2026, 10, 22), "M", None, None, "2026-10-22 is after today."),
    ("LPL002", D(2026, 10, 9), "M", None, None, "LPL002 joined on 2026-10-10."),
    ("LPL003", D(2026, 10, 1), "M", None, None, "LPL003 left on 2026-09-30."),
    ("LPL004", D(2026, 10, 8), "M", None, None,
     "LPL004 is Inactive, and attendance is not marked for an inactive employee."),
    ("LPL001", D(2026, 10, 13), "On Leave", None, None, "On Leave needs a Leave Type."),
    ("LPL001", D(2026, 10, 14), "On Leave", "Maternity", None, "No leave type Maternity."),
    ("LPL001", D(2026, 10, 15), "Present", None, "Swing", "No shift Swing."),
    ("LPL001", D(2026, 10, 2), "A", None, None, "LPL001 on 2026-10-02 is on row 2 too."),
    ("LPL001", D(2026, 9, 30), "M", None, None, "already"),
    ("LPL001", D(2026, 10, 1), "M", None, None,
     "Already marked Absent on HR-ATT-2026-00002. Cancel that one to mark the day again."),
    # a Half Day the register shows as its shift's letter, left as it was
    ("LPL005", D(2026, 10, 1), "N", None, None, "already"),
]
DAYS_IN = [{"row": number, "employee": who, "attendance_date": day, "status": said, "leave_type": leave,
            "shift": shift} for number, (who, day, said, leave, shift, _what) in enumerate(CASES, 2)]
seen = {}
result = R.check_days(DAYS_IN[:12], EMPLOYEES, NAMES, ON_SITE, TODAY, seen=seen)
rest = R.check_days(DAYS_IN[12:], EMPLOYEES, NAMES, ON_SITE, TODAY, seen=seen)
said = {record["row"]: why for record, why in result["problems"] + rest["problems"]}
marking = {row["row"]: row for row in result["to_mark"] + rest["to_mark"]}
for number, (who, day, text, leave, shift, what) in enumerate(CASES, 2):
    if isinstance(what, tuple):
        got = marking.get(number)
        check("row %d (%s, %r) is marked %s" % (number, who, text, what),
              got is not None and (got["status"], got["leave_type"], got["shift"]) == what,
              said.get(number) or got)
    elif what == "already":
        check("row %d is counted as marked already" % number, number not in said and number not in marking,
              said.get(number))
    else:
        check("row %d: %s" % (number, what), said.get(number) == what, said.get(number))
check("two marked already: the same status, and a Half Day shown as its shift's letter, left as it was",
      result["already"] + rest["already"] == 2, result["already"] + rest["already"])
check("a day twice in the file is caught though the two are read in different parts", 25 in said and 25 not in marking)
check("each day to mark keeps the record it came from", marking[2]["source"] is DAYS_IN[0]
      and marking[2]["employee"] == "LPL001" and marking[3]["employee"] == "LPL001")

# ── 4. The days not marked ────────────────────────────────────────────
problems = result["problems"] + rest["problems"]
again = R.problems_file(list(reversed(problems)))
sheet = openpyxl.load_workbook(io.BytesIO(again))[R.SHEET]
check("the days not marked come a row each, with why in a last column",
      [c.value for c in sheet[1]] == list(R.PROBLEM_HEADERS), [c.value for c in sheet[1]])
check("in the order of the file, whatever order they were found in",
      [sheet.cell(r, 6).value for r in range(2, sheet.max_row + 1)] ==
      [why for _record, why in sorted(problems, key=lambda p: p[0]["row"])])
check("a date is still a date", isinstance(sheet["B2"].value, datetime.datetime)
      and sheet["B2"].number_format == "yyyy-mm-dd")
reread = list(R.days_in(again, "days not marked.xlsx"))
check("the file goes back in as it is: a row per day, what each day said kept",
      R.layout_of(again, "x.xlsx") == R.ROWS and len(reread) == len([p for p in problems if R.text(p[0]["status"])])
      and {r["status"] for r in reread} >= {"Here", "On Leave"}, len(reread))
register_problem = ({"row": 7, "employee": "LPL001", "attendance_date": D(2026, 10, 5), "status": "X",
                     "day": D(2026, 10, 5)}, "X is not a day of the register.")
row_problem = ({"row": 9, "employee": "LPL002", "attendance_date": "2026-10-05", "status": "Here"}, "No.")
lines = R.listed([register_problem, row_problem] + problems, 3).split("\n")
check("the upload lists the first problems by row, a register's with its day, and how many more are in the file",
      lines[:2] == ["Row 7, 2026-10-05: X is not a day of the register.", "Row 9: No."] and len(lines) == 4
      and lines[-1] == "And %d more, in the file." % (len(problems) + 2 - 3), lines)
check("a register's problem names its day", "Row 7, 2026-10-05: X is not a day of the register." in
      R.listed([register_problem], 5) and R.listed([row_problem], 5) == "Row 9: No.")

# ── 5. The doctype, the job and the form ──────────────────────────────
doc = json.loads(read("hrms_addon", "hrms_addon", "doctype", "upload_attendance", "upload_attendance.json"))
fields = {f["fieldname"]: f for f in doc["fields"]}
glue = read("hrms_addon", "hrms_addon", "attendance_upload.py")
tree = ast.parse(glue)
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    consts[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    # a tuple of the names above, as RUNNING is
                    if isinstance(node.value, ast.Tuple) and all(isinstance(elt, ast.Name) for elt in node.value.elts):
                        consts[target.id] = tuple(consts.get(elt.id) for elt in node.value.elts)
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for name, value in zip(target.elts, node.value.elts):
                    consts[name.id] = ast.literal_eval(value)
check("the doctype is Upload Attendance, the name people search for", doc["name"] == "Upload Attendance"
      and consts.get("DOCTYPE") == "Upload Attendance")
check("one record per upload, numbered, kept in this app", not doc.get("issingle") and not doc.get("is_submittable")
      and doc.get("autoname", "").startswith("HR-ATU-") and doc.get("module") == "HRMS Addon")
check("its statuses are the job's", fields["status"]["options"].split("\n") == [
    consts.get(name) for name in ("DRAFT", "QUEUED", "IMPORTING", "DONE", "DONE_WITH_PROBLEMS", "FAILED")],
    fields["status"]["options"])
check("what the job writes is read-only on the form", all(fields[name].get("read_only") for name in
                                                         ("status", "imported_by", "imported_on", "days_in_file",
                                                          "marked", "already_marked", "not_marked", "problems_file",
                                                          "problems")))
check("the counts the job writes are fields", all(name in fields for name in consts.get("COUNTS", ())),
      consts.get("COUNTS"))
check("the company and the period are asked for", all(fields[name].get("reqd") for name in
                                                      ("company", "from_date", "to_date")))
check("the plant is called a plant, as on Luuka's other forms", fields["branch"]["label"] == "Plant")
check("the form says the register, and that a row per day reads too",
      "letter" in fields["attendance_file"].get("description", "") and "any number" in doc.get("description", ""))
roles = {p["role"] for p in doc["permissions"]}
check("HR only: the HR User, the HR Manager and the System Manager", roles == {"HR User", "HR Manager",
                                                                                 "System Manager"}, roles)
check("Frappe HR's Inactive is not among those put on the register", "Inactive" not in consts.get("ON_STAFF", ())
      and "Left" in consts.get("ON_STAFF", ()), consts.get("ON_STAFF"))


def body(name):
    found = re.search(r"^def %s\(.*?(?=^def |^# ──|\Z)" % name, glue, re.S | re.M)
    return found.group(0) if found else ""


for name in ("this_cycle", "download_template"):
    check("%s can be called from the form" % name,
          re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue) is not None)
template = body("download_template")
check("the register is for HR, and for those who may make an upload",
      "attendance.only_hr()" in template and 'frappe.has_permission(DOCTYPE, "create", throw=True)' in template)
check("no number of people is too many: only the period is held to a year",
      "len(days) > rules.MAX_DAYS" in template and "MAX_ROWS" not in glue and R.MAX_DAYS == 366
      and not hasattr(R, "MAX_ROWS"))
check("the days marked already go on it in their letters, in draft too",
      '"docstatus": ["<", 2]' in body("_marked") and "register.register_code(" in body("_marked")
      and "rules.register_rows(" in template)
check("a department takes in the departments under it", '"descendants of (inclusive)"' in body("_people"))
check("the register comes back in the answer, so a problem is a message and not an error page",
      "base64.b64encode(content)" in template and "frappe.response" not in template)
importing = body("start_import")
check("Import is HR's, on an upload they may change", "attendance.only_hr()" in importing
      and 'doc.check_permission("write")' in importing)
check("Import reads only the file's heading while the person waits, then queues the rest",
      importing.index("rules.layout_of(") < importing.index("frappe.enqueue(") and "rules.days_in(" not in importing)
check("an upload already being marked is not queued twice", "if running(doc):" in importing
      and 'job_id="upload_attendance::%s" % doc.name' in importing and "deduplicate=True" in importing)
check("the job starts after the upload is saved as Queued", "enqueue_after_commit=True" in importing
      and importing.index("doc.db_set(") < importing.index("frappe.enqueue("))
check("the job runs where long jobs do, given a day", 'queue="long"' in importing
      and "timeout=JOB_HOURS * 3600" in importing and consts.get("JOB_HOURS") == 24)
marking = body("_mark_file")
check("the days are counted as they are read, for the bar, and a file with none is said",
      "sum(1 for _record in rules.days_in(" in marking and "rules.NOTHING_FILLED" in marking)
check("then read again a part at a time, never held whole",
      "for part in _parts(rules.days_in(content, doc.attendance_file), PART):" in marking
      and consts.get("PART") == 2000)
check("each part checked before a day of it is written, the days met so far carried from part to part",
      marking.index("rules.check_days(") < marking.index("_mark_day(") and "seen=seen" in marking)
check("each part's employees read once, by an index, and a name the site lacks not asked twice",
      "index[name.lower()] = None" in body("_learn") and "index[row.name.lower()] = row.name" in body("_learn")
      and "_learn(people, index, part)" in marking)
check("the counts saved as it goes, which keeps the upload moving, and the bar moved by the percent",
      "doc.db_set(counts, commit=True)" in marking and "if done % BATCH == 0:" in marking
      and "frappe.publish_progress(" in marking and "if percent != shown:" in marking)
check("the days not marked go back as a file on the upload", "_problems_file(doc, problems)" in marking
      and '"attached_to_field": "problems_file"' in body("_problems_file"))
day = body("_mark_day")
check("each day is marked and submitted on its own, rolled back alone when it fails",
      "frappe.db.savepoint(SAVEPOINT)" in day and "frappe.db.rollback(save_point=SAVEPOINT)" in day
      and day.index("day.insert()") < day.index("day.submit()"))
check("and as the person who pressed Import: no permission is waived", "ignore_permissions" not in day)
check("Frappe HR's notes on each day are not kept in memory", "frappe.local.message_log = []" in day)
job = body("mark_all")
check("a job that stops says so on the upload, as Failed, and in the Error Log",
      "frappe.db.rollback()" in job and "frappe.log_error(" in job and '"status": FAILED' in job)
check("an upload that has not moved for half an hour has lost its job, and is free to go on",
      "add_to_date(now_datetime(), minutes=-STOPPED_AFTER)" in body("running") and consts.get("STOPPED_AFTER") == 30
      and 'doc.get("modified")' in body("running"))
check("and the form is told so", 'doc.set_onload("stopped", doc.get("status") in RUNNING and not running(doc))'
      in body("upload_onload"))
check("a file is read as bytes, a .csv too", 'open(path, "rb")' in body("_file_bytes")
      and "get_content()" not in body("_file_bytes"))
check("the site's names the letters come to: the leave types, the shifts, annual leave and off duty",
      "leave.annual_type()" in body("_site_names") and "register.OFF_DUTY_LEAVE_TYPE" in body("_site_names"))

hooks = read("hrms_addon", "hooks.py")
after = hooks[hooks.index("after_migrate = ["):]
after = after[:after.index("]")]
check("after every migrate the doctype is put back if Frappe HR's patch took it, before the navigation",
      '"hrms_addon.hrms_addon.attendance_upload.keep_doctype"' in after
      and after.index("attendance_upload.keep_doctype") < after.index("navigation.setup_on_migrate"))
check("which reloads ours only when it is gone", 'if not frappe.db.exists("DocType", DOCTYPE):' in body("keep_doctype")
      and 'frappe.reload_doc("hrms_addon", "doctype", "upload_attendance", force=True)' in body("keep_doctype"))
controller = read("hrms_addon", "hrms_addon", "doctype", "upload_attendance", "upload_attendance.py")
check("the form's Import is a method of the upload", re.search(
    r"@frappe\.whitelist\(\)\n    def start_import\(self\):\n        return attendance_upload\.start_import\(self\)",
    controller) is not None)
check("the upload's own checks run on load, save and delete", "attendance_upload.upload_validate(self)" in controller
      and "attendance_upload.upload_on_trash(self)" in controller and "attendance_upload.upload_onload(self)" in controller)
form = read("hrms_addon", "hrms_addon", "doctype", "upload_attendance", "upload_attendance.js")
check("the form calls the register and the cycle where they are",
      '"hrms_addon.hrms_addon.attendance_upload."' in form and 'HA_UPLOAD_ATTENDANCE + "download_template"' in form
      and 'HA_UPLOAD_ATTENDANCE + "this_cycle"' in form)
check("Import calls the upload's own method with the upload", 'method: "start_import"' in form
      and "doc: frm.doc" in form)
check("an upload is saved before it is imported", "frm.is_new() || frm.is_dirty() ? frm.save()" in form)
check("the form knows which statuses are running", "HA_UPLOAD_RUNNING = [%s]" % ", ".join(
    '"%s"' % status for status in consts.get("RUNNING", ())) in form)
check("a stopped marking offers Import again, to go on", "(frm.doc.__onload || {}).stopped" in form
      and "HA_UPLOAD_RUNNING.includes(frm.doc.status) && !stopped" in form
      and "if (frm.doc.attendance_file && !running)" in form)
check("one hint at a time: the form clears its own before it draws one (two stood on the page, 21 Oct 2026)",
      'frm.layout.message.find(".ha-upload-hint").remove();' in form
      and 'frm.$intro_message.addClass("ha-upload-hint")' in form and form.count("frm.set_intro(") == 1)
listing = read("hrms_addon", "hrms_addon", "doctype", "upload_attendance", "upload_attendance_list.js")
check("the list colours every status", all('%s:' % s in listing or '"%s":' % s in listing
                                           for s in fields["status"]["options"].split("\n")))

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL UPLOAD ATTENDANCE CHECKS PASSED")
