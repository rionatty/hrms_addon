# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The interview letters (interviews.seed_interview_letters): the invitation
and regret Email Templates, and HR Settings' interview day and letters where
they are empty, once. Regret emails stay switched off until HR switches them
on, as do invitations by SMS.

The HR Settings fields are fixtures, which migrate imports AFTER the
post_model_sync patches, so they are synced here first.
"""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon.interviews import seed_interview_letters


def execute():
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="HR Settings")
    seed_interview_letters()
