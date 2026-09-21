# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent Program workflow (test cases 1 to 3).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (talent.setup_workflows_on_migrate).

    Draft (HR, or drawn up automatically when a placement is finalised)
      --Enrol--> Enrolled       (the employee is on the programme; the
                                 training goes to L&D)
      --Start--> In Programme
      --Review--> Under Review  (the HR Officer reads the appraisal since
                                 it ended against the one before it)
      --Close--> Closed (submitted, with the decision recorded)
    Enrolled, In Programme or Under Review --Return--> Draft

The decision at the end — succession pipeline, promotion or replacement —
is the chart's last box, and it is taken on the review, not on the grid.
"""

DOCTYPE = "Talent Program"
WORKFLOW_NAME = "Talent Program"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
ENROLLED = "Enrolled"
RUNNING = "In Programme"
UNDER_REVIEW = "Under Review"
CLOSED = "Closed"
CANCELLED = "Cancelled"

ENROL = "Enrol"
START = "Start"
REVIEW = "Review"
CLOSE = "Close"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (ENROL, START, REVIEW, CLOSE, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
HOD = "Head of Department"
COUNCIL = "Talent Council"
MENTOR = "Mentor"
NEW_ROLES = (COUNCIL, MENTOR)
PERMISSIONS = {}

HR = (HR_OFFICER, HRM)
PENDING_STATES = (ENROLLED, RUNNING, UNDER_REVIEW)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in HR),
    *({"state": ENROLLED, "allow_edit": role, "status": ENROLLED, "style": "Warning",
       "send_email": 1} for role in HR + (MENTOR, HOD)),
    *({"state": RUNNING, "allow_edit": role, "status": RUNNING, "style": "Warning",
       "send_email": 1} for role in HR + (MENTOR,)),
    *({"state": UNDER_REVIEW, "allow_edit": role, "status": UNDER_REVIEW, "style": "Warning",
       "send_email": 1} for role in HR),
    *({"state": CLOSED, "allow_edit": role, "status": CLOSED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (HRM, COUNCIL)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": ENROL, "next_state": ENROLLED, "allowed": role} for role in HR),
    *({"state": ENROLLED, "action": START, "next_state": RUNNING, "allowed": role}
      for role in HR + (MENTOR,)),
    *({"state": ENROLLED, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in HR),
    *({"state": RUNNING, "action": REVIEW, "next_state": UNDER_REVIEW, "allowed": role}
      for role in HR),
    *({"state": RUNNING, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in HR),
    *({"state": UNDER_REVIEW, "action": CLOSE, "next_state": CLOSED, "allowed": role}
      for role in (HRM, COUNCIL)),
    *({"state": UNDER_REVIEW, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in HR),
    {"state": CLOSED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    DRAFT: ("enrolled_by", "enrolled_on"),
    UNDER_REVIEW: ("reviewed_by", "reviewed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {ENROLLED: MENTOR, RUNNING: MENTOR, UNDER_REVIEW: HR_OFFICER}


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
