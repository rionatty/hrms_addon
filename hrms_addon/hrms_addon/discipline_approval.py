# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Disciplinary Case workflow (5.3).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (discipline.setup_workflows_on_migrate).

    Draft (the HR Officer, from what the supervisor reported)
      --Investigate--> Under Investigation  (an officer is appointed)
      --Charge--> Charge Issued             (the Notice to Answer goes out)
      --Schedule--> Hearing Scheduled       (at least 48 hours ahead)
      --Decide--> Decided (submitted: the sanction stands and, where it is
                           a dismissal, the termination process follows)
    Under Investigation --No Case--> Closed (the chart's "Incident
                           happened? No", which ends the case)
    any state before the decision --Return--> Draft

Separation of duties is not a state but a rule, and it is in
discipline_rules: the investigating officer is never on the panel, and an
appeal is heard by someone who has not already acted.
"""

DOCTYPE = "Disciplinary Case"
WORKFLOW_NAME = "Disciplinary Case"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
INVESTIGATING = "Under Investigation"
CHARGED = "Charge Issued"
HEARING = "Hearing Scheduled"
DECIDED = "Decided"
CLOSED = "Closed"
CANCELLED = "Cancelled"

INVESTIGATE = "Investigate"
CHARGE = "Charge"
SCHEDULE = "Schedule Hearing"
DECIDE = "Decide"
NO_CASE = "No Case"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (INVESTIGATE, CHARGE, SCHEDULE, DECIDE, NO_CASE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
HR_OFFICER, HRM = "HR User", "HR Manager"
OFFICER = "Investigating Officer"
PANEL = "Disciplinary Panel"
EHS = "EHS Officer"
NEW_ROLES = (OFFICER, PANEL, EHS)
PERMISSIONS = {}

PENDING_STATES = (INVESTIGATING, CHARGED, HEARING)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in PREPARERS),
    *({"state": INVESTIGATING, "allow_edit": role, "status": INVESTIGATING, "style": "Warning",
       "send_email": 1} for role in (OFFICER, HR_OFFICER, HRM)),
    *({"state": CHARGED, "allow_edit": role, "status": CHARGED, "style": "Warning", "send_email": 1}
      for role in PREPARERS),
    *({"state": HEARING, "allow_edit": role, "status": HEARING, "style": "Warning", "send_email": 1}
      for role in (PANEL, HR_OFFICER, HRM)),
    *({"state": DECIDED, "allow_edit": role, "status": DECIDED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (PANEL, HRM)),
    {"state": CLOSED, "allow_edit": HRM, "status": CLOSED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": INVESTIGATE, "next_state": INVESTIGATING, "allowed": role}
      for role in PREPARERS),
    # "Incident happened? No" — the case ends there
    *({"state": INVESTIGATING, "action": NO_CASE, "next_state": CLOSED, "allowed": role}
      for role in (OFFICER, HR_OFFICER, HRM)),
    *({"state": INVESTIGATING, "action": CHARGE, "next_state": CHARGED, "allowed": role}
      for role in (OFFICER, HR_OFFICER, HRM)),
    *({"state": INVESTIGATING, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": CHARGED, "action": SCHEDULE, "next_state": HEARING, "allowed": role}
      for role in PREPARERS),
    *({"state": CHARGED, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in PREPARERS),
    *({"state": HEARING, "action": DECIDE, "next_state": DECIDED, "allowed": role}
      for role in (PANEL, HRM)),
    *({"state": HEARING, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": DECIDED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    INVESTIGATING: ("investigated_by", "investigated_on"),
    CHARGED: ("charged_by", "charged_on"),
    HEARING: ("decided_by", "decided_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    INVESTIGATING: ("investigation_report", "Investigating Officer"),
    CHARGED: ("charge_remarks", "HR Officer"),
    HEARING: ("hearing_minutes", "Disciplinary Panel"),
}
ROLE_WAITING = {INVESTIGATING: OFFICER, CHARGED: HR_OFFICER, HEARING: PANEL}


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
    """Problems with a step, as user-facing messages. What each step must
    carry is in discipline_rules; this is only the returning and the order.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the case.")
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
