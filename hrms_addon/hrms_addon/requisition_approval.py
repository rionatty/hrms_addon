# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Job Requisition approval: the definition and the stamping rules.

Deliberately imports nothing from Frappe. Everything here is plain data
and pure functions, so scripts/verify_requisition_workflow.py can load it
and exercise every transition on a machine with no bench. The Frappe side
(creating the Workflow, doc events, permissions) is in job_requisition.py
and only ever reads from this module.

WHAT IT MIRRORS

LPL/HR/36, the paper Staff Requisition Form, is signed in this order:

    Supervisor -> Process Owner -> Head of Department -> HR Officer
    -> HR Manager (Recruitment Authorized / Not Authorized)
    -> Executive Director (Recruitment Approved / Not Approved)

Each signature becomes one Frappe Workflow state. When an approver acts,
their name, the date and (for the two decision-makers) the decision are
written into the matching fields on the Approvals tab — see
compute_stamp_values(). Those fields are read-only in the form, and this
module also puts back any value that was changed without a workflow
transition, so nobody can type in someone else's approval.

THE GENERAL MANAGER, BY DEPARTMENT

The To-Be resourcing process adds one step the paper form lacks: a
non-administrative position also goes through the branch's General Manager,
between the HR Manager and the Executive Director. The Department's
Position Category decides (fetched onto the requisition), so the HR
Manager's Approve has two transitions with opposite conditions and exactly
one applies; route() says the same in plain Python for the checks.

    Administrative:     ... -> HR Manager -> Executive Director
    Non-Administrative: ... -> HR Manager -> General Manager -> Executive Director

