"""Checks what an employee's monthly gross is made of, without a bench.

    python scripts/verify_pay.py

  1  the allowances that are part of the gross: an earning paid every pay
     period as a recurring Additional Salary, in force on the day; never a
     payment made once, a deduction, a disabled one, or a component the
     slip leaves out of its gross
  2  the gross: the structure's with those on top, one that overwrites a
     structure component in its place; Luuka's own slip for LPL1834, whose
     salary advance is 40% of 878,400 and not of the Basic
  3  a pay period's amount as a month's
  4  pay.py works the gross out that way, and every module that needs a
     gross asks pay.py for it

The rules are loaded without Frappe.
"""
import importlib.util
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)
        print("FAIL", label)


def read(name):
    return io.open(os.path.join(APP, name), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("pay_rules")
V = load("advance_rules")


def row(component, amount, **more):
    base = {"salary_component": component, "amount": amount, "type": "Earning", "is_recurring": 1, "disabled": 0,
            "from_date": "2026-01-01", "to_date": "2026-12-31", "overwrite": 0}
    base.update(more)
    return base


# ── 1. which allowances count ───────────────────────────────────────────
HOUSE, TRANSPORT = row("House Rent Allowance", 72342), row("Transport Allowance", 70000)
names = lambda rows: [r["salary_component"] for r in rows]  # noqa: E731
check(names(R.standing([HOUSE, TRANSPORT], "2026-03-13")) == ["House Rent Allowance", "Transport Allowance"],
      "an earning paid every period, in force on the day, is part of the gross")
check(R.standing([row("Overtime", 54000, is_recurring=0)], "2026-03-13") == [], "a payment made once is not")
check(R.standing([row("Sacco Contribution", 30000, type="Deduction")], "2026-03-13") == [], "a deduction is not")
check(R.standing([row("House Rent Allowance", 72342, disabled=1)], "2026-03-13") == [], "a disabled one is not")
check(R.standing([row("House Rent Allowance", 72342, from_date="2026-04-01")], "2026-03-13") == [],
      "one that starts later is not yet")
check(R.standing([row("House Rent Allowance", 72342, to_date="2026-02-28")], "2026-03-13") == [],
      "one that has ended is no longer")
check(len(R.standing([row("A", 1, from_date="2026-03-13"), row("B", 1, to_date="2026-03-13")], "2026-03-13")) == 2,
      "the first and the last day count")
check(len(R.standing([row("A", 1, to_date=None)], "2026-03-13")) == 1, "no last day: still running")
check(R.standing([row("A", 0), row("B", -5)], "2026-03-13") == [], "nothing, or less than nothing, is no allowance")
check(names(R.standing([HOUSE, row("Taxable Salary", 736058)], "2026-03-13", {"Taxable Salary"})) == ["House Rent Allowance"],
      "a component the slip leaves out of its gross is left out here")
check(R.standing([HOUSE], None) == [] and R.standing(None, "2026-03-13") == [], "no day, or no rows")
check(len(R.standing([dict(HOUSE, type=None)], "2026-03-13")) == 1, "a row that does not say its type is an earning")

# ── 2. the gross ────────────────────────────────────────────────────────
luuka = R.gross_per_period(736058, [HOUSE, TRANSPORT])
check(luuka == 878400, "Basic 736,058 with House Rent 72,342 and Transport 70,000 is a gross of 878,400: %s" % luuka)
s = V.settings_from({})
check(V.entitled(V.SALARY_ADVANCE, luuka, V.MONTHLY, s) == 351360,
      "the salary advance is 40%% of it, 351,360, as on Luuka's own slip: %s" % V.entitled(V.SALARY_ADVANCE, luuka, V.MONTHLY, s))
check(V.entitled(V.SALARY_ADVANCE, 736058, V.MONTHLY, s) == 294423.2, "and was 294,423.20 on the Basic alone")
check(R.gross_per_period(736058, []) == 736058 and R.gross_per_period(736058, None) == 736058,
      "no standing allowance: the structure's gross as it is")
replaced = R.gross_per_period(878400, [row("House Rent Allowance", 90000, overwrite=1)], {"House Rent Allowance": 72342})
check(replaced == 896058, "an allowance that overwrites a structure component takes its place: %s" % replaced)
added = R.gross_per_period(878400, [row("House Rent Allowance", 90000, overwrite=0)], {"House Rent Allowance": 72342})
check(added == 968400, "one that does not overwrite is paid on top of it: %s" % added)
check(R.gross_per_period(736058, [row("House Rent Allowance", 90000, overwrite=1)], {}) == 826058,
      "overwriting a component the structure does not pay just adds it")
check(R.gross_per_period(736058, [row("A", 0.004), row("B", 0.004)]) == 736058.01, "rounded to the cent once, at the end")

# ── 3. a period as a month ──────────────────────────────────────────────
check(R.per_month(878400, "Monthly") == 878400 and R.per_month(878400, None) == 878400, "a monthly period is a month")
check(R.per_month(120000, "Weekly") == 520000 and R.per_month(240000, "Fortnightly") == 520000,
      "a weekly or fortnightly period as a month")
check(R.periods_in_year("Monthly") == 12 and R.periods_in_year("Weekly") == 52 and R.periods_in_year("x") == 12,
      "pay periods in a year; an unknown frequency is monthly")

# ── 4. wiring ───────────────────────────────────────────────────────────
pay = read("pay.py")
gross = pay.split("def monthly_gross(")[1].split("\ndef ")[0]
check("assignment.calculate_ctc_and_gross()" in gross and "annual_gross_earning" in gross,
      "the structure's part is still Frappe HR's own figure")
check("rules.gross_per_period(" in gross and "standing_allowances(employee, on)" in gross and "rules.per_month(" in gross,
      "monthly_gross adds the standing allowances in force on the day asked")
allowances = pay.split("def standing_allowances(")[1].split("\ndef ")[0]
check('"docstatus": 1' in allowances and '"is_recurring": 1' in allowances and '"employee": employee' in allowances,
      "only the employee's own submitted, recurring Additional Salary is read")
check("rules.standing(rows, day" in allowances and "_not_counted(name)" in allowances,
      "and judged by the rule, with the components a slip leaves out of its gross")
check(not re.search(r'"base"|\.base\b', pay), "the gross is never the assignment's Base")
for module in ("advances", "salary_advances", "leave_advances", "benefits", "encashments", "exits", "settlements",
               "loans", "overtime", "leave_overview"):
    source = read(module + ".py")
    check("pay.monthly_gross(" in source, "%s.py asks pay.py for the gross" % module)
    check('"Additional Salary", filters={"employee"' not in source.split("pay.monthly_gross(")[0][-400:],
          "%s.py does not add allowances of its own" % module)

print()
print("FAILED: %d" % len(fail) if fail else "ALL PAY CHECKS PASSED")
sys.exit(1 if fail else 0)
