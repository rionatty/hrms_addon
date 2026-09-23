# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the attendance board is showing.

The reading is in board_rules.py and what a register cell says is
attendance_rules.register_code; this is the part that asks the site.

One call fills the whole board, because it is one screen and five round
trips to draw it would be five chances to show half of it.

WHAT IT READS, AND WHAT IT DOES NOT

Everything here is a read. The board never marks attendance, never
pushes a punch and never closes a cycle — those belong to Frappe HR's
own auto-attendance and to devices.py. A board that quietly wrote things
while somebody looked at it would be a bad board.

THE CYCLE

The 26th of one month to the 25th of the next, which is Luuka's
attendance and payroll month (attendance_rules.CYCLE_START_DAY). A
cycle is named after the month it ENDS in, the way the register is.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime

from hrms_addon.hrms_addon import (attendance, attendance_rules as register,
                                   board_rules as rules)

ATTENDANCE = "Attendance"
CHECKIN = "Employee Checkin"
DEVICE = "Attendance Device"
LOG = "Attendance Device Log"
OFF_DUTY = "Off Duty Request"

# a register is read one plant at a time; a whole company at once is a
# spreadsheet, not a screen
REGISTER_LIMIT = 300
# how far back "clocked in and never out" is worth chasing
OPEN_DAYS = 7


@frappe.whitelist()
def board(cycle=None, branch=None, department=None, limit=None):
    """Everything on the board, in one answer."""
    if not frappe.has_permission(ATTENDANCE, "read"):
        frappe.throw(_("You may not read attendance."), frappe.PermissionError)

    now = now_datetime()
    year, month = _cycle(cycle, now)
    start, end = register.cycle_window(year, month)
    days = register.cycle_days(year, month)
    people = _people(start, end, branch, department)
    limit = cint(limit) or REGISTER_LIMIT

    marked = _attendance(start, end, list(people))
    # LPL/HR/25 has one day per form and its own letter on the register;
    # attendance.py already reads them, so this does not read them twice
    off_duty = (attendance._off_duty_between(list(people), start, end)
                if people else set())
    holidays = _holidays(people, start, end)
    # every row is worked out, and only the SHOWING of them is capped:
    # a footer that tallied the first three hundred people would be a
    # footer that quietly disagreed with the register it sits under
    rows = _register_rows(people, marked, off_duty, holidays, days)
    tallies = register.tallies(rows, days)
    lines = [_line(row, days) for row in rows]

    floor = _floor(people, now)
    machines = _machines(now, branch)
    return {
        "cycle": {
            "year": year, "month": month,
            "label": _("{0} to {1}").format(frappe.format(start, {"fieldtype": "Date"}),
                                            frappe.format(end, {"fieldtype": "Date"})),
            "start": str(start), "end": str(end),
            "days": [str(day) for day in days],
            "today": str(getdate(now)),
            "progress": rules.progress(days, getdate(now)),
        },
        "floor": floor,
        "cycle_totals": _totals(rows, days),
        "per_day": _per_day(rows, days),
        "plants": rules.plants(lines, floor["people"], machines),
        "register": {
            "rows": lines[:limit],
            "tallies": _tally_lines(tallies, days),
            "shown": min(len(lines), limit), "of": len(lines),
            "nights_short": [str(day) for day in rules.nights_covered(tallies, days)],
        },
        "exceptions": _exceptions(start, end, marked, machines, branch),
        "machines": machines,
        "codes": [{"code": code, "meaning": meaning}
                  for code, meaning in register.CODE_MEANING.items()],
        "read_at": str(now),
    }


# ── The cycle ─────────────────────────────────────────────────────────
def _cycle(cycle, now):
    """"2026-09" if somebody picked one, otherwise the cycle today is in."""
    if cycle:
        parts = str(cycle).split("-")
        try:
            return int(parts[0]), int(parts[1])
        except (IndexError, ValueError):
            frappe.throw(_("Enter the cycle as YYYY-MM, for example 2026-09."))
    return register.cycle_of(getdate(now))


