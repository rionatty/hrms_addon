"""Checks Luuka's 26-day month on Frappe HR's slips, without a bench:

    python scripts/verify_pay_days.py

Luuka, 21 Oct 2026: "when computing hourly rate for over time use 26days,
then on the payroll show the absent amount deducted from the worked days.
basic pay is computed from working days." Their register prices a day at the
month's pay over 26 days, whatever the month's length; Frappe HR divides by
the period's own days. So:

  1. the days: 26 Working Days, and Payment Days the days on the payroll, up
     to 26, less what Frappe HR took off; Luuka's own register reproduced
  2. an hour of overtime: the month's pay / 26 / the day's standard hours,
     on the Overtime Slip and on HR's cost check alike
  3. the Absent Amount: what the days not paid took off, Additional Salary
     paid by the days included
  4. Frappe HR's own code still does what the overrides build on
  5. the wiring: the mixins, the slip's check, the register's column, the
     two fields
"""
import ast
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
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


R = load("pay_days_rules")
S = load("payslip_rules")
O = load("overtime_rules")
print("loaded pay_days_rules.py, payslip_rules.py and overtime_rules.py without Frappe")


def paid(full, days):
    """Frappe HR's own proration of an earning: full x Payment Days / Working Days."""
    working, payment = days
    return full * payment / working


# ── 1. The days ───────────────────────────────────────────────────────
check("Luuka's month is 26 days", R.DAYS_IN_MONTH == 26)
# (what it is, days, on the payroll, Frappe HR counted from, Frappe HR paid, leave without pay) -> payment days
CASES = [
    ("a whole cycle of 31 days, holidays counted, a day absent", 26, 31, 31, 30, 0, 25),
    ("the same, holidays left out (five Sundays): the same day off", 26, 31, 26, 25, 0, 25),
    ("four Sundays left out, two days absent", 26, 31, 27, 25, 0, 24),
    ("a hire of the 15th, 11 days of the cycle", 26, 11, 11, 11, 0, 11),
    ("the same with a day absent", 26, 11, 11, 10, 0, 10),
    ("the same hire, Sundays left out: still the 11 days on the payroll", 26, 11, 9, 9, 0, 11),
    ("a leaver of the 10th, 16 days of the cycle", 26, 16, 16, 16, 0, 16),
    ("two days without pay, a day absent and half a day", 26, 31, 31, 27.5, 2, 22.5),
    ("a hire of the cycle's second day: the whole month", 26, 30, 30, 30, 0, 26),
    ("every day without pay: nothing", 26, 31, 31, 0, 31, 0),
    ("every day without pay, two days given back by a Payroll Correction", 26, 31, 31, 2, 31, 2),
    ("two days a Payroll Correction gives back, on a whole month", 26, 31, 31, 33, 0, 28),
    ("absent more days than are left: nothing, never less", 26, 5, 5, 0, 0, 0),
]
for what, days, on_payroll, counted, frappe_paid, lwp, wanted in CASES:
    got = R.slip_days(days, on_payroll, counted, frappe_paid, lwp)
    check("%s: 26 working days, %s paid" % (what, wanted), got == (26, wanted), got)
check("a slip worked out for the whole month (a preview) is the whole month",
      R.slip_days(26, 0, 0, 0, 0, preview=True) == (26, 26))
check("0 days, or none, leaves Frappe HR's own count", R.slip_days(0, 31, 31, 30, 0) is None
      and R.slip_days(None, 31, 31, 30, 0) is None and R.slip_days(-1, 31, 31, 30, 0) is None)
check("another month length, if Payroll Settings say so", R.slip_days(30, 31, 31, 30, 0) == (30, 29))

# Luuka's own September register, figures only: Frappe HR's proration on the
# days above comes to what the register paid, within the shilling the
# register's own rounding moves (44,342.31 is 44,343 there, 30,769.23 is
# 30,769)
REGISTER = [
    # (what, the month's pay, days, register's pay, register's Absent Amt)
    ("800,000 with a day absent", 800000, R.slip_days(26, 31, 31, 30, 0), 769231, 30769),
    ("800,000 with seven days absent", 800000, R.slip_days(26, 31, 31, 24, 0), 584615, 215385),
    ("600,000 with nine and a half days absent", 600000, R.slip_days(26, 31, 31, 21.5, 0), 380769, 219231),
    ("384,300 with three days absent", 384300, R.slip_days(26, 31, 31, 28, 0), 339957, 44343),
    ("a hire on 500,000 with 11 days of the cycle", 500000, R.slip_days(26, 11, 11, 11, 0), 211539, None),
    ("a hire on 3,800,000 with 12 days", 3800000, R.slip_days(26, 12, 12, 12, 0), 1753846, None),
    ("a hire on 650,000 with 7 days", 650000, R.slip_days(26, 7, 7, 7, 0), 175000, None),
]
for what, full, days, earned, absent in REGISTER:
    pay = paid(full, days)
    check("Luuka's register: %s is paid %s" % (what, "{:,}".format(earned)), abs(pay - earned) < 1, round(pay, 2))
    if absent is not None:
        check("   and the Absent Amount is %s" % "{:,}".format(absent), abs(full - pay - absent) < 1,
              round(full - pay, 2))
