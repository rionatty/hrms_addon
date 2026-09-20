# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Loan workflow (4.4).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (loans.setup_workflows_on_migrate).

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending HOD
      --Approve--> Pending Executive Director
      --Approve--> Pending General Manager
      --Approve--> Pending Accounts        (step 3: the accountant sets the
                                            terms actually discussed)
      --Approve--> Pending Employee Consent (LPL/HR/39)
      --Run--> Running (submitted: the repayment schedule becomes a
                        monthly deduction on the payroll)
    any Pending state --Return--> Draft (the reason in Return Remarks),
                                  which is the chart's "Approved? No"
    any Pending state --Reject--> Rejected
"""

DOCTYPE = "Employee Loan"
WORKFLOW_NAME = "Employee Loan"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_HOD = "Pending HOD"
PENDING_ED = "Pending Executive Director"
PENDING_GM = "Pending General Manager"
PENDING_ACCOUNTS = "Pending Accounts"
PENDING_CONSENT = "Pending Employee Consent"
RUNNING = "Running"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RUN = "Run"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RUN, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
HOD = "Head of Department"
ED = "Executive Director"
GM = "General Manager"
ACCOUNTS = "Accounts User"
HR_OFFICER, HRM = "HR User", "HR Manager"
PAYROLL = "Payroll Officer"
NEW_ROLES = (HOD, ED, GM, PAYROLL)
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_HOD, PENDING_ED, PENDING_GM, PENDING_ACCOUNTS, PENDING_CONSENT)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    *({"state": PENDING_ACCOUNTS, "allow_edit": role, "status": PENDING_ACCOUNTS, "style": "Warning",
       "send_email": 1} for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PENDING_CONSENT, "allow_edit": "Employee", "status": PENDING_CONSENT, "style": "Warning",
     "send_email": 1},
    *({"state": RUNNING, "allow_edit": role, "status": RUNNING, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (PAYROLL, HRM)),
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HOD, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_ED, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    {"state": PENDING_HOD, "action": REJECT, "next_state": REJECTED, "allowed": HOD},
    {"state": PENDING_ED, "action": APPROVE, "next_state": PENDING_GM, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": PENDING_ED, "action": REJECT, "next_state": REJECTED, "allowed": ED},
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ACCOUNTS, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_GM, "action": REJECT, "next_state": REJECTED, "allowed": GM},
    *({"state": PENDING_ACCOUNTS, "action": APPROVE, "next_state": PENDING_CONSENT, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_ACCOUNTS, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_CONSENT, "action": RUN, "next_state": RUNNING, "allowed": role}
      for role in ("Employee", PAYROLL, HR_OFFICER, HRM)),
    *({"state": PENDING_CONSENT, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in ("Employee", HRM)),
    {"state": RUNNING, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_HOD: ("hod_by", "hod_on"),
    PENDING_ED: ("ed_by", "ed_on"),
    PENDING_GM: ("gm_by", "gm_on"),
    PENDING_ACCOUNTS: ("accounts_by", "accounts_on"),
    PENDING_CONSENT: ("consent_by", "consent_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_HOD: ("hod_remarks", "Head of Department"),
    PENDING_ED: ("ed_remarks", "Executive Director"),
    PENDING_GM: ("gm_remarks", "General Manager"),
    PENDING_ACCOUNTS: ("accounts_remarks", "Accounts Officer"),
    PENDING_CONSENT: ("consent_remarks", "Employee"),
}
ROLE_WAITING = {
    PENDING_HOD: HOD,
    PENDING_ED: ED,
    PENDING_GM: GM,
    PENDING_ACCOUNTS: ACCOUNTS,
    PENDING_CONSENT: "Employee",
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
    """Problems with a step, as user-facing messages.

    facts: "return_remarks", the remark fields, and for the accountant's
    own step the terms they settled with the employee.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the loan.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the loan is refused." % who)
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
