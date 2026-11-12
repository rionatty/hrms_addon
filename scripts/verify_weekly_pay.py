"""Checks weekly pay for casuals without a bench:

    python scripts/verify_weekly_pay.py

Luuka, 5 Nov 2026: casuals are paid weekly on Thursdays; a payroll "should pick
from attendace and from last executed"; Per Meter stays monthly; PAYE, NSSF and
LST "not at all"; and the Pay Category says Weekly, not Hourly. 10 Nov 2026:
the Per Piece casuals are paid on the same weekly payroll, and a casual's
overtime is paid in the week at their own rate times the multiplier.

  1  the rules: a day's hours, the days to pay, the dates, who two payrolls share
  2  the dates a new payroll is given, and its Start held where the last stopped
  3  Get Employees: the structure and assignments made once, those to pay kept,
     the Per Piece casuals with piece pay, and those with overtime only
  4  the slip: the days it pays, a day marked late, a cancelled slip, a monthly one,
     and the approved overtime at the person's rate times the multiplier; each
     day at the Hourly Rate in force that day (10 Nov 2026: the rate is its own
     record, for HR alone, not a field on the employee)
  5  Frappe HR's own slip and assignment methods, lifted from its source: the
     week's line is hours x rate, never cut by payment days, and no tax is added
  6  the Employees tab, and reads that do not grow with the people
  7  wiring: the fields, the doctype, the hooks, the patch, the form, Output Pay
  8  upstream: what it stands on in Frappe HR and Frappe
"""
import ast
import copy
import datetime
import importlib.util
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []
D = datetime.date
TODAY = D(2026, 11, 5)


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
    return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
R = load("weekly_pay_rules")  # proves it has no Frappe import
O = load("output_rules")
OR = load("overtime_rules")
print("loaded weekly_pay_rules.py without Frappe")

# ── 1. The rules ─────────────────────────────────────────
check(R.on_weekly_pay({"payroll_frequency": "Weekly"}) and not R.on_weekly_pay({"payroll_frequency": "Monthly"})
      and not R.on_weekly_pay({"payroll_frequency": "Weekly", "salary_slip_based_on_timesheet": 1}),
      "a week's payroll or slip is one of Weekly frequency, not worked out from timesheets")
for status, worked, hours, why in (("Present", 12, 10.0, "what the clock shows, up to the standard day"),
                                   ("Present", 8, 8.0, "a short day is its hours"),
                                   ("Present", 0, 10.0, "a day marked with nothing from the clock pays the standard day"),
                                   ("Work From Home", None, 10.0, "and so does one worked from home"),
                                   ("Half Day", 0, 5.0, "half of it for a Half Day"),
                                   ("Half Day", 4, 4.0, "and a Half Day with clock hours, those hours")):
    check(R.day_hours(status, worked, 10) == hours, "a day: %s" % why, R.day_hours(status, worked, 10))
ROWS = [{"attendance_date": "2026-11-03", "status": "Present", "working_hours": 12},
        {"attendance_date": D(2026, 11, 4), "status": "Present", "working_hours": 8},
        {"attendance_date": D(2026, 11, 5), "status": "Absent", "working_hours": 0},
        {"attendance_date": D(2026, 11, 6), "status": "Half Day", "working_hours": 0},
        {"attendance_date": D(2026, 11, 7), "status": "On Leave", "working_hours": 0},
        {"attendance_date": D(2026, 11, 2), "status": "Present", "working_hours": 10},
        {"attendance_date": D(2026, 11, 1), "status": "Present", "working_hours": 10},
        {"attendance_date": D(2026, 11, 8), "status": "Present", "working_hours": 4},
        {"attendance_date": D(2026, 11, 8), "status": "Present", "working_hours": 5}]
days = R.to_pay(ROWS, ["2026-11-02"], [(D(2026, 10, 26), D(2026, 11, 1))], 10)
check([(day["attendance_date"], day["status"], day["hours"]) for day in days]
      == [(D(2026, 11, 3), "Present", 10.0), (D(2026, 11, 4), "Present", 8.0), (D(2026, 11, 6), "Half Day", 5.0),
          (D(2026, 11, 8), "Present", 9.0)],
      "the days to pay: worked, not yet paid, not on a monthly slip, one row a date, earliest first", days)
check(R.to_pay(list(reversed(ROWS)), ["2026-11-02"], [(D(2026, 10, 26), D(2026, 11, 1))], 10) == days,
      "in whatever order the attendance comes")
check(R.total_hours(days) == 32.0 and R.amount(32, 2500) == 80000.0 and R.amount(None, 2500) == 0.0,
      "the hours added up, and paid at the rate")
check(R.to_pay([], [], [], 10) == [] and R.to_pay(None, None, None, 10) == [], "no attendance, no days")
check(R.same_people({}, {"branch": "North"}) and R.same_people({"branch": "North"}, {"branch": "North"})
      and not R.same_people({"branch": "North"}, {"branch": "South"})
      and not R.same_people({"branch": "North", "grade": "A"}, {"branch": "North", "grade": "B"}),
      "two payrolls share people unless a filter they both have differs")
RUNS = [{"end_date": "2026-10-28", "branch": "North"}, {"end_date": D(2026, 11, 4), "branch": "South"}]
check(R.last_executed(RUNS, {"branch": "North"}) == D(2026, 10, 28) and R.last_executed(RUNS, {}) == D(2026, 11, 4)
      and R.last_executed([], {}) is None, "the last payroll for these people: their plant's, or any for the whole company")
check(R.dates(D(2026, 10, 28), D(2026, 11, 4)) == {"start": D(2026, 10, 29), "end": D(2026, 11, 4), "last": D(2026, 10, 28)},
      "a payroll starts the day after the last stopped and ends on the last day attendance was marked")
check(R.dates(None, D(2026, 11, 4)) == {"start": D(2026, 10, 29), "end": D(2026, 11, 4), "last": None},
      "the first has nothing to go from: a week ending on that day")
check(R.dates(D(2026, 11, 4), D(2026, 11, 4)) == {"start": D(2026, 11, 5), "end": None, "last": D(2026, 11, 4)}
      and R.dates(None, None) == {"start": None, "end": None, "last": None},
      "no End when nothing has been marked since: nothing to pay yet")
check(R.date_errors(D(2026, 10, 29), D(2026, 11, 4)) == [] and R.date_errors(None, D(2026, 11, 4)) == []
      and R.date_errors(D(2026, 11, 4), D(2026, 11, 4), D(2026, 11, 3)) == [],
      "dates that run forwards are fine; missing ones are Frappe's to ask for")
check("nothing to pay" in " ".join(R.date_errors(D(2026, 11, 5), D(2026, 11, 4), D(2026, 11, 4)))
      and "4 Nov 2026" in " ".join(R.date_errors(D(2026, 11, 5), D(2026, 11, 4), D(2026, 11, 4)))
      and "cannot be before" in " ".join(R.date_errors(D(2026, 11, 5), D(2026, 11, 4))),
      "an End before the Start says why", R.date_errors(D(2026, 11, 5), D(2026, 11, 4), D(2026, 11, 4)))
check(R.earliest(None, "2026-10-01", D(2026, 9, 1)) == D(2026, 9, 1) and R.earliest(None) is None, "the earliest day")
check(R.still_here(None, D(2026, 10, 29)) and not R.still_here(D(2026, 9, 30), D(2026, 10, 29))
      and R.still_here(D(2026, 11, 1), D(2026, 10, 29)) and R.still_here(D(2026, 10, 29), D(2026, 10, 29)),
      "someone who left before the Start is not on the payroll; one who left on it is")
check(R.assignment_from(D(2025, 1, 1), D(2026, 10, 29), []) == D(2025, 1, 1)
      and R.assignment_from(D(2025, 1, 1), D(2026, 10, 29), [D(2025, 1, 1)]) == D(2026, 10, 29)
      and R.assignment_from(D(2025, 1, 1), D(2026, 10, 29), ["2025-01-01", "2026-10-29"]) is None
      and R.assignment_from(None, D(2026, 10, 29), []) == D(2026, 10, 29),
      "an assignment from the joining date, else the Start, never on a day another starts")
ACCOUNTS = [{"parent": "Overtime", "account": "Overtime - LPT"}, {"parent": "Per Meter Earnings", "account": "Wages - LPT"},
            {"parent": "Per Piece Earnings", "account": "Wages - LPT"}, {"parent": "PAYE", "account": "PAYE - LPT"},
            {"parent": "Basic", "account": "Salaries - LPT"}]
EARNINGS = {"Overtime", "Per Meter Earnings", "Per Piece Earnings", "Basic"}
check(R.account_to_copy(ACCOUNTS, EARNINGS, "Basic") == "Salaries - LPT"
      and R.account_to_copy(ACCOUNTS[:4], EARNINGS, "Basic") == "Wages - LPT"
      and R.account_to_copy(ACCOUNTS[3:4], EARNINGS, "Basic") is None,
      "a new earning's account: Basic's, else the company's earnings' most used, never a deduction's")
check(R.structure_name("LPT") == "Weekly Casuals - LPT" and R.shown(D(2026, 10, 29)) == "29 Oct 2026", "the names")
check(R.weekly_began(D(2026, 10, 26), D(2026, 11, 25)) and R.weekly_began("2026-10-26", "2026-10-26")
      and not R.weekly_began(D(2026, 10, 26), D(2026, 10, 25)) and not R.weekly_began(None, D(2026, 11, 25)),
      "a monthly payroll reaches into weekly pay when it ends on or after the first weekly payroll's Start")
check(R.CATEGORIES == ("Weekly", "Per Piece") and R.PAY == "weekly_pay" and R.OVERTIME == "weekly_overtime",
      "a weekly payroll pays both kinds of casual, on two lines: the hours, and the overtime")
OT = [{"attendance_date": "2026-10-30", "status": "Present", "actual_overtime_duration": 2, "overtime_type": "Casual OT"},
      {"attendance_date": D(2026, 10, 29), "status": "Present", "actual_overtime_duration": 3, "overtime_type": "Casual OT"},
      {"attendance_date": D(2026, 10, 31), "status": "Present", "actual_overtime_duration": 4, "overtime_type": None},
      {"attendance_date": D(2026, 11, 2), "status": "Present", "actual_overtime_duration": 1.5, "overtime_type": "Casual OT"}]
due = R.overtime_to_pay(OT, {"2026-11-02": 1.5, D(2026, 10, 30): 0.5})
check([(row["attendance_date"], row["hours"]) for row in due] == [(D(2026, 10, 29), 3.0), (D(2026, 10, 30), 1.5)],
      "the overtime to pay: approved and sent to payroll, less what a slip paid, earliest first; none with no type", due)
check(R.overtime_amount([{"attendance_date": D(2026, 10, 29), "hours": 2}, {"attendance_date": D(2026, 10, 30), "hours": 3}],
                        857, {D(2026, 10, 29): 1.5, D(2026, 10, 30): 1.5}) == 6427.5
      and R.overtime_amount([{"attendance_date": "2026-10-31", "hours": 2}], 1000, {D(2026, 10, 31): 2.0}) == 4000.0
      and R.overtime_amount([], 1000, {}) == 0.0,
      "the worksheet's overtime: hours x their own rate x 1.5, or what the type gives a rest day")
RATES = [{"rate": 857, "from_date": D(2026, 1, 1)}, {"rate": 1000, "from_date": "2026-11-02"},
         {"rate": 0, "from_date": D(2026, 11, 10)}]
check(R.rate_on(RATES, D(2026, 11, 1)) == 857 and R.rate_on(RATES, "2026-11-02") == 1000
      and R.rate_on(RATES, D(2026, 11, 20)) == 1000 and R.rate_on(RATES, D(2025, 12, 31)) is None and R.rate_on([], TODAY) is None,
      "a rate is in force from its day until the next; none before the first; a rate of nothing is no rate")
check(R.day_rates([D(2025, 12, 31), D(2026, 11, 1), D(2026, 11, 3)], RATES, 0) == {D(2026, 11, 1): 857, D(2026, 11, 3): 1000}
      and R.day_rates([D(2025, 12, 31)], RATES, 2000) == {D(2025, 12, 31): 2000},
      "each day at the rate in force that day; one before any takes the standard rate, or none")