frappe_way = paid(800000, (31, 30))
check("Frappe HR's own count would have paid 774,194 for that day absent, 4,963 more than Luuka",
      round(frappe_way) == 774194, round(frappe_way, 2))

# ── 2. An hour of overtime ────────────────────────────────────────────
check("an hour: 800,000 / 26 days / 10 standard hours = 3,076.92",
      round(R.hourly_rate(800000, 26, 10), 2) == 3076.92, R.hourly_rate(800000, 26, 10))
check("the same whatever days were worked: the month's pay, not what the slip paid",
      R.hourly_rate(800000, 26, 10) == R.hourly_rate(800000, 26, 10.0))
check("no pay, no days or no standard hours: nothing, never a division by nought",
      R.hourly_rate(0, 26, 10) == 0 and R.hourly_rate(800000, 0, 10) == 0 and R.hourly_rate(800000, 26, 0) == 0
      and R.hourly_rate(800000, 26, None) == 0)
check("HR's cost check divides by the same days: 26 days of 10 hours, or the shift's own",
      O.hours_per_month(10, 26) == 260 and O.hours_per_month(None, 26) == 260 and O.hours_per_month(8, 26) == 208)
check("and by Payroll Settings' days where they say otherwise; 26 where they give none or 0",
      O.hours_per_month(10, 30) == 300 and O.hours_per_month(10, None) == 260 and O.hours_per_month(10, 0) == 260)
costed = O.priced([{"employee": "E1", "hours": 2}], {"E1": 800000}, O.WEEKDAY, standards={"E1": 10}, days=26)
check("a request costed on 26 days: 2 hours of 3,076.92 at the weekday's 1.5",
      costed["rows"][0]["hourly_rate"] == round(800000 / 260, 4) and costed["total"] == round(2 * round(800000 / 260, 4) * 1.5, 2),
      costed["rows"][0])
check("the slip's hour and the cost check's hour agree, to the cent",
      abs(R.hourly_rate(800000, 26, 10) - costed["rows"][0]["hourly_rate"]) < 0.01)
check("full_amount: the structure's amount and an Additional Salary's whole amount",
      R.full_amount({"default_amount": 700000, "additional_amount": 0}) == 700000
      and R.full_amount({"default_amount": 0, "additional_amount": 100000}) == 100000)

# ── 3. The Absent Amount ──────────────────────────────────────────────
days = R.slip_days(26, 31, 31, 30, 0)
rows = [
    {"salary_component": "Basic Salary", "default_amount": 700000, "amount": paid(700000, days),
     "depends_on_payment_days": 1},
    # House Rent paid as a standing Additional Salary is cut by the days too
    {"salary_component": "House Rent Allowance", "default_amount": 0, "additional_amount": 100000,
     "amount": paid(100000, days), "depends_on_payment_days": 1, "additional_salary": "HR-ADS-1"},
    # one that overwrites the structure's amount is paid whole
    {"salary_component": "Transport Allowance", "default_amount": 70000, "additional_amount": 0, "amount": 70000,
     "depends_on_payment_days": 1, "additional_salary": "HR-ADS-2"},
    {"salary_component": "Airtime", "default_amount": 30000, "amount": 30000, "depends_on_payment_days": 0},
    {"salary_component": "Overtime", "default_amount": 0, "additional_amount": 54000, "amount": 54000,
     "depends_on_payment_days": 0, "additional_salary": "HR-ADS-3"},
    {"salary_component": "Taxable Pay", "default_amount": 800000, "amount": 700000, "depends_on_payment_days": 1,
     "statistical_component": 1},
]
check("the Absent Amount is a day of the whole package, 800,000 / 26 = 30,769.23, House Rent's share included",
      S.absent_amount(rows) == 30769.23, S.absent_amount(rows))
