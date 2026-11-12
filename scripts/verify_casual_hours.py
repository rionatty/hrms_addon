"""Checks for the Casual Hours Sheet: one plant's casuals paid by the hour, a week's totals each, approved by its
General Manager before the weekly payroll pays it (Luuka, 12 Nov 2026: "the team captures total number of hours
worked and overtime how can we make it easy for them"; "working hour is 10 ... no maximum overtime hours for
casuals"; "build it").

Runs without a bench: casual_hours_rules.py and casual_hours_approval.py are loaded on their own, casual_hours.py
on a stand-in site, and the doctypes, the hooks and the form read as files. How the weekly slip pays a sheet is
walked in scripts/verify_weekly_pay.py (4b).

    python scripts/verify_casual_hours.py
"""
import datetime
import importlib.util
import io
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
D = datetime.date
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else "   <- %s" % (detail,))
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["hrms_addon.hrms_addon." + name] = module
    return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
R = load("casual_hours_rules")  # proves it has no Frappe import
A = load("casual_hours_approval")
WR = load("weekly_pay_rules")
OR = load("overtime_rules")
print("loaded casual_hours_rules.py and casual_hours_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────
check(R.number(None) == (0.0, None) and R.number("") == (0.0, None) and R.number(" 7.5 ") == (7.5, None)
      and R.number(12) == (12.0, None), "a cell is hours: nothing, a point, a whole number")
check(R.number("1,5")[0] is None and "with a point" in R.number("1,5")[1] and R.number("ten")[0] is None,
      "a comma is never read as a point, nor a word as hours", (R.number("1,5"), R.number("ten")))
template = [list(R.TEMPLATE_HEADS),
            ["LPC100", "Casual One", 52, 6, 6],
            ["LPC101", "Casual Two", None, None, None],
            ["LPC102", "Casual Three", "48", "1,5", None],
            ["LPC103", "Casual Four", 40, 0, 5]]
found = R.read_rows(template)
check([(row["employee"], row["hours"], row["overtime"], row["days"]) for row in found["rows"]]
      == [("LPC100", 52.0, 6.0, 6.0), ("LPC103", 40.0, 0.0, 5.0)]
      and found["problems"] == ["Row 4, LPC102: write 1,5 with a point, not a comma."],
      "the template read: a person with nothing is left out, a bad cell said with its row", found)
master = [["LUUKA PLASTICS LTD (CASUALS)"], ["CASUAL MASTER PAYROLL"], [],
          ["SrNo", "PAYROLL NO", "COUNT OF EMPLOYEE", "DEPARTMENTNAME", "HOURS WORKED", "WAGE RATE", "OT HOURS"],
          [], [1, "LPC 90017", "A Person", "PET", 60, 857, 4], [2, "LPC200", "B Person", "PET", 0, 857, 0],
          [None, "TOTAL", None, None, 60, None, 4]]
found = R.read_rows(master)
check([(row["employee"], row["name"], row["hours"], row["overtime"], row["line"]) for row in found["rows"]]
      == [("LPC 90017", "A Person", 60.0, 4.0, 6)],
      "the team's own sheet read too: its headings on row 4, the names from COUNT OF EMPLOYEE, the TOTAL line no one",
      found)
try:
    R.read_rows([["A", "B"], [1, 2]])
    check(False, "a sheet with no headings is refused")
except ValueError as error:
    check("PAYROLL NO and HOURS WORKED" in str(error), "a sheet with no headings is refused, saying what it wants", error)
# the casual master payroll's own layout (Luuka, Sep 2026): the hourly and the Per Piece casuals on one sheet, a Per
# Piece casual with no hours, and the overtime as OT1-AMOUNT, an amount
heads = ["SrNo", "PAYROLL NO", "COUNT OF EMPLOYEE", "DEPARTMENTNAME", "HOURS WORKED", "WAGE RATE", "BASIC",
         "PIECE RATE AMT1", "PIECE RATE AMT2", "PIECE RATE AMT3", "OT1-AMOUNT", "ARREARS", "GROSS AMOUNT",
         "SALARY ADVANCE", "NETTPAY"]
piece = [1, "LPC90001", "A Piece", "MOULDING", 0, 0, 0, 30000, 4000, 0, 0, 0, 34000, 0, 34000]
hourly = [2, "LPC90002\n", "B Hourly", "MOULDING", 50, 900, 45000, 0, 0, 0, 13500, 0, 58500, 0, 58500]
master = [["LUUKA PLASTICS LTD (CASUALS)"], ["CASUAL MASTER PAYROLL"], [], heads, [], piece, hourly]
try:
    R.read_rows(master)
    check(False, "overtime given only as an amount is refused")
except ValueError as error:
    check("OT1-AMOUNT, an amount, and no overtime hours" in str(error) and "OVERTIME HOURS column" in str(error),
          "overtime given only as an amount is refused, not read as none: it would go unpaid", error)
quiet = [list(row) for row in master]
quiet[-1][10] = 0
found = R.read_rows(quiet)
check([(row["employee"], row["hours"], row["overtime"]) for row in found["rows"]] == [("LPC90002", 50.0, 0.0)]
      and not found["problems"],
      "with no overtime that week it reads: the Per Piece casual's nought hours leave them out, the piece amounts "
      "are no overtime, the cell's line break is no part of the ID", found)
told = [list(row) for row in master]
told[3], told[5], told[6] = heads + ["OT HOURS"], piece + [0], hourly + [10]
found = R.read_rows(told)
check([(row["employee"], row["hours"], row["overtime"]) for row in found["rows"]] == [("LPC90002", 50.0, 10.0)],
      "with OT HOURS beside the amount, the hours are read and the amount left to the payroll", found)
kinds = {head: R._overtime_kind(R._head(head)) for head in (
    "OT1-AMOUNT", "OVERTIME AMT", "TOTAL OT AMOUNT", "Overtime Pay", "O/T Amount", "OT HOURS", "OT1-HRS", "OT2 HOURS",
    "OVERTIME", "OT RATE", "Overtime Type", "OTHER AMOUNT", "PIECE RATE AMT1", "NETTPAY", "BASIC")}
check(kinds == {"OT1-AMOUNT": "amount", "OVERTIME AMT": "amount", "TOTAL OT AMOUNT": "amount", "Overtime Pay": "amount",
                "O/T Amount": "amount", "OT HOURS": "hours", "OT1-HRS": "hours", "OT2 HOURS": "hours",
                "OVERTIME": "hours", "OT RATE": None, "Overtime Type": None, "OTHER AMOUNT": None,
                "PIECE RATE AMT1": None, "NETTPAY": None, "BASIC": None},
      "overtime as money or as hours, by its heading; OTHER AMOUNT, the piece rates, a rate or a type are neither",
      kinds)
# the headings as a sheet may spell them (review of 12 Nov 2026): HRS, dashes, dots, the line break Excel escapes
check([R._head(head) for head in ("OT1-HRS", "Payroll No.", "HRS WORKED", "Overtime\nHours", "OT_x000D_\nHOURS",
                                  "o/t hrs", "EMP. ID")]
      == ["OT1 HOURS", "PAYROLL NO", "HOURS WORKED", "OVERTIME HOURS", "OT HOURS", "OT HOURS", "EMP ID"],
      "a heading read as words: HRS as HOURS, dashes, dots, line breaks and O/T aside",
      [R._head(head) for head in ("OT1-HRS", "Payroll No.", "HRS WORKED", "Overtime\nHours", "OT_x000D_\nHOURS",
                                  "o/t hrs", "EMP. ID")])
for spelt in ("OT HRS", "OT1 HOURS", "OT1-HRS", "OVERTIME HRS", "Overtime Hours"):
    found = R.read_rows([["PAYROLL NO", "HOURS WORKED", spelt], ["LPC90002", 50, 6]])
    check([(row["hours"], row["overtime"]) for row in found["rows"]] == [(50.0, 6.0)],
          "%s is read as the overtime hours" % spelt, found)
# the casual master payroll's own IDs: Excel keeps a line break typed into the cell as _x000D_ (Casual week.xlsx)
found = R.read_rows([["PAYROLL NO", "HOURS WORKED"], ["LPC90003_x000D_\n", 60], [" LPC 90004 ", 40], [90005.0, 30],
                     [90006, 20]])
check([row["employee"] for row in found["rows"]] == ["LPC90003", "LPC 90004", "90005", "90006"],
      "an ID read clean: Excel's _x000D_ and the line break gone, a space inside kept, a number as written",
      [row["employee"] for row in found["rows"]])


def refused_sheet(table):
    try:
        R.read_rows(table)
    except ValueError as error:
        return str(error)
    return None


said = refused_sheet([["PAYROLL NO", "HOURS WORKED", "OT1-AMOUNT", "OT2-AMOUNT"], ["LPC90002", 50, 0, 2400]])
check(said and said.startswith("The sheet has OT2-AMOUNT, an amount, and no overtime hours"),
      "an amount in any overtime money column, not only the first, wants the hours; the heading said as written", said)
said = refused_sheet([["PAYROLL NO", "HOURS WORKED", "OT1-AMOUNT"], ["LPC90002", 50, "13,500"]])
check(said and "OT1-AMOUNT, an amount" in said, "an amount written as text with its comma is an amount", said)
said = refused_sheet([["PAYROLL NO", "HOURS WORKED", "OVERTIME HOURS", "OT2 HOURS"], ["LPC90002", 50, 6, 4]])
check(said == "The sheet has OT2 HOURS as well as OVERTIME HOURS: one column of overtime hours is read. Put each "
              "casual's overtime hours for the week in OVERTIME HOURS.",
      "a second column of overtime hours is refused, not left unpaid", said)
said = refused_sheet([["PAYROLL NO", "HOURS WORKED", "OVERTIME 1 HOURS"], ["LPC90002", 50, 6]])
check(said == "The sheet's OVERTIME 1 HOURS is not a heading the upload reads: name that column OVERTIME HOURS.",
      "overtime hours under a heading not read are refused, not read as none", said)
check(refused_sheet([["PAYROLL NO", "HOURS WORKED", "OVERTIME HOURS", "OT1-AMOUNT", "OT RATE"],
                     ["LPC90002", 50, 6, 13500, 1.5]]) is None
      and refused_sheet([["PAYROLL NO", "HOURS WORKED", "OT1-AMOUNT", "OT2 HOURS"], ["LPC90002", 50, 0, 0],
                         ["TOTAL", 50, 99, 99]]) is None,
      "an amount beside the hours read, a rate, and columns with nothing in them stop nothing; nor does a total line")
found = R.read_rows([["PAYROLL NO", "HOURS WORKED", "OVERTIME HOURS"], ["LPC90002", 60, 13500]])
check(found["rows"] and R.row_errors(found["rows"][0], 7) == ["13560 hours in all is more than 7 days have"],
      "an amount put in the overtime hours column is caught by the hours a week has: overtime has no cap, a week has",
      R.row_errors(found["rows"][0], 7) if found["rows"] else found)
# a workbook: the sheet it was saved on, else the only one with the headings (the worksheet's MASTER PAYROLL tab)
week = [["PAYROLL NO", "HOURS WORKED"], ["LPC90002", 50]]
last_week = [["PAYROLL NO", "HOURS WORKED"], ["LPC90002", 40]]
notes = [["Kawempe casuals"], ["see the next tab"]]
check(R.read_book([("WEEK", week), ("PREVIOUS", last_week)])["rows"][0]["hours"] == 50.0
      and R.read_book([("LEFT", notes), ("MASTER PAYROLL", week)])["rows"][0]["hours"] == 50.0,
      "a workbook is read from the sheet it was saved on, else from its only sheet with the headings")
try:
    R.read_book([("LEFT", notes), ("MASTER PAYROLL", week), ("PREVIOUS", last_week)])
    check(False, "two sheets with headings, saved on neither, are refused")
except ValueError as error:
    check("MASTER PAYROLL, PREVIOUS, each with PAYROLL NO and HOURS WORKED" in str(error),
          "two sheets with headings, saved on neither, are refused: last week's could be read for this one", error)
try:
    R.read_book([("LEFT", notes)])
    check(False, "a workbook with no headings is refused")
except R.NoHeadings as error:
    check("PAYROLL NO and HOURS WORKED" in str(error), "a workbook with no headings anywhere is refused, as a sheet is")
check(R.sheet_errors(None, D(2026, 11, 4)) == ["Say the week: its From and To."]
      and R.sheet_errors(D(2026, 11, 4), D(2026, 11, 1)) == ["To is before From."]
      and R.sheet_errors(D(2026, 10, 29), D(2026, 11, 4), D(2026, 11, 5)) == [],
      "a week: From and To, in that order")
check(R.sheet_errors(D(2026, 10, 20), D(2026, 11, 4)) == ["A sheet is one week: at most 7 days."]
      and R.sheet_errors(D(2026, 11, 5), D(2026, 11, 11), D(2026, 11, 8))
      == ["The week ends on 11 Nov 2026: hours are entered once they are worked."],
      "at most seven days, and none still to come", R.sheet_errors(D(2026, 11, 5), D(2026, 11, 11), D(2026, 11, 8)))
check(R.row_errors({"hours": 70, "overtime": 40, "days": 7}, 7) == [],
      "seven ten-hour days, and overtime with no cap: a casual's overtime has no maximum (Luuka, 12 Nov 2026)")
check(R.row_errors({"hours": 70.5}, 7) == ["70.5 hours is more than 7 days of 10 hours: put the rest under Overtime Hours"]
      and R.row_errors({"hours": 33}, 3, standard=11) == [],
      "no more ordinary hours than the week has standard days: the rest is overtime",
      R.row_errors({"hours": 70.5}, 7))
check(R.row_errors({"hours": -1}, 7) == ["hours and days cannot be less than nothing"]
      and R.row_errors({"days": 8}, 7) == ["8 days worked in a week of 7 days"], "nothing below nought, no eighth day")
check(R.pay(50, 6, 2500, 1.5) == {"hours_pay": 125000.0, "overtime_pay": 22500.0, "total_pay": 147500.0},
      "the hours at the rate, the overtime at the rate times its multiplier", R.pay(50, 6, 2500, 1.5))
check(R.overlap(D(2026, 10, 29), D(2026, 11, 4), D(2026, 11, 4), D(2026, 11, 10))
      and not R.overlap(D(2026, 10, 29), D(2026, 11, 4), D(2026, 11, 5), D(2026, 11, 11)),
      "two weeks overlap when they share a day")
check(R.in_spans(D(2026, 11, 1), [(D(2026, 10, 29), D(2026, 11, 4))]) and not R.in_spans(D(2026, 11, 5), [(D(2026, 10, 29), D(2026, 11, 4))]),
      "a day inside a sheet's week is the sheet's")
check(R.default_week(D(2026, 11, 4), D(2026, 11, 12)) == (D(2026, 11, 5), D(2026, 11, 11))
      and R.default_week(D(2026, 11, 4), D(2026, 11, 8)) == (D(2026, 11, 5), D(2026, 11, 7))
      and R.default_week(None, D(2026, 11, 12)) == (D(2026, 11, 5), D(2026, 11, 11)),
      "a new sheet is the week after the plant's last, never past yesterday; the first, the seven days to yesterday")
rows = [{"sheet": "S2", "to_date": D(2026, 11, 11), "hours": 40}, {"sheet": "S1", "to_date": D(2026, 11, 4), "hours": 50},
        {"sheet": "S0", "to_date": D(2026, 10, 28), "hours": 30}, {"sheet": "S3", "to_date": D(2026, 11, 4), "hours": 0}]
check([row["sheet"] for row in R.slip_rows(rows, {"S0"}, D(2026, 11, 4))] == ["S1"],
      "a slip pays the weeks ending by its End that no slip paid, and none that gives nothing")
days, overtime = R.day_rows([{"sheet": "S1", "to_date": D(2026, 11, 4), "hours": 50, "overtime": 6, "days": 5,
                              "overtime_type": "Casual OT"}])
check(days == [{"attendance_date": D(2026, 11, 4), "status": "Present", "hours": 50.0, "hours_sheet": "S1", "days_worked": 5.0}]
      and overtime == [{"attendance_date": D(2026, 11, 4), "status": "Present", "hours": 6.0, "overtime_type": "Casual OT",
                        "hours_sheet": "S1"}],
      "a sheet's row is the slip's day and overtime, dated the week's last day; the overtime says its sheet, which "
      "has it paid at the weekday rate", (days, overtime))
print("rules: the team's sheet read, the week and the hours checked, what a row comes to, what a slip pays")

# ── 2. The approval ───────────────────────────────────
check(A.next_states(A.DRAFT, ["HR User"]) == [(A.SEND, A.PENDING_GM)] and A.next_states(A.DRAFT, ["General Manager"]) == [],
      "HR send the week to the General Manager; the General Manager does not fill it")
check(A.next_states(A.PENDING_GM, ["General Manager"]) == [(A.APPROVE, A.APPROVED), (A.RETURN, A.DRAFT)]
      and A.next_states(A.PENDING_GM, ["HR User"]) == [],
      "the General Manager approves or returns it; an HR Officer cannot approve their own week")
check(A.next_states(A.PENDING_GM, ["HR Manager"]) == [(A.APPROVE, A.APPROVED), (A.RETURN, A.DRAFT)]
      and A.next_states(A.APPROVED, ["HR Manager"]) == [(A.CANCEL, A.CANCELLED)]
      and A.next_states(A.APPROVED, ["General Manager"]) == [],
      "the HR Manager may stand in for an absent General Manager, and alone cancels")
check({state["state"]: state.get("doc_status", "0") for state in A.STATES}
      == {A.DRAFT: "0", A.PENDING_GM: "0", A.APPROVED: "1", A.CANCELLED: "2"}
      and not any(state["send_email"] for state in A.STATES),
      "Approved submits it, Cancelled cancels it; nobody is emailed by role: the plant's own people are told")
check(A.step_errors(A.PENDING_GM, A.DRAFT, {}) == ["Write in Return Remarks what must be put right."]
      and A.step_errors(A.PENDING_GM, A.DRAFT, {"return_remarks": "Line 4 is short."}) == [],
      "a return says what to put right")
said = A.step_errors(A.DRAFT, A.PENDING_GM, {"people": 0, "unrated": ["LPC1"], "no_type": ["LPC2 (no type)"]})
check(len(said) == 3 and "Nobody is on this sheet" in said[0] and "No hourly rate" in said[1] and "LPC1" in said[1]
      and "no Overtime Type lists LPC2" in said[2],
      "nothing goes to the General Manager with nobody on it, a rate missing or overtime with no type", said)
check(A.step_errors(A.PENDING_GM, A.APPROVED, {"people": 3}) == [], "a week in order is approved")
said = A.step_errors(A.PENDING_GM, A.APPROVED, {"people": 3, "paid": ["LPC1 (Sal Slip/LPC1/00001)"]})
check(said == ["Some of these days were paid already from the attendance for LPC1 (Sal Slip/LPC1/00001): take them off "
               "this sheet, or cancel that pay first, or the week is paid twice."],
      "a week some of whose days were paid another way is not approved", said)
stamps = A.compute_stamps(A.DRAFT, A.PENDING_GM, "hro@x", "T1", {})
stamps = A.compute_stamps(A.PENDING_GM, A.APPROVED, "gm@x", "T2", stamps)
check((stamps["prepared_by"], stamps["approved_by"]) == ("hro@x", "gm@x")
      and A.compute_stamps(A.PENDING_GM, A.DRAFT, "gm@x", "T3", stamps) == dict.fromkeys(A.ALL_STAMP_FIELDS),
      "who prepared it and who approved it are signed; a return clears both", stamps)
print("approval: HR fill and send, the plant's General Manager approves or returns, the HR Manager cancels")

# ── 3. The glue, on a stand-in site ───────────────────
TODAY = D(2026, 11, 12)


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


def matches(row, filters):
    for field, want in (filters or {}).items():
        have = row.get(field)
        if not isinstance(want, (list, tuple)):
            if have != want and as_date(have) != as_date(want) if isinstance(want, D) else have != want:
                return False
            continue
        op, value = want[0], want[1]
        if op == "between" and not (as_date(have) and as_date(value[0]) <= as_date(have) <= as_date(value[1])):
            return False
        if op == "in" and have not in value:
            return False
        if op == "!=" and (have or "") == (value or ""):
            return False
        if op == "is" and bool(have) != (value == "set"):
            return False
        if op in ("<", "<=", ">", ">="):
            left, right = (as_date(have), as_date(value)) if as_date(value) else (have, value)
            if left is None or not {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]:
                return False
    return True


class Site:
    def __init__(self):
        self.tables, self.told, self.saved = {}, [], []

    def add(self, doctype, **values):
        self.tables.setdefault(doctype, []).append(Row(values))

    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, **kwargs):
        rows = [row for row in self.tables.get(doctype, []) if matches(row, filters)]
        if order_by:
            field, way = (order_by.split() + ["asc"])[:2]
            rows = sorted(rows, key=lambda row: str(row.get(field) or ""), reverse=way == "desc")
        if pluck:
            return [row.get(pluck) for row in rows]
        return [Row({field: row.get(field) for field in (fields or row.keys())}) for row in rows]

    def get_value(self, doctype, filters, fieldname, order_by=None, as_dict=False):
        found = self.get_all(doctype, filters if isinstance(filters, dict) else {"name": filters}, order_by=order_by)
        return found[0].get(fieldname) if found else None


