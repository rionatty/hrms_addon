# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance and shift management: Luuka's own cycle, codes and forms.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_attendance.py exercises them without a bench.

THE MONTH RUNS 26 TO 25

Both minutes say it plainly: "the period from the 26th of the previous
month to the 25th of the current month" (Reward & Compensation, 4.6 and
4.12), and the Employee Attendance Form (LPL/HR/07) is ruled with day
columns running 26, 27 ... 31, 1, 2 ... 25. So a cycle is named for the
month it ends in, and everything the register and the payroll
reconciliation do is bounded by that window rather than by a calendar
month.

THE CODES

LPL/HR/07 prints its own legend — ABSENT = A, SICK LEAVE = S, WEEKLY OFF =
WO, LEAVE = L — and the production file adds the two that say which shift
was worked: M for day, N for night, plus O for off duty (Manufacturing
Excellence, 4.3). One register carries both, so a cell says either which
shift the employee worked or why they did not.

THE DAY

Working hours "are normally 12 hours, inclusive of 2 hours of overtime"
(Reward & Compensation, 4.2). So a full shift is twelve hours, ten of them
standard and two overtime, and anything past twelve is overtime on top.

Those two figures are a shift's own (Luuka, 11 Oct 2026: "add parameter
set for overtime hours, currently it is two hours"): each Shift Type says
how long it is and how many of its hours are overtime, so the office day
can be eight with none. A shift that says nothing is the twelve with two
(shift_hours).

THE FORMS

  LPL/HR/25  the Off-Duty Request: badge, department, section, the day off
             and why, classified Paid / Ungranted / Compensation / Annual
             leave / Compassionate, signed by the Supervisor and the
             Section Manager with remarks for the HR Manager
  LPL/HR/14  the Overtime Request: names, section, duration and employment
             on one sheet, a requesting officer, an authoriser, and the
             food coupon HR issues afterwards
  Gate Pass  leaving the premises before the hours are done
             (Reward & Compensation, 4.2)