check("a whole month takes nothing off", S.absent_amount([dict(row, amount=row.get("default_amount", 0)
                                                               + row.get("additional_amount", 0)) for row in rows]) == 0)

# ── 4. Frappe HR's own code, as the overrides build on it ─────────────
slip_src = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_slip", "salary_slip.py")
overtime_src = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "overtime_slip", "overtime_slip.py")
register_src = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "report", "salary_register", "salary_register.py")
if all(os.path.exists(path) for path in (slip_src, overtime_src, register_src)):
    slip = open(slip_src, encoding="utf-8").read()
    for needle, why in (
        ("def get_working_days_details(self, lwp=None, for_preview=0, lwp_days_corrected=None):",
         "the days are counted in get_working_days_details, which the Salary Slip mixin follows"),
        ("def get_payment_days(self, include_holidays_in_total_working_days):",
         "the days Frappe HR counts the payment from, asked again by the mixin"),
        ("def actual_start_date(self):", "the first day on the payroll"),
        ("def actual_end_date(self):", "and the last"),
        ("self.get_working_days_details(lwp=self.leave_without_pay)\n\t\tself.calculate_net_pay()",
         "the days are counted before the pay is worked out from them"),
        ("(flt(row.default_amount) * flt(self.payment_days) / cint(self.total_working_days))",
         "an earning is paid by Payment Days / Working Days"),
        ("component_row.amount = self.get_amount_based_on_payment_days(component_row)[0]",
         "and only the amount paid is written back on the row, so its full amounts stay"),
        ("component_row.default_amount = 0\n\t\t\t\tcomponent_row.additional_amount = amount",
         "an Additional Salary keeps its whole amount on its row"),
        ('"include_holidays_in_total_working_days",', "the holidays are counted, or not, by Payroll Settings"),
    ):
        check("Frappe HR's Salary Slip: %s" % why, needle in slip)
    overtime = open(overtime_src, encoding="utf-8").read()
    for needle, why in (
        ("def _calculate_component_based_hourly_rate(self, overtime_type, standard_working_hours):",
         "an hour of salary-component overtime is worked out here, which the Overtime Slip mixin follows"),
        ("self._calculate_component_based_hourly_rate(\n\t\t\t\tovertime_type, standard_working_hours\n\t\t\t)",
         "called with the type and the standard hours"),
        ("self._cached_salary_slip = self._make_salary_slip(salary_structure)",
         "on the month's slip it keeps, which the mixin reads"),
        ("payment_days = max(self._cached_salary_slip.payment_days, 1)",
         "Frappe HR divides by the slip's Payment Days: what the 26 replaces"),
        ('not data.get("additional_salary", None)', "an Additional Salary row is not counted in the hour"),
        ('overtime_types[ot_type]["components"]', "the type's components are kept on overtime_types"),
    ):
        check("Frappe HR's Overtime Slip: %s" % why, needle in overtime)
    register = open(register_src, encoding="utf-8").read()
    check("Frappe HR's Salary Register has an Absent Days column and a row per slip with its currency",
          '"fieldname": "absent_days"' in register and '"salary_slip_id": ss.name' in register
          and '"currency": currency or company_currency' in register)
else:
    print("Frappe HR's own code: NOT CHECKED, it was not found under %s" % APPS_ROOT)

# ── 5. The wiring ─────────────────────────────────────────────────────
hooks_src = read("hrms_addon", "hooks.py")
hooks = {}
for node in ast.parse(hooks_src).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
extended = hooks.get("extend_doctype_class") or {}
check("the Salary Slip is paid on Luuka's month", extended.get("Salary Slip") ==
      ["hrms_addon.hrms_addon.pay_days.SalarySlipDays"], extended.get("Salary Slip"))
check("and the Overtime Slip's hour too", extended.get("Overtime Slip") ==
      ["hrms_addon.hrms_addon.pay_days.OvertimeSlipDays"], extended.get("Overtime Slip"))
check("the Salary Register gains its column beside the leave reports'",
      "hrms_addon.hrms_addon.report_extensions.SalaryRegisterColumns" in (extended.get("Report") or [])
      and "hrms_addon.hrms_addon.report_extensions.LeaveReportColumns" in (extended.get("Report") or []))
validate = (hooks.get("doc_events") or {}).get("Salary Slip", {}).get("validate")
check("the slip keeps its Absent Amount on validate, after the period is checked",
      validate == ["hrms_addon.hrms_addon.payslip.period_validate", "hrms_addon.hrms_addon.pay_days.slip_validate"],
      validate)