SITE = [None]
frappe = types.ModuleType("frappe")
frappe._ = lambda text, *args, **kwargs: text
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if not args or not callable(args[0]) else args[0]
frappe.throw = lambda message, title=None, *args, **kwargs: (_ for _ in ()).throw(Thrown(message))
frappe.has_permission = lambda *args, **kwargs: True
frappe.get_all = lambda *args, **kwargs: SITE[0].get_all(*args, **kwargs)
frappe.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: SITE[0].get_value(*args, **kwargs))
frappe.session = types.SimpleNamespace(user="hro@luuka")
frappe.response = {}
frappe.get_cached_doc = lambda doctype, name: types.SimpleNamespace(
    as_dict=lambda: Row(next(row for row in SITE[0].tables.get(doctype, []) if row.name == name)))
utils = types.ModuleType("frappe.utils")
utils.flt = lambda value, precision=None: float(value or 0)
utils.getdate = as_date
utils.today = lambda: TODAY.isoformat()
utils.now_datetime = lambda: datetime.datetime(2026, 11, 12, 9, 0)
xlsxutils = types.ModuleType("frappe.utils.xlsxutils")
MADE = []


def make_xlsx(data, sheet_name):
    MADE.append((sheet_name, data))
    return io.BytesIO(b"xlsx")


