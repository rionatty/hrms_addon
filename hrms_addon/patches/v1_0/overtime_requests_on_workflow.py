# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Overtime Request on its workflow (Luuka, 12 Oct 2026: "make the
approval like normal approval not like this"). Each request already on the
site takes the stage it stands at (overtime_approval.stage_of) before
after_migrate builds the workflow.

A request used to be submitted the moment it was raised. On the workflow it
is submitted when HR approve it, so one still waiting to be authorised or
costed goes back to a draft at that step, with its lines, for whoever holds
it to take from the Actions menu. One already costed, sent to payroll,
refused or cancelled stays as it is.

The workflow's state field is made here when the site has none yet, as
Frappe makes it. Safe to run twice: a request with a stage keeps it.
"""

import frappe

from hrms_addon.hrms_addon import overtime_approval as approval

LINES = "Overtime Request Employee"


def execute():
    if not frappe.db.table_exists(approval.DOCTYPE):
        return
    _state_field()
    for row in frappe.get_all(approval.DOCTYPE, filters=[[approval.STATE_FIELD, "is", "not set"]],
                              fields=["name", "docstatus", "status"], limit_page_length=0):
        state, docstatus = approval.stage_of(row.docstatus, row.status)
        frappe.db.set_value(approval.DOCTYPE, row.name,
                            {approval.STATE_FIELD: state, "status": state, "docstatus": docstatus},
                            update_modified=False)
        if docstatus != row.docstatus:
            for line in frappe.get_all(LINES, filters={"parent": row.name, "parenttype": approval.DOCTYPE},
                                       pluck="name", limit_page_length=0):
                frappe.db.set_value(LINES, line, "docstatus", docstatus, update_modified=False)


def _state_field():
    """Frappe's own workflow state field, as a Workflow makes it when it is
    saved (frappe/workflow/doctype/workflow/workflow.py)."""
    if frappe.db.has_column(approval.DOCTYPE, approval.STATE_FIELD):
        return
    frappe.get_doc({
        "doctype": "Custom Field", "dt": approval.DOCTYPE, "fieldname": approval.STATE_FIELD,
        "label": approval.STATE_FIELD.replace("_", " ").title(), "hidden": 1, "allow_on_submit": 1, "no_copy": 1,
        "fieldtype": "Link", "options": "Workflow State", "owner": "Administrator",
    }).insert(ignore_permissions=True)
    frappe.clear_cache(doctype=approval.DOCTYPE)
