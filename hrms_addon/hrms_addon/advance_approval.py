# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Advance workflow: Luuka's three advances, on one document.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (advances.setup_workflows_on_migrate).

One Workflow carries all three chains, because they are three routes
through the same document and the Advance Type says which — the same way
the Appraisal carries both appraisal forms (appraisal_approval.py). Each
junction out of Draft is conditional on the type:

  Leave Advance (4.2)     Draft --Submit--> Pending Accounts Manager
                                --Approve--> Pending Payroll Officer
                                --Approve--> Pending Finance
                                --Pay--> Paid
  Salary Advance (4.10)   Draft --Submit--> Pending HR Officer
                                --Approve--> Pending Payroll Officer
                                --Approve--> Pending Finance
                                --Pay--> Paid
  Special Advance         Draft --Submit--> Pending Section Head
  (LPL/HR/21)                   --Approve--> Pending Executive Director
                                --Approve--> Pending Finance
                                --Pay--> Paid

Any pending state returns to Draft with the reason in Return Remarks, or
is rejected outright.

Frappe HR's own `status` is theirs — their controller writes Paid, Claimed
and Returned from the money — so the workflow's state goes in
`custom_advance_status` beside it.
"""

# the three kinds, spelled here so this module stays importable on its own
# (scripts/verify_leave.py holds them to advance_rules.ADVANCE_TYPES)
LEAVE_ADVANCE = "Leave Advance"
SALARY_ADVANCE = "Salary Advance"
SPECIAL_ADVANCE = "Special Advance"

DOCTYPE = "Employee Advance"
WORKFLOW_NAME = "Employee Advance"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "custom_advance_status"

DRAFT = "Draft"
PENDING_ACCOUNTS_MANAGER = "Pending Accounts Manager"
PENDING_HR = "Pending HR Officer"
PENDING_SECTION_HEAD = "Pending Section Head"
PENDING_ED = "Pending Executive Director"
PENDING_PAYROLL = "Pending Payroll Officer"
PENDING_FINANCE = "Pending Finance"
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
HR_OFFICER, HRM = "HR User", "HR Manager"
ACCOUNTS_MANAGER = "Accounts Manager"
SECTION_HEAD = "Head of Department"
ED = "Executive Director"
PAYROLL = "Payroll Officer"
FINANCE = "Finance Officer"
NEW_ROLES = (SECTION_HEAD, ED, PAYROLL, FINANCE)
PERMISSIONS = {
    DOCTYPE: {
        HR_OFFICER: ("read", "write", "create", "submit", "cancel"),
        HRM: ("read", "write", "create", "submit", "cancel"),
        ACCOUNTS_MANAGER: ("read", "write", "submit"),
        SECTION_HEAD: ("read", "write", "submit"),
        ED: ("read", "write", "submit"),
        PAYROLL: ("read", "write", "submit"),
        FINANCE: ("read", "write", "submit"),
    },
}

# which type each conditional junction belongs to
IS_LEAVE = 'doc.custom_advance_type == "Leave Advance"'
IS_SALARY = 'doc.custom_advance_type == "Salary Advance"'
IS_SPECIAL = 'doc.custom_advance_type == "Special Advance"'
CONDITIONS = {LEAVE_ADVANCE: IS_LEAVE, SALARY_ADVANCE: IS_SALARY, SPECIAL_ADVANCE: IS_SPECIAL}

PENDING_STATES = (PENDING_ACCOUNTS_MANAGER, PENDING_HR, PENDING_SECTION_HEAD, PENDING_ED,
                  PENDING_PAYROLL, PENDING_FINANCE)

# the states each advance actually passes through, in order
ROUTES = {
    LEAVE_ADVANCE: (DRAFT, PENDING_ACCOUNTS_MANAGER, PENDING_PAYROLL, PENDING_FINANCE, PAID),
    SALARY_ADVANCE: (DRAFT, PENDING_HR, PENDING_PAYROLL, PENDING_FINANCE, PAID),
    SPECIAL_ADVANCE: (DRAFT, PENDING_SECTION_HEAD, PENDING_ED, PENDING_FINANCE, PAID),
}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_ACCOUNTS_MANAGER, "allow_edit": ACCOUNTS_MANAGER, "status": PENDING_ACCOUNTS_MANAGER,
     "style": "Warning", "send_email": 1},
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_SECTION_HEAD, "allow_edit": SECTION_HEAD, "status": PENDING_SECTION_HEAD,
     "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": PENDING_PAYROLL, "allow_edit": PAYROLL, "status": PENDING_PAYROLL, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_FINANCE, "allow_edit": FINANCE, "status": PENDING_FINANCE, "style": "Warning",
     "send_email": 1},
    {"state": PAID, "allow_edit": FINANCE, "status": PAID, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    # out of Draft: the type decides whose desk it lands on
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_ACCOUNTS_MANAGER, "allowed": role,
       "condition": IS_LEAVE} for role in PREPARERS),
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HR, "allowed": role,
       "condition": IS_SALARY} for role in PREPARERS),
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SECTION_HEAD, "allowed": role,
       "condition": IS_SPECIAL} for role in PREPARERS),
    # the leave advance: Accounts Manager, then Payroll
    {"state": PENDING_ACCOUNTS_MANAGER, "action": APPROVE, "next_state": PENDING_PAYROLL,
     "allowed": ACCOUNTS_MANAGER},
    {"state": PENDING_ACCOUNTS_MANAGER, "action": RETURN, "next_state": DRAFT, "allowed": ACCOUNTS_MANAGER},
    {"state": PENDING_ACCOUNTS_MANAGER, "action": REJECT, "next_state": REJECTED, "allowed": ACCOUNTS_MANAGER},
    # the salary advance: the HR Officer confirms attendance and leave first
    *({"state": PENDING_HR, "action": APPROVE, "next_state": PENDING_PAYROLL, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": REJECT, "next_state": REJECTED, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    # the special advance: LPL/HR/21's two sanctions
    {"state": PENDING_SECTION_HEAD, "action": APPROVE, "next_state": PENDING_ED, "allowed": SECTION_HEAD},
    {"state": PENDING_SECTION_HEAD, "action": RETURN, "next_state": DRAFT, "allowed": SECTION_HEAD},
    {"state": PENDING_SECTION_HEAD, "action": REJECT, "next_state": REJECTED, "allowed": SECTION_HEAD},
    {"state": PENDING_ED, "action": APPROVE, "next_state": PENDING_FINANCE, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": PENDING_ED, "action": REJECT, "next_state": REJECTED, "allowed": ED},
    # payroll sets the amount approved and the recovery, then Finance pays
    {"state": PENDING_PAYROLL, "action": APPROVE, "next_state": PENDING_FINANCE, "allowed": PAYROLL},
    {"state": PENDING_PAYROLL, "action": RETURN, "next_state": DRAFT, "allowed": PAYROLL},
    {"state": PENDING_PAYROLL, "action": REJECT, "next_state": REJECTED, "allowed": PAYROLL},
    {"state": PENDING_FINANCE, "action": PAY, "next_state": PAID, "allowed": FINANCE},
    {"state": PENDING_FINANCE, "action": RETURN, "next_state": DRAFT, "allowed": FINANCE},
    {"state": PENDING_FINANCE, "action": REJECT, "next_state": REJECTED, "allowed": FINANCE},
    {"state": PAID, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    PENDING_ACCOUNTS_MANAGER: ("custom_accounts_manager_by", "custom_accounts_manager_on"),
    PENDING_HR: ("custom_hr_by", "custom_hr_on"),
    PENDING_SECTION_HEAD: ("custom_section_head_by", "custom_section_head_on"),
    PENDING_ED: ("custom_ed_by", "custom_ed_on"),
    PENDING_PAYROLL: ("custom_payroll_by", "custom_payroll_on"),
    PENDING_FINANCE: ("custom_finance_by", "custom_finance_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_ACCOUNTS_MANAGER: ("custom_accounts_manager_remarks", "Accounts Manager"),
    PENDING_HR: ("custom_hr_remarks", "HR Officer"),
    PENDING_SECTION_HEAD: ("custom_section_head_remarks", "Section Head"),
    PENDING_ED: ("custom_ed_remarks", "Executive Director"),
    PENDING_PAYROLL: ("custom_payroll_remarks", "Payroll Officer"),
    PENDING_FINANCE: ("custom_finance_remarks", "Finance Officer"),
}
ALL_REMARK_FIELDS = tuple(pair[0] for pair in REMARK_FIELDS.values())
ROLE_WAITING = {
    PENDING_ACCOUNTS_MANAGER: ACCOUNTS_MANAGER,
    PENDING_HR: HR_OFFICER,
    PENDING_SECTION_HEAD: SECTION_HEAD,
    PENDING_ED: ED,
    PENDING_PAYROLL: PAYROLL,
    PENDING_FINANCE: FINANCE,
}


def route(advance_type):
    """The states this advance passes through, in order."""
    return ROUTES.get(advance_type or SALARY_ADVANCE, ROUTES[SALARY_ADVANCE])


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

    facts: "return_remarks", the remark fields, and for the Payroll
    Officer's step the amount they approved and how it is recovered.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the advance.")
        return errors
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the advance is refused." % who)
        return errors
    if old_state == PENDING_PAYROLL:
        # step 4 of the chart: "Payroll officer processes and specifies the
        # approved amount", and an advance is nothing without its recovery
        if not _num(facts.get("approved_amount")):
            errors.append("Set the amount approved before passing the advance to Finance.")
        if not int(facts.get("instalments") or 0):
            errors.append("Say in how many months the advance is recovered.")
    if old_state == PENDING_SECTION_HEAD and not _num(facts.get("section_head_amount")):
        errors.append("Write the amount sanctioned before passing the form on (LPL/HR/21).")
    if old_state == PENDING_ED and not _num(facts.get("ed_amount")):
        errors.append("Write the amount sanctioned before passing the form on (LPL/HR/21).")
    if old_state == PENDING_HR and not facts.get("attendance_confirmed"):
        errors.append("Confirm the employee's attendance and leave before passing the advance on.")
    return errors


def next_states(state, roles, advance_type=None):
    """[(action, next state)] the holder of `roles` may take from `state` on
    this kind of advance."""
    roles = set(roles or ())
    wanted = CONDITIONS.get(advance_type or SALARY_ADVANCE)
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        condition = transition.get("condition")
        if condition and condition != wanted:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def _text(value):
    return (value or "").strip()


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
