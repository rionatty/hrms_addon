# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave earned by the days worked.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_leave_accrual.py exercises them without a bench.

Luuka's leave is earned: what an employee may take is what they have worked
for, not the whole year's at once. How a leave type is earned is Frappe
HR's own standard setting on the Leave Type (Is Earned Leave, Earned Leave
Frequency, Allocate on Day, Rounding) and how much a year is the annual
allocation on the employee's Leave Policy. What this adds is the days
worked: each period's share is earned in proportion to the days of it the
employee actually worked, so a new joiner, a leaver, a day of leave without
pay and (unless Leave Management Settings say otherwise) a day absent all
earn less.

  periods       the frequency's periods of the leave year, as Frappe HR
                counts them: calendar months, quarters, halves or years
  credited_on   the day a period's leave is earned (Allocate on Day)
  earned        what has been earned by a day, period by period, rounded
                down to the Leave Type's Rounding so nothing not yet earned
                is ever counted
  available     what can still be taken: Frappe HR's balance, less what
                is allocated but not yet earned, less what is waiting for
                approval
"""

import calendar
import datetime
import math

FREQUENCIES = {"Monthly": 12, "Quarterly": 4, "Half-Yearly": 2, "Yearly": 1}
MONTHS_IN = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
DEFAULT_FREQUENCY = "Monthly"
FIRST_DAY, LAST_DAY, JOINING_DAY = "First Day", "Last Day", "Date of Joining"
ROUNDING_STEPS = {"0.25": 0.25, "0.5": 0.5, "1.0": 1.0, "1": 1.0}

# Leave Management Settings: up to which day leave is counted as earned
UP_TO_LEAVE_START, UP_TO_APPLYING = "The Day the Leave Starts", "The Day of Applying"
UP_TO = (UP_TO_LEAVE_START, UP_TO_APPLYING)

# Frappe HR's attendance statuses that mean the day was not worked
ABSENT = "Absent"


def earns(leave_type):
    """Whether a leave type is earned: Frappe HR's Is Earned Leave, and not
    leave without pay. leave_type: "is_earned_leave", "is_lwp"."""
    return bool(leave_type) and bool(int(leave_type.get("is_earned_leave") or 0)) \
        and not int(leave_type.get("is_lwp") or 0)


def period_of(day, frequency=DEFAULT_FREQUENCY):
    """(first day, last day) of the calendar period a day falls in."""
    day = _date(day)
    months = MONTHS_IN.get(frequency or DEFAULT_FREQUENCY, 1)
    first_month = (day.month - 1) // months * months + 1
    last_month = first_month + months - 1
    return (datetime.date(day.year, first_month, 1),
            datetime.date(day.year, last_month, calendar.monthrange(day.year, last_month)[1]))


def periods(start, end, frequency=DEFAULT_FREQUENCY):
    """[(period start, period end, from, to)]: every period overlapping the
    window, whole, and the part of it inside the window."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return []
    out = []
    day = start
    while day <= end:
        first, last = period_of(day, frequency)
        out.append((first, last, max(first, start), min(last, end)))
        day = last + datetime.timedelta(days=1)
    return out


def credited_on(first, last, allocate_on_day=LAST_DAY, joining=None):
    """The day a period's leave is earned: its first day, its last day, or
    the day of the month the employee joined on."""
    if allocate_on_day == FIRST_DAY:
        return first
    if allocate_on_day == JOINING_DAY and _date(joining):
        joined = _date(joining)
        return datetime.date(first.year, first.month,
                             min(joined.day, calendar.monthrange(first.year, first.month)[1]))
    return last


def worked_days(start, end, employed_from=None, employed_to=None, off=None):
    """The days between two days the employee was employed and not off. off:
    {date: the part of the day not worked, 1 or 0.5}."""
    start, end = _date(start), _date(end)
    low = max(start, _date(employed_from)) if _date(employed_from) else start
    high = min(end, _date(employed_to)) if _date(employed_to) else end
    if not low or not high or high < low:
        return 0.0
    days = (high - low).days + 1
    missed = sum(_num(part) for day, part in (off or {}).items() if low <= _date(day) <= high)
    return max(days - missed, 0.0)


def days_off(start, end, employed_from=None, employed_to=None, off=None):
    """The days not worked in the part of the window the employee was employed."""
    start, end = _date(start), _date(end)
    low = max(start, _date(employed_from)) if _date(employed_from) else start
    high = min(end, _date(employed_to)) if _date(employed_to) else end
    if not low or not high or high < low:
        return 0.0
    return sum(_num(part) for day, part in (off or {}).items() if low <= _date(day) <= high)


def year_days(start):
    """The days in the year from a day: 365, or 366 over a 29 February."""
    start = _date(start)
    try:
        after = start.replace(year=start.year + 1)
    except ValueError:  # 29 February
        after = datetime.date(start.year + 1, 3, 1)
    return (after - start).days


def per_year(policy_days=None, allocated=None, window_start=None, window_end=None, joining=None, relieving=None):
    """How many days a year the employee earns. The Leave Policy's annual
    allocation when there is one; otherwise what the allocation gives for
    its window, spread over the part of it they are employed and worked out
    for a year, so an allocation made for a new joiner's months earns the
    same rate as a full year's."""
    if _num(policy_days) > 0:
        return round(_num(policy_days), 6)
    if _num(allocated) <= 0 or not (_date(window_start) and _date(window_end)):
        return 0.0
    employed = worked_days(window_start, window_end, joining, relieving)
    if employed <= 0:
        return 0.0
    return round(_num(allocated) * year_days(window_start) / employed, 6)


