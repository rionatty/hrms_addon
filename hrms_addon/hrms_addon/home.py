# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The desk home, above the module tiles: a greeting, the figures that
matter today, what waits for the user, and the pages they open most.

The rules are in home_rules.py, without a Frappe import
(scripts/verify_home.py). This reads the site, in one call, and
public/js/hrms_addon_home.js draws it on Frappe's own desk page.

  summary   everything the home shows, for the logged-in user

WHOSE FIGURES

Each user has the desk of what they may know (home_rules.view_of): HR the
company's people, a manager the people who report to them, an employee
their own. People are read with frappe.get_list, so somebody limited to a
branch by a User Permission sees that branch's people, and a manager sees
only the reports they may read. What waits for the user is their own, as
My Alerts lists it (alerts.py): nothing here takes a user to look at.

NEVER AN ERROR

This is the page everybody lands on. A part that cannot be read is left out
and written to the Error Log (_or), and the rest of the home still comes.
"""

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from hrms_addon.hrms_addon import alerts, hr_overview, hr_overview_rules, home_rules as rules


@frappe.whitelist()
def summary():
    """Everything the desk home shows, for the logged-in user."""
    user = frappe.session.user
    today = getdate(nowdate())
    waits = rules.waiting(_or([], _alerts))
    hr = rules.sees_people(frappe.get_roles(user)) and frappe.has_permission("Employee", "read")
    me = _or(None, _employee_of, user)
    reports = _or([], _reports, me.name) if me and not hr else []
    view = rules.view_of(hr, me, reports)
    people = team = mine = None
    sections = {}
    if view == rules.HR:
        people = _or(None, _people, today)
        if people is not None:
            sections = {"today": people.pop("board"), "departments": people.pop("departments"),
                        "coming": people.pop("coming")}
    elif view == rules.MANAGER:
        team = _or(None, _team, me.name, reports, today)
        if team is not None:
            sections["team"] = team["rows"]
    if view in (rules.MANAGER, rules.STAFF):
        mine = _or(None, _mine, me, today)
        if mine is not None:
            sections["requests"] = mine.pop("requests")
            sections["holidays"] = _or([], _holidays, me, today)
    links = rules.shortcuts([page for page, _label in rules.SHORTCUTS if _may_open(page)])
    # the panels under what waits come in a call of their own (home_panels.py): here only which, and where
    from hrms_addon.hrms_addon import home_panels, home_panels_rules

    places = _or([], home_panels.places, frappe.get_roles(user), view, today)
    if any(item["place"] == home_panels_rules.SECTIONS for item in places):
        # Plants at a Glance stands where Today stood, and tells the same day plant by plant
        sections.pop("today", None)
    return {
        "greeting": hr_overview_rules.greeting(now_datetime().hour),
        "first_name": frappe.db.get_value("User", user, "first_name") or user,
        "today": str(today),
        "company": _or(None, frappe.defaults.get_user_default, "Company"),
        "waiting": waits,
        "view": view,
        "cards": rules.view_cards(view, waits, people, team, mine),
        "sections": sections,
        "shortcuts": links,
        "action": rules.call_to_action(links),
        "panels": places,
    }


def _or(fallback, read, *args):
    """What `read` gives, or `fallback` where it cannot be read. Logged with
    defer_insert: a GET is rolled back, and the log has to outlive it."""
    try:
        return read(*args)
    except Exception:
        frappe.log_error(title="Desk home: %s" % getattr(read, "__name__", "read"), defer_insert=True)
        return fallback


def _alerts():
    """The user's own assignments and notifications, as My Alerts lists them."""
    return alerts.my_alerts(limit=40)["alerts"]


def _people(today):
    """The company's people today, as far as the user may see them: the
    figures across the top, where they are today, the departments, and what
    is coming up."""
    rows = frappe.get_list("Employee", filters={"status": "Active"},
                           fields=["name", "employee_name", "date_of_joining", "date_of_birth", "department",
                                   "custom_probation_end_date"], limit_page_length=0)
    names = [row.name for row in rows] or [""]
    first = today.replace(day=1)
    until = add_days(today, rules.ENDING_DAYS)
    clocked, marked, on_leave, _seen = _marks(names, today)
    return {
        "board": rules.today_board([row.name for row in rows], clocked, marked, on_leave),
        "departments": rules.departments(rows),
        "coming": rules.coming_up(rows, _or([], _last_days, today), today),
        "active": len(rows),
        "joined": sum(1 for row in rows if row.date_of_joining and getdate(row.date_of_joining) >= first),
        "on_site": hr_overview._on_site(names, today),
        "on_leave": hr_overview._on_leave(names, today),
        "ending": _contracts_ending(today, until),
        "ending_from": str(today),
        "ending_to": str(until),
    }


