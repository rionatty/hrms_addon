# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Session Attendance (LMS blueprint, section 4.4; the brief's section 9): who
was invited to each session, who registered and came, who was late, excused or
a no-show, the attendance, no-show and completion rates and the training
hours; session by session, or by employee, department or plant. Read from the
day rows of Training Attendance; a session from before them, from Frappe HR's
own Present and Absent. The FRM03 attendance form is the session's own print,
and the report exports to Excel as it stands.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import learning_attendance_rules as att, learning_rules

VIEWS = ("Session", "Employee", "Department", "Plant")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    events = sessions(filters)
    names = [event.name for event in events] or [""]
    day_rows = frappe.get_all("Training Attendance", filters={"training_event": ["in", names]},
                              fields=["training_event", "employee", "employee_name", "department", "branch",
                                      "status", "hours"], limit_page_length=0)
    marked_here = {row.training_event for row in day_rows}
    legacy = [event.name for event in events if event.name not in marked_here] or [""]
    old_rows = frappe.get_all("Training Event Employee", filters={"parenttype": "Training Event", "parent": ["in", legacy]},
                              fields=["parent", "employee", "employee_name", "department", "attendance"],
                              limit_page_length=0)
    programmes = {row.name: row.custom_duration_hours for row in frappe.get_all(
        "Training Program", filters={"name": ["in", list({event.training_program for event in events
                                                         if event.training_program}) or [""]]},
        fields=["name", "custom_duration_hours"])}
    hours = {event.name: learning_rules.event_hours(event.start_time, event.end_time,
                                                    programmes.get(event.training_program)) for event in events}
    days = {event.name: len(att.session_days(event.start_time, event.end_time)) or 1 for event in events}
    plant = {event.name: event.custom_branch for event in events}
    # every session as day rows: an older one's participants as one day each
    rows = []
    for row in day_rows:
        hours_given = row.hours or (hours[row.training_event] / days[row.training_event] if row.status in att.CAME else 0)
        rows.append(dict(row, hours=hours_given, days=days[row.training_event]))
    for row in old_rows:
        status = att.from_event(row.attendance) or att.INVITED
        rows.append({"training_event": row.parent, "employee": row.employee, "employee_name": row.employee_name,
                     "department": row.department, "branch": plant.get(row.parent), "status": status,
                     "hours": hours[row.parent] if status in att.CAME else 0, "days": 1})
    view = filters.get("view") if filters.get("view") in VIEWS else "Session"
    if view == "Employee":
        return employee_view(rows)
    if view in ("Department", "Plant"):
        return group_view(rows, "department" if view == "Department" else "branch", view)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["training_event"], []).append(row)
    data = []
    for event in events:
        mine = grouped.get(event.name, [])
        found = att.figures(mine)
        data.append(dict(found, event=event.name, programme=event.training_program, branch=event.custom_branch,
                         day=getdate(event.start_time), session_hours=hours[event.name], present=found["attended"],
                         unmarked=found["invited"] - _marked(mine)))
    return session_columns(), data, None, chart(data), summary(data)


def _marked(rows):
    people = {}
    for row in rows:
        people.setdefault(row["employee"], []).append(row["status"])
    return sum(1 for statuses in people.values() if any(status not in att.OPEN for status in statuses))


def sessions(filters):
    """The sessions in the period, through the user's permissions: those held,
    and those still to be held where asked for."""
    conditions = {"docstatus": ["<", 2] if filters.get("include_scheduled") else 1,
                  "event_status": ["!=", "Cancelled"],
                  "start_time": ["between", [str(getdate(filters.get("from_date"))) + " 00:00:00",
                                             str(getdate(filters.get("to_date"))) + " 23:59:59"]]}
    if filters.get("company"):
        conditions["company"] = filters.get("company")
    if filters.get("branch"):
        conditions["custom_branch"] = filters.get("branch")
    if filters.get("training_program"):
        conditions["training_program"] = filters.get("training_program")
    return frappe.get_list("Training Event", filters=conditions, limit_page_length=0, order_by="start_time asc",
                           fields=["name", "event_name", "training_program", "start_time", "end_time",
                                   "custom_branch", "custom_evaluation_score"])


