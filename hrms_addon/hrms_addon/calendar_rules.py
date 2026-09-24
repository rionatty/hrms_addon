# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR calendar's rules: the month and its days, what each day of a
roster row shows, what clicking an empty day or dragging a block may do,
and how a block moves.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_calendar.py exercises them without a bench.
"""
import calendar
import datetime

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# what a leave block is; on a day with more than one, the strongest shows
APPROVED, APPLIED, PLANNED, MOVING = "approved", "applied", "planned", "moving"
LEAVE_KINDS = (APPROVED, APPLIED, PLANNED, MOVING)
STRENGTH = {APPROVED: 4, APPLIED: 3, PLANNED: 2, MOVING: 1}
HOLIDAY = "holiday"

# what a training block is
SCHEDULED, COMPLETED, PLANNED_SESSION = "scheduled", "completed", "planned"
SESSION_KINDS = (SCHEDULED, COMPLETED, PLANNED_SESSION)

# where an Annual Leave Plan stands, as the calendar treats it
PLAN_DRAFT, PLAN_PENDING, PLAN_APPROVED = "draft", "pending", "approved"
# what clicking an empty day does, and how a planned block moves
ADD_PLAN, ADD_APPLY = "plan", "apply"
MOVE_DIRECT, MOVE_ASK = "direct", "ask"


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


def month_number(name):
    """March -> 3; 0 for anything else."""
    return MONTHS.index(name) + 1 if name in MONTHS else 0


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


def session_status(event_status, docstatus=0):
    """What a Training Event shows as; None when it is off the calendar."""
    if int(docstatus or 0) == 2 or event_status == "Cancelled":
        return None
    return COMPLETED if event_status == "Completed" else SCHEDULED


def plan_state(docstatus, workflow_state):
    """An Annual Leave Plan being drawn up, waiting for approval, approved,
    or (cancelled) nothing."""
    docstatus = int(docstatus or 0)
    if docstatus == 1:
        return PLAN_APPROVED
    if docstatus == 2:
        return None
    return PLAN_DRAFT if workflow_state in (None, "", "Draft") else PLAN_PENDING


def leave_add_mode(is_hr, is_self, state):
    """What clicking an empty day on somebody's row does: HR put planned leave
    on a plan still being drawn up (or a new one); on an approved plan, or
    for the employee themself, a Leave Application is made; nobody else may."""
    if is_hr and state in (None, PLAN_DRAFT):
        return ADD_PLAN
    if is_hr or is_self:
        return ADD_APPLY
    return None


def leave_move_mode(is_hr, is_self, state, applied=False, moving=False):
    """How a planned block moves: HR move it straight on a plan being drawn
    up; on an approved plan the employee or HR ask to move it (a Leave Plan
    Change, for the supervisor and then the head of department), unless the
    leave is applied for already or a move is waiting."""
    if state == PLAN_DRAFT:
        return MOVE_DIRECT if is_hr else None
    if state == PLAN_APPROVED and (is_hr or is_self) and not applied and not moving:
        return MOVE_ASK
    return None


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


def pick_cells(blocks, holidays, month_days, one_per_day=True):
    """What each row shows on each day: {row: {date: {"blocks": [key, ...],
    "holiday": text or None}}}.

    blocks: key, row, from, to, kind, and start (a time, for the order).
    holidays: {row: {date: description}}.
    one_per_day: a leave row shows the strongest block of a day (approved,
    then applied for, then planned, then a move asked for); a training row
    shows every session of the day, the earliest first.
    """
    dates = [day["date"] for day in month_days]
    if not dates:
        return {}
    start, end = dates[0], dates[-1]
    kinds = {block["key"]: block.get("kind") for block in blocks}
    cells = {}

    def cell(row, day):
        return cells.setdefault(row, {}).setdefault(day, {"blocks": [], "holiday": None})

    for block in sorted(blocks, key=lambda block: (str(block.get("start") or ""), str(block["key"]))):
        for day in span_days(block.get("from"), block.get("to"), start, end):
            here = cell(block["row"], day)
            if not one_per_day:
                here["blocks"].append(block["key"])
            elif not here["blocks"]:
                here["blocks"] = [block["key"]]
            elif STRENGTH.get(block.get("kind"), 0) > STRENGTH.get(kinds.get(here["blocks"][0]), 0):
                here["blocks"] = [block["key"]]
    for row, dated in (holidays or {}).items():
        for day, text in (dated or {}).items():
            if day in dates:
                cell(row, day)["holiday"] = text or "Holiday"
    return cells


def off_counts(cells, blocks, month_days):
    """Per day, how many are off (leave approved or applied for) and how
    many more only have leave planned; a holiday counts nobody."""
    kinds = {block["key"]: block.get("kind") for block in blocks}
    off = {day["date"]: 0 for day in month_days}
    planned = dict(off)
    for dated in cells.values():
        for day, here in dated.items():
            if day not in off or here.get("holiday") or not here.get("blocks"):
                continue
            kind = kinds.get(here["blocks"][0])
            if kind in (APPROVED, APPLIED):
                off[day] += 1
            elif kind == PLANNED:
                planned[day] += 1
    return {"off": off, "planned": planned}


def too_many(count, most_off):
    """Whether a day's count is more than the plan allows off at once (0: no limit)."""
    return bool(int(most_off or 0)) and int(count or 0) > int(most_off)


def shifted(first, last, new_first):
    """A span moved to start on `new_first`, as long as it was."""
    first, last, new_first = _date(first), _date(last), _date(new_first)
    return new_first, new_first + (last - first)


def shifted_session(start, end, new_day):
    """A session moved to `new_day`, at the same hours and as long."""
    start, end = _datetime(start), _datetime(end)
    moved = datetime.datetime.combine(_date(new_day), start.time())
    return moved, moved + (end - start)


def in_month(day, year, month):
    day = _date(day)
    return bool(day) and (day.year, day.month) == (int(year), int(month))


def clock(value):
    """'07:00' from a datetime, a time, a duration or their text; '' from nothing."""
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime.datetime, datetime.time)):
        return value.strftime("%H:%M")
    if isinstance(value, datetime.timedelta):
        return (datetime.datetime.min + value).strftime("%H:%M")
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


def _datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    text = str(value).strip().replace("T", " ")
    return datetime.datetime.fromisoformat(text[:19] if len(text) > 10 else text + " 00:00:00")
