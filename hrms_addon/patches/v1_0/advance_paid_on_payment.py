"""An Employee Advance is Paid when its payment is recorded, not when Finance pass it (Luuka, 16 Nov 2026: "The state
changes to Paid before making the payment"). One left at Paid that the payments recorded against it do not cover goes
back to Approved, and becomes Paid when it is paid (advances.follow_payment). Safe to run twice."""

import frappe
from frappe.utils import flt

from hrms_addon.hrms_addon import advance_approval as approval

DOCTYPE = "Employee Advance"


def execute():
    meta = frappe.get_meta(DOCTYPE)
    # a fresh site: the workflow and the custom fields come after the patches, and there is nothing to put right
    if not (meta.has_field("workflow_state") and meta.has_field("custom_approved_amount")):
        return
    rows = frappe.get_all(DOCTYPE, filters={"docstatus": 1, "workflow_state": approval.PAID},
                          fields=["name", "paid_amount", "advance_amount", "custom_approved_amount"],
                          limit_page_length=0)
    for row in rows:
        to_pay = flt(row.custom_approved_amount) or flt(row.advance_amount)
        state = approval.paid_state(approval.PAID, row.paid_amount, to_pay)
        if state != approval.PAID:
            frappe.db.set_value(DOCTYPE, row.name, {"workflow_state": state, "custom_advance_status": state},
                                update_modified=False)
