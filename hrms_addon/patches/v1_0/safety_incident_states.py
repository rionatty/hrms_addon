"""The safety incidents recorded before their workflow (review items 12 and
16, Luuka 5 Nov 2026) stand at the matching state: a draft at Draft, one
already recorded at Recorded, its investigation still to come, a cancelled
one at Cancelled. Safe to run twice: only an incident with no state is
touched."""

import frappe

STATES = ((0, "Draft"), (1, "Recorded"), (2, "Cancelled"))


def execute():
    for docstatus, state in STATES:
        for name in frappe.get_all("Safety Incident", filters={"docstatus": docstatus, "workflow_state": ["is", "not set"]},
                                   pluck="name", limit_page_length=0):
            frappe.db.set_value("Safety Incident", name, {"workflow_state": state, "approval_status": state},
                                update_modified=False)
