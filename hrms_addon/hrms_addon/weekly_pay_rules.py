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
day, the rest being the overtime module's. A day marked with nothing from the
clock, as an uploaded one is, pays the standard day, or half of it for a Half
Day.
"""

import datetime

WEEKLY = "Weekly"
# what the weekly structure's one line reads
PAY = "weekly_pay"
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
