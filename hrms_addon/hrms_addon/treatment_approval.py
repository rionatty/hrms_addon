# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Medical Treatment Order workflow: review item 11 (Luuka, 5 Nov 2026):
"Under safety, need a provision for medical treatment order, one employee
uses to access the hospital treatment."

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (safety.setup_workflows_on_migrate).

    Draft (the supervisor, the head of department, HR or the EHS Officer;
           from a safety incident, or on its own for a sickness at work)
      --Send to EHS Officer--> Pending EHS Officer (the plant's own, named as
                 on the safety incident: nobody picks another)
      --Issue--> Issued (submitted: the employee takes the printed order to
                 the hospital, and where transport is needed the plant's
                 accountant is asked to pay it in cash)
    Pending EHS Officer --Return--> Draft (Return Remarks)
    Issued --Cancel--> Cancelled (the HR Manager)

The plant's EHS Officer issues it, or the HR Manager when the officer is
away (review item 12: "Need make their approval fixed"). No state sends
Frappe's own workflow email: the glue tells the officer and the accountant
by name.
"""

DOCTYPE = "Medical Treatment Order"
WORKFLOW_NAME = "Medical Treatment Order"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
PENDING_EHS = "Pending EHS Officer"
ISSUED = "Issued"
CANCELLED = "Cancelled"

SEND = "Send to EHS Officer"
ISSUE = "Issue"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SEND, ISSUE, RETURN, CANCEL)

EHS = "EHS Officer"
HR_OFFICER, HRM = "HR User", "HR Manager"
REPORTERS = ("Supervisor", "Head of Department", HR_OFFICER, HRM, EHS)
OFFICERS = (EHS, HRM)
NEW_ROLES = (EHS, "Supervisor", "Head of Department")
# the order is ours: who may do what is in its DocType
PERMISSIONS = {}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in REPORTERS),
    *({"state": PENDING_EHS, "allow_edit": role, "status": PENDING_EHS, "style": "Warning", "send_email": 0}
      for role in OFFICERS),
    *({"state": ISSUED, "allow_edit": role, "status": ISSUED, "style": "Success", "send_email": 0, "doc_status": "1"}
      for role in OFFICERS),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_EHS, "allowed": role} for role in REPORTERS),
    *({"state": PENDING_EHS, "action": ISSUE, "next_state": ISSUED, "allowed": role} for role in OFFICERS),
    *({"state": PENDING_EHS, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in OFFICERS),
    {"state": ISSUED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {PENDING_EHS: ("issued_by", "issued_on")}
ALL_STAMP_FIELDS = ("issued_by", "issued_on")
OFFICER_STATES = (DRAFT, PENDING_EHS)
PENDING_STATES = (PENDING_EHS,)
ROLE_WAITING = {PENDING_EHS: EHS}


def officer_fixed(old_state, new_state):
    """Whether the save names the plant's EHS Officer again: until the
    order is issued, and as it is."""
    return new_state in OFFICER_STATES or old_state in OFFICER_STATES


def compute_stamps(old_state, new_state, user, today, current):
    """Who issued the order, and when. current: as saved, never as typed."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == PENDING_EHS and new_state == ISSUED:
        values.update(issued_by=user, issued_on=today)
    elif old_state != new_state and new_state == DRAFT:
        values = dict.fromkeys(ALL_STAMP_FIELDS)
    return values


def step_errors(old_state, new_state, facts):
    """Who may take a step. facts: "user", "is_hrm", "ehs_officer",
    "branch", "return_remarks". What the order must say is
    safety_rules.order_errors, on every save past Draft."""
    if old_state == new_state or not new_state:
        return []
    user, officer = facts.get("user"), facts.get("ehs_officer")
    plant = facts.get("branch") or "the employee's"
    errors = []
    if new_state == PENDING_EHS and not officer:
        errors.append("No EHS Officer serves the %s plant: give one the EHS Officer role and a Branch User "
                      "Permission for the plant." % plant)
    if old_state == PENDING_EHS:
        if not (bool(user) and (user == officer or bool(facts.get("is_hrm")))):
            errors.append("The treatment order is for %s, the %s plant's EHS Officer, to issue or return (or the "
                          "HR Manager)." % (officer or "the EHS Officer", plant))
        if new_state == DRAFT and not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the order.")
    return errors


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
