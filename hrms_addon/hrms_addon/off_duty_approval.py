# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Off Duty Request workflow: the two signatures LPL/HR/25 carries.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (attendance.setup_workflows_on_migrate).

The paper is signed by the Supervisor and then the Section Manager, and
ends with "Remarks for Human Resource Manager", so:

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor
      --Approve--> Pending Section Manager
      --Approve--> Pending HR Manager
      --Approve--> Approved (submitted: the day is marked off duty)
    any Pending state --Return--> Draft (the reason in Return Remarks,
                                  which clears every signature)
    any Pending state --Reject--> Rejected
"""

DOCTYPE = "Off Duty Request"
WORKFLOW_NAME = "Off Duty Request"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_MANAGER = "Pending Section Manager"
PENDING_HRM = "Pending HR Manager"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
SUPERVISORS = ("Supervisor", "Head of Department")
MANAGER, HRM = "Head of Department", "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_MANAGER, PENDING_HRM)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning",
       "send_email": 1} for role in SUPERVISORS),
    {"state": PENDING_MANAGER, "allow_edit": MANAGER, "status": PENDING_MANAGER, "style": "Warning", "send_email": 1},
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_MANAGER, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in SUPERVISORS),
    {"state": PENDING_MANAGER, "action": APPROVE, "next_state": PENDING_HRM, "allowed": MANAGER},
    {"state": PENDING_MANAGER, "action": RETURN, "next_state": DRAFT, "allowed": MANAGER},
    {"state": PENDING_MANAGER, "action": REJECT, "next_state": REJECTED, "allowed": MANAGER},
    {"state": PENDING_HRM, "action": APPROVE, "next_state": APPROVED, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_HRM, "action": REJECT, "next_state": REJECTED, "allowed": HRM},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on"),
    PENDING_MANAGER: ("manager_by", "manager_on"),
    PENDING_HRM: ("hr_by", "hr_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("supervisor_remarks", "Supervisor"),
    PENDING_MANAGER: ("manager_remarks", "Section Manager"),
    PENDING_HRM: ("hr_remarks", "HR Manager"),
}
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISORS[0],
    PENDING_MANAGER: MANAGER,
    PENDING_HRM: HRM,
}


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step just passed forward is
    signed by `user` today, a return to Draft clears them all, and anything
    typed into a signature reverts to what it was (`current`)."""
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
    """Problems with a step, as user-facing messages."""
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the request.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the day off is refused." % who)
    return errors


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def _text(value):
    return (value or "").strip()
