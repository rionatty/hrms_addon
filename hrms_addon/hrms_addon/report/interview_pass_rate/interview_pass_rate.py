# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Pass Rate: each opening's rounds, how many were booked, came,
did not come, cleared, were rejected or wait on the panel, and the share of
those decided who passed. The arithmetic is in interview_analytics_rules.py."""

import frappe
from frappe import _
from frappe.utils import add_months, today

from hrms_addon.hrms_addon import interview_analytics_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = [["scheduled_on", ">=", filters.get("from_date") or add_months(today(), -3)],
                  ["scheduled_on", "<=", filters.get("to_date") or today()], ["docstatus", "!=", 2]]
    for field in ("job_opening", "designation"):
        if filters.get(field):
            conditions.append([field, "=", filters.get(field)])
    interviews = [{"job_opening": row.job_opening, "interview_type": row.interview_type, "round": row.custom_round,
                   "status": row.status, "docstatus": row.docstatus, "attendance": row.custom_attendance}
                  for row in frappe.get_all("Interview", filters=conditions,
                                            fields=["job_opening", "interview_type", "custom_round", "status", "docstatus",
                                                    "custom_attendance"])]
    return columns(), rules.pass_rates(interviews)


def columns():
    return [
        {"fieldname": "job_opening", "label": _("Job Opening"), "fieldtype": "Link", "options": "Job Opening", "width": 180},
        {"fieldname": "round", "label": _("Round"), "fieldtype": "Int", "width": 70},
        {"fieldname": "interview_type", "label": _("Interview Type"), "fieldtype": "Link", "options": "Interview Type",
         "width": 200},
        {"fieldname": "booked", "label": _("Booked"), "fieldtype": "Int", "width": 80},
        {"fieldname": "attended", "label": _("Came"), "fieldtype": "Int", "width": 80},
        {"fieldname": "absent", "label": _("Did Not Come"), "fieldtype": "Int", "width": 110},
        {"fieldname": "cleared", "label": _("Cleared"), "fieldtype": "Int", "width": 80},
        {"fieldname": "rejected", "label": _("Rejected"), "fieldtype": "Int", "width": 90},
        {"fieldname": "awaiting", "label": _("Awaiting the Panel"), "fieldtype": "Int", "width": 140},
        {"fieldname": "pass_rate", "label": _("Pass Rate"), "fieldtype": "Percent", "width": 100},
    ]