check(R.unrated([{"attendance_date": D(2026, 11, 1), "hours": 10}, {"attendance_date": D(2026, 10, 1), "hours": 0,
                 "overtime_hours": 2}, {"attendance_date": D(2026, 10, 2), "hours": 0}], {D(2026, 11, 1): 857})
      == [D(2026, 10, 1)], "a day that pays hours or overtime with no rate is said; one that pays nothing is not")
check(R.week_pay([{"hours": 10, "rate": 857}, {"hours": 5, "rate": 1000}, {"hours": 0, "overtime_hours": 2}]) == 13570
      and R.week_pay([{"hours": 10}], 10, 857) == 8570 and R.week_pay(None, 3, 1000) == 3000,
      "a week's pay is each day's hours at its own rate; a slip written before the days carried rates, its one rate")
check(R.overtime_amount([{"attendance_date": D(2026, 11, 1), "hours": 2}, {"attendance_date": D(2026, 11, 3), "hours": 2}],
                        {D(2026, 11, 1): 857, D(2026, 11, 3): 1000}, {D(2026, 11, 1): 1.5, D(2026, 11, 3): 1.5}) == 5571.0,
      "and each day's overtime at that day's rate")
check(R.rate_errors(857, D(2026, 1, 1)) == [] and "more than nothing" in " ".join(R.rate_errors(0, D(2026, 1, 1)))
      and "the day the rate starts" in " ".join(R.rate_errors(857, None))
      and "already have a rate from that day (HRATE-1)" in " ".join(R.rate_errors(857, D(2026, 1, 1), "HRATE-1")),
      "an Hourly Rate is more than nothing, from a day, one a day for each person")
table = R.days_table([{"attendance_date": D(2026, 10, 30), "status": "Present", "hours": 10.0}],
                     [{"attendance_date": D(2026, 10, 30), "status": "Present", "hours": 2.0},
                      {"attendance_date": D(2026, 10, 22), "status": "Present", "hours": 3.0}])
check([(row["attendance_date"], row["hours"], row["overtime_hours"]) for row in table]
      == [(D(2026, 10, 22), 0.0, 3.0), (D(2026, 10, 30), 10.0, 2.0)] and R.days_paid(table) == 1,
      "a slip's days: each with its overtime beside it, a day paid before with only its late overtime; the days paid "
      "are those with hours", table)
print("rules: the days and their hours, the dates, who two payrolls share")


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
        elif op == "!=":
            if same(have if have is not None else "", value if value is not None else ""):
                return False
        elif op == "between":
            if have is None or not as_date(value[0]) <= as_date(have) <= as_date(value[1]):
                return False
        elif op == "is":
            if bool(have) != (value == "set"):
                return False
        elif op in ("<", "<=", ">", ">="):
            if have is None:
                return False
            left, right = (as_date(have), as_date(value)) if as_date(value) and not isinstance(value, (int, float)) else (have, value)
            if not {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]:
                return False
        else:
            raise AssertionError("no stand-in for %s" % op)
    return True


def ordered(rows, order_by):
    if not order_by:
        return rows
    field, way = (order_by.split() + ["asc"])[:2]
    return sorted(rows, key=lambda row: (row.get(field) is None, as_date(row.get(field)) or row.get(field) or ""),
                  reverse=way.lower() == "desc")


class Doc:
    def __init__(self, site, values, row=None):
        self.site, self.row = site, row
        self.values = Row({key: [Row(line) for line in value] if isinstance(value, list) else value for key, value in values.items()})
        self.doctype = self.values.get("doctype")
        self.flags = Row()

    def get(self, key, default=None):
        return self.values.get(key, default)

    def __getattr__(self, key):
        if key.startswith("__") or key in ("values", "site", "row"):
            raise AttributeError(key)
        return self.__dict__["values"].get(key)

    def append(self, table, value):
        line = Child(value)
        self.values.setdefault(table, []).append(line)
        if self.row is not None:
            line["_into"] = self.row.setdefault(table, [])
        return line

    def insert(self):
        self.site.happening("insert", self)
        self.values.setdefault("name", "%s-%d" % (self.doctype[:3].upper(), len(self.site.rows(self.doctype)) + 1))
        self.values.setdefault("docstatus", 0)
        self.row = self.site.add(self.doctype, **{key: value for key, value in self.values.items() if key != "doctype"})
        return self

    def submit(self):
        self.site.happening("submit", self)
        self.row["docstatus"] = 1

    def save(self):
        for line in self.values.get("accounts") or []:
            if not self.site.rows("Salary Component Account") or not any(
                    row.parent == self.values.name and row.company == line.company for row in self.site.rows("Salary Component Account")):
                self.site.add("Salary Component Account", parent=self.values.name, parenttype="Salary Component",
                              company=line.company, account=line.account)
        self.site.saved.append(self.values.name)


class Child(Row):
    """A row appended to a document already saved, written on its own as Frappe's db_insert writes it."""

    def db_insert(self):
        self.pop("_into").append(Row(self))


class Site:
    def __init__(self):
        self.tables, self.calls, self.messages, self.saved = {}, [], [], []
        self.savepoints, self.commits, self.cleared = {}, 0, 0
        self.refuse_submit = {}
        self.settings = Row(standard_hours=10, standard_hourly_rate=2000)
        self.companies = {"LPL": Row(abbr="LPT", default_currency="UGX")}
        self.components = []
        self.day_kinds, self.pieces_waiting, self.cache_cleared = {}, set(), []
        # {employee: the run that paid their arrears}, as piece_pay.arrears_paid finds it
        self.arrears_paid = {}

    def add(self, doctype, **values):
        row = Row(values)
        row.setdefault("docstatus", 0)
        self.tables.setdefault(doctype, []).append(row)
        return row

    def rows(self, doctype):
        if doctype == "Overtime Details":  # an Overtime Slip's lines, as their own table holds them
            return [Row(line, parent=row.name, parenttype="Overtime Slip", docstatus=row.docstatus)
                    for row in self.tables.get("Overtime Slip", []) for line in row.get("overtime_details") or []]
        if doctype == "Salary Detail":  # a structure's lines, as their own table holds them
            return [Row(line, name="%s-%s-%d" % (row.name, field, number), parent=row.name, parenttype="Salary Structure",
                        parentfield=field)
                    for row in self.tables.get("Salary Structure", []) for field in ("earnings", "deductions")
                    for number, line in enumerate(row.get(field) or [])]
        return self.tables.get(doctype, [])

    def happening(self, what, doc):
        if what == "submit" and doc.doctype == "Salary Structure Assignment" and doc.get("employee") in self.refuse_submit:
            raise Thrown("<b>%s</b>" % self.refuse_submit[doc.get("employee")])

    # frappe
    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, limit=None):
        self.calls.append(("get_all", doctype))
        found = ordered([row for row in self.rows(doctype) if matches(row, filters)], order_by)
        if pluck:
            return [row.get(pluck) for row in found]
        return [Row({field: row.get(field) for field in (fields or ["name"])}) for row in found]

    def get_value(self, doctype, filters, fieldname, order_by=None, as_dict=False):
        self.calls.append(("get_value", doctype))
        filters = {"name": filters} if isinstance(filters, str) else filters
        found = ordered([row for row in self.rows(doctype) if matches(row, filters)], order_by)
        if isinstance(fieldname, (list, tuple)):
            return Row({field: found[0].get(field) for field in fieldname}) if found else None
        return found[0].get(fieldname) if found else None

    def exists(self, doctype, filters):
        self.calls.append(("exists", doctype))
        filters = {"name": filters} if isinstance(filters, str) else filters
        found = [row for row in self.rows(doctype) if matches(row, filters)]
        return found[0].get("name") if found else None

    def get_doc(self, values, name=None):
        if isinstance(values, dict):
            return Doc(self, values)
        row = next(row for row in self.rows(values) if row.name == name)
        accounts = [Row(company=line.company, account=line.account) for line in self.rows("Salary Component Account") if line.parent == name]
        return Doc(self, dict(row, doctype=values, accounts=accounts), row)

    def savepoint(self, name):
        self.savepoints[name] = copy.deepcopy(self.tables)

    def rollback(self, save_point=None):
        self.tables = copy.deepcopy(self.savepoints[save_point])

    def commit(self):
        self.commits += 1


SITE = [None]


def site():
    return SITE[0]


frappe = types.ModuleType("frappe")
frappe.__path__ = []
frappe._ = lambda text, *args, **kwargs: text


def whitelist(*args, **kwargs):
    return (lambda fn: fn) if not args or not callable(args[0]) else args[0]


def throw(message, title=None, *args, **kwargs):
    raise Thrown(message)


def has_permission(doctype, ptype="read", throw=False, **kwargs):
    if getattr(site(), "denied", False) and throw:
        raise Thrown("Not permitted")
    return not getattr(site(), "denied", False)


frappe.whitelist = whitelist
frappe.throw = throw
frappe.has_permission = has_permission
frappe.msgprint = lambda message, title=None, indicator=None, **kwargs: site().messages.append(message)
frappe.clear_last_message = lambda: setattr(site(), "cleared", site().cleared + 1)
frappe.get_all = lambda *args, **kwargs: site().get_all(*args, **kwargs)
frappe.get_doc = lambda *args, **kwargs: site().get_doc(*args, **kwargs)
frappe.get_cached_value = lambda doctype, name, field: (site().companies.get(name) or {}).get(field)
frappe.get_cached_doc = lambda doctype, name: types.SimpleNamespace(
    as_dict=lambda: Row(next(row for row in site().rows(doctype) if row.name == name)))
frappe.clear_document_cache = lambda doctype, name: site().cache_cleared.append((doctype, name))
frappe.db = types.SimpleNamespace(
    get_value=lambda *args, **kwargs: site().get_value(*args, **kwargs),
    exists=lambda *args, **kwargs: site().exists(*args, **kwargs),
    savepoint=lambda name: site().savepoint(name),
    rollback=lambda save_point=None: site().rollback(save_point),
    commit=lambda: site().commit(),
)
utils = types.ModuleType("frappe.utils")
utils.cint = lambda value: int(float(value or 0))
utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
utils.date_diff = lambda end, start: (as_date(end) - as_date(start)).days
utils.strip_html = lambda text: re.sub(r"<[^>]+>", "", text or "")
utils.today = lambda: TODAY.isoformat()
utils.getdate = as_date
output_pay = types.ModuleType("hrms_addon.hrms_addon.output_pay")
output_pay.settings = lambda: site().settings


def made_component(section):
    site().components.append(section)
    return "Hourly Earnings"


output_pay._component = made_component
# the overtime module reads the sort of day it is for the person; piece_pay says who has piece pay to be paid
overtime_glue = types.ModuleType("hrms_addon.hrms_addon.overtime")
overtime_glue.day_kind = lambda employee, day: site().day_kinds.get((employee, as_date(day)), OR.WEEKDAY)
piece_glue = types.ModuleType("hrms_addon.hrms_addon.piece_pay")
piece_glue.waiting = lambda employees, start, end: {name for name in employees if name in site().pieces_waiting}
piece_glue.ARREARS = ("Arrear", "ARR")
piece_glue.arrears_names = lambda: ("Arrear", "Arrears Deductions", "Arrears")
# {(employee, component): the run that paid their arrears under it}, as piece_pay.arrears_paid finds it
piece_glue.arrears_paid = lambda employee, day, component=None: site().arrears_paid.get((employee, component))
sys.modules.update({"frappe": frappe, "frappe.utils": utils, "hrms_addon.hrms_addon.output_pay": output_pay,
                    "hrms_addon.hrms_addon.output_rules": O, "hrms_addon.hrms_addon.overtime": overtime_glue,
                    "hrms_addon.hrms_addon.piece_pay": piece_glue})
# the Casual Hours Sheets, as they are: the weekly payroll reads them (casual_hours.py)
utils.now_datetime = lambda: datetime.datetime(2026, 11, 5, 9, 0)
people_glue = types.ModuleType("hrms_addon.hrms_addon.people")
people_glue.people_for = lambda role, branch, department=None: []
people_glue.hr_officers = lambda branch, department=None: []
people_glue.notify = people_glue.assign = people_glue.withdraw = lambda *args, **kwargs: None
sys.modules["hrms_addon.hrms_addon.people"] = people_glue
CHR = load("casual_hours_rules")
CH = load("casual_hours")
W = load("weekly_pay")


class Form:
    """A Payroll Entry or a Salary Slip, as a document."""

    def __init__(self, **values):
        self.__dict__.update(values)
        self.flags = Row()

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def set(self, key, value):
        self.__dict__[key] = value


