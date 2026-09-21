# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Shifts: the rotation, and what a shift is worth.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_shifts.py exercises them without a bench.

WHAT THIS DOES NOT BUILD

Frappe HR ships the shifts themselves: a Shift Type with its hours and its
auto-attendance, a Shift Assignment putting an employee on one for a span,
and a Shift Assignment Tool that assigns a whole plant or department at
once. None of that is rebuilt.

Two things it does not ship, and Luuka need:

  the rotation   a three-shift plant does not put a person on one shift and
                 leave them there. The shifts come round: day, night, off,
                 and back to day, a week at a time. Somebody asked to stay
                 on one shift for a while sits out the rotation until the
                 day they were promised, and then rejoins where the cycle
                 has got to, not where they left it.
  the allowance  a shift carries money — a night shift more than a day one
                 — and what is owed is counted from the shifts actually
                 worked, not from the roster somebody planned.

THE CYCLE

A rotation is an ordered list of shift types and a period. Whoever is on
position 0 this week is on position 1 next week. With three shifts and a
weekly period, an employee is back where they started after three weeks,
which is what "automatic weekly shift rotation" means on the shop floor.
"""

import datetime

WEEKLY, FORTNIGHTLY, MONTHLY = "Weekly", "Fortnightly", "Monthly"
PERIODS = (WEEKLY, FORTNIGHTLY, MONTHLY)
PERIOD_DAYS = {WEEKLY: 7, FORTNIGHTLY: 14, MONTHLY: 30}

# Luuka's own three, seeded under these names (Manufacturing Excellence,
# 4.3: the register's M and N, plus the office day)
GENERAL, DAY, NIGHT = "General", "Day Shift", "Night Shift"
THREE_SHIFT = (DAY, NIGHT)
SHIFT_HOURS = {GENERAL: (8.0, "08:00:00", "17:00:00"),
               DAY: (12.0, "07:00:00", "19:00:00"),
               NIGHT: (12.0, "19:00:00", "07:00:00")}


def cycle_length(shifts):
    return len(shifts or ())


def periods_between(start, day, period=WEEKLY):
    """How many whole periods have passed since the rotation started."""
    days = (_date(day) - _date(start)).days
    if days < 0:
        return 0
    return days // PERIOD_DAYS.get(period, 7)


def position_on(start, day, shifts, period=WEEKLY, offset=0):
    """Where in the cycle a group sits on a given day."""
    if not shifts:
        return None
    return (periods_between(start, day, period) + int(offset or 0)) % len(shifts)


def shift_on(start, day, shifts, period=WEEKLY, offset=0):
    """Which shift that is. An employee's own offset is what staggers one
    crew against another: crew A starts at day, crew B a position along."""
    position = position_on(start, day, shifts, period, offset)
    return shifts[position] if position is not None else None


def period_window(start, day, period=WEEKLY):
    """The span of the period a day falls in, which is what a Shift
    Assignment is written for."""
    length = PERIOD_DAYS.get(period, 7)
    passed = periods_between(start, day, period)
    opens = _date(start) + datetime.timedelta(days=passed * length)
    return {"from": opens, "to": opens + datetime.timedelta(days=length - 1)}


def schedule(start, day, members, shifts, period=WEEKLY):
    """The roster for the period a day falls in: one row per member, with
    the shift the cycle has brought round to them.

    A member held on a shift until a date is left on it, and that is said
    rather than silently done, because somebody asked for it and somebody
    else has to cover the shift they are not on.
    """
    window = period_window(start, day, period)
    rows = []
    for member in members or []:
        held = member.get("hold_until")
        if held and _date(held) >= window["from"]:
            rows.append({"employee": member.get("employee"),
                         "shift_type": member.get("held_shift") or member.get("shift_type"),
                         "from": window["from"], "to": window["to"], "rotated": False,
                         "held_until": _date(held)})
            continue
        rows.append({"employee": member.get("employee"),
                     "shift_type": shift_on(start, day, shifts, period,
                                            member.get("offset")),
                     "from": window["from"], "to": window["to"], "rotated": True,
                     "held_until": None})
    return rows


def rotation_errors(facts):
    errors = []
    if not facts.get("rotation_name"):
        errors.append("Give the rotation a name.")
    if not facts.get("start_date"):
        errors.append("Say when the rotation starts. Everything after it is counted from there.")
    if facts.get("period") and facts["period"] not in PERIODS:
        errors.append("A rotation comes round weekly, fortnightly or monthly.")
    shifts = [row.get("shift_type") for row in facts.get("shifts") or []]
    if len(shifts) < 2:
        errors.append("A rotation needs at least two shifts to come round between.")
    if len(set(shifts)) != len(shifts):
        errors.append("The same shift is in the cycle twice.")
    if any(not name for name in shifts):
        errors.append("A position in the cycle with no shift on it is not a position.")
    seen = set()
    for row in facts.get("members") or []:
        if not row.get("employee"):
            errors.append("A member without a name is not a member.")
            continue
        if row["employee"] in seen:
            errors.append("%s is on the rotation twice."
                          % (row.get("employee_name") or row["employee"]))
        seen.add(row["employee"])
        if row.get("offset") not in (None, "") and shifts \
                and not 0 <= int(row["offset"]) < len(shifts):
            errors.append("%s starts at position %s, and the cycle has %d."
                          % (row.get("employee_name") or row["employee"], row["offset"],
                             len(shifts)))
        if row.get("hold_until") and not (row.get("held_shift") or row.get("shift_type")):
            errors.append("%s is held off the rotation but no shift is named to hold them on."
                          % (row.get("employee_name") or row["employee"]))
    return errors


def due_to_rejoin(members, day):
    """Who was held off the rotation and whose date has come. They rejoin
    where the cycle has got to, not where they left it."""
    out = []
    for row in members or []:
        held = row.get("hold_until")
        if held and _date(held) < _date(day):
            out.append(row.get("employee"))
    return out


# ── What a shift is worth ─────────────────────────────────────────────
def allowance_due(worked, rates):
    """What the shifts actually worked come to.

    worked: {shift type: number of shifts}. rates: {shift type: the
    allowance one of them carries}. A shift with no rate is worth nothing
    and is not an error: an office day carries no allowance.
    """
    lines, total = [], 0.0
    for shift_type in sorted(worked or {}):
        count = int(worked[shift_type] or 0)
        rate = float((rates or {}).get(shift_type) or 0)
        if not (count and rate):
            continue
        amount = round(count * rate, 2)
        lines.append({"shift_type": shift_type, "shifts": count, "rate": rate,
                      "amount": amount})
        total += amount
    return {"lines": lines, "total": round(total, 2)}


def allowance_errors(facts):
    errors = []
    if not facts.get("employee"):
        errors.append("Say whose allowance this is.")
    if not (facts.get("from_date") and facts.get("to_date")):
        errors.append("Say which cycle the allowance covers.")
    if not (facts.get("lines") or []):
        errors.append("No shift with an allowance on it was worked in that cycle.")
    if not facts.get("salary_component"):
        errors.append("Say which salary component the allowance is paid through.")
    return errors


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