"""

import calendar
import datetime

# ── The cycle ─────────────────────────────────────────────────────────
CYCLE_START_DAY = 26  # the 26th of the previous month opens the cycle
CYCLE_END_DAY = 25  # the 25th closes it

# ── What a cell of the register says ──────────────────────────────────
DAY_SHIFT, NIGHT_SHIFT = "M", "N"
ABSENT, SICK, WEEKLY_OFF, LEAVE, OFF_DUTY = "A", "S", "WO", "L", "O"
CODE_MEANING = {
    DAY_SHIFT: "Day shift",
    NIGHT_SHIFT: "Night shift",
    ABSENT: "Absent",
    SICK: "Sick leave",
    WEEKLY_OFF: "Weekly off",
    LEAVE: "Leave",
    OFF_DUTY: "Off duty",
}
CODES = tuple(CODE_MEANING)
# the footer of LPL/HR/07 counts these, per day
TALLIES = ("Permanents Day", "Casuals Day", "Permanents Night", "Casuals Night")

# ── The day ───────────────────────────────────────────────────────────
# what a shift is until its Shift Type says otherwise (shift_hours)
FULL_SHIFT_HOURS = 12.0  # "normally 12 hours, inclusive of 2 hours of overtime"
OVERTIME_IN_SHIFT = 2.0
STANDARD_HOURS = FULL_SHIFT_HOURS - OVERTIME_IN_SHIFT
LONGEST_SHIFT_HOURS = 24.0
# a casual works six days and takes one off each week, scattered
WORKING_DAYS_A_WEEK = 6

# ── LPL/HR/25 ─────────────────────────────────────────────────────────
OFF_DUTY_KINDS = ("Paid", "Ungranted", "Compensation", "Annual Leave", "Compassionate")
# ── LPL/HR/14 ─────────────────────────────────────────────────────────
EMPLOYMENT_KINDS = ("Permanent", "Casual")
# HR issues a food coupon to whoever worked the overtime
COUPON_KINDS = EMPLOYMENT_KINDS


def cycle_window(year, month):
    """(first day, last day) of the cycle that ENDS in `month` of `year`:
    the 26th of the month before to the 25th of this one."""
    year, month = int(year), int(month)
    start_year, start_month = (year - 1, 12) if month == 1 else (year, month - 1)
    start_day = min(CYCLE_START_DAY, calendar.monthrange(start_year, start_month)[1])
    end_day = min(CYCLE_END_DAY, calendar.monthrange(year, month)[1])
    return datetime.date(start_year, start_month, start_day), datetime.date(year, month, end_day)


def cycle_of(day):
    """(year, month) of the cycle a day falls in: the 26th onwards belongs
    to the month after."""
    day = _date(day)
    if day.day >= CYCLE_START_DAY:
        return (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return day.year, day.month


def cycle_days(year, month):
    """Every day of the cycle, in the order LPL/HR/07 rules its columns."""
    start, end = cycle_window(year, month)
    return [start + datetime.timedelta(days=step) for step in range((end - start).days + 1)]


def register_code(facts):
    """What LPL/HR/07 prints in a day's cell for one employee.

    facts: "status" (the Attendance status), "shift" (its name), "leave_type",
    "off_duty" (an approved off-duty request covers the day), "holiday".
    """
    status = (facts.get("status") or "").strip()
    if facts.get("off_duty"):
        return OFF_DUTY
    if status == "On Leave":
        if facts.get("leave_type") == UNPAID_SUSPENSION:
            return ABSENT
        return SICK if _is_sick(facts.get("leave_type")) else LEAVE
    if status == "Absent":
        return ABSENT
    if status in ("Present", "Half Day", "Work From Home"):
        return NIGHT_SHIFT if _is_night(facts.get("shift")) else DAY_SHIFT
    if facts.get("holiday"):
        return WEEKLY_OFF
    return ""


# a suspension's unpaid days, marked as leave of this type
# (suspension_rules.UNPAID_LEAVE): the register prints them as the absence
# they are paid as
UNPAID_SUSPENSION = "Suspension Without Pay"


def _is_sick(leave_type):
    return "sick" in (leave_type or "").lower()


def _is_night(shift):
    return "night" in (shift or "").lower()


def tallies(rows, days):
    """The footer of LPL/HR/07: how many of each kind worked each day.

    rows: [{"employment": "Permanent"|"Casual", "days": {date: code}}]
    Returns {tally: {date: count}} plus "Total number of staff in Night shift".
    """
    counted = {name: {day: 0 for day in days} for name in TALLIES}
    nights = {day: 0 for day in days}
    for row in rows or []:
        casual = (row.get("employment") or "").strip().lower().startswith("casual")
        for day in days:
            code = (row.get("days") or {}).get(day)
            if code == DAY_SHIFT:
                counted["Casuals Day" if casual else "Permanents Day"][day] += 1
            elif code == NIGHT_SHIFT:
                counted["Casuals Night" if casual else "Permanents Night"][day] += 1
                nights[day] += 1
    counted["Total number of staff in Night shift"] = nights
    return counted


def shift_hours(shift=None):
    """What a shift's day is made of, as {"full", "overtime", "standard"}.

    A Shift Type that gives its hours says how long it is and how many of
    them are overtime; the standard hours are the rest. One that gives no
    hours is the twelve with two of overtime.

    shift: {"shift_hours", "overtime_hours"} off the Shift Type, or None.
    """
    full = _hours((shift or {}).get("shift_hours"))
    if full <= 0:
        return {"full": FULL_SHIFT_HOURS, "overtime": OVERTIME_IN_SHIFT, "standard": STANDARD_HOURS}
    overtime = min(max(_hours(shift.get("overtime_hours")), 0.0), full)
    # a shift that is all overtime has no standard hour to price one from
    if overtime >= full:
        overtime = 0.0
    return {"full": full, "overtime": overtime, "standard": round(full - overtime, 2)}


def shift_hours_errors(facts):
    """Problems with the hours a Shift Type gives.

    facts: "shift_hours", "overtime_hours".
    """
    full, overtime = _hours(facts.get("shift_hours")), _hours(facts.get("overtime_hours"))
    errors = []
    if full < 0 or 0 < full < 1 or full > LONGEST_SHIFT_HOURS:
        errors.append("A shift is between 1 and %g hours." % LONGEST_SHIFT_HOURS)
    if overtime < 0:
        errors.append("The overtime in a shift cannot be less than nothing.")
    elif overtime and not full:
        errors.append("Give the hours in the shift as well as the overtime in it.")
    elif full > 0 and overtime >= full:
        errors.append("The overtime in a shift (%g) must be less than the shift itself (%g)." % (overtime, full))
    return errors


def longest_shift(shifts):
    """The longest day any shift is, which an overtime sheet's hours are
    held to. shifts: what shift_hours returned for each Shift Type."""
    return max([row["full"] for row in shifts or ()] + [FULL_SHIFT_HOURS])


def overtime_hours(worked, standard=STANDARD_HOURS):
    """The overtime in a day's work: the hours past the shift's standard
    ones. On the twelve-hour shift with two of overtime, ten is the line."""
    if worked in (None, ""):
        return 0.0
    extra = float(worked) - float(standard or STANDARD_HOURS)
    return round(extra, 2) if extra > 0 else 0.0


def late_minutes(arrived, starts, grace=0):
    """How late an arrival is, past any grace. 0 when on time or early."""
    if not (arrived and starts):
        return 0
    minutes = int((_time_on(arrived) - _time_on(starts)).total_seconds() // 60) - int(grace or 0)
    return minutes if minutes > 0 else 0


def early_minutes(left, ends, grace=0):
    """How early a departure is, past any grace. 0 when on time or later."""
    if not (left and ends):
        return 0
    minutes = int((_time_on(ends) - _time_on(left)).total_seconds() // 60) - int(grace or 0)
    return minutes if minutes > 0 else 0


# ── What the clock says of a day ──────────────────────────────────────
# Frappe HR reads a day from its punches (Shift Type auto-attendance). What
# it does not say is added to the Attendance as it is marked
# (attendance.attendance_validate).
WORKED = ("Present", "Half Day", "Work From Home")
# who the scheduler marks attendance as: an absence it marked is the
# clock's own reading, one a person marked is theirs
SYSTEM_USERS = ("Administrator",)
# a punch written down this long after it was made did not come with its
# own hour's read: its day may have been marked without it
LATE_PUNCH_HOURS = 2
# the mark Frappe HR reads punches up to is kept this far behind a read,
# for the punch a terminal was still sending as the read began
SYNC_MARGIN_MINUTES = 10


def shift_span(day, start_time, end_time):
    """(start, end) of a shift worked on a day, as moments. A shift that
    ends at or before the hour it starts runs into the next day."""
    if not (day and start_time and end_time):
        return None, None
    start = datetime.datetime.combine(_date(day), _time_on(start_time).time())
    end = datetime.datetime.combine(_date(day), _time_on(end_time).time())
    if end <= start:
        end += datetime.timedelta(days=1)
    return start, end


def overnight(start_time, end_time):
    """Whether a shift runs past midnight, so its clock-out is dated the
    day after the attendance."""
    start, end = shift_span(datetime.date(2000, 1, 1), start_time, end_time)
    return bool(start and end and end.date() > start.date())


def minutes_late(arrived, starts, grace=0):
    """The minutes an arrival is late, counted from the start of the shift
    once it is past the grace. Inside the grace, none."""
    return late_minutes(arrived, starts) if late_minutes(arrived, starts, grace) else 0


def minutes_early(left, ends, grace=0):
    """The minutes a departure is early, counted to the end of the shift
    once it is past the grace. Inside the grace, none."""
    return early_minutes(left, ends) if early_minutes(left, ends, grace) else 0


def clock_out_missing(status, in_time, out_time):
    """A day with a clock-in and no clock-out. Its hours cannot be counted,
    so Frappe HR reads it as absent or half a day; it is said to be what
    it is, for somebody to put right before the payroll."""
    return bool(in_time) and not out_time and status in ("Absent", "Half Day")


def on_a_holiday(status, holiday, punched):
    """A day off somebody clocked in on is a day they came in: Present,
    whatever the hours. An absence or half a day on a holiday would take
    pay off a day nobody was due to work."""
    if holiday and punched and status in ("Absent", "Half Day"):
        return "Present"
    return status


def sync_mark(current, read_at, margin_minutes=SYNC_MARGIN_MINUTES):
    """How far Frappe HR may read the punches: up to just before the read
    that has just come in, and never back from where it stood.

    Frappe HR marks a shift's attendance, the absences included, only up
    to this mark, so it follows the reads: while BioTime cannot be read,
    nobody is marked absent for punches that have not arrived.
    """
    reached = _moment(read_at) - datetime.timedelta(minutes=int(margin_minutes or 0))
    if current and _moment(current) >= reached:
        return _moment(current)
    return reached


def came_late(punch_time, read_at, after_hours=LATE_PUNCH_HOURS):
    """A punch read long after it was made: a terminal that was off the
    network sends its punches when it is back."""
    if not (punch_time and read_at):
        return False
    return (_moment(read_at) - _moment(punch_time)).total_seconds() >= float(after_hours) * 3600


def absences_to_redo(punches, absences, read_at, after_hours=LATE_PUNCH_HOURS):
    """The absences the clock marked that late punches now contradict.

    punches: [{"employee", "time"}] just written down.
    absences: [{"name", "employee", "attendance_date", "owner",
    "leave_application", "attendance_request", "overnight"}], the Absent
    days of those employees.

    An absence is redone when a late punch falls on its day, or on the
    morning after where its shift runs past midnight; and only one the
    scheduler marked, with no leave and no attendance request behind it.
    One a person marked is theirs to change.
    """
    days = {}
    for punch in punches or []:
        if not punch.get("employee") or not came_late(punch.get("time"), read_at, after_hours):
            continue
        days.setdefault(punch["employee"], set()).add(_date(punch["time"]))
    names = []
    for row in absences or []:
        seen = days.get(row.get("employee"))
        if not seen or row.get("leave_application") or row.get("attendance_request") \
                or row.get("owner") not in SYSTEM_USERS:
            continue
        day = _date(row.get("attendance_date"))
        if day in seen or (row.get("overnight") and day + datetime.timedelta(days=1) in seen):
            names.append(row.get("name"))
    return names


# ── The three forms ───────────────────────────────────────────────────
def off_duty_errors(facts):
    """Problems with an Off-Duty Request (LPL/HR/25) as it goes for approval.

    facts: "employee", "off_date", "reason", "kind", "date_of_joining".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Name the employee asking for the day off.")
    if not facts.get("off_date"):
        errors.append("Give the date the employee will be absent.")
    elif facts.get("date_of_joining") and str(facts["off_date"]) < str(facts["date_of_joining"]):
        errors.append("The day off is before the employee joined (%s)." % facts["date_of_joining"])
    if not (facts.get("reason") or "").strip():
        errors.append("Give the reason for the day off.")
    if facts.get("kind") not in OFF_DUTY_KINDS:
        errors.append("Say how the day is treated: %s." % ", ".join(OFF_DUTY_KINDS))
    return errors


