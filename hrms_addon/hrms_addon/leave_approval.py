# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Application workflow: the three signatures Part 3 of LPL/HR/15 carries.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (leave.setup_workflows_on_migrate).

The form is signed by the Manager in line, then the Head of Department, and
approved last by the HR Officer, which is the chain the revised flow chart
gives as "1st. Immediate supervisor 2nd. HOD 3rd. HR Officer":

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor
      --Approve--> Pending HOD
      --Approve--> Pending HR Officer
      --Approve--> Approved (submitted: the days come off the balance)
    any Pending state --Return--> Draft (the reason in Return Remarks,
                                  which clears every signature)
    any Pending state --Reject--> Rejected

Frappe HR's own `status` stays Open / Approved / Rejected, because its
controller and its leave ledger read it; the workflow's own state goes in
`custom_leave_status` beside it (leave.py keeps the two in step).
"""

DOCTYPE = "Leave Application"
WORKFLOW_NAME = "Leave Application"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_leave_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HOD = "Pending HOD"
PENDING_HR = "Pending HR Officer"
APPROVED = "Approved"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
SUPERVISORS = ("Supervisor", "Head of Department")
HOD = "Head of Department"
HR_OFFICER = "HR User"
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
PERMISSIONS = {
    DOCTYPE: {
        "Supervisor": ("read", "write", "submit"),
        HOD: ("read", "write", "submit"),
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
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HOD, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in SUPERVISORS),
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HR, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    {"state": PENDING_HOD, "action": REJECT, "next_state": REJECTED, "allowed": HOD},
    *({"state": PENDING_HR, "action": APPROVE, "next_state": APPROVED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on).
# Part 3 of LPL/HR/15: Manager in line, Head of Dept, Approved By.
STAMPS = {
    PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
    PENDING_HOD: ("custom_hod_by", "custom_hod_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Manager in line"),
    PENDING_HOD: ("custom_hod_remarks", "Head of Department"),
    PENDING_HR: ("custom_hr_remarks", "HR Officer"),
}
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISORS[0],
    PENDING_HOD: HOD,
    PENDING_HR: HR_OFFICER,
}
# Frappe HR's own status, which its controller and its ledger read
UPSTREAM_STATUS = {APPROVED: "Approved", REJECTED: "Rejected", CANCELLED: "Cancelled"}


def upstream_status(state):
    """Frappe HR's `status` for a workflow state: everything before the end
    is still Open to them, because nothing has been decided yet."""
    return UPSTREAM_STATUS.get(state, "Open")


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step just passed forward is
    signed by `user` today, a return to Draft clears them all, and anything
    typed into a signature reverts to what it was (`current`)."""
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
    """Problems with a step, as user-facing messages."""
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the application.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the leave is refused." % who)
    if new_state == APPROVED and not _text(facts.get("custom_balance_before")):
        # Part 2 is the HR Officer's own: the balances before and after
        errors.append("Fill in Part 2, the leave balances, before approving the application.")
    return errors


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def _text(value):
    return str(value).strip() if value not in (None, "") else ""
