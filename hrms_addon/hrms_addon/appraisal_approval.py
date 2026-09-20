# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Appraisal workflow: the Supervisory Skills Evaluation Form's own
signature blocks.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (appraisals.setup_workflows_on_migrate).

The form is signed, in this order, by the Employee, the Supervisor, the
Human Resources Manager, the Production Manager and the General Manager, so:

    Draft (HR raises it for the quarter's employees)
      --Submit Self-Assessment--> Pending Supervisor
          (the form says the employee rates themselves first, then meets
           the supervisor to agree the final score)
      --Rate--> Pending HR Manager
      --Approve--> Pending Production Manager
      --Approve--> Pending General Manager
      --Approve--> Completed (submitted: the score stands, ready for the
                   management review)
    any Pending state --Return--> Draft (the reason in Return Remarks,
                                  which clears every signature)
    Completed --Cancel--> Cancelled (the HR Manager)

Frappe HR's Appraisal is the document this runs on, so the round keeps its
Appraisal Cycle, its appraisee list and the Appraisal Overview chart.
"""

DOCTYPE = "Appraisal"
WORKFLOW_NAME = "Performance Appraisal"
STATE_FIELD = "workflow_state"
# Frappe HR's Appraisal has no `status` field; the workflow writes its
# states here (a custom field this app adds)
STATUS_FIELD = "custom_appraisal_status"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HRM = "Pending HR Manager"
PENDING_PRODUCTION = "Pending Production Manager"
PENDING_GM = "Pending General Manager"
COMPLETED = "Completed"
CANCELLED = "Cancelled"

SELF = "Submit Self-Assessment"
RATE = "Rate"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SELF, RATE, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
APPRAISEE = "Employee"
SUPERVISORS = ("Supervisor", "Head of Department")
HRM, PRODUCTION, GM = "HR Manager", "Production Manager", "General Manager"
NEW_ROLES = ("Supervisor", "Head of Department", PRODUCTION, GM)
# Frappe HR gives the Appraisal to HR Manager and Employee only; the people
# who sign it need to read and write it, and the HR Officer to raise it
PERMISSIONS = {
    DOCTYPE: {
        "HR User": ("read", "write", "create", "submit", "cancel"),
        "Supervisor": ("read", "write", "submit"),
        "Head of Department": ("read", "write", "submit"),
        PRODUCTION: ("read", "write", "submit"),
        GM: ("read", "write", "submit"),
    },
    "Employee Performance Feedback": {"HR User": ("read", "write", "create", "submit")},
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_HRM, PENDING_PRODUCTION, PENDING_GM)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in PREPARERS + (APPRAISEE,)),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning", "send_email": 1}
      for role in SUPERVISORS),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_PRODUCTION, "allow_edit": PRODUCTION, "status": PENDING_PRODUCTION, "style": "Warning", "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": COMPLETED, "allow_edit": HRM, "status": COMPLETED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    # the employee rates themselves first; HR may do it for someone with no login
    *({"state": DRAFT, "action": SELF, "next_state": PENDING_SUPERVISOR, "allowed": role}
      for role in PREPARERS + (APPRAISEE,)),
    *({"state": PENDING_SUPERVISOR, "action": RATE, "next_state": PENDING_HRM, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_PRODUCTION, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_PRODUCTION, "action": APPROVE, "next_state": PENDING_GM, "allowed": PRODUCTION},
    {"state": PENDING_PRODUCTION, "action": RETURN, "next_state": DRAFT, "allowed": PRODUCTION},
    {"state": PENDING_GM, "action": APPROVE, "next_state": COMPLETED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": COMPLETED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    DRAFT: ("custom_employee_signed_by", "custom_employee_signed_on"),
    PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
    PENDING_HRM: ("custom_hrm_by", "custom_hrm_on"),
    PENDING_PRODUCTION: ("custom_production_by", "custom_production_on"),
    PENDING_GM: ("custom_gm_by", "custom_gm_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# the comment each signatory writes on the form, beside their signature
REMARK_FIELDS = {
    DRAFT: ("custom_employee_remarks", "Employee"),
    PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
    PENDING_HRM: ("custom_hrm_remarks", "HR Manager"),
    PENDING_PRODUCTION: ("custom_production_remarks", "Production Manager"),
    PENDING_GM: ("custom_gm_remarks", "General Manager"),
}


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
    """Problems with a step, as user-facing messages.

    facts: "return_remarks", the remark fields, and whatever
    appraisal_rules.appraisal_errors reads.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the appraisal.")
        return errors
    # the employee's own comments and the supervisor's are on the form; the
    # three managers above them sign, and comment where they wish
    if old_state == PENDING_SUPERVISOR and new_state == PENDING_HRM \
            and not _text(facts.get("custom_supervisor_remarks")):
        errors.append("Write the Supervisor's general comments before passing the form on.")
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
