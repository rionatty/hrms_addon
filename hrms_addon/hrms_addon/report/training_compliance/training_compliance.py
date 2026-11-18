# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Compliance (LMS blueprint section 23, the compliance and
mandatory training reports): one row per employee, with what the rules
require of them, how much is done, what is due soon or overdue, their
certificates that have run out, their light and their Training & Competency
Score, worked out as their Learning Passport works it out.

It reads through Frappe's permissions, so a plant's HR Officer sees that
plant.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import competency, learning, learning_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    s, day = learning.settings(), getdate(today())
    conditions = {"status": ["!=", rules.NOT_APPLICABLE]}
    for field in ("company", "branch", "department", "work_section", "designation", "training_category"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    if filters.get("mandatory_only"):
        conditions["training_category"] = ["in", frappe.get_all("Training Category", filters={"mandatory": 1},
                                                                pluck="name") or [""]]
    rows = frappe.get_list("Employee Training Requirement", filters=conditions,
                           fields=["employee", "employee_name", "branch", "department", "designation", "status",
                                   "requirement_type", "completed_on", "valid_until"], limit_page_length=0)
    people = {}
    for row in rows:
        people.setdefault(row.employee, []).append(row)
    expired = {}
    if people:
        for cert in frappe.get_all("Employee Certification",
                                   filters={"employee": ["in", list(people)], "status": rules.EXPIRED},
                                   fields=["employee"], limit_page_length=0):
            expired[cert.employee] = expired.get(cert.employee, 0) + 1
    marks = learning.assessment_averages(list(people), day)
    skills = competency.scores_for(list(people))
    data = []
    for employee, mine in people.items():
        figures = rules.summary(mine, day, s, assessment=marks.get(employee), competency=skills.get(employee))
        if filters.get("light") and figures["light"] != filters.get("light"):
            continue
        first = mine[0]
        data.append({
            "employee": employee, "employee_name": first.employee_name, "branch": first.branch,
            "department": first.department, "designation": first.designation, "required": figures["required"],
            "done": figures["done"], "coverage": figures["coverage"], "due_soon": figures["due_soon"],
            "overdue": figures["overdue"], "expired_certificates": expired.get(employee, 0),
            "assessment": marks.get(employee), "competency": skills.get(employee), "score": figures["score"],
            "light": figures["light"],
        })
    order = {rules.OVERDUE: 0, rules.DUE_SOON: 1, rules.COMPLIANT: 2, rules.NOT_APPLICABLE: 3}
    data.sort(key=lambda row: (order.get(row["light"], 4), row["coverage"] if row["coverage"] is not None else 101,
                               row["employee_name"] or ""))
    return columns(), data


def columns():
    return [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "designation", "label": _("Job Title"), "fieldtype": "Link", "options": "Designation",
         "width": 140},
        {"fieldname": "light", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "required", "label": _("Required"), "fieldtype": "Int", "width": 85},
        {"fieldname": "done", "label": _("Done"), "fieldtype": "Int", "width": 70},
        {"fieldname": "coverage", "label": _("Done %"), "fieldtype": "Percent", "width": 85},
        {"fieldname": "due_soon", "label": _("Due Soon"), "fieldtype": "Int", "width": 85},
        {"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Int", "width": 80},
        {"fieldname": "expired_certificates", "label": _("Certificates Run Out"), "fieldtype": "Int", "width": 100},
        {"fieldname": "assessment", "label": _("Assessments %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "competency", "label": _("Competency %"), "fieldtype": "Percent", "width": 105},
        {"fieldname": "score", "label": _("Score"), "fieldtype": "Int", "width": 70},
    ]
