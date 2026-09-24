# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The year's approved leave plans, month by month, as the employees are
shown them. HR, heads of department and supervisors see every plant and
department; an employee sees their own."""

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date, getdate

from hrms_addon.hrms_addon import leave, leave_rules as rules

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    year = cint(filters.get("year")) or getdate().year
    branch, department = filters.get("branch"), filters.get("department")
    own = leave.own_place(frappe.session.user)
    if own is not None:
        if not own:
            return columns(), []
        branch, department = own.branch, own.department
    return columns(), rows_for(year, branch, department)


def rows_for(year, branch=None, department=None):
    plans = frappe.get_all("Annual Leave Plan", filters=dict({"docstatus": 1, "year": year},
                                                            **({"branch": branch} if branch else {})),
                           pluck="name")
    if not plans:
        return []
    conditions = {"parent": ["in", plans], "parenttype": "Annual Leave Plan"}
    if department:
        conditions["department"] = department
    start, end = rules.year_window(year)
    include = leave.annual_counts_holidays()
    out = {}
    for row in frappe.get_all("Annual Leave Plan Employee", filters=conditions,
                              fields=["employee", "employee_name", "department", "planned_from", "planned_to",
                                      "planned_days"],
                              order_by="employee_name asc, planned_from asc"):
        entry = out.get(row.employee)
        if entry is None:
            entry = out[row.employee] = dict({"employee": row.employee, "employee_name": row.employee_name,
                                              "department": row.department, "dates": [], "total": 0.0,
                                              "holidays": leave.holidays_between(row.employee, start, end)},
                                             **{month: 0.0 for month in MONTHS})
        for month, days in rules.month_days(row.planned_from, row.planned_to, year, entry["holidays"],
                                            include).items():
            entry[MONTHS[month - 1]] += days
        entry["total"] += flt(row.planned_days)
        entry["dates"].append(_("{0} to {1}").format(format_date(row.planned_from, "d MMM"),
                                                     format_date(row.planned_to, "d MMM")))
    data = []
    for entry in out.values():
        entry.pop("holidays")
        entry["dates"] = "; ".join(entry["dates"])
        data.append(entry)
    return data


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "dates", "label": _("Planned Dates"), "fieldtype": "Data", "width": 200},
        *({"fieldname": month, "label": _(month.capitalize()), "fieldtype": "Float", "precision": 1, "width": 60}
          for month in MONTHS),
        {"fieldname": "total", "label": _("Total"), "fieldtype": "Float", "precision": 1, "width": 70},
    ]
