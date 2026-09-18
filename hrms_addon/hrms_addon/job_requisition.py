# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Requisition — Frappe side of the approval workflow.

The definition (states, transitions, which fields each signature fills)
lives in requisition_approval.py, which has no Frappe import so it can be
tested without a bench. This module only applies it:

  setup_on_migrate()  after_migrate: roles, permissions, Workflow States,
                      Workflow Actions and the Workflow itself, built by
                      workflows.py (which says why that is Python, not fixtures)
  before_validate()   defaults Requested By to the logged-in employee
  validate()          fills the Approvals tab as approvers act

To change who approves, change requisition_approval.py, not the Workflow in
the desk — a desk edit is overwritten on the next deploy.
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import requisition_approval as rules
from hrms_addon.hrms_addon import workflows

# ── Doc events ───────────────────────────────────────────────────────


def before_validate(doc, method=None):
    """Requested By = the logged-in user's employee record.

    Runs before the mandatory check, so an API or import that leaves it
    blank still saves. The form sets it on load (job_requisition.js); this
    is the server-side net for everything that is not the form.
    """
    if doc.is_new() and not doc.get("requested_by"):
        employee = _employee_for(frappe.session.user)
        if employee:
            doc.requested_by = employee


def validate(doc, method=None):
    before = doc.get_doc_before_save()
    old_state = before.get(rules.STATE_FIELD) if before else None
    new_state = doc.get(rules.STATE_FIELD)

    if rules.recommended_salary_missing(old_state, new_state, doc.get("expected_compensation")):
        frappe.throw(
            _("Enter the Recommended Salary and save before authorizing this requisition."),
            title=_("Recommended Salary Required"),
        )

    current = {field: before.get(field) for field in rules.ALL_STAMP_FIELDS} if before else {}
    stamped = rules.compute_stamp_values(old_state, new_state, frappe.session.user, today(), current)
    for field, value in stamped.items():
        doc.set(field, value)


@frappe.whitelist()
def get_session_employee():
    """Active employee linked to the logged-in user — for the form default.

    Server-side on purpose: the Employee role can only read its own
    employee record through user permissions, which is enough here but
    not something the browser should have to rely on.
    """
    return _employee_for(frappe.session.user)


def _employee_for(user):
    if not user or user in ("Guest", "Administrator"):
        return None
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


# ── Setup (after_migrate) ────────────────────────────────────────────


def setup_on_migrate():
    """after_migrate hook: the approval workflow, never failing the deploy."""
    workflows.setup_on_migrate(rules, "Job Requisition approval")
