# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Annual Leave Plan workflow: steps 1 to 3 of the leave process.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (leave.setup_workflows_on_migrate).

    Draft (the HR Officer draws it up at the end of the year)
      --Submit--> Pending HOD   (each department head approves their own)
      --Approve--> Pending HR Officer
      --Approve--> Approved     (submitted: the HR Officer then tells every
                                 employee their dates, and the system starts
                                 watching for them falling due)
    either Pending state --Return--> Draft (the reason in Return Remarks)
"""

DOCTYPE = "Annual Leave Plan"
WORKFLOW_NAME = "Annual Leave Plan"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_HOD = "Pending HOD"
PENDING_HR = "Pending HR Officer"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
HOD = "Head of Department"
HR_OFFICER = "HR User"
HRM = "HR Manager"
NEW_ROLES = ("Head of Department",)
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_HOD, PENDING_HR)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in PREPARERS),
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HOD, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HR, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    *({"state": PENDING_HR, "action": APPROVE, "next_state": APPROVED, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in PREPARERS),
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_HOD: ("hod_by", "hod_on"),
    PENDING_HR: ("hr_by", "hr_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_HOD: ("hod_remarks", "Head of Department"),
    PENDING_HR: ("hr_remarks", "HR Officer"),
}
ROLE_WAITING = {PENDING_HOD: HOD, PENDING_HR: HR_OFFICER}


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
            errors.append("Write in Return Remarks what must be put right before returning the plan.")
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
