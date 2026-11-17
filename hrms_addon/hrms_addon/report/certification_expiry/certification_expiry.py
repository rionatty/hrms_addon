# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Certification Expiry (LMS blueprint flow 4.6): every certificate that has
run out or is about to, soonest first, with how far up the ladder the alerts
have gone (learning.chase_certificates). Renewed and revoked certificates
are left out: something else stands in their place.

It reads through Frappe's permissions, so a plant's HR Officer sees that
plant.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import learning, learning_rules as rules

# the window picked -> the most days left a certificate may have to be listed (None: all)
WINDOWS = {"Run Out": -1, "Within 30 Days": 30, "Within 60 Days": 60, "Within 90 Days": 90,
           "Within 180 Days": 180, "All": None}
AUDIENCE_LABELS = {rules.EMPLOYEE: "Employee", rules.SUPERVISOR: "Supervisor", rules.HEAD: "Head of Department",
                   rules.HR: "HR", rules.MANAGEMENT: "Management"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    s, day = learning.settings(), getdate(today())
    conditions = {"status": ["not in", [rules.RENEWED, rules.REVOKED]]}
    for field in ("company", "branch", "department", "certification", "employee", "verification_status"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    limit = WINDOWS.get(filters.get("window") or "Within 180 Days", 180)
    data = []
    for row in frappe.get_list("Employee Certification", filters=conditions,
                               fields=["name", "employee", "employee_name", "branch", "department", "certification",
                                       "certificate_no", "issuing_body", "issue_date", "expiry_date",
                                       "verification_status", "alerts_sent", "revoked", "renewed_by"],
                               limit_page_length=0):
        left = rules.days_left(row.expiry_date, day)
        if limit is not None and (left is None or left > limit):
            continue
        sent = rules.sent_list(row.alerts_sent)
        told = rules.audiences_for(s["tiers"], min(sent)) if sent else []
        data.append(dict(row, days_left=left, status=rules.certificate_status(row, day, s),
                         told=", ".join(_(AUDIENCE_LABELS[who]) for who in told)))
    data.sort(key=lambda row: (row["days_left"] is None, row["days_left"] or 0))
    return columns(), data


def columns():
    return [
        {"fieldname": "name", "label": _("Record"), "fieldtype": "Link", "options": "Employee Certification",
         "width": 140},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "branch", "label": _("Plant"), "fieldtype": "Link", "options": "Branch", "width": 110},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "certification", "label": _("Certification"), "fieldtype": "Link",
         "options": "Certification", "width": 170},
        {"fieldname": "certificate_no", "label": _("Certificate No"), "fieldtype": "Data", "width": 120},
        {"fieldname": "issuing_body", "label": _("Issuing Body"), "fieldtype": "Data", "width": 120},
        {"fieldname": "expiry_date", "label": _("Expires"), "fieldtype": "Date", "width": 100},
        {"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 85},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 95},
        {"fieldname": "verification_status", "label": _("Checked"), "fieldtype": "Data", "width": 95},
        {"fieldname": "told", "label": _("Told So Far"), "fieldtype": "Data", "width": 260},
    ]
