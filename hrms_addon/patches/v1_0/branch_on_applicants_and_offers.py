# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Applicants and Job Offers made before they had a Branch get their opening's.

The Branch arrived with the onboarding: each branch's HR Officer sees only
its own applicants and offers (Branch User Permissions), and the onboarding
takes the branch from the offer. Only blanks are filled.

The fields are fixtures, which migrate imports AFTER the post_model_sync
patches, so they are synced here first.
"""

import frappe
from frappe.utils.fixtures import sync_fixtures


def execute():
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Job Applicant")
    frappe.clear_cache(doctype="Job Offer")
    frappe.db.sql(
        """update `tabJob Applicant` applicant
        join `tabJob Opening` opening on opening.name = applicant.job_title
        set applicant.custom_branch = opening.location
        where ifnull(applicant.custom_branch, '') = '' and ifnull(opening.location, '') != ''"""
    )
    frappe.db.sql(
        """update `tabJob Offer` offer
        join `tabJob Applicant` applicant on applicant.name = offer.job_applicant
        set offer.custom_branch = applicant.custom_branch
        where ifnull(offer.custom_branch, '') = '' and ifnull(applicant.custom_branch, '') != ''"""
    )