def populated():
    s = Site()
    SITE[0] = s
    people = (
        ("W1", "Weekly", "North", "Active", D(2025, 1, 1), None, 2500),
        ("W2", "Weekly", "North", "Active", D(2025, 3, 1), None, 0),
        ("W3", "Weekly", "South", "Active", D(2026, 10, 30), None, 3000),
        ("W4", "Weekly", "North", "Active", D(2024, 6, 1), None, 0),
        ("W5", "Weekly", "North", "Inactive", D(2024, 6, 1), None, 2500),
        ("W6", "Weekly", "North", "Left", D(2024, 6, 1), D(2026, 9, 30), 2500),
        ("W7", "Weekly", "North", "Active", D(2025, 5, 5), None, 2500),
        ("W8", "Weekly", "North", "Active", D(2025, 5, 5), None, 2500),
        ("M1", "Regular", "North", "Active", D(2020, 1, 1), None, 0),
    )
    for name, category, branch, status, joined, left, rate in people:
        s.add("Employee", name=name, company="LPL", custom_pay_category=category, branch=branch, status=status,
              date_of_joining=joined, relieving_date=left)
        if rate:
            s.add("Hourly Rate", name="HRATE-" + name, employee=name, rate=rate, from_date=D(2025, 1, 1))
    s.add("Salary Component", name="Hourly Earnings", type="Earning", depends_on_payment_days=0)
    s.add("Salary Component", name="Basic", type="Earning", depends_on_payment_days=1)
    s.add("Salary Component", name="PAYE", type="Deduction", depends_on_payment_days=0)
    s.add("Salary Component Account", parent="Basic", parenttype="Salary Component", company="LPL", account="Salaries - LPT")
    s.add("Salary Component Account", parent="PAYE", parenttype="Salary Component", company="LPL", account="PAYE - LPT")
    s.add("Salary Structure Assignment", name="SSA-OLD", employee="W7", salary_structure="Salaried", from_date=D(2025, 5, 5), docstatus=1)
    week = [(D(2026, 10, 29), "Present", 12), (D(2026, 10, 30), "Present", 10), (D(2026, 10, 31), "Present", 8),
            (D(2026, 11, 1), "Absent", 0), (D(2026, 11, 2), "Half Day", 0), (D(2026, 11, 3), "Present", 0),
            (D(2026, 11, 4), "Present", 10), (D(2026, 11, 5), "Present", 4)]
    for number, (day, status, hours) in enumerate(week):
        s.add("Attendance", name="A-W1-%d" % number, employee="W1", attendance_date=day, status=status, working_hours=hours, docstatus=1)
    for number, day in enumerate((D(2026, 10, 29), D(2026, 10, 30))):
        s.add("Attendance", name="A-W2-%d" % number, employee="W2", attendance_date=day, status="Present", working_hours=10, docstatus=1)
    s.add("Attendance", name="A-W3-0", employee="W3", attendance_date=D(2026, 10, 30), status="Present", working_hours=9, docstatus=1)
    s.add("Attendance", name="A-W4-0", employee="W4", attendance_date=D(2026, 10, 30), status="Present", working_hours=9, docstatus=1)
    s.add("Attendance", name="A-W7-0", employee="W7", attendance_date=D(2026, 10, 31), status="Present", working_hours=9, docstatus=1)
    s.add("Attendance", name="A-M1-0", employee="M1", attendance_date=D(2026, 11, 4), status="Present", working_hours=9, docstatus=1)
    s.add("Attendance", name="A-W1-DRAFT", employee="W1", attendance_date=D(2026, 10, 28), status="Present", working_hours=9, docstatus=0)
    return s


# ── 2. The dates ─────────────────────────────────────────
s = populated()
check(W.dates_for("LPL") == {"start": D(2026, 10, 29), "end": D(2026, 11, 4), "last": None},
      "the first payroll: a week ending on the last day marked before today; today's 5 Nov is not over", W.dates_for("LPL"))
s.add("Output Pay Run", name="OPR-1", company="LPL", section="Hourly", branch="North", to_date=D(2026, 10, 25), docstatus=1)
s.add("Output Pay Run", name="OPR-2", company="LPL", section="Hourly", branch="North", to_date=D(2026, 11, 25), docstatus=2)
s.add("Output Pay Run", name="OPR-3", company="LPL", section="Per Meter", branch="North", to_date=D(2026, 11, 25), docstatus=1)
check(W.dates_for("LPL", branch="North")["start"] == D(2026, 10, 26) and W.dates_for("LPL", branch="South")["last"] is None,
      "a plant whose casuals an Hourly run paid by the month carries on the day after it; another plant has nothing to go from",
      (W.dates_for("LPL", branch="North"), W.dates_for("LPL", branch="South")))
s.add("Payroll Entry", name="PE-1", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=1,
      start_date=D(2026, 10, 22), end_date=D(2026, 10, 28))
s.add("Payroll Entry", name="PE-GONE", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=2,
      start_date=D(2026, 10, 29), end_date=D(2026, 11, 4))
s.add("Payroll Entry", name="PE-DRAFT", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=0,
      start_date=D(2026, 10, 29), end_date=D(2026, 11, 4))
s.add("Payroll Entry", name="PE-MONTH", company="LPL", payroll_frequency="Monthly", salary_slip_based_on_timesheet=0, docstatus=1,
      start_date=D(2026, 10, 26), end_date=D(2026, 11, 25))
check(W.dates_for("LPL") == {"start": D(2026, 10, 29), "end": D(2026, 11, 4), "last": D(2026, 10, 28)},
      "from the day after the last submitted weekly payroll; a cancelled or draft one, or a monthly one, does not count",
      W.dates_for("LPL"))
s.add("Payroll Entry", name="PE-2", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=1,
      start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), branch="South")
check(W.dates_for("LPL", branch="North")["start"] == D(2026, 10, 29) and W.dates_for("LPL", branch="South")["start"] == D(2026, 11, 5)
      and W.dates_for("LPL")["start"] == D(2026, 11, 5),
      "each plant from its own last payroll; the whole company from the last of any")
check(W.dates_for("LPL", branch="South")["end"] is None, "and no End where nothing was marked since")
s.denied = True
try:
    W.dates_for("LPL")
    check(False, "the dates are only for those who may read payrolls")
except Thrown:
    check(True, "the dates are only for those who may read payrolls")
s.denied = False

run = Form(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="North",
           start_date=D(2026, 10, 1), end_date=D(2026, 11, 4))
W.payroll_validate(run)
check(run.start_date == D(2026, 10, 29), "a payroll's Start is held the day after the last, whatever was sent", run.start_date)
run = Form(name="PE-2", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="South",
           start_date=D(2026, 10, 29), end_date=D(2026, 11, 4))
W.payroll_validate(run)
check(run.start_date == D(2026, 10, 29), "a payroll is not measured against itself", run.start_date)
run = Form(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="South",
           start_date=D(2026, 11, 1), end_date=D(2026, 11, 4))
try:
    W.payroll_validate(run)
    check(False, "an End before where it must start is refused, saying why")
except Thrown as error:
    check("nothing to pay" in str(error), "an End before where it must start is refused, saying why", str(error))
for other in (Form(name="X", company="LPL", payroll_frequency="Monthly", start_date=D(2026, 10, 26), end_date=D(2026, 11, 25)),
              Form(name="Y", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=1, start_date=D(2026, 10, 1),
                   end_date=D(2026, 10, 7))):
    before = other.start_date
    W.payroll_validate(other)
    check(other.start_date == before, "a %s payroll keeps its dates" % ("monthly" if other.payroll_frequency == "Monthly" else "timesheet"))
print("dates: from where the last payroll stopped to the last day marked")


# ── 3. Get Employees ─────────────────────────────────────
class FrappeHRPayrollEntry:
    """Frappe HR's own Get Employees, as it reads: those with a submitted assignment on an active structure of this
    frequency, of the company and the filters, not Inactive, and not gone before the Start."""

    @staticmethod
    def found(doc):
        structures = {row.name for row in site().rows("Salary Structure") if row.docstatus == 1 and row.payroll_frequency == doc.payroll_frequency
                      and row.company == doc.company}
        assigned = {row.employee for row in site().rows("Salary Structure Assignment") if row.docstatus == 1 and row.salary_structure in structures
                    and as_date(row.from_date) <= as_date(doc.end_date)}
        return [row.name for row in site().rows("Employee") if row.name in assigned and row.status != "Inactive" and row.company == doc.company
                and (not doc.get("branch") or row.branch == doc.branch) and (not row.relieving_date or row.relieving_date >= as_date(doc.start_date))]

    def fill_employee_details(self):
        people = self.found(self)
        if not people:
            frappe.throw("No employees found")
        self.employees = [Row(employee=name) for name in people]
        self.number_of_employees = len(people)
        return [{"employee": name, "unmarked_days": 1} for name in people] if self.get("validate_attendance") else None


class PayrollEntry(W.PayrollEntryWeekly, FrappeHRPayrollEntry, Form):
    pass


s = populated()
entry = PayrollEntry(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="North",
                     start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), employees=[])
s.refuse_submit["W8"] = "Cost centre Main - X belongs to another company"
unmarked = entry.fill_employee_details()
structure = next(row for row in s.rows("Salary Structure"))
check(structure.name == "Weekly Casuals - LPT" and structure.docstatus == 1 and structure.payroll_frequency == "Weekly"
      and structure.currency == "UGX" and structure.is_active == "Yes" and not structure.get("deductions")
      and [(line.salary_component, line.amount_based_on_formula, line.formula) for line in structure.earnings]
      == [("Hourly Earnings", 1, "weekly_pay"), ("Casual Overtime", 1, "weekly_overtime")],
      "the company's weekly structure is made: the week's hours and the overtime, and no PAYE, NSSF or LST", structure)
check(all(any(row.parent == earning and row.account == "Salaries - LPT" and row.company == "LPL"
              for row in s.rows("Salary Component Account")) for earning in ("Hourly Earnings", "Casual Overtime")),
      "each earning takes an account for the company, as posting the payroll needs one: Basic's")
overtime_component = [row for row in s.rows("Salary Component") if row.name == "Casual Overtime"]
check(len(overtime_component) == 1 and overtime_component[0].type == "Earning" and overtime_component[0].salary_component_abbr == "COT"
      and overtime_component[0].depends_on_payment_days == 0 and overtime_component[0].remove_if_zero_valued == 1,
      "the overtime's earning is made once: not cut by payment days, and off a slip where it is nothing", overtime_component)
made = {row.employee: row for row in s.rows("Salary Structure Assignment") if row.salary_structure == "Weekly Casuals - LPT"}
check(sorted(made) == ["W1", "W2", "W4", "W7"] and all(row.docstatus == 1 for row in made.values()),
      "assignments for the plant's weekly people: not Inactive, not gone before the Start, not monthly staff, not another plant's",
      sorted(made))
check(made["W1"].from_date == D(2025, 1, 1) and made["W7"].from_date == D(2026, 10, 29) and made["W1"].currency == "UGX",
      "each from their joining date; one whose other assignment starts that day from the Start", (made["W1"], made["W7"]))
check("W8" not in made and not [row for row in s.rows("Salary Structure Assignment") if row.employee == "W8"] and s.cleared == 1
      and any("W8: Cost centre Main - X" in message and "<b>" not in message for message in s.messages),
      "one that cannot be assigned is named with the reason, its half-made assignment undone, and the rest are made",
      s.messages)
check([row.employee for row in entry.employees] == ["W1", "W2", "W4", "W7"] and entry.number_of_employees == 4 and unmarked is None,
      "Get Employees keeps those with days to pay", [row.employee for row in entry.employees])
before = len(s.rows("Salary Structure Assignment"))
s.messages.clear()
entry = PayrollEntry(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, validate_attendance=1,
                     start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), employees=[])
s.settings.standard_hourly_rate = 0
unmarked = entry.fill_employee_details()
check(len(s.rows("Salary Structure Assignment")) == before + 1 and len(s.rows("Salary Structure")) == 1,
      "asked again, only those still without one are assigned, and the structure is not made twice")
check(sorted(row.employee for row in entry.employees) == ["W1", "W3", "W7"]
      and any("W2, W4" in message for message in s.messages),
      "with no standard rate, those with no rate of their own are left out and named; their days wait for the next payroll",
      ([row.employee for row in entry.employees], s.messages))
