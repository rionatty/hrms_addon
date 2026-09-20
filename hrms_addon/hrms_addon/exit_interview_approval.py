# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Exit Interview workflow (4.5, step 4), on Frappe HR's Exit Interview.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (exits.setup_workflows_on_migrate).

    Draft (the employee fills it in, or HR for someone with no login)
      --Submit--> Pending Supervisor
      --Approve--> Pending HOD
      --Approve--> Pending HR Officer
      --Approve--> Approved (submitted)
    any Pending state --Return--> Draft (the reason in Return Remarks)

Frappe HR's own `status` is theirs — Pending, Scheduled, Completed — so
the chain's state goes in `custom_exit_status` beside it.
"""

DOCTYPE = "Exit Interview"
WORKFLOW_NAME = "Exit Interview"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_exit_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HOD = "Pending HOD"
PENDING_HR = "Pending HR Officer"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
SUPERVISORS = ("Supervisor", "Head of Department")
HOD = "Head of Department"
HR_OFFICER, HRM = "HR User", "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
PERMISSIONS = {
    DOCTYPE: {
        "Supervisor": ("read", "write", "submit"),
        HOD: ("read", "write", "submit"),
        "Employee": ("read", "write"),
    },
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HOD, PENDING_HR)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning",
       "send_email": 1} for role in SUPERVISORS),
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role}
      for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HOD, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in SUPERVISORS),
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HR, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    *({"state": PENDING_HR, "action": APPROVE, "next_state": APPROVED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
    PENDING_HOD: ("custom_hod_by", "custom_hod_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
    PENDING_HOD: ("custom_hod_remarks", "Head of Department"),
    PENDING_HR: ("custom_hr_remarks", "HR Officer"),
}
ROLE_WAITING = {PENDING_SUPERVISOR: SUPERVISORS[0], PENDING_HOD: HOD, PENDING_HR: HR_OFFICER}


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
            errors.append("Write in Return Remarks what must be put right before returning the interview.")
        return errors
    if new_state == PENDING_SUPERVISOR and not _text(facts.get("interview_summary")):
        errors.append("The employee fills the exit interview in before it goes for approval.")
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
