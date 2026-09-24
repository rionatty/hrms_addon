# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR calendar (page/hr_calendar): one month of leave as a roster,
everybody down the side and the days across, and the month's training as
a wall calendar. One call (month) fills the page; nothing here writes.

Who sees what follows the leave plan (leave.own_place): HR, heads of
department and supervisors see every plant and department, an employee
their own.
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from hrms_addon.hrms_addon import calendar_rules as rules, leave, training_rules

PLAN, ROW, APPLICATION = "Annual Leave Plan", "Annual Leave Plan Employee", "Leave Application"
EVENT, EVENT_EMPLOYEE = "Training Event", "Training Event Employee"
SCHEDULE, LINE = "Monthly Training Schedule", "Training Schedule Line"
CALENDAR, ENTRY = "Training Calendar", "Training Calendar Entry"
# the page's own roles (page/hr_calendar/hr_calendar.json): Training Event
# is HR's to read, and this only shows when and where it is
OPENS_TO = {"HR User", "HR Manager", "System Manager", "Head of Department", "Supervisor", "Employee"}
PEOPLE_LIMIT = 300
NAMES_SHOWN = 60


@frappe.whitelist()
def month(view="leave", year=None, month=None, branch=None, department=None, everyone=0):
    """Everything the calendar shows for one month, in one answer."""
    if not OPENS_TO & set(frappe.get_roles()):
        frappe.throw(_("You may not open the calendar."), frappe.PermissionError)
    year, number = rules.month_of(year, month, getdate(today()))
    start, end = rules.month_window(year, number)
    out = {"year": year, "month": number, "title": rules.month_title(year, number),
           "view": "training" if view == "training" else "leave", "branch": branch, "department": department}
    own = leave.own_place(frappe.session.user)
    if own is not None:
        if not own:
            days = rules.days(year, number, {}, getdate(today()))
            return dict(out, days=days, weeks=rules.weeks(days), people=[], counts={"off": {}, "planned": {}},
                        sessions=[], planned=[], restricted=1)
        branch, department = own.branch, own.department
        out.update(branch=branch, department=department, restricted=1)
    if out["view"] == "training":
        out.update(_training(year, number, start, end, branch, department))
    else:
        out.update(_leave(year, number, start, end, branch, department, cint(everyone)))
    return out


# ── Leave, as a roster ────────────────────────────────────────────────
def _leave(year, number, start, end, branch, department, everyone):
    people = _people(branch, department)
    names = [person.name for person in people]
    applications = _applications(names, start, end)
    planned = _planned(names, year, start, end)
    with_leave = {row["employee"] for row in applications} | {row["employee"] for row in planned}
    shown = [person for person in people if everyone or person.name in with_leave]
    lists = _holiday_lists(shown, start, end)
    holidays = {person.name: lists.get(_holiday_list(person), {}) for person in shown}
    cells = rules.leave_cells(applications, planned, holidays, start, end)
    header = rules.common_holidays(list(holidays.values())) if shown else _company_holidays(start, end)
    days = rules.days(year, number, header, getdate(today()))
    return {
        "days": days, "weeks": rules.weeks(days),
        "people": [{"employee": person.name, "employee_name": person.employee_name,
                    "department": person.department, "designation": person.designation,
                    "cells": cells.get(person.name, {})} for person in shown],
        "counts": rules.off_counts(cells, days), "most_off": _most_off(year, branch, department),
        "everyone": everyone, "in_all": len(people), "capped": len(people) >= PEOPLE_LIMIT,
    }


def _people(branch, department):
    filters = {"status": "Active"}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = department
    return frappe.get_all("Employee", filters=filters,
                          fields=["name", "employee_name", "department", "designation", "holiday_list", "company"],
                          order_by="employee_name asc", limit_page_length=PEOPLE_LIMIT)


def _applications(names, start, end):
    if not names:
        return []
    out = []
    for row in frappe.get_all(APPLICATION,
                              filters={"employee": ["in", names], "docstatus": ["in", [0, 1]],
                                       "from_date": ["<=", end], "to_date": [">=", start]},
                              fields=["name", "employee", "from_date", "to_date", "leave_type", "status", "docstatus"]):
        kind = rules.leave_kind(row.docstatus, row.status)
        if kind:
            out.append({"employee": row.employee, "from_date": row.from_date, "to_date": row.to_date, "kind": kind,
                        "label": "%s, %s" % (row.leave_type, _dates(row.from_date, row.to_date)),
                        "link": [APPLICATION, row.name]})
    return out


def _planned(names, year, start, end):
    if not names:
        return []
    plans = frappe.get_all(PLAN, filters={"docstatus": 1, "year": year}, pluck="name")
    if not plans:
        return []
    return [{"employee": row.employee, "planned_from": row.planned_from, "planned_to": row.planned_to,
             "label": _("Planned, {0}").format(_dates(row.planned_from, row.planned_to)), "link": [PLAN, row.parent]}
            for row in frappe.get_all(ROW, filters={"parent": ["in", plans], "parenttype": PLAN,
                                                     "employee": ["in", names],
                                                     "planned_from": ["<=", end], "planned_to": [">=", start]},
                                      fields=["parent", "employee", "planned_from", "planned_to"])]


def _most_off(year, branch, department):
    """The tightest Most Off at Once of the year's approved plans in view."""
    filters = {"docstatus": 1, "year": year}
    if branch:
        filters["branch"] = branch
    if department:
        filters["department"] = department
    values = [cint(value) for value in frappe.get_all(PLAN, filters=filters, pluck="most_off") if cint(value)]
    return min(values) if values else 0


