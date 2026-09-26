# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Onboarding workflow: where each new employee stands in Luuka's
To-Be induction process (blueprint 1.2.4, onboarding_rules.py).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (onboarding.setup_workflow_on_migrate).

    Draft --Start Onboarding--> Onboarding (submitted: the tasks are made)
    Onboarding --Submit for Approval--> Pending HR Manager Approval
    Pending HR Manager Approval --Approve--> Approved
    Pending HR Manager Approval --Return to HR--> Onboarding (a reason required)
    Onboarding / Approved --Cancel--> Cancelled (the HR Manager)

The branch HR Officer drives it; the HR Manager, one for all branches,
approves (step 7). Frappe HR lets HR User create an onboarding but not
submit it, and starting one submits it, so HR User is granted submit.

Every state after Draft is a submitted document, so a step is an update
after submit: Frappe runs no `validate` then, and onboarding.py checks the
step in before_update_after_submit as well. The fields a step needs (the
date the rules were signed, the HR Manager's remarks and stamp) are
therefore allow_on_submit.
"""

DOCTYPE = "Employee Onboarding"
WORKFLOW_NAME = "Employee Onboarding"
STATE_FIELD = "workflow_state"
# Employee Onboarding has no `status`; the workflow writes its states here
STATUS_FIELD = "custom_onboarding_status"

DRAFT = "Draft"
ONBOARDING = "Onboarding"
PENDING_HRM = "Pending HR Manager Approval"
APPROVED = "Approved"
CANCELLED = "Cancelled"

START = "Start Onboarding"
SUBMIT = "Submit for Approval"
APPROVE = "Approve"
RETURN = "Return to HR"
CANCEL = "Cancel"
ACTIONS = (START, SUBMIT, APPROVE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
APPROVER = "HR Manager"
NEW_ROLES = ()
PERMISSIONS = {DOCTYPE: {"HR User": ("read", "write", "create", "submit")}}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": ONBOARDING, "allow_edit": role, "status": ONBOARDING, "style": "Primary", "send_email": 0, "doc_status": "1"}
      for role in PREPARERS),
    {"state": PENDING_HRM, "allow_edit": APPROVER, "status": PENDING_HRM, "style": "Warning", "send_email": 1, "doc_status": "1"},
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0, "doc_status": "1"}
      for role in PREPARERS),
    {"state": CANCELLED, "allow_edit": APPROVER, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": START, "next_state": ONBOARDING, "allowed": role} for role in PREPARERS),
    *({"state": ONBOARDING, "action": SUBMIT, "next_state": PENDING_HRM, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HRM, "action": APPROVE, "next_state": APPROVED, "allowed": APPROVER},
    {"state": PENDING_HRM, "action": RETURN, "next_state": ONBOARDING, "allowed": APPROVER},
    {"state": ONBOARDING, "action": CANCEL, "next_state": CANCELLED, "allowed": APPROVER},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": APPROVER},
)

# The HR Manager's approval, recorded when they approve
STAMP_FIELDS = ("custom_hrm_approved_by", "custom_hrm_approved_on")


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    return [(t["action"], t["next_state"]) for t in TRANSITIONS if t["state"] == state and t["allowed"] in roles]


def compute_stamps(old_state, new_state, user, today, current):
    """The HR Manager's approval after this save: recorded when they approve,
    kept otherwise (a typed date reverts), cleared when they return it."""
    if not old_state:
        return dict.fromkeys(STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in STAMP_FIELDS}
    if old_state == PENDING_HRM and new_state == APPROVED:
        return dict(zip(STAMP_FIELDS, (user, today)))
    if old_state == PENDING_HRM and new_state == ONBOARDING:
        return dict.fromkeys(STAMP_FIELDS)
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts, from the onboarding: "head_of_department", "activities" (how many),
    "holiday_list" (or the Employee, whose list serves), "employee",
    "rules_signed_on", "bio_data_signed_on" (the Employee's) and "hrm_remarks".
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == ONBOARDING and old_state in (None, DRAFT):
        if not facts.get("head_of_department"):
            errors.append("Name the Head of Department the new employee is handed over to before starting the onboarding.")
        if not facts.get("activities"):
            errors.append("Choose an Employee Onboarding Template, or add the activities, before starting the onboarding.")
        if not facts.get("holiday_list"):
            errors.append("Choose the Holiday List the task dates skip (the company has no default one) before "
                          "starting the onboarding.")
    if new_state == PENDING_HRM:
        errors += _ready_for_approval(facts)
        # Steps 2 to 4 of the induction are done: the rules signed, the
        # Employee created and updated from the signed Personal Bio-Data Form
        if not facts.get("rules_signed_on"):
            errors.append("Record the date the Workplace Rules and Regulations were signed (Orientation section) "
                          "before sending the onboarding to the HR Manager.")
        if not facts.get("employee"):
            errors.append("Create the Employee (Create > Employee) before sending the onboarding to the HR Manager. "
                          "An Employee made another way is found once its Job Applicant (Joining tab) is this candidate.")
        elif not facts.get("bio_data_signed_on"):
            errors.append("Update the Employee from the signed Personal Bio-Data Form and record the date it was signed "
                          "(Employee, Personal Bio-Data tab) before sending the onboarding to the HR Manager.")
    if old_state == PENDING_HRM and new_state == ONBOARDING and not (facts.get("hrm_remarks") or "").strip():
        errors.append("Write in the HR Manager's Remarks what HR should change before returning the onboarding.")
    return errors


def _ready_for_approval(facts):
    """Steps 5 to 7 and the training choice, done before the HR Manager
    approves: the salary structure, the tools of work, the supervisor.

    facts: "supervisor", "supervisor_is_employee", "salary_structure",
    "base_salary", "salary_from", "date_of_joining" (ISO dates),
    "tax_slab_needed" (the structure's name when it deducts tax and no slab
    is chosen), "tools_pending" ([tool]), "training_required",
    "training_missing" ([label]), "medical_certificate_missing" (the JD asks
    for a medical check before joining and no certificate is attached).
    """
    errors = []
    if not facts.get("supervisor"):
        errors.append("Choose the Supervisor the new employee reports to (Employee Details) before sending the "
                      "onboarding to the HR Manager.")
    elif facts.get("supervisor_is_employee"):
        errors.append("The Supervisor cannot be the new employee.")
    if not facts.get("salary_structure"):
        errors.append("Choose the Salary Structure (Salary section) before sending the onboarding to the HR Manager.")
    if not (facts.get("base_salary") or 0) > 0:
        errors.append("Enter the Base salary (Salary section) before sending the onboarding to the HR Manager.")
    if not facts.get("salary_from"):
        errors.append("Set the date the salary is Effective From (Salary section) before sending the onboarding to "
                      "the HR Manager.")
    elif facts.get("date_of_joining") and str(facts["salary_from"]) < str(facts["date_of_joining"]):
        errors.append("The salary cannot start before the Date of Joining.")
    if facts.get("tax_slab_needed"):
        errors.append("Choose the Income Tax Slab (Salary section): the Salary Structure %s deducts income tax."
                      % facts["tax_slab_needed"])
    if facts.get("tools_pending"):
        errors.append("Issue the tools of work, or mark them Not Needed, before sending the onboarding to the HR "
                      "Manager: %s." % ", ".join(facts["tools_pending"]))
    if facts.get("training_required") and facts.get("training_missing"):
        errors.append("Training is required: fill in the %s (Training section) before sending the onboarding to the "
                      "HR Manager." % ", ".join(facts["training_missing"]))
    if facts.get("medical_certificate_missing"):
        errors.append("The job needs a medical check before joining: attach the Medical Fitness Certificate "
                      "(Orientation section) before sending the onboarding to the HR Manager.")
    return errors
