# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Graduate Trainee Progress (test cases 16 to 20): each trainee, the
stage they are at, their rotations done, their milestones passed and their
average, and the milestone they are working towards — those overdue first."""

import frappe
from frappe import _
from frappe.utils import getdate, today


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["<", 2]}
    if filters.get("cohort"):
        conditions["cohort"] = filters.cohort
    if filters.get("branch"):
        conditions["home_branch"] = filters.branch
    trainees = frappe.get_list("Graduate Trainee Program", filters=conditions, fields=[
        "name", "trainee_name", "cohort", "workflow_state", "mentor_name", "home_branch", "start_date", "end_date",
        "milestones_passed", "average_score", "employee"], limit_page_length=0)
    names = [row.name for row in trainees]
    rotations, due = {}, {}
    for row in frappe.get_all("Trainee Rotation", filters={"parent": ["in", names],
                                                            "parenttype": "Graduate Trainee Program"},
                              fields=["parent", "completed"], limit=0) if names else []:
        counts = rotations.setdefault(row.parent, [0, 0])
        counts[1] += 1
        counts[0] += 1 if row.completed else 0
    for row in frappe.get_all("Trainee Milestone", filters={"parent": ["in", names],
                                                             "parenttype": "Graduate Trainee Program",
                                                             "result": ["in", ("", None)]},
                              fields=["parent", "milestone", "due_on"], order_by="due_on asc", limit=0) \
            if names else []:
        due.setdefault(row.parent, row)
    now = getdate(today())
    rows = []
    for row in trainees:
        done, total = rotations.get(row.name, [0, 0])
        upcoming = due.get(row.name)
        rows.append(dict(row, rotations_done=done, rotations=total,
                         next_milestone=upcoming.milestone if upcoming else None,
                         next_due=upcoming.due_on if upcoming else None,
                         overdue=1 if upcoming and upcoming.due_on and getdate(upcoming.due_on) < now else 0))
    rows.sort(key=lambda row: (-row["overdue"], str(row.get("next_due") or "9999"), str(row.get("trainee_name") or "")))
    summary = [
        {"value": len([row for row in rows if row.get("workflow_state") not in ("Confirmed", "Exited")]),
         "label": _("In the programme"), "datatype": "Int", "indicator": "Blue"},
        {"value": len([row for row in rows if row.get("workflow_state") == "Confirmed"]), "label": _("Confirmed"),
         "datatype": "Int", "indicator": "Green"},
        {"value": len([row for row in rows if row.get("overdue")]), "label": _("Milestones overdue"), "datatype": "Int",
         "indicator": "Red"},
    ]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Trainee"), "fieldname": "name", "fieldtype": "Link", "options": "Graduate Trainee Program",
         "width": 140},
        {"label": _("Name"), "fieldname": "trainee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Cohort"), "fieldname": "cohort", "fieldtype": "Data", "width": 160},
        {"label": _("Stage"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 130},
        {"label": _("Mentor"), "fieldname": "mentor_name", "fieldtype": "Data", "width": 150},
        {"label": _("Plant"), "fieldname": "home_branch", "fieldtype": "Link", "options": "Branch", "width": 100},
        {"label": _("Started"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
        {"label": _("Ends"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
        {"label": _("Rotations Done"), "fieldname": "rotations_done", "fieldtype": "Int", "width": 110},
        {"label": _("Rotations"), "fieldname": "rotations", "fieldtype": "Int", "width": 85},
        {"label": _("Milestones Passed"), "fieldname": "milestones_passed", "fieldtype": "Int", "width": 125},
        {"label": _("Average Score"), "fieldname": "average_score", "fieldtype": "Float", "width": 110},
        {"label": _("Next Milestone"), "fieldname": "next_milestone", "fieldtype": "Data", "width": 140},
        {"label": _("Due"), "fieldname": "next_due", "fieldtype": "Date", "width": 100},
        {"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Check", "width": 80},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
    ]