def employee_view(rows):
    people = {}
    for row in rows:
        person = people.setdefault(row["employee"], {"employee": row["employee"],
                                                     "employee_name": row.get("employee_name"),
                                                     "department": row.get("department"), "branch": row.get("branch"),
                                                     "sessions": {}})
        person["sessions"].setdefault(row["training_event"], []).append(row)
    data = []
    for person in people.values():
        found = [att.figures(day_rows) for day_rows in person["sessions"].values()]
        data.append({"employee": person["employee"], "employee_name": person["employee_name"],
                     "department": person["department"], "branch": person["branch"], "invited": len(found),
                     "present": sum(item["attended"] for item in found), "late": sum(item["late"] for item in found),
                     "absent": sum(item["no_show"] for item in found), "excused": sum(item["excused"] for item in found),
                     "hours": round(sum(item["hours"] for item in found), 1)})
    columns = [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 100},
        {"fieldname": "invited", "label": _("Sessions"), "fieldtype": "Int", "width": 80},
        {"fieldname": "present", "label": _("Attended"), "fieldtype": "Int", "width": 80},
        {"fieldname": "late", "label": _("Late"), "fieldtype": "Int", "width": 60},
        {"fieldname": "absent", "label": _("No-Shows"), "fieldtype": "Int", "width": 80},
        {"fieldname": "excused", "label": _("Excused"), "fieldtype": "Int", "width": 70},
        {"fieldname": "hours", "label": _("Training Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
    ]
    data.sort(key=lambda row: (-row["hours"], row["employee_name"] or ""))
    return columns, data


def group_view(rows, field, label):
    """Each department or plant: its people's attendance across the sessions."""
    groups = {}
    for row in rows:
        groups.setdefault(row.get(field) or "", {}).setdefault((row["training_event"], row["employee"]), []).append(row)
    data = []
    for name, people in groups.items():
        found = [att.figures(day_rows) for day_rows in people.values()]
        attended = sum(item["attended"] for item in found)
        no_shows = sum(item["no_show"] for item in found)
        employees = len({employee for _event, employee in people})
        hours = round(sum(item["hours"] for item in found), 1)
        marked = sum(item["marked"] for item in found)
        data.append({"group": name or _("Not Set"), "invited": len(found), "present": attended,
                     "late": sum(item["late"] for item in found), "absent": no_shows,
                     "attendance_rate": round(100.0 * attended / marked, 1) if marked else None,
                     "no_show_rate": round(100.0 * no_shows / marked, 1) if marked else None,
                     "employees": employees, "hours": hours,
                     "hours_per_employee": round(hours / employees, 1) if employees else 0})
    data.sort(key=lambda row: (row["attendance_rate"] is None, row["attendance_rate"] or 0))
    columns = [
        {"fieldname": "group", "label": _(label), "fieldtype": "Data", "width": 170},
        {"fieldname": "employees", "label": _("Employees"), "fieldtype": "Int", "width": 90},
        {"fieldname": "invited", "label": _("Places"), "fieldtype": "Int", "width": 70},
        {"fieldname": "present", "label": _("Attended"), "fieldtype": "Int", "width": 80},
        {"fieldname": "late", "label": _("Late"), "fieldtype": "Int", "width": 60},
        {"fieldname": "absent", "label": _("No-Shows"), "fieldtype": "Int", "width": 80},
        {"fieldname": "attendance_rate", "label": _("Attendance %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "no_show_rate", "label": _("No-Show %"), "fieldtype": "Percent", "width": 95},
        {"fieldname": "hours", "label": _("Training Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "hours_per_employee", "label": _("Hours per Employee"), "fieldtype": "Float", "precision": 1,
         "width": 120},
    ]
    return columns, data, None, None


def session_columns():
    return [
        {"fieldname": "event", "label": _("Session"), "fieldtype": "Link", "options": "Training Event", "width": 160},
        {"fieldname": "programme", "label": _("Training Program"), "fieldtype": "Link",
         "options": "Training Program", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 100},
        {"fieldname": "day", "label": _("Date"), "fieldtype": "Date", "width": 95},
        {"fieldname": "session_hours", "label": _("Hours"), "fieldtype": "Float", "precision": 1, "width": 65},
        {"fieldname": "invited", "label": _("Invited"), "fieldtype": "Int", "width": 70},
        {"fieldname": "registered", "label": _("Registered"), "fieldtype": "Int", "width": 90},
        {"fieldname": "present", "label": _("Attended"), "fieldtype": "Int", "width": 80},
        {"fieldname": "late", "label": _("Late"), "fieldtype": "Int", "width": 60},
        {"fieldname": "excused", "label": _("Excused"), "fieldtype": "Int", "width": 70},
        {"fieldname": "no_show", "label": _("No-Shows"), "fieldtype": "Int", "width": 80},
        {"fieldname": "unmarked", "label": _("Not Marked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "attendance_rate", "label": _("Attendance %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "no_show_rate", "label": _("No-Show %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "completion_rate", "label": _("Completion %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "hours", "label": _("Training Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
    ]


def chart(data):
    shown = [row for row in data if row["invited"]][-12:]
    if not shown:
        return None
    return {"type": "bar", "colors": ["#14395E", "#E8A317"], "height": 240,
            "data": {"labels": [str(row["programme"] or row["event"])[:24] for row in shown],
                     "datasets": [{"name": _("Attendance %"), "values": [row["attendance_rate"] or 0 for row in shown]},
                                  {"name": _("Completion %"), "values": [row["completion_rate"] or 0 for row in shown]}]}}


def summary(data):
    invited = sum(row["invited"] for row in data)
    present = sum(row["present"] for row in data)
    no_shows = sum(row["no_show"] for row in data)
    marked = sum(row.get("marked") or 0 for row in data)
    return [
        {"value": len(data), "label": _("Sessions"), "datatype": "Int"},
        {"value": invited, "label": _("Invited"), "datatype": "Int"},
        {"value": present, "label": _("Attended"), "datatype": "Int"},
        {"value": round(100.0 * present / marked, 1) if marked else 0, "label": _("Attendance %"), "datatype": "Percent"},
        {"value": round(100.0 * no_shows / marked, 1) if marked else 0, "label": _("No-Show %"), "datatype": "Percent"},
        {"value": round(sum(row["hours"] for row in data), 1), "label": _("Training Hours"), "datatype": "Float"},
    ]
