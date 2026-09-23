# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave encashment workflow (Reward and Compensation, §4.5), on Frappe HR's
Leave Encashment.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (encashments.setup_on_migrate).

    Draft (the employee, or HR for someone with no login)
      --Submit--> Pending Supervisor
      --Approve--> Pending HR
      --Approve--> Pending General Manager
      --Approve--> Pending Executive Director
      --Approve--> Approved            ("before being returned to Human
                                         Resource")
      --Forward--> Pending Accounts    (the Accounts Manager in Finance)
      --Process--> Processed (submitted: Frappe HR's own Additional Salary
                              pays it with the payroll)
    any Pending state --Return--> Draft (the reason in Return Remarks)
    any approver --Reject--> Rejected (never submitted: a submitted
                                       encashment is paid)

Frappe HR's own `status` is theirs — their controller writes Unpaid and
Paid from the money — so the chain's state goes in
`custom_encashment_status` beside it.
"""

DOCTYPE = "Leave Encashment"
WORKFLOW_NAME = "Leave Encashment"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_encashment_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HR = "Pending HR"
PENDING_GM = "Pending General Manager"
PENDING_ED = "Pending Executive Director"
APPROVED = "Approved"
PENDING_ACCOUNTS = "Pending Accounts"
PROCESSED = "Processed"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
FORWARD = "Forward"
PROCESS = "Process"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, FORWARD, PROCESS, RETURN, REJECT, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
SUPERVISOR = "Supervisor"
HR_OFFICER, HRM = "HR User", "HR Manager"
GM = "General Manager"
ED = "Executive Director"
ACCOUNTS = "Accounts Manager"
NEW_ROLES = (SUPERVISOR, GM, ED)
PERMISSIONS = {
    DOCTYPE: {
        SUPERVISOR: ("read", "write"),
        GM: ("read", "write"),
        ED: ("read", "write"),
        ACCOUNTS: ("read", "write", "submit"),
    },
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HR, PENDING_GM, PENDING_ED, APPROVED, PENDING_ACCOUNTS)
# where Management may cut the days asked for
MANAGEMENT = (PENDING_GM, PENDING_ED)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_SUPERVISOR, "allow_edit": SUPERVISOR, "status": PENDING_SUPERVISOR, "style": "Warning",
     "send_email": 1},
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Info", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_ACCOUNTS, "allow_edit": ACCOUNTS, "status": PENDING_ACCOUNTS, "style": "Warning",
     "send_email": 1},
    {"state": PROCESSED, "allow_edit": ACCOUNTS, "status": PROCESSED, "style": "Success", "send_email": 0,
     "doc_status": "1"},
    *({"state": REJECTED, "allow_edit": role, "status": REJECTED, "style": "Danger", "send_email": 0}
      for role in (HR_OFFICER, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    {"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HR, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": SUPERVISOR},
    {"state": PENDING_SUPERVISOR, "action": REJECT, "next_state": REJECTED, "allowed": SUPERVISOR},
    *({"state": PENDING_HR, "action": APPROVE, "next_state": PENDING_GM, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_GM, "action": REJECT, "next_state": REJECTED, "allowed": GM},
    {"state": PENDING_ED, "action": APPROVE, "next_state": APPROVED, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": PENDING_ED, "action": REJECT, "next_state": REJECTED, "allowed": ED},
    *({"state": APPROVED, "action": FORWARD, "next_state": PENDING_ACCOUNTS, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_ACCOUNTS, "action": PROCESS, "next_state": PROCESSED, "allowed": ACCOUNTS},
    {"state": PENDING_ACCOUNTS, "action": RETURN, "next_state": DRAFT, "allowed": ACCOUNTS},
    {"state": PROCESSED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
    PENDING_GM: ("custom_gm_by", "custom_gm_on"),
    PENDING_ED: ("custom_ed_by", "custom_ed_on"),
    APPROVED: ("custom_forwarded_by", "custom_forwarded_on"),
    PENDING_ACCOUNTS: ("custom_accounts_by", "custom_accounts_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
    PENDING_HR: ("custom_hr_remarks", "HR Officer"),
    PENDING_GM: ("custom_gm_remarks", "General Manager"),
    PENDING_ED: ("custom_ed_remarks", "Executive Director"),
    PENDING_ACCOUNTS: ("custom_accounts_remarks", "Accounts Manager"),
}
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISOR,
    PENDING_HR: HR_OFFICER,
    PENDING_GM: GM,
    PENDING_ED: ED,
    APPROVED: HR_OFFICER,
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
    """Problems with a step, as user-facing messages.

    facts: "return_remarks" and the remark fields.
    """
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
            errors.append("Write the %s's remarks saying why the encashment is refused." % who)
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
