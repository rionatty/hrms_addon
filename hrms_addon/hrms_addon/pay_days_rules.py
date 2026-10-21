# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's day of pay: the month's pay over 26 days.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_pay_days.py runs it without a bench. pay_days.py puts it on
Frappe HR's own Salary Slip and Overtime Slip.

WHAT LUUKA DO

Luuka's payroll (the September 2026 register, 1,535 people) prices a day at
the month's pay divided by 26, whatever the month's length (Luuka, 21 Oct
2026: "when computing hourly rate for over time use 26days ... basic pay is
computed from working days"):

  a day absent      Basic Salary x days absent / 26 is the Absent Amt, and
                    the basic paid is the rest (BASIC EARNED). 800,000 with
                    a day absent is 769,231, not 774,194 (30 of 31 days)
  a part month      the days on the payroll / 26: a hire of 15 September,
                    11 days of the cycle, is paid 500,000 x 11 / 26 = 211,539
  an hour of overtime   the month's pay / 26 / the day's standard hours

WHAT FRAPPE HR DOES

Frappe HR counts the period's own days (31, 30 or 28, less the holidays
where Payroll Settings leave them out) and pays each earning that follows
the payment days by Payment Days / Working Days. Its Overtime Slip divides a
month's pay by the slip's Payment Days. So once Frappe HR has counted, the
slip is given 26 Working Days, and its Payment Days are the days on the
payroll, up to 26, less every day Frappe HR took off: leave without pay,
absences, unmarked days it counts as absent, half days, and a Payroll
Correction it gave back.
"""

# Luuka's month; Payroll Settings' Days in a Pay Month says otherwise
DAYS_IN_MONTH = 26


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def slip_days(days, on_payroll, counted_from, paid, without_pay, preview=False):
    """(Working Days, Payment Days) on a month of `days` days, or None to
    leave Frappe HR's own count (`days` 0 or less).

    on_payroll     the period's calendar days the employee is on the payroll:
                   from the first day or the day they joined, to the last day
                   or the day they left
    counted_from   the days Frappe HR counted the payment from: the same,
                   less the holidays where Payroll Settings leave them out
    paid           the Payment Days Frappe HR came to
    without_pay    the leave without pay Frappe HR counted
    preview        a slip worked out for a whole month (a preview): all of it
    """
    days = _num(days)
    if days <= 0:
        return None
    if preview:
        return days, days
    counted_from, paid = _num(counted_from), _num(paid)
    if counted_from <= _num(without_pay):
        # leave without pay took every day: Frappe HR pays none, and what
        # it pays all the same is a Payroll Correction it gave back
        return days, max(paid, 0.0)
    taken = counted_from - paid
    return days, max(0.0, min(_num(on_payroll), days) - taken)


def hourly_rate(monthly, days, standard_hours):
    """An hour of the month's pay: monthly / days / the day's standard hours."""
    monthly, days, standard_hours = _num(monthly), _num(days), _num(standard_hours)
    if not (monthly and days > 0 and standard_hours > 0):
        return 0.0
    return monthly / days / standard_hours


def full_amount(row):
    """What an earning row of a slip comes to for the whole month: the
    structure's amount (default_amount) and an Additional Salary's whole
    amount (additional_amount). Frappe HR writes only the amount paid back
    on the row, so both are still the month's."""
    return _num(row.get("default_amount")) + _num(row.get("additional_amount"))