xlsxutils.make_xlsx = make_xlsx
FILES = {}
output_pay = types.ModuleType("hrms_addon.hrms_addon.output_pay")
output_pay.settings = lambda: {"standard_hours": 10}
output_pay._file_bytes = lambda file_url: FILES[file_url]
people = types.ModuleType("hrms_addon.hrms_addon.people")
people.people_for = lambda role, branch, department=None: ["gm.%s@luuka" % (branch or "").lower()] if role == "General Manager" else []
people.hr_officers = lambda branch, department=None: ["hro@luuka"]
people.notify = lambda users, doctype, name, subject, message=None: SITE[0].told.append(("notify", tuple(users), subject))
people.assign = lambda doctype, name, users, description, date=None, notify=0: SITE[0].told.append(("assign", tuple(users)))
people.withdraw = lambda doctype, name, users: SITE[0].told.append(("withdraw", tuple(users)))
overtime = types.ModuleType("hrms_addon.hrms_addon.overtime")
overtime._types_for = lambda: "types"
TYPED_AS = []


def type_on(employee, day, types=None, kind=None):
    TYPED_AS.append(kind)
    return ("Casual OT", None) if employee in SITE[0].typed else (None, "no Overtime Type lists them")


overtime.type_on = type_on
# the week's last day is a public holiday, as 11 Nov 2026 is taken to be here: the week's overtime is still a weekday's
overtime.day_kind = lambda employee, day: OR.PUBLIC_HOLIDAY
weekly_pay = types.ModuleType("hrms_addon.hrms_addon.weekly_pay")
weekly_pay.standard_rate = lambda: SITE[0].standard_rate
weekly_pay.rate_history = lambda employees, until=None: {row.employee: [row] for row in SITE[0].tables.get("Hourly Rate", [])
                                                         if row.employee in employees}
