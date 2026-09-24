# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How the year's approved leave plans were kept to, by department: leave
taken, applied for, not applied for, still to come, and moved."""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import leave_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    year = cint(filters.get("year")) or getdate().year
    plans = frappe.get_all("Annual Leave Plan", filters=dict({"docstatus": 1, "year": year},
                                                            **({"branch": filters.branch} if filters.get("branch")
                                                               else {})),
                           pluck="name")
    rows = frappe.get_all("Annual Leave Plan Employee",
                          filters={"parent": ["in", plans], "parenttype": "Annual Leave Plan"},
                          fields=["department", "planned_from", "leave_application", "original_from"]) if plans else []
    applications = {row.name: row for row in frappe.get_all(
        "Leave Application", filters={"name": ["in", [row.leave_application for row in rows
                                                      if row.leave_application] or [""]]},
        fields=["name", "docstatus", "status", "to_date"])}
    counts = rules.adherence([{
        "department": row.department,
        "leave_status": rules.plan_row_status(row.planned_from, today(), applications.get(row.leave_application)),
        "moved": bool(row.original_from)} for row in rows])
    data = []
    for department, count in sorted(counts.items()):
        data.append({"department": department, "planned": count["planned"], "taken": count[rules.TAKEN],
                     "applied": count[rules.APPLIED], "not_applied": count[rules.NOT_APPLIED],
                     "to_come": count[rules.PLANNED], "moved": count["moved"],
                     "taken_percent": round(100.0 * count[rules.TAKEN] / count["planned"]) if count["planned"] else 0})
    return columns(), data


def columns():
    return [
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 180},
        {"fieldname": "planned", "label": _("Planned"), "fieldtype": "Int", "width": 90},
        {"fieldname": "taken", "label": _("Taken"), "fieldtype": "Int", "width": 90},
        {"fieldname": "applied", "label": _("Applied For"), "fieldtype": "Int", "width": 100},
        {"fieldname": "not_applied", "label": _("Not Applied"), "fieldtype": "Int", "width": 100},
        {"fieldname": "to_come", "label": _("Still to Come"), "fieldtype": "Int", "width": 110},
        {"fieldname": "moved", "label": _("Moved"), "fieldtype": "Int", "width": 90},
        {"fieldname": "taken_percent", "label": _("Taken %"), "fieldtype": "Percent", "width": 90},
    ]