glue = read("hrms_addon", "hrms_addon", "pay_days.py")


def body(name):
    found = re.search(r"^(?:class|def) %s\b.*?(?=^(?:class|def) |^# ──|\Z)" % name, glue, re.S | re.M)
    return found.group(0) if found else ""


mixin = body("SalarySlipDays")
check("the Salary Slip mixin counts as Frappe HR does first, then sets the month",
      "super().get_working_days_details(*args, **kwargs)" in mixin and "set_month(self" in mixin
      and mixin.index("super()") < mixin.index("set_month(self"))
check("and knows a preview from its arguments, keyword or not",
      'kwargs.get("for_preview", args[1] if len(args) > 1 else 0)' in mixin)
month = body("set_month")
check("only a monthly slip not worked out from timesheets, and only while the days are set",
      "if not days or not on_luuka_month(slip):" in month
      and 'slip.get("payroll_frequency") == MONTHLY' in body("on_luuka_month")
      and 'not cint(slip.get("salary_slip_based_on_timesheet"))' in body("on_luuka_month"))
check("the days on the payroll are its calendar days, from joining to leaving",
      "on_payroll=date_diff(slip.actual_end_date, slip.actual_start_date) + 1" in month)
check("and what Frappe HR counted from is asked of Frappe HR, holidays as Payroll Settings say",
      "counted_from=slip.get_payment_days(holidays_counted)" in month
      and '"include_holidays_in_total_working_days"' in month)
check("the setting: 26 until it is saved otherwise, 0 to give Frappe HR its own count back",
      "frappe.db.get_singles_dict(SETTINGS).get(DAYS_FIELD)" in body("days_in_month")
      and "return rules.DAYS_IN_MONTH" in body("days_in_month"))
ot = body("OvertimeSlipDays")
check("the Overtime Slip mixin lets Frappe HR make its month's slip first, and keeps Frappe HR's hour where the "
      "month is not Luuka's", "theirs = super()._calculate_component_based_hourly_rate(" in ot
      and "return theirs" in ot and "on_luuka_month(slip)" in ot)
check("its hour is the components' whole month over the days and the standard hours",
      "rules.hourly_rate(monthly_amount(slip, components), days, standard_working_hours)" in ot
      and 'flt(row.get("default_amount"))' in body("monthly_amount")
      and 'not row.get("additional_salary")' in body("monthly_amount"))
check("the slip's Absent Amount is the Pay Slip's own sum", "payslip_rules.absent_amount(" in body("slip_validate")
      and "rules.absent_amount(earnings)" in read("hrms_addon", "hrms_addon", "payslip.py"))
register_glue = body("with_absent_amount")
check("the register's column sits after the Absent Days, in the register's currency",
      'column.get("fieldname") == "absent_days"' in register_glue and "columns.insert(at + 1" in register_glue
      and "slip.exchange_rate" in register_glue)
extensions = read("hrms_addon", "hrms_addon", "report_extensions.py")
check("the register's mixin touches the Salary Register only, and gives it back as it was should it fail",
      "if self.name != pay_days.REGISTER:" in extensions and "pay_days.with_absent_amount(result)" in extensions
      and 'REGISTER = "Salary Register"' in glue)
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
setting = fields.get("Payroll Settings-custom_days_in_month") or {}
check("Payroll Settings' Days in a Pay Month: a whole number, 26, never below nought, beside the half day's fraction",
      (setting.get("fieldtype"), setting.get("default"), setting.get("non_negative"), setting.get("insert_after"))
      == ("Int", "26", 1, "daily_wages_fraction_for_half_day"), setting)
absent = fields.get("Salary Slip-custom_absent_amount") or {}
check("the slip's Absent Amount: money in the slip's currency, read only, under the Absent Days",
      (absent.get("fieldtype"), absent.get("options"), absent.get("read_only"), absent.get("insert_after"))
      == ("Currency", "currency", 1, "absent_days"), absent)
check("both are in the fixtures the app ships", all('"%s",' % name in hooks_src for name in
                                                    ("Payroll Settings-custom_days_in_month",
                                                     "Salary Slip-custom_absent_amount")))
check("the setting's field name is the one the code reads", 'DAYS_FIELD = "custom_days_in_month"' in glue
      and 'ABSENT_FIELD = "custom_absent_amount"' in glue)
check("HR's cost check divides by the same days as the Overtime Slip",
      "days=pay_days.days_in_month())" in read("hrms_addon", "hrms_addon", "overtime.py"))

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL PAY DAYS CHECKS PASSED")
