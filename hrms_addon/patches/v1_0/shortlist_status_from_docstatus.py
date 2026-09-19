# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Shortlists made before the HOD screening get the Status of where they stand.

The Status column arrived with the screening workflow and defaults to Draft,
so a shortlist already submitted would list as Draft. post_model_sync: the
column exists only after the model sync. The workflow sets their state the
same way when it is first saved (Frappe fills an empty state from docstatus).
"""

import frappe

from hrms_addon.hrms_addon import interview_shortlist_approval as screening


def execute():
    for docstatus, status in ((1, screening.SCREENED), (2, screening.CANCELLED)):
        frappe.db.sql(
            "update `tabInterview Shortlist` set status = %s where docstatus = %s and ifnull(status, '') in ('', %s)",
            (status, docstatus, screening.DRAFT),
        )