check([row["employee"] for row in unmarked] == ["W1", "W3", "W7"], "and unmarked attendance is told only for those kept", unmarked)
s.settings.standard_hourly_rate = 2000
entry = PayrollEntry(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0,
                     start_date=D(2026, 11, 6), end_date=D(2026, 11, 12), employees=[])
try:
    entry.fill_employee_details()
    check(False, "nobody with days to pay: it says so")
except Thrown as error:
    check("Nobody has attendance, an approved hours sheet, piece work or Additional Salary to pay up to 12 Nov 2026"
          in str(error),
          "nobody with days or anything else to pay: it says so",
          str(error))
monthly = PayrollEntry(name="PE-M", company="LPL", payroll_frequency="Monthly", salary_slip_based_on_timesheet=0,
                       start_date=D(2026, 10, 26), end_date=D(2026, 11, 25), employees=[])
made_before = len(s.rows("Salary Structure Assignment"))
try:
    monthly.fill_employee_details()
except Thrown:
    pass
check(len(s.rows("Salary Structure Assignment")) == made_before, "a monthly payroll is Frappe HR's own: nobody is assigned anything")

# a monthly payroll and the casuals: theirs until weekly pay begins, the weekly payroll's after
s = populated()
s.add("Employee", name="P1", company="LPL", custom_pay_category="Per Piece", branch="North", status="Active",
      date_of_joining=D(2025, 1, 1))
s.add("Salary Structure", name="Salaried", docstatus=1, payroll_frequency="Monthly", company="LPL")
for name in ("M1", "W1", "P1"):
    s.add("Salary Structure Assignment", name="SSA-M-" + name, employee=name, salary_structure="Salaried",
          from_date=D(2025, 1, 1), docstatus=1)


def month(end=D(2026, 11, 25), validate=0):
    return PayrollEntry(name="PE-M", company="LPL", payroll_frequency="Monthly", salary_slip_based_on_timesheet=0,
                        start_date=D(2026, 10, 26), end_date=end, employees=[], validate_attendance=validate)


before = month()
before.fill_employee_details()
check(sorted(row.employee for row in before.employees) == ["M1", "P1", "W1", "W7"],
      "before weekly pay begins, a monthly payroll pays the casuals as it did", [row.employee for row in before.employees])
s.add("Payroll Entry", name="PE-FIRST", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0,
      docstatus=0, start_date=D(2026, 10, 26), end_date=D(2026, 11, 11))
s.messages.clear()
after = month(validate=1)
unmarked = after.fill_employee_details()
check([row.employee for row in after.employees] == ["M1"] and after.number_of_employees == 1
      and [row["employee"] for row in unmarked] == ["M1"]
      and any("Left out, paid by the week: 3 casual(s)." in message for message in s.messages),
      "once the first weekly payroll is made, a monthly payroll reaching into its days leaves the casuals out, and says "
      "so: their slips would pay the piece work again", ([row.employee for row in after.employees], s.messages))
october = month(end=D(2026, 10, 25))
october.fill_employee_details()
check(sorted(row.employee for row in october.employees) == ["M1", "P1", "W1", "W7"],
      "a month that ended before weekly pay began still pays them", [row.employee for row in october.employees])
s.rows("Salary Structure Assignment")[-3]["docstatus"] = 2
try:
    month().fill_employee_details()
    check(False, "a monthly payroll of casuals only says why it has nobody")
except Thrown as error:
    check("Everyone found is a casual paid by the week" in str(error), "a monthly payroll of casuals only says why it has nobody",
          str(error))
crowd = Site()
SITE[0] = crowd
for number in range(120):
    crowd.add("Employee", name="C%03d" % number, company="LPL", custom_pay_category="Weekly", status="Active", date_of_joining=D(2025, 1, 1))
crowd.add("Salary Component", name="Hourly Earnings", type="Earning", depends_on_payment_days=0)
crowd_entry = Form(company="LPL", start_date=D(2026, 10, 29))
check(W.assign_missing(crowd_entry) == {} and crowd.commits == 2 and len(crowd.rows("Salary Structure Assignment")) == 120,
      "120 assigned in one go are saved every 50: a click cut short by the server's time limit carries on", crowd.commits)
cut = Site()
SITE[0] = cut
cut.add("Salary Component", name="Hourly Earnings", type="Earning", depends_on_payment_days=1)
try:
    W.structure_for("LPL")
    check(False, "an earning cut by payment days is refused for the weekly line")
except Thrown as error:
    check("Depends on Payment Days" in str(error) and not cut.rows("Salary Structure"),
          "an earning cut by payment days is refused for the weekly line", str(error))
cut = Site()
SITE[0] = cut
cut.add("Salary Component", name="Hourly Earnings", type="Earning", depends_on_payment_days=0)
cut.add("Salary Component", name="Casual Overtime", type="Earning", depends_on_payment_days=1)
try:
    W.structure_for("LPL")
    check(False, "and so is an overtime earning cut by payment days")
except Thrown as error:
    check("Casual Overtime is cut by payment days" in str(error) and not cut.rows("Salary Structure"),
          "and so is an overtime earning cut by payment days", str(error))
old = Site()
SITE[0] = old
old.add("Salary Component", name="Hourly Earnings", type="Earning", depends_on_payment_days=0)
old.add("Salary Structure", name="Weekly Casuals - LPT", docstatus=1, company="LPL", payroll_frequency="Weekly",
        earnings=[Row(salary_component="Hourly Earnings", abbr="HRE", amount_based_on_formula=1, formula="weekly_pay", docstatus=1)])
check(W.structure_for("LPL") == "Weekly Casuals - LPT" and W.structure_for("LPL") == "Weekly Casuals - LPT", "an older structure is kept")
lines = old.rows("Salary Structure")[0].earnings
check([(line.salary_component, line.formula, line.abbr, line.docstatus, line.depends_on_payment_days) for line in lines]
      == [("Hourly Earnings", "weekly_pay", "HRE", 1, None), ("Casual Overtime", "weekly_overtime", "COT", 1, 0)]
      and old.cache_cleared == [("Salary Structure", "Weekly Casuals - LPT")] and len(old.rows("Salary Structure")) == 1,
      "a structure made before overtime was paid by the week gets the overtime line once, submitted with it", lines)

# both kinds of casual: the Per Piece ones are assigned too, and kept when they have piece pay in the week
s = populated()
for name in ("P1", "P2"):
    s.add("Employee", name=name, company="LPL", custom_pay_category="Per Piece", branch="North", status="Active",
          date_of_joining=D(2025, 1, 1))
s.pieces_waiting = {"P1"}
s.settings.standard_hourly_rate = 0
s.add("Weekly Pay Day", parent="SS-OLD", employee="W8", attendance_date=D(2026, 10, 30), hours=10, overtime_hours=0, docstatus=1)
s.add("Attendance", name="A-W8-0", employee="W8", attendance_date=D(2026, 10, 30), status="Present", working_hours=10,
      actual_overtime_duration=3, overtime_type="Casual OT", docstatus=1)
entry = PayrollEntry(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="North",
                     start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), employees=[])
entry.fill_employee_details()
made = {row.employee for row in s.rows("Salary Structure Assignment") if row.salary_structure == "Weekly Casuals - LPT"}
check({"P1", "P2"} <= made, "the Per Piece casuals are given the weekly structure too", sorted(made))
check(sorted(row.employee for row in entry.employees) == ["P1", "W1", "W7", "W8"],
      "kept: the Per Piece casual with piece pay in the week, though no rate; one whose day was paid and whose overtime "
      "was approved since; not the Per Piece one with nothing, nor those with hours and no rate",
      sorted(row.employee for row in entry.employees))
s.settings.standard_hourly_rate = 2000
# arrears and anything else owed a casual, entered as Additional Salary, keep them though they have no days (Luuka,
# 11 Nov 2026: "arrears and additional salary should be done on the additional salary which is going be included when
# running payroll")
s = populated()
s.add("Employee", name="W9", company="LPL", custom_pay_category="Weekly", branch="North", status="Active",
      date_of_joining=D(2025, 1, 1))
s.pieces_waiting = {"W9"}
entry = PayrollEntry(name="PE-NEW", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, branch="North",
                     start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), employees=[])
entry.fill_employee_details()
check("W9" in [row.employee for row in entry.employees],
      "a casual by the hour with no days but arrears entered as Additional Salary in the week is kept, to be paid them",
      sorted(row.employee for row in entry.employees))
print("Get Employees: the structure and assignments made once, those to pay kept")


# a casual's Additional Salary is never cut by the days paid (Frappe HR cuts it where its component is cut by payment
# days, and a Per Piece casual is paid no days)
def additional(employee, component, ref=None):
    return Row(employee=employee, salary_component=component, ref_doctype=ref)


s = populated()
s.add("Employee", name="P9", company="LPL", custom_pay_category="Per Piece", branch="North", status="Active",
      date_of_joining=D(2025, 1, 1))
s.add("Employee", name="M9", company="LPL", custom_pay_category="Monthly", branch="North", status="Active",
      date_of_joining=D(2025, 1, 1))
s.add("Salary Component", name="Bonus Cut", depends_on_payment_days=1)
s.add("Salary Component", name="Arrears", depends_on_payment_days=0)
for employee in ("P9", "W1"):
    try:
        W.additional_validate(additional(employee, "Bonus Cut"))
        check(False, "a casual's Additional Salary under a component cut by the days paid is refused")
    except Thrown as error:
        check("Bonus Cut is cut by the days paid, and %s is a casual paid by the week" % employee in str(error)
              and "Untick Depends on Payment Days on Bonus Cut, or use a component that is not cut, such as Arrear."
              in str(error), "a casual's Additional Salary under a component cut by the days paid is refused, saying "
                             "what to do (%s)" % employee, str(error))
W.additional_validate(additional("P9", "Arrears"))
W.additional_validate(additional("M9", "Bonus Cut"))
W.additional_validate(additional("P9", "Bonus Cut", ref="Arrear"))
check(True, "under a component not cut it is taken; a monthly employee's is Frappe HR's as ever; an Arrear's is left "
            "whole by Frappe HR anyway")
# arrears a Per Piece run has paid for the week are not entered again by hand (Luuka, 12 Nov 2026: "arrears should work
# like additional salary and it should post to additional salary respectively")
# arrears are added under Arrear or taken back under Arrears Deductions (Luuka, 12 Nov 2026: arrears "can be addition
# or deduction"), and Arrears is what a run paid under before: each is guarded under its own name
for component in ("Arrear", "Arrears Deductions", "Arrears"):
    s.arrears_paid = {("P9", component): "OPR-2026-00004"}
    try:
        W.additional_validate(Row(employee="P9", salary_component=component, payroll_date=D(2026, 11, 2)))
        check(False, "a casual's arrears the week's run has paid under %s are not entered again by hand" % component)
    except Thrown as error:
        check("OPR-2026-00004 has paid P9's arrears for that week. Change them on that run, not here." in str(error),
              "a casual's arrears the week's run has paid under %s are not entered again by hand, saying which run"
              % component, str(error))
s.arrears_paid = {("P9", "Arrear"): "OPR-2026-00004"}
W.additional_validate(Row(employee="P9", salary_component="Arrears Deductions", payroll_date=D(2026, 11, 2)))
W.additional_validate(Row(employee="P9", salary_component="Arrear", payroll_date=D(2026, 11, 2),
                          ref_doctype="Output Pay Run"))
s.arrears_paid = {}
W.additional_validate(Row(employee="P9", salary_component="Arrear", payroll_date=D(2026, 11, 2)))
check(True, "a deduction beside an addition the run paid is taken, the run's own arrears are, and a casual's with "
            "none paid for the week")


# ── 4. The slip ──────────────────────────────────────────
def slip(employee="W1", start=D(2026, 10, 29), end=D(2026, 11, 4), frequency="Weekly", **values):
    return Form(name="SS-%s" % employee, employee=employee, company="LPL", payroll_frequency=frequency,
                salary_slip_based_on_timesheet=0, start_date=start, end_date=end, **values)


def submitted(site_, doc):
    site_.add("Salary Slip", name=doc.name, employee=doc.employee, payroll_frequency=doc.payroll_frequency,
              start_date=doc.start_date, end_date=doc.end_date, docstatus=1)
    for row in doc.custom_weekly_days:
        site_.add("Weekly Pay Day", parent=doc.name, docstatus=1, **row)


