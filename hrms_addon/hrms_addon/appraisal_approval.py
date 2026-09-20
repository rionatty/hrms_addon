# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Appraisal workflow: the signature blocks of both of Luuka's appraisal
forms, on Frappe HR's Appraisal.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (appraisals.setup_workflows_on_migrate).

TWO FORMS, TWO CHAINS, ONE WORKFLOW

Luuka runs both forms side by side (confirmed 23 Sep 2026), and they are
signed by different people. The Appraisal's Form Type picks the route, the
way a Job Requisition's Position Category picks its own:

  Supervisory Skills (LPL/HR/18)
    Draft (the employee assesses themselves)
      --Submit Self-Assessment--> Pending Supervisor
      --Rate--> Pending HR Manager
      --Approve--> Pending Production Manager
      --Approve--> Pending General Manager
      --Approve--> Completed

  Balanced Scorecard (LPL PMS)
    Draft (HR raises it from the role's scorecard)
      --Submit Self-Assessment--> Pending Supervisor  (the appraiser scores)
      --Rate--> Pending Employee                      (the employee comments)
      --Approve--> Pending Head of Department
      --Approve--> Pending HR Manager
      --Approve--> Pending Executive Director
      --Approve--> Completed

  any Pending state --Return--> Draft (the reason in Return Remarks, which
                                clears every signature)
  Completed --Cancel--> Cancelled (the HR Manager)

Both routes share Draft, Pending Supervisor, Pending HR Manager, Completed
and Cancelled, so the two junctions that differ carry a condition on the
form type and nothing else does.
"""

DOCTYPE = "Appraisal"
WORKFLOW_NAME = "Performance Appraisal"
STATE_FIELD = "workflow_state"
# Frappe HR's Appraisal has no `status` field; the workflow writes its
# states here (a custom field this app adds)
STATUS_FIELD = "custom_appraisal_status"
# which form the employee is on, and so which way the appraisal is routed
FORM_FIELD = "custom_form_type"
FORM_SUPERVISORY = "Supervisory Skills (LPL/HR/18)"
FORM_BSC = "Balanced Scorecard"
FORM_TYPES = (FORM_SUPERVISORY, FORM_BSC)
IS_BSC = 'doc.custom_form_type == "Balanced Scorecard"'
NOT_BSC = 'doc.custom_form_type != "Balanced Scorecard"'

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_EMPLOYEE = "Pending Employee"
PENDING_HOD = "Pending Head of Department"
PENDING_HRM = "Pending HR Manager"
PENDING_PRODUCTION = "Pending Production Manager"
PENDING_GM = "Pending General Manager"
PENDING_ED = "Pending Executive Director"
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
HOD, HRM, PRODUCTION, GM, ED = "Head of Department", "HR Manager", "Production Manager", "General Manager", \
    "Executive Director"
NEW_ROLES = ("Supervisor", HOD, PRODUCTION, GM, ED)
# Frappe HR gives the Appraisal to HR Manager and Employee only; the people
# who sign it need to read and write it, and the HR Officer to raise it
PERMISSIONS = {
    DOCTYPE: {
        "HR User": ("read", "write", "create", "submit", "cancel"),
        "Supervisor": ("read", "write", "submit"),
        HOD: ("read", "write", "submit"),
        PRODUCTION: ("read", "write", "submit"),
        GM: ("read", "write", "submit"),
        ED: ("read", "write", "submit"),
    },
    "Employee Performance Feedback": {"HR User": ("read", "write", "create", "submit")},
}

PENDING_STATES = (PENDING_SUPERVISOR, PENDING_EMPLOYEE, PENDING_HOD, PENDING_HRM, PENDING_PRODUCTION,
                  PENDING_GM, PENDING_ED)
# the states each form actually passes through
ROUTES = {
    FORM_SUPERVISORY: (DRAFT, PENDING_SUPERVISOR, PENDING_HRM, PENDING_PRODUCTION, PENDING_GM, COMPLETED),
    FORM_BSC: (DRAFT, PENDING_SUPERVISOR, PENDING_EMPLOYEE, PENDING_HOD, PENDING_HRM, PENDING_ED, COMPLETED),
}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0}
      for role in PREPARERS + (APPRAISEE,)),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning", "send_email": 1}
      for role in SUPERVISORS),
    {"state": PENDING_EMPLOYEE, "allow_edit": APPRAISEE, "status": PENDING_EMPLOYEE, "style": "Warning", "send_email": 1},
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_PRODUCTION, "allow_edit": PRODUCTION, "status": PENDING_PRODUCTION, "style": "Warning",
     "send_email": 1},
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": COMPLETED, "allow_edit": HRM, "status": COMPLETED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    # the employee rates themselves first on the supervisory form; on the
    # scorecard HR opens it for the appraiser. Either way HR may act for
    # someone with no login.
    *({"state": DRAFT, "action": SELF, "next_state": PENDING_SUPERVISOR, "allowed": role}
      for role in PREPARERS + (APPRAISEE,)),
    # the junction that differs: the scorecard goes back to the employee
    *({"state": PENDING_SUPERVISOR, "action": RATE, "next_state": PENDING_HRM, "allowed": role,
       "condition": NOT_BSC} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RATE, "next_state": PENDING_EMPLOYEE, "allowed": role,
       "condition": IS_BSC} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    # the scorecard's own middle: the employee, then the Head of Department
    *({"state": PENDING_EMPLOYEE, "action": APPROVE, "next_state": PENDING_HOD, "allowed": role}
      for role in (APPRAISEE,) + PREPARERS),
    {"state": PENDING_EMPLOYEE, "action": RETURN, "next_state": DRAFT, "allowed": APPRAISEE},
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HRM, "allowed": HOD},
    {"state": PENDING_HOD, "action": RETURN, "next_state": DRAFT, "allowed": HOD},
    # the second junction: the supervisory form goes to Production, the
    # scorecard straight to the Executive Director
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_PRODUCTION, "allowed": HRM, "condition": NOT_BSC},
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_ED, "allowed": HRM, "condition": IS_BSC},
    {"state": PENDING_HRM, "action": RETURN, "next_state": DRAFT, "allowed": HRM},
    {"state": PENDING_PRODUCTION, "action": APPROVE, "next_state": PENDING_GM, "allowed": PRODUCTION},
    {"state": PENDING_PRODUCTION, "action": RETURN, "next_state": DRAFT, "allowed": PRODUCTION},
    {"state": PENDING_GM, "action": APPROVE, "next_state": COMPLETED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_ED, "action": APPROVE, "next_state": COMPLETED, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": COMPLETED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: form -> state left -> (by, on).
# The two forms sign different blocks, so Draft means the employee's own
# self-assessment on one and HR opening the file on the other.
STAMPS_BY_FORM = {
    FORM_SUPERVISORY: {
        DRAFT: ("custom_employee_signed_by", "custom_employee_signed_on"),
        PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
        PENDING_HRM: ("custom_hrm_by", "custom_hrm_on"),
        PENDING_PRODUCTION: ("custom_production_by", "custom_production_on"),
        PENDING_GM: ("custom_gm_by", "custom_gm_on"),
    },
    FORM_BSC: {
        PENDING_SUPERVISOR: ("custom_supervisor_by", "custom_supervisor_on"),
        PENDING_EMPLOYEE: ("custom_employee_signed_by", "custom_employee_signed_on"),
        PENDING_HOD: ("custom_hod_by", "custom_hod_on"),
        PENDING_HRM: ("custom_hrm_by", "custom_hrm_on"),
        PENDING_ED: ("custom_ed_by", "custom_ed_on"),
    },
}
STAMPS = STAMPS_BY_FORM[FORM_SUPERVISORY]
ALL_STAMP_FIELDS = tuple(dict.fromkeys(
    field for stamps in STAMPS_BY_FORM.values() for pair in stamps.values() for field in pair))

# the comment each signatory writes on the form, beside their signature
REMARK_FIELDS_BY_FORM = {
    FORM_SUPERVISORY: {
        DRAFT: ("custom_employee_remarks", "Employee"),
        PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Supervisor"),
        PENDING_HRM: ("custom_hrm_remarks", "HR Manager"),
        PENDING_PRODUCTION: ("custom_production_remarks", "Production Manager"),
        PENDING_GM: ("custom_gm_remarks", "General Manager"),
    },
    FORM_BSC: {
        PENDING_SUPERVISOR: ("custom_supervisor_remarks", "Appraiser"),
        PENDING_EMPLOYEE: ("custom_employee_remarks", "Employee"),
        PENDING_HOD: ("custom_hod_remarks", "HOD"),
        PENDING_HRM: ("custom_hrm_remarks", "HR Manager"),
        PENDING_ED: ("custom_ed_remarks", "Executive Director"),
    },
}
REMARK_FIELDS = REMARK_FIELDS_BY_FORM[FORM_SUPERVISORY]
ALL_REMARK_FIELDS = tuple(dict.fromkeys(
    pair[0] for remarks in REMARK_FIELDS_BY_FORM.values() for pair in remarks.values()))
# who is told when the appraisal reaches a state waiting on them
ROLE_WAITING = {
    PENDING_SUPERVISOR: SUPERVISORS[0],
    PENDING_EMPLOYEE: APPRAISEE,
    PENDING_HOD: HOD,
    PENDING_HRM: HRM,
    PENDING_PRODUCTION: PRODUCTION,
    PENDING_GM: GM,
    PENDING_ED: ED,
}


def stamps_for(form_type):
    return STAMPS_BY_FORM.get(form_type or FORM_SUPERVISORY, STAMPS_BY_FORM[FORM_SUPERVISORY])


def remarks_for(form_type):
    return REMARK_FIELDS_BY_FORM.get(form_type or FORM_SUPERVISORY, REMARK_FIELDS_BY_FORM[FORM_SUPERVISORY])


def compute_stamps(old_state, new_state, user, today, current, form_type=None):
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
    stamps = stamps_for(form_type)
    if old_state in stamps:
        values.update(zip(stamps[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts: "form_type", "return_remarks" and the remark fields; whatever
    each form's own rules read is judged by the glue.
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right before returning the appraisal.")
        return errors
    form_type = facts.get("form_type") or FORM_SUPERVISORY
    # the person who rates writes their comments before passing the form on;
    # the managers above them sign, and comment where they wish
    rating_state = PENDING_SUPERVISOR
    if old_state == rating_state and new_state != DRAFT:
        field, who = remarks_for(form_type)[rating_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's general comments before passing the form on." % who)
    return errors


def next_states(state, roles, form_type=None):
    """[(action, next state)] the holder of `roles` may take from `state` on
    this form."""
    roles = set(roles or ())
    is_bsc = (form_type or FORM_SUPERVISORY) == FORM_BSC
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        condition = transition.get("condition")
        if condition == IS_BSC and not is_bsc:
            continue
        if condition == NOT_BSC and is_bsc:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def route(form_type):
    """The states this form passes through, in order."""
    return ROUTES.get(form_type or FORM_SUPERVISORY, ROUTES[FORM_SUPERVISORY])


def _text(value):
    return (value or "").strip()