def overtime_errors(facts):
    """Problems with an Overtime Request (LPL/HR/14) as it is submitted.

    facts: "overtime_date", "employees" ([{"employee", "hours", "employment"}]),
    "requested_by", "section", "full_shift" (the longest shift's hours).
    """
    errors = []
    full_shift = _hours(facts.get("full_shift")) or FULL_SHIFT_HOURS
    if not facts.get("overtime_date"):
        errors.append("Give the date the overtime is worked.")
    if not facts.get("requested_by"):
        errors.append("Name the requesting officer.")
    rows = facts.get("employees") or []
    if not rows:
        errors.append("List the employees who will work the overtime.")
    seen = set()
    for row in rows:
        if not row.get("employee"):
            errors.append("Every line must name an employee.")
            break
        if row["employee"] in seen:
            errors.append("%s is listed twice." % row["employee"])
            break
        seen.add(row["employee"])
    for row in rows:
        hours = row.get("hours")
        if hours in (None, "") or float(hours or 0) <= 0:
            errors.append("Give the duration in hours for every employee (%s)."
                          % (row.get("employee") or "?"))
            break
        if float(hours) > full_shift:
            errors.append("%s hours is longer than a full shift (%g): check the duration."
                          % (hours, full_shift))
            break
    return errors


def gate_pass_errors(facts):
    """Problems with a Gate Pass as it is issued.

    facts: "employee", "pass_date", "out_time", "expected_return", "reason".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Name the employee leaving the premises.")
    if not facts.get("pass_date"):
        errors.append("Give the date of the pass.")
    if not facts.get("out_time"):
        errors.append("Give the time the employee leaves.")
    if not (facts.get("reason") or "").strip():
        errors.append("Give the reason for leaving before the hours are done.")
    out, back = facts.get("out_time"), facts.get("expected_return")
    if out and back and str(back) <= str(out):
        errors.append("The expected return (%s) must be after the time of leaving (%s)." % (back, out))
    return errors


def late_notice_errors(facts):
    """Problems with a Late Arrival Notice as it is sent.

    facts: "employee", "arrival_date", "expected_time", "reason",
    "shift_start".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Name the employee who will be late.")
    if not facts.get("arrival_date"):
        errors.append("Give the day they will be late.")
    if not facts.get("expected_time"):
        errors.append("Give the time they expect to arrive.")
    elif facts.get("shift_start") and _time_on(facts["expected_time"]) <= _time_on(facts["shift_start"]):
        errors.append("Arriving at %s is not late: the shift starts at %s."
                      % (str(facts["expected_time"])[:5], str(facts["shift_start"])[:5]))
    if not (facts.get("reason") or "").strip():
        errors.append("Give the reason they will be late.")
    return errors


