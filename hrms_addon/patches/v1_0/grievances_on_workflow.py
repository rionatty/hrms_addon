# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The non-disciplinary grievance on its workflow (Luuka, 7 Oct 2026: "did
you build non displnary ... please proceed"). Each grievance already on the
site takes the stage it stands at (grievance_approval.stage_of) before
after_migrate builds the workflow, which would otherwise put every draft
back at Draft for whoever drew it up to raise again.

The workflow's state field is made here when the site has none yet, as
Frappe makes it. Safe to run twice: a grievance with a stage keeps it.
"""

import frappe

from hrms_addon.hrms_addon import grievance_approval as approval


def execute():
    if not frappe.db.table_exists(approval.DOCTYPE):
        return
    _state_field()
    columns = set(frappe.db.get_table_columns(approval.DOCTYPE))
    fields = ["name", "docstatus", "status"] + [field for field in ("custom_assigned_hod", "custom_appeal_filed")
                                                if field in columns]
    for row in frappe.get_all(approval.DOCTYPE, filters=[[approval.STATE_FIELD, "is", "not set"]], fields=fields,
                              limit_page_length=0):
        state = approval.stage_of(row.docstatus, row.status, row.get("custom_assigned_hod"),
                                  bool(row.get("custom_appeal_filed")))
        frappe.db.set_value(approval.DOCTYPE, row.name,
                            {approval.STATE_FIELD: state, "status": approval.FRAPPE_STATUS[state]},
                            update_modified=False)


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
