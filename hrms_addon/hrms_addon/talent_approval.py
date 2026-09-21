# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent Placement workflow (test cases 6 to 8).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (talent.setup_workflows_on_migrate).

    Draft (the line manager: the potential assessment and the rationale)
      --Submit--> In Calibration   (the peer group, across the plants)
      --Send to Council--> Council Review
      --Finalise--> Finalised (submitted: the placement locks, the
                    development plan is drawn up and its training goes
                    to L&D)
    Council Review --Return to Calibration--> In Calibration
    In Calibration --Return--> Draft

A submitted placement goes to calibration rather than straight to the
council, because a box means nothing until it has been compared with the
boxes the other plants gave: the same words mean different things in
extrusion and in printing until somebody sits the managers down together.

"Line manager" here is Luuka's Supervisor and Head of Department roles,
which is what the rest of this app calls the two people above an employee.
The Talent Council is new, and so is Mentor.
"""

DOCTYPE = "Talent Placement"
WORKFLOW_NAME = "Talent Placement"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
CALIBRATION = "In Calibration"
COUNCIL_REVIEW = "Council Review"
FINALISED = "Finalised"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
TO_COUNCIL = "Send to Council"
FINALISE = "Finalise"
RETURN_TO_CALIBRATION = "Return to Calibration"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, TO_COUNCIL, FINALISE, RETURN_TO_CALIBRATION, RETURN, CANCEL)

SUPERVISOR = "Supervisor"
HOD = "Head of Department"
HR_OFFICER = "HR User"
HRM = "HR Manager"
COUNCIL = "Talent Council"
MENTOR = "Mentor"
NEW_ROLES = (COUNCIL, MENTOR)
PERMISSIONS = {}

MANAGERS = (SUPERVISOR, HOD)
HR = (HR_OFFICER, HRM)
PENDING_STATES = (CALIBRATION, COUNCIL_REVIEW)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in MANAGERS + HR),
    *({"state": CALIBRATION, "allow_edit": role, "status": CALIBRATION, "style": "Warning",
       "send_email": 1} for role in MANAGERS + HR),
    *({"state": COUNCIL_REVIEW, "allow_edit": role, "status": COUNCIL_REVIEW, "style": "Warning",
       "send_email": 1} for role in (COUNCIL, HRM)),
    *({"state": FINALISED, "allow_edit": role, "status": FINALISED, "style": "Success",
       "send_email": 0, "doc_status": "1"} for role in (COUNCIL, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": CALIBRATION, "allowed": role}
      for role in MANAGERS + HR),
    *({"state": CALIBRATION, "action": TO_COUNCIL, "next_state": COUNCIL_REVIEW, "allowed": role}
      for role in HR),
    *({"state": CALIBRATION, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in HR),
    *({"state": COUNCIL_REVIEW, "action": FINALISE, "next_state": FINALISED, "allowed": role}
      for role in (COUNCIL, HRM)),
    *({"state": COUNCIL_REVIEW, "action": RETURN_TO_CALIBRATION, "next_state": CALIBRATION,
       "allowed": role} for role in (COUNCIL, HRM)),
    {"state": FINALISED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    DRAFT: ("submitted_by", "submitted_on"),
    CALIBRATION: ("calibrated_by", "calibrated_on"),
    COUNCIL_REVIEW: ("finalised_by", "finalised_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {CALIBRATION: HOD, COUNCIL_REVIEW: COUNCIL}


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
    """Problems with a step. What a placement must carry is in
    talent_rules; this is only the returning."""
    if old_state == new_state:
        return []
    errors = []
    if new_state in (DRAFT, CALIBRATION) and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what the placement must have before it comes "
                          "back.")
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