# the verified Attendance Verifications, as attendance_verification.verified_sheets gives them: each with its people
attendance_verification = types.ModuleType("hrms_addon.hrms_addon.attendance_verification")


def verified_sheets(first, last, company=None, employees=None):
    found = []
    for sheet in getattr(SITE[0], "verified", []):
        if as_date(sheet["from_date"]) <= as_date(last) and as_date(sheet["to_date"]) >= as_date(first):
            people = [who for who in sheet["employees"] if employees is None or who in employees]
            found.append(Row(sheet, employees=people))
    return found


attendance_verification.verified_sheets = verified_sheets
sys.modules.update({"frappe": frappe, "frappe.utils": utils, "frappe.utils.xlsxutils": xlsxutils,
                    "hrms_addon.hrms_addon.output_pay": output_pay, "hrms_addon.hrms_addon.people": people,
                    "hrms_addon.hrms_addon.overtime": overtime, "hrms_addon.hrms_addon.overtime_rules": OR,
                    "hrms_addon.hrms_addon.weekly_pay": weekly_pay,
                    "hrms_addon.hrms_addon.attendance_verification": attendance_verification})
app.attendance_verification = attendance_verification
G = load("casual_hours")


class Sheet:
    """A Casual Hours Sheet, as a document: its rows are Rows, and save validates it as Frappe would."""

    def __init__(self, before=None, **values):
        self.__dict__.update(dict(doctype="Casual Hours Sheet", name="HR-CHS-NEW", company="LPL", branch="Kawempe",
                                  docstatus=0, workflow_state="Draft", owner="hro@luuka"))
        self.__dict__.update(values)
        self.rows = [Row(row, idx=n + 1) for n, row in enumerate(values.get("rows", []))]
        self._before = before
        self.saved = 0

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def set(self, key, value):
        if key == "rows":
            value = [Row(row, idx=n + 1) for n, row in enumerate(value)]
        self.__dict__[key] = value

    def get_doc_before_save(self):
        return self._before

    def check_permission(self, ptype):
        return True

    def db_set(self, field, value, update_modified=True):
        self.__dict__[field] = value

    def save(self):
        G.sheet_validate(self)
        self.saved += 1


