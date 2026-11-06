# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Overtime Register (Luuka, 5 Nov 2026: "Provide a provision for overtime
filtering on the payroll dashboard"): every employee on an overtime request in
the dates, with the hours asked, what the clock showed, the hours paid and what
they came to, filtered by plant, department, Overtime Type, day, status and
employee. The dates are the current attendance cycle, the 26th to the 25th,
until others are picked. Requests are read as the user may read them, so a
plant's HR Officer sees their plant's."""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import attendance_rules, overtime_rules as rules

REQUEST, LINE = "Overtime Request", "Overtime Request Employee"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = window(filters)
    conditions = {"overtime_date": ["between", [str(start), str(end)]]}
    for key in ("company", "branch"):
        if filters.get(key):
            conditions[key] = filters[key]
    conditions["status"] = filters.status if filters.get("status") else ["not in", list(rules.LEFT_OUT)]
    requests = {row.name: row for row in frappe.get_list(
        REQUEST, filters=conditions, fields=["name", "overtime_date", "status", "branch"], limit_page_length=0)}
    lines = []
    if requests:
        wanted = {"parenttype": REQUEST, "parent": ["in", list(requests)]}
        for key in ("employee", "overtime_type", "day_kind"):
            if filters.get(key):
                wanted[key] = filters[key]
        lines = frappe.get_all(LINE, filters=wanted, limit_page_length=0, fields=[
            "parent", "employee", "employee_name", "hours", "overtime_type", "hourly_rate", "multiplier", "amount",
            "day_kind", "worked_hours", "clocked", "payable_hours"])
    departments = _departments({line.employee for line in lines})
    found = []
    for line in lines:
        department = departments.get(line.employee)
        if filters.get("department") and department != filters.department:
            continue
        request = requests[line.parent]
        found.append(dict(line, request=line.parent, overtime_date=request.overtime_date, status=request.status,
                          branch=request.branch, department=department))
    rows = rules.register_rows(found)
    currency = frappe.get_cached_value("Company", filters.company, "default_currency") if filters.get("company") else None
    return columns(), rows, None, rules.register_chart(rows), rules.register_summary(rows, currency)


def window(filters):
    """The dates asked for, else the attendance cycle today falls in."""
    start, end = attendance_rules.cycle_window(*attendance_rules.cycle_of(today()))
    return (getdate(filters.get("from_date")) if filters.get("from_date") else start,
            getdate(filters.get("to_date")) if filters.get("to_date") else end)


def _departments(employees):
    """{employee: their department}: a request's lines may be from another department than its own."""
    names = sorted(filter(None, employees))
    if not names:
        return {}
    return {row.name: row.department for row in frappe.get_all(
        "Employee", filters={"name": ["in", names]}, fields=["name", "department"], limit_page_length=0)}


def columns():
    return [
        {"fieldname": "overtime_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 115},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 100},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "day_kind", "label": _("Day"), "fieldtype": "Data", "width": 105},
        {"fieldname": "overtime_type", "label": _("Overtime Type"), "fieldtype": "Link", "options": "Overtime Type",
         "width": 140},
        {"fieldname": "multiplier", "label": _("Rate (x)"), "fieldtype": "Float", "width": 70},
        {"fieldname": "hours", "label": _("Hours Asked"), "fieldtype": "Float", "width": 90},
        {"fieldname": "worked_hours", "label": _("By the Clock"), "fieldtype": "Float", "width": 90},
        {"fieldname": "payable_hours", "label": _("Hours Paid"), "fieldtype": "Float", "width": 85},
        {"fieldname": "hourly_rate", "label": _("Hourly Rate"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "amount", "label": _("Cost Asked"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "paid_amount", "label": _("Paid"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "request", "label": _("Request"), "fieldtype": "Link", "options": "Overtime Request",
         "width": 150},
    ]
