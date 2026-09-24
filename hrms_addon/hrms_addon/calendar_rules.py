# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR calendar's rules: the month, its days and weeks, what a leave cell
shows, and what a day's count of people off means.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_calendar.py exercises them without a bench.
"""
import calendar
import datetime

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# what a leave cell shows: the stronger fact on a day wins, as Frappe HR's
# roster has it, a holiday over everything
HOLIDAY, APPROVED, APPLIED, PLANNED = "holiday", "approved", "applied", "planned"
KINDS = (HOLIDAY, APPROVED, APPLIED, PLANNED)
STRENGTH = {HOLIDAY: 4, APPROVED: 3, APPLIED: 2, PLANNED: 1}

# what a training session shows as
SCHEDULED, COMPLETED, PLANNED_SESSION = "scheduled", "completed", "planned"


def month_of(year, month, today):
    """The month asked for, else the one today is in."""
    today = _date(today)
    year = int(year or 0) or today.year
    month = int(month or 0) or today.month
    if not 1 <= month <= 12:
        raise ValueError("month %r" % month)
    return year, month


def month_window(year, month):
    year, month = int(year), int(month)
    return datetime.date(year, month, 1), datetime.date(year, month, calendar.monthrange(year, month)[1])


def month_title(year, month):
    return "%s %d" % (MONTHS[int(month) - 1], int(year))


def days(year, month, holidays=None, today=None):
    """The month's days: the date, its number, its weekday, the holiday it
    is (if any) and whether it is today. holidays: {date: description}."""
    start, end = month_window(year, month)
    holidays = {_date(day): text for day, text in (holidays or {}).items()}
    today = _date(today) if today else None
    out = []
    day = start
    while day <= end:
        out.append({"date": day.isoformat(), "day": day.day, "weekday": WEEKDAYS[day.weekday()],
                    "holiday": holidays.get(day), "today": day == today})
        day += datetime.timedelta(days=1)
    return out


def weeks(month_days):
    """The days as a wall calendar shows them: rows of seven, Monday first,
    None where the month is not."""
    rows = []
    if not month_days:
        return rows
    row = [None] * _date(month_days[0]["date"]).weekday()
    for day in month_days:
        row.append(day)
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        rows.append(row + [None] * (7 - len(row)))
    return rows


def common_holidays(lists):
    """The holidays everybody shown has: {date: description}, for the header."""
    lists = [dict(one or {}) for one in lists]
    if not lists:
        return {}
    shared = set(lists[0])
    for one in lists[1:]:
        shared &= set(one)
    return {day: lists[0][day] for day in shared}


def leave_kind(docstatus, status):
    """What a Leave Application is on the calendar: approved, still applied
    for, or nothing (refused, cancelled)."""
    if int(docstatus or 0) == 2 or status in ("Rejected", "Cancelled"):
        return None
    if int(docstatus or 0) == 1 and status == "Approved":
        return APPROVED
    return APPLIED


def span_days(first, last, start, end):
    """The days from `first` to `last` that fall between `start` and `end`."""
    first, last = _date(first), _date(last)
    if not first or not last:
        return []
    day, until = max(first, _date(start)), min(last, _date(end))
    out = []
    while day <= until:
        out.append(day.isoformat())
        day += datetime.timedelta(days=1)
    return out


def leave_cells(applications, planned, holidays, start, end):
    """{employee: {date: {"kind", "label", "link"}}} for the month.

    applications: employee, from_date, to_date, kind, label, link.
    planned: employee, planned_from, planned_to, label, link.
    holidays: {employee: {date: description}}.
    """
    cells = {}

    def put(employee, day, cell):
        mine = cells.setdefault(employee, {})
        have = mine.get(day)
        if have is None or STRENGTH[cell["kind"]] > STRENGTH[have["kind"]]:
            mine[day] = cell

    for row in planned or ():
        for day in span_days(row.get("planned_from"), row.get("planned_to"), start, end):
            put(row["employee"], day, {"kind": PLANNED, "label": row.get("label") or "Planned",
                                       "link": row.get("link")})
    for row in applications or ():
        if row.get("kind") not in (APPROVED, APPLIED):
            continue
        for day in span_days(row.get("from_date"), row.get("to_date"), start, end):
            put(row["employee"], day, {"kind": row["kind"], "label": row.get("label") or row["kind"].title(),
                                       "link": row.get("link")})
    for employee, dated in (holidays or {}).items():
        for day, text in dated.items():
            for same in span_days(day, day, start, end):
                put(employee, same, {"kind": HOLIDAY, "label": text or "Holiday", "link": None})
    return cells


def off_counts(cells, month_days):
    """Per day, how many are off (approved or applied for) and how many more
    only have leave planned."""
    off = {day["date"]: 0 for day in month_days}
    planned = dict(off)
    for mine in cells.values():
        for day, cell in mine.items():
            if day not in off:
                continue
            if cell["kind"] in (APPROVED, APPLIED):
                off[day] += 1
            elif cell["kind"] == PLANNED:
                planned[day] += 1
    return {"off": off, "planned": planned}


def too_many(count, most_off):
    """Whether a day's count is more than the plan allows off at once (0: no limit)."""
    return bool(int(most_off or 0)) and int(count or 0) > int(most_off)


def session_status(event_status, docstatus=0):
    """What a Training Event shows as; None when it is off the calendar."""
    if int(docstatus or 0) == 2 or event_status == "Cancelled":
        return None
    return COMPLETED if event_status == "Completed" else SCHEDULED


def clock(value):
    """'07:00' from a datetime, a time, a duration or their text; '' from nothing."""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime.datetime):
        return value.strftime("%H:%M")
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime.timedelta):
        value = datetime.datetime.min + value
        return value.strftime("%H:%M")
    text = str(value).strip()
    if len(text) >= 16 and text[10] in " T":
        text = text[11:]
    parts = text.split(":")
    if not parts[0].strip().isdigit():
        return ""
    return "%02d:%02d" % (int(parts[0]), int(parts[1]) if len(parts) > 1 and parts[1][:2].isdigit() else 0)


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