def site():
    s = Site()
    SITE[0] = s
    s.standard_rate, s.typed = 0, {"LPC100", "LPC103"}
    for name, category, branch, number in (("LPC100", "Weekly", "Kawempe", "100"), ("LPC101", "Weekly", "Kawempe", "101"),
                                           ("LPC 90017", "Weekly", "Kawempe", "90017"), ("LPC103", "Weekly", "Kawempe", "103"),
                                           ("LPC200", "Per Piece", "Kawempe", "200"), ("LPC300", "Weekly", "Namanve", "300"),
                                           ("LPC104", "Weekly", "Kawempe", "104")):
        s.add("Employee", name=name, employee_name="Name " + name, custom_pay_category=category, company="LPL",
              branch=branch, employee_number=number, status="Active", relieving_date=None)
    for name in ("LPC100", "LPC 90017", "LPC103", "LPC300"):
        s.add("Hourly Rate", employee=name, rate=2500, from_date=D(2026, 1, 1))
    # a public holiday's overtime at 2, a weekday's at 1.5
    s.add("Overtime Type", name="Casual OT", standard_multiplier=1.5, applicable_for_public_holiday=1,
          public_holiday_multiplier=2.0)
    return s


s = site()
week = dict(from_date=D(2026, 11, 5), to_date=D(2026, 11, 11))
doc = Sheet(rows=[{"employee": "LPC100", "hours_worked": 52, "overtime_hours": 6, "days_worked": 6},
                  {"employee": "LPC 90017", "hours_worked": 40}], **week)
G.sheet_validate(doc)
first = doc.rows[0]
check((first.rate, first.overtime_type, first.multiplier, first.hours_pay, first.overtime_pay, first.total_pay,
       first.employee_name) == (2500, "Casual OT", 1.5, 130000.0, 22500.0, 152500.0, "Name LPC100"),
      "each row priced: their own rate on the week's last day, their Overtime Type's 1.5, what it comes to",
      dict(first))
check(TYPED_AS and set(TYPED_AS) == {OR.WEEKDAY},
      "the week ends on a public holiday, and its overtime is still a weekday's: the type taken as a weekday's, at 1.5, "
      "not 2", TYPED_AS)
check((doc.total_people, doc.total_hours, doc.total_overtime, doc.total_pay, doc.status) == (2, 92.0, 6.0, 252500.0, "Draft"),
      "the week's totals", (doc.total_people, doc.total_hours, doc.total_overtime, doc.total_pay))


def refused(document):
    try:
        G.sheet_validate(document)
    except Thrown as error:
        return str(error)
    return None


said = refused(Sheet(rows=[{"employee": "LPC200", "hours_worked": 10}, {"employee": "LPC300", "hours_worked": 10},
                           {"employee": "LPC100", "hours_worked": 71}, {"employee": "LPC100", "hours_worked": 1}], **week))
check(said and "LPC200 is not paid by the hour: their Pay Category is Per Piece" in said
      and "LPC300 is at Namanve, not Kawempe: their plant's sheet takes them" in said
      and "LPC100: 71 hours is more than 7 days of 10 hours" in said and "LPC100 is on the sheet twice" in said,
      "a Per Piece casual, another plant's, a week of too many ordinary hours, a person twice: each said", said)
s.add("Casual Hours Sheet", name="HR-CHS-OLD", company="LPL", from_date=D(2026, 11, 8), to_date=D(2026, 11, 14), docstatus=0)
s.add("Casual Hours Row", parent="HR-CHS-OLD", parenttype="Casual Hours Sheet", employee="LPC 90017")
said = refused(Sheet(rows=[{"employee": "LPC 90017", "hours_worked": 10}], **week))
check(said == "LPC 90017 is already on HR-CHS-OLD for some of these days.",
      "a person already on another sheet of those days is refused: each week is entered once, so paid once", said)
s.tables["Casual Hours Sheet"][-1]["docstatus"] = 2
check(refused(Sheet(rows=[{"employee": "LPC 90017", "hours_worked": 10}], **week)) is None,
      "a cancelled sheet takes nobody's week")
said = refused(Sheet(rows=[{"employee": "LPC100", "hours_worked": 10}], from_date=D(2026, 11, 10), to_date=D(2026, 11, 16)))
check(said == "The week ends on 16 Nov 2026: hours are entered once they are worked.", "no week still to come", said)

before = Sheet(rows=[{"employee": "LPC104", "hours_worked": 30}, {"employee": "LPC101", "overtime_hours": 2}], **week)
sending = Sheet(before=before, workflow_state="Pending General Manager",
                rows=[{"employee": "LPC104", "hours_worked": 30}, {"employee": "LPC101", "overtime_hours": 2}], **week)
said = refused(sending)
check(said and "No hourly rate on the week's last day for LPC104; LPC101" in said and "no Overtime Type lists LPC101" in said,
      "it goes to the General Manager only with every rate and Overtime Type in place", said)
s.standard_rate = 2000
s.typed.add("LPC101")
sending = Sheet(before=before, workflow_state="Pending General Manager", return_remarks="old",
                rows=[{"employee": "LPC104", "hours_worked": 30}, {"employee": "LPC101", "overtime_hours": 2}], **week)
