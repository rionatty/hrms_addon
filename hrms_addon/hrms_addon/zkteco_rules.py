# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Reading a ZKTeco clocking machine: what its punches mean, and how to
turn them into check-ins that can be trusted.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_attendance.py exercises them without a bench. The device
itself is talked to in devices.py, which imports the driver lazily so a
site without it still installs.

WHAT THE MACHINE GIVES

Each record carries a user id (the badge number, which is
Employee.attendance_device_id upstream), a timestamp, a status and a punch
code. The punch code is what the employee pressed:

    0 Check In    1 Check Out    2 Break Out    3 Break In
    4 Overtime In 5 Overtime Out

Older firmware, and any machine where nobody presses anything, reports 255
or 0 for everything. So the punch code is used where it means something
and the direction is worked out otherwise.

THE TWO FAULTS LUUKA REPORTED

  "the machines are in close proximity to each other; sometimes clock-in
   and clock-out become one record due to face detection, since the
   machines are in the same place"

A face seen twice within a few seconds is one arrival, not an arrival and
a departure, so punches from the same person inside DOUBLE_READ_SECONDS
collapse into one. Two machines standing together also means the same face
can be read by both, so the collapse is across devices by default.

  "sometimes the attendance recorded by the biometric machines jumps out
   (fails to reach the system), and the supplier is contacted to push the
   data"