def _marks(names, today):
    """Today, for these employees: who has clocked in, how Attendance marks
    each ({employee: (status, late_entry)}), who is on approved leave, and
    which of the three the user may read. Each is read with the user's own
    permissions, User Permissions narrowing it as everywhere else; one they
    may not read is not read at all, and what it would tell is left blank.
    reports_to is no permission: a manager sees their people's day only as
    far as their roles may read it."""
    seen = {"clock": bool(frappe.has_permission("Employee Checkin", "read")),
            "attendance": bool(frappe.has_permission("Attendance", "read")),
            "leave": bool(frappe.has_permission("Leave Application", "read"))}
    clocked, marked, on_leave = set(), {}, set()
    if seen["clock"]:
        clocked = set(frappe.get_list("Employee Checkin", filters={
            "employee": ["in", names], "time": [">=", str(today)]}, pluck="employee", limit_page_length=0))
    if seen["attendance"]:
        marked = {row.employee: (row.status, row.late_entry) for row in frappe.get_list(
            "Attendance", filters={"employee": ["in", names], "attendance_date": today, "docstatus": 1},
            fields=["employee", "status", "late_entry"], limit_page_length=0)}
    if seen["leave"]:
        on_leave = set(frappe.get_list("Leave Application", filters={
            "employee": ["in", names], "docstatus": 1, "status": "Approved", "from_date": ["<=", today],
            "to_date": [">=", today]}, pluck="employee", limit_page_length=0))
    return clocked, marked, on_leave, seen


def _last_days(today):
    """The submitted exits whose last day is coming, as far as the user may see them."""
    if not frappe.has_permission("Employee Separation", "read"):
        return []
    return frappe.get_list("Employee Separation", filters={
        "docstatus": 1, "custom_relieving_date": ["between", [today, add_days(today, rules.COMING_DAYS)]]},
        fields=["name", "employee", "employee_name", "custom_relieving_date"], limit_page_length=0)


def _employee_of(user):
    """The user's own employee record, if they have one that is active."""
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                               ["name", "employee_name", "holiday_list", "company"], as_dict=True)


def _reports(employee):
    """The active employees who report to this one, as far as the user may see them. Somebody who may not
    read employees at all has no team on their desk; asking would fail, and be logged, on every desk load."""
    if not frappe.has_permission("Employee", "read"):
        return []
    return frappe.get_list("Employee", filters={"reports_to": employee, "status": "Active"},
                           fields=["name", "employee_name"], limit_page_length=0)


def _team(employee, reports, today):
    """A manager's people and where each is today."""
    clocked, marked, on_leave, seen = _marks([row.name for row in reports] or [""], today)
    return dict(rules.team_today(reports, clocked, marked, on_leave, seen=seen), employee=employee)


def _mine(me, today):
    """An employee's own: the leave they have left, their days at work this
    month, and their requests."""
    from hrms_addon.hrms_addon import exits

    days = []
    if frappe.has_permission("Attendance", "read"):
        days = frappe.get_list("Attendance", filters={
            "employee": me.name, "docstatus": 1, "attendance_date": ["between", [today.replace(day=1), today]]},
            fields=["status", "late_entry"], limit_page_length=0)
    found = []
    for doctype, label in rules.REQUESTS:
        # a site without the doctype, or a user who may not read it, has none of these on the desk
        if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
            continue
        for row in frappe.get_list(doctype, filters={"employee": me.name, "docstatus": ["<", 2]},
                                   fields=["name", "status", "docstatus", "modified"], order_by="modified desc",
                                   limit_page_length=50):
            found.append((doctype, label, row))
    requests = rules.my_requests(found)
    return dict(rules.my_days(days), employee=me.name, waiting=requests["waiting"], requests=requests["rows"],
                leave_left=_or(None, exits._leave_balance, me.name, today))


def _holidays(me, today):
    """The next holidays on the employee's holiday list, or their company's."""
    holiday_list = me.get("holiday_list") or frappe.get_cached_value("Company", me.get("company"), "default_holiday_list")
    if not holiday_list:
        return []
    return rules.holidays(frappe.get_all("Holiday", filters={
        "parent": holiday_list, "holiday_date": [">=", today], "weekly_off": 0},
        fields=["holiday_date", "description"], order_by="holiday_date asc", limit_page_length=3), today)


def _contracts_ending(today, until):
    """The contracts still running that end by `until`, as far as the user
    may see them. None on a site without the contracts."""
    try:
        return len(frappe.get_list("Employee Contract", filters={
            "docstatus": 1, "status": ["in", list(rules.RUNNING)], "end_date": ["between", [today, until]]},
            pluck="name", limit_page_length=0))
    except Exception:
        return 0


def _may_open(page):
    """A page the site has and the user's roles may open."""
    try:
        return bool(frappe.db.exists("Page", page) and frappe.get_cached_doc("Page", page).is_permitted())
    except Exception:
        return False