G.sheet_validate(sending)
check(sending.rows[0].rate == 2000 and sending.prepared_by == "hro@luuka" and sending.return_remarks is None
      and sending.status == "Pending General Manager"
      and ("notify", ("gm.kawempe@luuka",), "Casual hours of Kawempe, 5 Nov 2026 to 11 Nov 2026: 2 people, 30.0 hours and 2.0 "
                                            "overtime hours to approve.") in s.told,
      "sent: the standard rate where there is none, who prepared it, and the plant's own General Manager told",
      (sending.rows[0].rate, sending.prepared_by, s.told))
frappe.session.user = "gm.kawempe@luuka"
approving = Sheet(before=sending, workflow_state="Approved", prepared_by="hro@luuka",
                  rows=[{"employee": "LPC104", "hours_worked": 30}], **week)
G.sheet_validate(approving)
G.sheet_before_submit(approving)
check(approving.approved_by == "gm.kawempe@luuka" and approving.status == "Approved"
      and ("withdraw", ("gm.kawempe@luuka",)) in s.told
      and any(entry[0] == "notify" and "approved: the weekly payroll pays them" in entry[2] for entry in s.told),
      "approved: signed by the General Manager, their task closed, HR and Payroll told the payroll pays it", s.told)
frappe.session.user = "hro@luuka"
try:
    G.sheet_before_submit(Sheet(workflow_state="Draft", **week))
    check(False, "a plain submit is refused")
except Thrown as error:
    check("General Manager approves the week" in str(error), "a plain submit is refused: only the approval submits it")
s.add("Weekly Pay Day", parent="Sal Slip/LPC104/00001", hours_sheet="HR-CHS-PAID", docstatus=1, employee="LPC104")
try:
    G.sheet_before_cancel(Sheet(name="HR-CHS-PAID", **week))
    check(False, "a paid week is not cancelled")
except Thrown as error:
    check("Sal Slip/LPC104/00001" in str(error), "a week a submitted slip paid is not cancelled: the slips go first")
s.tables["Weekly Pay Day"][-1]["docstatus"] = 2
G.sheet_before_cancel(Sheet(name="HR-CHS-PAID", **week))
check(True, "once its slip is cancelled, the week may be")
print("the sheet: the plant's casuals by the hour, priced, sent with everything in place, approved by its own General Manager")

# the upload, from a real workbook
import openpyxl  # noqa: E402

s = site()
book = openpyxl.Workbook()
sheet = book.active
for row in (["Kawempe casuals, week 5-11 Nov"], [],
            ["PAYROLL NO", "NAME", "HOURS WORKED", "OVERTIME HOURS", "DAYS WORKED"],
            ["LPC100", "x", 52, 6, 6], ["LPC90017", "spaces dropped", 40, 0, 5], ["104", "by employee number", 30, 0, 3],
            ["LPC999", "nobody", 10, 0, 1], ["LPC200", "per piece", 10, 0, 1], ["LPC300", "Namanve", 10, 0, 1],
            ["LPC100", "twice", 5, 0, 1], ["LPC101", "comma", "1,5", 0, 1], ["LPC103", "too many", 80, 0, 7]):
    sheet.append(row)
content = io.BytesIO()
book.save(content)
FILES["/private/files/hours.xlsx"] = content.getvalue()
draft = Sheet(**week)
s.tables[G.DOCTYPE] = []
frappe.get_doc = lambda doctype, name: draft
found = G.upload_sheet("HR-CHS-NEW", "/private/files/hours.xlsx")
check([(row.employee, row.hours_worked, row.overtime_hours, row.days_worked) for row in draft.rows]
      == [("LPC100", 52.0, 6.0, 6.0), ("LPC 90017", 40.0, 0.0, 5.0), ("LPC104", 30.0, 0.0, 3.0)]
      and draft.uploaded_sheet == "/private/files/hours.xlsx" and draft.saved == 1,
      "the workbook's people taken, by their ID with or without its space, or their Employee Number",
      [(row.employee, row.hours_worked) for row in draft.rows])
problems = found["problems"]
check(len(problems) == 6 and any("LPC999: no such employee" in text for text in problems)
      and any("LPC200: not paid by the hour" in text for text in problems)
      and any("LPC300: at Namanve, not Kawempe" in text for text in problems)
      and any("Row 10, LPC100: on the file twice" in text for text in problems)
      and any("write 1,5 with a point" in text for text in problems)
      and any("LPC103: 80 hours is more than 7 days" in text for text in problems),
      "and each one left out said, with its row", problems)
check((found["people"], found["hours"], found["overtime"], found["missing"]) == (3, 122.0, 6.0, 2),
      "what was taken, and how many of the plant's casuals are not on it", found)
draft.workflow_state = "Pending General Manager"
try:
    G.upload_sheet("HR-CHS-NEW", "/private/files/hours.xlsx")
    check(False, "a sent sheet takes no upload")
except Thrown as error:
    check("Only a draft sheet takes an upload" in str(error), "a sheet with the General Manager takes no upload")
FILES["/private/files/notes.xlsx"] = b"not a workbook"
draft.workflow_state = "Draft"
try:
    G.upload_sheet("HR-CHS-NEW", "/private/files/notes.xlsx")
    check(False, "a file that is not a workbook is refused")
except Thrown as error:
    check("could not be read" in str(error), "a file that is not a workbook is refused, plainly")
# the casual worksheet as the team keeps it: saved on its LEFT tab, the week on MASTER PAYROLL under two title rows,
# an ID with the line break Excel keeps as _x000D_, and OT HRS for the overtime hours
book = openpyxl.Workbook()
book.active.title = "LEFT"
book.active.append(["Casuals who left"])
master_tab = book.create_sheet("MASTER PAYROLL")
for row in (["LUUKA PLASTICS LTD (CASUALS)"], ["CASUAL MASTER PAYROLL"], [],
            ["SrNo", "PAYROLL NO", "COUNT OF EMPLOYEE", "HOURS WORKED", "WAGE RATE", "OT HRS", "OT1-AMOUNT"],
            [1, "LPC100_x000D_\n", "x", 50, 2500, 6, 22500], [2, "LPC104", "y", 30, 2500, 0, 0]):
    master_tab.append(row)
