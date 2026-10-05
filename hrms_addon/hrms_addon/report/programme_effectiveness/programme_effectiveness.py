# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Programme Effectiveness (test cases 2 and 3): each programme whose
outcome can be read (a blank score is kept as 0, so one after above 0),
the appraisal score before and after it, the movement
and how effective that makes it, and what management decided — the
programmes that worked best first."""

import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": ["<", 2], "score_after": [">", 0]}
    for field in ("program_type", "branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    rows = frappe.get_list("Talent Program", filters=conditions, fields=[
        "name", "employee", "employee_name", "program_type", "workflow_state", "score_before", "score_after",
        "movement", "effectiveness", "decision", "end_date"], limit_page_length=0)
    rows.sort(key=lambda row: (-(row.movement or 0), str(row.employee_name or "")))
    kinds = ["Highly Effective", "Effective", "Some Effect", "No Effect"]
    chart = {"data": {"labels": [_(kind) for kind in kinds],
                      "datasets": [{"name": _("Programmes"),
                                    "values": [len([row for row in rows if row.effectiveness == kind]) for kind in kinds]}]},
             "type": "bar", "colors": ["#14395E"]}
    moved = [row.movement for row in rows if row.movement is not None]
    summary = [
        {"value": len(rows), "label": _("Programmes read"), "datatype": "Int", "indicator": "Blue"},
        {"value": round(sum(moved) / len(moved), 1) if moved else 0, "label": _("Average movement"),
         "datatype": "Float", "indicator": "Green"},
        {"value": len([row for row in rows if row.effectiveness in ("Highly Effective", "Effective")]),
         "label": _("Effective or better"), "datatype": "Int", "indicator": "Green"},
    ]
    return columns(), rows, None, chart, summary


def columns():
    return [
        {"label": _("Plan"), "fieldname": "name", "fieldtype": "Link", "options": "Talent Program", "width": 140},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Programme"), "fieldname": "program_type", "fieldtype": "Data", "width": 170},
        {"label": _("Status"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 110},
        {"label": _("Score Before"), "fieldname": "score_before", "fieldtype": "Float", "width": 105},
        {"label": _("Score After"), "fieldname": "score_after", "fieldtype": "Float", "width": 100},
        {"label": _("Movement"), "fieldname": "movement", "fieldtype": "Float", "width": 95},
        {"label": _("Effectiveness"), "fieldname": "effectiveness", "fieldtype": "Data", "width": 130},
        {"label": _("Decision"), "fieldname": "decision", "fieldtype": "Data", "width": 150},
        {"label": _("Ended"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
    ]