s = populated()
one = slip()
W.slip_before_validate(one)
W.slip_validate(one)
check([(row["attendance_date"], row["hours"]) for row in one.custom_weekly_days]
      == [(D(2026, 10, 29), 10.0), (D(2026, 10, 30), 10.0), (D(2026, 10, 31), 8.0), (D(2026, 11, 2), 5.0), (D(2026, 11, 3), 10.0),
          (D(2026, 11, 4), 10.0)] and all(row["employee"] == "W1" for row in one.custom_weekly_days),
      "a slip lists each day it pays and its hours: a twelve-hour day pays ten, an uploaded day the standard, the Absent day nothing",
      one.custom_weekly_days)
check(one.custom_weekly_hours == 53.0 and one.custom_weekly_rate == 2500 and one.flags.weekly_pay,
      "its hours and the person's own rate", (one.custom_weekly_hours, one.custom_weekly_rate))
check(one.custom_days_in_period == 7 and one.custom_days_paid == 6, "it shows the week's days and the days it pays")
two = slip("W2")
W.slip_before_validate(two)
check(two.custom_weekly_rate == 2000 and two.custom_weekly_hours == 20.0, "no rate of their own: the standard rate", two.custom_weekly_rate)
submitted(s, one)
s.add("Payroll Entry", name="PE-1", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=1,
      start_date=D(2026, 10, 29), end_date=D(2026, 11, 4))
s.rows("Attendance")[3]["docstatus"] = 2
s.add("Attendance", name="A-W1-LATE", employee="W1", attendance_date=D(2026, 11, 1), status="Present", working_hours=9, docstatus=1)
s.add("Attendance", name="A-W1-EARLY", employee="W1", attendance_date=D(2026, 10, 20), status="Present", working_hours=9, docstatus=1)
nxt = slip(start=D(2026, 11, 5), end=D(2026, 11, 11))
W.slip_before_validate(nxt)
check([(row["attendance_date"], row["hours"]) for row in nxt.custom_weekly_days] == [(D(2026, 11, 1), 9.0), (D(2026, 11, 5), 4.0)],
      "the next week's slip pays a day marked after its week was paid, and none twice; nothing from before weekly pay began",
      nxt.custom_weekly_days)
for row in s.rows("Weekly Pay Day"):
    row["docstatus"] = 2
nxt = slip(start=D(2026, 11, 5), end=D(2026, 11, 11))
W.slip_before_validate(nxt)
check(len(nxt.custom_weekly_days) == 8, "a cancelled slip gives its days back", nxt.custom_weekly_days)
s = populated()
s.add("Attendance", name="A-W1-OCT", employee="W1", attendance_date=D(2026, 10, 24), status="Present", working_hours=10, docstatus=1)
s.add("Salary Slip", name="SS-OCT", employee="W1", payroll_frequency="Monthly", start_date=D(2026, 9, 26), end_date=D(2026, 10, 25), docstatus=1)
moved = slip(start=D(2026, 10, 20), end=D(2026, 11, 4))
W.slip_before_validate(moved)
check(moved.custom_weekly_days[0]["attendance_date"] == D(2026, 10, 29) and len(moved.custom_weekly_days) == 6,
      "someone moved from monthly to weekly is not paid again for days their monthly slip paid", moved.custom_weekly_days[:2])
monthly_person = slip("M1")
W.slip_before_validate(monthly_person)
W.slip_validate(monthly_person)
check(monthly_person.get("custom_weekly_days") is None and not monthly_person.flags.get("weekly_pay")
      and monthly_person.get("custom_days_paid") is None, "a weekly slip for someone not paid by the week is left alone")
month_slip = slip("W1", start=D(2026, 9, 26), end=D(2026, 10, 25), frequency="Monthly")
W.slip_before_validate(month_slip)
check(month_slip.get("custom_weekly_days") is None, "and so is a monthly slip")
s.settings.standard_hours = 8
eight = slip()
W.slip_before_validate(eight)
check([row["hours"] for row in eight.custom_weekly_days][:4] == [8.0, 8.0, 8.0, 4.0],
      "the standard day is Output Pay Settings': at eight, a twelve-hour day pays eight and a Half Day four",
      [row["hours"] for row in eight.custom_weekly_days])
s.settings.standard_hours = 10
s.settings.standard_hourly_rate = 0
try:
    W.slip_before_validate(slip("W4"))
    check(False, "a slip with hours and no rate is refused")
except Thrown as error:
    check("W4 has hours but no hourly rate" in str(error), "a slip with hours and no rate is refused", str(error))

# the approved overtime: at their own rate x the multiplier the type gives the day, and none twice
s = populated()
s.add("Overtime Type", name="Casual OT", standard_multiplier=1.5, applicable_for_weekend=1, weekend_multiplier=2.0)
for row in s.rows("Attendance"):
    if row.name == "A-W1-1":
        row.update(actual_overtime_duration=2, overtime_type="Casual OT")
    if row.name == "A-W1-2":
        row.update(actual_overtime_duration=3, overtime_type="Casual OT")
    if row.name == "A-W1-6":
        row.update(actual_overtime_duration=4, overtime_type=None)
s.day_kinds[("W1", D(2026, 10, 31))] = OR.REST_DAY
paid_ot = slip()
W.slip_before_validate(paid_ot)
W.slip_validate(paid_ot)
check(paid_ot.custom_weekly_overtime_hours == 5.0 and paid_ot.custom_weekly_overtime == 2 * 2500 * 1.5 + 3 * 2500 * 2.0,
      "the slip pays the approved overtime: Friday's at 1.5, Saturday's at the weekend's 2; none not yet sent to payroll",
      (paid_ot.custom_weekly_overtime_hours, paid_ot.custom_weekly_overtime))
check([(row["attendance_date"], row["overtime_hours"]) for row in paid_ot.custom_weekly_days if row["overtime_hours"]]
      == [(D(2026, 10, 30), 2.0), (D(2026, 10, 31), 3.0)] and paid_ot.custom_weekly_hours == 53.0 and paid_ot.custom_days_paid == 6,
      "each day notes its overtime beside its hours; the hours and days are as before", paid_ot.custom_weekly_days)
submitted(s, paid_ot)
s.add("Payroll Entry", name="PE-1", company="LPL", payroll_frequency="Weekly", salary_slip_based_on_timesheet=0, docstatus=1,
      start_date=D(2026, 10, 29), end_date=D(2026, 11, 4))
for row in s.rows("Attendance"):
    if row.name == "A-W1-1":
        row.update(actual_overtime_duration=4)
later = slip(start=D(2026, 11, 5), end=D(2026, 11, 11))
W.slip_before_validate(later)
W.slip_validate(later)
check(later.custom_weekly_overtime_hours == 2.0 and later.custom_weekly_overtime == 2 * 2500 * 1.5
      and [(row["attendance_date"], row["hours"], row["overtime_hours"]) for row in later.custom_weekly_days]
      == [(D(2026, 10, 30), 0.0, 2.0), (D(2026, 11, 5), 4.0, 0.0)] and later.custom_days_paid == 1,
      "more overtime approved for a day already paid goes on the next slip, the day's hours not paid again",
      later.custom_weekly_days)
s = populated()
s.add("Overtime Type", name="Casual OT", standard_multiplier=1.5)
for row in s.rows("Attendance"):
    if row.name in ("A-W1-1", "A-W1-2"):
        row.update(actual_overtime_duration=2, overtime_type="Casual OT")
s.add("Overtime Slip", name="OTS-1", employee="W1", docstatus=1,
      overtime_details=[Row(reference_document="A-W1-1", overtime_duration=2)])
s.add("Overtime Slip", name="OTS-2", employee="W1", docstatus=2,
      overtime_details=[Row(reference_document="A-W1-2", overtime_duration=2)])
before_weekly = slip()
W.slip_before_validate(before_weekly)
check(before_weekly.custom_weekly_overtime_hours == 2.0 and before_weekly.custom_weekly_overtime == 2 * 2500 * 1.5,
      "hours a submitted Overtime Slip paid, before the casual was paid by the week, are not paid again; a cancelled "
      "one's are", (before_weekly.custom_weekly_overtime_hours, before_weekly.custom_weekly_days))
nothing = Site()
SITE[0] = nothing
nothing.add("Employee", name="W9", company="LPL", custom_pay_category="Weekly")
nothing.settings.standard_hourly_rate = 0
nothing.add("Weekly Pay Day", parent="SS-OLD", employee="W9", attendance_date=D(2026, 10, 30), hours=10, overtime_hours=0,
            docstatus=1)
nothing.add("Attendance", name="A-W9-0", employee="W9", attendance_date=D(2026, 10, 30), status="Present", working_hours=10,
            actual_overtime_duration=3, overtime_type="Casual OT", docstatus=1)
try:
    W.slip_before_validate(slip("W9"))
    check(False, "overtime with no rate to pay it at is refused too")
except Thrown as error:
    check("W9 has hours but no hourly rate" in str(error), "overtime with no rate to pay it at is refused too", str(error))

# a raise in the middle of the week: each day at the rate in force that day
s = populated()
s.add("Hourly Rate", name="HRATE-W1-NOV", employee="W1", rate=3000, from_date=D(2026, 11, 2))
s.add("Overtime Type", name="Casual OT", standard_multiplier=1.5)
for row in s.rows("Attendance"):
    if row.name in ("A-W1-1", "A-W1-5"):
        row.update(actual_overtime_duration=2, overtime_type="Casual OT")
raised = slip()
W.slip_before_validate(raised)
check([(row["attendance_date"], row["hours"], row["rate"]) for row in raised.custom_weekly_days]
      == [(D(2026, 10, 29), 10.0, 2500), (D(2026, 10, 30), 10.0, 2500), (D(2026, 10, 31), 8.0, 2500),
          (D(2026, 11, 2), 5.0, 3000), (D(2026, 11, 3), 10.0, 3000), (D(2026, 11, 4), 10.0, 3000)]
      and raised.custom_weekly_rate == 3000,
      "each day the slip pays shows the rate it is paid at: the old one before the raise, the new from its day",
      raised.custom_weekly_days)
check(raised.custom_weekly_overtime == 2 * 2500 * 1.5 + 2 * 3000 * 1.5,
      "and each day's overtime is at that day's rate", raised.custom_weekly_overtime)


class EvalBase:
    def get_data_for_eval(self):
        return {}, {}


class EvalSlip(W.SalarySlipWeekly, EvalBase, Form):
    pass


evaluated = EvalSlip(**{key: value for key, value in raised.__dict__.items() if key != "flags"})
data, _defaults = evaluated.get_data_for_eval()
check(data["weekly_pay"] == 28 * 2500 + 25 * 3000 and data["weekly_overtime"] == raised.custom_weekly_overtime,
      "the week's line is the days' hours each at its own rate, not all at the newest", data)
check(W.rates_of(["W1", "W2"], on=D(2026, 11, 1)) == {"W1": 2500, "W2": 2000.0}
      and W.rates_of(["W1"], on=D(2026, 11, 2)) == {"W1": 3000},
      "a casual's rate on a day: their own in force that day, else the standard rate", W.rates_of(["W1", "W2"], on=D(2026, 11, 1)))
s = populated()
s.settings.standard_hourly_rate = 0
for row in s.rows("Hourly Rate"):
    if row.employee == "W1":
        row["from_date"] = D(2026, 11, 2)
try:
    W.slip_before_validate(slip())
    check(False, "a day before the casual's first rate, with no standard rate, refuses the slip and says which day")
except Thrown as error:
    check("W1 has hours but no hourly rate on 29 Oct 2026" in str(error),
          "a day before the casual's first rate, with no standard rate, refuses the slip and says which day", str(error))
for values, needle, why in (({"rate": 900, "from_date": D(2025, 1, 1)}, "already have a rate from that day (HRATE-W3)",
                             "a second rate from the same day"),
                            ({"rate": 0, "from_date": D(2026, 12, 1)}, "more than nothing", "a rate of nothing")):
    try:
        W.rate_validate(Form(name="NEW", employee="W3", **values))
        check(False, "an Hourly Rate is refused: %s" % why)
    except Thrown as error:
        check(needle in str(error), "an Hourly Rate is refused: %s" % why, str(error))
W.rate_validate(Form(name="HRATE-W3", employee="W3", rate=3100, from_date=D(2025, 1, 1)))
check(True, "and a rate saved again is not taken for a second one")
print("the slip: each unpaid day once, late days on the next, nothing a monthly slip paid, the overtime once")

