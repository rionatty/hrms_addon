"""Checks Luuka's 26-day month on Frappe HR's slips, without a bench:

    python scripts/verify_pay_days.py

Luuka, 21 Oct 2026: "when computing hourly rate for over time use 26days,
then on the payroll show the absent amount deducted from the worked days.
basic pay is computed from working days." Their register prices a day at the
month's pay over 26 days, whatever the month's length; Frappe HR divides by
the period's own days. So:

  1. the days: 26 Working Days, and Payment Days the days on the payroll, up
     to 26, less what Frappe HR took off; Luuka's own register reproduced
  2. an hour of overtime: the month's pay / 26 / 8, the standard working day,
     on the Overtime Slip and on HR's cost check alike
  3. the Absent Amount: what the days not paid took off, Additional Salary
     paid by the days included
  4. Frappe HR's own code still does what the overrides build on
  5. the wiring: the mixins, the slip's check, the register's column, the
     two fields
  6. the days a slip shows: the calendar's, Sundays and holidays included, as
     Luuka's register and Pay Slip count them, on every screen, and paying
     nobody
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
# Luuka, 21 Oct 2026: "standard woring hours is 8"
check("Luuka's day is 8 standard working hours", R.HOURS_IN_DAY == 8)
check("an hour: 800,000 / 26 days / 8 hours = 3,846.15",
      round(R.hourly_rate(800000, 26, 8), 2) == 3846.15, R.hourly_rate(800000, 26, 8))
check("the same whatever days were worked: the month's pay, not what the slip paid",
      R.hourly_rate(800000, 26, 8) == R.hourly_rate(800000, 26, 8.0))
check("no pay, no days or no hours: nothing, never a division by nought",
      R.hourly_rate(0, 26, 8) == 0 and R.hourly_rate(800000, 0, 8) == 0 and R.hourly_rate(800000, 26, 0) == 0
      and R.hourly_rate(800000, 26, None) == 0)
check("HR's cost check divides by the same day: 26 days of 8 hours, whatever the shift's own standard hours",
      O.hours_per_month(10, 26, 8) == 208 and O.hours_per_month(None, 26, 8) == 208 and O.hours_per_month(12, 26, 8) == 208)
check("with Hours in a Pay Day at 0, by the shift's own standard hours, ten where it gives none",
      O.hours_per_month(10, 26, 0) == 260 and O.hours_per_month(None, 26, None) == 260 and O.hours_per_month(9, 26, 0) == 234)
check("and by Payroll Settings' days where they say otherwise; 26 where they give none or 0",
      O.hours_per_month(10, 30, 8) == 240 and O.hours_per_month(10, None, 8) == 208 and O.hours_per_month(10, 0, 8) == 208)
costed = O.priced([{"employee": "E1", "hours": 2}], {"E1": 800000}, O.WEEKDAY, standards={"E1": 10}, days=26,
                  day_hours=8)
check("a request costed on 26 days of 8 hours: 2 hours of 3,846.15 at the weekday's 1.5, the shift's 10 aside",
      costed["rows"][0]["hourly_rate"] == round(800000 / 208, 4) and costed["total"] == round(2 * round(800000 / 208, 4) * 1.5, 2),
      costed["rows"][0])
check("the slip's hour and the cost check's hour agree, to the cent",
      abs(R.hourly_rate(800000, 26, 8) - costed["rows"][0]["hourly_rate"]) < 0.01)
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
check("the Salary Slip is paid on Luuka's month", "hrms_addon.hrms_addon.pay_days.SalarySlipDays" in
      (extended.get("Salary Slip") or []), extended.get("Salary Slip"))
check("and the Overtime Slip's hour too", extended.get("Overtime Slip") ==
      ["hrms_addon.hrms_addon.pay_days.OvertimeSlipDays"], extended.get("Overtime Slip"))
check("the Salary Register gains its column beside the leave reports'",
      "hrms_addon.hrms_addon.report_extensions.SalaryRegisterColumns" in (extended.get("Report") or [])
      and "hrms_addon.hrms_addon.report_extensions.LeaveReportColumns" in (extended.get("Report") or []))
validate = (hooks.get("doc_events") or {}).get("Salary Slip", {}).get("validate")
check("the slip keeps its Absent Amount on validate, after the period is checked",
      validate[:2] == ["hrms_addon.hrms_addon.payslip.period_validate", "hrms_addon.hrms_addon.pay_days.slip_validate"],
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
check("its hour is the components' whole month over the days and the day's 8 hours, the shift's own only with "
      "Hours in a Pay Day at 0",
      "rules.hourly_rate(monthly_amount(slip, components), days, hours_in_day() or standard_working_hours)" in ot
      and 'flt(row.get("default_amount"))' in body("monthly_amount")
      and 'not row.get("additional_salary")' in body("monthly_amount"))
check("the day's hours: 8 until it is saved otherwise, 0 to divide by each shift's own",
      "frappe.db.get_singles_dict(SETTINGS).get(HOURS_FIELD)" in body("hours_in_day")
      and "return rules.HOURS_IN_DAY" in body("hours_in_day") and 'HOURS_FIELD = "custom_hours_in_day"' in glue)
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
shown_field = fields.get("Payroll Settings-custom_days_shown") or {}
check("and its Days Shown on Slips: the month's own, or the calendar's, the month's unless HR choose, under the days",
      (shown_field.get("fieldtype"), shown_field.get("options"), shown_field.get("default"),
       shown_field.get("insert_after")) == ("Select", "\n".join(R.SHOWN), R.PAY_MONTH, "custom_days_in_month")
      and '"Payroll Settings-custom_days_shown",' in hooks_src, shown_field)
hours = fields.get("Payroll Settings-custom_hours_in_day") or {}
check("and its Hours in a Pay Day: 8, never below nought, under the days shown",
      (hours.get("fieldtype"), hours.get("default"), hours.get("non_negative"), hours.get("insert_after"))
      == ("Float", "8", 1, "custom_days_shown") and '"Payroll Settings-custom_hours_in_day",' in hooks_src, hours)
absent = fields.get("Salary Slip-custom_absent_amount") or {}
check("the slip's Absent Amount: money in the slip's currency, read only, under the Absent Days",
      (absent.get("fieldtype"), absent.get("options"), absent.get("read_only"), absent.get("insert_after"))
      == ("Currency", "currency", 1, "absent_days"), absent)
check("both are in the fixtures the app ships", all('"%s",' % name in hooks_src for name in
                                                    ("Payroll Settings-custom_days_in_month",
                                                     "Salary Slip-custom_absent_amount")))
check("the setting's field name is the one the code reads", 'DAYS_FIELD = "custom_days_in_month"' in glue
      and 'ABSENT_FIELD = "custom_absent_amount"' in glue)
check("HR's cost check divides by the same days and hours as the Overtime Slip",
      "days=pay_days.days_in_month(), day_hours=pay_days.hours_in_day())" in read("hrms_addon", "hrms_addon",
                                                                                 "overtime.py"))

# ── 6. The days a slip shows ──────────────────────────────────────────
# Luuka, 1 Nov 2026: "then you should include holiday sunday". Their own
# September register: Paid Days + Absent Days = 31 for all 1,353 monthly staff,
# and the Absent Amt still the full pay / 26 for all 503 absences.
# (what it is, the period, on the payroll, Frappe HR counted from, Frappe HR paid, leave without pay) -> days shown
SHOWN = [
    ("a whole cycle of 31 days", 31, 31, 31, 31, 0, 31),
    ("a day absent", 31, 31, 31, 30, 0, 30),
    ("half a day absent, as Luuka's register has 30.5", 31, 31, 31, 30.5, 0, 30.5),
    ("a day absent, Sundays left out of Frappe HR's count: the Sundays are still shown", 31, 31, 27, 26, 0, 30),
    ("a hire of the 15th, 11 days of the cycle", 31, 11, 11, 11, 0, 11),
    ("the same with a day absent", 31, 11, 11, 10, 0, 10),
    ("the same hire, Sundays left out", 31, 11, 9, 9, 0, 11),
    ("a leaver of the 10th, 16 days of the cycle", 31, 16, 16, 16, 0, 16),
    ("a hire of the cycle's second day, paid the whole 26: the 30 days they were here", 31, 30, 30, 30, 0, 30),
    ("two days without pay, a day absent and half a day", 31, 31, 31, 27.5, 2, 27.5),
    ("every day without pay: nothing", 31, 31, 31, 0, 31, 0),
    ("every day without pay, two days given back by a Payroll Correction", 31, 31, 31, 2, 31, 2),
    ("every working day without pay, Sundays left out: nothing, not the four Sundays", 31, 31, 27, 0, 27, 0),
    ("the same with two days given back", 31, 31, 27, 2, 27, 2),
    ("absent more days than are left: nothing, never less", 31, 5, 5, -1, 0, 0),
    ("a Payroll Correction giving back more than was taken: never more days than they were here", 31, 31, 31, 33, 0, 31),
    ("the cycle of 26 February, 28 days, a day absent", 28, 28, 28, 27, 0, 27),
    ("a period of 30 days", 30, 30, 30, 29, 0, 29),
]
for what, period, on_payroll, counted, frappe_paid, lwp, wanted in SHOWN:
    got = R.calendar_days(period, on_payroll, counted, frappe_paid, lwp)
    check("shown: %s: %s working days, %s paid" % (what, period, wanted), got == (period, wanted), got)
check("and the same day is still a 26th of the pay: 30 days shown, 800,000 x 25 / 26 paid, as Luuka's register",
      R.calendar_days(31, 31, 31, 30, 0) == (31, 30) and round(paid(800000, R.slip_days(26, 31, 31, 30, 0))) == 769231)
# Luuka, 8 Nov 2026: "revert Working days to be considered need be as 26". What a
# slip shows is the month's own unless Payroll Settings choose the calendar's.
check("the days shown are the month's own, the 26 pay is divided by, unless HR choose the calendar's",
      R.shown_days(R.PAY_MONTH, 31, (26, 25), {"on_payroll": 31, "counted_from": 31, "paid": 30, "without_pay": 0})
      == (26, 25)
      and R.shown_days(R.CALENDAR, 31, (26, 25), {"on_payroll": 31, "counted_from": 31, "paid": 30, "without_pay": 0})
      == (31, 30)
      and R.shown_days("anything else", 31, (26, 25), {"on_payroll": 31, "counted_from": 31, "paid": 30,
                                                       "without_pay": 0}) == (26, 25))
check("a choice nobody made, or one the settings no longer offer, is the month's own",
      'return stored if stored in rules.SHOWN else rules.PAY_MONTH' in body("days_shown"))
# Luuka, 8 Nov 2026: "For per metre, basic pay is untouched regardless of absence".
# (what it is, on the payroll, Frappe HR counted from, Frappe HR paid, leave without pay) -> payment days
PER_METER = [
    ("a whole cycle, three days absent: the whole 26", 31, 31, 28, 0, 26),
    ("never clocked in at all: still the whole 26", 31, 31, 0, 0, 26),
    ("two days of leave without pay: still the whole 26", 31, 31, 29, 2, 26),
    ("a hire of the 15th: the 11 days on the payroll, absences or not", 11, 11, 8, 0, 11),
    ("a leaver of the 10th: the 16 days", 16, 16, 16, 0, 16),
]
for what, on_payroll, counted, frappe_paid, lwp, wanted in PER_METER:
    got = R.slip_days(26, on_payroll, counted, frappe_paid, lwp, output_paid=True)
    check("per meter: %s" % what, got == (26, wanted), got)
check("per meter on the calendar: every day they are on the payroll",
      R.calendar_days(31, 31, 31, 28, 0, output_paid=True) == (31, 31)
      and R.calendar_days(31, 11, 11, 8, 0, output_paid=True) == (31, 11))
check("only Per Meter is paid whole: the other categories still lose an absent day",
      R.is_output_paid("Per Meter") and not R.is_output_paid("Regular") and not R.is_output_paid("Per Piece")
      and not R.is_output_paid("Weekly") and not R.is_output_paid(None))
check("a preview is the whole month for anyone", R.slip_days(26, 0, 0, 0, 0, preview=True, output_paid=True) == (26, 26))
month = body("set_month")
check("a slip's pay is still worked out on the 26, the days shown from the same facts, after it",
      "counted = rules.slip_days(days, output_paid=output_paid, **facts)" in month
      and "slip.total_working_days, slip.payment_days = counted" in month
      and "slip.custom_days_in_period, slip.custom_days_paid = rules.shown_days(\n        shown, period, "
          "(slip.total_working_days, slip.payment_days), facts, output_paid)" in month
      and month.index("facts = dict(") < month.index("rules.slip_days(days, output_paid=output_paid, **facts)")
      < month.index("rules.shown_days("))
check("a per meter slip is known by the employee's Pay Category, and shows no day absent",
      "output_paid = rules.is_output_paid(pay_category(slip.get(\"employee\")))" in month
      and "slip.absent_days, slip.leave_without_pay = 0, 0" in month
      and 'CATEGORY_FIELD = "custom_pay_category"' in glue)
check("the period is every day of it, not the days on the payroll",
      "period = date_diff(slip.end_date, slip.start_date) + 1" in month)
check("a slip left to Frappe HR shows Frappe HR's own count; a preview the whole month, on the days chosen",
      month.index("slip.custom_days_in_period, slip.custom_days_paid = slip.total_working_days, slip.payment_days")
      < month.index("if not days or not on_luuka_month(slip):")
      and "slip.custom_days_in_period, slip.custom_days_paid = (period, period) if shown == rules.CALENDAR \\\n"
          "            else (slip.total_working_days, slip.payment_days)" in month)
for name, label, after, about in (("custom_days_in_period", "Working Days", "total_working_days", "Days Shown on Slips"),
                                  ("custom_days_paid", "Payment Days", "payment_days", "Days Shown on Slips")):
    field = fields.get("Salary Slip-%s" % name) or {}
    check("the slip's %s: a read only number under Frappe HR's, in the fixtures the app ships" % label,
          (field.get("fieldtype"), field.get("label"), field.get("read_only"), field.get("no_copy"),
           field.get("insert_after")) == ("Float", label, 1, 1, after) and about in field.get("description", "")
          and '"Salary Slip-%s",' % name in hooks_src, field)
setters = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "property_setter.json"))}
for name in ("total_working_days", "payment_days"):
    setter = setters.get("Salary Slip-%s-hidden" % name) or {}
    check("Frappe HR's own %s, the 26 that pay works from, is hidden on the form: one Working Days and one Payment "
          "Days to read" % name,
          (setter.get("doc_type"), setter.get("field_name"), setter.get("property"), setter.get("value"))
          == ("Salary Slip", name, "hidden", "1") and '"Salary Slip-%s-hidden",' % name in hooks_src, setter)
register_glue = body("with_absent_amount")
check("the Salary Register's Payment Days are the days the slip shows",
      'PAID_FIELD = "custom_days_paid"' in glue and 'row["payment_days"] = flt(slip.get(PAID_FIELD))' in register_glue
      and 'fields=["name", ABSENT_FIELD, PAID_FIELD, "currency", "exchange_rate"]' in register_glue)
printed = read("hrms_addon", "hrms_addon", "payslip.py")
check("the Pay Slip prints them, as Luuka's own slip does: Paid Days 31, Working Days 31",
      '"paid_days": flt(doc.get("custom_days_paid")),' in printed
      and '"working_days": flt(doc.get("custom_days_in_period")),' in printed)
payroll_rules = load("payroll_register_rules")
check("and the payroll's Employees tab reads them",
      payroll_rules.SLIP_FIGURES["custom_working_days"] == "custom_days_in_period"
      and payroll_rules.SLIP_FIGURES["custom_paid_days"] == "custom_days_paid")
patches = read("hrms_addon", "patches.txt")
pay_month_patch = read("hrms_addon", "patches", "v1_0", "slip_days_on_the_pay_month.py")
check("the slips already made show their own 26 again, their pay left alone, unless the calendar is chosen",
      "hrms_addon.patches.v1_0.slip_days_on_the_pay_month" in read("hrms_addon", "patches.txt")
      and "if pay_days.days_shown() == rules.CALENDAR:\n        return" in pay_month_patch
      and '{"custom_days_in_period": working, "custom_days_paid": paid}' in pay_month_patch
      and '"payroll_frequency": "Monthly", "salary_slip_based_on_timesheet": 0' in pay_month_patch
      and "payment_days\"" not in pay_month_patch.split("set_value(")[-1].split(")")[0])
patch = read("hrms_addon", "patches", "v1_0", "slip_days_on_the_calendar.py")
check("slips already made are given them, once the fields are there, with their pay left alone",
      "hrms_addon.patches.v1_0.slip_days_on_the_calendar" in patches
      and patch.index('sync_fixtures("hrms_addon")') < patch.index("frappe.get_all(SLIP")
      and 'filters={"docstatus": ["<", 2]}, limit_page_length=0, fields=[' in patch
      and "update_modified=False" in patch and ".save(" not in patch
      and "total_working_days\":" not in patch and "if flt(slip.custom_days_in_period):\n            continue" in patch)
if os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_correction", "payroll_correction.py")):
    correction = open(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_correction",
                                   "payroll_correction.py"), encoding="utf-8").read()
    check("why Frappe HR's own two stay on the 26: a Payroll Correction prices a day from the slip's stored Working Days",
          'total_working_days = salary_slip.get("total_working_days", 1)' in correction
          and 'per_day_amount = flt(component_data["default_amount"] / total_working_days)' in correction)
    report = open(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "report", "salary_register", "salary_register.py"),
                  encoding="utf-8").read()
    check("Frappe HR's Salary Register has a Payment Days column for them",
          '"payment_days": ss.payment_days,' in report and '"fieldname": "payment_days",' in report)

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL PAY DAYS CHECKS PASSED")