# ── Who is on the register ────────────────────────────────────────────
def _people(start, end, branch=None, department=None):
    """Everybody who was on the books during the cycle, by number.

    Not only those still here: somebody who left on the 10th still worked
    the days before it, and the register has to show them.
    """
    filters = {"date_of_joining": ["<=", end], "status": ["in", ("Active", "Left")]}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = department
    found = frappe.get_all(
        "Employee", filters=filters, limit_page_length=0,
        fields=["name", "employee_name", "branch", "department", "designation",
                "employment_type", "relieving_date", "holiday_list", "status",
                "attendance_device_id", "default_shift"],
        order_by="employee_name asc")
    people = {}
    for row in found:
        if row.relieving_date and getdate(row.relieving_date) < getdate(start):
            continue
        people[row.name] = row
    return people


def _attendance(start, end, employees):
    """Every marked day in the cycle, as {employee: {date: row}}."""
    if not employees:
        return {}
    marked = {}
    for row in frappe.get_all(
            ATTENDANCE, limit_page_length=0,
            filters={"attendance_date": ["between", [start, end]], "docstatus": 1,
                     "employee": ["in", employees]},
            fields=["employee", "attendance_date", "status", "shift", "leave_type",
                    "in_time", "out_time", "working_hours", "late_entry", "early_exit"]):
        marked.setdefault(row.employee, {})[getdate(row.attendance_date)] = row
    return marked


def _holidays(people, start, end):
    """The holiday each person's list keeps, read once per list rather
    than once per person."""
    lists = {row.holiday_list for row in people.values() if row.holiday_list}
    default = frappe.db.get_value("Company", frappe.defaults.get_user_default("Company"),
                                  "default_holiday_list")
    if default:
        lists.add(default)
    kept = {}
    for name in lists:
        kept[name] = {getdate(row.holiday_date) for row in frappe.get_all(
            "Holiday", filters={"parent": name, "parenttype": "Holiday List",
                                "holiday_date": ["between", [start, end]]},
            fields=["holiday_date"], limit_page_length=0)}
    return {"lists": kept, "default": default}


# ── The register ──────────────────────────────────────────────────────
def _register_rows(people, marked, off_duty, holidays, days):
    """One line per person, each day a letter of LPL/HR/07."""
    rows = []
    for name, person in people.items():
        theirs = marked.get(name) or {}
        kept = (holidays["lists"].get(person.holiday_list or holidays["default"])
                or set())
        cells = {}
        for day in days:
            day = getdate(day)
            marked_day = theirs.get(day)
            cells[day] = register.register_code({
                "status": marked_day.status if marked_day else None,
                "shift": (marked_day.shift if marked_day else None) or person.default_shift,
                "leave_type": marked_day.leave_type if marked_day else None,
                "off_duty": (name, day) in off_duty,
                "holiday": day in kept,
            })
        rows.append({
            "employee": name, "employee_name": person.employee_name,
            "branch": person.branch, "department": person.department,
            "designation": person.designation,
            "employment": person.employment_type, "days": cells,
        })
    return rows


def _line(row, days):
    """A register row as the page draws it: the letters in column order,
    and what they add up to."""
    codes = [row["days"].get(getdate(day)) or "" for day in days]
    return dict(rules.worked_and_overtime(codes),
                employee=row["employee"], employee_name=row["employee_name"],
                branch=row["branch"], department=row["department"],
                employment=row["employment"], codes=codes)


def _tally_lines(tallies, days):
    """The footer of LPL/HR/07, in the order it is printed."""
    order = list(register.TALLIES) + ["Total number of staff in Night shift"]
    return [{"label": name,
             "counts": [int((tallies.get(name) or {}).get(getdate(day)) or 0) for day in days]}
            for name in order]


def _totals(rows, days):
    """What the whole cycle came to, by letter."""
    counted = {code: 0 for code in register.CODES}
    for row in rows:
        for day in days:
            code = row["days"].get(getdate(day))
            if code:
                counted[code] = counted.get(code, 0) + 1
    worked = counted[register.DAY_SHIFT] + counted[register.NIGHT_SHIFT]
    return dict(counted, worked=worked,
                rate=rules.rate(worked, worked + counted[register.ABSENT]))