# ── 4b. The weeks a Casual Hours Sheet gives ─────────────
s = populated()
# a public holiday's overtime at 2 (the Employment Act's floor), a weekday's at 1.5
s.add("Overtime Type", name="Casual OT", standard_multiplier=1.5, applicable_for_public_holiday=1,
      public_holiday_multiplier=2.0)
s.add("Casual Hours Sheet", name="HR-CHS-1", company="LPL", branch="North", from_date=D(2026, 10, 29),
      to_date=D(2026, 11, 4), docstatus=1)
s.add("Casual Hours Row", name="CHR-1", parent="HR-CHS-1", parenttype="Casual Hours Sheet", docstatus=1, employee="W8",
      hours_worked=50, overtime_hours=6, days_worked=5, overtime_type="Casual OT")
s.add("Casual Hours Row", name="CHR-2", parent="HR-CHS-1", parenttype="Casual Hours Sheet", docstatus=1, employee="W1",
      hours_worked=40, overtime_hours=0, days_worked=4)
s.add("Attendance", name="A-W1-OT", employee="W1", attendance_date=D(2026, 10, 30), status="Present", working_hours=10,
      actual_overtime_duration=3, overtime_type="Casual OT", docstatus=1)
# the week ends on a public holiday: its overtime is still a weekday's, at 1.5, not all of it at the holiday's 2
s.day_kinds[("W8", D(2026, 11, 4))] = OR.PUBLIC_HOLIDAY
weekly_sheet = slip("W8")
W.slip_before_validate(weekly_sheet)
W.slip_validate(weekly_sheet)
check([(row["attendance_date"], row["hours"], row["overtime_hours"], row.get("hours_sheet"), row.get("days_worked"),
        row["rate"]) for row in weekly_sheet.custom_weekly_days] == [(D(2026, 11, 4), 50.0, 6.0, "HR-CHS-1", 5.0, 2500)],
      "an approved sheet's week is one row, dated its last day, at the week's hours and overtime: no ten-hour cap on "
      "a week's total", weekly_sheet.custom_weekly_days)
check((weekly_sheet.custom_weekly_hours, weekly_sheet.custom_weekly_overtime_hours, weekly_sheet.custom_weekly_overtime,
       weekly_sheet.custom_days_paid) == (50.0, 6.0, 22500.0, 5.0)
      and R.week_pay(weekly_sheet.custom_weekly_days, weekly_sheet.custom_weekly_hours, weekly_sheet.custom_weekly_rate)
      == 125000,
      "the hours at their own rate, the overtime at it times 1.5 with no cap, though the week ends on a public "
      "holiday, the days the sheet says",
      (weekly_sheet.custom_weekly_hours, weekly_sheet.custom_weekly_overtime, weekly_sheet.custom_days_paid))
attendance_ot = [{"attendance_date": D(2026, 11, 4), "overtime_type": "Casual OT"}]
check(W.multipliers("W8", attendance_ot) == {D(2026, 11, 4): 2.0},
      "an attendance day's overtime on that holiday is still the holiday's: only a sheet's week is taken as weekdays",
      W.multipliers("W8", attendance_ot))
both = slip("W1")
W.slip_before_validate(both)
check([(row["attendance_date"], row["hours"], row.get("hours_sheet")) for row in both.custom_weekly_days]
      == [(D(2026, 11, 4), 40.0, "HR-CHS-1")] and both.custom_weekly_overtime_hours == 0,
      "the sheet's week replaces the attendance's days and overtime in it: the week is paid once, not twice",
      both.custom_weekly_days)
# a casual the sheet leaves out is paid from the attendance, as the verification shows them (casual_hours.spans)
left_out = slip("W3")
W.slip_before_validate(left_out)
check([(row["attendance_date"], row.get("hours_sheet")) for row in left_out.custom_weekly_days]
      == [(D(2026, 10, 30), None)],
      "a casual the plant's sheet leaves out is paid from the attendance, never nothing", left_out.custom_weekly_days)
submitted(s, weekly_sheet)
again = slip("W8")
W.slip_before_validate(again)
check(not again.custom_weekly_days and not again.custom_weekly_overtime,
      "a week a submitted slip paid is not paid again", again.custom_weekly_days)
for row in s.rows("Weekly Pay Day"):
    if row.get("hours_sheet") == "HR-CHS-1":
        row["docstatus"] = 2
back = slip("W8")
W.slip_before_validate(back)
check([row.get("hours_sheet") for row in back.custom_weekly_days] == ["HR-CHS-1"],
      "a cancelled slip gives the week back", back.custom_weekly_days)
s.add("Casual Hours Sheet", name="HR-CHS-2", company="LPL", branch="North", from_date=D(2026, 10, 29),
      to_date=D(2026, 11, 4), docstatus=0)
s.add("Casual Hours Row", name="CHR-3", parent="HR-CHS-2", parenttype="Casual Hours Sheet", docstatus=0, employee="W2",
      hours_worked=30, days_worked=3)
not_yet = slip("W2")
W.slip_before_validate(not_yet)
check(not_yet.custom_weekly_hours == 20.0 and not any(row.get("hours_sheet") for row in not_yet.custom_weekly_days),
      "a sheet not yet approved pays nothing, and leaves the attendance's days as they were", not_yet.custom_weekly_days)
s.add("Casual Hours Sheet", name="HR-CHS-3", company="LPL", branch="North", from_date=D(2026, 11, 5),
      to_date=D(2026, 11, 11), docstatus=1)
s.add("Casual Hours Row", name="CHR-4", parent="HR-CHS-3", parenttype="Casual Hours Sheet", docstatus=1, employee="W7",
      hours_worked=45, days_worked=5)
seven = slip("W7")
W.slip_before_validate(seven)
check([(row["attendance_date"], row.get("hours_sheet")) for row in seven.custom_weekly_days] == [(D(2026, 10, 31), None)],
      "a week that ends after the slip waits for the slip that reaches it", seven.custom_weekly_days)
run = Form(name="PE-SHEETS", company="LPL", start_date=D(2026, 10, 29), end_date=D(2026, 11, 4), payroll_frequency="Weekly",
           salary_slip_based_on_timesheet=0, employees=[Row(employee=name) for name in ("W8", "W5")])
W._keep_those_to_pay(run)
check([row.employee for row in run.employees] == ["W8"],
      "Get Employees keeps a casual whose week only a sheet gives", [row.employee for row in run.employees])
figures = {"W8": {}, "W1": {}}
W.show_on_figures(Form(company="LPL", start_date=D(2026, 10, 29), end_date=D(2026, 11, 4)), figures)
check((figures["W8"]["custom_hours_worked"], figures["W8"]["custom_paid_days"], figures["W1"]["custom_hours_worked"],
       figures["W1"]["custom_paid_days"]) == (50.0, 5.0, 40.0, 4.0),
      "the Employees tab shows a sheet's hours and days, and none of the days it covers twice", figures)
s.rows("Attendance")[:] = [row for row in s.rows("Attendance") if as_date(row["attendance_date"]) < D(2026, 11, 2)]
check(W.dates_for("LPL")["end"] == D(2026, 11, 4),
      "a weekly payroll reaches the last day an approved sheet ends on, though nobody was marked on it",
      W.dates_for("LPL"))
check(R.days_paid([{"hours": 9}, {"hours": 0, "overtime_hours": 2}, {"hours": 40, "hours_sheet": "S", "days_worked": 4},
                   {"hours": 12, "hours_sheet": "T"}]) == 5.0,
      "the days paid: a day each, a sheet's days worked, none for overtime alone or a sheet that gives no days")
print("the sheets: a week at its totals, once, in place of its days; approved ones only; on the Employees tab")

# ── 5. Frappe HR's own methods, lifted from its source ───
SLIP_SOURCE = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_slip", "salary_slip.py")
SSA_SOURCE = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_structure_assignment", "salary_structure_assignment.py")
if os.path.exists(SLIP_SOURCE) and os.path.exists(SSA_SOURCE):
    def lifted(path, names, class_name):
        source = open(path, encoding="utf-8").read()
        bodies = []
        for name in names:
            found = re.search(r"^\tdef %s\(.*?(?=^\tdef |^\t@|^def |^@|^[A-Z_]+ = |\Z)" % name, source, re.S | re.M)
            assert found, name
            bodies.append(found.group(0))
        return source, "class %s:\n" % class_name + "".join(bodies)

    class Line(Row):
        def precision(self, field):
            return 2

        def set(self, key, value):
            self[key] = value

    GLOBALS = {"int": int, "float": float, "round": round, "min": min, "max": max}

    def safe_eval(code, eval_globals=None, eval_locals=None):
        return eval(code, {**GLOBALS, "__builtins__": {}}, eval_locals)

    component_flags = {"Hourly Earnings": Row(remove_if_zero_valued=1, round_to_the_nearest_integer=0),
                       "Casual Overtime": Row(remove_if_zero_valued=1, round_to_the_nearest_integer=0),
                       "PAYE Master": Row(remove_if_zero_valued=0, round_to_the_nearest_integer=0)}
    upstream = types.SimpleNamespace(
        get_cached_value=lambda doctype, name, field: (component_flags.get(name) or {}).get(field),
        db=types.SimpleNamespace(get_value=lambda doctype, name, field, cache=False: (component_flags.get(name) or {}).get(field)),
        msgprint=lambda *args, **kwargs: None, _dict=Row, throw=throw)
    slip_source, slip_class = lifted(SLIP_SOURCE, ("get_data_for_eval", "eval_condition_and_formula", "add_structure_components",
                                                   "add_structure_component", "update_component_row",
                                                   "update_component_amount_based_on_payment_days", "get_amount_based_on_payment_days",
                                                   "get_component_totals", "add_tax_components"), "LiftedSlip")
    namespace = {"frappe": upstream, "_": lambda text: text, "flt": lambda value, precision=None: round(float(value or 0), precision or 9),
                 "cint": lambda value: int(float(value or 0)), "rounded": round, "getdate": as_date, "_safe_eval": safe_eval,
                 "COMPONENT_PARENTFIELDS": ["earnings", "deductions", "employer_contributions"],
                 "get_component_eval_context": lambda employee, assignment: Row(base=0, HRE=0),
                 "get_salary_component_data": lambda name: Row(salary_component=name, abbr="PM", depends_on_payment_days=0),
                 "throw_error_message": lambda row, error, title=None, description=None: throw(title)}
    exec(slip_class, namespace)

    class FrappeSlip(namespace["LiftedSlip"]):
        def __init__(self, frequency, hours, rate, payment_days, depends, overtime=0):
            self.payroll_frequency, self.salary_slip_based_on_timesheet = frequency, 0
            self.custom_weekly_hours, self.custom_weekly_rate = hours, rate
            self.custom_weekly_overtime = overtime
            self.employee, self.salary_structure = "W1", "Weekly Casuals - LPT"
            self.total_working_days, self.payment_days = 7, payment_days
            self.start_date, self.joining_date, self.relieving_date = D(2026, 10, 29), D(2025, 1, 1), None
            self.payroll_period = None
            self.earnings, self.deductions, self.employer_contributions = [], [], []
            self.whitelisted_globals = GLOBALS
            self._salary_structure_assignment = Row()
            row = Row(salary_component="Hourly Earnings", abbr="HRE", amount_based_on_formula=1, formula="weekly_pay",
                      condition=None, amount=0, default_amount=0, depends_on_payment_days=depends, precision=2)
            extra = Row(salary_component="Casual Overtime", abbr="COT", amount_based_on_formula=1, formula="weekly_overtime",
                        condition=None, amount=0, default_amount=0, depends_on_payment_days=0, precision=2)
            self._evaluated_components = {"earnings": [row, extra], "deductions": [], "employer_contributions": []}

        def get(self, key, default=None):
            return getattr(self, key, default)

        def set(self, key, value):
            setattr(self, key, value)

        def append(self, key, value=None):
            line = Line(value or {})
            getattr(self, key).append(line)
            return line

        def remove(self, line):
            for key in ("earnings", "deductions"):
                if line in getattr(self, key):
                    getattr(self, key).remove(line)

        def as_dict(self):
            return Row(employee=self.employee, payment_days=self.payment_days, total_working_days=self.total_working_days,
                       custom_weekly_hours=self.custom_weekly_hours, custom_weekly_rate=self.custom_weekly_rate)

        def is_new(self):
            return True

        def get_tax_components(self):
            return ["PAYE Master"]

        def handle_additional_salary_tax_component(self):
            return False

        def calculate_variable_based_on_taxable_salary(self, component):
            self._component_based_variable_tax[component] = {"current_tax_amount": 999.0}

    class WeeklySlip(W.SalarySlipWeekly, FrappeSlip):
        pass

    def worked(cls, frequency="Weekly", depends=0, overtime=0):
        doc = cls(frequency, 53.0, 2500, 4, depends, overtime)
        doc.add_structure_components("earnings")
        doc.add_tax_components()
        return doc, doc.get_component_totals("earnings", depends_on_payment_days=1)

    week, gross = worked(WeeklySlip)
    line = week.earnings[0] if week.earnings else Row()
    check(line.salary_component == "Hourly Earnings" and line.amount == 132500.0 and line.default_amount == 132500.0 and gross == 132500.0,
          "Frappe HR's own slip code pays the week's line as hours x rate, though the week had absences", (dict(line), gross))
    check(week.deductions == [] and week._component_based_variable_tax == {} and week.other_deduction_components == [],
          "and adds no tax line to a weekly slip", week.deductions)
    check([line.salary_component for line in week.earnings] == ["Hourly Earnings"],
          "a week with no overtime has no overtime line", [line.salary_component for line in week.earnings])
    ot_week, ot_gross = worked(WeeklySlip, overtime=22500.0)
    check([(line.salary_component, line.amount) for line in ot_week.earnings]
          == [("Hourly Earnings", 132500.0), ("Casual Overtime", 22500.0)] and ot_gross == 155000.0,
          "the overtime line pays what the slip worked out, whole, though the week had absences",
          [(line.salary_component, line.amount) for line in ot_week.earnings])
    month, _gross = worked(WeeklySlip, frequency="Monthly")
    check([line.salary_component for line in month.deductions] == ["PAYE Master"],
          "while a slip whose structure has no tax line is given the Salary Component master's: the trap the weekly slip is kept from",
          month.deductions)
    cut_week, cut_gross = worked(WeeklySlip, depends=1)
    check(cut_week.earnings and round(cut_gross) == round(132500 * 4 / 7),
          "a line cut by payment days would take the absences off twice, which is why structure_for refuses that earning", cut_gross)
    try:
        worked(FrappeSlip)
        failed_plain = False
    except Thrown:
        failed_plain = True
    check(failed_plain, "without the slip's mixin the formula has nothing to read, and the slip is refused")

    ssa_source, ssa_class = lifted(SSA_SOURCE, ("_evaluate_component_table",), "LiftedAssignment")
    flags = re.search(r"^SALARY_COMPONENT_FLAGS = \((.*?)\)\n", ssa_source, re.S | re.M)
    named_error = []
    ssa_namespace = {"frappe": upstream, "_": lambda text: text, "flt": lambda value, precision=None: float(value or 0),
                     "sanitize_expression": lambda code: code.strip() if code else code, "_safe_eval": safe_eval,
                     "COMPONENT_EVAL_GLOBALS": GLOBALS, "SALARY_COMPONENT_FLAGS": ast.literal_eval("(" + flags.group(1) + ")"),
                     "throw_error_message": lambda row, error, title=None, description=None: named_error.append(title)}
    exec(ssa_class, ssa_namespace)

    class FrappeAssignment(ssa_namespace["LiftedAssignment"]):
        def _get_component_eval_context(self):
            return Row(base=0, HRE=0)

    class WeeklyAssignment(W.SalaryStructureAssignmentWeekly, FrappeAssignment):
        pass

    structure_line = Line(salary_component="Hourly Earnings", abbr="HRE", amount_based_on_formula=1, formula="weekly_pay", amount=0)
    overtime_line = Line(salary_component="Casual Overtime", abbr="COT", amount_based_on_formula=1, formula="weekly_overtime",
                         amount=0)
    rows = WeeklyAssignment()._evaluate_component_table([structure_line, overtime_line],
                                                        WeeklyAssignment()._get_component_eval_context())
    check(len(rows) == 2 and all(row.default_amount == 0 for row in rows) and not named_error,
          "the assignment works both lines out to nothing, with no error", rows)
    try:
        FrappeAssignment()._evaluate_component_table([structure_line], FrappeAssignment()._get_component_eval_context())
    except NameError:
        named_error.append("raised")
    check(named_error, "without the assignment's mixin the formula would fail on every assignment", named_error)
