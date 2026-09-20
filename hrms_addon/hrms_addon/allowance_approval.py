# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Allowance Application workflow (4.3), on Frappe HR's Travel Request.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (allowances.setup_workflows_on_migrate).

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor
      --Approve--> Pending HR Officer
      --Approve--> Pending General Manager
      --Approve--> Pending Accounts   (step 3: Accounts process the payment)
      --Pay--> Paid                   (step 4: Accounts set it to Paid)
    any Pending state --Return--> Draft (the reason in Return Remarks)
    any Pending state --Reject--> Rejected

Frappe HR's Travel Request has no status field of its own, so the state
goes in `custom_allowance_status`.
"""

DOCTYPE = "Travel Request"
WORKFLOW_NAME = "Allowance Application"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_allowance_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HR = "Pending HR Officer"
PENDING_GM = "Pending General Manager"
PENDING_ACCOUNTS = "Pending Accounts"
PAID = "Paid"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
PAY = "Pay"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, PAY, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
SUPERVISORS = ("Supervisor", "Head of Department")
HR_OFFICER, HRM = "HR User", "HR Manager"
GM = "General Manager"
ACCOUNTS = "Accounts User"
NEW_ROLES = ("Supervisor", "Head of Department", GM)
PERMISSIONS = {
    DOCTYPE: {
        HR_OFFICER: ("read", "write", "create", "submit", "cancel"),
        HRM: ("read", "write", "create", "submit", "cancel"),
        "Supervisor": ("read", "write", "submit"),
        "Head of Department": ("read", "write", "submit"),
        GM: ("read", "write", "submit"),
        ACCOUNTS: ("read", "write", "submit"),
        "Accounts Manager": ("read", "write", "submit"),
    },
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HR, PENDING_GM, PENDING_ACCOUNTS)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning",
       "send_email": 1} for role in SUPERVISORS),
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    *({"state": PENDING_ACCOUNTS, "allow_edit": role, "status": PENDING_ACCOUNTS, "style": "Warning",
       "send_email": 1} for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PAID, "allow_edit": ACCOUNTS, "status": PAID, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role}
      for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HR, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_HR, "action": APPROVE, "next_state": PENDING_GM, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ACCOUNTS, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_GM, "action": REJECT, "next_state": REJECTED, "allowed": GM},
    *({"state": PENDING_ACCOUNTS, "action": PAY, "next_state": PAID, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_ACCOUNTS, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PAID, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
    PENDING_GM: ("custom_gm_by", "custom_gm_on"),
    PENDING_ACCOUNTS: ("custom_accounts_by", "custom_accounts_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
    PENDING_HR: ("custom_hr_remarks", "HR Officer"),
    PENDING_GM: ("custom_gm_remarks", "General Manager"),
    PENDING_ACCOUNTS: ("custom_accounts_remarks", "Accounts Officer"),
}
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISORS[0],
    PENDING_HR: HR_OFFICER,
    PENDING_GM: GM,
    PENDING_ACCOUNTS: ACCOUNTS,
}


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
            errors.append("Write in Return Remarks what must be put right before returning the request.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the allowance is refused." % who)
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