book.active = 0
content = io.BytesIO()
book.save(content)
FILES["/private/files/worksheet.xlsx"] = content.getvalue()
found = G.upload_sheet("HR-CHS-NEW", "/private/files/worksheet.xlsx")
check([(row.employee, row.hours_worked, row.overtime_hours) for row in draft.rows]
      == [("LPC100", 50.0, 6.0), ("LPC104", 30.0, 0.0)] and not found["problems"],
      "the team's worksheet taken as saved: the week from its MASTER PAYROLL tab, the ID Excel marked found, OT HRS "
      "read as the overtime hours beside the amount", ([(row.employee, row.hours_worked) for row in draft.rows], found))
G.download_template("HR-CHS-NEW")
name, data = MADE[-1]
check(data[0] == list(R.TEMPLATE_HEADS)
      and [row[0] for row in data[1:]] == ["LPC 90017", "LPC100", "LPC101", "LPC103", "LPC104"]
      and frappe.response["filename"] == "Casual hours Kawempe 5 Nov 2026 to 11 Nov 2026.xlsx"
      and frappe.response["type"] == "binary",
      "the template: the plant's casuals by the hour, by PAYROLL NO, none of another plant's or the Per Piece",
      (data, frappe.response.get("filename")))
s.add("Casual Hours Sheet", name="HR-CHS-9", company="LPL", branch="Kawempe", from_date=D(2026, 10, 29),
      to_date=D(2026, 11, 4), docstatus=1)
check(G.new_sheet_week("LPL", "Kawempe") == {"from_date": "2026-11-05", "to_date": "2026-11-11"}
      and G.latest_to({"company": "LPL"}) == D(2026, 11, 4),
      "a plant's next sheet is the week after its last; a weekly payroll reaches the last approved week",
      G.new_sheet_week("LPL", "Kawempe"))
print("the upload: the team's workbook read, each person found or said; the template; the next week")

# the sheets give the weeks of those they list, on the payroll and on the Attendance Verification (Luuka, 12 Nov 2026:
# "for casuals the attendance verification should be from casual hours sheet"; "validate attendace varies from the
# casual hour sheet"). The review of b453383 the same day: a casual a sheet leaves out is paid from the clock, as the
# verification shows them; the days worked are counted per sheet, never on two verifications; a verified week is not
# changed under the General Manager; a week paid another way is not paid again
s = site()
for name, branch, start, end, docstatus, state in (
        ("HR-CHS-A", "Kawempe", D(2026, 10, 29), D(2026, 11, 4), 1, "Approved"),
        ("HR-CHS-B", "Kawempe", D(2026, 11, 5), D(2026, 11, 11), 0, "Pending General Manager"),
        ("HR-CHS-N", "Namanve", D(2026, 10, 29), D(2026, 11, 4), 1, "Approved"),
        # a cancelled sheet over the very same week, its 99 hours never counted
        ("HR-CHS-X", "Kawempe", D(2026, 10, 30), D(2026, 11, 5), 2, "Cancelled")):
    s.add("Casual Hours Sheet", name=name, company="LPL", branch=branch, from_date=start, to_date=end,
          docstatus=docstatus, workflow_state=state)
for parent, employee, hours, overtime, days, docstatus in (("HR-CHS-A", "LPC100", 50, 6, 5, 1),
                                                           ("HR-CHS-B", "LPC100", 30, 0, 0, 0),
                                                           ("HR-CHS-X", "LPC101", 99, 9, 7, 2)):
    s.add("Casual Hours Row", parent=parent, parenttype="Casual Hours Sheet", employee=employee, hours_worked=hours,
          overtime_hours=overtime, days_worked=days, docstatus=docstatus)
A_WEEK = (D(2026, 10, 29), D(2026, 11, 4))
check(G.spans(["LPC100", "LPC101", "LPC300", "LPC200"]) == {"LPC100": [A_WEEK]},
      "the payroll takes an approved sheet's week for those it lists: LPC101, left off Kawempe's, is paid from the "
      "clock, never nothing; never a sheet still with the General Manager or cancelled",
      G.spans(["LPC100", "LPC101", "LPC300", "LPC200"]))
got = G.for_verification(["LPC100", "LPC101"], D(2026, 10, 30), D(2026, 11, 5))
week_days = {D(2026, 10, 30) + datetime.timedelta(days=n) for n in range(7)}
check(got["people"] == {"LPC100": {"covered": week_days, "counted": {D(2026, 11, 5)}, "hours": 50.0, "overtime": 6.0,
                                   "days": 5.0}},
      "the verification's casuals: each day a sheet gives, theirs; the totals and days of the sheet whose last day it "
      "holds; the days of one that leaves its Days Worked blank counted from the attendance; nobody a sheet leaves out",
      got["people"])
check(got["sheets"] == {"HR-CHS-A": {"from_date": D(2026, 10, 29), "to_date": D(2026, 11, 4), "state": "Approved",
                                     "people": 1},
                        "HR-CHS-B": {"from_date": D(2026, 11, 5), "to_date": D(2026, 11, 11),
                                     "state": "Pending General Manager", "people": 1}},
      "the sheets over its days, not a cancelled one, with how many of its casuals each has", got["sheets"])
# a week the General Manager has verified for a casual is not changed under them: reopened first
s.verified = [{"name": "HR-ATV-1", "branch": "Kawempe", "from_date": D(2026, 10, 29), "to_date": D(2026, 11, 4),
               "employees": ["LPC103"]}]
said = refused(Sheet(rows=[{"employee": "LPC103", "hours_worked": 10}], from_date=D(2026, 10, 29),
                     to_date=D(2026, 11, 4)))
check(said == "LPC103 is on HR-ATV-1, verified for Kawempe: the General Manager reopens it before these hours change.",
      "hours over days a verified Attendance Verification holds for the person are refused", said)
check(refused(Sheet(rows=[{"employee": "LPC 90017", "hours_worked": 10}], from_date=D(2026, 10, 29),
                    to_date=D(2026, 11, 4))) is None, "another casual's hours, not verified, are taken")
try:
    G.sheet_before_cancel(Sheet(name="HR-CHS-Q", rows=[{"employee": "LPC103"}], from_date=D(2026, 10, 29),
                                to_date=D(2026, 11, 4)))
    check(False, "an approved week the General Manager has verified is not cancelled")
except Thrown as error:
    check("LPC103 is on HR-ATV-1" in str(error), "nor is its cancel: the verified week would change under it")
s.verified = []
# a week paid another way is not sent or approved: it would be paid twice (found by the review of b453383)
s.standard_rate = 2000
s.add("Weekly Pay Day", parent="Sal Slip/LPC104/00009", employee="LPC104", attendance_date=D(2026, 10, 30), docstatus=1,
      hours=9)
