"""Checks what a payroll's Employees tab shows before its slips are made, without a bench:

    python scripts/verify_slip_figures.py

Luuka, 1 Nov 2026: "this information doesnt populate after fetching employee",
"we have over 2000 employees". slip_figures.py reads the whole payroll at once;
slip_figures_rules.py comes to what a slip comes to:

  1  the days, as Frappe HR's slip counts them on attendance
  2  a structure's lines for a whole month, as the assignment works them out
  3  the rows a slip would have, and what each is paid for the days
  4  the glue, on a stand-in for Frappe with real filters: who is read, what is
     left unread, Luuka's month, the figures a row is given
  5  the number of reads does not grow with the number of people
  6  upstream: what it stands on in Frappe HR
"""
import datetime
import glob
import importlib.util
import json
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []
D = datetime.date


def check(condition, label, detail=""):
    if not condition:
        fail.append(label)
        print("FAIL", label, detail)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("slip_figures_rules")  # proves it has no Frappe import
pay_days_rules = load("pay_days_rules")
payslip_rules = load("payslip_rules")
print("loaded slip_figures_rules.py without Frappe")

START, END = D(2026, 8, 26), D(2026, 9, 25)
SUNDAYS = {D(2026, 8, 30), D(2026, 9, 6), D(2026, 9, 13), D(2026, 9, 20)}
COUNTED = {"include_holidays_in_total_working_days": 1, "consider_marked_attendance_on_holidays": 0,
           "daily_wages_fraction_for_half_day": 0.5, "consider_unmarked_attendance_as": "Present"}
LEAVE = {"Without Pay": {"is_lwp": 1, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0, "include_holiday": 0},
         "Part Paid": {"is_lwp": 0, "is_ppl": 1, "fraction_of_daily_salary_per_leave": 0.75, "include_holiday": 1}}


def days(attendance=(), joining=None, relieving=None, holidays=SUNDAYS, settings=COUNTED, marked=()):
    return R.days_of(START, END, joining, relieving, holidays, list(attendance), settings, LEAVE, marked)


def day(when, status, leave_type=None, half=None):
    return {"attendance_date": when, "status": status, "leave_type": leave_type, "half_day_status": half}


FULL = {"working": 31, "on_payroll": 31, "counted_from": 31, "paid": 31.0, "without_pay": 0.0, "absent": 0.0}
TUESDAY, SUNDAY = D(2026, 9, 1), D(2026, 9, 6)

# ── 1. The days ──────────────────────────────────────────
check(days() == FULL, "a whole month with nothing marked off", days())
now = days([day(TUESDAY, "Absent")])
check((now["paid"], now["absent"]) == (30.0, 1.0), "a day absent", now)
now = days([day(SUNDAY, "Absent")])
check((now["paid"], now["absent"]) == (31.0, 0.0), "an absence on a holiday is not counted", now)
now = days([day(SUNDAY, "Absent")], settings=dict(COUNTED, consider_marked_attendance_on_holidays=1))
check((now["paid"], now["absent"]) == (30.0, 1.0), "unless Payroll Settings count what is marked on holidays", now)
now = days([day(SUNDAY, "Absent")], settings=dict(COUNTED, consider_marked_attendance_on_holidays="1",
                                                  include_holidays_in_total_working_days="0"))
check(now["absent"] == 0.0, "which they can only do where holidays are counted at all", now)
now = days([day(TUESDAY, "Half Day", half="Absent")])
check((now["paid"], now["absent"], now["without_pay"]) == (30.5, 0.5, 0.0), "half a day absent is half", now)
now = days([day(TUESDAY, "Half Day", half="Present")])
check((now["paid"], now["absent"]) == (31.0, 0.0), "a half day at work takes nothing", now)
now = days([day(SUNDAY, "Half Day", half="Absent")])
check((now["paid"], now["absent"]) == (31.0, 0.0), "nor one on a holiday", now)
now = days([day(TUESDAY, "Half Day", half="Absent")], settings=dict(COUNTED, daily_wages_fraction_for_half_day=0.25))
check((now["paid"], now["absent"]) == (30.75, 0.25), "the half day is Payroll Settings' fraction", now)
now = days([day(TUESDAY, "On Leave", leave_type="Annual")])
check(now == FULL, "paid leave takes nothing", now)
now = days([day(TUESDAY, "On Leave", leave_type="Without Pay")])
check((now["paid"], now["absent"], now["without_pay"]) == (30.0, 0.0, 1.0), "leave without pay is no absence, and is paid no day", now)
now = days([day(SUNDAY, "On Leave", leave_type="Without Pay")])
check(now["without_pay"] == 0.0, "nor on a holiday, where the leave type leaves holidays out", now)
now = days([day(SUNDAY, "On Leave", leave_type="Part Paid")])
check(now["without_pay"] == 0.75, "and does where it includes them", now)
now = days([day(TUESDAY, "On Leave", leave_type="Part Paid")])
check((now["paid"], now["without_pay"]) == (30.25, 0.75), "part paid leave takes its share of the day", now)
now = days([day(TUESDAY, "Half Day", leave_type="Without Pay", half="Present")])
check((now["paid"], now["without_pay"]) == (30.5, 0.5), "half a day of leave without pay", now)
now = days([day(TUESDAY, "Half Day", leave_type="Annual", half="Present")])
check(now == FULL, "half a day of paid leave", now)

now = days(joining=D(2026, 9, 15))
check((now["on_payroll"], now["counted_from"], now["paid"]) == (11, 11, 11.0), "joined in the period: the days from then", now)
now = days(joining=START)
check(now == FULL, "joined on the first day: all of it", now)
now = days(joining=D(2026, 10, 1))
check((now["counted_from"], now["paid"]) == (0, 0.0), "joined after it: none", now)
now = days(relieving=D(2026, 9, 10))
check((now["on_payroll"], now["paid"]) == (16, 16.0), "left in the period: the days to then", now)
now = days(relieving=END)
check(now == FULL, "left on the last day: all of it", now)
now = days(relieving=D(2026, 10, 10))
check(now == FULL, "leaving after it: all of it", now)
now = days(relieving=D(2026, 8, 1))
check(now == FULL, "and a leaving date before it is not read as the end of it, as Frappe HR does not", now)
now = days([day(D(2026, 9, 20), "Absent"), day(D(2026, 9, 15), "Absent")], relieving=D(2026, 9, 10))
check(now["absent"] == 0.0, "attendance after they left is not counted", now)
now = days([day(D(2026, 8, 28), "Absent")], joining=D(2026, 9, 15))
check((now["absent"], now["paid"]) == (1.0, 10.0), "before they joined it is, as Frappe HR reads from the period's start", now)
now = days([day(D(2026, 8, 28), "Half Day", half="Absent")], joining=D(2026, 9, 15))
check(now["absent"] == 0.0, "but a half day there is not, as Frappe HR reads those from when they joined", now)

