# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Clearance Form workflow (LPL/HR/22), for both exits.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (exits.setup_workflows_on_migrate).

The two charts sign the same form with different people, so one Workflow
carries both chains and the Exit Type says which — the way the Appraisal
carries both appraisal forms:

  Voluntary (4.5, step 8)     Draft --Submit--> Pending HR Officer
                                   --Approve--> Pending Finance
                                   --Approve--> Pending General Manager
                                   --Clear--> Cleared
  Involuntary (4.6, step 8)   Draft --Submit--> Pending General Manager
                                   --Approve--> Pending Accounts
                                   --Approve--> Pending HR Manager
                                   --Clear--> Cleared

Either way the ten boxes are accounted for and signed before the form
leaves Draft, and the cessation of employment follows it.
"""

# the two exits, spelled here so this module stays importable on its own
# (scripts/verify_exits.py holds them to exit_rules.EXIT_TYPES)
VOLUNTARY = "Voluntary"
INVOLUNTARY = "Involuntary"

DOCTYPE = "Clearance Form"
WORKFLOW_NAME = "Clearance Form"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_HR = "Pending HR Officer"
PENDING_FINANCE = "Pending Finance"
PENDING_GM = "Pending General Manager"
PENDING_ACCOUNTS = "Pending Accounts"
PENDING_HRM = "Pending HR Manager"
CLEARED = "Cleared"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
CLEAR = "Clear"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, CLEAR, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager", "Employee")
HR_OFFICER, HRM = "HR User", "HR Manager"
FINANCE = "Finance Officer"
ACCOUNTS = "Accounts User"
GM = "General Manager"
NEW_ROLES = (GM, FINANCE)
# the DocType carries every role's rights
PERMISSIONS = {}

IS_VOLUNTARY = 'doc.exit_type == "Voluntary"'
IS_INVOLUNTARY = 'doc.exit_type == "Involuntary"'
CONDITIONS = {VOLUNTARY: IS_VOLUNTARY, INVOLUNTARY: IS_INVOLUNTARY}

PENDING_STATES = (PENDING_HR, PENDING_FINANCE, PENDING_GM, PENDING_ACCOUNTS, PENDING_HRM)
ROUTES = {
    VOLUNTARY: (DRAFT, PENDING_HR, PENDING_FINANCE, PENDING_GM, CLEARED),
    INVOLUNTARY: (DRAFT, PENDING_GM, PENDING_ACCOUNTS, PENDING_HRM, CLEARED),
}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 1}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_FINANCE, "allow_edit": FINANCE, "status": PENDING_FINANCE, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    *({"state": PENDING_ACCOUNTS, "allow_edit": role, "status": PENDING_ACCOUNTS, "style": "Warning",
       "send_email": 1} for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    *({"state": CLEARED, "allow_edit": role, "status": CLEARED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (HRM, GM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    # out of Draft: which exit decides whose desk it lands on
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_HR, "allowed": role,
       "condition": IS_VOLUNTARY} for role in PREPARERS),
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_GM, "allowed": role,
       "condition": IS_INVOLUNTARY} for role in PREPARERS),
    # the voluntary chain
    *({"state": PENDING_HR, "action": APPROVE, "next_state": PENDING_FINANCE, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": PENDING_FINANCE, "action": APPROVE, "next_state": PENDING_GM, "allowed": FINANCE},
    {"state": PENDING_FINANCE, "action": RETURN, "next_state": DRAFT, "allowed": FINANCE},
    {"state": PENDING_GM, "action": CLEAR, "next_state": CLEARED, "allowed": GM,
     "condition": IS_VOLUNTARY},
    # the involuntary chain
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ACCOUNTS, "allowed": GM,
     "condition": IS_INVOLUNTARY},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    *({"state": PENDING_ACCOUNTS, "action": APPROVE, "next_state": PENDING_HRM, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    *({"state": PENDING_ACCOUNTS, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (ACCOUNTS, "Accounts Manager")),
    {"state": PENDING_HRM, "action": CLEAR, "next_state": CLEARED, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": CLEARED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_HR: ("hr_by", "hr_on"),
    PENDING_FINANCE: ("finance_by", "finance_on"),
    PENDING_GM: ("gm_by", "gm_on"),
    PENDING_ACCOUNTS: ("accounts_by", "accounts_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_HR: ("hr_remarks", "HR Officer"),
    PENDING_FINANCE: ("finance_remarks", "Finance"),
    PENDING_GM: ("gm_remarks", "General Manager"),
    PENDING_ACCOUNTS: ("accounts_remarks", "Accounts"),
    PENDING_HRM: ("hrm_remarks", "HR Manager"),
}
ROLE_WAITING = {
    PENDING_HR: HR_OFFICER,
    PENDING_FINANCE: FINANCE,
    PENDING_GM: GM,
    PENDING_ACCOUNTS: ACCOUNTS,
    PENDING_HRM: HRM,
}


def route(exit_type):
    """The desks this form passes, in order."""
    return ROUTES.get(exit_type or VOLUNTARY, ROUTES[VOLUNTARY])


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

    facts: "return_remarks", the remark fields, and whether the ten boxes
    are accounted for and signed.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the form.")
        return errors
    if old_state in (None, DRAFT) and new_state != DRAFT and not facts.get("complete"):
        errors.append("Every box on LPL/HR/22 is accounted for and signed before the form goes up.")
    return errors


def next_states(state, roles, exit_type=None):
    """[(action, next state)] the holder of `roles` may take from `state` on
    this kind of exit."""
    roles = set(roles or ())
    wanted = CONDITIONS.get(exit_type or VOLUNTARY)
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
