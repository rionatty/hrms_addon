# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Graduate Trainee Program workflow (test cases 16 to 20).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (talent.setup_workflows_on_migrate).

    Recruited (made from the job applicant on hire)
      --Induct--> In Induction      (a mentor, a cohort, the checklist)
      --Start Rotation--> In Rotation
      --Assess--> Under Assessment  (a milestone appraisal is raised in the
                                     performance module)
      --Pass--> In Rotation         (back out for the next stint)
      --Confirm--> Confirmed (submitted: the Employee record is created,
                   and the trainee enters the grid and the succession pool)
      --Fail--> Exited (submitted)

A trainee goes round the rotation-to-assessment loop as many times as there
are milestones, which is why Pass returns to In Rotation rather than
ending anywhere. Only the last milestone confirms.
"""

DOCTYPE = "Graduate Trainee Program"
WORKFLOW_NAME = "Graduate Trainee Program"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

RECRUITED = "Recruited"
IN_INDUCTION = "In Induction"
IN_ROTATION = "In Rotation"
UNDER_ASSESSMENT = "Under Assessment"
CONFIRMED = "Confirmed"
EXITED = "Exited"
CANCELLED = "Cancelled"

INDUCT = "Induct"
START_ROTATION = "Start Rotation"
ASSESS = "Assess"
PASS = "Pass"
CONFIRM = "Confirm"
FAIL = "Fail"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (INDUCT, START_ROTATION, ASSESS, PASS, CONFIRM, FAIL, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
SUPERVISOR = "Supervisor"
HOD = "Head of Department"
MENTOR = "Mentor"
COUNCIL = "Talent Council"
NEW_ROLES = (MENTOR, COUNCIL)
PERMISSIONS = {}

HR = (HR_OFFICER, HRM)
PENDING_STATES = (IN_INDUCTION, IN_ROTATION, UNDER_ASSESSMENT)

STATES = (
    *({"state": RECRUITED, "allow_edit": role, "status": RECRUITED, "style": "", "send_email": 0}
      for role in HR),
    *({"state": IN_INDUCTION, "allow_edit": role, "status": IN_INDUCTION, "style": "Warning",
       "send_email": 1} for role in HR + (MENTOR,)),
    *({"state": IN_ROTATION, "allow_edit": role, "status": IN_ROTATION, "style": "Warning",
       "send_email": 1} for role in HR + (MENTOR, SUPERVISOR)),
    *({"state": UNDER_ASSESSMENT, "allow_edit": role, "status": UNDER_ASSESSMENT,
       "style": "Warning", "send_email": 1} for role in HR + (SUPERVISOR, HOD)),
    *({"state": CONFIRMED, "allow_edit": role, "status": CONFIRMED, "style": "Success",
       "send_email": 0, "doc_status": "1"} for role in (HRM, COUNCIL)),
    {"state": EXITED, "allow_edit": HRM, "status": EXITED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": RECRUITED, "action": INDUCT, "next_state": IN_INDUCTION, "allowed": role}
      for role in HR + (MENTOR,)),
    *({"state": IN_INDUCTION, "action": START_ROTATION, "next_state": IN_ROTATION,
       "allowed": role} for role in HR + (SUPERVISOR,)),
    *({"state": IN_INDUCTION, "action": RETURN, "next_state": RECRUITED, "allowed": role}
      for role in HR),
    *({"state": IN_ROTATION, "action": ASSESS, "next_state": UNDER_ASSESSMENT, "allowed": role}
      for role in HR + (SUPERVISOR, HOD)),
    *({"state": UNDER_ASSESSMENT, "action": PASS, "next_state": IN_ROTATION, "allowed": role}
      for role in HR + (HOD,)),
    *({"state": UNDER_ASSESSMENT, "action": CONFIRM, "next_state": CONFIRMED, "allowed": role}
      for role in (HRM, COUNCIL)),
    *({"state": UNDER_ASSESSMENT, "action": FAIL, "next_state": EXITED, "allowed": role}
      for role in (HRM, COUNCIL)),
    {"state": CONFIRMED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
    {"state": EXITED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    RECRUITED: ("inducted_by", "inducted_on"),
    UNDER_ASSESSMENT: ("confirmed_by", "confirmed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {IN_INDUCTION: MENTOR, IN_ROTATION: SUPERVISOR, UNDER_ASSESSMENT: HOD}


def compute_stamps(old_state, new_state, user, today, current):
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == RECRUITED:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    if old_state == new_state:
        return []
    errors = []
    if new_state == RECRUITED and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right.")
    if new_state == EXITED and not _text(facts.get("exit_reason")):
        errors.append("Say why the trainee leaves the programme.")
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
