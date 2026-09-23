# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The salary advances of one run, for Finance: who is paid, how, and to
which account."""

import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.get("salary_advance_processing"):
        return columns(), []
    frappe.has_permission("Salary Advance Processing", "read", filters.salary_advance_processing, throw=True)
    conditions = {"parent": filters.salary_advance_processing, "parenttype": "Salary Advance Processing",
                  "include": 1, "qualifies": 1}
    if filters.get("salary_mode"):
        conditions["salary_mode"] = filters.salary_mode
    rows = frappe.get_all("Salary Advance Processing Employee", filters=conditions,
                          fields=["employee", "employee_name", "branch", "department", "salary_mode", "bank_name",
                                  "bank_ac_no", "amount", "employee_advance"],
                          order_by="salary_mode asc, employee_name asc")
    return columns(), rows


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee",
         "width": 130},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 120},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 150},
        {"fieldname": "salary_mode", "label": _("Salary Mode"), "fieldtype": "Data", "width": 100},
        {"fieldname": "bank_name", "label": _("Bank"), "fieldtype": "Data", "width": 130},
        {"fieldname": "bank_ac_no", "label": _("Account No"), "fieldtype": "Data", "width": 150},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "employee_advance", "label": _("Employee Advance"), "fieldtype": "Link",
         "options": "Employee Advance", "width": 150},
    ]
