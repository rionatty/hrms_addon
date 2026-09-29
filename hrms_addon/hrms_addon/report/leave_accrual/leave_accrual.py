# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What each employee has earned of a leave type by a day, from the days
worked, and what they can still take (leave_accrual.py). HR, heads of
department and supervisors see everyone the filters give; an employee sees
their own."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import leave, leave_accrual


def execute(filters=None):
    filters = frappe._dict(filters or {})
    types = leave_accrual.earning_types()
    leave_type = filters.get("leave_type") or (types[0] if types else None)
    if not leave_type or leave_type not in types:
        return columns(), [], _("Only a leave type set as Earned Leave accrues.")
    on = getdate(filters.get("date") or today())
    conditions = {"status": "Active"}
    for key in ("company", "branch", "department"):
        if filters.get(key):
            conditions[key] = filters[key]
    if filters.get("employee"):
        conditions["name"] = filters.employee
    if leave.own_place(frappe.session.user) is not None:
        mine = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        if not mine:
            return columns(), []
        conditions["name"] = mine
    people = frappe.get_all("Employee", filters=conditions, fields=["name", "employee_name", "department", "branch"],
                            order_by="employee_name asc", limit_page_length=0)
    found = leave_accrual.earned_for([person.name for person in people], leave_type, on)
    data = []
    for person in people:
        row = found.get(person.name)
        if not row:
            continue
        data.append({"employee": person.name, "employee_name": person.employee_name, "department": person.department,
                     "branch": person.branch, "leave_type": leave_type, "per_year": round(row.per_year, 2),
                     "days_worked": row.days_worked, "days_off": row.days_off, "earned": row.earned,
                     "brought_forward": row.carried, "taken": row.taken, "pending": row.pending,
                     "available": row.available})
    return columns(), data


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "leave_type", "label": _("Leave Type"), "fieldtype": "Link", "options": "Leave Type",
         "width": 120},
        {"fieldname": "per_year", "label": _("Days a Year"), "fieldtype": "Float", "precision": 2, "width": 100},
        {"fieldname": "days_worked", "label": _("Days Worked"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "days_off", "label": _("Days Not Worked"), "fieldtype": "Float", "precision": 1, "width": 130},
        {"fieldname": "earned", "label": _("Earned"), "fieldtype": "Float", "precision": 2, "width": 90},
        {"fieldname": "brought_forward", "label": _("Brought Forward"), "fieldtype": "Float", "precision": 2,
         "width": 130},
        {"fieldname": "taken", "label": _("Taken"), "fieldtype": "Float", "precision": 2, "width": 90},
        {"fieldname": "pending", "label": _("Waiting Approval"), "fieldtype": "Float", "precision": 2, "width": 130},
        {"fieldname": "available", "label": _("Can Be Taken"), "fieldtype": "Float", "precision": 2, "width": 120},
    ]
