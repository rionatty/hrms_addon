# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interviewer Calibration: each panel member's scores against their
colleagues' on the same candidates, so HR sees who marks high or low, and how
often each recommends an offer. The arithmetic is in
interview_analytics_rules.py."""

import frappe
from frappe import _
from frappe.utils import add_months, today

from hrms_addon.hrms_addon import interview_analytics_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = [["scheduled_on", ">=", filters.get("from_date") or add_months(today(), -3)],
                  ["scheduled_on", "<=", filters.get("to_date") or today()], ["docstatus", "!=", 2]]
    for field in ("designation", "interview_type"):
        if filters.get(field):
            conditions.append([field, "=", filters.get(field)])
    interviews = frappe.get_all("Interview", filters=conditions, pluck="name")
    sheets = [{"interviewer": row.interviewer, "interview": row.interview, "percent": row.custom_score_percent,
               "recommendation": row.custom_recommendation}
              for row in frappe.get_all("Interview Feedback", filters={"interview": ["in", interviews or [""]], "docstatus": 1},
                                        fields=["interviewer", "interview", "custom_score_percent", "custom_recommendation"])]
    rows = rules.calibration(sheets)
    names = dict(frappe.get_all("User", filters={"name": ["in", [row["interviewer"] for row in rows] or [""]]},
                                fields=["name", "full_name"], as_list=True))
    for row in rows:
        row["full_name"] = names.get(row["interviewer"]) or row["interviewer"]
    return columns(), rows


def columns():
    return [
        {"fieldname": "interviewer", "label": _("Panel Member"), "fieldtype": "Link", "options": "User", "width": 200},
        {"fieldname": "full_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
        {"fieldname": "sheets", "label": _("Sheets"), "fieldtype": "Int", "width": 80},
        {"fieldname": "average", "label": _("Their Average"), "fieldtype": "Percent", "width": 120},
        {"fieldname": "others_average", "label": _("Colleagues' Average"), "fieldtype": "Percent", "width": 140},
        {"fieldname": "difference", "label": _("Difference"), "fieldtype": "Float", "precision": 2, "width": 110},
        {"fieldname": "compared", "label": _("Interviews Shared"), "fieldtype": "Int", "width": 130},
        {"fieldname": "offer_share", "label": _("Offer"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "reject_share", "label": _("Reject"), "fieldtype": "Percent", "width": 90},
    ]
