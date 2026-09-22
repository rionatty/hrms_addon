# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The attendance board: the floor now, the cycle so far, what needs a person.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_attendance_board.py exercises them without a bench.

WHY A BOARD AND NOT MORE CHARTS

Luuka's attendance question is not "how many were present last quarter".
It is "who is on the floor this minute, is the night shift covered,
whose hours have turned into overtime, and what do I have to put right
before the register closes on the 25th". A monthly bar chart answers
none of that.

So the middle of the board is the register itself — LPL/HR/07, the sheet
they already read, ruled 26th to 25th and filled from the punches
instead of by hand — with the state of the floor above it and the things
that need somebody below it.

WHAT IS DECIDED HERE

Only the reading. Whether a machine has gone quiet, whether somebody is
still inside, whether their hours have crossed into overtime, how full a
day was. The queries are in attendance_board.py, and what a day's cell
says is attendance_rules.register_code — this module does not repeat it.
"""

import datetime

# ── The shift, as Luuka works it ──────────────────────────────────────
# "normally 12 hours, inclusive of 2 hours of overtime", so the tenth
# hour is where a day's work turns into overtime
FULL_SHIFT_HOURS = 12.0
OVERTIME_AFTER_HOURS = 10.0

ON_SHIFT, INTO_OVERTIME, OVER_A_SHIFT = "On shift", "Into overtime", "Over a full shift"

# ── The machines ──────────────────────────────────────────────────────
# A machine that stops sending is invisible until payroll — which is
# Luuka's "attendance jumps out". These are the hours after which
# somebody should go and look.
QUIET_AFTER_HOURS = 2
SILENT_AFTER_HOURS = 12

HEALTHY, QUIET, SILENT, NEVER = "Healthy", "Quiet", "Silent", "Never heard from"
HEALTH_MEANING = {
    HEALTHY: "sending punches",
    QUIET: "nothing for a couple of hours — may be between shifts",
    SILENT: "nothing all day; somebody should look at it",
    NEVER: "no punch has ever come from this machine",
}

# ── What needs a person ───────────────────────────────────────────────
# Each is a thing somebody has to do something about, not a number to
# look at. The counting is in the glue; the meaning is here.
HIGH, MEDIUM = "high", "medium"
EXCEPTIONS = (
    {"kind": "on_leave_but_punched", "severity": HIGH,
     "label": "Clocked in while on approved leave",
     "why": "either the leave was cut short and nobody said, or somebody else used the badge"},
    {"kind": "absent_with_punch", "severity": HIGH,
     "label": "Marked absent, but a machine saw them",
     "why": "the register will pay them nothing for a day they were here"},
    {"kind": "failed_push", "severity": HIGH,
     "label": "Punches written down that never landed",
     "why": "they are held and can be pushed again without going back to the machine"},
    {"kind": "silent_terminal", "severity": HIGH,
     "label": "Machines that have gone quiet",
     "why": "a machine nobody notices has stopped is found at payroll, too late to fix"},
    {"kind": "in_without_out", "severity": MEDIUM,
     "label": "Clocked in, never clocked out",
     "why": "the hours cannot be worked out, so the day pays as if it was never finished"},
    {"kind": "unknown_badge", "severity": MEDIUM,
     "label": "Badges nobody carries",
     "why": "somebody is clocking who is not on the payroll, or a badge was never recorded"},
    {"kind": "undirected_terminal", "severity": MEDIUM,
     "label": "Terminals with no plant set",
     "why": "BioTime names a terminal but not the door it guards; the punches are kept "
            "meanwhile, but nothing knows which plant they belong to"},
)
EXCEPTION_KINDS = tuple(row["kind"] for row in EXCEPTIONS)

# ── How full a day was ────────────────────────────────────────────────
FULL, THIN, SHORT = "full", "thin", "short"
BANDS = ((0.95, FULL), (0.85, THIN), (0.0, SHORT))


def machine_health(last_seen, now, quiet_hours=QUIET_AFTER_HOURS,
                   silent_hours=SILENT_AFTER_HOURS):
    """How a clocking machine is doing, by how long since its last punch."""
    if not last_seen:
        return NEVER
    quiet_for = (_moment(now) - _moment(last_seen)).total_seconds() / 3600.0
    if quiet_for >= silent_hours:
        return SILENT
    if quiet_for >= quiet_hours:
        return QUIET
    return HEALTHY


def inside_now(readings):
    """Who is on the floor, and since when.

    The last reading for each person decides it: IN and they are inside,
    OUT and they have gone home. Nothing here looks at the date, only at
    the order — somebody whose last reading is an IN from last night is
    on a night shift, not a mistake.
    """
    last = {}
    for row in sorted(readings or [],
                      key=lambda row: (str(row.get("employee") or ""),
                                       str(row.get("time") or ""))):
        if row.get("employee"):
            last[row["employee"]] = row
    return {who: row for who, row in last.items()
            if str(row.get("log_type") or "").upper() == "IN"}


def hours_so_far(since, now):
    """How long somebody has been inside, in hours."""
    if not since:
        return 0.0
    hours = (_moment(now) - _moment(since)).total_seconds() / 3600.0
    return round(max(hours, 0.0), 2)


def standing_of(hours, overtime_after=OVERTIME_AFTER_HOURS, full_shift=FULL_SHIFT_HOURS):
    """What those hours mean on Luuka's twelve-hour shift."""
    hours = float(hours or 0)
    if hours >= full_shift:
        return OVER_A_SHIFT
    if hours >= overtime_after:
        return INTO_OVERTIME
    return ON_SHIFT


