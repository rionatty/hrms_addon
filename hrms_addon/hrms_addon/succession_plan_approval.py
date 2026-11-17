# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Succession Plan workflow (the talent blueprint, section 6: "Succession
Plan: Cycle, owner, status, workflow_state").

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (talent.setup_workflows_on_migrate).

    Draft (HR: the year's critical roles gathered, Get Positions)
      --Send to Council--> Council Review
                           (every role in it still nominating goes to the
                            council with it, as one)
      --Finalise--> Finalised (submitted: the council confirms every role in
                    it that it has before it; each confirmation does what a
                    role's own does: successors developed, gaps raised to
                    resourcing)
    Council Review --Return--> Draft

The plan is the council's view of the bench across a year's roles; each
role keeps its own steps and can still be moved on its own.
"""

DOCTYPE = "Succession Plan"
WORKFLOW_NAME = "Succession Plan"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
COUNCIL_REVIEW = "Council Review"
FINALISED = "Finalised"
CANCELLED = "Cancelled"

TO_COUNCIL = "Send to Council"
FINALISE = "Finalise"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (TO_COUNCIL, FINALISE, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
COUNCIL = "Talent Council"
NEW_ROLES = (COUNCIL,)
PERMISSIONS = {}

HR = (HR_OFFICER, HRM)
PENDING_STATES = (COUNCIL_REVIEW,)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in HR + (COUNCIL,)),
    *({"state": COUNCIL_REVIEW, "allow_edit": role, "status": COUNCIL_REVIEW, "style": "Warning",
       "send_email": 1} for role in (COUNCIL, HRM)),
    *({"state": FINALISED, "allow_edit": role, "status": FINALISED, "style": "Success",
       "send_email": 0, "doc_status": "1"} for role in (COUNCIL, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": TO_COUNCIL, "next_state": COUNCIL_REVIEW, "allowed": role}
      for role in HR),
    *({"state": COUNCIL_REVIEW, "action": FINALISE, "next_state": FINALISED, "allowed": role}
      for role in (COUNCIL, HRM)),
    *({"state": COUNCIL_REVIEW, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (COUNCIL, HRM)),
    {"state": FINALISED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    DRAFT: ("sent_by", "sent_on"),
    COUNCIL_REVIEW: ("finalised_by", "finalised_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {COUNCIL_REVIEW: COUNCIL}

# a role's own states (succession_approval.py), as the plan reads them
POSITION_DRAFT, POSITION_NOMINATING, POSITION_REVIEW, POSITION_CONFIRMED = (
    "Draft", "Nominations Open", "Council Review", "Confirmed")


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
    """Why the plan cannot take this step. facts: "return_remarks",
    "positions": [{"succession_position", "state"}]."""
    if old_state == new_state:
        return []
    errors = []
    positions = facts.get("positions") or []
    if new_state == DRAFT and old_state in PENDING_STATES and not _text(facts.get("return_remarks")):
        errors.append("Write in Return Remarks what must be put right.")
    if new_state == COUNCIL_REVIEW:
        if not positions:
            errors.append("There are no critical roles in the plan. Get the positions first.")
        drafts = [row.get("succession_position") for row in positions if row.get("state") == POSITION_DRAFT]
        if drafts:
            errors.append("Nominations have not been opened for: %s. Open them, or take the role out of the plan."
                          % ", ".join(drafts))
    return errors


def to_send(positions):
    """The roles that go to the council with the plan: those still nominating."""
    return [row.get("succession_position") for row in positions or ()
            if row.get("state") == POSITION_NOMINATING]


def to_confirm(positions):
    """The roles the council confirms by finalising the plan: those before it."""
    return [row.get("succession_position") for row in positions or ()
            if row.get("state") == POSITION_REVIEW]


def summary(positions):
    """The plan's figures from its roles' benches."""
    rows = list(positions or ())
    return {
        "total_positions": len(rows),
        "covered": sum(1 for row in rows if row.get("coverage") == "Covered"),
        "at_risk": sum(1 for row in rows if row.get("coverage") == "At Risk"),
        "gaps": sum(1 for row in rows if row.get("coverage") == "Gap"),
        "single_person_roles": sum(1 for row in rows if int(row.get("single_person_role") or 0)),
        "ready_now": sum(int(row.get("ready_now") or 0) for row in rows),
    }


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
