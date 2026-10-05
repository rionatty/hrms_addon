# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Top Talent and Flight Risk (test case 22): the people in boxes 6, 8
and 9, the risk of losing each and what losing them would cost, the roles
they are named to succeed and how far their development plan has got —
the highest risk first. It names boxes, so it is for HR and the Talent
Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports

RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    review = filters.get("talent_review") or talent_reports.latest_review()
    conditions = {"talent_review": review, "docstatus": ["<", 2], "top_talent": 1}
    for field in ("branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    placed = frappe.get_list("Talent Placement", filters=conditions, fields=[
        "name", "employee", "employee_name", "designation", "branch", "box", "box_name", "performance_score",
        "potential_score", "flight_risk", "impact_of_loss", "on_pip", "development_plan", "workflow_state"],
        limit_page_length=0) if review else []
    people = [row.employee for row in placed]
    benches = {}
    for row in frappe.get_all("Succession Candidate", filters={"employee": ["in", people],
                                                                "parenttype": "Succession Position"},
                              fields=["employee", "parent", "readiness"], limit=0) if people else []:
        role = frappe.db.get_value("Succession Position", row.parent, "designation")
        benches.setdefault(row.employee, []).append("%s (%s)" % (role or row.parent, _(row.readiness or "")))
    progress = talent_reports.plan_progress([row.development_plan for row in placed if row.development_plan])
    rows = []
    for row in placed:
        plan = progress.get(row.development_plan) or {}
        rows.append(dict(row, successor_for=", ".join(benches.get(row.employee, [])) or None,
                         plan_share=plan.get("share"), actions_late=plan.get("late")))
    rows.sort(key=lambda row: (RISK_ORDER.get(row.get("flight_risk"), 3), -(row.get("box") or 0),
                               str(row.get("employee_name") or "")))
    summary = [
        {"value": len(rows), "label": _("Top talent"), "datatype": "Int", "indicator": "Green"},
        {"value": len([row for row in rows if row.get("flight_risk") == "High"]), "label": _("High flight risk"),
         "datatype": "Int", "indicator": "Red"},
        {"value": len([row for row in rows if row.get("flight_risk") == "Medium"]),
         "label": _("Medium flight risk"), "datatype": "Int", "indicator": "Orange"},
        {"value": len([row for row in rows if not row.get("successor_for")]), "label": _("On no bench"),
         "datatype": "Int", "indicator": "Grey"},
    ]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Job Title"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation",
         "width": 160},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 100},
        {"label": _("Box"), "fieldname": "box", "fieldtype": "Int", "width": 55},
        {"label": _("Cell"), "fieldname": "box_name", "fieldtype": "Data", "width": 130},
        {"label": _("Year to Date"), "fieldname": "performance_score", "fieldtype": "Float", "width": 100},
        {"label": _("Potential"), "fieldname": "potential_score", "fieldtype": "Float", "width": 90},
        {"label": _("Flight Risk"), "fieldname": "flight_risk", "fieldtype": "Data", "width": 95},
        {"label": _("Impact of Loss"), "fieldname": "impact_of_loss", "fieldtype": "Data", "width": 110},
        {"label": _("Successor For"), "fieldname": "successor_for", "fieldtype": "Data", "width": 220},
        {"label": _("Plan Done"), "fieldname": "plan_share", "fieldtype": "Percent", "width": 90},
        {"label": _("Actions Late"), "fieldname": "actions_late", "fieldtype": "Int", "width": 95},
        {"label": _("On an Improvement Plan"), "fieldname": "on_pip", "fieldtype": "Check", "width": 90},
        {"label": _("Placement"), "fieldname": "name", "fieldtype": "Link", "options": "Talent Placement",
         "width": 140},
    ]
