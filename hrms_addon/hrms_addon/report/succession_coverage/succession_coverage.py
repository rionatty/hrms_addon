# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Succession Coverage (test case 15): per critical role, who holds it, what
it would cost to lose them, and who is named to step in, readiest first.

The gaps come first, because a report the council reads at the top is a
report about the roles nobody can fill. It reads through Frappe's
permissions, so a branch's HR Officer sees that branch's roles.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_rules as rules

ORDER = {rules.POSITION_GAP: 0, rules.AT_RISK: 1, rules.COVERED: 2}
RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["<", 2]}
    for field in ("company", "branch", "department", "risk_level", "coverage"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    if filters.get("gaps_only"):
        conditions["gap"] = 1
    if filters.get("single_person_only"):
        conditions["single_person_role"] = 1
    positions = frappe.get_list(
        "Succession Position", filters=conditions,
        fields=["name", "designation", "department", "branch", "incumbent", "incumbent_name",
                "risk_level", "coverage", "gap", "single_person_role", "status", "job_opening",
                "retirement_or_exit_due"],
        limit_page_length=0)
    rows = []
    for position in positions:
        candidates = frappe.get_all(
            "Succession Candidate",
            filters={"parent": position.name, "parenttype": "Succession Position"},
            fields=["employee", "employee_name", "readiness", "development_needs",
                    "training_requisition"], limit=50)
        ordered = rules.readiness_order(candidates)
        counts = rules.bench_strength(candidates)
        rows.append({
            "position": position.name,
            "designation": position.designation,
            "department": position.department,
            "branch": position.branch,
            "incumbent": position.incumbent,
            "incumbent_name": position.incumbent_name,
            "single_person_role": position.single_person_role,
            "risk_level": position.risk_level,
            "coverage": position.coverage,
            "ready_now": counts[rules.READY_NOW],
            "ready_soon": counts[rules.READY_SOON],
            "emerging": counts[rules.EMERGING],
            "successors": ", ".join(
                "%s (%s)" % (row.get("employee_name") or row.get("employee"), row.get("readiness"))
                for row in ordered) or None,
            "development_needs": "; ".join(
                need["needs"] for need in rules.development_needs(candidates)) or None,
            "job_opening": position.job_opening,
            "exit_due": position.retirement_or_exit_due,
            "status": position.status,
        })
    rows.sort(key=lambda row: (ORDER.get(row["coverage"], 3),
                               RISK_ORDER.get(row["risk_level"], 3),
                               str(row["designation"] or "")))
    return columns(), rows


def columns():
    return [
        {"label": _("Role"), "fieldname": "designation", "fieldtype": "Link",
         "options": "Designation", "width": 180},
        {"label": _("Position"), "fieldname": "position", "fieldtype": "Link",
         "options": "Succession Position", "width": 130},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link",
         "options": "Department", "width": 140},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch",
         "width": 110},
        {"label": _("Incumbent"), "fieldname": "incumbent_name", "fieldtype": "Data",
         "width": 160},
        {"label": _("One Person Only"), "fieldname": "single_person_role", "fieldtype": "Check",
         "width": 70},
        {"label": _("Risk"), "fieldname": "risk_level", "fieldtype": "Data", "width": 80},
        {"label": _("Coverage"), "fieldname": "coverage", "fieldtype": "Data", "width": 90},
        {"label": _("Ready Now"), "fieldname": "ready_now", "fieldtype": "Int", "width": 90},
        {"label": _("1-2 Years"), "fieldname": "ready_soon", "fieldtype": "Int", "width": 90},
        {"label": _("Emerging"), "fieldname": "emerging", "fieldtype": "Int", "width": 90},
        {"label": _("Successors"), "fieldname": "successors", "fieldtype": "Data", "width": 300},
        {"label": _("Development Needs"), "fieldname": "development_needs", "fieldtype": "Data",
         "width": 260},
        {"label": _("Job Opening"), "fieldname": "job_opening", "fieldtype": "Link",
         "options": "Job Opening", "width": 130},
        {"label": _("Exit Due"), "fieldname": "exit_due", "fieldtype": "Date", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]