def step_down(value, rounding=None):
    """Down to the Leave Type's Rounding, or to two places when it has none."""
    value = round(_num(value), 6)
    step = ROUNDING_STEPS.get(str(rounding or "").strip())
    if not step:
        return math.floor(value * 100 + 1e-6) / 100.0
    return math.floor(value / step + 1e-6) * step


def earned(facts):
    """What has been earned by a day.

    facts: "per_year" (days a year), "window_start", "window_end" (the leave
    year), "frequency", "allocate_on_day", "rounding", "as_of", "joining",
    "relieving", "off" ({date: part of the day not worked}).

    Returns {"earned", "days_worked", "days_off", "periods"}: each period
    ("from", "to", "credited_on", "worked", "days", "earned", "credited").
    A day after today is counted as worked unless it is already known not
    to be (leave without pay approved for it): that is what "earned by the
    day the leave starts" means for a leave still to come.
    """
    rate = _num(facts.get("per_year"))
    start, end = _date(facts.get("window_start")), _date(facts.get("window_end"))
    as_of = _date(facts.get("as_of"))
    frequency = facts.get("frequency") if facts.get("frequency") in FREQUENCIES else DEFAULT_FREQUENCY
    joining, relieving, off = facts.get("joining"), facts.get("relieving"), facts.get("off") or {}
    out = {"earned": 0.0, "days_worked": 0.0, "days_off": 0.0, "periods": []}
    if not (start and end and as_of) or rate <= 0:
        return out
    share = rate / FREQUENCIES[frequency]
    raw = 0.0
    for first, last, low, high in periods(start, end, frequency):
        on = credited_on(first, last, facts.get("allocate_on_day"), joining)
        on = min(max(on, low), high)
        worked = worked_days(low, high, joining, relieving, off)
        amount = share * worked / ((last - first).days + 1)
        credited = on <= as_of and worked > 0
        if credited:
            raw += amount
        out["periods"].append({"from": low, "to": high, "credited_on": on, "worked": worked,
                               "days": (high - low).days + 1, "earned": round(amount, 4), "credited": credited})
    cap = rate * max(1.0, ((end - start).days + 1) / float(year_days(start)))
    out["earned"] = step_down(min(raw, cap), facts.get("rounding"))
    upto = min(as_of, end)
    out["days_worked"] = worked_days(start, upto, joining, relieving, off)
    out["days_off"] = days_off(start, upto, joining, relieving, off)
    return out


def unpaid_days(spans, holidays=None):
    """{date: part not worked} for leave without pay. spans: "from_date",
    "to_date", "half_day", "half_day_date", "include_holiday"; holidays: the
    employee's holidays, which leave without pay does not take unless its
    type counts them."""
    off = {}
    shut = {_date(day) for day in holidays or ()}
    for span in spans or ():
        first, last = _date(span.get("from_date")), _date(span.get("to_date"))
        if not first or not last or last < first:
            continue
        half = _date(span.get("half_day_date")) if int(span.get("half_day") or 0) else None
        if int(span.get("half_day") or 0) and not half and first == last:
            half = first
        day = first
        while day <= last:
            if int(span.get("include_holiday") or 0) or day not in shut:
                off[day] = max(off.get(day, 0.0), 0.5 if day == half else 1.0)
            day += datetime.timedelta(days=1)
    return off


def merge_off(*parts):
    """One {date: part not worked} from several, the larger part on a day
    both have."""
    out = {}
    for part in parts:
        for day, value in (part or {}).items():
            day = _date(day)
            if day:
                out[day] = max(out.get(day, 0.0), min(_num(value), 1.0))
    return out


def available(balance, credited, earned_days, pending=0.0):
    """What can be taken: Frappe HR's balance (brought forward included),
    less what is allocated for the year but not yet earned, less what is
    waiting for approval."""
    unearned = max(_num(credited) - _num(earned_days), 0.0)
    return round(_num(balance) - unearned - _num(pending), 2)


def unearned(credited, earned_days):
    """What an allocation gives that was never earned."""
    return round(max(_num(credited) - _num(earned_days), 0.0), 2)


def accrual_errors(facts):
    """Why a leave cannot be taken as applied for, as user-facing messages.

    facts: "leave_type", "days" (applied for), "available", "earned",
    "days_worked", "carried", "as_of".
    """
    days, left = _num(facts.get("days")), _num(facts.get("available"))
    if days <= left + 1e-6:
        return []
    return ["%g day(s) of %s applied for, %g can be taken. By %s %g day(s) are earned from %g day(s) worked "
            "and %g brought forward; the rest are taken or waiting for approval. Apply for Leave Without Pay "
            "for the other %g day(s)." % (days, facts.get("leave_type") or "leave", max(left, 0.0),
                                          _day(facts.get("as_of")), _num(facts.get("earned")),
                                          _num(facts.get("days_worked")), _num(facts.get("carried")),
                                          round(days - max(left, 0.0), 2))]


def count_up_to(setting, leave_start, applied_on):
    """The day leave is counted as earned up to, by Leave Management Settings."""
    if setting == UP_TO_APPLYING and _date(applied_on):
        return _date(applied_on)
    return _date(leave_start) or _date(applied_on)


def _day(value):
    value = _date(value)
    return value.strftime("%d %b %Y").lstrip("0") if value else ""


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    try:
        return datetime.date(*(int(part) for part in str(value)[:10].split("-")))
    except (ValueError, TypeError):
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
