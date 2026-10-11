# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's pay slip, and the payroll period a slip is for.

The slip is printed the way Luuka's payroll has always printed it: who it
is for, PAYMENTS down to GROSS PAY, DEDUCTIONS down to TOTAL, NET PAY, then
the days. This file says what goes on it:

  lines         the earnings or deductions that are money paid or taken. A
                statistical component (Taxable Pay, Cash Gross Pay) and one
                left out of the totals (the employer's NSSF share) are the
                payroll's working, not lines of the slip; a line of nought
                (Local Service Tax outside July to October) is not printed
  slip_for      "SEPTEMBER 2026": the month the period closes in
  absent_amount what the days not worked took off the pay
  day_counts    leave taken and days absent, from the period's attendance

and what period a monthly payroll runs for:

  period_errors the 26th of one month to the 25th of the next, the same
                cycle the attendance register (LPL/HR/07), the advances,
                the loans and the penalties run on. A recovery is dated the
                25th, the day the period closes, so a payroll run for the
                25th to the 24th leaves every recovery of the month off the
                slip and takes it a month late.

No Frappe import: scripts/verify_payslip.py loads this file on its own.
"""

import calendar
import datetime

# the same cycle as attendance_rules and advance_rules; verify_payslip.py
# checks the three agree
CYCLE_START_DAY = 26
CYCLE_END_DAY = 25
MONTHLY = "Monthly"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")

ON_LEAVE, HALF_DAY, ABSENT = "On Leave", "Half Day", "Absent"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _day(value):
    value = _date(value)
    return value.strftime("%d-%m-%Y") if value else ""


# ── 1. The lines of the slip ──────────────────────────────────────────
# How Luuka's own slip names and orders its lines, by the Salary Component's
# name in lower case: what a site's components are given where nobody has
# said otherwise (payslip.seed_slip_names). Their slip prints the deductions
# NSSF, PAYE, Local Service Tax, then the advance; the salary structure has
# to work out the Local Service Tax first, because PAYE is charged after it.
SLIP_SEED = {
    "house rent allowance": {"name": "HRA"},
    "nssf employee": {"name": "NSSF", "order": 1},
    "nssf": {"order": 1},
    "payee": {"name": "PAYE", "order": 2},
    "paye": {"order": 2},
    "local service tax": {"order": 3},
    "advance recovery": {"name": "Advance Salary", "order": 4},
}
UNPLACED = 10 ** 6


def slip_name(component, given=None):
    """What a line is called on the slip: the component's Name on Pay Slip
    as it was typed, else the component's own name in capitals, as Luuka's
    slip prints BASIC and TRANSPORT ALLOWANCE."""
    given = str(given or "").strip()
    return given or str(component or "").upper()


def seed_for(component, current=None):
    """What to put on a component for Luuka's slip, where it is still
    blank: {"name", "order"} with only what is to be set. What somebody has
    typed is theirs."""
    wanted = SLIP_SEED.get(str(component or "").strip().lower())
    if not wanted:
        return {}
    current = current or {}
    out = {}
    if wanted.get("name") and not str(current.get("name") or "").strip():
        out["name"] = wanted["name"]
    if wanted.get("order") and not int(_num(current.get("order"))):
        out["order"] = wanted["order"]
    return out


def lines(rows, hours=None, shown=None):
    """[{"component", "name", "amount", "hours"}] for a slip's earnings or
    deductions. `hours` maps a row's Additional Salary to the hours it pays
    (overtime). `shown` maps a component to how it reads on the slip:
    {"name": its Name on Pay Slip, "order": its place}. Lines with a place
    come first, in it; the rest follow in the slip's own order."""
    hours, shown = hours or {}, shown or {}
    out = []
    for index, row in enumerate(rows or []):
        if int(_num(row.get("statistical_component"))) or int(_num(row.get("do_not_include_in_total"))):
            continue
        amount = _num(row.get("amount"))
        if not amount:
            continue
        component = row.get("salary_component") or ""
        how = shown.get(component) or {}
        place = int(_num(how.get("order")))
        out.append(((place if place > 0 else UNPLACED, index),
                    {"component": component, "name": slip_name(component, how.get("name")), "amount": amount,
                     "hours": _num(hours.get(row.get("additional_salary"))) or None}))
    return [line for _at, line in sorted(out, key=lambda pair: pair[0])]


def total(shown):
    return round(sum(_num(line.get("amount")) for line in shown or []), 2)


def slip_for(end_date):
    """The month a slip is for: the one its period closes in."""
    day = _date(end_date)
    return "%s %d" % (MONTHS[day.month - 1].upper(), day.year) if day else ""


def absent_amount(earnings):
    """What the days not paid took off: for each earning that follows the
    payment days, its full amount less what was paid."""
    lost = 0.0
    for row in earnings or []:
        if int(_num(row.get("statistical_component"))) or int(_num(row.get("do_not_include_in_total"))):
            continue
        if not int(_num(row.get("depends_on_payment_days"))) or row.get("additional_salary"):
            continue
        full, paid = _num(row.get("default_amount")), _num(row.get("amount"))
        if full > paid:
            lost += full - paid
    return round(lost, 2)


def day_counts(attendance):
    """(leave taken, days absent) from the period's attendance rows
    ({"status", "leave_type"}). A half day on leave is half a day of leave;
    a half day without leave is half a day absent."""
    leave = absent = 0.0
    for row in attendance or []:
        status = row.get("status")
        if status == ON_LEAVE:
            leave += 1
        elif status == ABSENT:
            absent += 1
        elif status == HALF_DAY:
            if row.get("leave_type"):
                leave += 0.5
            else:
                absent += 0.5
    return leave, absent


# ── 2. The payroll period ─────────────────────────────────────────────
def period_of(day):
    """(first day, last day) of the payroll period a day falls in."""
    day = _date(day)
    if day.day >= CYCLE_START_DAY:
        start = datetime.date(day.year, day.month, CYCLE_START_DAY)
    else:
        year, month = (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)
        start = datetime.date(year, month, min(CYCLE_START_DAY, calendar.monthrange(year, month)[1]))
    year, month = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    end = datetime.date(year, month, min(CYCLE_END_DAY, calendar.monthrange(year, month)[1]))
    return start, end


def period_errors(frequency, start_date, end_date):
    """Why a monthly payroll cannot run for these dates, as messages. Other
    frequencies are not Luuka's cycle and are left alone."""
    if (frequency or MONTHLY) != MONTHLY:
        return []
    start, end = _date(start_date), _date(end_date)
    if not start or not end:
        return []
    # the period most of these days fall in: the 25th to the 24th is meant
    # for the cycle that opens the day after
    wanted_start, wanted_end = period_of(start + (end - start) / 2)
    if (start, end) == (wanted_start, wanted_end):
        return []
    return ["The payroll period runs from the %dth to the %dth. For %s use %s to %s, not %s to %s: what is "
            "recovered from the month's pay (advances, loans, penalties) is dated %s and would be left off."
            % (CYCLE_START_DAY, CYCLE_END_DAY, slip_for(wanted_end).title(), _day(wanted_start), _day(wanted_end),
               _day(start), _day(end), _day(wanted_end))]
