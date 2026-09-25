# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""On the site's Employee Loan workflow: the employee no longer runs their
own loan (chart step 4 is HR's or the Payroll Officer's), and the HR
Officer may record a consent signed on paper.

The workflow is set up in the desk (loan_approval.DESK_MANAGED), so this
changes only those two things and leaves the approvals as they are. Safe
to run twice.
"""

import frappe


def execute():
    from hrms_addon.hrms_addon import loan_approval as approval

    if not frappe.db.exists("Workflow", approval.WORKFLOW_NAME):
        return
    workflow = frappe.get_doc("Workflow", approval.WORKFLOW_NAME)
    changed = False
    keep = [row for row in workflow.transitions if not (row.action == approval.RUN and row.allowed == "Employee")]
    if len(keep) != len(workflow.transitions):
        workflow.set("transitions", keep)
        changed = True
    consent = [row for row in workflow.states if row.state == approval.PENDING_CONSENT]
    if consent and not any(row.allow_edit == approval.HR_OFFICER for row in consent):
        model = consent[0]
        workflow.append("states", {"state": approval.PENDING_CONSENT, "doc_status": model.doc_status,
                                   "allow_edit": approval.HR_OFFICER, "update_field": model.update_field,
                                   "update_value": model.update_value, "send_email": model.send_email})
        changed = True
    if changed:
        workflow.save(ignore_permissions=True)
