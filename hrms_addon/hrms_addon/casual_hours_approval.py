# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Casual Hours Sheet workflow: each plant's General Manager approves its
casuals' week before the weekly payroll pays it.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (casual_hours.setup_workflows_on_migrate).

    Draft (the plant's HR Officer fills the week: the template, or the
           team's sheet uploaded)
      --Send to General Manager--> Pending General Manager
      --Approve--> Approved (submitted: the weekly payroll pays it)
    Pending General Manager --Return--> Draft (with what must be put right)
    Approved --Cancel--> Cancelled (refused once a slip paid any of it)

The HR Manager serves every plant and may stand in for a General Manager
who is away. No state emails the role: the plant's own General Manager and
HR Officers are told by name (casual_hours._tell_step).
"""

DOCTYPE = "Casual Hours Sheet"
WORKFLOW_NAME = "Casual Hours Sheet"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
PENDING_GM = "Pending General Manager"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SEND = "Send to General Manager"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SEND, APPROVE, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
GM = "General Manager"
PAYROLL_OFFICER = "Payroll Officer"
NEW_ROLES = (GM,)
# the General Manager's Approve submits the sheet; the HR Manager cancels one
PERMISSIONS = {DOCTYPE: {GM: ("read", "write", "submit", "report", "print")}}

PREPARERS = (HR_OFFICER, HRM)
APPROVERS = (GM, HRM)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_GM, "allow_edit": role, "status": PENDING_GM, "style": "Warning", "send_email": 0}
      for role in APPROVERS),
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in APPROVERS),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_GM, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_GM, "action": APPROVE, "next_state": APPROVED, "allowed": role} for role in APPROVERS),
    *({"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in APPROVERS),
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# the signature each step leaves, stamped as the sheet leaves that step
STAMPS = {
    DRAFT: ("prepared_by", "prepared_on"),
    PENDING_GM: ("approved_by", "approved_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, now, current):
    """The signatures after a step: the leaving step stamped with who and when; a return to Draft clears them,
    as the sheet is filled again. A sheet returned from Pending General Manager carries no approver."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state == PENDING_GM and new_state != APPROVED:
        return values
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, now)))
    return values


def step_errors(old_state, new_state, facts):
    """What a step needs, as messages.

    facts:
      return_remarks  what the General Manager wrote, for a return
      people          how many are on the sheet
      unrated         [text] of those with hours and no hourly rate
      no_type         [text] of those with overtime and no Overtime Type
      paid            [text] of those some of whose days in the week a slip paid another way
    """
    if old_state == new_state:
        return []
    if new_state == DRAFT and old_state == PENDING_GM:
        return [] if _text(facts.get("return_remarks")) else ["Write in Return Remarks what must be put right."]
    if new_state not in (PENDING_GM, APPROVED):
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


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))
