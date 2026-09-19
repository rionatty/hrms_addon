# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Contract Expiry Status: the blueprint's report for the HR Officer (Contract
Management, "Contracts expiry status"). The contracts still running (those
not renewed too, until they end) or ended, soonest end first, with the days
left and the alerts sent. It reads through Frappe's permissions, so a
branch's HR Officer sees that branch's."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from hrms_addon.hrms_addon import contract_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    day = getdate(today())
    conditions = {"docstatus": 1}
    for field in ("company", "branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    conditions["status"] = filters.status if filters.get("status") else [
        "in", [rules.ACTIVE, rules.EXPIRING, rules.EXPIRED, rules.NOT_RENEWED]]
    if cint(filters.get("ending_within")):
        conditions["end_date"] = ["<=", add_days(day, cint(filters.ending_within))]
    rows = frappe.get_list(
        "Employee Contract",
        filters=conditions,
        fields=["name as contract", "employee", "employee_name", "branch", "department", "employment_type", "start_date",
                "end_date", "status", "alerts_sent"],
        order_by="end_date asc",
    )
    for row in rows:
        row.days_left = rules.days_left(row.end_date, day) if row.end_date else None
    return columns(), rows


def columns():
    return [
        {"fieldname": "contract", "label": _("Contract"), "fieldtype": "Link", "options": "Employee Contract", "width": 150},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 150},
        {"fieldname": "employment_type", "label": _("Contract Type"), "fieldtype": "Link", "options": "Employment Type",
         "width": 120},
        {"fieldname": "start_date", "label": _("Start"), "fieldtype": "Date", "width": 100},
        {"fieldname": "end_date", "label": _("End"), "fieldtype": "Date", "width": 100},
        {"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 90},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "alerts_sent", "label": _("Alerts Sent (Days Before)"), "fieldtype": "Data", "width": 150},
    ]
