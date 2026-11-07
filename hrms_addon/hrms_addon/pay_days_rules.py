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
  an hour of overtime   the month's pay / 26 / 8, the standard working hours
                    of a day (Luuka, 21 Oct 2026: "standard woring hours is
                    8"): 800,000 is 3,846.15 an hour, whatever the shift.
                    When the clock counts overtime is the shift's own
                    figure (12 hours, 2 of them overtime); what an hour is
                    paid is this

WHAT FRAPPE HR DOES

Frappe HR counts the period's own days (31, 30 or 28, less the holidays
where Payroll Settings leave them out) and pays each earning that follows
the payment days by Payment Days / Working Days. Its Overtime Slip divides a
month's pay by the slip's Payment Days. So once Frappe HR has counted, the
slip is given 26 Working Days, and its Payment Days are the days on the
payroll, up to 26, less every day Frappe HR took off: leave without pay,
absences, unmarked days it counts as absent, half days, and a Payroll
Correction it gave back.

WHAT THE SLIP SHOWS

A slip shows its Working Days and Payment Days on the month of 26 its pay is
divided by (Luuka, 8 Nov 2026: "revert Working days to be considered need be
as 26"). On 1 Nov they had asked for the calendar's ("then you should include
holiday sunday"): 31 days in the cycle of 26 August, 30 Paid Days with a day
absent, and that day still a 26th of the pay. Payroll Settings' Days Shown on
Slips keeps both: Days in a Pay Month, the default, or Calendar Days
(calendar_days). Frappe HR's own Working Days and Payment Days stay on the 26
either way, hidden on the form: they are what it divides by, here and in a
Payroll Correction.

PER METER

Per meter staff are paid a basic that does not move and their output (Luuka,
8 Nov 2026: "For per metre, basic pay is untouched regardless of absence ...
Attendance is based on their output which is going uploaded as per meter").
Their slip loses no day to an absence or a leave: its Payment Days are the
days they are on the payroll, up to the month, so a part month is still a
part month.
"""

# Luuka's month, and its day; Payroll Settings' Days in a Pay Month and
# Hours in a Pay Day say otherwise
DAYS_IN_MONTH = 26
HOURS_IN_DAY = 8
# the days a slip shows: Payroll Settings' Days Shown on Slips
PAY_MONTH, CALENDAR = "Days in a Pay Month", "Calendar Days"
SHOWN = (PAY_MONTH, CALENDAR)
# the pay categories whose attendance is their output: no day of theirs is
# taken off for an absence
OUTPUT_PAID = ("Per Meter",)


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def is_output_paid(category):
    """Whether a pay category's slip is paid whole, whatever the attendance."""
    return (category or "") in OUTPUT_PAID


def slip_days(days, on_payroll, counted_from, paid, without_pay, preview=False, output_paid=False):
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
    output_paid    a per meter slip (is_output_paid): no absence or leave is
                   taken off, only the days off the payroll
    """
    days = _num(days)
    if days <= 0:
        return None
    if preview:
        return days, days
    if output_paid:
        return days, max(0.0, min(_num(on_payroll), days))
    counted_from, paid = _num(counted_from), _num(paid)
    if counted_from <= _num(without_pay):
        # leave without pay took every day: Frappe HR pays none, and what
        # it pays all the same is a Payroll Correction it gave back
        return days, max(paid, 0.0)
    taken = counted_from - paid
    return days, max(0.0, min(_num(on_payroll), days) - taken)


def calendar_days(period, on_payroll, counted_from, paid, without_pay, output_paid=False):
    """(Working Days, Payment Days) as the slip shows them: every day of the
    period, Sundays and holidays included, and the days on the payroll less
    every day Frappe HR took off.

    period         the period's calendar days
    the rest       as slip_days has them
    """
    on_payroll, counted_from, paid = _num(on_payroll), _num(counted_from), _num(paid)
    if output_paid:
        return _num(period), max(0.0, min(on_payroll, _num(period)))
    if counted_from <= _num(without_pay):
        # as slip_days: leave without pay took every day, and what is paid
        # all the same is a Payroll Correction it gave back
        return _num(period), max(paid, 0.0)
    return _num(period), max(0.0, min(on_payroll, on_payroll - (counted_from - paid)))


def shown_days(choice, period, month, facts, output_paid=False):
    """(Working Days, Payment Days) as the slip shows them: `month`, the days
    its pay is divided by (slip_days), or the calendar's where Payroll Settings
    choose CALENDAR. facts: on_payroll, counted_from, paid, without_pay."""
    if choice == CALENDAR:
        return calendar_days(period, output_paid=output_paid, **facts)
    return month


def hourly_rate(monthly, days, standard_hours):
    """An hour of the month's pay: monthly / days / the hours of a day (8)."""
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
