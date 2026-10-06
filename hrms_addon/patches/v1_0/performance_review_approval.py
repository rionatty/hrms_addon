# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance Reviews go to management for approval (Luuka, 6 Oct 2026:
"the report is supposed to be shared to the management for approval").

The old statuses become the workflow's states. A review Shared went to
management with no step to approve, so it goes back to Draft for HR to
send on, which tells the General Manager; Decided is Approved; Cancelled
stays Cancelled. Only reviews with no state yet are touched, so it is safe
to run twice.
"""

import frappe

from hrms_addon.hrms_addon import performance_review_approval as approval

# the state each docstatus stands in
STATES = {0: approval.DRAFT, 1: approval.APPROVED, 2: approval.CANCELLED}


def execute():
    if not frappe.db.has_column(approval.DOCTYPE, approval.STATE_FIELD):
        return
    for review in frappe.get_all(approval.DOCTYPE, filters={approval.STATE_FIELD: ["is", "not set"]},
                                 fields=["name", "docstatus"]):
        state = STATES.get(review.docstatus, approval.DRAFT)
        frappe.db.set_value(approval.DOCTYPE, review.name, {approval.STATE_FIELD: state, "status": state},
                            update_modified=False)