def _per_day(rows, days):
    """The strip along the top: one column per day of the cycle."""
    strip = []
    for day in days:
        day = getdate(day)
        counted = {code: 0 for code in register.CODES}
        for row in rows:
            code = row["days"].get(day)
            if code:
                counted[code] = counted.get(code, 0) + 1
        worked = counted[register.DAY_SHIFT] + counted[register.NIGHT_SHIFT]
        full = rules.rate(worked, worked + counted[register.ABSENT])
        strip.append({"date": str(day), "worked": worked,
                      "night": counted[register.NIGHT_SHIFT],
                      "absent": counted[register.ABSENT],
                      "leave": counted[register.LEAVE] + counted[register.SICK],
                      "rate": full, "band": rules.band(full)})
    return strip


# ── The floor, this minute ────────────────────────────────────────────
def _floor(people, now):
    """Who is inside now, how long they have been, and where.

    Yesterday's punches are read as well as today's, because a night
    shift starts on one day and ends on the next.
    """
    if not people:
        return {"tally": rules.floor_tally([]), "branches": [], "people": []}
    readings = frappe.get_all(
        CHECKIN, limit_page_length=0,
        filters={"employee": ["in", list(people)],
                 "time": ["between", [add_days(getdate(now), -1), now]]},
        fields=["employee", "time", "log_type", "shift"], order_by="time asc")
    standing = rules.inside_now([{"employee": row.employee, "time": row.time,
                                  "log_type": row.log_type, "shift": row.shift}
                                 for row in readings])
    inside = []
    for name, row in standing.items():
        person = people.get(name)
        if not person:
            continue
        shift = row.get("shift") or person.default_shift or ""
        hours = rules.hours_so_far(row.get("time"), now)
        inside.append({
            "employee": name, "employee_name": person.employee_name,
            "branch": person.branch, "department": person.department,
            "since": str(row.get("time")), "hours": hours,
            "night": "night" in str(shift).lower(),
            "standing": rules.standing_of(hours),
        })
    inside.sort(key=lambda row: -row["hours"])
    return {"tally": rules.floor_tally(inside), "branches": rules.by_branch(inside),
            "people": inside}


# ── What needs a person ───────────────────────────────────────────────
def _exceptions(start, end, marked, machines, branch=None):
    """Each thing somebody has to act on, counted, with where to go.

    Every count is scoped to the plant being looked at. Luuka's plants
    have their own HR Officers, and a list that showed one plant's
    register beside another plant's dead machines would be telling
    somebody to go and fix something that is not theirs.
    """
    punched = _days_with_a_punch(start, end, list(marked))
    on_leave, absent = 0, 0
    for employee, days in marked.items():
        for day, row in days.items():
            if day not in punched.get(employee, ()):
                continue
            if row.status == "On Leave":
                on_leave += 1
            elif row.status == "Absent":
                absent += 1

    # the punches this plant's machines wrote down; a terminal nobody has
    # placed belongs to no plant, so it is only counted company-wide
    theirs = [row["device"] for row in machines]
    on_theirs = {"device": ["in", theirs]} if branch else {}
    unplaced = [row for row in _devices() if not row.branch or not row.direction]
    counted = {
        "on_leave_but_punched": on_leave,
        "absent_with_punch": absent,
        "in_without_out": _open_days(now_datetime(), list(marked) if branch else None),
        "unknown_badge": _log_count("Unknown Employee", on_theirs),
        "failed_push": _log_count("Failed", on_theirs),
        "undirected_terminal": 0 if branch else len(unplaced),
        "silent_terminal": len([row for row in machines
                                if row["health"] in (rules.SILENT, rules.NEVER)]),
    }
    at_plant = {"branch": branch} if branch else {}
    routes = {
        "unknown_badge": {"doctype": LOG, "filters": dict(on_theirs,
                                                          status="Unknown Employee")},
        "failed_push": {"doctype": LOG, "filters": dict(on_theirs, status="Failed")},
        "undirected_terminal": {"doctype": DEVICE, "filters": {"branch": ""}},
        "silent_terminal": {"doctype": DEVICE, "filters": at_plant},
        "on_leave_but_punched": {"doctype": ATTENDANCE, "filters": dict(at_plant,
                                                                        status="On Leave")},
        "absent_with_punch": {"doctype": ATTENDANCE, "filters": dict(at_plant,
                                                                     status="Absent")},
        "in_without_out": {"doctype": CHECKIN, "filters": {"log_type": "IN"}},
    }
    return [dict(row, count=counted.get(row["kind"], 0), route=routes.get(row["kind"]))
            for row in rules.EXCEPTIONS]