def _dates(first, last):
    return _("{0} to {1}").format(frappe.utils.format_date(first, "d MMM"), frappe.utils.format_date(last, "d MMM"))


# ── Holidays ──────────────────────────────────────────────────────────
def _holiday_list(person):
    return person.get("holiday_list") or _company_holiday_list(person.get("company"))


def _company_holiday_list(company=None):
    if company:
        return frappe.db.get_value("Company", company, "default_holiday_list")
    first = frappe.get_all("Company", fields=["default_holiday_list"], order_by="creation asc", limit_page_length=1)
    return first[0].default_holiday_list if first else None


def _holiday_lists(people, start, end):
    """{holiday list: {date: description}} for the lists these people are on."""
    wanted = {name for name in (_holiday_list(person) for person in people) if name}
    return {name: _list_holidays(name, start, end) for name in wanted}


def _list_holidays(name, start, end):
    return {getdate(row.holiday_date).isoformat(): row.description or (_("Weekly off") if row.weekly_off else _("Holiday"))
            for row in frappe.get_all("Holiday", filters={"parent": name, "parenttype": "Holiday List",
                                                          "holiday_date": ["between", [start, end]]},
                                      fields=["holiday_date", "description", "weekly_off"])}


def _company_holidays(start, end):
    name = _company_holiday_list()
    return _list_holidays(name, start, end) if name else {}


# ── Training, as a wall calendar ──────────────────────────────────────
def _training(year, number, start, end, branch, department):
    days = rules.days(year, number, _company_holidays(start, end), getdate(today()))
    sessions = _events(start, end, branch, department) + _unbooked(start, end, department)
    sessions.sort(key=lambda session: (session["date"], session["start"], session["course"] or ""))
    return {"days": days, "weeks": rules.weeks(days), "sessions": sessions,
            "planned": _undated(year, number), "people": [], "counts": {"off": {}, "planned": {}}}


def _events(start, end, branch, department):
    """The Training Events in the month, one chip per day they run."""
    events = frappe.get_all(EVENT, filters={"docstatus": ["in", [0, 1]], "event_status": ["!=", "Cancelled"],
                                            "start_time": ["<", add_days(end, 1)], "end_time": [">=", start]},
                            fields=["name", "event_name", "course", "event_status", "location", "trainer_name",
                                    "start_time", "end_time", "docstatus"])
    if not events:
        return []
    people = frappe.get_all(EVENT_EMPLOYEE, filters={"parent": ["in", [event.name for event in events]],
                                                     "parenttype": EVENT},
                            fields=["parent", "employee", "employee_name", "department"])
    places = {}
    if branch or department:
        places = {row.name: row for row in frappe.get_all(
            "Employee", filters={"name": ["in", [row.employee for row in people] or [""]]},
            fields=["name", "branch", "department"])}
    by_event = {}
    for row in people:
        by_event.setdefault(row.parent, []).append(row)
    out = []
    for event in events:
        status = rules.session_status(event.event_status, event.docstatus)
        if not status:
            continue
        mine = by_event.get(event.name, [])
        if branch or department:
            mine = [row for row in mine if _in_place(places.get(row.employee), row, branch, department)]
            if not mine:
                continue
        for day in rules.span_days(event.start_time, event.end_time, start, end):
            out.append({"date": day, "start": rules.clock(event.start_time), "end": rules.clock(event.end_time),
                        "course": event.course or event.event_name, "venue": event.location,
                        "trainer": event.trainer_name, "status": status, "people": len(mine),
                        "names": [row.employee_name or row.employee for row in mine][:NAMES_SHOWN],
                        "target": None, "link": [EVENT, event.name]})
    return out


def _in_place(place, row, branch, department):
    department_of = (place and place.department) or row.department
    return (not branch or bool(place and place.branch == branch)) and (not department or department_of == department)


def _unbooked(start, end, department):
    """Sessions on a schedule still being drawn up: dated, not yet booked."""
    drafts = frappe.get_all(SCHEDULE, filters={"docstatus": 0}, pluck="name")
    if not drafts:
        return []
    filters = {"parent": ["in", drafts], "parenttype": SCHEDULE, "training_date": ["between", [start, end]],
               "training_event": ["is", "not set"]}
    if department:
        filters["department"] = department
    return [{"date": getdate(row.training_date).isoformat(),
             "start": rules.clock(row.start_time) or rules.clock(training_rules.SESSION_STARTS),
             "end": rules.clock(row.end_time) or rules.clock(training_rules.SESSION_ENDS),
             "course": row.course, "venue": row.venue, "trainer": row.trainer, "status": rules.PLANNED_SESSION,
             "people": 0, "names": [], "target": row.target_group, "link": [SCHEDULE, row.parent]}
            for row in frappe.get_all(LINE, filters=filters,
                                      fields=["parent", "course", "training_date", "start_time", "end_time", "venue",
                                              "trainer", "target_group"])]


def _undated(year, number):
    """What the training calendar plans for the month with no date yet."""
    rows = frappe.get_all(ENTRY, filters={"parenttype": CALENDAR, "planned_year": year,
                                          "planned_month": rules.MONTHS[number - 1], "scheduled": ["!=", 1]},
                          fields=["parent", "course", "trainer", "target_group", "section"])
    if not rows:
        return []
    live = set(frappe.get_all(CALENDAR, filters={"name": ["in", [row.parent for row in rows]],
                                                  "docstatus": ["in", [0, 1]]}, pluck="name"))
    return [{"course": row.course, "trainer": row.trainer, "target": row.target_group, "section": row.section,
             "link": [CALENDAR, row.parent]} for row in rows if row.parent in live]