else:
    print("Frappe HR's source not found here: its own methods not lifted")

# ── 6. The Employees tab, and reads ──────────────────────
s = populated()
s.add("Employee", name="P1", company="LPL", custom_pay_category="Per Piece", branch="North", status="Active")
s.add("Attendance", name="A-P1-0", employee="P1", attendance_date=D(2026, 10, 30), status="Present", working_hours=10, docstatus=1)
figures = {"W1": {"custom_working_days": 31, "custom_paid_days": 31}, "W2": {"custom_working_days": 31, "custom_paid_days": 31},
           "P1": {"custom_working_days": 31, "custom_paid_days": 31}}
W.show_on_figures(Form(company="LPL", start_date=D(2026, 10, 29), end_date=D(2026, 11, 4)), figures)
check(figures == {"W1": {"custom_working_days": 7, "custom_paid_days": 6, "custom_hours_worked": 53.0},
                  "W2": {"custom_working_days": 7, "custom_paid_days": 2, "custom_hours_worked": 20.0},
                  "P1": {"custom_working_days": 7, "custom_paid_days": 0, "custom_hours_worked": 0}},
      "a weekly payroll's tab shows the days and the hours its slips will pay (12 marked paid as the full 10, a half "
      "day 5, a day marked with none 10; Luuka, 12 Nov 2026); a Per Piece casual's none, their pay being their bags",
      figures)


def reads(count):
    many = Site()
    SITE[0] = many
    for number in range(count):
        name = "P%04d" % number
        many.add("Employee", name=name, company="LPL", custom_pay_category="Weekly")
        many.add("Hourly Rate", name="HRATE-" + name, employee=name, rate=2500, from_date=D(2025, 1, 1))
        many.add("Attendance", employee=name, attendance_date=D(2026, 10, 30), status="Present", working_hours=10, docstatus=1)
    names = ["P%04d" % number for number in range(count)]
    many.calls.clear()
    found = W.days_to_pay(names, D(2026, 10, 29), D(2026, 11, 4), "LPL")
    W.rates_of(names)
    W.overtime_due(names, D(2026, 10, 29), D(2026, 11, 4), "LPL")
    return len(many.calls), found


few_reads, _few = reads(3)
many_reads, many_found = reads(2000)
# two of the reads are the Casual Hours Sheets', the same however many people (casual_hours.spans)
check(few_reads == many_reads <= 11 and len(many_found["P1999"]) == 1,
      "2,000 people take no more reads than 3: %d and %d" % (many_reads, few_reads))
print("the Employees tab: the days the slips will pay, read for everyone at once")

# ── 7. Wiring ────────────────────────────────────────────
custom = {row["name"]: row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))}
category = custom["Employee-custom_pay_category"]
check(category["options"].split("\n") == ["Regular", "Per Meter", "Per Piece", "Weekly"],
      "the Pay Category says Weekly, not Hourly, and Regular, not Monthly", category["options"])
check("Employee-custom_hourly_rate" not in custom and not [row for row in custom.values() if row["dt"] == "Employee"
                                                        and "hourly" in row["fieldname"]],
      "the hourly rate is not on the employee's record, where its holder could change it")
rate_meta = json.load(open(os.path.join(APP, "doctype", "hourly_rate", "hourly_rate.json"), encoding="utf-8"))
rate_fields = {field["fieldname"]: field for field in rate_meta["fields"]}
check(rate_meta["name"] == "Hourly Rate" and not rate_meta.get("istable") and rate_meta.get("track_changes") == 1
      and rate_meta.get("allow_import") == 1
      and all(rate_fields[name].get("reqd") == 1 for name in ("employee", "rate", "from_date"))
      and rate_fields["employee"]["options"] == "Employee" and rate_fields["branch"].get("fetch_from") == "employee.branch",
      "an Hourly Rate is its own record: who, the rate, from when; every change kept; its plant, so a user held to a "
      "plant sees only that plant's")
check({perm["role"] for perm in rate_meta["permissions"]} == {"System Manager", "HR Manager", "HR User"}
      and not next(perm for perm in rate_meta["permissions"] if perm["role"] == "HR User").get("delete"),
      "and only HR open it: the HR Manager, and the HR officer (HR User), who may not delete one")
sys.modules.pop("hrms_addon.hrms_addon.security_rules", None)
SECURITY = load("security_rules", register=False)
check("Hourly Rate" in SECURITY.HR_ONLY and "Hourly Rate" not in SECURITY.read_only_grants(["Hourly Rate", "Output Rate"])
      and "Output Rate" in SECURITY.read_only_grants(["Hourly Rate", "Output Rate"]),
      "nor do the read-only roles: an auditor reads the rates on the slips, not the rates themselves")
day_meta = json.load(open(os.path.join(APP, "doctype", "weekly_pay_day", "weekly_pay_day.json"), encoding="utf-8"))
check(any(field["fieldname"] == "rate" and field.get("read_only") == 1 and field.get("in_list_view") == 1
          for field in day_meta["fields"])
      and sum(field.get("columns") or 0 for field in day_meta["fields"] if field.get("in_list_view")) <= 10,
      "each day on a slip shows the rate it was paid at, within the grid's ten columns")
output_meta = json.load(open(os.path.join(APP, "doctype", "output_rate", "output_rate.json"), encoding="utf-8"))
check(output_meta.get("allow_import") == 1 and all(perm.get("import") for perm in output_meta["permissions"]
                                                  if perm.get("write") and perm.get("create")),
      "Sizes and Work Units may be imported, by those who keep them")
navigation = read("hrms_addon", "hrms_addon", "navigation_rules.py")
check('("Hourly Rates", "Hourly Rate", DOCTYPE),' in navigation
      and '("Hourly Rates", "Hourly Rate", DOCTYPE, "Setup", None),' in navigation,
      "the rates are on the Payroll page, beside the Sizes and Work Units: a link only those who may open them see")
check("hrms_addon.patches.v1_0.hourly_rates_off_employee" in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
      and "hrms_addon.patches.v1_0.output_rate_import" in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1],
      "the patches run after the doctypes are synced, so the Hourly Rate is there to move the rates to")

# the patch: each rate on an employee becomes their Hourly Rate from the day they joined, and the field goes
moved_site = Site()
moved_site.add("Employee", name="C1", custom_hourly_rate=857, date_of_joining=D(2026, 3, 2))
moved_site.add("Employee", name="C2", custom_hourly_rate=1700, date_of_joining=None)
moved_site.add("Employee", name="C3", custom_hourly_rate=0, date_of_joining=D(2026, 3, 2))
moved_site.add("Employee", name="C4", custom_hourly_rate=1000, date_of_joining=D(2026, 3, 2))
moved_site.add("Hourly Rate", name="HRATE-C4", employee="C4", rate=1000, from_date=D(2026, 3, 2))
moved_site.add("Custom Field", name="Employee-custom_hourly_rate")
moved_site.add("DocType", name="Hourly Rate")
deleted = []
patch_site = types.SimpleNamespace(
    db=types.SimpleNamespace(exists=moved_site.exists, has_column=lambda doctype, column: True),
    get_all=moved_site.get_all, get_doc=moved_site.get_doc,
    delete_doc=lambda doctype, name, **kwargs: deleted.append((doctype, name)) or moved_site.tables[doctype].clear())
patch_utils = types.ModuleType("frappe.utils")
patch_utils.getdate = as_date
sys.modules["frappe"], sys.modules["frappe.utils"] = patch_site, patch_utils
spec = importlib.util.spec_from_file_location("hourly_rates_off_employee",
                                              os.path.join(PACKAGE, "patches", "v1_0", "hourly_rates_off_employee.py"))
rate_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate_patch)
rate_patch.execute()
rate_patch.execute()
sys.modules["frappe"], sys.modules["frappe.utils"] = frappe, utils
check(sorted((row.employee, row.rate, row.from_date) for row in moved_site.rows("Hourly Rate"))
      == [("C1", 857, D(2026, 3, 2)), ("C2", 1700, D(2025, 1, 1)), ("C4", 1000, D(2026, 3, 2))]
      and deleted == [("Custom Field", "Employee-custom_hourly_rate")],
      "the patch moves each rate on an employee to an Hourly Rate from the day they joined, once, and takes the "
      "field off the employee", (sorted((row.employee, row.rate, row.from_date) for row in moved_site.rows("Hourly Rate")),
                                  deleted))