left_out = dict(COUNTED, include_holidays_in_total_working_days=0)
now = days(settings=left_out)
check((now["working"], now["counted_from"], now["paid"]) == (27, 27, 27.0), "holidays left out of the count", now)
now = days(joining=D(2026, 9, 15), settings=left_out)
check((now["counted_from"], now["paid"]) == (10, 10.0), "only those in the time on the payroll, from when they joined", now)
now = days(holidays=None)
check(now == FULL, "no holiday list", now)
now = days([day(TUESDAY, "On Leave", leave_type="Without Pay")] + [day(D(2026, 9, 2), "Absent")],
           joining=END)
check((now["counted_from"], now["paid"], now["absent"]) == (1, 0.0, 1.0), "leave without pay that takes every day: nothing paid, and nothing more counted", now)

absent_if_unmarked = dict(COUNTED, consider_unmarked_attendance_as="Absent")
every_day = [START + datetime.timedelta(days=offset) for offset in range(31)]
workdays = [when for when in every_day if when not in SUNDAYS]
now = days(settings=absent_if_unmarked, marked=workdays)
check((now["paid"], now["absent"]) == (31.0, 0.0), "unmarked days absent: a month marked has none", now)
now = days(settings=absent_if_unmarked, marked=workdays[:-2])
check((now["paid"], now["absent"]) == (29.0, 2.0), "two days unmarked are two days absent", now)
now = days(settings=absent_if_unmarked, marked=workdays[:-2] + [SUNDAY])
check((now["paid"], now["absent"]) == (29.0, 2.0), "and a mark on a holiday does not make up for one", now)
now = days(settings=absent_if_unmarked, marked=[when for when in workdays if when >= D(2026, 9, 15)], joining=D(2026, 9, 15))
check((now["paid"], now["absent"]) == (11.0, 0.0), "days before they joined are no unmarked days", now)
now = days(settings=absent_if_unmarked, marked=[when for when in workdays if when <= D(2026, 9, 10)], relieving=D(2026, 9, 10))
check((now["paid"], now["absent"]) == (16.0, 0.0), "nor days after they left", now)
now = days(settings=dict(absent_if_unmarked, include_holidays_in_total_working_days=0), marked=workdays[:-1])
check((now["working"], now["paid"], now["absent"]) == (27, 26.0, 1.0), "with holidays left out of the count too", now)
now = days(settings=dict(absent_if_unmarked, include_holidays_in_total_working_days=0), marked=[when for when in workdays if when >= D(2026, 9, 15)],
           joining=D(2026, 9, 15))
check((now["paid"], now["absent"]) == (10.0, 0.0), "and the days before they joined less their holidays", now)
now = days(settings=absent_if_unmarked)
check((now["paid"], now["absent"]) == (4.0, 27.0), "nothing marked at all: every day but the holidays", now)
marked_to_the_10th = [when for when in workdays if when <= D(2026, 9, 10)]
now = days(settings=dict(absent_if_unmarked, include_holidays_in_total_working_days=0), marked=marked_to_the_10th,
           relieving=D(2026, 9, 10), holidays=SUNDAYS | {END})
check((now["paid"], now["absent"]) == (14.0, 0.0), "the days after they left, less the holidays among them, are none either", now)
now = R.days_of(START, END, None, None, SUNDAYS, [day(TUESDAY, "On Leave", leave_type="Stray")], COUNTED,
                {"Stray": {"is_lwp": 1, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0.5, "include_holiday": 0}})
check(now["without_pay"] == 1.0, "a fraction on a leave type that is not part paid is not read", now)


# ── 2. A structure's lines ───────────────────────────────
def evaluate(code, data):
    return eval(code, {"__builtins__": {}}, data)


def line(component, abbr, formula=None, amount=0, condition=None, follows=1, statistical=0, out_of_total=0):
    return {"salary_component": component, "abbr": abbr, "amount": amount, "amount_based_on_formula": 1 if formula else 0,
            "formula": formula, "condition": condition, "depends_on_payment_days": follows,
            "statistical_component": statistical, "do_not_include_in_total": out_of_total}


rows = R.month_lines([line("Basic", "BS", "(base * 1)"), line("House", "HR", "BS * 0.1"), line("Taxable", "TS", "BS + HR", statistical=1),
                      line("Overtime", "OT", amount=0), line("Fixed", "FX", amount=5000, follows=0)], {"base": 800000}, evaluate)
check([(row["salary_component"], row["default_amount"]) for row in rows] == [("Basic", 800000.0), ("House", 80000.0), ("Fixed", 5000.0)],
      "a later line reads an earlier; a statistical line and a line of nought have no row", rows)
data = {"base": 100}
R.month_lines([line("Basic", "BS", "base"), line("Taxable", "TS", "BS * 2", statistical=1), line("Other", "OO", "TS + 1")], data, evaluate)
check(data["OO"] == 201, "and one can read a statistical line, as on a slip", data)
rows = R.month_lines([line("Basic", "BS", "base / 3")], {"base": 100}, evaluate)
check(rows[0]["default_amount"] == 33.33, "to the cent", rows)
rows = R.month_lines([line("Basic", "BS", "base", condition="grade == 'A'"), line("Other", "OO", "base", condition="grade == 'B'")],
                     {"base": 100, "grade": "A"}, evaluate)