def floor_tally(people):
    """The band across the top: how many are inside, and in what state.

    people: [{"employee", "night", "hours"}]
    """
    tally = {"inside": 0, "day": 0, "night": 0,
             "into_overtime": 0, "over_a_shift": 0}
    for row in people or []:
        tally["inside"] += 1
        tally["night" if row.get("night") else "day"] += 1
        standing = standing_of(row.get("hours"))
        if standing == OVER_A_SHIFT:
            tally["over_a_shift"] += 1
            tally["into_overtime"] += 1
        elif standing == INTO_OVERTIME:
            tally["into_overtime"] += 1
    return tally


def by_branch(people):
    """The same, split by plant, busiest first."""
    branches = {}
    for row in people or []:
        name = row.get("branch") or "Unplaced"
        seat = branches.setdefault(name, {"branch": name, "inside": 0, "day": 0, "night": 0})
        seat["inside"] += 1
        seat["night" if row.get("night") else "day"] += 1
    return sorted(branches.values(), key=lambda seat: (-seat["inside"], seat["branch"]))


def plants(lines, inside=None, machines=None, day_codes=("M", "N"), night_code="N",
           absent_code="A"):
    """One line per plant, side by side.

    Luuka's plants are run by their own people — each has its own HODs,
    its own supervisors and its own HR Officer — so "how is attendance"
    is a question with one answer per plant, not one for the company. The
    worst turnout is put first, because a board that sorts alphabetically
    hides the plant that needs somebody.
    """
    seats = {}

    def seat_for(name):
        return seats.setdefault(name or "Unplaced", {
            "branch": name or "Unplaced", "people": 0, "worked": 0, "night": 0,
            "absent": 0, "inside": 0, "inside_night": 0,
            "machines": 0, "machines_watch": 0, "rate": None})

    for line in lines or []:
        seat = seat_for(line.get("branch"))
        seat["people"] += 1
        for code in line.get("codes") or []:
            if code in day_codes:
                seat["worked"] += 1
            if code == night_code:
                seat["night"] += 1
            elif code == absent_code:
                seat["absent"] += 1
    for row in inside or []:
        seat = seat_for(row.get("branch"))
        seat["inside"] += 1
        if row.get("night"):
            seat["inside_night"] += 1
    for row in machines or []:
        # a terminal nobody has placed belongs to no plant, and inventing
        # one for it would put a row on the board with no people in it.
        # It is already its own line under what needs a person.
        if not row.get("branch"):
            continue
        seat = seat_for(row["branch"])
        seat["machines"] += 1
        if row.get("health") in (SILENT, NEVER):
            seat["machines_watch"] += 1
    for seat in seats.values():
        seat["rate"] = rate(seat["worked"], seat["worked"] + seat["absent"])
        seat["band"] = band(seat["rate"])
    # the plant in trouble first: nothing to judge it on goes last
    return sorted(seats.values(),
                  key=lambda seat: (seat["rate"] is None,
                                    seat["rate"] if seat["rate"] is not None else 0,
                                    seat["branch"]))


def rate(present, expected):
    """How full a day was, 0 to 1. A day nobody was expected is not empty,
    it is not a working day, and answers None."""
    expected = int(expected or 0)
    if expected <= 0:
        return None
    return round(min(float(present or 0) / expected, 1.0), 4)


def band(full):
    """Which band a day's rate falls in, for the strip along the top."""
    if full is None:
        return None
    for floor, name in BANDS:
        if full >= floor:
            return name
    return SHORT


def progress(days, today):
    """How far through the cycle today is: (day number, how many, fraction).

    A cycle that has not started answers 0, and one already closed
    answers its full length — the board is read on days either side of
    the 25th as well as inside it.
    """
    days = list(days or [])
    if not days:
        return {"day": 0, "of": 0, "through": 0.0}
    today = _day(today)
    done = len([day for day in days if _day(day) <= today])
    return {"day": done, "of": len(days),
            "through": round(float(done) / len(days), 4)}


def worked_and_overtime(codes, day_codes=("M", "N"), full_shift=FULL_SHIFT_HOURS,
                        overtime_after=OVERTIME_AFTER_HOURS):
    """A person's line at the right of the register: days worked, and the
    overtime those days carry.

    Every full shift carries its two hours, which is how Luuka's shift is
    built. Hours actually worked past the twelfth are the pull's business,
    not the register's.
    """
    worked = len([code for code in codes or [] if code in day_codes])
    return {"worked": worked,
            "overtime": round(worked * (full_shift - overtime_after), 2)}


def nights_covered(tallies, days, wanted=None):
    """Which days of the cycle had nobody on nights.

    tallies: what attendance_rules.tallies() returned.
    """
    nights = (tallies or {}).get("Total number of staff in Night shift") or {}
    short = []
    for day in days or []:
        on = int(nights.get(day) or 0)
        if on < int(wanted or 1):
            short.append(day)
    return short


def _moment(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    return datetime.datetime.fromisoformat(str(value)[:19].replace("T", " "))


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
