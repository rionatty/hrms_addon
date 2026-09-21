# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Document Expiry (Alerts, Documents & Notifications): every document an
employee holds that has run out or is about to, soonest first, and every
mandatory document nobody is holding at all.

It reads through Frappe's permissions, so a branch's HR Officer sees that
branch's people.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import document_rules as rules

ORDER = {rules.EXPIRED: 0, rules.MISSING: 1, rules.EXPIRING: 2, rules.VALID: 3}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    day = getdate(today())
    conditions = {"status": filters.employee_status or "Active"}
    for field in ("company", "branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    employees = frappe.get_list(
        "Employee", filters=conditions,
        fields=["name", "employee_name", "branch", "department", "designation",
                "custom_is_foreign", "custom_drives", "custom_operates_machinery"],
        limit_page_length=0)
    if not employees:
        return columns(), []
    policy = {row.name: dict(row) for row in frappe.get_all(
        "Employee Document Type", fields=["name", "applies_to", "expires", "notice_days",
                                          "mandatory", "enabled"], limit=200)}
    held = {}
    for row in frappe.get_all(
            "Employee Document",
            filters={"parenttype": "Employee",
                     "parent": ["in", [employee.name for employee in employees]]},
            fields=["parent", "document_type", "number", "issued_on", "expires_on", "status",
                    "alerted_at"], limit=20000):
        held.setdefault(row.parent, []).append(row)

    rows = []
    for employee in employees:
        facts = {"is_foreign": employee.custom_is_foreign, "drives": employee.custom_drives,
                 "operates_machinery": employee.custom_operates_machinery}
        mine = held.get(employee.name, [])
        for row in mine:
            kind = policy.get(row.document_type, {})
            status = rules.status_of(row.expires_on, day,
                                     kind.get("notice_days") or rules.DEFAULT_NOTICE_DAYS,
                                     row.number)
            if filters.get("expiring_only") and status == rules.VALID:
                continue
            rows.append(_row(employee, row.document_type, row.number, row.expires_on, status,
                             day))
        if filters.get("skip_missing"):
            continue
        numbers = {row.document_type: row.number for row in mine if row.number}
        wanted = [(name, kind["applies_to"]) for name, kind in policy.items()
                  if kind.get("mandatory") and kind.get("enabled")
                  and rules.required_for(kind.get("applies_to"), facts)]
        for name in rules.missing(wanted, numbers):
            rows.append(_row(employee, name, None, None, rules.MISSING, day))
    rows.sort(key=lambda row: (ORDER.get(row["status"], 9),
                               str(row["expires_on"] or "9999-99-99"),
                               str(row["employee_name"] or "")))
    return columns(), rows


def _row(employee, document_type, number, expires_on, status, day):
    return {
        "employee": employee.name, "employee_name": employee.employee_name,
        "branch": employee.branch, "department": employee.department,
        "designation": employee.designation, "document_type": document_type,
        "number": number, "expires_on": expires_on, "status": status,
        "days_left": rules.days_left(expires_on, day) if expires_on else None,
    }


def columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link",
         "options": "Employee", "width": 120},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch",
         "width": 110},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link",
         "options": "Department", "width": 150},
        {"label": _("Document"), "fieldname": "document_type", "fieldtype": "Link",
         "options": "Employee Document Type", "width": 190},
        {"label": _("Number"), "fieldname": "number", "fieldtype": "Data", "width": 150},
        {"label": _("Runs Out"), "fieldname": "expires_on", "fieldtype": "Date", "width": 110},
        {"label": _("Days Left"), "fieldname": "days_left", "fieldtype": "Int", "width": 90},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]
