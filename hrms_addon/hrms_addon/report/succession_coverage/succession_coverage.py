# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Succession Coverage (test case 15): per critical role, who holds it,
how likely losing them is and what it would cost, and who is named to step
in, in the council's order.

The gaps come first, then the riskiest, because a report the council reads
at the top is a report about the roles nobody can fill. It reads through
Frappe's permissions, so a branch's HR Officer sees that branch's roles.
Every figure is read in a handful of queries for all the roles at once,
never one a role. A holder on their way out shows what is filling the
role: the successor whose promotion is drafted, or the requisition for a
replacement.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import succession_rules, talent, talent_rules as rules

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
                "retirement_or_exit_due", "impact_score", "loss_probability", "role_risk", "successors"],
        limit_page_length=0)
    names = [position.name for position in positions]
    drafted = talent.drafted_for_many(names)
    benches = {}
    for row in frappe.get_all("Succession Candidate", filters={"parent": ["in", names],
                                                                "parenttype": "Succession Position"},
                              fields=["parent", "employee", "employee_name", "readiness", "rank", "development_needs",
                                      "emergency_cover", "other_roles"], limit_page_length=0) if names else []:
        benches.setdefault(row.parent, []).append(row)
    rows = []
    for position in positions:
        found = drafted.get(position.name) or {}
        promotion = found.get("promotion") or {}
        candidates = succession_rules.ranked(benches.get(position.name, []))
        counts = rules.bench_strength(candidates)
        rows.append({
            "position": position.name, "designation": position.designation, "department": position.department,
            "branch": position.branch, "incumbent": position.incumbent, "incumbent_name": position.incumbent_name,
            "single_person_role": position.single_person_role, "risk_level": position.risk_level,
            "impact_score": position.impact_score, "loss_probability": position.loss_probability,
            "role_risk": position.role_risk, "coverage": position.coverage,
            "ready_now": counts[rules.READY_NOW], "ready_soon": counts[rules.READY_SOON],
            "emerging": counts[rules.EMERGING],
            "emergency_cover": ", ".join(row.employee_name or row.employee for row in candidates
                                         if row.emergency_cover) or None,
            "successors": ", ".join(
                "%s (%s%s)" % (row.get("employee_name") or row.get("employee"), row.get("readiness"),
                               _(", named for {0} more").format(row.other_roles) if row.get("other_roles") else "")
                for row in candidates) or None,
            "development_needs": "; ".join(need["needs"] for need in rules.development_needs(candidates)) or None,
            "taking_over": promotion.get("employee_name") or promotion.get("employee"),
            "promotion": promotion.get("name"),
            "requisition": (found.get("requisition") or {}).get("name"),
            "job_opening": (found.get("opening") or {}).get("name") or position.job_opening,
            "exit_due": position.retirement_or_exit_due,
            "status": position.status,
        })
    rows.sort(key=lambda row: (ORDER.get(row["coverage"], 3), RISK_ORDER.get(row["risk_level"], 3),
                               -(row["role_risk"] or 0), str(row["designation"] or "")))
    bench = succession_rules.bench_index([{"ready_now": row["ready_now"],
                                           "successors": row["ready_now"] + row["ready_soon"] + row["emerging"]}
                                          for row in rows])
    summary = [
        {"value": bench["roles"], "label": _("Critical roles"), "datatype": "Int", "indicator": "Blue"},
        {"value": bench["ready_now_share"], "label": _("With a successor ready now"), "datatype": "Percent",
         "indicator": "Green"},
        {"value": bench["two_share"], "label": _("With two or more"), "datatype": "Percent", "indicator": "Blue"},
        {"value": bench["none"], "label": _("Nobody named"), "datatype": "Int", "indicator": "Red"},
        {"value": len([row for row in rows if row["risk_level"] == "High"]), "label": _("High risk of loss"),
         "datatype": "Int", "indicator": "Red"},
    ]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Role"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 180},
        {"label": _("Position"), "fieldname": "position", "fieldtype": "Link", "options": "Succession Position",
         "width": 130},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 110},
        {"label": _("Incumbent"), "fieldname": "incumbent_name", "fieldtype": "Data", "width": 160},
        {"label": _("One Person Only"), "fieldname": "single_person_role", "fieldtype": "Check", "width": 70},
        {"label": _("Impact"), "fieldname": "impact_score", "fieldtype": "Float", "width": 70},
        {"label": _("Probability"), "fieldname": "loss_probability", "fieldtype": "Percent", "width": 90},
        {"label": _("Role Risk"), "fieldname": "role_risk", "fieldtype": "Float", "width": 85},
        {"label": _("Risk"), "fieldname": "risk_level", "fieldtype": "Data", "width": 80},
        {"label": _("Coverage"), "fieldname": "coverage", "fieldtype": "Data", "width": 90},
        {"label": _("Ready Now"), "fieldname": "ready_now", "fieldtype": "Int", "width": 90},
        {"label": _("1-2 Years"), "fieldname": "ready_soon", "fieldtype": "Int", "width": 90},
        {"label": _("Emerging"), "fieldname": "emerging", "fieldtype": "Int", "width": 90},
        {"label": _("Emergency Cover"), "fieldname": "emergency_cover", "fieldtype": "Data", "width": 160},
        {"label": _("Successors"), "fieldname": "successors", "fieldtype": "Data", "width": 320},
        {"label": _("Development Needs"), "fieldname": "development_needs", "fieldtype": "Data", "width": 260},
        {"label": _("Taking Over"), "fieldname": "taking_over", "fieldtype": "Data", "width": 160},
        {"label": _("Promotion"), "fieldname": "promotion", "fieldtype": "Link", "options": "Employee Position Change",
         "width": 140},
        {"label": _("Requisition"), "fieldname": "requisition", "fieldtype": "Link", "options": "Job Requisition",
         "width": 140},
        {"label": _("Job Opening"), "fieldname": "job_opening", "fieldtype": "Link", "options": "Job Opening",
         "width": 130},
        {"label": _("Exit Due"), "fieldname": "exit_due", "fieldtype": "Date", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
    ]
