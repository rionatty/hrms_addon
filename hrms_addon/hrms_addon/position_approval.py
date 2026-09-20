# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Position Change workflow: the Candidate Preamble Promotion
Form's own signature blocks.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (positions.setup_workflows_on_migrate).

The paper form is signed, in this order, by the Supervisor, the Human
Resource Manager, the General Manager and the Executive Director, so:

    Draft (HR, or the supervisor, fills the preamble and the change)
      --Submit to Supervisor--> Pending Supervisor
      --Approve--> Pending HR Manager
      --Approve--> Pending General Manager
      --Approve--> Pending Executive Director
      --Approve--> Approved (submitted: the change applied to the employee)
    any Pending state --Return--> Draft (the reason in Return Remarks,
                                  which clears every signature)
    Approved --Cancel--> Cancelled (the HR Manager)

The Executive Director signs the letter, so their approval is what submits
the document and applies the change.
"""

DOCTYPE = "Employee Position Change"
WORKFLOW_NAME = "Employee Position Change"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HRM = "Pending HR Manager"
PENDING_GM = "Pending General Manager"
PENDING_ED = "Pending Executive Director"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SUBMIT = "Submit to Supervisor"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
SUPERVISORS = ("Supervisor", "Head of Department")
HRM, GM, ED = "HR Manager", "General Manager", "Executive Director"
# the Legal Manager witnesses the renewal and salary review letters; the role
# is created here so it can be given to whoever signs (Luuka, 20 Sep 2026)
LEGAL = "Legal Manager"
NEW_ROLES = ("Supervisor", "Head of Department", GM, ED, LEGAL)
# every role's rights on the document are in the DocType itself
PERMISSIONS = {}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HRM, PENDING_GM, PENDING_ED)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in PREPARERS + SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning", "send_email": 1}
      for role in SUPERVISORS),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": APPROVED, "allow_edit": HRM, "status": APPROVED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role}
      for role in PREPARERS + SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HRM, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_GM, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_ED, "action": APPROVE, "next_state": APPROVED, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
    PENDING_GM: ("gm_by", "gm_on"),
    PENDING_ED: ("ed_by", "ed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# the comment each signatory writes on the form, beside their signature
REMARK_FIELDS = {
    PENDING_SUPERVISOR: ("supervisor_remarks", "Supervisor"),
    PENDING_HRM: ("hrm_remarks", "HR Manager"),
    PENDING_GM: ("gm_remarks", "General Manager"),
    PENDING_ED: ("ed_remarks", "Executive Director"),
}


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step just passed forward is signed
    by `user` today, a return to Draft clears them all, and anything typed
    into a signature reverts to what it was (`current`)."""
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

    facts: "return_remarks" and the four remark fields, plus whatever
    position_rules.change_errors and preamble_errors read.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the form.")
        return errors
    if new_state == PENDING_SUPERVISOR and old_state in (None, DRAFT):
        # what the change itself must say is position_rules' to judge; the
        # glue asks it as well, so this module stays on its own
        return errors
    if old_state in REMARK_FIELDS and new_state != DRAFT:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's comments on the form before passing it on." % who)
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
    return (value or "").strip()
