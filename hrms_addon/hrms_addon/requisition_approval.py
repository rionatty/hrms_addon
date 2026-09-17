# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Requisition approval: the definition and the stamping rules.

Deliberately imports nothing from Frappe. Everything here is plain data
and pure functions, so scripts/verify_requisition_workflow.py can load it
and exercise every transition on a machine with no bench. The Frappe side
(creating the Workflow, doc events, permissions) is in job_requisition.py
and only ever reads from this module.

WHAT IT MIRRORS

LPL/HR/36, the paper Staff Requisition Form, is signed in this order:

    Supervisor -> Process Owner -> Head of Department -> HR Officer
    -> HR Manager (Recruitment Authorized / Not Authorized)
    -> Executive Director (Recruitment Approved / Not Approved)

Each signature becomes one Frappe Workflow state. When an approver acts,
their name, the date and (for the two decision-makers) the decision are
written into the matching fields on the Approvals tab — see
compute_stamp_values(). Those fields are read-only in the form, and this
module also puts back any value that was changed without a workflow
transition, so nobody can type in someone else's approval.

Not modelled, on purpose: the blueprint's approval matrix adds a General
Manager step and splits admin from non-admin routes. The paper form the
client handed over has neither, so neither does this.
"""

DOCTYPE = "Job Requisition"
WORKFLOW_NAME = "Job Requisition Approval"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
APPROVED = "Approved"
REJECTED = "Rejected"

SUBMIT = "Submit for Approval"
APPROVE = "Approve"
REJECT = "Reject"
REVISE = "Revise"
ACTIONS = (SUBMIT, APPROVE, REJECT, REVISE)

# Roles this app creates. HR User / HR Manager ship with HRMS.
NEW_ROLES = ("Supervisor", "Process Owner", "Head of Department", "Executive Director")

# Who may raise a requisition: every role with create permission on Job
# Requisition (HR Manager and System Manager from HRMS, the rest granted in
# PERMISSIONS below). Each of them may edit a Draft, submit it, and revise
# it after a rejection.
#
# Frappe makes a workflow document read-only ("This form is not editable
# due to a Workflow", frappe/public/js/frappe/model/workflow.js is_read_only)
# for anyone who is not an edit role of its current state. A Draft editable
# by one role alone locked every other author out of their own requisition.
REQUESTER_ROLES = ("Head of Department", "Supervisor", "Process Owner", "HR User", "HR Manager", "System Manager")

HRM_STATE = "Pending HR Manager Approval"

# One row per signature on the paper form, in signing order.
#   state  : the Workflow State the requisition waits in
#   role   : who may approve or reject it there
#   stamp  : which Approvals-tab fields record that signature
APPROVAL_CHAIN = (
    {
        "state": "Pending Supervisor Approval",
        "role": "Supervisor",
        "stamp": {"user": "custom_supervisor", "date": "custom_supervisor_date"},
    },
    {
        "state": "Pending Process Owner Approval",
        "role": "Process Owner",
        "stamp": {"user": "custom_process_owner", "date": "custom_process_owner_date"},
    },
    {
        "state": "Pending HOD Approval",
        "role": "Head of Department",
        "stamp": {"user": "custom_hod", "date": "custom_hod_date"},
    },
    {
        "state": "Pending HR Officer Review",
        "role": "HR User",
        "stamp": {"user": "custom_hr_officer", "date": "custom_hr_officer_date"},
    },
    {
        "state": HRM_STATE,
        "role": "HR Manager",
        "stamp": {
            "user": "custom_hrm",
            "date": "custom_hrm_date",
            "decision": "custom_hrm_decision",
            "approved": "Recruitment Authorized",
            "rejected": "Not Authorized",
        },
    },
    {
        "state": "Pending Executive Director Approval",
        "role": "Executive Director",
        "stamp": {
            "user": "custom_ed",
            "date": "custom_ed_date",
            "decision": "custom_ed_decision",
            "approved": "Recruitment Approved",
            "rejected": "Not Approved",
        },
    },
)

# Workflow Document State rows. update_value keeps the standard Job
# Requisition `status` in step, which matters: HRMS only shows its
# "Create Job Opening" button when status == "Open & Approved".
#
# Draft has one row per requester role: a state row names a single
# "Only Allow Edit For" role, and Frappe lets anyone holding the role of
# ANY row for the state edit (get_document_state_roles). The first row is
# still Draft, so new requisitions still start there.
#
# send_email: Frappe emails everyone who may take a state's next action
# (frappe/workflow/doctype/workflow_action). That is right for the approval
# steps, but in Draft and Rejected the next action (Submit, Revise) is open
# to every requester role, so each saved draft would email every HR
# Manager, Head of Department and Supervisor. Those two states stay quiet.
STATES = (
    *(
        {"state": DRAFT, "allow_edit": role, "status": "Pending", "style": "", "send_email": 0}
        for role in REQUESTER_ROLES
    ),
    *(
        {"state": step["state"], "allow_edit": step["role"], "status": "Pending", "style": "Warning", "send_email": 1}
        for step in APPROVAL_CHAIN
    ),
    {"state": APPROVED, "allow_edit": "HR Manager", "status": "Open & Approved", "style": "Success", "send_email": 1},
    {"state": REJECTED, "allow_edit": "HR Manager", "status": "Rejected", "style": "Danger", "send_email": 0},
)


def _build_transitions():
    rows = [
        {"state": DRAFT, "action": SUBMIT, "next_state": APPROVAL_CHAIN[0]["state"], "allowed": role}
        for role in REQUESTER_ROLES
    ]
    for index, step in enumerate(APPROVAL_CHAIN):
        is_last = index == len(APPROVAL_CHAIN) - 1
        next_state = APPROVED if is_last else APPROVAL_CHAIN[index + 1]["state"]
        rows.append({"state": step["state"], "action": APPROVE, "next_state": next_state, "allowed": step["role"]})
        rows.append({"state": step["state"], "action": REJECT, "next_state": REJECTED, "allowed": step["role"]})
    # A rejected requisition goes back to the requester to amend and resubmit.
    rows.extend({"state": REJECTED, "action": REVISE, "next_state": DRAFT, "allowed": role} for role in REQUESTER_ROLES)
    return tuple(rows)


TRANSITIONS = _build_transitions()

STAMP_RULES = {step["state"]: step["stamp"] for step in APPROVAL_CHAIN}

ALL_STAMP_FIELDS = tuple(
    fieldname
    for step in APPROVAL_CHAIN
    for key in ("user", "date", "decision")
    if (fieldname := step["stamp"].get(key))
)

# Rights the workflow needs to actually work. Approving saves the
# document, so every approver role needs write. Standard HRMS gives
# HR User only READ on Job Requisition, so the HR Officer step would fail
# without this. Designation and Employment Type are pickers on the form
# that the Employee role cannot search at all upstream.
PERMISSIONS = {
    "Job Requisition": {
        "Supervisor": ("read", "write", "create"),
        "Process Owner": ("read", "write", "create"),
        "Head of Department": ("read", "write", "create"),
        "Executive Director": ("read", "write"),
        "HR User": ("read", "write", "create"),
    },
    "Designation": {
        "Supervisor": ("select",),
        "Process Owner": ("select",),
        "Head of Department": ("select",),
    },
    "Employment Type": {
        "Supervisor": ("select",),
        "Process Owner": ("select",),
        "Head of Department": ("select",),
    },
}


def compute_stamp_values(old_state, new_state, user, today, current):
    """Every Approvals-tab field's correct value after this save.

    old_state / new_state : workflow_state before and after the save
                            (old_state is None when the document is new)
    user, today           : who is saving, and the date
    current               : {fieldname: value} as stored in the database
                            before this save ({} for a new document)

    The return value covers ALL stamp fields, not just the ones that
    change. The caller writes every one back, which is what stops a value
    typed in (or posted through the API) from surviving a save: anything
    not produced by a transition reverts to what the database held.
    """
    values = {field: current.get(field) for field in ALL_STAMP_FIELDS}

    if not old_state:
        # A brand-new requisition carries no approvals, whatever was posted.
        return {field: None for field in ALL_STAMP_FIELDS}

    if old_state == new_state:
        return values

    if old_state == REJECTED and new_state == DRAFT:
        # Revised after rejection: it must be approved again from scratch.
        return {field: None for field in ALL_STAMP_FIELDS}

    rule = STAMP_RULES.get(old_state)
    if not rule:
        return values

    approved = new_state != REJECTED
    # Sign-only steps record an approval. The two decision steps record
    # either outcome, because the paper form has a box for each.
    if approved or rule.get("decision"):
        values[rule["user"]] = user
        values[rule["date"]] = today
        if rule.get("decision"):
            values[rule["decision"]] = rule["approved"] if approved else rule["rejected"]

    return values


def recommended_salary_missing(old_state, new_state, recommended_salary):
    """The HR Manager recommends the salary on the paper form, so it must
    be filled in before they authorize. Rejecting needs no salary."""
    return old_state == HRM_STATE and new_state not in (HRM_STATE, REJECTED) and not recommended_salary
