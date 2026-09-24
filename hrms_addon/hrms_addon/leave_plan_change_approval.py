# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Plan Change workflow: one planned leave moved to new dates.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (leave.setup_workflows_on_migrate).

    Draft (the employee, or HR for them)
      --Submit--> Pending Supervisor
      --Approve--> Pending HOD
      --Approve--> Approved (submitted: the plan takes the new dates)
    either Pending state --Reject--> Rejected, or --Return--> Draft, with
    the remarks saying why
"""

DOCTYPE = "Leave Plan Change"
WORKFLOW_NAME = "Leave Plan Change"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HOD = "Pending HOD"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
REJECT = "Reject"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, REJECT, RETURN, CANCEL)

PREPARERS = ("Employee", "HR User", "HR Manager")
SUPERVISOR = "Supervisor"
HOD = "Head of Department"
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HOD)
REMARKS = {PENDING_SUPERVISOR: "supervisor_remarks", PENDING_HOD: "hod_remarks"}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_SUPERVISOR, "allow_edit": SUPERVISOR, "status": PENDING_SUPERVISOR, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": HOD, "status": APPROVED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    *({"state": REJECTED, "allow_edit": role, "status": REJECTED, "style": "Danger", "send_email": 0}
      for role in (SUPERVISOR, HOD)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    {"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HOD, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": SUPERVISOR},
    {"state": PENDING_HOD, "action": APPROVE, "next_state": APPROVED, "allowed": HOD},
    {"state": PENDING_HOD, "action": REJECT, "next_state": REJECTED, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on"), PENDING_HOD: ("hod_by", "hod_on")}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {PENDING_SUPERVISOR: SUPERVISOR, PENDING_HOD: HOD}


def compute_stamps(old_state, new_state, user, today, current):
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
    """facts: "supervisor_remarks", "hod_remarks"."""
    if old_state == new_state or old_state not in REMARKS:
        return []
    if new_state in (REJECTED, DRAFT) and not _text(facts.get(REMARKS[old_state])):
        return ["Write the remarks saying why."]
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
    return (value or "").strip()