check([row["salary_component"] for row in rows] == ["Basic"], "a condition that fails leaves the line off", rows)
data = {"base": 100, "grade": "A"}
rows = R.month_lines([line("Other", "OO", "base", condition="grade == 'B'"), line("Basic", "BS", "base")], data, evaluate)
check("OO" not in data and len(rows) == 1, "and its abbreviation unset, as the assignment leaves it", data)
rows = R.month_lines([dict(line("Basic", "BS", amount=5), formula="base")], {"base": 100}, evaluate)
check(rows[0]["default_amount"] == 5.0, "a formula left on a line not based on one is not read", rows)
rows = R.month_lines([line("Broken", "BR", "not_a_field * 2"), line("Basic", "BS", "BR + base")], {"base": 100}, evaluate)
check([(row["salary_component"], row["default_amount"]) for row in rows] == [("Basic", 100.0)],
      "a line that cannot be worked out comes to nought, and the rest are still worked out", rows)
rows = R.month_lines([line("Broken", "BR", amount=0, condition="not_a_field > 1"), line("Basic", "BS", "base")], {"base": 100}, evaluate)
check(len(rows) == 1, "as does one whose condition cannot", rows)
check(R.names_in("base * custom_rate + (BS if grade else 0)") == {"base", "custom_rate", "BS", "grade"}, "the names a formula reads")
check(R.names_in(None) == set() and R.names_in("") == set() and R.names_in("1 +") == set(), "a blank or broken one reads none")

# ── 3. The rows a slip would have ────────────────────────
BASIC_LINE = R.month_lines([line("Basic", "BS", "base")], {"base": 800000}, evaluate)


def additional(component, amount, overwrite=0, follows=1, out_of_total=0, statistical=0):
    return {"salary_component": component, "amount": amount, "overwrite_salary_structure_amount": overwrite,
            "depends_on_payment_days": follows, "do_not_include_in_total": out_of_total, "statistical_component": statistical}


paid = R.paid_rows(R.earning_rows(BASIC_LINE, []), 25, 26)
check(paid[0]["amount"] == 769230.77 and payslip_rules.absent_amount(paid) == 30769.23,
      "800,000 with a day absent is 769,231, and 30,769.23 taken off", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, []), 26, 26)
check(paid[0]["amount"] == 800000 and payslip_rules.absent_amount(paid) == 0, "a whole month takes nothing off", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, []), 0, 26)
check(paid[0]["amount"] == 0 and payslip_rules.absent_amount(paid) == 800000, "no days paid take it all off", paid)
rows = R.earning_rows(BASIC_LINE, [additional("House", 70000)])
paid = R.paid_rows(rows, 25, 26)
check(rows[1]["default_amount"] == 0 and rows[1]["additional_amount"] == 70000 and paid[1]["amount"] == 67307.69
      and payslip_rules.absent_amount(paid) == 33461.54, "an Additional Salary that follows the days is cut by them too", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, [additional("Bonus", 70000, follows=0)]), 25, 26)
check(paid[1]["amount"] == 70000 and payslip_rules.absent_amount(paid) == 30769.23, "one that does not, is not", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, [additional("Bonus", 70000, out_of_total=1)]), 25, 26)
check(payslip_rules.absent_amount(paid) == 30769.23, "nor one outside the totals, for what the days took off", paid)
rows = R.earning_rows(BASIC_LINE, [additional("Basic", 900000, overwrite=1)])
paid = R.paid_rows(rows, 25, 26)
check(len(rows) == 1 and pay_days_rules.full_amount(rows[0]) == 900000 and paid[0]["amount"] == 900000
      and payslip_rules.absent_amount(paid) == 0, "one that overwrites a structure's amount takes its place and is paid whole", rows)
check(BASIC_LINE[0]["additional_amount"] == 0 and "whole" not in BASIC_LINE[0], "without touching the lines the next person's come from", BASIC_LINE)
rows = R.earning_rows(BASIC_LINE, [additional("House", 70000, overwrite=1)])
paid = R.paid_rows(rows, 25, 26)
check(len(rows) == 2 and paid[1]["amount"] == 67307.69, "with no such amount to overwrite it is a row like any other", rows)
rows = R.earning_rows(BASIC_LINE, [additional("House", 10), additional("House", 20, overwrite=1)])
check([row["additional_amount"] for row in rows] == [0, 10, 20], "and does not overwrite another Additional Salary", rows)
paid = R.paid_rows(R.earning_rows(R.month_lines([line("Per Meter Basic", "PB", "base", follows=0)], {"base": 300000}, evaluate), []), 20, 26)
check(paid[0]["amount"] == 300000 and payslip_rules.absent_amount(paid) == 0, "a line that does not follow the days is paid whole", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, []), 25, 26, rounded={"Basic"})
check(paid[0]["amount"] == 769231 and payslip_rules.absent_amount(paid) == 30769, "a component paid to the nearest shilling", paid)
paid = R.paid_rows(R.earning_rows(BASIC_LINE, []), 25, 0)
check(paid[0]["amount"] == 800000, "no working days to divide by: whole", paid)


