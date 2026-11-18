# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance and scheduling: the rules, without a Frappe import
(scripts/verify_learning_attendance.py). learning_attendance.py reads and
writes the site.

The blueprint's section 4.4 and the brief's sections 8 and 9 (18 Nov 2026):

  Training Attendance  a row per employee per session per day: Invited,
                       Registered, Attended, Late, Absent, Excused or
                       No-show; the time in and out and the hours; how it was
                       taken (by hand, a QR code, the employee number, the
                       employee's own phone); who marked it and the
                       supervisor's confirmation
  the session          its seats, who registered, the waiting list that
                       moves up when a seat comes free; Frappe HR's own
                       Present or Absent kept in step (Present when they came
                       on any day), which is what the training rules read
  clashes              a trainer or a venue booked twice at once is refused
                       (Learning Settings), an employee booked twice is said
"""

import datetime

INVITED, REGISTERED, ATTENDED, LATE, ABSENT, EXCUSED, NO_SHOW = (
    "Invited", "Registered", "Attended", "Late", "Absent", "Excused", "No-show")
STATUSES = (INVITED, REGISTERED, ATTENDED, LATE, ABSENT, EXCUSED, NO_SHOW)
CAME = (ATTENDED, LATE)
MISSED = (ABSENT, EXCUSED, NO_SHOW)
OPEN = (INVITED, REGISTERED)
MANUAL, QR, NUMBER, MOBILE = "Manual", "QR", "Employee Number", "Mobile"
METHODS = (MANUAL, QR, NUMBER, MOBILE)
WAITING, MOVED_IN, WITHDRAWN = "Waiting", "Moved In", "Withdrawn"
WAITLIST_STATUSES = (WAITING, MOVED_IN, WITHDRAWN)
PRESENT, ABSENT_HR = "Present", "Absent"
# a session runs at most this many days, for its attendance rows
MOST_DAYS = 31
# an employee may sign themselves in from this long before the session starts
EARLY_MINUTES = 30
QR_PREFIX = "EMP:"


# ── The days and the hours ────────────────────────────────────────────
def session_days(start, end):
    """The days a session runs, a row's day each: from its first to its last,
    at most MOST_DAYS."""
    first, last = _date(start), _date(end) or _date(start)
    if not first:
        return []
    last = max(first, last)
    count = min((last - first).days + 1, MOST_DAYS)
    return [first + datetime.timedelta(days=offset) for offset in range(count)]


def day_window(start, end, day):
    """(from, to) datetimes the session runs on one of its days: its start and
    end times on that day."""
    start, end, day = _datetime(start), _datetime(end), _date(day)
    if not start or not day:
        return None, None
    begins = datetime.datetime.combine(day, start.time())
    ends = datetime.datetime.combine(day, (end or start).time())
    if ends <= begins:
        ends = begins + datetime.timedelta(hours=1)
    return begins, ends


def is_late(begins, signed_in, minutes):
    """Signed in more than `minutes` after the session began that day."""
    begins, signed_in = _datetime(begins), _datetime(signed_in)
    return bool(begins and signed_in and signed_in > begins + datetime.timedelta(minutes=int(_num(minutes))))


def hours_between(time_in, time_out):
    """The hours from signing in to signing out, nought where either is missing."""
    first, last = _seconds(time_in), _seconds(time_out)
    if first is None or last is None or last <= first:
        return 0.0
    return round((last - first) / 3600.0, 2)


def day_hours(begins, ends):
    begins, ends = _datetime(begins), _datetime(ends)
    if not begins or not ends or ends <= begins:
        return 0.0
    return round((ends - begins).total_seconds() / 3600.0, 2)


# ── What Frappe HR is told ────────────────────────────────────────────
def event_attendance(statuses):
    """Frappe HR's Present or Absent for a participant from their days:
    Present when they came on any day; Absent once every day is marked and
    they came on none; None while a day is still open."""
    statuses = [status for status in statuses or () if status]
    if any(status in CAME for status in statuses):
        return PRESENT
    if statuses and all(status in MISSED for status in statuses):
        return ABSENT_HR
    return None


def from_event(attendance):
    """A day's status from Frappe HR's grid, where HR marked it there."""
    return {PRESENT: ATTENDED, ABSENT_HR: ABSENT}.get(attendance)


def marked_status(old, new):
    """Whether a change marks the day (stamps who marked it, and when)."""
    return new not in OPEN and new != old


# ── Seats and the waiting list ────────────────────────────────────────
def seats_left(capacity, taken):
    """None where the session has no limit."""
    capacity = int(_num(capacity))
    if capacity <= 0:
        return None
    return max(0, capacity - int(_num(taken)))


def admit(capacity, taken):
    """Registered while a seat is free, else on the waiting list."""
    left = seats_left(capacity, taken)
    return REGISTERED if left is None or left > 0 else WAITING


def next_in(waitlist, seats):
    """The waiting to move into `seats` free seats: the earliest asked first."""
    waiting = [row for row in waitlist or () if row.get("status") == WAITING and row.get("employee")]
    waiting.sort(key=lambda row: (str(row.get("requested_on") or ""), int(_num(row.get("idx")))))
    return waiting[:max(0, int(_num(seats)))] if seats is not None else waiting


def registration_errors(event, today):
    """Why nobody can register for a session now."""
    if int(_num(event.get("docstatus"))) != 0 or event.get("event_status") == "Cancelled":
        return ["This session is closed."]
    start = _datetime(event.get("start_time"))
    if start and start.date() < _date(today):
        return ["This session has started."]
    return []


# ── Clashes ───────────────────────────────────────────────────────────
def overlap(a_start, a_end, b_start, b_end):
    a_start, a_end, b_start, b_end = (_datetime(value) for value in (a_start, a_end, b_start, b_end))
    if not (a_start and a_end and b_start and b_end):
        return False
    return a_start < b_end and b_start < a_end


def trainer_keys(rows):
    """What identifies each trainer of a session: the employee, else the email,
    else the name, in small letters."""
    keys = set()
    for row in rows or ():
        key = row.get("employee") or (row.get("trainer_email") or "").strip().lower() \
            or (row.get("trainer_name") or "").strip().lower()
        if key:
            keys.add(key)
    return keys


def clashes(session, others):
    """{"venue": [sessions], "trainer": [sessions], "employees": {employee: [sessions]}}
    of the other sessions overlapping this one in time.

    session and others: {"name", "start", "end", "venue", "trainers" (keys), "employees" (set)}."""
    found = {"venue": [], "trainer": [], "employees": {}}
    for other in others or ():
        if other.get("name") == session.get("name"):
            continue
        if not overlap(session.get("start"), session.get("end"), other.get("start"), other.get("end")):
            continue
        venue = (session.get("venue") or "").strip().lower()
        if venue and venue == (other.get("venue") or "").strip().lower():
            found["venue"].append(other["name"])
        if set(session.get("trainers") or ()) & set(other.get("trainers") or ()):
            found["trainer"].append(other["name"])
        for employee in sorted(set(session.get("employees") or ()) & set(other.get("employees") or ())):
            found["employees"].setdefault(employee, []).append(other["name"])
    return found


def line_clashes(lines):
    """The schedule lines that share a venue or a trainer at the same time:
    [(first line's course, second line's course, "venue" or "trainer")]."""
    out = []
    lines = [line for line in lines or () if line.get("date")]
    for index, first in enumerate(lines):
        for second in lines[index + 1:]:
            if _date(first["date"]) != _date(second["date"]):
                continue
            if not overlap(*(_on(first) + _on(second))):
                continue
            for field in ("venue", "trainer"):
                one, two = (first.get(field) or "").strip().lower(), (second.get(field) or "").strip().lower()
                if one and one == two:
                    out.append((first.get("course"), second.get("course"), field))
    return out


def _on(line):
    day = _date(line["date"])
    starts = _time(line.get("start_time")) or datetime.time(7, 0)
    ends = _time(line.get("end_time")) or datetime.time(9, 0)
    return datetime.datetime.combine(day, starts), datetime.datetime.combine(day, ends)


# ── A code at the sign-in table ───────────────────────────────────────
def code_of(text):
    """What a scanned or typed code names: an employee ID or number, from a
    QR code (EMP:<id>), a link (...?employee=<id>) or the number typed."""
    text = (text or "").strip()
    if not text:
        return ""
    if text.upper().startswith(QR_PREFIX):
        return text[len(QR_PREFIX):].strip()
    if "employee=" in text:
        return text.split("employee=", 1)[1].split("&", 1)[0].strip()
    return text


def own_window(start, end, now):
    """Whether an employee may sign themselves in now: from a little before
    the session starts until it ends, on one of its days."""
    start, end, now = _datetime(start), _datetime(end), _datetime(now)
    if not (start and end and now):
        return False
    if now.date() not in session_days(start, end):
        return False
    begins, ends = day_window(start, end, now.date())
    return begins - datetime.timedelta(minutes=EARLY_MINUTES) <= now <= ends


# ── The figures ───────────────────────────────────────────────────────
def figures(rows):
    """A set of attendance rows read as the blueprint asks: invited (people),
    days marked, attended, late, absent, excused, no-shows, the attendance
    and no-show rates, the completion rate (came every day) and the hours.

    rows: [{"employee", "status", "hours", "days"}], days being how many days
    the session runs."""
    people = {}
    for row in rows or ():
        person = people.setdefault(row.get("employee"), {"days": int(_num(row.get("days"))) or 1, "came": 0,
                                                          "statuses": [], "hours": 0.0})
        person["statuses"].append(row.get("status"))
        if row.get("status") in CAME:
            person["came"] += 1
            person["hours"] += _num(row.get("hours"))
    statuses = [status for person in people.values() for status in person["statuses"]]
    attended = sum(1 for person in people.values() if any(status in CAME for status in person["statuses"]))
    no_shows = sum(1 for person in people.values()
                   if person["statuses"] and all(status in (ABSENT, NO_SHOW) for status in person["statuses"]))
    excused = sum(1 for person in people.values()
                  if EXCUSED in person["statuses"] and not any(status in CAME for status in person["statuses"]))
    marked = sum(1 for person in people.values() if any(status not in OPEN for status in person["statuses"]))
    completed = sum(1 for person in people.values() if person["came"] >= person["days"])
    return {
        "invited": len(people),
        "registered": sum(1 for person in people.values()
                          if REGISTERED in person["statuses"] or any(status in CAME for status in person["statuses"])),
        "attended": attended, "late": sum(1 for person in people.values() if LATE in person["statuses"]),
        "absent": statuses.count(ABSENT), "excused": excused, "no_show": no_shows, "marked": marked,
        "attendance_rate": _share(attended, marked), "no_show_rate": _share(no_shows, marked),
        "completion_rate": _share(completed, len(people)),
        "hours": round(sum(person["hours"] for person in people.values()), 2),
    }


def _share(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


# ── Dates and numbers ─────────────────────────────────────────────────
def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    try:
        return datetime.datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def _time(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.time):
        return value
    if isinstance(value, datetime.datetime):
        return value.time()
    if isinstance(value, datetime.timedelta):
        return (datetime.datetime.min + value).time()
    parts = str(value).strip().split(":")
    try:
        return datetime.time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0,
                             int(float(parts[2])) if len(parts) > 2 else 0)
    except ValueError:
        return None


def _seconds(value):
    moment = _time(value)
    return moment.hour * 3600 + moment.minute * 60 + moment.second if moment else None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
