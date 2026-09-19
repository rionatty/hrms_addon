# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Probation Evaluation workflow: the End of probation evaluation /
confirmation form (LPL/HR/32) through its signatures to the decision.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (probation.setup_workflow_on_migrate).

    Draft (HR captures the employee's self-assessment)
      --Submit to Supervisor--> Pending Supervisor (the supervisor rates)
      --Approve--> Pending General Manager   (non-administrative departments)
      --Approve--> Pending Head of Department
      --Approve--> Pending HR Manager        (the recommendation)
      --Approve--> Pending Executive Director
      --Decide--> Decided (submitted: the decision applied to the Employee)
    Pending Supervisor --Return to HR--> Draft (the reason in the remarks)
    Decided --Cancel--> Cancelled (the HR Manager)

The General Manager signs the form's "Manager's remarks" for the positions
routed through the branch General Manager, as a requisition is
(org_rules.py); an administrative department's evaluation goes straight to
the Head of Department. Everything before Decided is a draft, so Frappe
runs validate at each step.
"""

DOCTYPE = "Probation Evaluation"
WORKFLOW_NAME = "Probation Evaluation"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
PENDING_GM = "Pending General Manager"
PENDING_HOD = "Pending Head of Department"
PENDING_HRM = "Pending HR Manager"
PENDING_ED = "Pending Executive Director"
DECIDED = "Decided"
CANCELLED = "Cancelled"

SUBMIT = "Submit to Supervisor"
APPROVE = "Approve"
DECIDE = "Decide"
RETURN = "Return to HR"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, DECIDE, RETURN, CANCEL)

PREPARERS = ("HR User", "HR Manager")
SUPERVISORS = ("Supervisor", "Head of Department")
GM, HOD, HRM, ED = "General Manager", "Head of Department", "HR Manager", "Executive Director"
# the requisition workflow creates these too; whichever runs first does
NEW_ROLES = ("Supervisor", "General Manager", "Head of Department", "Executive Director")
# every role's rights are in the DocType itself
PERMISSIONS = {}

CATEGORY_FIELD = "position_category"
IS_ADMINISTRATIVE = 'doc.position_category == "Administrative"'
NOT_ADMINISTRATIVE = 'doc.position_category != "Administrative"'

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning", "send_email": 1}
      for role in SUPERVISORS),
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": PENDING_HOD, "allow_edit": HOD, "status": PENDING_HOD, "style": "Warning", "send_email": 1},
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    {"state": DECIDED, "allow_edit": HRM, "status": DECIDED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_GM, "allowed": role,
       "condition": NOT_ADMINISTRATIVE} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": APPROVE, "next_state": PENDING_HOD, "allowed": role,
       "condition": IS_ADMINISTRATIVE} for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in SUPERVISORS),
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_HOD, "allowed": GM},
    {"state": PENDING_HOD, "action": APPROVE, "next_state": PENDING_HRM, "allowed": HOD},
    {"state": PENDING_HRM, "action": APPROVE, "next_state": PENDING_ED, "allowed": HRM},
    {"state": PENDING_ED, "action": DECIDE, "next_state": DECIDED, "allowed": ED},
    {"state": DECIDED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    PENDING_SUPERVISOR: ("supervisor_by", "supervisor_on"),
    PENDING_GM: ("manager_by", "manager_on"),
    PENDING_HOD: ("hod_by", "hod_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
    PENDING_ED: ("ed_by", "ed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step just passed forward is
    signed by `user` today; a return to HR clears the supervisor's; anything
    typed into a signature reverts to what it was (`current`)."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        values.update(dict.fromkeys(STAMPS[PENDING_SUPERVISOR]))
        return values
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts: "factors" and "objectives" ([{"employee_rating", "supervisor_rating",
    "label"}]), "supervisor_remarks", "manager_remarks", "hod_remarks",
    "hrm_recommendation", "hrm_remarks", "ed_decision", "end_of_probation",
    "new_end_of_probation", "confirmation_date" (ISO dates).
    """
    if old_state == new_state:
        return []
    errors = []
    factors, objectives = facts.get("factors") or [], facts.get("objectives") or []
    if new_state == PENDING_SUPERVISOR and old_state in (None, DRAFT):
        if not factors:
            errors.append("List the ratable factors (Section A) before sending the evaluation to the supervisor.")
        unrated = [row["label"] for row in factors if not row.get("employee_rating")]
        if unrated:
            errors.append("The employee's self-assessment first: rate every factor, or N/A where it does not fit the "
                          "job (Section A): %s." % ", ".join(unrated))
        if not objectives:
            errors.append("List the probation objectives / KPIs (Section B) before sending the evaluation to the supervisor.")
        unrated = [row["label"] for row in objectives if not row.get("employee_rating")]
        if unrated:
            errors.append("The employee's self-assessment first: rate every objective (Section B): %s." % ", ".join(unrated))
    if old_state == PENDING_SUPERVISOR and new_state in (PENDING_GM, PENDING_HOD):
        unrated = [row["label"] for row in factors + objectives if not row.get("supervisor_rating")]
        if unrated:
            errors.append("Give the supervisor's rating for every factor and objective: %s." % ", ".join(unrated))
        if not _text(facts.get("supervisor_remarks")):
            errors.append("Write the Immediate Supervisor's remarks before passing the evaluation on.")
    if old_state == PENDING_SUPERVISOR and new_state == DRAFT and not _text(facts.get("supervisor_remarks")):
        errors.append("Write in the Immediate Supervisor's remarks what HR should correct before returning the evaluation.")
    for state, field, label in ((PENDING_GM, "manager_remarks", "Manager's remarks"),
                                (PENDING_HOD, "hod_remarks", "Head of Department's remarks")):
        if old_state == state and new_state not in (state, DRAFT) and not _text(facts.get(field)):
            errors.append("Write the %s before passing the evaluation on." % label)
    if old_state == PENDING_HRM and new_state == PENDING_ED:
        if not facts.get("hrm_recommendation"):
            errors.append("Choose the HR Manager's recommendation: Confirm, Extend Probation or Terminate.")
        if not _text(facts.get("hrm_remarks")):
            errors.append("Write the HR Manager's remarks with the recommendation.")
    if old_state == PENDING_ED and new_state == DECIDED:
        decision = facts.get("ed_decision")
        if not decision:
            errors.append("Choose the Executive Director's decision: Confirm, Extend Probation or Terminate.")
        elif decision == "Extend Probation":
            new_end, end = facts.get("new_end_of_probation"), facts.get("end_of_probation")
            if not new_end:
                errors.append("Set the new End of Probation date for the extension.")
            elif end and str(new_end) <= str(end):
                errors.append("The extended probation must end after the current End of Probation (%s)." % end)
        elif decision == "Confirm" and not facts.get("confirmation_date"):
            errors.append("Set the Confirmation Date the employee is confirmed from.")
    return errors


def next_states(state, roles, category=None):
    """[(action, next state)] the holder of `roles` may take from `state` for
    an evaluation of this Position Category."""
    roles = set(roles or ())
    out = []
    for t in TRANSITIONS:
        if t["state"] != state or t["allowed"] not in roles:
            continue
        condition = t.get("condition")
        if condition == IS_ADMINISTRATIVE and category != "Administrative":
            continue
        if condition == NOT_ADMINISTRATIVE and category == "Administrative":
            continue
        if (t["action"], t["next_state"]) not in out:
            out.append((t["action"], t["next_state"]))
    return out


def _text(value):
    return (value or "").strip()
