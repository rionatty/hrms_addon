# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""HR Overview: the HR home dashboard (page/hr_overview), filled in one call.

The rules are in hr_overview_rules.py (no Frappe import, tested by
scripts/verify_hr_overview.py); the page is page/hr_overview/hr_overview.js.

  overview   every figure on the page, for the branch chosen or for every
             branch the user may see

WHOSE FIGURES

The employees are read with frappe.get_list, so someone limited to a
branch by a User Permission sees that branch's people, and every other
figure is counted for those people only. The tasks are the user's own
assignments, as My Alerts lists them (alerts.py).
"""

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from hrms_addon.hrms_addon import alerts
from hrms_addon.hrms_addon import hr_overview_rules as rules

# how many of the user's tasks the page shows; the rest are in My Alerts
TASKS_SHOWN = 4
# how far back the attendance chart looks for days with attendance marked
ATTENDANCE_LOOKBACK = 21


@frappe.whitelist()
def overview(branch: str | None = None) -> dict:
    """Every figure on the HR Overview page."""
    frappe.has_permission("Employee", "read", throw=True)
    today = getdate(nowdate())
    people = frappe.get_list("Employee", filters={"branch": branch} if branch else {},
                             fields=["name", "status", "date_of_joining", "relieving_date", "employment_type"],
                             limit_page_length=0)
    active = [row for row in people if row.status == "Active"]
    names = [row.name for row in active] or [""]
    history = [(getdate(row.date_of_joining) if row.date_of_joining else None,
                getdate(row.relieving_date) if row.relieving_date else None) for row in people]
    ends = rules.month_ends(today)
    series = rules.headcount_series(history, ends)
    on_site = _on_site(names, today)
    return {
        "greeting": rules.greeting(now_datetime().hour),
        "first_name": frappe.db.get_value("User", frappe.session.user, "first_name") or frappe.session.user,
        "today": str(today),
        "branch": branch,
        "branches": frappe.get_list("Branch", pluck="name", order_by="name asc", limit_page_length=0),
        "kpis": {
            "employees": len(active),
            "joined_this_month": rules.joined_between(history, today.replace(day=1), today),
            "on_site": on_site,
            "on_site_percent": rules.percent(on_site, len(active)),
            "on_leave": _on_leave(names, today),
            "turnover": rules.turnover(history, today),
        },
        "headcount": {"months": [str(end) for end in ends], "values": series},
        "attendance": _attendance(names, today),
        "appraisals": _appraisals(names, today),
        "employment": rules.tally([row.employment_type for row in active]),
        "tasks": _tasks(),
    }


def _on_site(names, today):
    """Who has clocked in today; where nobody has, who is marked present."""
    clocked = frappe.get_all("Employee Checkin", filters={"employee": ["in", names], "time": [">=", str(today)]},
                             pluck="employee")
    if clocked:
        return len(set(clocked))
    return len(set(frappe.get_all("Attendance", filters={
        "employee": ["in", names], "attendance_date": today, "docstatus": 1, "status": ["in", list(rules.PRESENT)]},
        pluck="employee")))


def _on_leave(names, today):
    """Who is on approved leave today."""
    return len(set(frappe.get_all("Leave Application", filters={
        "employee": ["in", names], "docstatus": 1, "status": "Approved",
        "from_date": ["<=", today], "to_date": [">=", today]}, pluck="employee")))


def _attendance(names, today):
    """The last days with attendance marked, each as the chart stacks it."""
    rows = frappe.get_all("Attendance", filters={
        "employee": ["in", names], "docstatus": 1, "attendance_date": [">=", add_days(today, -ATTENDANCE_LOOKBACK)]},
        fields=["attendance_date", "status", "late_entry"], limit_page_length=0)
    marked = [(getdate(row.attendance_date), row.status, row.late_entry) for row in rows]
    days = rules.recent_days([day for day, _status, _late in marked], today)
    return [dict(row, date=str(row["date"])) for row in rules.attendance_days(marked, days)]


def _appraisals(names, today):
    """The latest appraisal cycle that has begun, and how far it has got."""
    cycle = frappe.get_all("Appraisal Cycle", filters={"start_date": ["<=", today]}, fields=["name", "cycle_name"],
                           order_by="start_date desc", limit=1)
    if not cycle:
        return None
    rows = frappe.get_all("Appraisal", filters={"appraisal_cycle": cycle[0].name, "employee": ["in", names],
                                                "docstatus": ["!=", 2]},
                          fields=["docstatus", "custom_total_score", "custom_band"], limit_page_length=0)
    summary = rules.appraisal_summary([(row.docstatus, row.custom_total_score, row.custom_band) for row in rows])
    summary["cycle"] = cycle[0].cycle_name or cycle[0].name
    return summary


def _tasks():
    """The user's own assignments, the most pressing first, as My Alerts has them."""
    found = alerts.my_alerts(limit=40)["alerts"]
    tasks = [alert for alert in found if alert.get("kind") == alerts.rules.ASSIGNMENT]
    return [dict(task, ring=rules.task_ring(task.get("urgency"))) for task in tasks[:TASKS_SHOWN]]