Nothing is thrown away here: every punch read is written down before it is
turned into a check-in, so a punch that failed to land can be found and
pushed again without going back to the machine.
"""

import datetime

IN, OUT = "IN", "OUT"

# what the employee pressed, as ZKTeco numbers it
CHECK_IN, CHECK_OUT, BREAK_OUT, BREAK_IN, OVERTIME_IN, OVERTIME_OUT = 0, 1, 2, 3, 4, 5
PUNCH_MEANING = {
    CHECK_IN: "Check In",
    CHECK_OUT: "Check Out",
    BREAK_OUT: "Break Out",
    BREAK_IN: "Break In",
    OVERTIME_IN: "Overtime In",
    OVERTIME_OUT: "Overtime Out",
}
PUNCH_DIRECTION = {
    CHECK_IN: IN,
    CHECK_OUT: OUT,
    BREAK_OUT: OUT,
    BREAK_IN: IN,
    OVERTIME_IN: IN,
    OVERTIME_OUT: OUT,
}
# 255 is what a machine reports when nobody chose a direction
UNDECIDED = 255

# a device may be mounted at a door that only ever admits or only ever
# releases, in which case it says so and the punch code is not consulted
DIRECTION_IN, DIRECTION_OUT, DIRECTION_BOTH = "In only", "Out only", "In and Out"
DEVICE_DIRECTIONS = (DIRECTION_BOTH, DIRECTION_IN, DIRECTION_OUT)

# a face read twice this close together is one reading
DOUBLE_READ_SECONDS = 90
# how far back a pull reaches when a device has never synced
FIRST_PULL_DAYS = 7


def direction_of(punch, device_direction=DIRECTION_BOTH):
    """IN, OUT, or None when the machine did not say.

    A device mounted one way round overrides the punch code: whatever the
    employee pressed, that door only goes one way.
    """
    if device_direction == DIRECTION_IN:
        return IN
    if device_direction == DIRECTION_OUT:
        return OUT
    try:
        code = int(punch)
    except (TypeError, ValueError):
        return None
    return PUNCH_DIRECTION.get(code)


def dedupe(punches, within=DOUBLE_READ_SECONDS, per_device=False):
    """The same face read twice within `within` seconds is one reading.

    punches: [{"device_user_id", "time", "punch", "device"}], any order.
    Returns them in time order, the later of each pair dropped. Keeping
    `per_device` False collapses across machines too, because Luuka's stand
    side by side and one face reaches both.
    """
    ordered = sorted(punches or [], key=lambda row: (str(row.get("device_user_id")), _moment(row.get("time"))))
    kept, last = [], {}
    for row in ordered:
        key = (str(row.get("device_user_id")), row.get("device") if per_device else None)
        moment = _moment(row.get("time"))
        seen = last.get(key)
        if seen is not None and (moment - seen).total_seconds() < within:
            continue
        last[key] = moment
        kept.append(row)
    return sorted(kept, key=lambda row: (_moment(row.get("time")), str(row.get("device_user_id"))))


def resolve(punches, directions=None, opening=None):
    """Every punch given a direction.

    Where the machine said which way it was, that stands. Where it did not,
    the punches alternate through the day, starting with IN unless
    `opening` says this employee was already inside.

    punches: [{"device_user_id", "time", "punch", "device"}], in time order.
    directions: {device: one of DEVICE_DIRECTIONS}.
    opening: {device_user_id: IN|OUT} — the last direction already known.
    Returns the same rows with "log_type" set.
    """
    directions = directions or {}
    standing = dict(opening or {})
    out = []
    for row in punches or []:
        badge = str(row.get("device_user_id"))
        told = direction_of(row.get("punch"), directions.get(row.get("device"), DIRECTION_BOTH))
        if told is None:
            told = OUT if standing.get(badge) == IN else IN
        standing[badge] = told
        out.append(dict(row, log_type=told))
    return out


def pairs(punches):
    """The day's punches read as (in, out) pairs, for the hours worked.
    An unpaired IN at the end is returned with None beside it."""
    made, waiting = [], None
    for row in punches or []:
        if row.get("log_type") == IN:
            if waiting is not None:
                made.append((waiting, None))
            waiting = row
        elif waiting is not None:
            made.append((waiting, row))
            waiting = None
    if waiting is not None:
        made.append((waiting, None))
    return made


def worked_hours(punches):
    """The hours between each pair, added up. None when nothing pairs."""
    total = 0.0
    counted = False
    for entry, leaving in pairs(punches):
        if not (entry and leaving):
            continue
        total += (_moment(leaving.get("time")) - _moment(entry.get("time"))).total_seconds() / 3600.0
        counted = True
    return round(total, 2) if counted else None


def since(last_sync, today, days=FIRST_PULL_DAYS):
    """The moment a pull reads from: just after the last sync, or a few days
    back when the device has never synced."""
    if last_sync:
        return _moment(last_sync)
    return _moment(today) - datetime.timedelta(days=days)


def to_push(punches, since_moment=None, known_badges=None):
    """The punches worth pushing, and the ones that cannot be.

    Returns (push, unknown): rows newer than `since_moment` whose badge is
    known, and rows whose badge belongs to nobody. A badge nobody owns is
    kept and reported rather than dropped, because it is usually an employee
    whose device id was never filled in.
    """
    push, unknown = [], []
    for row in punches or []:
        if since_moment and _moment(row.get("time")) <= _moment(since_moment):
            continue
        badge = str(row.get("device_user_id") or "").strip()
        if known_badges is not None and badge not in known_badges:
            unknown.append(row)
            continue
        push.append(row)
    return push, unknown


def device_errors(facts):
    """Problems with an Attendance Device as it is saved.

    facts: "device_name", "host", "port", "direction", "enabled".
    """
    errors = []
    if not (facts.get("device_name") or "").strip():
        errors.append("Give the machine a name.")
    if not (facts.get("host") or "").strip():
        errors.append("Give the machine's IP address or host name.")
    port = facts.get("port")
    if port in (None, ""):
        errors.append("Give the machine's port (ZKTeco machines listen on 4370 by default).")
    else:
        try:
            number = int(port)
        except (TypeError, ValueError):
            number = -1
        if not 1 <= number <= 65535:
            errors.append("The port must be between 1 and 65535.")
    if facts.get("direction") not in DEVICE_DIRECTIONS:
        errors.append("Say which way the machine faces: %s." % ", ".join(DEVICE_DIRECTIONS))
    return errors


def _moment(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    return datetime.datetime.fromisoformat(str(value).replace("T", " ").split(".")[0])
