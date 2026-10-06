# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Development Plan Tracker (test cases 1 and 9): every development
plan, how many of its actions are done and how many are past their date,
the training it sent to L&D and what came of it (the sessions booked,
attended and found effective) — the plans most behind first."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["<", 2]}
    for field in ("program_type", "branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    plans = frappe.get_list("Talent Program", filters=conditions, fields=[
        "name", "employee", "employee_name", "program_type", "workflow_state", "start_date", "end_date", "mentor",
        "training_requisition"], limit_page_length=0)
    progress = talent_reports.plan_progress([row.name for row in plans])
    trained = talent_reports.training_progress([row.name for row in plans])
    rows = [dict(row, **progress.get(row.name, {}), **trained.get(row.name, {})) for row in plans]
    rows.sort(key=lambda row: (-(row.get("late") or 0), row.get("share") or 0, str(row.get("employee_name") or "")))
    actions = sum(row.get("actions") or 0 for row in rows)
    done = sum(row.get("done") or 0 for row in rows)
    summary = [
        {"value": len(rows), "label": _("Plans"), "datatype": "Int", "indicator": "Blue"},
        {"value": round(100.0 * done / actions) if actions else 0, "label": _("Actions done"),
         "datatype": "Percent", "indicator": "Green"},
        {"value": sum(row.get("late") or 0 for row in rows), "label": _("Actions past their date"),
         "datatype": "Int", "indicator": "Red"},
        {"value": sum(row.get("attended") or 0 for row in rows), "label": _("Trainings attended"),
         "datatype": "Int", "indicator": "Green"},
    ]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Plan"), "fieldname": "name", "fieldtype": "Link", "options": "Talent Program", "width": 140},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Programme"), "fieldname": "program_type", "fieldtype": "Data", "width": 170},
        {"label": _("Status"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 110},
        {"label": _("Starts"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
        {"label": _("Ends"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
        {"label": _("Actions"), "fieldname": "actions", "fieldtype": "Int", "width": 75},
        {"label": _("Done"), "fieldname": "done", "fieldtype": "Int", "width": 65},
        {"label": _("Past Their Date"), "fieldname": "late", "fieldtype": "Int", "width": 110},
        {"label": _("Done %"), "fieldname": "share", "fieldtype": "Percent", "width": 85},
        {"label": _("Mentor or Coach"), "fieldname": "mentor", "fieldtype": "Link", "options": "Employee",
         "width": 130},
        {"label": _("Sent to L&D"), "fieldname": "training_requisition", "fieldtype": "Link",
         "options": "Training Requisition", "width": 140},
        {"label": _("Trainings"), "fieldname": "trainings", "fieldtype": "Int", "width": 85},
        {"label": _("Attended"), "fieldname": "attended", "fieldtype": "Int", "width": 85},
        {"label": _("Effective"), "fieldname": "effective", "fieldtype": "Int", "width": 85},
    ]