# ── 4. The glue ──────────────────────────────────────────
class Row(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


def matches(row, filters):
    for field, wanted in (filters or {}).items():
        value = row.get(field)
        if isinstance(wanted, (list, tuple)):
            operator, target = wanted
            # a date may be asked for as a string, as today() gives it
            if isinstance(value, D) and isinstance(target, str):
                target = D.fromisoformat(target)
            if operator == "in":
                good = value in target
            elif operator == "<=":
                good = value is not None and value <= target
            elif operator == ">=":
                good = value is not None and value >= target
            elif operator == "between":
                good = value is not None and target[0] <= value <= target[1]
            else:
                raise ValueError(operator)
        else:
            good = value == wanted
        if not good:
            return False
    return True


class Site:
    META = {"Employee": {"grade", "department", "date_of_joining", "relieving_date", "custom_pay_category"},
            "Salary Structure Assignment": {"custom_rate", "base", "variable", "employee", "salary_structure"}}

    def __init__(self, tables=None, settings=None):
        self.tables, self.calls, self.checked = {**TABLES, **(tables or {})}, [], []
        self.settings = {"payroll_based_on": "Attendance", "custom_days_in_month": 26, **COUNTED, **(settings or {})}
        self.install()

    def install(self):
        site = self
        module = types.ModuleType("frappe")
        module.__path__ = []
        module._ = lambda text, *args, **kwargs: text

        def get_all(doctype, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, or_filters=None, as_list=False):
            site.calls.append((doctype, dict(filters or {}), list(fields or ()), limit_page_length))
            rows = [row for row in site.tables.get(doctype, []) if matches(row, filters)]
            if or_filters:
                rows = [row for row in rows if any(row.get(field) == value for field, value in or_filters.items())]
            if order_by:
                field, direction = order_by.split()
                rows = sorted(rows, key=lambda row: row.get(field), reverse=direction == "desc")
            if pluck:
                return [row.get(pluck) for row in rows]
            if as_list:
                return [tuple(row.get(field) for field in fields) for row in rows]
            return [Row({field: row.get(field) for field in fields}) for row in rows]

        class Meta:
            def __init__(self, doctype):
                self.doctype = doctype

            def has_field(self, name):
                return name in site.META.get(self.doctype, ())

        module.get_all = get_all
        module.get_meta = Meta
        module.db = types.SimpleNamespace(get_singles_dict=lambda doctype: site.settings)
        module.whitelist = lambda *args, **kwargs: (lambda function: function)
        utils = types.ModuleType("frappe.utils")
        utils.cint = lambda value: int(float(value or 0))
        utils.flt = lambda value, precision=None: float(value or 0)
        utils.getdate = lambda value=None: value if isinstance(value, D) else D.fromisoformat(value) if value else TODAY
        utils.date_diff = lambda end, start: (end - start).days
        utils.today = lambda: str(TODAY)
        hrms_utils = types.ModuleType("hrms.payroll.utils")
        hrms_utils.COMPONENT_EVAL_GLOBALS = {"round": round}
        hrms_utils.SALARY_SLIP_EVAL_DEFAULTS = {"gross_pay": 0}

        def safe_eval(code, eval_globals, eval_locals):
            site.checked.append(code)
            if "__" in code:
                raise SyntaxError("Illegal rule")
            return eval(code, {**eval_globals, "__builtins__": {}, "round": round}, eval_locals)

        hrms_utils._safe_eval = safe_eval
        hrms_utils.get_component_abbr_map = lambda: {"BS": 0, "UN": 0}
        hrms_utils.sanitize_expression = lambda code: code.strip() if code else code
        package = types.ModuleType("hrms_addon")
        package.__path__ = []
        app = types.ModuleType("hrms_addon.hrms_addon")
        app.__path__ = []
        hrms, payroll = types.ModuleType("hrms"), types.ModuleType("hrms.payroll")
        hrms.__path__, payroll.__path__ = [], []
        sys.modules.update({"frappe": module, "frappe.utils": utils, "hrms": hrms, "hrms.payroll": payroll, "hrms.payroll.utils": hrms_utils,
                            "hrms_addon": package, "hrms_addon.hrms_addon": app, "hrms_addon.hrms_addon.pay_days_rules": pay_days_rules,
                            "hrms_addon.hrms_addon.payslip_rules": payslip_rules, "hrms_addon.hrms_addon.slip_figures_rules": R})
        sys.modules["hrms_addon.hrms_addon.pay_days"] = load("pay_days")
        sys.modules["hrms_addon.hrms_addon.weekly_pay_rules"] = load("weekly_pay_rules")
        # what a weekly payroll's tab shows is weekly_pay's (verify_weekly_pay.py): left as the month's count here
        sys.modules["hrms_addon.hrms_addon.weekly_pay"] = types.SimpleNamespace(show_on_figures=lambda doc, figures: None)
        self.glue = load("slip_figures")


TODAY = D(2026, 11, 1)
ACTIVE, OTHER_STRUCTURE = "Monthly Pay", "Weekly Pay"
PEOPLE = {
    "E1": {"name": "E1", "company": "LPL", "date_of_joining": D(2020, 1, 1), "relieving_date": None, "grade": "A"},
    "E2": {"name": "E2", "company": "LPL", "date_of_joining": D(2026, 9, 15), "relieving_date": None, "grade": "B"},
    "E3": {"name": "E3", "company": "LPL", "date_of_joining": D(2020, 1, 1), "relieving_date": None, "grade": "B"},
    "E4": {"name": "E4", "company": "LPL", "date_of_joining": D(2020, 1, 1), "relieving_date": None, "grade": "B"},
}
TABLES = {
    "Employee": list(PEOPLE.values()),
    "Salary Structure": [{"name": ACTIVE, "docstatus": 1, "is_active": "Yes", "payroll_frequency": "Monthly"},
                         {"name": "Old Pay", "docstatus": 1, "is_active": "No", "payroll_frequency": "Monthly"},
                         {"name": "Draft Pay", "docstatus": 0, "is_active": "Yes", "payroll_frequency": "Monthly"},
                         {"name": OTHER_STRUCTURE, "docstatus": 1, "is_active": "Yes", "payroll_frequency": "Weekly"}],
    "Salary Detail": [
        dict(line("Taxable Salary", "TS", "BS", statistical=1), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=2),
        dict(line("Basic", "BS", " (base * 1)\n"), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=1),
        dict(line("Overtime", "OT", amount=0, follows=0), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=3),
        dict(line("PAYE", "TX", "BS * 0.3"), parent=ACTIVE, parenttype="Salary Structure", parentfield="deductions", idx=4),
        dict(line("Basic", "BS", "base * 100"), parent="Old Pay", parenttype="Salary Structure", parentfield="earnings", idx=1),
        dict(line("Basic", "BS", "base * 200"), parent=OTHER_STRUCTURE, parenttype="Salary Structure", parentfield="earnings", idx=1),
        dict(line("Basic", "BS", "base * 400"), parent="Draft Pay", parenttype="Salary Structure", parentfield="earnings", idx=1),
        dict(line("Basic", "BS", "base * 300"), parent="Slip", parenttype="Salary Slip", parentfield="earnings", idx=1),
    ],
    "Salary Structure Assignment": [
        {"employee": "E1", "salary_structure": ACTIVE, "base": 800000, "variable": 0, "from_date": D(2026, 1, 1), "docstatus": 1},
        {"employee": "E1", "salary_structure": ACTIVE, "base": 100, "variable": 0, "from_date": D(2024, 1, 1), "docstatus": 1},
        {"employee": "E1", "salary_structure": ACTIVE, "base": 999, "variable": 0, "from_date": D(2026, 10, 1), "docstatus": 1},
        {"employee": "E1", "salary_structure": ACTIVE, "base": 998, "variable": 0, "from_date": D(2026, 3, 1), "docstatus": 2},
        {"employee": "E1", "salary_structure": "Old Pay", "base": 997, "variable": 0, "from_date": D(2026, 4, 1), "docstatus": 1},
        {"employee": "E1", "salary_structure": OTHER_STRUCTURE, "base": 996, "variable": 0, "from_date": D(2026, 5, 1), "docstatus": 1},
        {"employee": "E1", "salary_structure": "Draft Pay", "base": 995, "variable": 0, "from_date": D(2026, 6, 1), "docstatus": 1},
        {"employee": "E2", "salary_structure": ACTIVE, "base": 500000, "variable": 0, "from_date": D(2026, 9, 15), "docstatus": 1},
        {"employee": "E3", "salary_structure": ACTIVE, "base": 260000, "variable": 0, "from_date": D(2026, 1, 1), "docstatus": 1},
    ],
    "Holiday List Assignment": [
        {"assigned_to": "LPL", "holiday_list": "Company List", "from_date": D(2026, 1, 1), "docstatus": 1},
        {"assigned_to": "LPL", "holiday_list": "Old Company List", "from_date": D(2025, 1, 1), "docstatus": 1},
        {"assigned_to": "LPL", "holiday_list": "Next Year", "from_date": D(2027, 1, 1), "docstatus": 1},
        {"assigned_to": "LPL", "holiday_list": "Not Submitted", "from_date": D(2026, 6, 1), "docstatus": 0},
        {"assigned_to": "E3", "holiday_list": "E3 List", "from_date": D(2026, 1, 1), "docstatus": 1},
    ],
    "Holiday": [{"parent": "Company List", "holiday_date": TUESDAY},
                {"parent": "Company List", "holiday_date": D(2026, 10, 9)},
                {"parent": "E3 List", "holiday_date": D(2026, 9, 2)},
                {"parent": "Old Company List", "holiday_date": D(2026, 9, 3)}],
    "Attendance": [
        dict(day(D(2026, 9, 3), "Absent"), employee="E1", docstatus=1),
        dict(day(D(2026, 9, 4), "Absent"), employee="E1", docstatus=0),
        dict(day(D(2026, 9, 5), "Absent"), employee="E1", docstatus=2),
        dict(day(TUESDAY, "Absent"), employee="E1", docstatus=1),
        dict(day(D(2026, 9, 26), "Absent"), employee="E1", docstatus=1),
        dict(day(D(2026, 8, 25), "Absent"), employee="E1", docstatus=1),
        dict(day(D(2026, 9, 7), "Present"), employee="E1", docstatus=1),
        dict(day(D(2026, 9, 2), "Absent"), employee="E3", docstatus=1),
        dict(day(TUESDAY, "Half Day", half="Absent"), employee="E3", docstatus=1),
        dict(day(D(2026, 9, 8), "On Leave", leave_type="Without Pay"), employee="E3", docstatus=1),
        dict(day(D(2026, 9, 9), "On Leave", leave_type="Annual"), employee="E3", docstatus=1),
        dict(day(D(2026, 9, 9), "Absent"), employee="OTHER", docstatus=1),
    ],
    "Leave Type": [{"name": "Without Pay", "is_lwp": 1, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0, "include_holiday": 0},
                   {"name": "Part Paid", "is_lwp": 0, "is_ppl": 1, "fraction_of_daily_salary_per_leave": 0.75, "include_holiday": 1},
                   {"name": "Annual", "is_lwp": 0, "is_ppl": 0, "fraction_of_daily_salary_per_leave": 0, "include_holiday": 0}],
    "Salary Component": [
        {"name": "Basic", "type": "Earning", "depends_on_payment_days": 1},
        {"name": "House", "type": "Earning", "depends_on_payment_days": 1},
        {"name": "Overtime", "type": "Earning", "depends_on_payment_days": 0},
        {"name": "Hidden", "type": "Earning", "depends_on_payment_days": 1, "statistical_component": 1},
        {"name": "Benefit", "type": "Earning", "depends_on_payment_days": 1, "do_not_include_in_total": 1},
        {"name": "Rounded", "type": "Earning", "depends_on_payment_days": 1, "round_to_the_nearest_integer": 1},
        {"name": "Recovery", "type": "Deduction", "depends_on_payment_days": 1},
    ],
    "Additional Salary": [
        {"employee": "E3", "salary_component": "House", "amount": 26000, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 1,
         "from_date": D(2026, 1, 1), "to_date": D(2026, 12, 31)},
        {"employee": "E3", "salary_component": "Basic", "amount": 52000, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "Overtime", "amount": 1000000, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "House", "amount": 1000001, "docstatus": 0, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "House", "amount": 1000002, "docstatus": 1, "type": "Earning", "disabled": 1, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "House", "amount": 1000003, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 8, 25)},
        {"employee": "E3", "salary_component": "House", "amount": 1000004, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 1,
         "from_date": D(2026, 1, 1), "to_date": D(2026, 9, 24)},
        {"employee": "E3", "salary_component": "House", "amount": 1000005, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 1,
         "from_date": D(2026, 9, 26), "to_date": D(2026, 12, 31)},
        {"employee": "E3", "salary_component": "Recovery", "amount": 1000006, "docstatus": 1, "type": "Deduction", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "Hidden", "amount": 1000007, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
        {"employee": "E3", "salary_component": "Benefit", "amount": 1000008, "docstatus": 1, "type": "Earning", "disabled": 0, "is_recurring": 0,
         "payroll_date": D(2026, 9, 25)},
    ],
}


class Run(dict):
    __getattr__ = dict.get


MONTHLY = Run(name="HR-PRUN-1", company="LPL", docstatus=0, payroll_frequency="Monthly", start_date="2026-08-26", end_date="2026-09-25")


def expected(run=MONTHLY, employees=("E1", "E2", "E3", "E4"), **options):
    site = Site(**options)
    return site, site.glue.expected(run, employees)


def figure(working, paid, absent, amount, basic):
    return {"custom_working_days": working, "custom_paid_days": paid, "custom_absent_days": absent,
            "custom_absent_amount": amount, "custom_basic_salary": basic}


site, shown = expected()
check(shown["E1"] == figure(26, 25.0, 1.0, 30769.23, 800000.0),
      "the latest assignment by the period's end on a structure of this frequency, submitted and active; a submitted "
      "absence inside the period; none on their holiday, in draft or cancelled, or outside the period", shown["E1"])
check(shown["E2"] == figure(26, 11.0, 0.0, 288461.54, 500000.0),
      "a hire of the 15th: 11 of 26 paid, as a part month is", shown["E2"])
check(shown["E3"]["custom_working_days"] == 26 and shown["E3"]["custom_paid_days"] == 24.5 and shown["E3"]["custom_absent_days"] == 0.5,
      "their own holiday list, so the 2nd is a holiday and the 1st is a half day; a day of leave without pay; paid leave takes nothing", shown["E3"])
check(shown["E3"]["custom_basic_salary"] == 312000.0, "the Basic with an Additional Salary on it whole", shown["E3"])
# E3: 26 less 1.5 taken is 24.5 of 26, on Basic 260,000 + 52,000 and House 26,000
check(shown["E3"]["custom_absent_amount"] == round((260000 - round(260000 * 24.5 / 26, 2)) + (52000 - round(52000 * 24.5 / 26, 2))
                                                   + (26000 - round(26000 * 24.5 / 26, 2)), 2),
      "the absent amount off everything that follows the days; overtime, and what is cancelled, disabled, of another "
      "period, a deduction, statistical or out of the totals is none of it", shown["E3"])
check(shown["E4"] == figure(26, 26.0, 0.0, 0.0, 0.0), "someone with no assignment still has their days", shown["E4"])
# the calendar's days, where Payroll Settings choose them (Luuka, 1 Nov 2026), the pay the same
_site, calendar = expected(settings={"custom_days_shown": "Calendar Days"})
check(calendar["E1"] == figure(31, 30.0, 1.0, 30769.23, 800000.0) and calendar["E2"] == figure(31, 11.0, 0.0, 288461.54, 500000.0)
      and calendar["E4"] == figure(31, 31.0, 0.0, 0.0, 0.0) and calendar["E3"]["custom_paid_days"] == 29.5,
      "on Calendar Days: 31 days shown, 30 with a day absent, the hire's 11, and the same absent amounts", calendar)
# a per meter employee's basic is untouched, absent or not (Luuka, 8 Nov 2026)
per_meter = [dict(row, custom_pay_category="Per Meter") if row["name"] == "E1" else row for row in TABLES["Employee"]]
_site, output_paid = expected(tables={"Employee": per_meter}, employees=("E1", "E2"))
check(output_paid["E1"] == figure(26, 26.0, 0.0, 0.0, 800000.0),
      "a per meter employee absent a day: the whole 26 paid, no day absent, nothing taken off their basic", output_paid["E1"])
check(output_paid["E2"] == figure(26, 11.0, 0.0, 288461.54, 500000.0), "and the regular hire beside them as before", output_paid["E2"])
_site, output_calendar = expected(tables={"Employee": per_meter}, employees=("E1",), settings={"custom_days_shown": "Calendar Days"})
check(output_calendar["E1"]["custom_working_days"] == 31 and output_calendar["E1"]["custom_paid_days"] == 31.0
      and output_calendar["E1"]["custom_absent_amount"] == 0.0,
      "and on the calendar: every day of the 31", output_calendar["E1"])
check(set(shown) == {"E1", "E2", "E3", "E4"}, "only those asked about", set(shown))
_site, some = expected(employees=("E1",))
check(set(some) == {"E1"}, "those with a slip are not worked out", set(some))
check(set(figure(0, 0, 0, 0, 0)) == {"custom_working_days", "custom_paid_days", "custom_absent_days", "custom_absent_amount",
                                     "custom_basic_salary"}, "the five figures")

read = {call[0]: call for call in site.calls}
check("Present" not in read["Attendance"][1]["status"][1] and read["Attendance"][1]["docstatus"] == 1,
      "only the attendance that takes days off is read, submitted", read["Attendance"])
check(read["Attendance"][1]["attendance_date"] == ["between", [START, END]], "of the period alone", read["Attendance"])
check(read["Holiday"][1]["holiday_date"] == ["between", [START, END]], "as are the holidays", read["Holiday"])
check(sum(1 for call in site.calls if call[0] == "Attendance") == 1, "and once, where an unmarked day is not absent")
check(all(call[3] == 0 for call in site.calls), "all of it, with no limit", site.calls)
check(all("*" not in call[2] for call in site.calls), "and never every field of a record", site.calls)
wanted = next(call for call in site.calls if call[0] == "Additional Salary")[1]["salary_component"][1]
check(set(wanted) == {"Basic", "House", "Rounded"}, "of Additional Salaries only what the figures need", wanted)

_site, zeroed = expected(settings={"custom_days_in_month": 0})
check(zeroed["E1"]["custom_working_days"] == 31 and zeroed["E1"]["custom_paid_days"] == 30.0
      and zeroed["E1"]["custom_absent_amount"] == round(800000 - round(800000 * 30 / 31, 2), 2),
      "Days in a Pay Month at 0: Frappe HR's own count pays them", zeroed["E1"])
weekly = Run(MONTHLY, payroll_frequency="Weekly")
_site, other = expected(run=weekly)
check(other["E1"]["custom_basic_salary"] == 996 * 200 and other["E1"]["custom_working_days"] == 31
      and other["E1"]["custom_absent_amount"] == round(199200 - round(199200 * 30 / 31, 2), 2),
      "another frequency: its own structure, and Frappe HR's count pays it", other["E1"])
_site, left_out_month = expected(settings={"custom_days_in_month": 0, "include_holidays_in_total_working_days": 0}, employees=("E1",))
check(left_out_month["E1"]["custom_working_days"] == 30 and left_out_month["E1"]["custom_paid_days"] == 29.0,
      "Frappe HR's count, with the period's holidays left out of it and no other holiday", left_out_month["E1"])
_site, whole_shilling = expected(tables={"Salary Component": [dict(TABLES["Salary Component"][0], round_to_the_nearest_integer=1)]}, employees=("E1",))
check(whole_shilling["E1"]["custom_absent_amount"] == 30769.0, "a component paid to the nearest shilling", whole_shilling["E1"])
_site, not_by_days = expected(tables={"Salary Component": [dict(TABLES["Salary Component"][0], depends_on_payment_days=0), TABLES["Salary Component"][1]]},
                              employees=("E3",))
check(not_by_days["E3"]["custom_basic_salary"] == 312000.0, "a Basic's Additional Salary is read whether or not the component follows the days", not_by_days["E3"])
reordered = {"Salary Detail": [dict(line("House", "HR", "BS * 0.1"), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=2),
                               dict(line("Basic", "BS", "base"), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=1)]}
_site, in_order = expected(tables=reordered, employees=("E1",))
check(in_order["E1"]["custom_absent_amount"] == 33846.15, "a structure's lines are worked out in its own order", in_order["E1"])
_site, none = expected(tables={"Holiday List Assignment": []}, employees=("E1",))
check(none["E1"]["custom_paid_days"] == 24.0, "no holiday list at all: every absence counts", none["E1"])
_site, company_only = expected(tables={"Additional Salary": [], "Salary Component": []}, employees=("E3",))
check(company_only["E3"]["custom_basic_salary"] == 260000.0, "no components to read Additional Salaries of: none are", company_only)
check(not [call for call in _site.calls if call[0] == "Additional Salary"], "and none are asked for", _site.calls)
_site, nothing = expected(tables={"Salary Structure": []}, employees=("E1",))
check(nothing["E1"]["custom_basic_salary"] == 0 and nothing["E1"]["custom_paid_days"] == 25.0, "no structure at all: the days alone", nothing)

for run, why in ((Run(MONTHLY, docstatus=2), "a cancelled payroll"), (Run(MONTHLY, salary_slip_based_on_timesheet=1), "one worked out from timesheets"),
                 (Run(MONTHLY, start_date=None), "one with no start date"), (Run(MONTHLY, end_date=None), "or no end date")):
    site, nothing = expected(run=run)
    check(nothing == {} and not site.calls, "%s: nothing is read" % why, site.calls)
site, nothing = expected(employees=())
check(nothing == {} and not site.calls, "nobody without a slip: nothing is read", site.calls)
site, nothing = expected(settings={"payroll_based_on": "Leave"})
check(nothing == {} and not site.calls, "Payroll Settings that do not go by attendance: left to the slips", site.calls)

site, shown = expected(settings={"consider_unmarked_attendance_as": "Absent"}, employees=("E1",))
check(sum(1 for call in site.calls if call[0] == "Attendance") == 2, "an unmarked day absent: only then all of the attendance is read", site.calls)
check(shown["E1"]["custom_absent_days"] == 29.0,
      "and they count: 31 days, less the 3rd and 7th marked and submitted and the holiday, and the 3rd absent", shown["E1"])

formula_reads = {
    "Salary Detail": [dict(line("Basic", "BS", "base * custom_rate if grade == 'A' else 0"), parent=ACTIVE, parenttype="Salary Structure",
                           parentfield="earnings", idx=1)],
    "Salary Structure Assignment": [dict(TABLES["Salary Structure Assignment"][0], custom_rate=2)],
}
site, shown = expected(tables=formula_reads, employees=("E1",))
check(shown["E1"]["custom_basic_salary"] == 1600000.0, "a formula reads the fields of the assignment and the employee", shown["E1"])
fields = {call[0]: call[2] for call in site.calls}
check("custom_rate" in fields["Salary Structure Assignment"] and "grade" in fields["Employee"]
      and "custom_rate" not in fields["Employee"] and "grade" not in fields["Salary Structure Assignment"],
      "which are read only of the record that has them", fields)
slip_read = {"Salary Detail": [dict(line("Basic", "BS", "base * payment_days / total_working_days + absent_days"), parent=ACTIVE,
                                    parenttype="Salary Structure", parentfield="earnings", idx=1)]}
_site, shown = expected(tables=slip_read, employees=("E1",))
check(shown["E1"]["custom_basic_salary"] == 800000.0, "and is worked out for a whole month with nothing taken off", shown["E1"])
start_read = {"Salary Detail": [dict(line("Basic", "BS", "base * (start_date.month)"), parent=ACTIVE, parenttype="Salary Structure",
                                     parentfield="earnings", idx=1)]}
_site, shown = expected(tables=start_read, employees=("E1",))
check(shown["E1"]["custom_basic_salary"] == 6400000.0, "of the payroll's own period", shown["E1"])
abbr_read = {"Salary Detail": [dict(line("Basic", "BS", "base + UN"), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=1)]}
_site, shown = expected(tables=abbr_read, employees=("E1",))
check(shown["E1"]["custom_basic_salary"] == 800000.0, "where any component's abbreviation not yet worked out is nought", shown["E1"])


check("base + UN" in _site.checked, "a formula goes through Frappe HR's own check", _site.checked)
refused = {"Salary Detail": [dict(line("Basic", "BS", "base + (1).__class__.__name__.__len__()"), parent=ACTIVE, parenttype="Salary Structure",
                                  parentfield="earnings", idx=1)],
           "Additional Salary": []}
_site, shown = expected(tables=refused, employees=("E1", "E3"))
check(shown["E1"]["custom_basic_salary"] == 0 and shown["E3"]["custom_basic_salary"] == 0 and _site.checked.count(refused["Salary Detail"][0]["formula"]) == 2,
      "and one it refuses is refused for everyone, each time, and never run compiled", _site.checked)
failing = {"Salary Detail": [dict(line("Basic", "BS", "base / (grade_rate - 2)"), parent=ACTIVE, parenttype="Salary Structure", parentfield="earnings", idx=1)],
           "Salary Structure Assignment": [dict(TABLES["Salary Structure Assignment"][0], grade_rate=2), dict(TABLES["Salary Structure Assignment"][8], grade_rate=3)],
           "Additional Salary": []}
site = Site(tables=failing)
site.META = {**Site.META, "Salary Structure Assignment": Site.META["Salary Structure Assignment"] | {"grade_rate"}}
shown = site.glue.expected(MONTHLY, ("E1", "E3"))
check(shown["E1"]["custom_basic_salary"] == 0 and shown["E3"]["custom_basic_salary"] == 260000.0,
      "one that fails for one person is still worked out for the next", shown)


# ── 5. The reads do not grow with the people ─────────────
def crowd(count):
    return {
        "Employee": [{"name": "P%d" % n, "company": "LPL", "date_of_joining": D(2020, 1, 1), "relieving_date": None} for n in range(count)],
        "Salary Structure Assignment": [{"employee": "P%d" % n, "salary_structure": ACTIVE, "base": 100000 + n, "variable": 0,
                                         "from_date": D(2026, 1, 1), "docstatus": 1} for n in range(count)],
        "Attendance": [dict(day(D(2026, 9, 3), "Absent"), employee="P%d" % n, docstatus=1) for n in range(0, count, 3)],
    }


few = Site(tables=crowd(3))
few_shown = few.glue.expected(MONTHLY, ["P%d" % n for n in range(3)])
many = Site(tables=crowd(600))
many_shown = many.glue.expected(MONTHLY, ["P%d" % n for n in range(600)])
check(len(many_shown) == 600 and many_shown["P3"]["custom_absent_days"] == 1.0 and many_shown["P4"]["custom_absent_days"] == 0.0,
      "600 people each have their own", many_shown["P3"])
check(len(many.calls) == len(few.calls) and len(many.calls) <= 12,
      "and take no more reads than 3: %d and %d" % (len(many.calls), len(few.calls)), [call[0] for call in many.calls])
check(many.checked.count("(base * 1)") == 1 and many.checked.count("BS") == 1,
      "with each formula checked once, not 600 times", many.checked[:5])
check(many_shown["P5"]["custom_basic_salary"] == 100005.0 and many_shown["P599"]["custom_basic_salary"] == 100599.0,
      "while each still comes to their own", many_shown["P599"])

# ── 5b. A weekly payroll: the days its slips will pay ─────
told = []


def show_on_figures(doc, figures):
    told.append((doc.get("payroll_frequency"), sorted(figures)))
    for row in figures.values():
        row.update(custom_working_days=7, custom_paid_days=5)


def told_of(run, employees):
    site = Site()
    sys.modules["hrms_addon.hrms_addon.weekly_pay"] = types.SimpleNamespace(show_on_figures=show_on_figures)
    return site.glue.expected(run, employees)


WEEKLY_RUN = Run(name="HR-PRUN-9", company="LPL", docstatus=0, payroll_frequency="Weekly", start_date="2026-09-03", end_date="2026-09-09")
shown = told_of(WEEKLY_RUN, ("E1", "E3"))
check(told == [("Weekly", ["E1", "E3"])] and shown["E1"]["custom_paid_days"] == 5 and shown["E3"]["custom_working_days"] == 7,
      "a weekly payroll's tab shows the days weekly pay will pay, not a month's count", (told, shown))
told.clear()
told_of(MONTHLY, ("E1",))
told_of(Run(WEEKLY_RUN, salary_slip_based_on_timesheet=1), ("E1",))
check(not told, "a monthly payroll, and a weekly one on timesheets, keep the month's count", told)

# ── 6. Upstream ──────────────────────────────────────────
utils_path = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "utils.py")
if os.path.exists(utils_path):
    utils_src = open(utils_path, encoding="utf-8").read()
    for name in ("COMPONENT_EVAL_GLOBALS = {", "SALARY_SLIP_EVAL_DEFAULTS = {", "def _safe_eval(", "def get_component_abbr_map(", "def sanitize_expression("):
        check(name in utils_src, "Frappe HR's payroll utils have %s" % name)
    slip_src = open(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_slip", "salary_slip.py"), encoding="utf-8").read()
    for needle, why in (
        ('(attendance.status.isin(["Absent", "Half Day", "On Leave"]))', "the attendance a slip reads is what is read here"),
        ("get_holiday_list_for_employee(self.employee)", "and its holiday list is found as of today"),
        ("self.get_half_absent_days(", "half days counted apart"),
    ):
        check(needle in slip_src, "Frappe HR's slip: %s (%r not found)" % (why, needle))
    holiday_src = open(os.path.join(APPS_ROOT, "hrms", "hrms", "utils", "holiday_list.py"), encoding="utf-8").read()
    check('"Holiday List Assignment"' in holiday_src and "get_assigned_holiday_list(company, as_on, as_dict)" in holiday_src,
          "a holiday list is assigned, to the employee or else their company")
    # a field that is not there would make every read fail: an error logged, and noughts on every row
    site, _shown = expected(settings={"consider_unmarked_attendance_as": "Absent"})
    asked = {}
    for doctype, filters, fields, _limit in site.calls:
        asked.setdefault(doctype, set()).update(fields, filters)
    asked["Leave Type"].update({"is_ppl", "is_lwp"})
    asked["Salary Structure"].add("name")
    # the app's own fields on a doctype upstream count as its fields: a migrate adds them
    ours = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
    for doctype, fields in sorted(asked.items()):
        scrubbed = doctype.lower().replace(" ", "_")
        found = glob.glob(os.path.join(APPS_ROOT, "*", "*", "*", "doctype", scrubbed, scrubbed + ".json"))
        check(found, "%s is a doctype upstream" % doctype)
        if found:
            standard = {"name", "docstatus", "parent", "parenttype", "parentfield", "idx"}
            known = {field["fieldname"] for field in json.load(open(found[0], encoding="utf-8"))["fields"]} | standard
            known |= {field["fieldname"] for field in ours if field["dt"] == doctype}
            check(fields <= known, "%s has the fields read of it: %s" % (doctype, sorted(fields - known)))
    run_src = open(os.path.join(APPS_ROOT, "frappe", "frappe", "desk", "form", "save.py"), encoding="utf-8").read()
    check("run_onload(doc)" in run_src, "the save Get Employees ends with runs onload, so the figures come back with it")
else:
    print("Frappe HR's source not found here: upstream not checked")

print()
print("FAILED: %d" % len(fail) if fail else "ALL SLIP FIGURE CHECKS PASSED")
sys.exit(1 if fail else 0)