Every approver apart from the HR Manager and the Executive Director belongs
to a branch. The requisition carries its Branch, and branch-level users
hold Branch User Permissions (org_rules.py), so each step reaches only the
requesting branch's Supervisor, HOD, HR Officer or General Manager.
"""

DOCTYPE = "Job Requisition"
WORKFLOW_NAME = "Job Requisition Approval"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
APPROVED = "Approved"
REJECTED = "Rejected"

SUBMIT = "Submit for Approval"
APPROVE = "Approve"
REJECT = "Reject"
REVISE = "Revise"
ACTIONS = (SUBMIT, APPROVE, REJECT, REVISE)

# Roles this app creates. HR User / HR Manager ship with HRMS.
NEW_ROLES = ("Supervisor", "Process Owner", "Head of Department", "Executive Director", "General Manager")

# The Department's Position Category, fetched onto the requisition, picks the
# route after the HR Manager (org_rules.POSITION_CATEGORIES). Blank counts as
# non-administrative: the longer route is the safer one.
ADMINISTRATIVE = "Administrative"
CATEGORY_FIELD = "custom_position_category"
# Workflow Transition conditions, evaluated by Frappe with the requisition as `doc`
IS_ADMINISTRATIVE = 'doc.custom_position_category == "Administrative"'
NOT_ADMINISTRATIVE = 'doc.custom_position_category != "Administrative"'

# Who may raise a requisition: every role with create permission on Job
# Requisition (HR Manager and System Manager from HRMS, the rest granted in
# PERMISSIONS below). Each of them may edit a Draft, submit it, and revise
# it after a rejection.
#
# Frappe makes a workflow document read-only ("This form is not editable
# due to a Workflow", frappe/public/js/frappe/model/workflow.js is_read_only)
# for anyone who is not an edit role of its current state. A Draft editable
# by one role alone locked every other author out of their own requisition.
REQUESTER_ROLES = ("Head of Department", "Supervisor", "Process Owner", "HR User", "HR Manager", "System Manager")

HRM_STATE = "Pending HR Manager Approval"
GM_STATE = "Pending General Manager Approval"

# One row per signature on the paper form, in signing order.
#   state   : the Workflow State the requisition waits in
#   role    : who may approve or reject it there
#   stamp   : which Approvals-tab fields record that signature
#   only_if : a step some requisitions skip: the Workflow Transition
#   skip_if   conditions for reaching it and for going past it
APPROVAL_CHAIN = (
    {
        "state": "Pending Supervisor Approval",
        "role": "Supervisor",
        "stamp": {"user": "custom_supervisor", "date": "custom_supervisor_date"},
    },
    {
        "state": "Pending Process Owner Approval",
        "role": "Process Owner",
        "stamp": {"user": "custom_process_owner", "date": "custom_process_owner_date"},
    },
    {
        "state": "Pending HOD Approval",
        "role": "Head of Department",
        "stamp": {"user": "custom_hod", "date": "custom_hod_date"},
    },
    {
        "state": "Pending HR Officer Review",
        "role": "HR User",
        "stamp": {"user": "custom_hr_officer", "date": "custom_hr_officer_date"},
    },
    {
        "state": HRM_STATE,
        "role": "HR Manager",
        "stamp": {
            "user": "custom_hrm",
            "date": "custom_hrm_date",
            "decision": "custom_hrm_decision",
            "approved": "Recruitment Authorized",
            "rejected": "Not Authorized",
        },
    },
    {
        # Non-administrative departments only (the To-Be resourcing process)
        "state": GM_STATE,
        "role": "General Manager",
        "stamp": {"user": "custom_gm", "date": "custom_gm_date"},
        "only_if": NOT_ADMINISTRATIVE,
        "skip_if": IS_ADMINISTRATIVE,
    },
    {
        "state": "Pending Executive Director Approval",
        "role": "Executive Director",
        "stamp": {
            "user": "custom_ed",
            "date": "custom_ed_date",
            "decision": "custom_ed_decision",
            "approved": "Recruitment Approved",
            "rejected": "Not Approved",
        },
    },
)

# Workflow Document State rows. update_value keeps the standard Job
# Requisition `status` in step, which matters: HRMS only shows its
# "Create Job Opening" button when status == "Open & Approved".
#
# Draft has one row per requester role: a state row names a single
# "Only Allow Edit For" role, and Frappe lets anyone holding the role of
# ANY row for the state edit (get_document_state_roles). The first row is
# still Draft, so new requisitions still start there.
#
# send_email: Frappe emails everyone who may take a state's next action
# (frappe/workflow/doctype/workflow_action). That is right for the approval
# steps, but in Draft and Rejected the next action (Submit, Revise) is open
# to every requester role, so each saved draft would email every HR
# Manager, Head of Department and Supervisor. Those two states stay quiet.
STATES = (
    *(
        {"state": DRAFT, "allow_edit": role, "status": "Pending", "style": "", "send_email": 0}
        for role in REQUESTER_ROLES
    ),
    *(
        {"state": step["state"], "allow_edit": step["role"], "status": "Pending", "style": "Warning", "send_email": 1}
        for step in APPROVAL_CHAIN
    ),
    {"state": APPROVED, "allow_edit": "HR Manager", "status": "Open & Approved", "style": "Success", "send_email": 1},
    {"state": REJECTED, "allow_edit": "HR Manager", "status": "Rejected", "style": "Danger", "send_email": 0},
)


def _build_transitions():
    rows = [
        {"state": DRAFT, "action": SUBMIT, "next_state": APPROVAL_CHAIN[0]["state"], "allowed": role}
        for role in REQUESTER_ROLES
    ]
    for index, step in enumerate(APPROVAL_CHAIN):
        for condition, next_state in _approval_targets(index):
            row = {"state": step["state"], "action": APPROVE, "next_state": next_state, "allowed": step["role"]}
            if condition:
                row["condition"] = condition
            rows.append(row)
        rows.append({"state": step["state"], "action": REJECT, "next_state": REJECTED, "allowed": step["role"]})
    # A rejected requisition goes back to the requester to amend and resubmit.
    rows.extend({"state": REJECTED, "action": REVISE, "next_state": DRAFT, "allowed": role} for role in REQUESTER_ROLES)
    return tuple(rows)


def _approval_targets(index):
    """[(condition, next state)] for Approve at APPROVAL_CHAIN[index]: the next
    step, or, before a step some requisitions skip, one transition into it and
    one past it, with opposite conditions."""
    following = _state_after(index)
    step = APPROVAL_CHAIN[index + 1] if index + 1 < len(APPROVAL_CHAIN) else None
    if step and step.get("skip_if"):
        return [(step["only_if"], following), (step["skip_if"], _state_after(index + 1))]
    return [(None, following)]


def _state_after(index):
    return APPROVAL_CHAIN[index + 1]["state"] if index + 1 < len(APPROVAL_CHAIN) else APPROVED


TRANSITIONS = _build_transitions()


def route(category):
    """The approval states a requisition passes through, in order, for a
    Department of this Position Category (what the conditions above do)."""
    return [
        step["state"]
        for step in APPROVAL_CHAIN
        if not (step.get("skip_if") and category == ADMINISTRATIVE)
    ]

STAMP_RULES = {step["state"]: step["stamp"] for step in APPROVAL_CHAIN}

ALL_STAMP_FIELDS = tuple(
    fieldname
    for step in APPROVAL_CHAIN
    for key in ("user", "date", "decision")
    if (fieldname := step["stamp"].get(key))
)

# Rights the workflow needs to actually work. Approving saves the
# document, so every approver role needs write. Standard HRMS gives
# HR User only READ on Job Requisition, so the HR Officer step would fail
# without this. Designation and Employment Type are pickers on the form
# that the Employee role cannot search at all upstream.
PERMISSIONS = {
    "Job Requisition": {
        "Supervisor": ("read", "write", "create"),
        "Process Owner": ("read", "write", "create"),
        "Head of Department": ("read", "write", "create"),
        "Executive Director": ("read", "write"),
        "General Manager": ("read", "write"),
        "HR User": ("read", "write", "create"),
    },
    "Designation": {
        "Supervisor": ("select",),
        "Process Owner": ("select",),
        "Head of Department": ("select",),
    },
    "Employment Type": {
        "Supervisor": ("select",),
        "Process Owner": ("select",),
        "Head of Department": ("select",),
    },
}


def compute_stamp_values(old_state, new_state, user, today, current):
    """Every Approvals-tab field's correct value after this save.

    old_state / new_state : workflow_state before and after the save
                            (old_state is None when the document is new)
    user, today           : who is saving, and the date
    current               : {fieldname: value} as stored in the database
                            before this save ({} for a new document)

    The return value covers ALL stamp fields, not just the ones that
    change. The caller writes every one back, which is what stops a value
    typed in (or posted through the API) from surviving a save: anything
    not produced by a transition reverts to what the database held.
    """
    values = {field: current.get(field) for field in ALL_STAMP_FIELDS}

    if not old_state:
        # A brand-new requisition carries no approvals, whatever was posted.
        return {field: None for field in ALL_STAMP_FIELDS}

    if old_state == new_state:
        return values

    if old_state == REJECTED and new_state == DRAFT:
        # Revised after rejection: it must be approved again from scratch.
        return {field: None for field in ALL_STAMP_FIELDS}

    rule = STAMP_RULES.get(old_state)
    if not rule:
        return values

    approved = new_state != REJECTED
    # Sign-only steps record an approval. The two decision steps record
    # either outcome, because the paper form has a box for each.
    if approved or rule.get("decision"):
        values[rule["user"]] = user
        values[rule["date"]] = today
        if rule.get("decision"):
            values[rule["decision"]] = rule["approved"] if approved else rule["rejected"]

    return values


def recommended_salary_missing(old_state, new_state, recommended_salary):
    """The HR Manager recommends the salary on the paper form, so it must
    be filled in before they authorize. Rejecting needs no salary."""
    return old_state == HRM_STATE and new_state not in (HRM_STATE, REJECTED) and not recommended_salary


# Why the new employee is needed, and how they are to be recruited
REASON_FIELD = "custom_reason_type"
MODE_FIELDS = ("custom_external_advert", "custom_internal_advert", "custom_head_hunt", "custom_reference_to_database")


def request_errors(old_state, new_state, values):
    """What a requisition must say while it is written, in a draft and as it
    is sent for approval: the reason, and at least one mode of recruitment.
    One already with the approvers is left as it is."""
    if new_state not in (None, "", DRAFT) and old_state not in (None, "", DRAFT):
        return []
    errors = []
    if not str(values.get(REASON_FIELD) or "").strip():
        errors.append("Say why the new employee is required.")
    if not any(int(values.get(field) or 0) for field in MODE_FIELDS):
        errors.append("Tick at least one Mode of Recruitment.")
    return errors
