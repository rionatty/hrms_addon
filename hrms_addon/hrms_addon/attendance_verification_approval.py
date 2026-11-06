# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance Verification workflow: each branch signs its attendance off
before payroll pays it.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (attendance_verification.setup_workflows_on_migrate).

    Draft (the branch's HR Officer reads the branch's attendance for the
           month, or the casuals' week, and puts right what it lists)
      --Send to General Manager--> Pending General Manager
      --Verify--> Verified (submitted: payroll may pay these days, and they
                  change no more)
    Pending General Manager --Return--> Draft (with what must be put right)
    Verified --Reopen--> Reopened (cancelled: the days may change again;
                  Amend makes the sheet to verify again)

The HR Manager serves every branch and may stand in for a General Manager
who is away. No state emails the role: the branch's own General Manager and
HR Officers are told by name (attendance_verification._tell_step), as every
approval here goes to the branch's own people.
"""

DOCTYPE = "Attendance Verification"
WORKFLOW_NAME = "Attendance Verification"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
PENDING_GM = "Pending General Manager"
VERIFIED = "Verified"
REOPENED = "Reopened"

SEND = "Send to General Manager"
VERIFY = "Verify"
RETURN = "Return"
REOPEN = "Reopen"
ACTIONS = (SEND, VERIFY, RETURN, REOPEN)

HR_OFFICER = "HR User"
HRM = "HR Manager"
GM = "General Manager"
PAYROLL_OFFICER = "Payroll Officer"
NEW_ROLES = (GM,)
# the General Manager's Verify submits the sheet and Reopen cancels it; the
# Payroll Officer reads which branches have verified
PERMISSIONS = {DOCTYPE: {GM: ("read", "write", "submit", "cancel", "print", "report")}}

PREPARERS = (HR_OFFICER, HRM)
VERIFIERS = (GM, HRM)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_GM, "allow_edit": role, "status": PENDING_GM, "style": "Warning", "send_email": 0}
      for role in VERIFIERS),
    *({"state": VERIFIED, "allow_edit": role, "status": VERIFIED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in VERIFIERS),
    *({"state": REOPENED, "allow_edit": role, "status": REOPENED, "style": "Danger", "send_email": 0,
       "doc_status": "2"} for role in VERIFIERS),
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_GM, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_GM, "action": VERIFY, "next_state": VERIFIED, "allowed": role} for role in VERIFIERS),
    *({"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in VERIFIERS),
    *({"state": VERIFIED, "action": REOPEN, "next_state": REOPENED, "allowed": role} for role in VERIFIERS),
)

# the signature each step leaves, stamped as the sheet leaves that step
STAMPS = {
    DRAFT: ("prepared_by", "prepared_on"),
    PENDING_GM: ("verified_by", "verified_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)


def compute_stamps(old_state, new_state, user, now, current):
    """The signatures after a step: the leaving step stamped with who and
    when; a return to Draft clears them, as the sheet is read again. A sheet
    returned from Pending General Manager carries no verifier."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if new_state == DRAFT:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    if old_state == PENDING_GM and new_state != VERIFIED:
        return values
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, now)))
    return values


def step_errors(old_state, new_state, facts):
    """What a step needs.

    facts:
      return_remarks  what the General Manager wrote, for a return
      sheet_errors    what the sheet itself lacks (rules.sheet_errors)
      people          how many are on it
      issues          [text] of what is still to put right
      changed         [text] of the people whose figures moved since they were read
    """
    if old_state == new_state:
        return []
    if new_state == DRAFT and old_state == PENDING_GM:
        return [] if _text(facts.get("return_remarks")) else ["Write in Return Remarks what must be put right."]
    if new_state not in (PENDING_GM, VERIFIED):
        return []
    errors = list(facts.get("sheet_errors") or [])
    if errors:
        return errors
    if not facts.get("people"):
        errors.append("Nobody is on this sheet. Get Attendance reads the branch's people.")
    issues = list(facts.get("issues") or [])
    if issues:
        errors.append("Put these right first, then Get Attendance again: %s" % _listed(issues))
    changed = list(facts.get("changed") or [])
    if new_state == VERIFIED and changed:
        errors.append("The attendance changed after these figures were read (%s). Save to read them again, "
                      "check them, then verify." % _listed(changed))
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
