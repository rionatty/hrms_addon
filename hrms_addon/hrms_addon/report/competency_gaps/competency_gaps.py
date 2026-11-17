# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Competency Gaps: everyone below the level a skill needs of them, missing a
certificate it needs, or due to be assessed again, with how far short they
are and since when.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import competency, competency_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    found = rules.current(competency.counting_rows(filters))
    data = []
    for row in found.values():
        if row.status == rules.COMPETENT:
            continue
        if filters.get("status") and row.status != filters.get("status"):
            continue
        data.append({"employee": row.employee, "employee_name": row.employee_name, "work_section": row.work_section,
                     "skill": row.skill, "critical": row.critical, "level": rules.level_of(row.level),
                     "needed": rules.level_of(row.required_level),
                     "short": max(0, (rules.level_of(row.required_level) or 0) - (rules.level_of(row.level) or 0)),
                     "status": row.status, "assessed_on": row.assessed_on, "next_due": row.next_due,
                     "assessment": row.name})
    data.sort(key=lambda row: (not row["critical"], -row["short"], row["employee_name"] or ""))
    columns = [
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 110},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "work_section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
         "width": 150},
        {"fieldname": "skill", "label": _("Skill"), "fieldtype": "Link", "options": "Skill", "width": 170},
        {"fieldname": "critical", "label": _("Critical"), "fieldtype": "Check", "width": 70},
        {"fieldname": "level", "label": _("Level"), "fieldtype": "Int", "width": 60},
        {"fieldname": "needed", "label": _("Needed"), "fieldtype": "Int", "width": 70},
        {"fieldname": "short", "label": _("Short"), "fieldtype": "Int", "width": 60},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
        {"fieldname": "assessed_on", "label": _("Assessed On"), "fieldtype": "Date", "width": 100},
        {"fieldname": "next_due", "label": _("Reassess By"), "fieldtype": "Date", "width": 100},
        {"fieldname": "assessment", "label": _("Assessment"), "fieldtype": "Link",
         "options": "Competency Assessment", "width": 150},
    ]
    return columns, data
