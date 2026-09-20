# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Cessation Benefits workflow (4.9), on Frappe HR's Full and Final
Statement.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (settlements.setup_workflows_on_migrate).

    Draft (the HR Officer opens it from the cleared exit)
      --Submit--> Pending Accounts   (step 3: the benefits due and the
                                      deductions to be made)
      --Approve--> Pending Employee  (step 4: the employee confirms and
                                      signs the severance / full and final
                                      pay, LPL/HR/20)
      --Approve--> Pending Executive Director  (step 5)
      --Approve--> Pending Payroll   (step 5: scheduled for the next run)
      --Schedule--> Scheduled (submitted; the payroll process follows)
    any Pending state --Return--> Draft (the reason in Return Remarks)

Frappe HR's own `status` is theirs — Draft, Unpaid, Paid — so the chain's
state goes in `custom_settlement_status` beside it.
"""

DOCTYPE = "Full and Final Statement"
WORKFLOW_NAME = "Cessation Benefits"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_settlement_status"

DRAFT = "Draft"
PENDING_ACCOUNTS = "Pending Accounts"
PENDING_EMPLOYEE = "Pending Employee"
PENDING_ED = "Pending Executive Director"
PENDING_PAYROLL = "Pending Payroll"
SCHEDULED = "Scheduled"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
SCHEDULE = "Schedule"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, SCHEDULE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
HR_OFFICER, HRM = "HR User", "HR Manager"
ACCOUNTS = "Accounts User"
APPRAISEE = "Employee"
ED = "Executive Director"
PAYROLL = "Payroll Officer"
NEW_ROLES = (ED, PAYROLL)
PERMISSIONS = {
    DOCTYPE: {
        HR_OFFICER: ("read", "write", "create", "submit", "cancel"),
        HRM: ("read", "write", "create", "submit", "cancel"),
        ACCOUNTS: ("read", "write", "submit"),
        ED: ("read", "write", "submit"),
        PAYROLL: ("read", "write", "submit"),
        APPRAISEE: ("read", "write"),
    },
}

PENDING_STATES = (PENDING_ACCOUNTS, PENDING_EMPLOYEE, PENDING_ED, PENDING_PAYROLL)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_ACCOUNTS, "allow_edit": role, "status": PENDING_ACCOUNTS, "style": "Warning",
       "send_email": 1} for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PENDING_EMPLOYEE, "allow_edit": APPRAISEE, "status": PENDING_EMPLOYEE, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": PENDING_PAYROLL, "allow_edit": PAYROLL, "status": PENDING_PAYROLL, "style": "Warning",
     "send_email": 1},
    *({"state": SCHEDULED, "allow_edit": role, "status": SCHEDULED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (PAYROLL, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_ACCOUNTS, "allowed": role}
      for role in PREPARERS),
    *({"state": PENDING_ACCOUNTS, "action": APPROVE, "next_state": PENDING_EMPLOYEE, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_ACCOUNTS, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_EMPLOYEE, "action": APPROVE, "next_state": PENDING_ED, "allowed": role}
      for role in (APPRAISEE,) + PREPARERS),
    {"state": PENDING_EMPLOYEE, "action": RETURN, "next_state": DRAFT, "allowed": APPRAISEE},
    {"state": PENDING_ED, "action": APPROVE, "next_state": PENDING_PAYROLL, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": PENDING_PAYROLL, "action": SCHEDULE, "next_state": SCHEDULED, "allowed": PAYROLL},
    {"state": PENDING_PAYROLL, "action": RETURN, "next_state": DRAFT, "allowed": PAYROLL},
    {"state": SCHEDULED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_ACCOUNTS: ("custom_accounts_by", "custom_accounts_on"),
    PENDING_EMPLOYEE: ("custom_employee_signed_by", "custom_employee_signed_on"),
    PENDING_ED: ("custom_ed_by", "custom_ed_on"),
    PENDING_PAYROLL: ("custom_payroll_by", "custom_payroll_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_ACCOUNTS: ("custom_accounts_remarks", "Accounts"),
    PENDING_EMPLOYEE: ("custom_employee_remarks", "Employee"),
    PENDING_ED: ("custom_ed_remarks", "Executive Director"),
    PENDING_PAYROLL: ("custom_payroll_remarks", "Payroll Officer"),
}
ROLE_WAITING = {
    PENDING_ACCOUNTS: ACCOUNTS,
    PENDING_EMPLOYEE: APPRAISEE,
    PENDING_ED: ED,
    PENDING_PAYROLL: PAYROLL,
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
    """Problems with a step, as user-facing messages."""
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the statement.")
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
