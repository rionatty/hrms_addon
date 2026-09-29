# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Advance workflow.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (leave_advances.setup_on_migrate).

    Draft (raised from the approved leave by the HR Officer, or by itself)
      --Submit--> Pending Accounts Manager
      --Approve--> Approved (submitted: the Leave Advance Processing picks
                             it up for the Payroll Officer's file)
      --Return--> Draft (the Accounts Manager says what to change)
      --Reject--> Rejected (the Accounts Manager says why)
    Approved --Cancel--> Cancelled (only while it is not yet paid)

After approval the advance's own status follows the money: In Processing
on a run, Paid once Finance submit the bank entry, then Recovering and
Recovered as the payroll takes it back.
"""

DOCTYPE = "Leave Advance"
WORKFLOW_NAME = "Leave Advance"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_ACCOUNTS_MANAGER = "Pending Accounts Manager"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager")
ACCOUNTS_MANAGER = "Accounts Manager"
HRM = "HR Manager"
NEW_ROLES = ("Payroll Officer", "Finance Officer")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_ACCOUNTS_MANAGER,)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_ACCOUNTS_MANAGER, "allow_edit": ACCOUNTS_MANAGER, "status": PENDING_ACCOUNTS_MANAGER,
     "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": ACCOUNTS_MANAGER, "status": APPROVED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    {"state": REJECTED, "allow_edit": ACCOUNTS_MANAGER, "status": REJECTED, "style": "Danger", "send_email": 0},
    *({"state": CANCELLED, "allow_edit": role, "status": CANCELLED, "style": "Danger", "send_email": 0,
       "doc_status": "2"} for role in (HRM, ACCOUNTS_MANAGER)),
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_ACCOUNTS_MANAGER, "allowed": role}
      for role in PREPARERS),
    {"state": PENDING_ACCOUNTS_MANAGER, "action": APPROVE, "next_state": APPROVED, "allowed": ACCOUNTS_MANAGER},
    {"state": PENDING_ACCOUNTS_MANAGER, "action": RETURN, "next_state": DRAFT, "allowed": ACCOUNTS_MANAGER},
    {"state": PENDING_ACCOUNTS_MANAGER, "action": REJECT, "next_state": REJECTED, "allowed": ACCOUNTS_MANAGER},
    *({"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": role}
      for role in (HRM, ACCOUNTS_MANAGER)),
)

STAMPS = {PENDING_ACCOUNTS_MANAGER: ("accounts_manager_by", "accounts_manager_on")}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {PENDING_ACCOUNTS_MANAGER: ACCOUNTS_MANAGER}


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
    """facts: "remarks" (the Accounts Manager's), "qualifies"."""
    if old_state == new_state:
        return []
    if new_state in (REJECTED, DRAFT) and old_state == PENDING_ACCOUNTS_MANAGER \
            and not _text(facts.get("remarks")):
        return ["Write the Accounts Manager's remarks saying why."]
    if new_state in (PENDING_ACCOUNTS_MANAGER, APPROVED) and not facts.get("qualifies"):
        return ["The employee does not qualify for this leave advance (see Why Not)."]
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
