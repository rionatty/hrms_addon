# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Salary Advance Request workflow.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (salary_advances.setup_on_migrate).

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor   (the Section In-Charge or Supervisor)
      --Approve--> Approved (submitted: the request is active and each
                             month's Salary Advance Processing picks it up)
      --Reject--> Rejected (the supervisor says why)
      --Return--> Draft (the supervisor says what to change)
"""

DOCTYPE = "Salary Advance Request"
WORKFLOW_NAME = "Salary Advance Request"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
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
SUPERVISORS = ("Supervisor", "Head of Department")
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department", "Payroll Officer")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_SUPERVISOR,)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning",
       "send_email": 1} for role in SUPERVISORS),
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in SUPERVISORS),
    *({"state": REJECTED, "allow_edit": role, "status": REJECTED, "style": "Danger", "send_email": 0}
      for role in SUPERVISORS),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": APPROVED, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in SUPERVISORS),
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on")}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {PENDING_SUPERVISOR: "Supervisor"}


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
    """facts: "supervisor_remarks"."""
    if old_state == new_state:
        return []
    if new_state in (REJECTED, DRAFT) and old_state == PENDING_SUPERVISOR \
            and not _text(facts.get("supervisor_remarks")):
        return ["Write the supervisor's remarks saying why."]
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
