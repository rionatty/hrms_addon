# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""HR Overview: the figures on the HR home dashboard (page/hr_overview).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_hr_overview.py exercises them without a bench.

Every figure is worked out from what the site already records: the
employees' joining and relieving dates, the attendance marked, the
punches of the day, the appraisals and the user's own assignments.
"""

import calendar
import datetime

# the greeting, by the hour of the site's clock
GREETINGS = ((12, "Good morning"), (17, "Good afternoon"), (24, "Good evening"))

# the attendance chart's stack, bottom up, and what each Attendance status counts as
ATTENDANCE_KINDS = ("On Time", "Late", "Absent", "On Leave")
PRESENT = ("Present", "Half Day", "Work From Home")

# how far back the charts look
MONTHS_SHOWN = 12
DAYS_SHOWN = 7
TURNOVER_MONTHS = 12

# the appraisal bands, best first (appraisal_rules.BANDS)
BANDS = ("Excellent", "Very Good", "Good", "Average", "Below Average")

# a task's band in My Alerts -> how full its ring is drawn: the nearer, the fuller
TASK_RINGS = {"overdue": 100, "today": 85, "soon": 60, "later": 30, "none": 10}


def greeting(hour):
    """Good morning, afternoon or evening for an hour of the day (0-23)."""
    for upto, words in GREETINGS:
        if hour < upto:
            return words
    return GREETINGS[-1][1]


def percent(part, whole, places=1):
    """part of whole as a percent, 0 when there is no whole."""
    return round(100.0 * part / whole, places) if whole else 0.0


def month_ends(today, count=MONTHS_SHOWN):
    """The last day of each of the `count` months up to today's, oldest
    first; the current month ends today, since it has not ended yet."""
    ends = []
    year, month = today.year, today.month
    for _ in range(count):
        ends.append(today if (year, month) == (today.year, today.month) else _last_day(year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(ends))


def headcount_on(employees, day):
    """How many were employed on `day`: joined on or before it and not
    relieved before it. employees: [(date_of_joining, relieving_date)]."""
    return sum(1 for joined, relieved in employees
               if joined and joined <= day and (not relieved or relieved >= day))


def headcount_series(employees, ends):
    """The headcount at each date in `ends`."""
    return [headcount_on(employees, end) for end in ends]


def turnover(employees, today, months=TURNOVER_MONTHS):
    """Leavers over the last `months` months, and the rate: leavers over
    the average of the headcount at the start and today, as a percent."""
    start = months_back(today, months)
    leavers = sum(1 for _joined, relieved in employees if relieved and start < relieved <= today)
    average = (headcount_on(employees, start) + headcount_on(employees, today)) / 2.0
    return {"leavers": leavers, "rate": percent(leavers, average)}


def joined_between(employees, start, end):
    """How many joined from `start` to `end`, both days in."""
    return sum(1 for joined, _relieved in employees if joined and start <= joined <= end)


def recent_days(marked, today, count=DAYS_SHOWN):
    """The last `count` days with attendance marked, up to today, oldest first."""
    return sorted({day for day in marked if day and day <= today})[-count:]


def attendance_days(rows, days):
    """Each day's attendance as the chart stacks it: on time, late, absent,
    on leave. rows: [(attendance_date, status, late_entry)]."""
    table = {day: dict.fromkeys(ATTENDANCE_KINDS, 0) for day in days}
    for day, status, late in rows:
        if day not in table:
            continue
        if status in PRESENT:
            table[day]["Late" if late else "On Time"] += 1
        elif status == "Absent":
            table[day]["Absent"] += 1
        elif status == "On Leave":
            table[day]["On Leave"] += 1
    return [dict(table[day], date=day) for day in days]


def tally(values, order=()):
    """[(value, how many)]: those in `order` in that order, then the rest,
    most first; blanks counted as "Not Set"."""
    counts = {}
    for value in values:
        key = value or "Not Set"
        counts[key] = counts.get(key, 0) + 1
    known = [(value, counts.pop(value)) for value in order if value in counts]
    return known + sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def appraisal_summary(rows):
    """The appraisal gauge: how many of a cycle's appraisals are submitted,
    the average score of those, and how they fall into the bands.
    rows: [(docstatus, total score, band)]."""
    done = [(score, band) for docstatus, score, band in rows if docstatus == 1]
    scores = [float(score) for score, _band in done if score is not None]
    return {
        "total": len(rows),
        "submitted": len(done),
        "percent": percent(len(done), len(rows)),
        "average": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "bands": [(band, count) for band, count in tally([band for _score, band in done], BANDS) if band in BANDS],
    }


def task_ring(band):
    """How full a task's ring is drawn for its band in My Alerts."""
    return TASK_RINGS.get(band or "none", TASK_RINGS["none"])


def months_back(day, months):
    """The same day `months` months earlier, kept within that month."""
    year, month = day.year, day.month - months
    while month < 1:
        year, month = year - 1, month + 12
    return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _last_day(year, month):
    return datetime.date(year, month, calendar.monthrange(year, month)[1])
