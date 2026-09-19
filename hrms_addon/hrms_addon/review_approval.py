# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Onboarding Review workflow: the Staff Onboarding Form (LPL/HR/04), filled
at 30, 60 and 90 days (the To-Be 30-60-90 Day Employee Review).

No Frappe import; workflows.py builds it on every migrate
(reviews.setup_workflow_on_migrate).

    Draft (HR captures the new employee's answers and comments)
      --Submit to Supervisor--> Pending Supervisor (the supervisor's comments)
      --Submit to HR Manager--> Pending HR Manager (the HR Manager's remarks)
      --Complete--> Completed (submitted)
    Completed --Cancel--> Cancelled (the HR Manager)

The supervisor's step is open to the Supervisor and the Head of Department
roles: the To-Be has the Head of Department monitor the new employee with
it. Branch and Department User Permissions route it to the employee's own.
"""

DOCTYPE = "Onboarding Review"
WORKFLOW_NAME = "Onboarding Review"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_HRM = "Pending HR Manager"
COMPLETED = "Completed"
CANCELLED = "Cancelled"

SUBMIT = "Submit to Supervisor"
FORWARD = "Submit to HR Manager"
COMPLETE = "Complete"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, FORWARD, COMPLETE, CANCEL)

PREPARERS = ("HR User", "HR Manager")
SUPERVISORS = ("Supervisor", "Head of Department")
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
PERMISSIONS = {}

# The Staff Onboarding Form, at these days after joining
REVIEW_DAYS = (30, 60, 90)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning", "send_email": 1}
      for role in SUPERVISORS),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": COMPLETED, "allow_edit": HRM, "status": COMPLETED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": FORWARD, "next_state": PENDING_HRM, "allowed": role} for role in SUPERVISORS),
    {"state": PENDING_HRM, "action": COMPLETE, "next_state": COMPLETED, "allowed": HRM},
    {"state": COMPLETED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

STAMPS = {
    PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step passed is signed by `user`
    today; a typed signature reverts to what it was (`current`)."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state != new_state and old_state in STAMPS and new_state != CANCELLED:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts: "roles_responsibilities", "feel_about_role", "supervisor_comments",
    "hrm_remarks".
    """
    if old_state == new_state:
        return []
    errors = []
    if new_state == PENDING_SUPERVISOR and old_state in (None, DRAFT):
        if not _text(facts.get("roles_responsibilities")):
            errors.append("Record the roles and responsibilities the new employee lists (Section B) before sending the "
                          "review to the supervisor.")
        if not _text(facts.get("feel_about_role")):
            errors.append("Record how the new employee feels about the new role before sending the review to the supervisor.")
    if old_state == PENDING_SUPERVISOR and new_state == PENDING_HRM and not _text(facts.get("supervisor_comments")):
        errors.append("Write the supervisor's general comments before sending the review to the HR Manager.")
    if old_state == PENDING_HRM and new_state == COMPLETED and not _text(facts.get("hrm_remarks")):
        errors.append("Write the Human Resources Manager's remarks before completing the review.")
    return errors


def _text(value):
    return (value or "").strip()
