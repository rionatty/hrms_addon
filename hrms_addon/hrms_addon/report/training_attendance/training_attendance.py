# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Attendance (LMS blueprint, section 4.4): who was invited to each
session, who came, the no-shows and the training hours, session by session or
employee by employee. The FRM03 attendance form is the session's own print.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import learning_delivery_rules as rules, learning_rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    events = sessions(filters)
    names = [event.name for event in events] or [""]
    rows = frappe.get_all("Training Event Employee", filters={"parenttype": "Training Event", "parent": ["in", names]},
                          fields=["parent", "employee", "employee_name", "department", "attendance"])
    programmes = {row.name: row.custom_duration_hours for row in frappe.get_all(
        "Training Program", filters={"name": ["in", list({event.training_program for event in events
                                                         if event.training_program}) or [""]]},
        fields=["name", "custom_duration_hours"])}
    by_event = {}
    for row in rows:
        by_event.setdefault(row.parent, []).append(row)
    hours = {event.name: learning_rules.event_hours(event.start_time, event.end_time,
                                                    programmes.get(event.training_program)) for event in events}
    if filters.get("view") == "Employee":
        return employee_view(events, by_event, hours)
    data = []
    for event in events:
        counted = rules.attendance_of({"employees": by_event.get(event.name, [])}, hours[event.name])
        data.append(dict(counted, event=event.name, programme=event.training_program,
                         day=getdate(event.start_time), session_hours=hours[event.name]))
    return session_columns(), data, None, None, summary(data)


def sessions(filters):
    """The sessions held in the period: submitted, not cancelled, started in it."""
    conditions = {"docstatus": 1, "event_status": ["!=", "Cancelled"],
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


def employee_view(events, by_event, hours):
    people = {}
    for event in events:
        for row in by_event.get(event.name, []):
            person = people.setdefault(row.employee, {"employee": row.employee, "employee_name": row.employee_name,
                                                      "department": row.department, "invited": 0, "present": 0,
                                                      "absent": 0, "hours": 0.0})
            person["invited"] += 1
            if row.attendance == "Present":
                person["present"] += 1
                person["hours"] += hours[event.name]
            elif row.attendance == "Absent":
                person["absent"] += 1
    columns = [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 160},
        {"fieldname": "invited", "label": _("Invited"), "fieldtype": "Int", "width": 80},
        {"fieldname": "present", "label": _("Attended"), "fieldtype": "Int", "width": 80},
        {"fieldname": "absent", "label": _("No-Shows"), "fieldtype": "Int", "width": 80},
        {"fieldname": "hours", "label": _("Training Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
    ]
    data = sorted(people.values(), key=lambda row: (-row["hours"], row["employee_name"] or ""))
    return columns, data


def session_columns():
    return [
        {"fieldname": "event", "label": _("Session"), "fieldtype": "Link", "options": "Training Event", "width": 160},
        {"fieldname": "programme", "label": _("Training Program"), "fieldtype": "Link",
         "options": "Training Program", "width": 180},
        {"fieldname": "day", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "session_hours", "label": _("Hours"), "fieldtype": "Float", "precision": 1, "width": 70},
        {"fieldname": "invited", "label": _("Invited"), "fieldtype": "Int", "width": 70},
        {"fieldname": "present", "label": _("Attended"), "fieldtype": "Int", "width": 80},
        {"fieldname": "absent", "label": _("No-Shows"), "fieldtype": "Int", "width": 80},
        {"fieldname": "unmarked", "label": _("Not Marked"), "fieldtype": "Int", "width": 90},
        {"fieldname": "no_show", "label": _("No-Show %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "hours", "label": _("Training Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
    ]


def summary(data):
    invited = sum(row["invited"] for row in data)
    present = sum(row["present"] for row in data)
    absent = sum(row["absent"] for row in data)
    return [
        {"value": len(data), "label": _("Sessions"), "datatype": "Int"},
        {"value": invited, "label": _("Invited"), "datatype": "Int"},
        {"value": present, "label": _("Attended"), "datatype": "Int"},
        {"value": round(100.0 * absent / (present + absent), 1) if present + absent else 0, "label": _("No-Show %"),
         "datatype": "Float"},
        {"value": round(sum(row["hours"] for row in data), 1), "label": _("Training Hours"), "datatype": "Float"},
    ]
