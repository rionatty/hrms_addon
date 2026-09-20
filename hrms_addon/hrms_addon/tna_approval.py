# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Needs Assessment workflow: the HR Officer's assessment approved
by the HR Manager, then the General Manager (the flowchart's step 4 and the
test script's case 3).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (training.setup_workflows_on_migrate).

    Draft --Submit for Approval--> Pending HR Manager
      --Approve--> Pending General Manager --Approve--> Approved (submitted)
    Pending HR Manager / Pending General Manager --Return--> Draft
      (the reason in Return Remarks; the author amends and resubmits)
    Approved --Cancel--> Cancelled
"""

DOCTYPE = "Training Needs Assessment"
WORKFLOW_NAME = "Training Needs Assessment"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_HRM = "Pending HR Manager"
PENDING_GM = "Pending General Manager"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SUBMIT = "Submit for Approval"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
HRM, GM = "HR Manager", "General Manager"
NEW_ROLES = ("General Manager",)
PERMISSIONS = {}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HRM, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_GM, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_GM, "action": APPROVE, "next_state": APPROVED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {PENDING_HRM: ("hrm_by", "hrm_on"), PENDING_GM: ("gm_by", "gm_on")}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step passed forward is signed by
    `user` today; a return clears every signature (the assessment starts its
    approval again); a typed signature reverts to what it was."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state in STAMPS and new_state != CANCELLED:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts: what training_rules.assessment_errors reads, plus "return_remarks".
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == PENDING_HRM and old_state in (None, DRAFT):
        errors += facts.get("assessment_errors") or []
    if new_state == DRAFT and old_state in (PENDING_HRM, PENDING_GM) and not (facts.get("return_remarks") or "").strip():
        errors.append("Write in Return Remarks what the HR Officer should amend before returning the assessment.")
    return errors