def notified_in_advance(notified_on, arrival_date, shift_start):
    """A notice is given in advance when it is sent before the shift starts
    on the day. With no shift known, before the day begins."""
    if not (notified_on and arrival_date):
        return False
    starts = _time_on(shift_start).time() if shift_start else datetime.time(0, 0)
    return _time_on(notified_on) < datetime.datetime.combine(_date(arrival_date), starts)


def full_day(status, late_entry, notice, on_leave=False):
    """What a day an acknowledged notice covers is recorded as, as
    (status, late_entry): a half day is a full day and the arrival is not
    counted late. An absence stays an absence (the notice said late, not
    away), and a half day of leave is the leave's, not the notice's.

    notice: whether an acknowledged notice given in advance covers the day.
    """
    if not notice or on_leave:
        return status, late_entry
    if status in ("Present", "Half Day", "Work From Home"):
        return ("Present" if status == "Half Day" else status), 0
    return status, late_entry


def coupons(rows):
    """The food coupons LPL/HR/14 has HR issue: how many of each employment
    kind worked the overtime."""
    counted = {kind: 0 for kind in COUPON_KINDS}
    for row in rows or []:
        kind = (row.get("employment") or "").strip().title()
        if kind in counted:
            counted[kind] += 1
    return counted


def _hours(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _moment(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    return datetime.datetime.fromisoformat(str(value).replace("T", " ")[:19])


def _time_on(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.time):
        return datetime.datetime.combine(datetime.date(2000, 1, 1), value)
    text = str(value)
    if len(text) <= 8 and ":" in text:
        parts = [int(part) for part in text.split(":")[:3]]
        while len(parts) < 3:
            parts.append(0)
        return datetime.datetime.combine(datetime.date(2000, 1, 1), datetime.time(*parts))
    return datetime.datetime.fromisoformat(text)


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