def _log_count(status, on_theirs):
    """How many log rows of a status, at these machines. A plant with no
    machine of its own has none, rather than all of them."""
    if on_theirs and not on_theirs.get("device", [None, []])[1]:
        return 0
    return frappe.db.count(LOG, dict(on_theirs, status=status))


def _days_with_a_punch(start, end, employees):
    """{employee: {dates}} — which days a machine saw somebody at all."""
    if not employees:
        return {}
    seen = {}
    for row in frappe.get_all(
            CHECKIN, limit_page_length=0,
            filters={"employee": ["in", employees],
                     "time": ["between", [start, add_days(end, 1)]]},
            fields=["employee", "time"]):
        seen.setdefault(row.employee, set()).add(getdate(row.time))
    return seen


def _open_days(now, employees=None):
    """Days somebody clocked in and never clocked out, over the last week.

    Only the last few days: an open day from March is history, not
    something anybody is going to go and fix this morning. And only the
    people being looked at, so a plant is not handed another's.
    """
    since = add_days(getdate(now), -OPEN_DAYS)
    filters = {"time": [">=", since]}
    if employees is not None:
        if not employees:
            return 0
        filters["employee"] = ["in", employees]
    tally = {}
    for row in frappe.get_all(
            CHECKIN, limit_page_length=0, filters=filters,
            fields=["employee", "time", "log_type"], order_by="time asc"):
        day = getdate(row.time)
        # a night shift's OUT lands the next morning, so the day it
        # belongs to is the day its IN was
        key = (row.employee, day)
        if str(row.log_type or "").upper() == "IN":
            tally[key] = tally.get(key, 0) + 1
        else:
            for back in (0, 1):
                older = (row.employee, getdate(add_days(day, -back)))
                if tally.get(older):
                    tally[older] -= 1
                    break
    return len([count for count in tally.values() if count > 0])


# ── The machines ──────────────────────────────────────────────────────
def _devices(branch=None):
    filters = {"branch": branch} if branch else None
    return frappe.get_all(DEVICE, limit_page_length=0, filters=filters,
                          fields=["name", "device_name", "branch", "direction", "source",
                                  "enabled", "company"],
                          order_by="device_name asc")


def _machines(now, branch=None):
    """Every clocking machine, and how long since it last said anything.

    One plant's machines when a plant is being looked at: its HR Officer
    cannot do anything about a machine at the other plant, and a red dot
    they cannot act on is noise.
    """
    devices = _devices(branch)
    if not devices:
        return []
    last = {row.device: row.last_seen for row in frappe.get_all(
        LOG, filters={"device": ["in", [row.name for row in devices]]},
        fields=["device", "MAX(punch_time) as last_seen"], group_by="device")}
    today = {row.device: row.punches for row in frappe.get_all(
        LOG, filters={"device": ["in", [row.name for row in devices]],
                      "punch_time": [">=", getdate(now)]},
        fields=["device", "COUNT(name) as punches"], group_by="device")}
    machines = []
    for row in devices:
        seen = last.get(row.name)
        machines.append({
            "device": row.name, "device_name": row.device_name or row.name,
            "branch": row.branch, "direction": row.direction, "source": row.source,
            "enabled": cint(row.enabled),
            "last_seen": str(seen) if seen else None,
            "health": rules.machine_health(seen, now) if cint(row.enabled) else rules.QUIET,
            "punches_today": cint(today.get(row.name)),
        })
    order = {rules.NEVER: 0, rules.SILENT: 1, rules.QUIET: 2, rules.HEALTHY: 3}
    machines.sort(key=lambda row: (order.get(row["health"], 9), row["device_name"]))
    return machines


@frappe.whitelist()
def branches():
    """The plants and departments the board can be narrowed to."""
    return {
        "branches": frappe.get_all("Branch", pluck="name", order_by="name asc",
                                   limit_page_length=0),
        "departments": frappe.get_all("Department", pluck="name", order_by="name asc",
                                      limit_page_length=0,
                                      filters={"is_group": 0}),
    }
