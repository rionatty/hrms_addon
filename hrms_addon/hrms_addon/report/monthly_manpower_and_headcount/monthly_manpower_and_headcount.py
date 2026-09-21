# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Monthly Manpower and Headcount (Dashboards & Reports, case 3): the
report that replaces the manual extract.

Per plant and department: how many were there at the start of the month,
who joined, who left, how many are there now, and what the establishment
costs. The wage bill is read from the salary structure assignments in
force, not from a payroll run, so the report answers before a run as well
as after one — and so it is not payroll's to produce.

It reads through Frappe's permissions, so a branch's HR Officer sees that
branch's people.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate, today

from hrms_addon.hrms_addon import attendance_rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    opens, closes = _window(filters)
    conditions = {}
    for field in ("company", "branch", "department", "employment_type"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    employees = frappe.get_list(
        "Employee", filters=conditions,
        fields=["name", "branch", "department", "employment_type", "grade", "status",
                "date_of_joining", "relieving_date"],
        limit_page_length=0)
    bases = _bases([row.name for row in employees], closes)

    groups = {}
    for employee in employees:
        joined = getdate(employee.date_of_joining) if employee.date_of_joining else None
        left = getdate(employee.relieving_date) if employee.relieving_date else None
        if joined and joined > closes:
            continue  # not yet with Luuka in this month
        key = (employee.branch or _("No Plant"), employee.department or _("No Department"))
        row = groups.setdefault(key, {
            "branch": key[0], "department": key[1], "opening": 0, "joined": 0, "left": 0,
            "closing": 0, "wage_bill": 0.0, "unpriced": 0})
        here_at_open = bool(joined and joined < opens) and not (left and left < opens)
        joined_now = bool(joined and opens <= joined <= closes)
        left_now = bool(left and opens <= left <= closes)
        here_at_close = bool(joined and joined <= closes) and not (left and left <= closes)
        row["opening"] += 1 if here_at_open else 0
        row["joined"] += 1 if joined_now else 0
        row["left"] += 1 if left_now else 0
        row["closing"] += 1 if here_at_close else 0
        if here_at_close:
            base = flt(bases.get(employee.name))
            row["wage_bill"] += base
            row["unpriced"] += 0 if base else 1

    rows = sorted(groups.values(), key=lambda row: (str(row["branch"]), str(row["department"])))
    for row in rows:
        row["movement"] = row["joined"] - row["left"]
        row["average_wage"] = round(row["wage_bill"] / row["closing"], 2) if row["closing"] else 0
    return columns(), rows


def _window(filters):
    """The month the report covers. Luuka's own cycle runs the 26th to the
    25th, so the report offers both and says which it used."""
    if filters.get("use_attendance_cycle"):
        year = int(filters.get("year") or getdate(today()).year)
        month = int(filters.get("month") or getdate(today()).month)
        opens, closes = attendance_rules.cycle_window(year, month)
        return getdate(opens), getdate(closes)
    day = getdate("%s-%02d-01" % (filters.get("year") or getdate(today()).year,
                                  int(filters.get("month") or getdate(today()).month)))
    return getdate(get_first_day(day)), getdate(get_last_day(day))


def _bases(employees, on):
    """Each employee's monthly base, from the assignment in force."""
    if not employees:
        return {}
    rows = frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": ["in", employees], "docstatus": 1, "from_date": ["<=", on]},
        fields=["employee", "base", "from_date"], order_by="from_date asc", limit=20000)
    out = {}
    for row in rows:
        out[row.employee] = flt(row.base)  # later rows supersede earlier ones
    return out


def columns():
    return [
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Data", "width": 140},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Data",
         "width": 180},
        {"label": _("Opening"), "fieldname": "opening", "fieldtype": "Int", "width": 90},
        {"label": _("Joined"), "fieldname": "joined", "fieldtype": "Int", "width": 90},
        {"label": _("Left"), "fieldname": "left", "fieldtype": "Int", "width": 90},
        {"label": _("Movement"), "fieldname": "movement", "fieldtype": "Int", "width": 100},
        {"label": _("Closing"), "fieldname": "closing", "fieldtype": "Int", "width": 90},
        {"label": _("Wage Bill"), "fieldname": "wage_bill", "fieldtype": "Currency",
         "width": 150},
        {"label": _("Average Wage"), "fieldname": "average_wage", "fieldtype": "Currency",
         "width": 140},
        {"label": _("No Salary on Record"), "fieldname": "unpriced", "fieldtype": "Int",
         "width": 150},
    ]
