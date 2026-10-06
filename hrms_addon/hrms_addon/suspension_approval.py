# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Suspension workflow: signed as Luuka's Suspension Letter is
signed.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (suspensions.setup_workflows_on_migrate).

    Draft (the HR Officer, by hand or from a Disciplinary Case decided at
           the Suspension rung)
      --Send to HR Manager--> Pending HR Manager (who witnesses the letter)
      --Approve--> Pending General Manager (who signs it)
      --Approve--> Approved (submitted: the days are marked on the
                   attendance and the employee is Suspended while it runs)
    Pending HR Manager or Pending General Manager --Return--> Draft
    Approved --Cancel--> Cancelled (the HR Manager: the days are taken off
                   the attendance and the employee is Active again)

Each signature is stamped with who and when; a return clears them all and
says why.
"""

DOCTYPE = "Employee Suspension"
WORKFLOW_NAME = "Employee Suspension Approval"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
PENDING_HRM = "Pending HR Manager"
PENDING_GM = "Pending General Manager"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SEND = "Send to HR Manager"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SEND, APPROVE, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
GM = "General Manager"
NEW_ROLES = (GM,)
# the General Manager's approval files the suspension, which takes submit
PERMISSIONS = {DOCTYPE: {GM: ("read", "write", "submit", "print")}}

HR = (HR_OFFICER, HRM)
PENDING_STATES = (PENDING_HRM, PENDING_GM)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in HR),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (GM, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_HRM, "allowed": role} for role in HR),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_GM, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_GM, "action": APPROVE, "next_state": APPROVED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# the signature each step leaves, stamped as the suspension leaves that step
STAMPS = {
    DRAFT: ("prepared_by", "prepared_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
    PENDING_GM: ("gm_by", "gm_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# who is waiting at each step, and the remarks that step writes
ROLE_WAITING = {PENDING_HRM: HRM, PENDING_GM: GM}
REMARK_FIELDS = {PENDING_HRM: "hrm_remarks", PENDING_GM: "gm_remarks"}


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after a step: the leaving step stamped with who and
    when; a return to Draft clears them all, as the letter starts over."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """What a step needs. facts: "return_remarks", and "errors", what the
    suspension itself still lacks (suspension_rules.suspension_errors)."""
    if old_state == new_state:
        return []
    if new_state == DRAFT and old_state in PENDING_STATES:
        return [] if _text(facts.get("return_remarks")) else ["Write in Return Remarks what must be put right."]
    if new_state in PENDING_STATES + (APPROVED,):
        return list(facts.get("errors") or [])
    return []


def next_states(state, roles):
    roles = set(roles or ())
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))