# the deploy makes each company's weekly structure, its Casual Overtime line and earning, so they are there to see
ready_site = Site()
for name, company, category in (("C1", "LPL", "Weekly"), ("C2", "LPL", "Per Piece"), ("C3", "OTHER", "Weekly"),
                                 ("C4", "BROKEN", "Weekly"), ("M1", "STAFF", "Regular")):
    ready_site.add("Employee", name=name, company=company, custom_pay_category=category)
made_for, logged, rolled = [], [], []


def made(company):
    made_for.append(company)
    if company == "BROKEN":
        raise Thrown("Hourly Earnings is cut by payment days")
    return "Weekly Casuals"


ready_frappe = types.SimpleNamespace(
    db=types.SimpleNamespace(has_column=lambda doctype, column: True, savepoint=lambda name: None,
                             rollback=lambda save_point=None: rolled.append(save_point)),
    get_all=ready_site.get_all, log_error=lambda title=None, **kwargs: logged.append(title))
real_structure_for = W.structure_for
W.structure_for = made
sys.modules["frappe"] = ready_frappe
spec = importlib.util.spec_from_file_location("casual_overtime_ready",
                                              os.path.join(PACKAGE, "patches", "v1_0", "casual_overtime_ready.py"))
ready_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ready_patch)
ready_patch.execute()
sys.modules["frappe"] = frappe
W.structure_for = real_structure_for
check(made_for == ["BROKEN", "LPL", "OTHER"] and logged == ["HRMS Addon: the casuals' weekly structure for BROKEN"]
      and rolled == ["casual_overtime_ready"],
      "the deploy makes the weekly structure, with its Casual Overtime line and earning, for each company with casuals, "
      "once a company; one that cannot be made is logged and undone, and the rest go on", (made_for, logged, rolled))
check("hrms_addon.patches.v1_0.casual_overtime_ready" in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1],
      "after the doctypes are synced")

# HR may import the casuals' Overtime Type: Frappe HR's allows import but gives no role the right
granted = []
grant_frappe = types.SimpleNamespace(db=types.SimpleNamespace(exists=lambda doctype, name: True))
security_stub = types.ModuleType("hrms_addon.hrms_addon.security")
security_stub.grant = lambda grants, permlevel=0: granted.append(grants)
saved_security = sys.modules.get("hrms_addon.hrms_addon.security")
sys.modules["frappe"], sys.modules["hrms_addon.hrms_addon.security"] = grant_frappe, security_stub
app.security = security_stub
spec = importlib.util.spec_from_file_location("overtime_type_import",
                                              os.path.join(PACKAGE, "patches", "v1_0", "overtime_type_import.py"))
type_patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(type_patch)
type_patch.execute()
sys.modules["frappe"] = frappe
if saved_security is None:
    sys.modules.pop("hrms_addon.hrms_addon.security", None)
    del app.security
else:
    sys.modules["hrms_addon.hrms_addon.security"] = saved_security
check(granted == [{"Overtime Type": {"System Manager": ("import",), "HR Manager": ("import",)}}]
      and "hrms_addon.patches.v1_0.overtime_type_import" in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1],
      "the HR Manager and the System Manager may import Overtime Types, as Administrator alone could", granted)
setters = {row["name"]: row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "property_setter.json"),
                                                     encoding="utf-8"))}
allow = setters.get("Overtime Type-main-allow_import") or {}
check((allow.get("doc_type"), allow.get("doctype_or_field"), allow.get("property"), allow.get("value"))
      == ("Overtime Type", "DocType", "allow_import", "1")
      and '"Overtime Type-main-allow_import",' in read("hrms_addon", "hooks.py"),
      "and Overtime Type allows import on every site, Data Import refusing it otherwise: a Property Setter the "
      "fixtures sync", allow)
chain = [("Salary Slip-custom_weekly_section", "Section Break", "base_hour_rate"),
         ("Salary Slip-custom_weekly_hours", "Float", "custom_weekly_section"),
         ("Salary Slip-custom_weekly_rate", "Currency", "custom_weekly_hours"),
         ("Salary Slip-custom_weekly_days", "Table", "custom_weekly_rate"),
         ("Salary Slip-custom_weekly_overtime_hours", "Float", "custom_weekly_days"),
         ("Salary Slip-custom_weekly_overtime", "Currency", "custom_weekly_overtime_hours")]
check(all(name in custom and custom[name]["fieldtype"] == fieldtype and custom[name]["insert_after"] == after for name, fieldtype, after in chain),
      "the slip's Weekly Pay section, one field after another under Frappe HR's hourly wages")
check(all(custom[name].get("read_only") == 1 and custom[name].get("no_copy") == 1 for name, _t, _a in chain[1:])
      and custom["Salary Slip-custom_weekly_days"]["options"] == "Weekly Pay Day"
      and custom["Salary Slip-custom_weekly_overtime"]["options"] == "currency"
      and custom["Salary Slip-custom_weekly_section"]["depends_on"] == "eval:doc.payroll_frequency=='Weekly'",
      "written by the server only, and shown on a weekly slip only")
meta = json.load(open(os.path.join(APP, "doctype", "weekly_pay_day", "weekly_pay_day.json"), encoding="utf-8"))
fields = {field["fieldname"]: field for field in meta["fields"]}
check(meta["istable"] == 1 and meta["name"] == "Weekly Pay Day"
      and set(fields) == {"attendance_date", "status", "hours", "rate", "overtime_hours", "employee", "hours_sheet",
                          "days_worked"}
      and fields["hours_sheet"].get("options") == "Casual Hours Sheet" and fields["hours_sheet"].get("search_index") == 1
      and fields["overtime_hours"]["fieldtype"] == "Float"
      and fields["employee"].get("search_index") == 1 and fields["attendance_date"].get("search_index") == 1
      and all(field.get("read_only") == 1 for field in fields.values()),
      "a day a slip paid: its date and its person indexed, as the paid days are read by them")
hooks_source = read("hrms_addon", "hooks.py")
check('"validate": "hrms_addon.hrms_addon.weekly_pay.additional_validate",' in hooks_source,
      "every Additional Salary is checked for a casual's on save")
hooks = {}
for node in ast.parse(hooks_source).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
extended, events = hooks["extend_doctype_class"], hooks["doc_events"]
METHOD = "hrms_addon.hrms_addon.weekly_pay."
check(METHOD + "SalarySlipWeekly" in extended["Salary Slip"] and METHOD + "PayrollEntryWeekly" in extended["Payroll Entry"]
      and METHOD + "SalaryStructureAssignmentWeekly" in extended["Salary Structure Assignment"],
      "the slip, the payroll and the assignment take weekly pay's methods")
check(events["Salary Slip"]["before_validate"][-1] == METHOD + "slip_before_validate"
      and events["Salary Slip"]["validate"][-1] == METHOD + "slip_validate"
      and METHOD + "payroll_validate" in events["Payroll Entry"]["validate"],
      "a slip's days are worked out before it is, its days shown after; a payroll's Start is held")
check(all(name in hooks_source for name, _t, _a in chain), "the slip's fields are in the fixtures the app syncs")
patches = read("hrms_addon", "patches.txt").split()
check("hrms_addon.patches.v1_0.hourly_casuals_weekly" in patches, "the patch that moves Hourly to Weekly runs")
moved = []
patch_frappe = types.SimpleNamespace(db=types.SimpleNamespace(has_column=lambda doctype, column: True,
                                                                 set_value=lambda *args, **kwargs: moved.append((args, kwargs))))
sys.modules["frappe"] = patch_frappe
spec = importlib.util.spec_from_file_location("hourly_casuals_weekly", os.path.join(PACKAGE, "patches", "v1_0", "hourly_casuals_weekly.py"))
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.execute()
sys.modules["frappe"] = frappe
check(moved == [(("Employee", {"custom_pay_category": "Hourly"}, "custom_pay_category", "Weekly"), {"update_modified": False})],
      "and moves everyone tagged Hourly in one statement", moved)
script = read("hrms_addon", "public", "js", "payroll_entry.js")
for needle, why in (('const HA_WEEKLY_METHOD = "hrms_addon.hrms_addon.weekly_pay.dates_for";', "the form asks the method the server whitelists"),
                    ("ha_weekly(frm);", "on refresh"),
                    ("branch: ha_weekly_changed,", "and again for another plant"),
                    ("grade: ha_weekly_changed,", "or another filter"),
                    ('ha_weekly_put(frm, "start_date", dates.start);', "the dates written straight on, so Frappe HR does not move the End"),
                    ('if (dates && dates.last) frm.toggle_enable("start_date", false);', "a Start that follows the last payroll is not typed")):
    check(needle in script, "the form: %s" % why, needle)
check("@frappe.whitelist()\ndef dates_for(" in read("hrms_addon", "hrms_addon", "weekly_pay.py"), "the method is whitelisted")
run_meta = json.load(open(os.path.join(APP, "doctype", "output_pay_run", "output_pay_run.json"), encoding="utf-8"))
section = next(field for field in run_meta["fields"] if field["fieldname"] == "section")
check(section["options"].split("\n") == ["Per Meter", "Per Piece"], "an Output Pay Run is for Per Meter or Per Piece: the casuals are paid weekly")
check('if doc.get("section") == rules.PER_PIECE:' in read("hrms_addon", "hrms_addon", "output_pay.py").split("def _set_period")[1][:300]
      and "Per Piece casuals are paid by the week: upload their sheet" not in read("hrms_addon", "hrms_addon", "output_pay.py"),
      "a Per Piece run is for a week, not a month: it feeds the weekly payroll, which pays it (Luuka, 11 Nov 2026)")
glue = read("hrms_addon", "hrms_addon", "output_pay.py")
check("_fill_hours" not in glue and "_price_hours" not in glue and "custom_pay_category\": rules.HOURLY" not in glue,
      "and it no longer pays anyone by the hour")
weekly_glue = read("hrms_addon", "hrms_addon", "weekly_pay.py")
check('OVERTIME_COMPONENT = ("Casual Overtime", "COT")' in weekly_glue
      and 'WEEKLY_OVERTIME, WEEKLY_OVERTIME_HOURS = "Casual Overtime", "custom_weekly_overtime_hours"'
      in read("hrms_addon", "hrms_addon", "payslip.py"),
      "the Pay Slip knows the overtime line by the name it is made under, and prints its hours beside it")
check("deductions" not in weekly_glue.split("def structure_for")[1].split("def _give_account")[0],
      "the weekly structure is made with no deductions at all")
print("wiring: the fields, the doctype, the hooks, the patch, the form")

# ── 8. Upstream ──────────────────────────────────────────
if os.path.exists(SLIP_SOURCE):
    entry_source = read_upstream = open(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_entry", "payroll_entry.py"),
                                        encoding="utf-8").read()
    slip_text = open(SLIP_SOURCE, encoding="utf-8").read()
    ssa_text = open(SSA_SOURCE, encoding="utf-8").read()
    document = open(os.path.join(APPS_ROOT, "frappe", "frappe", "model", "document.py"), encoding="utf-8").read()
    for text, needle, why in (
            (entry_source, "def fill_employee_details(self)", "Get Employees is a method of the Payroll Entry that can be built on"),
            (entry_source, "(SalaryStructureAssignment.payroll_payable_account == filters.payroll_payable_account)",
             "it finds people by their assignment, so each casual needs one"),
            (entry_source, "query = query.where(SalaryStructure.payroll_frequency == payroll_frequency)", "on a structure of the payroll's frequency"),
            (slip_text, "tax_components = self.get_tax_components()", "a slip with no tax line is given the master's"),
            (slip_text, "self._evaluated_components = self._get_ssa_doc().get_evaluated_components()", "the slip's lines come from the assignment"),
            (ssa_text, "def _get_component_eval_context(self) -> frappe._dict:", "which works them out in its own context"),
            (slip_text, "self.data, self.default_data = self.get_data_for_eval()", "and the slip again in its own"),
            (document, 'self.run_method("before_validate")', "a slip's days are worked out again as it is submitted"),
            (document, 'd.set("docstatus", docstatus)', "and its days are submitted and cancelled with it")):
        check(needle in text, "upstream: %s" % why, needle)
else:
    print("Frappe HR's source not found here: upstream not checked")

print()
print("FAILED: %d" % len(fail) if fail else "ALL WEEKLY PAY CHECKS PASSED")
sys.exit(1 if fail else 0)
