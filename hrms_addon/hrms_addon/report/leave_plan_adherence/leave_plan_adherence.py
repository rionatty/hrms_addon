# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How the year's approved leave plans were kept to, by department: leave
taken, applied for, not applied for, still to come, and moved; and the days
planned beside the annual leave its people have earned so far
(leave_accrual.py)."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import leave_accrual, leave_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    year = cint(filters.get("year")) or getdate().year
    plans = frappe.get_all("Annual Leave Plan", filters=dict({"docstatus": 1, "year": str(year)},
                                                            **({"branch": filters.branch} if filters.get("branch")
                                                               else {})),
                           pluck="name")
    rows = frappe.get_all("Annual Leave Plan Employee",
                          filters={"parent": ["in", plans], "parenttype": "Annual Leave Plan"},
                          fields=["department", "employee", "planned_from", "planned_days", "leave_application",
                                  "original_from"]) if plans else []
    applications = {row.name: row for row in frappe.get_all(
        "Leave Application", filters={"name": ["in", [row.leave_application for row in rows
                                                      if row.leave_application] or [""]]},
        fields=["name", "docstatus", "status", "to_date"])}
    counts = rules.adherence([{
        "department": row.department,
        "leave_status": rules.plan_row_status(row.planned_from, today(), applications.get(row.leave_application)),
        "moved": bool(row.original_from)} for row in rows])
    start, end = rules.year_window(year)
    earned = leave_accrual.earned_for([row.employee for row in rows], rules.ANNUAL,
                                      min(max(getdate(today()), start), end))
    planned_days, earned_days, counted = {}, {}, set()
    for row in rows:
        key = row.department or ""
        planned_days[key] = planned_days.get(key, 0.0) + flt(row.planned_days)
        found = earned.get(row.employee)
        if found and (key, row.employee) not in counted:
            counted.add((key, row.employee))
            earned_days[key] = earned_days.get(key, 0.0) + flt(found.earned)
    data = []
    for department, count in sorted(counts.items()):
        data.append({"department": department, "planned": count["planned"], "taken": count[rules.TAKEN],
                     "applied": count[rules.APPLIED], "not_applied": count[rules.NOT_APPLIED],
                     "to_come": count[rules.PLANNED], "moved": count["moved"],
                     "taken_percent": round(100.0 * count[rules.TAKEN] / count["planned"]) if count["planned"] else 0,
                     "days_planned": round(planned_days.get(department, 0.0), 2),
                     "days_earned": round(earned_days.get(department, 0.0), 2) if earned else None})
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
        {"fieldname": "days_planned", "label": _("Days Planned"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "days_earned", "label": _("Days Earned So Far"), "fieldtype": "Float", "precision": 2,
         "width": 140},
    ]
