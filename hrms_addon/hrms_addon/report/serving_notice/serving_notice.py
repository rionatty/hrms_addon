# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Who is serving notice: each exit with its last day, the days of notice
served and left, the days it falls short, and how far the exit has got
(interview, clearance, settlement). The exits are read with the user's own
permissions, so an HR Officer sees their own plant's."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from hrms_addon.hrms_addon import exit_rules as rules, exits

SERVING, RECENT, ALL = "Serving Notice", "Left in the Last 30 Days", "All Open Exits"
RECENT_DAYS = 30
NOT_STARTED = "Not Started"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    return columns(), rows_for(filters)


def rows_for(filters, day=None):
    day = getdate(day or today())
    wanted = {"docstatus": ["<", 2], "custom_relieving_date": ["is", "set"]}
    for field, key in (("company", "company"), ("custom_branch", "branch"), ("department", "department"),
                       ("custom_exit_type", "exit_type")):
        if filters.get(key):
            wanted[field] = filters.get(key)
    show = filters.get("show") or SERVING
    if show == SERVING:
        wanted["custom_relieving_date"] = [">=", day]
    elif show == RECENT:
        wanted["custom_relieving_date"] = ["between", [add_days(day, -RECENT_DAYS), add_days(day, -1)]]
    found = frappe.get_list("Employee Separation", filters=wanted, fields=exits.NOTICE_FIELDS,
                            order_by="custom_relieving_date asc", limit_page_length=0)
    steps = exits.exit_steps(found) if found else {}
    data = []
    for row in found:
        progress = rules.notice_progress(row.custom_notice_given, row.custom_relieving_date, day)
        interview, clearance, settlement, todo = steps[row.name]
        if show == ALL and progress["stage"] == rules.GONE and not todo:
            continue  # left, and nothing of the exit still to do
        data.append({
            "separation": row.name, "employee": row.employee, "employee_name": row.employee_name,
            "branch": row.custom_branch, "department": row.department, "designation": row.designation,
            "exit_type": row.custom_exit_type, "reason": row.custom_reason,
            "notice_given": row.custom_notice_given, "notice_days": cint(row.custom_notice_days),
            "last_day": row.custom_relieving_date, "stage": progress["stage"],
            "days_served": progress["days_served"] if row.custom_notice_given else None,
            "days_left": max(progress["days_left"], 0), "days_short": cint(row.custom_notice_short_days),
            "separation_status": _("Submitted") if row.docstatus == 1 else _("Draft"),
            "interview": interview or (None if row.custom_exit_type == rules.INVOLUNTARY else NOT_STARTED),
            "clearance": clearance or NOT_STARTED, "settlement": settlement or NOT_STARTED,
            "to_do": ", ".join(todo),
        })
    return data


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation",
         "width": 150},
        {"fieldname": "exit_type", "label": _("Exit Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 120},
        {"fieldname": "notice_given", "label": _("Notice Given On"), "fieldtype": "Date", "width": 115},
        {"fieldname": "notice_days", "label": _("Notice Required (days)"), "fieldtype": "Int", "width": 110},
        {"fieldname": "last_day", "label": _("Last Day of Service"), "fieldtype": "Date", "width": 120},
        {"fieldname": "stage", "label": _("Stage"), "fieldtype": "Data", "width": 130},
        {"fieldname": "days_served", "label": _("Days Served"), "fieldtype": "Int", "width": 95},
        {"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 85},
        {"fieldname": "days_short", "label": _("Days Short"), "fieldtype": "Int", "width": 90},
        {"fieldname": "separation_status", "label": _("Separation"), "fieldtype": "Data", "width": 100},
        {"fieldname": "interview", "label": _("Exit Interview"), "fieldtype": "Data", "width": 140},
        {"fieldname": "clearance", "label": _("Clearance Form"), "fieldtype": "Data", "width": 160},
        {"fieldname": "settlement", "label": _("Full and Final Statement"), "fieldtype": "Data", "width": 170},
        {"fieldname": "to_do", "label": _("Still To Do"), "fieldtype": "Data", "width": 260},
        {"fieldname": "separation", "label": _("Employee Separation"), "fieldtype": "Link",
         "options": "Employee Separation", "width": 170},
    ]
