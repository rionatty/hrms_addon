# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casual Hours Sheet workflow: each plant's HR Officer approves its casuals'
week before the weekly payroll pays it.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (casual_hours.setup_workflows_on_migrate).

    Draft (the plant's HR Officer fills the week: the template, or the
           team's sheet uploaded)
      --Approve--> Approved (submitted: the weekly payroll pays it)
    Approved --Cancel--> Cancelled (refused once a slip paid any of it)

Only the plant's own HR Officers approve or cancel its sheet
(approver_errors); the HR Manager serves every plant. Until 17 Nov 2026 the
HR Officer sent the week to the plant's General Manager, who approved it or
returned it; Luuka asked that it go "to HR Offer", as the Attendance
Verification had the day before.
"""

DOCTYPE = "Casual Hours Sheet"
WORKFLOW_NAME = "Casual Hours Sheet"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
APPROVED = "Approved"
CANCELLED = "Cancelled"

APPROVE = "Approve"
CANCEL = "Cancel"
ACTIONS = (APPROVE, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
GM = "General Manager"
PAYROLL_OFFICER = "Payroll Officer"
NEW_ROLES = ()
# the HR Officer's Approve submits the sheet, and either cancels one; the General Manager keeps what it had, to read
PERMISSIONS = {DOCTYPE: {HR_OFFICER: ("read", "write", "submit", "cancel", "report", "print")}}

PREPARERS = (HR_OFFICER, HRM)
APPROVERS = (HR_OFFICER, HRM)
# who may approve or cancel any plant's sheet
OVERSEERS = (HRM, "System Manager")

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in APPROVERS),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": APPROVE, "next_state": APPROVED, "allowed": role} for role in APPROVERS),
    *({"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": role} for role in APPROVERS),
)

# the signatures: who prepared the week, stamped as it leaves Draft, and who approved it, as it is approved
STAMPS = {DRAFT: ("prepared_by", "prepared_on")}
APPROVAL_STAMP = ("approved_by", "approved_on")
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair) + APPROVAL_STAMP


def compute_stamps(old_state, new_state, user, now, current):
    """The signatures after a step: the leaving step stamped with who and when, and the approval with whoever
    approved; a sheet back at Draft carries none."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, now)))
    if new_state == APPROVED:
        values.update(zip(APPROVAL_STAMP, (user, now)))
    return values


def approver_errors(user, roles, plant_officers, plant):
    """Who may approve or cancel a plant's sheet: its own HR Officers (plant_officers), the HR Manager and the System
    Manager for any plant, and the Administrator."""
    if user == "Administrator" or set(roles or ()) & set(OVERSEERS) or user in (plant_officers or ()):
        return []
    return ["Only the HR Officer of %s, or the HR Manager, approves or cancels its casual hours."
            % (plant or "this plant")]


def step_errors(old_state, new_state, facts):
    """What approving the week needs, as messages.

    facts:
      people          how many are on the sheet
      unrated         [text] of those with hours and no hourly rate
      no_type         [text] of those with overtime and no Overtime Type
      paid            [text] of those some of whose days in the week a slip paid another way
    """
    if old_state == new_state or new_state != APPROVED:
        return []
    errors = []
    if not facts.get("people"):
        errors.append("Nobody is on this sheet: download the template, fill it in and upload it.")
    unrated = list(facts.get("unrated") or [])
    if unrated:
        errors.append("No hourly rate on the week's last day for %s: give them an Hourly Rate, or set the Standard "
                      "Hourly Rate on Output Pay Settings." % _listed(unrated))
    no_type = list(facts.get("no_type") or [])
    if no_type:
        errors.append("Overtime, but no Overtime Type lists %s: add them to the casuals' Overtime Type."
                      % _listed(no_type))
    paid = list(facts.get("paid") or [])
    if paid:
        errors.append("Some of these days were paid already from the attendance for %s: take them off this sheet, or "
                      "cancel that pay first, or the week is paid twice." % _listed(paid))
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


SHOWN = 10


def _listed(items, shown=SHOWN):
    items = list(items)
    if len(items) <= shown:
        return "; ".join(items)
    return "%s; and %d more" % ("; ".join(items[:shown]), len(items) - shown)