before = Sheet(rows=[{"employee": "LPC104", "hours_worked": 30}], from_date=D(2026, 10, 29), to_date=D(2026, 11, 4))
said = refused(Sheet(before=before, workflow_state="Pending General Manager",
                     rows=[{"employee": "LPC104", "hours_worked": 30}], from_date=D(2026, 10, 29),
                     to_date=D(2026, 11, 4)))
check(said and "Some of these days were paid already from the attendance for LPC104 (Sal Slip/LPC104/00009)" in said,
      "a week some of whose days a weekly slip paid from the attendance is not sent: it would be paid twice", said)
check(refused(Sheet(rows=[{"employee": "LPC104", "hours_worked": 30}], from_date=D(2026, 10, 29),
                    to_date=D(2026, 11, 4))) is None, "a draft may still hold it, while HR put it right")
print("the sheets' weeks: of those they list, the days worked per sheet, locked once verified, never paid twice")

# ── 4. The doctypes, the form, the wiring ─────────────


def doctype(folder):
    return json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))


sheet_json, row_json = doctype("casual_hours_sheet"), doctype("casual_hours_row")
fields = {field["fieldname"]: field for field in sheet_json["fields"]}
row_fields = {field["fieldname"]: field for field in row_json["fields"]}
check(sheet_json["is_submittable"] == 1 and fields["rows"]["options"] == "Casual Hours Row" and row_json["istable"] == 1
      and fields["branch"]["reqd"] == 1
      and fields["status"]["options"].split("\n") == list(dict.fromkeys(state["state"] for state in A.STATES)),
      "a submittable sheet a plant, its rows the casuals, its status the workflow's")
money = {"rate", "multiplier", "hours_pay", "overtime_pay", "total_pay"}
check(all(row_fields[name].get("permlevel") == 1 and row_fields[name].get("read_only") == 1 for name in money)
      and fields["total_pay"].get("permlevel") == 1
      and all(row_fields[name].get("permlevel", 0) == 0 for name in ("employee", "hours_worked", "overtime_hours", "days_worked")),
      "the rates and the pay are kept to HR (permission level 1), as the Hourly Rate is; the hours are anyone's")
level_one = {perm["role"] for perm in sheet_json["permissions"] if perm.get("permlevel") == 1 and perm.get("read")}
check(level_one == {"System Manager", "HR Manager", "HR User"},
      "the General Manager approves the hours and never sees a rate", level_one)
roles = {perm["role"]: perm for perm in sheet_json["permissions"] if not perm.get("permlevel")}
check(roles["General Manager"].get("submit") and not roles["General Manager"].get("create")
      and not roles["HR User"].get("submit") and roles["HR Manager"].get("cancel")
      and not roles["Payroll Officer"].get("write"),
      "HR fill it, the General Manager approves it, the HR Manager cancels, the Payroll Officer reads")
check(all(fields[name].get("read_only") for name in ("status", "uploaded_sheet", "total_people", "total_hours",
                                                       "total_overtime", "prepared_by", "approved_by"))
      and fields["workflow_state"].get("hidden"), "the figures and signatures are written by the server")
day = doctype("weekly_pay_day")
day_fields = {field["fieldname"]: field for field in day["fields"]}
check(day_fields["hours_sheet"]["options"] == "Casual Hours Sheet" and day_fields["hours_sheet"].get("search_index") == 1
      and day_fields["days_worked"]["fieldtype"] == "Float", "a slip's day says the sheet it was paid from")
glue = read("hrms_addon", "hrms_addon", "casual_hours.py")
controller = read("hrms_addon", "hrms_addon", "doctype", "casual_hours_sheet", "casual_hours_sheet.py")
check(all(call in controller for call in ("casual_hours.sheet_validate(self)", "casual_hours.sheet_before_submit(self)",
                                          "casual_hours.sheet_before_cancel(self)", "casual_hours.sheet_on_cancel(self)")),
      "the sheet's controller runs the glue at each step")
check('@frappe.whitelist(methods=["POST"])\ndef upload_sheet(sheet, file_url):' in glue
      and 'doc.check_permission("write")' in glue and "@frappe.whitelist()\ndef download_template(sheet):" in glue,
      "the upload is a POST by someone who may change the sheet; the template is read")
form = read("hrms_addon", "hrms_addon", "doctype", "casual_hours_sheet", "casual_hours_sheet.js")
check('__("Download Template")' in form and '__("Upload Sheet")' in form and 'HA_HOURS + "upload_sheet"' in form
      and 'HA_HOURS + "download_template?sheet="' in form and '"Draft") === "Draft"' in form
      and 'allowed_file_types: [".xlsx"]' in form,
      "the form: the template to download, and the upload while it is a draft")
hooks = read("hrms_addon", "hooks.py")
check('"hrms_addon.hrms_addon.casual_hours.setup_workflows_on_migrate",' in hooks,
      "the approval is built on every migrate")
navigation = read("hrms_addon", "hrms_addon", "navigation_rules.py")
check(navigation.count('"Casual Hours Sheet"') >= 4, "on the Payroll page beside the Output Pay Run, and in its sidebar")
weekly = read("hrms_addon", "hrms_addon", "weekly_pay.py")
for needle, what in (("casual_hours.spans(employees)", "the days a sheet covers are not paid from the attendance"),
                     ("casual_hours.unpaid([doc.employee]", "the slip pays the sheet's week"),
                     ("casual_hours.waiting(", "Get Employees keeps whom a sheet owes"),
                     ("casual_hours.latest_to(wanted)", "a payroll reaches the last approved week")):
    check(needle in weekly, "weekly_pay: %s" % what)
gate = read("hrms_addon", "hrms_addon", "attendance_verification.py")
lone = gate[gate.index("\ndef slip_before_submit("):gate.index("\n@frappe.whitelist()\ndef payroll_branches(")]
check('if row.get("attendance_date") and not row.get("hours_sheet")]}' in lone
      and "weekly_pay.days_to_pay(" in gate[gate.index("\ndef _days_paid("):gate.index("\ndef _range(")],
      "the attendance verification asks nothing more of a sheet's week, which its General Manager approved on the "
      "sheet: not on the payroll (days_to_pay leaves the week out), nor on a slip submitted alone")
print("wiring: the doctypes, HR's rates kept to HR, the form, the hook, the page, the weekly payroll, the gate")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL CASUAL HOURS CHECKS PASSED")
