# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employees Claim Form workflow (4.7), on Frappe HR's Expense Claim.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (benefits.setup_workflows_on_migrate).

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor  (who says whether the claim is genuine)
      --Approve--> Pending HOD
      --Approve--> Pending HR
      --Approve--> Pending General Manager
      --Approve--> Pending Accounts
      --Pay--> Paid
    any Pending state --Return--> Draft (the reason in Return Remarks)
    any Pending state --Reject--> Rejected

The flow chart draws three approvers — HOD, HR Manager, General Manager —
and the test script written after it adds the immediate supervisor first,
which is also whose signature LPL/HR/27 carries. The chain here is the
script's, and the chart's three are all in it in their order.

Frappe HR's own `approval_status` and `status` are theirs — their
controller writes Paid and Unpaid from the money — so the chain's state
goes in `custom_claim_status` beside them.
"""

DOCTYPE = "Expense Claim"
WORKFLOW_NAME = "Employee Claim"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_claim_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HOD = "Pending HOD"
PENDING_HR = "Pending HR"
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
SUPERVISOR = "Supervisor"
HOD = "Head of Department"
HR_OFFICER, HRM = "HR User", "HR Manager"
GM = "General Manager"
ACCOUNTS = "Accounts User"
NEW_ROLES = (SUPERVISOR, HOD, GM)
PERMISSIONS = {
    DOCTYPE: {
        SUPERVISOR: ("read", "write", "submit"),
        HOD: ("read", "write", "submit"),
        GM: ("read", "write", "submit"),
        HR_OFFICER: ("read", "write", "create", "submit", "cancel"),
    },
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HOD, PENDING_HR, PENDING_GM, PENDING_ACCOUNTS)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_SUPERVISOR, "allow_edit": SUPERVISOR, "status": PENDING_SUPERVISOR, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
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
    {"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HOD, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": SUPERVISOR},
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HR, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    {"state": PENDING_HOD, "action": REJECT, "next_state": REJECTED, "allowed": HOD},
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
    PENDING_HOD: ("custom_hod_by", "custom_hod_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
    PENDING_GM: ("custom_gm_by", "custom_gm_on"),
    PENDING_ACCOUNTS: ("custom_accounts_by", "custom_accounts_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
    PENDING_HOD: ("custom_hod_remarks", "Section Manager"),
    PENDING_HR: ("custom_hr_remarks", "HR Manager"),
    PENDING_GM: ("custom_gm_remarks", "General Manager"),
    PENDING_ACCOUNTS: ("custom_accounts_remarks", "Accounts Officer"),
}
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISOR,
    PENDING_HOD: HOD,
    PENDING_HR: HR_OFFICER,
    PENDING_GM: GM,
    PENDING_ACCOUNTS: ACCOUNTS,
}
# Frappe HR's own approval_status, which their controller reads
UPSTREAM_APPROVAL = {PAID: "Approved", REJECTED: "Rejected"}


def upstream_approval(state):
    return UPSTREAM_APPROVAL.get(state, "Draft")


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
    """Problems with a step, as user-facing messages.

    facts: "return_remarks", the remark fields, and for the supervisor's
    own step whether the claim is genuine (LPL/HR/27).
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the claim.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the claim is refused." % who)
        return errors
    if old_state == PENDING_SUPERVISOR and not facts.get("genuine"):
        errors.append("The supervisor says whether the claim is genuine before it goes up (LPL/HR/27).")
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
