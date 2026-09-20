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
FULL_SHIFT_HOURS = 12.0  # "normally 12 hours, inclusive of 2 hours of overtime"
OVERTIME_IN_SHIFT = 2.0
STANDARD_HOURS = FULL_SHIFT_HOURS - OVERTIME_IN_SHIFT
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
        return SICK if _is_sick(facts.get("leave_type")) else LEAVE
    if status == "Absent":
        return ABSENT
    if status in ("Present", "Half Day", "Work From Home"):
        return NIGHT_SHIFT if _is_night(facts.get("shift")) else DAY_SHIFT
    if facts.get("holiday"):
        return WEEKLY_OFF
    return ""


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


def overtime_hours(worked, standard=STANDARD_HOURS):
    """The overtime in a day's work. A full shift is twelve hours with two
    of them overtime, so ten standard hours is the line."""
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
    "requested_by", "section".
    """
    errors = []
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
        if float(hours) > FULL_SHIFT_HOURS:
            errors.append("%s hours is longer than a full shift (%g): check the duration."
                          % (hours, FULL_SHIFT_HOURS))
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


def coupons(rows):
    """The food coupons LPL/HR/14 has HR issue: how many of each employment
    kind worked the overtime."""
    counted = {kind: 0 for kind in COUPON_KINDS}
    for row in rows or []:
        kind = (row.get("employment") or "").strip().title()
        if kind in counted:
            counted[kind] += 1
    return counted


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
