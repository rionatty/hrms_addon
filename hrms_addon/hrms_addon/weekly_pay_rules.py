# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casuals paid by the week, as rules with no Frappe import (on the site:
weekly_pay.py; scripts/verify_weekly_pay.py).

Luuka, 5 Nov 2026: casuals are paid weekly on Thursdays; a payroll "should pick
from attendace and from last executed"; Per Meter and Per Piece stay monthly;
PAYE, NSSF and LST "not at all"; and their Pay Category says Weekly, not Hourly.

THE DATES

A weekly payroll starts the day after the last one for the same people stopped,
and stops on the last day with attendance before today, today not being over.
The first has nothing to go from: it is a week ending on that last day, and its
Start can be changed.

THE DAYS

A person is paid for each day marked as worked that no submitted slip has paid.
A slip lists the days it paid, so a day marked after its week was paid goes on
the next slip, and a cancelled slip gives its days back. Days before the
company's first weekly payroll are never counted, nor days a monthly slip of
theirs covers: someone moved from monthly to weekly is not paid twice.

THE PAY

The hours of those days at their rate: what the clock shows up to the standard
day. A day marked with nothing from the clock, as an uploaded one is, pays the
standard day, or half of it for a Half Day.

THE RATE (Luuka, 10 Nov 2026: "the hourly rate should be independent doctype it
shouldnt be on employee what if the employee updates his her personal rate?")

A casual's rate is an Hourly Rate of their own, from a day, which only HR can
open; a raise is a new one from the day it starts, so the days before it keep
the rate they were worked at. Each day on a slip is paid at the rate in force
that day, and shows it; one with none takes Output Pay Settings' standard rate.

TWO KINDS OF CASUAL (Luuka, 10 Nov 2026, with their casual worksheet)

"casual is divided into two, one that is paid per piece and the one they are
paid by the number of working hours and each hour has a rate": Weekly, by the
hour, and Per Piece, by the bags packed at each bag's price. One weekly payroll
pays both. A Per Piece casual's week comes from their Per Piece reports, the
weekly workbook uploaded on the week's Output Pay Run (piece_pay.py), which is
worked out apart from the payroll and feeds it: each person is paid as
Additional Salary dated the week's last day, with the arrears beside it.

OVERTIME BY THE WEEK

The worksheet pays a casual's overtime in the week, at their own hourly rate
times one and a half. The overtime is still asked for and approved as anyone's
is (overtime.py), which writes the hours paid and the Overtime Type onto the
day's attendance; the weekly slip pays those hours at the casual's own rate
times the multiplier the type gives that day, and notes them beside the day.
Overtime approved after its day was paid goes on the next slip.

A MONTHLY PAYROLL

Once weekly pay has begun, from the Start of the company's first weekly
payroll, a monthly payroll leaves the casuals out: a monthly slip reads every
Additional Salary dated in its month, and would pay a Per Piece casual's weeks
again. A monthly payroll ending before weekly pay began pays them as before.
"""

import datetime

WEEKLY = "Weekly"
PER_PIECE = "Per Piece"
# who a weekly payroll pays: the casuals by the hour and by the piece (Per Meter is paid monthly)
CATEGORIES = (WEEKLY, PER_PIECE)
# what the weekly structure's two lines read: the hours at the rate, and the overtime
PAY = "weekly_pay"
OVERTIME = "weekly_overtime"
WORKED = ("Present", "Half Day", "Work From Home")
HALF_DAY = "Half Day"
# what a payroll can be narrowed to: two reach the same people unless one of these differs
FILTERS = ("branch", "department", "designation", "grade")
# a first payroll has nothing to go from: a week, this many days back from its last
FIRST_WEEK_BACK = 6
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def shown(value):
    """A date as a message says it: 29 Oct 2026."""
    day = _date(value)
    return "%d %s %d" % (day.day, MONTHS[day.month - 1], day.year) if day else ""


def on_weekly_pay(doc):
    """Whether a payroll or a slip is a week's, from attendance and not from timesheets."""
    return doc.get("payroll_frequency") == WEEKLY and not int(_num(doc.get("salary_slip_based_on_timesheet")))


# ── The days and the pay ──────────────────────────────
def day_hours(status, worked, standard):
    """The hours a day pays. standard: the hours of a day, Output Pay Settings' or the register's."""
    day, hours = _num(standard), _num(worked)
    if hours > 0:
        return round(min(hours, day), 2)
    return round(day / 2.0 if status == HALF_DAY else day, 2)


def to_pay(attendance, paid, covered, standard):
    """The days still to pay a person, earliest first, one row a date:
    [{"attendance_date", "status", "hours"}]. attendance: [{"attendance_date", "status", "working_hours"}];
    paid: the dates submitted slips have paid; covered: [(first day, last day)] of their submitted monthly slips."""
    done = {_date(day) for day in paid or ()}
    spans = [(_date(first), _date(last)) for first, last in covered or ()]
    days = {}
    for row in attendance or []:
        day, status = _date(row.get("attendance_date")), row.get("status")
        if not day or status not in WORKED or day in done or any(first <= day <= last for first, last in spans):
            continue
        seat = days.setdefault(day, {"attendance_date": day, "status": status, "hours": 0.0})
        seat["hours"] = round(seat["hours"] + day_hours(status, row.get("working_hours"), standard), 2)
    return [days[day] for day in sorted(days)]


def overtime_to_pay(attendance, paid):
    """The approved overtime still to pay a person, earliest first: [{"attendance_date", "status", "hours",
    "overtime_type"}]. attendance: [{"attendance_date", "status", "actual_overtime_duration", "overtime_type"}],
    as the overtime module wrote them on approval; paid: {date: the overtime hours submitted slips paid for it}.
    Overtime with no type was never sent to payroll, and is not paid."""
    paid = {_date(day): _num(hours) for day, hours in (paid or {}).items()}
    out = []
    for row in attendance or []:
        day = _date(row.get("attendance_date"))
        hours = round(_num(row.get("actual_overtime_duration")) - paid.get(day, 0.0), 2)
        if day and row.get("overtime_type") and hours > 0:
            out.append({"attendance_date": day, "status": row.get("status"), "hours": hours,
                        "overtime_type": row.get("overtime_type")})
    return sorted(out, key=lambda row: row["attendance_date"])


def overtime_amount(rows, rate, multipliers):
    """What the overtime comes to: each day's hours x the person's own hourly rate that day x the multiplier its
    Overtime Type gives that day. rate: one rate, or {date: rate}; multipliers: {date: multiplier}."""
    def rate_on_day(day):
        return _num(rate.get(day)) if isinstance(rate, dict) else _num(rate)

    return round(sum(_num(row.get("hours")) * rate_on_day(_date(row.get("attendance_date")))
                     * _num((multipliers or {}).get(_date(row.get("attendance_date")))) for row in rows or []), 2)


def rate_on(rates, day):
    """The hourly rate in force on a day: the one with the latest From on or before it; None before the first.
    rates: [{"rate", "from_date"}], a person's Hourly Rates."""
    day = _date(day)
    found = [row for row in rates or [] if day and _date(row.get("from_date")) and _date(row.get("from_date")) <= day
             and _num(row.get("rate")) > 0]
    return _num(max(found, key=lambda row: _date(row["from_date"]))["rate"]) if found else None


def day_rates(days, rates, standard=0):
    """{date: the rate each of these days is paid at}: the person's rate in force that day, else the standard
    rate. A day with neither is left out."""
    out = {}
    for day in days or []:
        rate = rate_on(rates, day) or _num(standard)
        if rate > 0:
            out[_date(day)] = rate
    return out


def unrated(table, rates_by_day):
    """The days of a slip's Days Paid that pay something, hours or overtime, and have no rate: [date]."""
    return [_date(row["attendance_date"]) for row in table or []
            if (_num(row.get("hours")) > 0 or _num(row.get("overtime_hours")) > 0)
            and _date(row["attendance_date"]) not in (rates_by_day or {})]


def week_pay(rows, hours=None, rate=None):
    """What a week's hours come to: each day's hours at the rate it carries (a slip's Days Paid). A slip written
    before its days carried their rates pays its hours at its one rate."""
    worked = [row for row in rows or [] if _num(row.get("hours")) > 0]
    if worked and all(_num(row.get("rate")) > 0 for row in worked):
        return round(sum(_num(row.get("hours")) * _num(row.get("rate")) for row in worked), 2)
    return amount(hours, rate)


def rate_errors(rate, from_date, clash=None):
    """What is wrong with an Hourly Rate, as messages. clash: the Hourly Rate the person already has from that
    day, if any."""
    errors = []
    if _num(rate) <= 0:
        errors.append("The hourly rate is more than nothing.")
    if not _date(from_date):
        errors.append("Say the day the rate starts.")
    if clash:
        errors.append("They already have a rate from that day (%s): change that one." % clash)
    return errors


def days_table(days, overtime):
    """A slip's Days Paid: each day it pays, with that day's overtime hours beside it, and a day whose
    overtime alone is paid now (approved after the day was) with no hours of its own."""
    rows = {_date(day["attendance_date"]): dict(day, overtime_hours=0.0) for day in days or []}
    for row in overtime or []:
        day = _date(row["attendance_date"])
        seat = rows.setdefault(day, {"attendance_date": day, "status": row.get("status"), "hours": 0.0,
                                     "overtime_hours": 0.0})
        seat["overtime_hours"] = round(_num(seat.get("overtime_hours")) + _num(row.get("hours")), 2)
    return [rows[day] for day in sorted(rows)]


def days_paid(rows):
    """The days a slip pays the hours of: its Days Paid, less those it pays only overtime for."""
    return len([row for row in rows or [] if _num(row.get("hours")) > 0])


def weekly_began(first_start, end):
    """Whether a monthly payroll ending on `end` reaches into weekly pay, which began on the Start of the
    company's first weekly payroll: its casuals are then the weekly payroll's."""
    first, end = _date(first_start), _date(end)
    return bool(first and end and end >= first)


def total_hours(days):
    return round(sum(_num(day.get("hours")) for day in days or []), 2)


def amount(hours, rate):
    return round(_num(hours) * _num(rate), 2)


# ── The dates ─────────────────────────────────────────
def same_people(one, other):
    """Whether two payrolls can reach the same people: no filter on which they differ."""
    return all(not one.get(field) or not other.get(field) or one.get(field) == other.get(field)
               for field in FILTERS)


def last_executed(runs, wanted):
    """The day the last payroll for these people stopped. runs: [{"end_date", and its FILTERS}]."""
    ends = [_date(run.get("end_date")) for run in runs or [] if same_people(run, wanted)]
    return max((day for day in ends if day), default=None)


def dates(last, latest):
    """{"start", "end", "last"} for a new payroll. last: where the last one stopped; latest: the last day with
    attendance before today. No End where there is no attendance after the last payroll: nothing to pay yet."""
    last, latest = _date(last), _date(latest)
    if last:
        start = last + datetime.timedelta(days=1)
        return {"start": start, "end": latest if latest and latest >= start else None, "last": last}
    if not latest:
        return {"start": None, "end": None, "last": None}
    return {"start": latest - datetime.timedelta(days=FIRST_WEEK_BACK), "end": latest, "last": None}


def date_errors(start, end, last=None):
    """Why a weekly payroll cannot run for these dates, as messages."""
    start, end, last = _date(start), _date(end), _date(last)
    if not start or not end or end >= start:
        return []
    if last:
        return ["The last weekly payroll stopped on %s: there is nothing to pay up to %s." % (shown(last), shown(end))]
    return ["The End Date cannot be before the Start Date."]


def earliest(*days):
    """The earliest of these days that is one."""
    found = [day for day in (_date(day) for day in days) if day]
    return min(found) if found else None


# ── What the payroll stands on ────────────────────────
def structure_name(abbr):
    """The company's weekly structure: a structure's name is the whole site's."""
    return "Weekly Casuals - %s" % abbr


def still_here(relieving_date, start):
    """Whether someone who may have left can be on a payroll starting then."""
    left, start = _date(relieving_date), _date(start)
    return not left or not start or left >= start


def assignment_from(joining, start, taken):
    """The day a person's assignment starts: when they joined, so that a payroll can start on any day after. The
    payroll's Start where they have another assignment from that day, as two cannot share one. None if both are
    taken. taken: the days their other assignments start."""
    busy = {_date(day) for day in taken or ()}
    for day in (_date(joining), _date(start)):
        if day and day not in busy:
            return day
    return None


def account_to_copy(rows, earnings, basic):
    """The account a new earning takes for a company: Basic's, else the one its earnings use most.
    rows: the company's [{"parent", "account"}]; earnings: the names of the Earning components."""
    theirs = [row for row in rows or [] if row.get("parent") in earnings and row.get("account")]
    for row in theirs:
        if row.get("parent") == basic:
            return row.get("account")
    used = {}
    for row in theirs:
        used[row.get("account")] = used.get(row.get("account"), 0) + 1
    return max(sorted(used), key=used.get) if used else None
