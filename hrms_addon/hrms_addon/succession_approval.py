# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Succession Position workflow (test cases 11 to 14).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (talent.setup_workflows_on_migrate).

    Draft (HR or the council: the role, the incumbent, the risk)
      --Open Nominations--> Nominations Open
                            (the line manager names successors from the
                             finalised talent pool and rates each one)
      --Send to Council--> Council Review
      --Confirm--> Confirmed (submitted: where the bench has nobody ready
                   now and the council confirms the gap, a job opening is
                   raised in resourcing and the development needs go to
                   L&D)
    Nominations Open or Council Review --Return--> Draft

The coverage — covered, at risk, or a gap — is worked out from the bench,
not typed. The council confirms the gap; the system does not confirm it for
them, because raising a job opening against a live incumbent is not a thing
to do quietly.
"""

DOCTYPE = "Succession Position"
WORKFLOW_NAME = "Succession Position"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
NOMINATIONS = "Nominations Open"
COUNCIL_REVIEW = "Council Review"
CONFIRMED = "Confirmed"
CANCELLED = "Cancelled"

OPEN_NOMINATIONS = "Open Nominations"
TO_COUNCIL = "Send to Council"
CONFIRM = "Confirm"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (OPEN_NOMINATIONS, TO_COUNCIL, CONFIRM, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
HOD = "Head of Department"
SUPERVISOR = "Supervisor"
COUNCIL = "Talent Council"
NEW_ROLES = (COUNCIL,)
PERMISSIONS = {}

HR = (HR_OFFICER, HRM)
MANAGERS = (SUPERVISOR, HOD)
PENDING_STATES = (NOMINATIONS, COUNCIL_REVIEW)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in HR + (COUNCIL,)),
    *({"state": NOMINATIONS, "allow_edit": role, "status": NOMINATIONS, "style": "Warning",
       "send_email": 1} for role in MANAGERS + HR),
    *({"state": COUNCIL_REVIEW, "allow_edit": role, "status": COUNCIL_REVIEW, "style": "Warning",
       "send_email": 1} for role in (COUNCIL, HRM)),
    *({"state": CONFIRMED, "allow_edit": role, "status": CONFIRMED, "style": "Success",
       "send_email": 0, "doc_status": "1"} for role in (COUNCIL, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": OPEN_NOMINATIONS, "next_state": NOMINATIONS, "allowed": role}
      for role in HR + (COUNCIL,)),
    *({"state": NOMINATIONS, "action": TO_COUNCIL, "next_state": COUNCIL_REVIEW, "allowed": role}
      for role in MANAGERS + HR),
    *({"state": NOMINATIONS, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in HR),
    *({"state": COUNCIL_REVIEW, "action": CONFIRM, "next_state": CONFIRMED, "allowed": role}
      for role in (COUNCIL, HRM)),
    *({"state": COUNCIL_REVIEW, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (COUNCIL, HRM)),
    {"state": CONFIRMED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    NOMINATIONS: ("nominated_by", "nominated_on"),
    COUNCIL_REVIEW: ("confirmed_by", "confirmed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {NOMINATIONS: HOD, COUNCIL_REVIEW: COUNCIL}


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
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right.")
    if old_state == NOMINATIONS and new_state == COUNCIL_REVIEW:
        if not (facts.get("candidates") or []) and not facts.get("gap_notes"):
            errors.append("There are no successors named. Write in the council's note why the "
                          "role goes forward with an empty bench.")
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
