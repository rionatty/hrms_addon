# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The applicants of the open Job Openings, from before their screening was
kept on them: each one screened and kept (cv_screening.rescreen_opening),
and one from someone on the staff linked to their employee record, where
exactly one active record matches (internal_hires.py). A link HR made is
left as it is.

The fields are fixtures, which migrate imports AFTER the post_model_sync
patches, so they are synced here first.
"""

import frappe
from frappe.utils.fixtures import sync_fixtures


def execute():
    from hrms_addon.hrms_addon import cv_screening
    from hrms_addon.hrms_addon import internal_hire_rules as rules

    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Job Applicant")
    openings = frappe.get_all("Job Opening", filters={"status": "Open"}, pluck="name")
    for name in frappe.get_all("Job Applicant", filters={"job_title": ["in", openings or [""]]}, pluck="name"):
        doc = frappe.get_doc("Job Applicant", name)
        if not doc.get("custom_employee"):
            staff = rules.employee_match(cv_screening.employees_like(doc, limit=5))
            if staff:
                frappe.db.set_value("Job Applicant", name, "custom_employee", staff, update_modified=False)
    for opening in openings:
        cv_screening.rescreen_opening(opening)
