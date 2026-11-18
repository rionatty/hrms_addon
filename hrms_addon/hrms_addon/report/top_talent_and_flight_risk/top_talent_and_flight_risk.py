# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Top Talent and Flight Risk (test case 22): the people in the top-talent
boxes, the risk of losing each as last assessed and what losing them would
cost, the retention actions open on them, the roles they are named to
succeed and how far their development plan has got: the highest risk
first. Read in a handful of queries for everyone at once. It names boxes,
so it is for HR and the Talent Council."""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import succession_rules, talent_reports

RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    review = filters.get("talent_review") or talent_reports.latest_review()
    conditions = {"talent_review": review, "docstatus": ["<", 2], "top_talent": 1}
    for field in ("branch", "department", "flight_risk"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    placed = frappe.get_list("Talent Placement", filters=conditions, fields=[
        "name", "employee", "employee_name", "designation", "branch", "box", "box_name", "performance_score",
        "potential_score", "flight_risk", "impact_of_loss", "risk_assessed_on", "on_pip", "development_plan",
        "workflow_state"], limit_page_length=0) if review else []
    people = [row.employee for row in placed]
    names = [row.name for row in placed]
    benches = {}
    if people:
        for row in frappe.db.sql("""
                select candidate.employee, position.designation, candidate.readiness
                from `tabSuccession Candidate` candidate
                join `tabSuccession Position` position on position.name = candidate.parent
                where candidate.parenttype = 'Succession Position' and position.docstatus < 2
                  and candidate.employee in %(people)s""", {"people": people}, as_dict=True):
            benches.setdefault(row.employee, []).append("%s (%s)" % (row.designation, _(row.readiness or "")))
    actions = {}
    for row in frappe.get_all("Retention Action", filters={"parent": ["in", names], "parenttype": "Talent Placement"},
                              fields=["parent", "status", "due"], limit_page_length=0) if names else []:
        actions.setdefault(row.parent, []).append(row)
    progress = talent_reports.plan_progress([row.development_plan for row in placed if row.development_plan])
    rows = []
    for row in placed:
        plan = progress.get(row.development_plan) or {}
        live, late = succession_rules.open_retention(actions.get(row.name, []), today())
        rows.append(dict(row, successor_for=", ".join(benches.get(row.employee, [])) or None,
                         retention_open=live, retention_late=late,
                         plan_share=plan.get("share"), actions_late=plan.get("late")))
    rows.sort(key=lambda row: (RISK_ORDER.get(row.get("flight_risk"), 3), -(row.get("box") or 0),
                               str(row.get("employee_name") or "")))
    watched = [row for row in rows if row.get("flight_risk") in ("High", "Medium")]
    summary = [
        {"value": len(rows), "label": _("Top talent"), "datatype": "Int", "indicator": "Green"},
        {"value": len([row for row in rows if row.get("flight_risk") == "High"]), "label": _("High flight risk"),
         "datatype": "Int", "indicator": "Red"},
        {"value": len([row for row in rows if row.get("flight_risk") == "Medium"]),
         "label": _("Medium flight risk"), "datatype": "Int", "indicator": "Orange"},
        {"value": len([row for row in watched if not row["retention_open"]]), "label": _("At risk, no action open"),
         "datatype": "Int", "indicator": "Red"},
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
        {"label": _("Assessed On"), "fieldname": "risk_assessed_on", "fieldtype": "Date", "width": 100},
        {"label": _("Impact of Loss"), "fieldname": "impact_of_loss", "fieldtype": "Data", "width": 110},
        {"label": _("Retention Actions Open"), "fieldname": "retention_open", "fieldtype": "Int", "width": 110},
        {"label": _("Overdue"), "fieldname": "retention_late", "fieldtype": "Int", "width": 80},
        {"label": _("Successor For"), "fieldname": "successor_for", "fieldtype": "Data", "width": 220},
        {"label": _("Plan Done"), "fieldname": "plan_share", "fieldtype": "Percent", "width": 90},
        {"label": _("Actions Late"), "fieldname": "actions_late", "fieldtype": "Int", "width": 95},
        {"label": _("On an Improvement Plan"), "fieldname": "on_pip", "fieldtype": "Check", "width": 90},
        {"label": _("Placement"), "fieldname": "name", "fieldtype": "Link", "options": "Talent Placement",
         "width": 140},
    ]
