# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Report approval: prepared by HR, "Thru: Human Resource Manager",
"Forwarded to: the Executive Director", the way Luuka's interview report is
routed on paper.

No Frappe import, like requisition_approval.py, so scripts/verify_interviews.py
walks every path without a bench. workflows.py builds the Workflow from it on
every migrate (interviews.setup_report_workflow_on_migrate).

    Draft --Submit for Approval--> Pending HR Manager --Approve--> Pending Executive Director
    Pending Executive Director --Approve--> Approved (submitted)
    Pending HR Manager / Pending Executive Director --Reject--> Rejected --Revise--> Draft
    Approved --Cancel--> Cancelled (the HR Manager)

Approval closes the day's interviews and moves each applicant on
(interviews.close_report). Cancelling the report undoes neither: the
interviews' results stand. The Cancel step exists because Frappe's own
Cancel leaves a workflow's state as it was, so the report would go on
showing Approved.
"""

DOCTYPE = "Interview Report"
WORKFLOW_NAME = "Interview Report Approval"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_HRM = "Pending HR Manager"
PENDING_ED = "Pending Executive Director"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

# The same action names as the requisition's, so both workflows share them
SUBMIT = "Submit for Approval"
APPROVE = "Approve"
REJECT = "Reject"
REVISE = "Revise"
# ... and the shortlist's
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, REJECT, REVISE, CANCEL)

# Who prepares a report (the paper's "Prepared by"), edits it and sends it on
PREPARERS = ("HR User", "HR Manager")
# Who may cancel an approved report (the DocType gives only them cancel)
CANCELLER = "HR Manager"

# The requisition workflow creates this role too; ensured here as well so the
# report does not depend on it
NEW_ROLES = ("Executive Director",)

# Frappe submits the report when the Executive Director approves it, so the
# role needs submit. HR's own roles are in the DocType.
PERMISSIONS = {DOCTYPE: {"Executive Director": ("read", "write", "submit")}}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_HRM, "allow_edit": "HR Manager", "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": "Executive Director", "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": "Executive Director", "status": APPROVED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    *({"state": REJECTED, "allow_edit": role, "status": REJECTED, "style": "Danger", "send_email": 0} for role in PREPARERS),
    {"state": CANCELLED, "allow_edit": CANCELLER, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HRM, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_ED, "allowed": "HR Manager"},
    {"state": PENDING_HRM, "action": REJECT, "next_state": REJECTED, "allowed": "HR Manager"},
    {"state": PENDING_ED, "action": APPROVE, "next_state": APPROVED, "allowed": "Executive Director"},
    {"state": PENDING_ED, "action": REJECT, "next_state": REJECTED, "allowed": "Executive Director"},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": CANCELLER},
    *({"state": REJECTED, "action": REVISE, "next_state": DRAFT, "allowed": role} for role in PREPARERS),
)

# The report's sign-off block: who moved it on from each step, and when
STAMPS = {
    PENDING_HRM: ("hrm_approver", "hrm_approved_on"),
    PENDING_ED: ("ed_approver", "ed_approved_on"),
}
STAMP_FIELDS = ("hrm_approver", "hrm_approved_on", "ed_approver", "ed_approved_on")


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    return [(t["action"], t["next_state"]) for t in TRANSITIONS if t["state"] == state and t["allowed"] in roles]


def compute_stamps(old_state, new_state, user, today, current):
    """Every sign-off field's value after this save.

    Approving out of Pending HR Manager records the HR Manager; approving out
    of Pending Executive Director records the Executive Director. A revised
    report starts its approvals again, a new one has none, and otherwise the
    stored values stand, so a date typed in (or posted through the API) does
    not survive the save.

    current: {field: value} as stored before this save ({} for a new report).
    """
    if not old_state:
        return dict.fromkeys(STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in STAMP_FIELDS}
    if old_state == new_state:
        return values
    if old_state == REJECTED and new_state == DRAFT:
        return dict.fromkeys(STAMP_FIELDS)
    if old_state in STAMPS and new_state != REJECTED:
        who, when = STAMPS[old_state]
        values[who], values[when] = user, today
    return values


def leaves_draft(new_state):
    """Past Draft (sent for approval, approved or rejected), the report must be complete."""
    return bool(new_state) and new_state != DRAFT
