"""Checks the Per Piece casuals' weekly pay without a bench:

    python scripts/verify_piece_pay.py

Luuka, 10 Nov 2026: "casual is divided into two, one that is paid per piece and
the one they are paid by the number of working hours". The Per Piece casuals'
workbook (PET packaging: a sheet a week, Thursday to Wednesday) is uploaded on
the weekly Payroll Entry; each week becomes a Per Piece report whose pay is
written as Additional Salary dated the week's last day, the arrears beside it,
and the weekly slip pays it as it pays any Additional Salary.

  1  a sheet's week from its name, in every layout Luuka's 2026 names take
  2  a workbook read: the headings, the prices, the rows, the TOTAL row, an
     Employee Id column, a sheet dated by its title or by nothing
  3  the rows checked: by Employee Id or name, a price's category on the week's
     day, the arrears paid, and what is left out and why
  4  the upload: one report a week and plant, their pay written; the upload made
     again replaces the last; a week on daily reports or a paid slip is left out
  5  a report: its arrears; its pay as Additional Salary under the right earning;
     refused once a slip paid the week; cancelled with its pay unless paid
  6  who a weekly payroll's Get Employees keeps
  7  wiring: the hooks, the report's fields, the button, the monthly run closed
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import sys
import types

from openpyxl import Workbook, load_workbook

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
D = datetime.date
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else detail)
    if not condition:
        fail.append(label)


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name, register=True):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if register:
        sys.modules["hrms_addon.hrms_addon." + name] = module
        setattr(app, name, module)
    return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
package.hrms_addon = app
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
S = load("piece_sheet")  # proves it has no Frappe import
O = load("output_rules")
R = load("weekly_pay_rules")
AR = load("advance_run_rules")
print("loaded piece_sheet.py and output_rules.py without Frappe")

# ── 1. A sheet's week from its name ──────────────────────
NAMES_2026 = {
    "1st-7th-Jan-2026": (D(2026, 1, 1), D(2026, 1, 7)),
    "08th-14th-January-2026": (D(2026, 1, 8), D(2026, 1, 14)),
    "29th-January to 04th-Feb-2026": (D(2026, 1, 29), D(2026, 2, 4)),
    "26th-Feb to 04th-March-26": (D(2026, 2, 26), D(2026, 3, 4)),
    "26th-03 to 01st-04th-2026": (D(2026, 3, 26), D(2026, 4, 1)),
    "30th-April to 6th-May-2026": (D(2026, 4, 30), D(2026, 5, 6)),
    "28th-May to 03rd-June 2026": (D(2026, 5, 28), D(2026, 6, 3)),
    "25th-June- to 1st-July-2026": (D(2026, 6, 25), D(2026, 7, 1)),
    "02-08th-July-2026": (D(2026, 7, 2), D(2026, 7, 8)),
    "23rd-29th-July-2026 ": (D(2026, 7, 23), D(2026, 7, 29)),
    "30th-July-05th-Aug-2026": (D(2026, 7, 30), D(2026, 8, 5)),
    "27th-August-02nd-September-2026": (D(2026, 8, 27), D(2026, 9, 2)),
    "10th-16th-September-2026 (2)": (D(2026, 9, 10), D(2026, 9, 16)),
    "17th-23ed-September-2026": (D(2026, 9, 17), D(2026, 9, 23)),
    "15th-21st-Octoer-2026": (D(2026, 10, 15), D(2026, 10, 21)),
    "22nd-28th-October-2026": (D(2026, 10, 22), D(2026, 10, 28)),
    "29th-Oct-04th-Nov-26": (D(2026, 10, 29), D(2026, 11, 4)),
    "27-04-23 to 3-05-23": (D(2023, 4, 27), D(2023, 5, 3)),
    "28th-Dec-23 to 3rd-Jan-2024": (D(2023, 12, 28), D(2024, 1, 3)),
    "11th-17th-04-24": (D(2024, 4, 11), D(2024, 4, 17)),
    "30th to 05th-August-2026": (D(2026, 7, 30), D(2026, 8, 5)),
}
wrong = {name: S.week_of(name) for name, week in NAMES_2026.items() if S.week_of(name) != week}
check(not wrong, "every layout of Luuka's sheet names gives its week, Thursday to Wednesday, typos and all", wrong)
check(all(S.week_of(name)[0].weekday() == 3 and S.week_of(name)[1].weekday() == 2
          for name in NAMES_2026 if S.week_of(name)[1].year == 2026),
      "each 2026 week starts on a Thursday and ends on a Wednesday")
check(S.week_of("EXTRA LABOUR") is None and S.week_of("1st-28th-Jan-2026") is None and S.week_of("8th-14th-2024") is None
      and S.week_of("13th-19-03-2925") is None and S.week_of("") is None and S.week_of(None) is None,
      "a name with no week, a month long, with no month or with a year that cannot be, dates nothing")
print("names: each sheet's week")


# ── 2. A workbook read ───────────────────────────────────
def sheet_rows(title, people, id_column=False, prices=(200, 180, 170)):
    """A sheet as Luuka lay theirs out: the title, the headings, the prices, a row a person, TOTAL."""
    width = len(prices)
    head = ["NO."] + (["PAYROLL NO"] if id_column else []) + ["NAME", "NUMBER OF BAGS PACKED"] + [None] * (width - 1) \
        + ["AMOUNT PER BAG PACKED"] + [None] * (width - 1) + ["TOTAL AMOUNT", "ARREARS"]
    price_row = [None] * (2 + (1 if id_column else 0)) + list(prices) + list(prices) + [None, None]
    rows = [[title], head, price_row]
    for number, person in enumerate(people, 1):
        bags = [person["bags"].get(price) for price in prices]
        amounts = [(value or 0) * price if isinstance(value, (int, float)) else None for value, price in zip(bags, prices)]
        total = person.get("total", sum(amount or 0 for amount in amounts))
        rows.append([number] + ([person.get("id")] if id_column else []) + [person["name"]] + bags + amounts
                    + [total, person.get("arrears")])
    rows.append([None] + ([None] if id_column else []) + ["TOTAL"])
    rows.append([None] + ([None] if id_column else []) + ["AFTER THE TOTAL", 99])
    return rows


def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


WEEK1 = [{"name": "TEST PERSON ONE", "id": "LPL-001", "bags": {200: 10, 180: 5}, "arrears": 500},
         {"name": "tester  second.", "id": "E2", "bags": {200: 3}},
         {"name": "THIRD EXAMPLE", "id": "E3", "bags": {170: 4}},
         {"name": "TWIN NAME", "bags": {200: 1}},
         {"name": "NOBODY KNOWN", "bags": {180: 2}},
         {"name": "FOURTH SAMPLE", "id": "E4", "bags": {200: 2}},
         {"name": "", "bags": {}}]
WEEK2 = [{"name": "Test Person One", "id": "E1", "bags": {200: 4}, "total": 900},
         {"name": "SECOND TESTER", "id": "E2", "bags": {180: 2}}]
CONTENT = workbook([
    ("22nd-28th-October-2026", sheet_rows("PET PACKAGING 22ND-28TH OCTOBER 2026", WEEK1, id_column=True)),
    ("29th-Oct-04th-Nov-26", sheet_rows("PET PACKAGING 22ND-28TH OCTOBER 2026", WEEK2, id_column=True)),
    ("15th-21st-Octoer-2026", sheet_rows("PET PACKAGING", [{"name": "TEST PERSON ONE", "id": "E1", "bags": {200: 7}}],
                                         id_column=True)),
    ("EXTRA LABOUR", [["EXTRA LABOUR"], ["NAME", "DAYS"], ["CASUAL", 3]]),
])
everything = S.read(CONTENT)
check([week["sheet"] for week in everything["weeks"]] == ["22nd-28th-October-2026", "29th-Oct-04th-Nov-26", "15th-21st-Octoer-2026"]
      and everything["unread"] == ["EXTRA LABOUR"] and everything["skipped"] == 0,
      "every dated sheet is read; one dated by nothing is named as unread", (everything["unread"], everything["skipped"]))
second = everything["weeks"][1]
check(second["start"] == D(2026, 10, 29) and second["end"] == D(2026, 11, 4),
      "a sheet is dated by its name, though its title is left from the week before", (second["start"], second["end"]))
first = everything["weeks"][0]
check(first["prices"] == [200.0, 180.0, 170.0] and [row["name"] for row in first["rows"]][:2] == ["TEST PERSON ONE", "tester second."]
      and len(first["rows"]) == 6 and first["rows"][0]["row"] == 4,
      "the prices under the bags heading; a row a person from the fourth, an empty row passed over, nothing after TOTAL",
      [row["name"] for row in first["rows"]])
row = first["rows"][0]
check(row["bags"] == {200.0: 10, 180.0: 5, 170.0: None} and row["total"] == 2900.0 and row["arrears"] == 500.0
      and row["employee_id"] == "LPL-001",
      "a row's employee number, its bags at each price, its total and its arrears", row)
wanted = S.read(CONTENT, wanted=lambda start, end: D(2026, 10, 22) <= end <= D(2026, 11, 4))
check([week["sheet"] for week in wanted["weeks"]] == ["22nd-28th-October-2026", "29th-Oct-04th-Nov-26"] and wanted["skipped"] == 1,
      "only the weeks asked for are read; the others are counted", wanted["skipped"])
titled = S.read(workbook([("Sheet7", sheet_rows("PET PACKAGING 05TH-11TH-NOVEMBER-2026", WEEK2))]))
check([(week["start"], week["end"]) for week in titled["weeks"]] == [(D(2026, 11, 5), D(2026, 11, 11))],
      "a sheet whose name dates nothing is dated by its title", titled)
ids = S.read(workbook([("05th-11th-November-2026", sheet_rows("PET", [{"name": "ANYBODY", "id": " lpl-007. ", "bags": {200: 1}}],
                                                                id_column=True))]))
check(ids["weeks"][0]["rows"][0]["employee_id"] == "lpl-007." and ids["weeks"][0]["prices"] == [200.0, 180.0, 170.0],
      "an Employee Id column is read beside the name", ids["weeks"][0]["rows"])
# Luuka's own Per Piece template (Luuka, 11 Nov 2026: "this is the client template for data importation"): one sheet
# named Sheet1, the week as its title in C1, NO. headed on the prices' row, and that column holds the employee number
CLIENT = [[None, None, "03rd-09th-September-2026"],
          [None, "NAME", "NUMBER 0F BAGS PACKED", None, None, "AMOUNT PER BAG PACKED", None, None, "TOTAL AMOUNT", "ARREARS"],
          ["NO.", None, 200, 180, 170, 200, 180, 170],
          ["E1", "TEST PERSON ONE", 166, 23, None, 33200, 4140, 0, 37340, None],
          [2, "SECOND TESTER ", 42, 170, None, 8400, 30600, 0, 39000, 500],
          [None, "TOTAL", None, None, None, None, None, None, 76340, 500]]
client = S.read(workbook([("Sheet1", CLIENT)]))
client_week = client["weeks"][0]
check((client_week["start"], client_week["end"]) == (D(2026, 9, 3), D(2026, 9, 9))
      and client_week["prices"] == [200.0, 180.0, 170.0]
      and [(row["row"], row["employee_id"], row["name"]) for row in client_week["rows"]]
      == [(4, "E1", "TEST PERSON ONE"), (5, "2", "SECOND TESTER")] and client_week["rows"][1]["arrears"] == 500,
      "Luuka's own template: dated by its title, its NO. read as the employee number though it is headed on the "
      "prices' row, its bags, its arrears", client_week)
headless = S.read(workbook([("05th-11th-November-2026", [["PET"], ["NAME", "DAYS"], [None, 3]])]))
check(headless["weeks"] == [] and headless["unread"] == ["05th-11th-November-2026"],
      "a dated sheet with no bags heading is named as unread, not guessed at", headless)
try:
    S.read(b"not a workbook")
    check(False, "a file that is no workbook is refused, saying so")
except ValueError as error:
    check("not an Excel workbook" in str(error), "a file that is no workbook is refused, saying so", str(error))
print("the workbook: headings, prices, rows, the weeks asked for")

# ── 3. The rows checked ──────────────────────────────────
PEOPLE = [
    {"employee": "E1", "employee_name": "Test Person One", "employee_number": "LPL-001", "category": "Per Piece", "branch": "PET"},
    {"employee": "E2", "employee_name": "Second Tester", "employee_number": None, "category": "Per Piece", "branch": "PET"},
    {"employee": "E3", "employee_name": "Third Example", "employee_number": None, "category": "Weekly", "branch": "PET"},
    {"employee": "E4", "employee_name": "Fourth Sample", "employee_number": None, "category": "Per Piece", "branch": "BOTTLES"},
    {"employee": "E5", "employee_name": "Twin Name", "employee_number": None, "category": "Per Piece", "branch": "PET"},
    {"employee": "E6", "employee_name": "Name Twin", "employee_number": None, "category": "Per Piece", "branch": "PET"},
    {"employee": "E7", "employee_name": "Seventh Case", "employee_number": "LPL-007", "category": "Per Piece", "branch": "PET"},
    {"employee": "E8", "employee_name": "Eighth Person", "employee_number": None, "category": "Per Piece", "branch": "PET"},
    {"employee": "E9", "employee_name": "Ninth Person", "employee_number": None, "category": "Per Piece", "branch": "PET"},
]
SIZES = {"BAG 200", "BAG 180", "BAG 170"}
RATES = {"BAG 200": [{"work_unit": 190, "valid_from": D(2026, 1, 1)}, {"work_unit": 200, "valid_from": D(2026, 10, 1)}],
         "BAG 180": [{"work_unit": 180, "valid_from": D(2026, 1, 1)}],
         "BAG 170": [{"work_unit": 170, "valid_from": D(2026, 1, 1)}]}
PERIOD = (D(2026, 10, 22), D(2026, 11, 4))
check(O.piece_key("tester  second.") == O.piece_key("SECOND TESTER") == "SECOND TESTER" and O.employee_key(" lpl-007. ") == "LPL-007",
      "a name is read whatever its case, spacing, dots or word order; an employee number whatever its spacing")
taken = O.take_pieces(wanted["weeks"], PEOPLE, SIZES, RATES, PERIOD, "PET", ["EXTRA LABOUR"])
check(taken["work"] == {("E1", D(2026, 10, 28), "BAG 200"): (10.0, 200.0, "'22nd-28th-October-2026', row 4"),
                        ("E1", D(2026, 10, 28), "BAG 180"): (5.0, 180.0, "'22nd-28th-October-2026', row 4"),
                        ("E2", D(2026, 10, 28), "BAG 200"): (3.0, 200.0, "'22nd-28th-October-2026', row 5"),
                        ("E1", D(2026, 11, 4), "BAG 200"): (4.0, 200.0, "'29th-Oct-04th-Nov-26', row 4"),
                        ("E2", D(2026, 11, 4), "BAG 180"): (2.0, 180.0, "'29th-Oct-04th-Nov-26', row 5")},
      "each person's bags under the category priced so that week, dated the week's last day", taken["work"])
check(taken["arrears"] == {},
      "the ARREARS column is not paid by the upload: arrears are entered as Additional Salary, which the weekly "
      "payroll pays (Luuka, 11 Nov 2026)", taken["arrears"])
problems = " | ".join(taken["problems"])
for needle, why in (("Third Example (E3) is paid Weekly, not Per Piece", "a casual paid by the hour is not paid for bags"),
                    ("row 7: TWIN NAME has no employee number, so the bags, worth 200, are left out: put it in the NO. "
                     "column. By name: Twin Name (E5) and Name Twin (E6).",
                     "a row with no employee number is not paid, however well its name fits (Luuka, 11 Nov 2026: \"use "
                     "employee number not employee name\"); those its name fits are said, for the number to be put in"),
                    ("row 8: NOBODY KNOWN has no employee number, so the bags, worth 360, are left out: put it in the "
                     "NO. column.", "and one whose name fits nobody is said, with what it was worth"),
                    ("Fourth Sample (E4) works at BOTTLES, not PET", "another plant's person is left to their own payroll")):
    check(needle in problems, "left out and said: %s" % why, taken["problems"])
check(len(taken["problems"]) == 4, "and nothing else is left out", taken["problems"])
check(not any("by name" in problem.lower() for problem in taken["problems"] if "NOBODY KNOWN" in problem),
      "a name near nobody's names nobody", taken["problems"])
notes = " | ".join(taken["notes"])
check("Weeks taken: 22-Oct-2026 to 28-Oct-2026 and 29-Oct-2026 to 04-Nov-2026." in notes
      and "Test Person One's total is 900, but the bags at their prices come to 800, which is what is paid" in notes
      and "Arrears on the sheet are not paid by this upload: enter them as Additional Salary, which the weekly payroll "
          "pays. 1, 500 in all: Test Person One (E1) 500." in notes
      and "Sheets with no week in their name or title, not read: EXTRA LABOUR." in notes,
      "said beside it: the weeks taken, a total that is not its bags, the arrears to enter as Additional Salary, the "
      "sheets not read", taken["notes"])
old_price = O.take_pieces([{"sheet": "old", "start": D(2026, 9, 3), "end": D(2026, 9, 9), "prices": [190.0],
                            "rows": [{"row": 4, "name": "Second Tester", "employee_id": "E2", "bags": {190.0: 2}}]}],
                          PEOPLE, SIZES, RATES, (D(2026, 9, 3), D(2026, 9, 9)), None)
check(old_price["work"] == {("E2", D(2026, 9, 9), "BAG 200"): (2.0, 190.0, "'old', row 4")} and not old_price["problems"],
      "a price names the category whose Work Unit it was on the week's last day, before the price went up", old_price)
by_id = O.take_pieces(ids["weeks"], PEOPLE, SIZES, RATES, (D(2026, 11, 5), D(2026, 11, 11)), "PET")
check(list(by_id["work"]) == [("E7", D(2026, 11, 11), "BAG 200")],
      "where the sheet has an Employee Id column, the person is found by it, whatever the name says", by_id)
check(O.employee_key("LPL-007_x000D_\n") == "LPL-007" and "payroll no" in S.EMPLOYEE_ID,
      "Luuka's PAYROLL NO heading is an Employee Id column, and the _x000D_ Excel leaves on an Id is passed over")
near = O.take_pieces([{"sheet": "w", "start": D(2026, 10, 29), "end": D(2026, 11, 4), "prices": [200.0],
                       "rows": [{"row": 4, "name": "SECOND TESTOR", "bags": {200.0: 1}},
                                {"row": 5, "name": "THIRD EXAMPEL", "bags": {200.0: 1}}]}],
                     PEOPLE, SIZES, RATES, PERIOD, "PET")
check(near["work"] == {} and any("SECOND TESTOR has no employee number, so the bags, worth 200, are left out: put it in "
                                 "the NO. column. Closest by name: Second Tester (E2)." in problem
                                 for problem in near["problems"])
      and not any("by name" in problem for problem in near["problems"] if "THIRD EXAMPEL" in problem)
      and "'w' has no employee numbers, so nobody on it is paid: put each person's employee number in the NO. column."
      in near["problems"],
      "a sheet with no employee numbers pays nobody, and says so; the closest Per Piece casual to each name is said, "
      "never taken", near["problems"])
counted = O.take_pieces([{"sheet": "w", "start": D(2026, 10, 29), "end": D(2026, 11, 4), "prices": [200.0],
                          "rows": [{"row": 4, "name": "Second Tester", "employee_id": "1", "bags": {200.0: 1}},
                                   {"row": 5, "name": "Seventh Case", "employee_id": "2", "bags": {200.0: 1}}]}],
                        PEOPLE, SIZES, RATES, PERIOD, "PET")
check(counted["work"] == {} and "'w' has no employee numbers, so nobody on it is paid: put each person's employee number "
                                "in the NO. column." in counted["problems"]
      and any("Second Tester has no employee number" in problem and "By name: Second Tester (E2)" in problem
              for problem in counted["problems"]),
      "a 1, 2, 3 in the NO. column counts the rows: nobody's employee number, so nobody is paid on it", counted["problems"])
numbered = O.take_pieces([{"sheet": "w", "start": D(2026, 10, 29), "end": D(2026, 11, 4), "prices": [200.0],
                           "rows": [{"row": 4, "name": "SECOND TESTOR", "employee_id": "E2", "bags": {200.0: 1}},
                                    {"row": 5, "name": "SECOND TESTER", "employee_id": "E9", "bags": {200.0: 2}},
                                    {"row": 6, "name": "", "employee_id": "LPL-007", "bags": {200.0: 3}}]}],
                         PEOPLE, SIZES, RATES, PERIOD, "PET")
check(set(numbered["work"]) == {("E2", D(2026, 11, 4), "BAG 200"), ("E9", D(2026, 11, 4), "BAG 200"),
                                ("E7", D(2026, 11, 4), "BAG 200")} and not numbered["problems"],
      "a row is paid by its number, whatever its name says: a misspelt name, another's name, no name", numbered)
check([note for note in numbered["notes"] if "check the number" in note]
      == ["'w', row 5: E9 is Ninth Person, not SECOND TESTER as the sheet says: check the number before the run is "
          "submitted."],
      "a number whose employee's name has no word of the sheet's is said, to be checked before the run is paid; a "
      "misspelt name sharing a word is not", numbered["notes"])
cases = O.take_pieces([{"sheet": "w", "start": D(2026, 10, 29), "end": D(2026, 11, 4), "prices": [200.0, 150.0],
                        "rows": [{"row": 4, "name": "Second Tester", "employee_id": "LPL-999", "bags": {200.0: 1}},
                                 {"row": 5, "name": "Seventh Case", "employee_id": "LPL-007", "bags": {200.0: "two", 150.0: 3}},
                                 {"row": 6, "name": "Test Person One", "employee_id": "E1", "bags": {200.0: 1}},
                                 {"row": 7, "name": "TEST PERSON ONE", "employee_id": "E1", "bags": {200.0: 2}},
                                 {"row": 8, "name": "Twin Name", "employee_id": "E5", "bags": {}, "arrears": 0},
                                 {"row": 9, "name": "Second Tester", "employee_id": "E2", "bags": {200.0: -1}},
                                 {"row": 10, "name": "Eighth Person", "employee_id": "E8", "bags": {200.0: "ABSENT"}},
                                 {"row": 11, "name": "Twin Name", "employee_id": "E5", "bags": {200.0: 0, 180.0: None}},
                                 {"row": 12, "name": "Ninth Person", "employee_id": "E9", "bags": {}, "arrears": -300}]}],
                      PEOPLE, SIZES, RATES, PERIOD, "PET")
said = " | ".join(cases["problems"])
for needle, why in (("No Per Piece category is priced 150 on 04-Nov-2026", "a price no category has"),
                    ("the Employee Id LPL-999 is nobody here", "an Employee Id that is nobody's"),
                    ("'two' bags at 200 is not a number of bags", "bags that are not a number"),
                    ("Test Person One (E1) is on 'w' twice (rows 6 and 7), so neither is taken", "a person twice in a week"),
                    ("-1 bags at 200 is not a number of bags", "bags less than nothing, though nothing else is on the row"),
                    ("'ABSENT' bags at 200 is not a number of bags", "a word where the bags go")):
    check(needle in said, "left out and said: %s" % why, cases["problems"])
check(cases["work"] == {} and cases["arrears"] == {}
      and not any("row 11" in problem or "row 12" in problem for problem in cases["problems"]),
      "and none of it is paid; a row of noughts, or of arrears alone, is nobody's business here", cases["problems"])
two_sheets = O.take_pieces([dict(wanted["weeks"][1], sheet="a"), dict(wanted["weeks"][1], sheet="b")], PEOPLE, SIZES, RATES,
                           PERIOD, "PET")
check(two_sheets["work"] == {} and "is on 2 sheets ('a' and 'b'): none of them is taken" in " ".join(two_sheets["problems"]),
      "a week on two sheets is not guessed between", two_sheets["problems"])
same_price = O.take_pieces(wanted["weeks"][1:], PEOPLE, SIZES | {"BAG 200B"}, dict(RATES, **{"BAG 200B": RATES["BAG 200"]}),
                           PERIOD, "PET")
check("BAG 200 and BAG 200B are all priced 200" in " ".join(same_price["problems"])
      and ("E1", D(2026, 11, 4), "BAG 200") not in same_price["work"],
      "two categories at one price leave those bags out: which was packed cannot be told", same_price["problems"])
outside = O.take_pieces(wanted["weeks"], PEOPLE, SIZES, RATES, (D(2026, 11, 5), D(2026, 11, 11)), "PET")
check(outside["work"] == {} and "No weekly sheet ends between 05-Nov-2026 and 11-Nov-2026" in " ".join(outside["problems"]),
      "a week is the payroll's whose last day is in its dates; none, and it says so", outside["problems"])
check(O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4)) == (D(2026, 11, 4), None)
      and O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4), left=D(2026, 10, 31)) == (D(2026, 10, 31), None)
      and O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4), joined=D(2026, 11, 2), left=D(2026, 11, 30)) == (D(2026, 11, 4), None)
      and O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4), left=D(2026, 10, 28))[1] == "they left on 28-Oct-2026, before the "
                                                                                       "days this run pays"
      and O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4), joined=D(2026, 11, 5))[1] == "they joined on 05-Nov-2026, after the week"
      and O.piece_pay_day(D(2026, 10, 29), D(2026, 11, 4), status="Inactive")[1] == "they are Inactive",
      "a week's pay is dated its last day, or the last day of one who left during it; not for one who joined after it, "
      "left before it, or is Inactive")
anywhere = O.take_pieces(wanted["weeks"][:1], PEOPLE, SIZES, RATES, PERIOD, None)
check(("E4", D(2026, 10, 28), "BAG 200") in anywhere["work"], "a payroll for every plant takes every plant's casuals")
print("the rows: found by employee number alone, priced by the week's category, what is left out said")


# ── A stand-in site ──────────────────────────────────────
class Thrown(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


def as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, D):
        return value
    try:
        return D.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def same(have, want):
    if isinstance(have, D) or isinstance(want, D):
        return as_date(have) == as_date(want)
    return have == want


def matches(row, filters):
    for field, want in (filters or {}).items():
        have = row.get(field)
        if not isinstance(want, (list, tuple)):
            if not same(have, want):
                return False
            continue
        op, value = want[0], want[1]
        if op == "in":
            if not any(same(have, one) for one in value):
                return False
        elif op == "between":
            if have is None or not as_date(value[0]) <= as_date(have) <= as_date(value[1]):
                return False
        elif op in ("<", "<=", ">", ">="):
            if have is None:
                return False
            left, right = (as_date(have), as_date(value)) if isinstance(value, (D, str)) else (have, value)
            if not {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]:
                return False
        else:
            raise AssertionError("no stand-in for %s" % op)
    return True


CHILDREN = {"Daily Production Line": ("Daily Production Report", ("lines",)),
            "Daily Production Overtime": ("Daily Production Report", ("looms_ot", "arrears")),
            "Salary Detail": ("Salary Slip", ("earnings", "deductions")),
            "Output Rate Work Unit": ("Output Rate", ("rates",))}


class Doc:
    def __init__(self, site, values, row=None):
        self.__dict__.update(site=site, row=row, flags=Row())
        self.__dict__["values"] = Row({key: [Row(line, idx=number) for number, line in enumerate(value, 1)]
                                       if isinstance(value, list) else value for key, value in values.items()})

    def __getattr__(self, key):
        if key.startswith("__"):
            raise AttributeError(key)
        return self.__dict__["values"].get(key)

    def __setattr__(self, key, value):
        self.__dict__["values"][key] = value
        if self.row is not None:
            self.row[key] = value

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        setattr(self, key, value)

    def check_permission(self, ptype):
        if self.site.denied:
            raise Thrown("Not permitted")

    def is_new(self):
        return self.row is None

    def run(self, event):
        for path in EVENTS.get(self.values.get("doctype"), {}).get(event, []):
            HANDLERS[path](self)

    def insert(self):
        doctype = self.values["doctype"]
        self.values.setdefault("name", "%s-%d" % ("".join(word[0] for word in doctype.split()), self.site.next()))
        self.values.setdefault("docstatus", 0)
        self.run("validate")  # Frappe's insert: the validate hooks, then the mandatory fields
        if doctype == "Daily Production Report" and not self.values.get("lines") and not self.flags.get("ignore_mandatory"):
            raise Thrown("Value missing for Daily Production Report: Lines")
        self.__dict__["row"] = self.site.add(doctype, **{key: value for key, value in self.values.items() if key != "doctype"})
        self.site.log.append(("insert", doctype, self.values["name"]))
        if self.values["docstatus"] == 1:
            self.run("on_submit")
        return self

    def submit(self):
        self.docstatus = 1
        self.run("on_submit")
        self.site.log.append(("submit", self.values["doctype"], self.values["name"]))

    def cancel(self):
        self.run("on_cancel")
        self.docstatus = 2
        self.site.log.append(("cancel", self.values["doctype"], self.values["name"]))

    def save(self):
        self.site.log.append(("save", self.values["doctype"], self.values["name"]))
        return self


class Site:
    def __init__(self):
        self.tables, self.log, self.files, self.messages = {}, [], {}, []
        self.denied, self.unassignable, self.assigned, self.number = False, {}, [], 0
        self.accounts = set()

    def next(self):
        self.number += 1
        return self.number

    def add(self, doctype, **values):
        row = Row(values)
        row.setdefault("docstatus", 0)
        self.tables.setdefault(doctype, []).append(row)
        return row

    def rows(self, doctype):
        if doctype in CHILDREN:
            parent_type, fields = CHILDREN[doctype]
            return [Row(line, parent=row.name, parenttype=parent_type, parentfield=field, docstatus=row.docstatus)
                    for row in self.tables.get(parent_type, []) for field in fields for line in row.get(field) or []]
        return self.tables.get(doctype, [])

    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, limit=None):
        found = [row for row in self.rows(doctype) if matches(row, filters)]
        if order_by:
            field, way = (order_by.split() + ["asc"])[:2]
            found.sort(key=lambda row: str(row.get(field) or ""), reverse=way == "desc")
        if pluck:
            return [row.get(pluck) for row in found]
        return [Row({field: row.get(field) for field in (fields or ["name"])}) for row in found]

    def get_value(self, doctype, filters, fieldname, order_by=None, as_dict=False):
        filters = {"name": filters} if isinstance(filters, str) else filters
        found = self.get_all(doctype, filters, fields=[fieldname] if isinstance(fieldname, str) else fieldname,
                             order_by=order_by)
        if not found:
            return None
        return found[0] if not isinstance(fieldname, str) else found[0].get(fieldname)

    def exists(self, doctype, filters):
        filters = {"name": filters} if isinstance(filters, str) else filters
        found = [row for row in self.rows(doctype) if matches(row, filters)]
        return found[0].get("name") if found else None

    def get_doc(self, values, name=None):
        if isinstance(values, dict):
            return Doc(self, values)
        row = next(row for row in self.rows(values) if row.name == name)
        return Doc(self, dict(row, doctype=values), row)

    def delete(self, doctype, name):
        self.tables[doctype] = [row for row in self.tables.get(doctype, []) if row.name != name]
        self.log.append(("delete", doctype, name))


SITE = [None]


def site():
    return SITE[0]


frappe = types.ModuleType("frappe")
frappe._ = lambda text, *args, **kwargs: text


def whitelist(*args, **kwargs):
    return (lambda fn: fn) if not args or not callable(args[0]) else args[0]


def throw(message, title=None, *args, **kwargs):
    raise Thrown(message)


frappe.whitelist = whitelist
frappe.throw = throw
frappe.msgprint = lambda message, *args, **kwargs: site().messages.append(message)
frappe.get_all = lambda *args, **kwargs: site().get_all(*args, **kwargs)
frappe.get_doc = lambda *args, **kwargs: site().get_doc(*args, **kwargs)
frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda field: True)
frappe.get_cached_value = lambda doctype, name, field: {"default_currency": "UGX"}.get(field)
frappe.delete_doc = lambda doctype, name, **kwargs: site().delete(doctype, name)
frappe.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: site().get_value(*args, **kwargs),
                                  exists=lambda *args, **kwargs: site().exists(*args, **kwargs))
utils = types.ModuleType("frappe.utils")
utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
utils.cint = lambda value: int(float(value or 0))
utils.getdate = lambda value=None: as_date(value) if value else D(2026, 11, 10)
frappe.utils = utils
sys.modules.update({"frappe": frappe, "frappe.utils": utils})

# output_pay and weekly_pay as piece_pay uses them: their own checks are verify_output_pay.py and verify_weekly_pay.py
output_pay = types.ModuleType("hrms_addon.hrms_addon.output_pay")
output_pay.REPORT, output_pay.REPORT_LINE, output_pay.REPORT_OT = ("Daily Production Report", "Daily Production Line",
                                                                   "Daily Production Overtime")
output_pay._file_bytes = lambda file_url: site().files[file_url]


def sizes_of(names=None, section=None):
    return {row.name: {"section": row.section, "enabled": row.enabled, "order": 0,
                       "rates": [{"work_unit": line.work_unit, "valid_from": line.valid_from} for line in row.rates or []]}
            for row in site().rows("Output Rate") if (names is None or row.name in names) and (not section or row.section == section)}


def made_component(section):
    name = {"Per Piece": "Per Piece Earnings"}[section]
    if not site().exists("Salary Component", name):
        site().add("Salary Component", name=name, type="Earning", depends_on_payment_days=0)
    return name


def priced_lines(doc, method=None):
    """output_pay.report_validate's part piece_pay stands on: each line priced at its category's Work Unit that day."""
    sizes = sizes_of()
    for line in doc.get("lines") or []:
        line.rate = O.work_unit_on(sizes[line.size]["rates"], doc.report_date) or 0
        line.amount = O.line_total(line.output, line.rate)


output_pay._sizes = sizes_of
output_pay._component = made_component
output_pay._pay_categories = lambda employees: {row.name: row.custom_pay_category for row in site().rows("Employee")
                                                if row.name in set(employees)}
output_pay.report_validate = priced_lines
output_pay.report_on_submit = lambda doc, method=None: None
output_pay.report_on_cancel = lambda doc, method=None: None
output_pay.RUN = "Output Pay Run"
output_pay._paid_run = lambda branch, section, day: next(
    (row.name for row in site().rows("Output Pay Run") if row.docstatus == 1 and row.branch == branch
     and row.section == section and as_date(row.from_date) <= as_date(day) <= as_date(row.to_date)), None)


def fill_run(doc):
    """output_pay._fill and _earnings, as far as piece_pay stands on them: the run's lines and arrears from the
    submitted Per Piece reports of its plant and days, those that wrote their own pay left out, and what each
    person is paid under each earning (output_rules.earnings). Their own checks are verify_output_pay.py."""
    reports = [row for row in site().rows("Daily Production Report")
               if row.docstatus == 1 and row.section == "Per Piece" and row.branch == doc.branch
               and as_date(doc.from_date) <= as_date(row.report_date) <= as_date(doc.to_date)]
    own = P.self_paid([row.name for row in reports])
    reports = [row for row in reports if row.name not in own]
    lines = [Row(employee=line.employee, size=line.size, output=line.output, amount=line.amount or 0)
             for row in reports for line in row.lines or []]
    # arrears are paid as Additional Salary, none from a report (Luuka, 11 Nov 2026)
    named = {row.name: row.salary_component for row in site().rows("Output Rate") if row.get("salary_component")}
    doc.lines = lines
    doc.arrears = []
    doc.earnings = [Row(row) for row in O.earnings(lines, {}, named, "Per Piece Earnings", P.ARREARS[0])]


output_pay._fill = fill_run
weekly_pay = types.ModuleType("hrms_addon.hrms_addon.weekly_pay")


def assign_people(employees, company, start):
    site().assigned.append((sorted(employees), company, start))
    return {employee: site().unassignable[employee] for employee in employees if employee in site().unassignable}


weekly_pay.assign_people = assign_people
weekly_pay._give_account = lambda component, company: site().accounts.add((component, company))
sys.modules.update({"hrms_addon.hrms_addon.output_pay": output_pay, "hrms_addon.hrms_addon.weekly_pay": weekly_pay})
app.output_pay, app.weekly_pay = output_pay, weekly_pay
load("advance_runs")
P = load("piece_pay")

# the report's events as hooks.py lists them, run by the stand-in on insert, submit and cancel
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
EVENTS = {"Daily Production Report": {event: paths if isinstance(paths, list) else [paths]
                                      for event, paths in hooks["doc_events"]["Daily Production Report"].items()}}
HANDLERS = {}
for paths in EVENTS["Daily Production Report"].values():
    for path in paths:
        module, function = path.rsplit(".", 1)
        HANDLERS[path] = getattr(sys.modules[module], function)


def populated():
    s = Site()
    SITE[0] = s
    for person in PEOPLE:
        s.add("Employee", name=person["employee"], employee_name=person["employee_name"],
              employee_number=person["employee_number"], custom_pay_category=person["category"], branch=person["branch"])
    for name, unit in (("BAG 200", 200), ("BAG 180", 180), ("BAG 170", 170)):
        s.add("Output Rate", name=name, section="Per Piece", enabled=1, salary_component=None,
              rates=[Row(work_unit=unit, valid_from=D(2026, 1, 1))])
    s.add("Output Rate", name="SIZE 1", section="Per Meter", enabled=1, rates=[Row(work_unit=200, valid_from=D(2026, 1, 1))])
    s.add("Salary Component", name="Per Piece Earnings", type="Earning", depends_on_payment_days=0)
    s.add("Output Pay Run", name="RUN-W", company="LPL", section="Per Piece", docstatus=0, from_date=D(2026, 10, 22),
          to_date=D(2026, 11, 4), branch="PET")
    s.files["/private/files/pet.xlsx"] = CONTENT
    return s


def pay_run(name):
    """output_pay.run_on_submit, as far as a Per Piece run goes: what piece_pay.before_paying asks first, then each
    earning written as Additional Salary dated the day it gives."""
    run = site().get_doc("Output Pay Run", name)
    fill_run(run)
    days = P.before_paying(run)
    for row in run.earnings:
        if row.amount > 0:
            site().add("Additional Salary", name="ADS-%d" % site().next(), employee=row.employee, company=run.company,
                       salary_component=row.salary_component, amount=row.amount, type="Earning", is_recurring=0,
                       payroll_date=days.get(row.employee) or run.to_date, ref_doctype="Output Pay Run",
                       ref_docname=run.name, docstatus=1)
    run.docstatus = 1


def reports_of(s):
    """{the week's last day: {employee: [(category, bags)]}} of the submitted Per Piece reports that stand."""
    out = {}
    for row in s.rows("Daily Production Report"):
        if row.docstatus == 1 and row.section == "Per Piece":
            seat = out.setdefault(as_date(row.report_date), {})
            for line in row.lines or []:
                seat.setdefault(line.employee, []).append((line.size, line.output))
    return out


def pay(s):
    """{(employee, component, payroll date): amount} of the Additional Salary that stands."""
    return {(row.employee, row.salary_component, as_date(row.payroll_date)): row.amount
            for row in s.rows("Additional Salary") if row.docstatus == 1}


# ── 4. The upload ────────────────────────────────────────
s = populated()
found = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
reports = [row for row in s.rows("Daily Production Report")]
check([(row.report_date, row.branch, row.source, row.section, row.docstatus, row.sheet_run) for row in reports]
      == [(D(2026, 10, 28), "PET", "Uploaded", "Per Piece", 1, "RUN-W"), (D(2026, 11, 4), "PET", "Uploaded", "Per Piece", 1, "RUN-W")]
      and found["reports"] == [row.name for row in reports],
      "one submitted Per Piece report for each week and plant, dated the week's last day, naming the run it was uploaded on",
      reports)
check([(line.employee, line.size, line.output, line.rate, line.amount) for line in reports[0].lines]
      == [("E1", "BAG 200", 10.0, 200, 2000.0), ("E1", "BAG 180", 5.0, 180, 900.0), ("E2", "BAG 200", 3.0, 200, 600.0)]
      and not reports[0].arrears,
      "each line its bags at the category's price; no arrears on the report: they are entered as Additional Salary",
      reports[0].lines)
check(not s.rows("Additional Salary"),
      "the upload writes no pay: the run does when it is submitted, as a Per Meter run does (Luuka, 11 Nov 2026)",
      s.rows("Additional Salary"))
run = s.rows("Output Pay Run")[0]
check(run.uploaded_sheet == "/private/files/pet.xlsx" and ("save", "Output Pay Run", "RUN-W") in s.log
      and {(row.employee, row.salary_component): row.amount for row in run.earnings}
      == {("E1", "Per Piece Earnings"): 3700.0, ("E2", "Per Piece Earnings"): 960.0},
      "the run is filled from the week's reports and saved with its sheet", run.earnings)
check(found["weeks"] == 2 and found["people"] == 2 and found["bags"] == 24.0 and found["amount"] == 4660.0 and found["arrears"] == 0,
      "the upload says what it took: the weeks, the people, the bags and the pay; no arrears", found)
check(len(found["problems"]) == 4 and any("NOBODY KNOWN" in problem for problem in found["problems"])
      and any("Arrears on the sheet are not paid by this upload" in note for note in found["notes"])
      and any("1 other weekly sheet(s) end outside 22-Oct-2026 to 04-Nov-2026: the run of the week each ends in takes it."
              in note for note in found["notes"]),
      "and what it left out, and what it saw: the sheets the run of another week takes", found["notes"])
check(("E1", "E2") == tuple(s.assigned[0][0]) and s.assigned[0][2] == D(2026, 10, 22),
      "those on the sheet are given the weekly structure first, from the run's From, as Get Employees would", s.assigned)
pay_run("RUN-W")
check(pay(s) == {("E1", "Per Piece Earnings", D(2026, 11, 4)): 3700.0, ("E2", "Per Piece Earnings", D(2026, 11, 4)): 960.0},
      "submitted, each person's pay is Additional Salary dated the run's last day, which the weekly slip pays; no arrears",
      pay(s))
check(not [row for row in s.rows("Salary Component") if row.name == "Arrears"],
      "no Arrears earning is made by a run: it pays none", s.rows("Salary Component"))
check(s.accounts == {("Per Piece Earnings", "LPL")},
      "each earning paid is given the company's account, as posting the payroll needs one", s.accounts)
check((["E1", "E2"], "LPL", D(2026, 10, 22)) == s.assigned[-1],
      "and each person paid is on the weekly structure as the run is submitted", s.assigned[-1])

s = populated()
P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
first = [row.name for row in s.rows("Daily Production Report")]
again = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(len(s.rows("Daily Production Report")) == 2 and not set(first) & {row.name for row in s.rows("Daily Production Report")}
      and [event for event in s.log if event[:2] == ("delete", "Daily Production Report")] and not s.rows("Additional Salary"),
      "uploaded again, the last upload goes and the new one stands: nothing twice",
      (len(s.rows("Daily Production Report")), s.log))
pay_run("RUN-W")
check(pay(s) == {("E1", "Per Piece Earnings", D(2026, 11, 4)): 3700.0, ("E2", "Per Piece Earnings", D(2026, 11, 4)): 960.0},
      "and the run pays it once", pay(s))
s = populated()
s.add("Output Pay Run", name="RUN-B", company="LPL", section="Per Piece", docstatus=0, from_date=D(2026, 10, 22),
      to_date=D(2026, 11, 4), branch="BOTTLES")
P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
P.upload_pieces("RUN-B", "/private/files/pet.xlsx")
P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
pay_run("RUN-B")
check(pay(s) == {("E4", "Per Piece Earnings", D(2026, 11, 4)): 400.0}
      and [row.branch for row in s.rows("Daily Production Report")].count("BOTTLES") == 1
      and [row.branch for row in s.rows("Daily Production Report")].count("PET") == 2,
      "another plant's run takes its own casuals off the same workbook, and this plant's upload leaves theirs standing",
      pay(s))
s = populated()
P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
s.files["/private/files/one_week.xlsx"] = workbook([("29th-Oct-04th-Nov-26", sheet_rows(
    "PET", [{"name": "SECOND TESTER", "id": "E2", "bags": {180: 7}}], id_column=True))])
P.upload_pieces("RUN-W", "/private/files/one_week.xlsx")
check(reports_of(s) == {D(2026, 10, 28): {"E1": [("BAG 200", 10.0), ("BAG 180", 5.0)], "E2": [("BAG 200", 3.0)]},
                        D(2026, 11, 4): {"E2": [("BAG 180", 7.0)]}},
      "a sheet of one week replaces that week's upload, and the other week's stands", reports_of(s))

s = populated()
s.add("Daily Production Report", name="DPR-HAND", report_date=D(2026, 10, 25), section="Per Piece", source="Entered", branch="PET",
      docstatus=1, lines=[Row(employee="E2", size="BAG 200", output=1, amount=200.0)])
s.add("Daily Production Report", name="DPR-METER", report_date=D(2026, 10, 25), section="Per Meter", source="Entered", branch="PET",
      docstatus=1, lines=[Row(employee="E1", size="SIZE 1", output=1)])
held = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check("E2" not in reports_of(s)[D(2026, 10, 28)] and reports_of(s)[D(2026, 11, 4)].get("E2") == [("BAG 180", 2.0)]
      and "E1" in reports_of(s)[D(2026, 10, 28)]
      and any("Second Tester's week to 28-Oct-2026 is on submitted daily reports (DPR-HAND)" in problem for problem in held["problems"]),
      "a week a supervisor's daily report already has for a person stays on it, said; their other week and the others are "
      "taken", (reports_of(s), held["problems"]))
pay_run("RUN-W")
check(pay(s).get(("E2", "Per Piece Earnings", D(2026, 11, 4))) == 560.0,
      "and the run pays the supervisor's report with the week's sheet: 200 and 360", pay(s))

s = populated()
s.add("Salary Slip", name="SS-PAID", employee="E1", docstatus=1, payroll_frequency="Weekly", start_date=D(2026, 10, 22),
      end_date=D(2026, 10, 28))
paid = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check("E1" not in reports_of(s)[D(2026, 10, 28)] and not s.rows("Daily Production Report")[0].arrears
      and "E1" in reports_of(s)[D(2026, 11, 4)]
      and any("Test Person One's week to 28-Oct-2026 on the sheet, 2,900, is left out: SS-PAID has already paid that week." in problem
              for problem in paid["problems"]),
      "a week a submitted weekly slip already covers is left out and said; the person's other week is taken", paid["problems"])

s = populated()
s.add("Output Pay Run", name="RUN-OLD", company="LPL", section="Per Piece", docstatus=1, from_date=D(2026, 10, 22),
      to_date=D(2026, 10, 28), branch="PET")
s.add("Daily Production Report", name="DPR-OLD", report_date=D(2026, 10, 28), section="Per Piece", source="Uploaded", branch="PET",
      docstatus=1, output_pay_run="RUN-OLD", lines=[Row(employee="E1", size="BAG 200", output=9, amount=1800.0)])
stands = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(reports_of(s)[D(2026, 10, 28)] == {"E1": [("BAG 200", 9)]} and "E1" in reports_of(s)[D(2026, 11, 4)]
      and not [event for event in s.log if event[:2] in (("delete", "Daily Production Report"), ("cancel", "Daily Production Report"))]
      and any("The week to 28-Oct-2026 on the sheet is left out: RUN-OLD has already paid it." in problem
              for problem in stands["problems"]),
      "a week another submitted run has paid is left out and said, and its reports stand behind that pay", stands["problems"])

s = populated()
s.files["/private/files/arrears.xlsx"] = workbook([("29th-Oct-04th-Nov-26", sheet_rows("PET", [
    {"name": "EIGHTH PERSON", "id": "E8", "bags": {}, "arrears": 250}], id_column=True))])
only_arrears = P.upload_pieces("RUN-W", "/private/files/arrears.xlsx")
pay_run("RUN-W")
check(pay(s) == {} and not s.rows("Daily Production Report")
      and any("Eighth Person (E8) 250" in note for note in only_arrears["notes"]),
      "a week with only arrears makes nothing: the arrears are said, to be entered as Additional Salary",
      (pay(s), only_arrears["notes"]))
s = populated()
for row in s.rows("Employee"):
    if row.name == "E2":
        row.update(relieving_date=D(2026, 10, 31), status="Left")
    if row.name == "E1":
        row.update(date_of_joining=D(2026, 10, 29))
employment = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
pay_run("RUN-W")
check(pay(s) == {("E2", "Per Piece Earnings", D(2026, 10, 31)): 960.0, ("E1", "Per Piece Earnings", D(2026, 11, 4)): 800.0}
      and any("Test Person One's week to 28-Oct-2026 on the sheet, 2,900, is left out: they joined on 29-Oct-2026, after "
              "the week." in problem for problem in employment["problems"]),
      "one who left during the run's days is paid on their last day; a week before someone joined is left out and said, "
      "not a failed upload", (pay(s), employment["problems"]))
s = populated()
for row in s.rows("Employee"):
    if row.name == "E2":
        row.update(relieving_date=D(2026, 10, 20), status="Left")
gone = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(not any("E2" in seat for seat in reports_of(s).values())
      and any("Second Tester's week to 28-Oct-2026 on the sheet, 600, is left out: they left on 20-Oct-2026, before the "
              "days this run pays." in problem for problem in gone["problems"]),
      "one who left before the run's days is not paid on it, and is said", gone["problems"])
s = populated()
for row in s.rows("Employee"):
    if row.name == "E2":
        row.update(status="Inactive")
inactive = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(not any("E2" in seat for seat in reports_of(s).values()) and "E1" in reports_of(s)[D(2026, 10, 28)]
      and any("Second Tester's week to 04-Nov-2026 on the sheet, 360, is left out: they are Inactive." in problem
              for problem in inactive["problems"]),
      "an Inactive person's weeks are left out and said; everyone else is taken", inactive["problems"])
s = populated()
s.unassignable["E2"] = "they already have an assignment from that day"
failed = P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(not any("E2" in seat for seat in reports_of(s).values())
      and any("Second Tester's pay on the sheet, 960, is left out: they have no salary assignment: they already have an "
              "assignment from that day" in problem for problem in failed["problems"]),
      "one who cannot be given the weekly structure is left out, saying why", failed["problems"])
for change, why in (({"docstatus": 1}, "a submitted run takes no sheet"),
                    ({"section": "Per Meter"}, "a Per Meter run takes no Per Piece sheet"),
                    ({"to_date": None}, "nor a run with no dates")):
    s = populated()
    s.rows("Output Pay Run")[0].update(change)
    try:
        P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
        check(False, why)
    except Thrown:
        check(not s.rows("Daily Production Report"), why)
s = populated()
s.denied = True
try:
    P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
    check(False, "only one who may change the run uploads to it")
except Thrown:
    check(True, "only one who may change the run uploads to it")
s = populated()
s.files["/private/files/bad.xlsx"] = b"not a workbook"
try:
    P.upload_pieces("RUN-W", "/private/files/bad.xlsx")
    check(False, "a file that is no workbook is refused")
except Thrown as error:
    check("not an Excel workbook" in str(error), "a file that is no workbook is refused", str(error))
print("the upload: a report a week on the run, no pay until the run is submitted, made again without paying twice")


# ── 5. A report, and the run paying ──────────────────────
def report(**values):
    base = {"doctype": "Daily Production Report", "report_date": D(2026, 11, 4), "section": "Per Piece", "branch": "PET",
            "company": "LPL", "shift": "Day", "source": "Entered", "lines": [], "arrears": [], "looms_ot": []}
    base.update(values)
    return site().get_doc(base)


s = populated()
for values, needle, why in (
        ({"arrears": [{"employee": "E1", "amount": 10}]}, "Arrears are entered as Additional Salary, which the weekly payroll pays: take them off this report",
         "a new Per Piece report takes no arrears: they are entered as Additional Salary (Luuka, 11 Nov 2026)"),
        ({"section": "Per Meter", "arrears": [{"employee": "E1", "amount": 10}]}, "Arrears are entered as Additional Salary, which the weekly payroll pays: take them off this report",
         "nor a Per Meter one"),
        ({"looms_ot": [{"employee": "E1", "amount": 10}]}, "A Per Piece report has no Looms OT: enter what is owed as "
                                                          "Additional Salary.", "a Per Piece report has no Looms OT")):
    try:
        report(**values).insert()
        check(False, "a report: %s" % why)
    except Thrown as error:
        check(needle in str(error), "a report: %s" % why, str(error))
s.rows("Output Rate")[0]["salary_component"] = "Bag Pay"
s.add("Salary Component", name="Bag Pay", type="Earning", depends_on_payment_days=0)
typed = report(lines=[{"employee": "E1", "size": "BAG 200", "output": 2}, {"employee": "E1", "size": "BAG 180", "output": 1}])
typed.docstatus = 1
typed.insert()
check(not pay(s), "a Per Piece report writes no pay by itself: its week's run pays it", pay(s))
pay_run("RUN-W")
check(pay(s) == {("E1", "Bag Pay", D(2026, 11, 4)): 400.0, ("E1", "Per Piece Earnings", D(2026, 11, 4)): 180.0},
      "a category whose Output Rate names an earning is paid under it; the others under Per Piece Earnings", pay(s))
s = populated()
next(row for row in s.rows("Salary Component") if row.name == "Per Piece Earnings")["depends_on_payment_days"] = 1
cut = report(lines=[{"employee": "E1", "size": "BAG 200", "output": 2}])
cut.docstatus = 1
cut.insert()
try:
    pay_run("RUN-W")
    check(False, "an earning cut by payment days is refused: a casual's pieces are what they made")
except Thrown as error:
    check("Per Piece Earnings is cut by payment days" in str(error) and not pay(s),
          "an earning cut by payment days is refused: a casual's pieces are what they made", str(error))
s = populated()
s.add("Salary Slip", name="SS-WEEK", employee="E1", docstatus=1, payroll_frequency="Weekly", start_date=D(2026, 10, 29),
      end_date=D(2026, 11, 4))
late = report(lines=[{"employee": "E1", "size": "BAG 200", "output": 2}])
late.docstatus = 1
late.insert()
try:
    pay_run("RUN-W")
    check(False, "a run for a week a submitted slip already paid is refused: its pay would never be counted")
except Thrown as error:
    check("SS-WEEK has already paid E1's week of 04-Nov-2026" in str(error) and not pay(s),
          "a run for a week a submitted slip already paid is refused: its pay would never be counted", str(error))
s = populated()
s.unassignable["E1"] = "joined after the day"
unassigned = report(lines=[{"employee": "E1", "size": "BAG 200", "output": 2}])
unassigned.docstatus = 1
unassigned.insert()
try:
    pay_run("RUN-W")
    check(False, "a run for someone with no salary assignment is refused, saying why")
except Thrown as error:
    check("No salary assignment for: E1: joined after the day." in str(error) and not pay(s),
          "a run for someone with no salary assignment is refused, saying why", str(error))

# a report that wrote its own pay, before a run paid Per Piece (10 Nov 2026)
s = populated()
s.add("Daily Production Report", name="DPR-OWN", report_date=D(2026, 10, 28), section="Per Piece", source="Uploaded", branch="PET",
      docstatus=1, lines=[Row(employee="E1", size="BAG 200", output=10, amount=2000.0)])
s.add("Daily Production Report", name="DPR-NEW", report_date=D(2026, 11, 4), section="Per Piece", source="Uploaded", branch="PET",
      docstatus=1, lines=[Row(employee="E1", size="BAG 200", output=4, amount=800.0)])
for name, component, amount in (("ADS-OWN-1", "Per Piece Earnings", 2000.0), ("ADS-OWN-2", "Arrears", 500.0)):
    s.add("Additional Salary", name=name, employee="E1", salary_component=component, amount=amount, payroll_date=D(2026, 10, 28),
          ref_doctype="Daily Production Report", ref_docname="DPR-OWN", docstatus=1, type="Earning", is_recurring=0)
check(P.self_paid(["DPR-OWN", "DPR-NEW"]) == {"DPR-OWN"} and P.self_paid([]) == set(),
      "a report that wrote its own pay, before a run paid Per Piece, is known as such")
pay_run("RUN-W")
check(pay(s) == {("E1", "Per Piece Earnings", D(2026, 10, 28)): 2000.0, ("E1", "Arrears", D(2026, 10, 28)): 500.0,
                 ("E1", "Per Piece Earnings", D(2026, 11, 4)): 800.0},
      "and a run leaves it out: its people are paid already, never twice", pay(s))
s.add("Salary Slip", name="SS-TOOK", employee="E1", docstatus=1, payroll_frequency="Weekly", start_date=D(2026, 10, 22),
      end_date=D(2026, 10, 28), earnings=[Row(salary_component="Per Piece Earnings", additional_salary="ADS-OWN-1")])
own = next(row for row in s.rows("Daily Production Report") if row.name == "DPR-OWN")
try:
    s.get_doc("Daily Production Report", "DPR-OWN").cancel()
    check(False, "such a report whose pay a submitted slip took cannot be cancelled, naming the slip")
except Thrown as error:
    check("Cancel the salary slip first" in str(error) and "SS-TOOK" in str(error) and own.docstatus == 1
          and len([row for row in s.rows("Additional Salary") if row.ref_docname == "DPR-OWN"]) == 2,
          "such a report whose pay a submitted slip took cannot be cancelled, naming the slip", str(error))
s.rows("Salary Slip")[0]["docstatus"] = 2
s.get_doc("Daily Production Report", "DPR-OWN").cancel()
check(own.docstatus == 2 and not [row for row in s.rows("Additional Salary") if row.ref_docname == "DPR-OWN"],
      "once that slip is cancelled the report is, and its own pay goes with it")
print("a report: no arrears, no pay of its own; the run: the right earning, refused once paid; the old way let go")

# ── 6. Get Employees ─────────────────────────────────────
s = populated()
P.upload_pieces("RUN-W", "/private/files/pet.xlsx")
check(P.waiting(["E1", "E2", "E7"], D(2026, 10, 22), D(2026, 11, 4)) == set(),
      "a run not yet submitted has paid nobody: the weekly payroll does not wait for them")
pay_run("RUN-W")
check(P.waiting(["E1", "E2", "E7"], D(2026, 10, 22), D(2026, 11, 4)) == {"E1", "E2"},
      "a weekly payroll keeps the Per Piece casuals a submitted run has pay for in its days")
check(P.waiting(["E1", "E2"], D(2026, 11, 5), D(2026, 11, 11)) == set() and P.waiting([], D(2026, 10, 22), D(2026, 11, 4)) == set(),
      "and not for another week's")
s.add("Salary Slip", name="SS-E2", employee="E2", docstatus=1, payroll_frequency="Weekly", start_date=D(2026, 10, 22),
      end_date=D(2026, 11, 4), earnings=[Row(additional_salary=row.name) for row in s.rows("Additional Salary") if row.employee == "E2"])
check(P.waiting(["E1", "E2"], D(2026, 10, 22), D(2026, 11, 4)) == {"E1"},
      "nor one whose piece pay a submitted slip has paid")
s.add("Additional Salary", name="ADS-OWN", employee="E7", salary_component="Per Piece Earnings", amount=100.0,
      payroll_date=D(2026, 11, 3), ref_doctype="Daily Production Report", ref_docname="DPR-OWN", docstatus=1,
      type="Earning", is_recurring=0)
check(P.waiting(["E1", "E7"], D(2026, 10, 22), D(2026, 11, 4)) == {"E1", "E7"},
      "one with pay a report wrote for itself, before a run paid Per Piece, is still kept")
# arrears and anything else owed, entered as Additional Salary (Luuka, 11 Nov 2026)
s.add("Additional Salary", name="ADS-ARR", employee="E8", salary_component="Arrears", amount=250.0,
      payroll_date=D(2026, 11, 1), docstatus=1, type="Earning", is_recurring=0)
s.add("Additional Salary", name="ADS-DED", employee="E9", salary_component="Advance Recovery", amount=50.0,
      payroll_date=D(2026, 11, 1), docstatus=1, type="Deduction", is_recurring=0)
s.add("Additional Salary", name="ADS-REC", employee="E6", salary_component="Bonus", amount=10.0, payroll_date=None,
      from_date=D(2026, 10, 1), to_date=D(2026, 12, 31), docstatus=1, type="Earning", is_recurring=1)
s.add("Additional Salary", name="ADS-OLD", employee="E5", salary_component="Arrears", amount=99.0,
      from_date=D(2026, 1, 1), to_date=D(2026, 9, 30), docstatus=1, type="Earning", is_recurring=1)
check(P.waiting(["E5", "E6", "E8", "E9"], D(2026, 10, 22), D(2026, 11, 4)) == {"E6", "E8"},
      "a casual's arrears entered as Additional Salary keep them, and a recurring one running in the days; a deduction "
      "alone does not, nor a recurring one that ended before", P.waiting(["E5", "E6", "E8", "E9"], D(2026, 10, 22),
                                                                        D(2026, 11, 4)))
print("Get Employees: the casuals with piece pay, arrears or anything else as Additional Salary to be paid")

# ── 6b. The template to download (Luuka, 11 Nov 2026) ─────────────────
check([S.week_title(*days) for days in ((D(2026, 9, 3), D(2026, 9, 9)), (D(2026, 10, 29), D(2026, 11, 4)),
                                        (D(2026, 12, 31), D(2027, 1, 6)), (D(2026, 11, 21), D(2026, 11, 27)))]
      == ["03rd-09th-September-2026", "29th-October-04th-November-2026", "31st-December-2026-06th-January-2027",
          "21st-27th-November-2026"]
      and all(S.week_of(S.week_title(a, b)) == (a, b) for a, b in ((D(2026, 9, 3), D(2026, 9, 9)),
                                                                  (D(2026, 10, 29), D(2026, 11, 4)),
                                                                  (D(2026, 12, 31), D(2027, 1, 6)))),
      "the week titled as Luuka's template titles it, and read back as that week")
blank = S.template(D(2026, 10, 29), D(2026, 11, 4), [200.0, 180.0, 170.0],
                   [{"employee": "E1", "employee_name": "Test Person One"}, {"employee": "LPL-007", "employee_name": "Seventh Case"}])
sheet_out = load_workbook(io.BytesIO(blank)).active
cells = [[cell.value for cell in row] for row in sheet_out.iter_rows(min_row=1, max_row=6)]
check(cells[0][2] == "29th-October-04th-November-2026" and cells[1][1:3] == ["NAME", "NUMBER OF BAGS PACKED"]
      and cells[1][5] == "AMOUNT PER BAG PACKED" and cells[1][8:10] == ["TOTAL AMOUNT", "ARREARS"]
      and cells[2][:5] == ["NO.", None, 200, 180, 170] and cells[3][:2] == ["E1", "Test Person One"]
      and cells[4][:2] == ["LPL-007", "Seventh Case"] and cells[5][1] == "TOTAL"
      and cells[3][5] == '=IF(C4="",0,C4*C$3)' and cells[3][8] == "=SUM(F4:H4)",
      "the template is Luuka's own layout: the week, NAME, the bags and amounts at each price, the totals, ARREARS, "
      "each person's employee number in NO., the amounts adding up as the bags are typed", cells)
odd = load_workbook(io.BytesIO(S.template(D(2026, 10, 29), D(2026, 11, 4), [200.0],
                                          [{"employee": "=E1", "employee_name": "=HYPERLINK(\"x\")"}]))).active
check(odd["A4"].data_type == "s" and odd["B4"].data_type == "s" and odd["A4"].value == "=E1",
      "an employee number or a name that begins with = stays text, never a formula")
filled = load_workbook(io.BytesIO(blank))
filled.active["C4"], filled.active["D5"] = 10, 3
again_out = io.BytesIO()
filled.save(again_out)
round_trip = O.take_pieces(S.read(again_out.getvalue())["weeks"], PEOPLE, SIZES, RATES, PERIOD, "PET")
check(round_trip["work"] == {("E1", D(2026, 11, 4), "BAG 200"): (10.0, 200.0, "'Sheet1', row 4"),
                             ("E7", D(2026, 11, 4), "BAG 180"): (3.0, 180.0, "'Sheet1', row 5")}
      and not round_trip["problems"],
      "filled in and uploaded, it pays each person by the number it carries", round_trip)
download = read("hrms_addon", "hrms_addon", "piece_pay.py")
for needle, why in (
    ("@frappe.whitelist()\ndef download_pieces(run):", "the run's download is a method the form calls"),
    ('doc.check_permission("read")', "by one who may read the run"),
    ("if not piece_sheet.WEEK_DAYS[0] <= (end - start).days + 1 <= piece_sheet.WEEK_DAYS[1]:",
     "for one week, as the upload reads one"),
    ("rules.work_unit_on(seat[\"rates\"], end)", "each category's price on the week's last day"),
    ('filters = {"custom_pay_category": rules.PER_PIECE, "status": ["!=", "Inactive"], "date_of_joining": ["<=", end]}',
     "the Per Piece casuals on staff that week"),
    ('filters["branch"] = branch', "of the run's plant"),
    ("if not row.relieving_date or getdate(row.relieving_date) >= start", "not gone before it"),
):
    check(needle in download, "piece_pay.download_pieces: %s" % why, needle)

# ── 7. Wiring ────────────────────────────────────────────
events = hooks["doc_events"]["Daily Production Report"]
check(events["validate"] == ["hrms_addon.hrms_addon.output_pay.report_validate", "hrms_addon.hrms_addon.piece_pay.report_validate"]
      and events["on_submit"] == "hrms_addon.hrms_addon.output_pay.report_on_submit"
      and events["on_cancel"] == ["hrms_addon.hrms_addon.piece_pay.report_on_cancel",
                                  "hrms_addon.hrms_addon.output_pay.report_on_cancel"],
      "a report is priced before its arrears are checked; its submit writes no pay; a cancel lets go of pay it wrote "
      "itself first", events)
meta = json.load(open(os.path.join(APP, "doctype", "daily_production_report", "daily_production_report.json"), encoding="utf-8"))
fields = {field["fieldname"]: field for field in meta["fields"]}
check(fields["arrears"]["fieldtype"] == "Table" and fields["arrears"]["options"] == "Daily Production Overtime"
      and fields["total_arrears"].get("read_only") == 1
      and fields["arrears_section"]["depends_on"] == "eval:doc.section == 'Per Piece' && (doc.arrears || []).length"
      and meta["field_order"].index("arrears") < meta["field_order"].index("totals_section")
      and set(meta["field_order"]) == set(fields),
      "the report keeps the arrears it had from before, shown only where there are some, every field placed")
run_meta = json.load(open(os.path.join(APP, "doctype", "output_pay_run", "output_pay_run.json"), encoding="utf-8"))
run_fields = {field["fieldname"]: field for field in run_meta["fields"]}
piece, meter = "eval:doc.section == 'Per Piece'", "eval:doc.section != 'Per Piece'"
check(all(run_fields[name].get("mandatory_depends_on") == piece and run_fields[name].get("read_only_depends_on") == meter
          and not run_fields[name].get("read_only") for name in ("from_date", "to_date"))
      and all(run_fields[name].get("mandatory_depends_on") == meter and run_fields[name].get("depends_on") == meter
              and not run_fields[name].get("reqd") for name in ("year", "month")),
      "a Per Piece run is given its week, From and To; a Per Meter run its month, as before")
arrears_meta = json.load(open(os.path.join(APP, "doctype", "output_pay_arrears", "output_pay_arrears.json"), encoding="utf-8"))
some = "eval:doc.section == 'Per Piece' && (doc.arrears || []).length"
check(run_fields["arrears"]["options"] == "Output Pay Arrears" and run_fields["arrears_section"]["depends_on"] == some
      and run_fields["total_arrears"]["depends_on"] == some and arrears_meta.get("istable") == 1
      and [field["label"] for field in arrears_meta["fields"] if field["fieldname"] == "amount"] == ["Arrears"]
      and set(run_meta["field_order"]) == set(run_fields) and not run_fields["uploaded_sheet"].get("depends_on")
      and os.path.exists(os.path.join(APP, "doctype", "output_pay_arrears", "output_pay_arrears.py")),
      "the run keeps any arrears a draft took from before, shown only where there are some, and keeps its sheet")
seat_meta = json.load(open(os.path.join(APP, "doctype", "output_pay_employee", "output_pay_employee.json"), encoding="utf-8"))
check([field["label"] for field in seat_meta["fields"] if field["fieldname"] == "arrears"] == ["Arrears"],
      "each person's arrears show beside their work")
script = read("hrms_addon", "hrms_addon", "doctype", "output_pay_run", "output_pay_run.js")
for needle, why in (('"hrms_addon.hrms_addon.piece_pay.upload_pieces"', "the button asks the method the server whitelists"),
                    ('"hrms_addon.hrms_addon.piece_pay.upload_pieces",\n\t\t\t\t\t{ run: frm.doc.name, file_url: file.file_url },',
                     "for this run"),
                    ('if (frm.doc.section === "Per Piece") {', "on a Per Piece run"),
                    ("if (frm.doc.docstatus !== 0 || frm.is_new()) return;", "a draft one"),
                    ("if (frm.doc.from_date && frm.doc.to_date) {", "with its dates"),
                    ('frm.add_custom_button(__("Download Per Piece Sheet"), () =>', "the week's template, to fill in"),
                    ('"/api/method/hrms_addon.hrms_addon.piece_pay.download_pieces?run=" +', "from this run"),
                    ('restrictions: { allowed_file_types: [".xlsx"] }', "an Excel workbook only"),
                    ('frm.add_custom_button(__("Upload Per Piece Sheet"), () => ha_upload_piece_sheet(frm));',
                     "named as Luuka call it")):
    check(needle in script, "the run's button: %s" % why, needle)
payroll_script = read("hrms_addon", "public", "js", "payroll_entry.js")
check("Per Piece Sheet" not in payroll_script and "piece_pay" not in payroll_script and "ha_weekly_pieces" not in payroll_script,
      "the payroll has no Per Piece sheet any more: the pay is worked out apart from it (Luuka, 11 Nov 2026)")
glue = read("hrms_addon", "hrms_addon", "piece_pay.py")
check('@frappe.whitelist(methods=["POST"])\ndef upload_pieces(run, file_url):' in glue and "doc.check_permission(\"write\")" in glue
      and "def report_on_submit" not in glue and "output_pay._fill(doc)" in glue and '"sheet_run": doc.name' in glue,
      "the upload is a POST, by one who may change the run, which it fills; a report's submit writes no pay")
check('common = {"employee": ["in", employees], "docstatus": 1, "type": "Earning"}' in glue
      and "dict(common, is_recurring=0, payroll_date=[\"between\", [first, last]])" in glue
      and "dict(common, is_recurring=1, from_date=[\"<=\", last]," in glue,
      "the weekly payroll waits for any Additional Salary earning in its days: a run's pay, a report's own from before, "
      "arrears entered by HR")
print("wiring: the hooks, the report's arrears, the run's week and its button, the payroll without one")

print()
print("FAILED: %d" % len(fail) if fail else "ALL PER PIECE CHECKS PASSED")
sys.exit(1 if fail else 0)
