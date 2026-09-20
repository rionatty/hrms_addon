# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Calendar workflow: the planner (LPL/TRAINING/01) the HR Officer
draws up from the approved needs, approved by the General Manager. The
Board's approval is recorded on it by date once given.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (training.setup_workflows_on_migrate).

    Draft --Submit for Approval--> Pending General Manager
      --Approve--> Approved (submitted)   --Return--> Draft
    Approved --Cancel--> Cancelled
"""

DOCTYPE = "Training Calendar"
WORKFLOW_NAME = "Training Calendar"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_GM = "Pending General Manager"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SUBMIT = "Submit for Approval"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
GM, HRM = "General Manager", "HR Manager"
NEW_ROLES = ("General Manager",)
PERMISSIONS = {}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_GM, "allowed": role} for role in PREPARERS),
    {"state": PENDING_GM, "action": APPROVE, "next_state": APPROVED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {PENDING_GM: ("gm_by", "gm_on")}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, today, current):
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
    """facts: "entries" (count), "return_remarks"."""
    if old_state == new_state:
        return []
    errors = []
    if new_state == PENDING_GM and old_state in (None, DRAFT) and not facts.get("entries"):
        errors.append("Add the trainings to the calendar (Get Approved Needs, or type them) before sending it for approval.")
    if new_state == DRAFT and old_state == PENDING_GM and not (facts.get("return_remarks") or "").strip():
        errors.append("Write in Return Remarks what should change before returning the calendar.")
    return errors
