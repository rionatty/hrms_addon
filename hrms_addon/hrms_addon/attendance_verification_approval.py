# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance Verification workflow: each branch's HR Officer signs its
attendance off before payroll pays it (Luuka, 16 Nov 2026: "attendace
verification should be done by the HR officer for each branch"; until then
the branch's General Manager verified what HR sent).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (attendance_verification.setup_workflows_on_migrate).

    Draft (the branch's HR Officer reads the branch's attendance for the
           month, or the casuals' week, and puts right what it lists)
      --Verify--> Verified (submitted: payroll may pay these days, and they
                  change no more)
    Verified --Reopen--> Reopened (cancelled: the days may change again;
                  Amend makes the sheet to verify again)

Only the branch's own HR Officers verify or reopen its sheet
(verifier_errors); the HR Manager serves every branch and may stand in. No
state emails the role: the branch's HR and Payroll Officers are told by name
when it is verified, as every approval here goes to the branch's own people.
"""

DOCTYPE = "Attendance Verification"
WORKFLOW_NAME = "Attendance Verification"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
VERIFIED = "Verified"
REOPENED = "Reopened"

VERIFY = "Verify"
REOPEN = "Reopen"
ACTIONS = (VERIFY, REOPEN)

HR_OFFICER = "HR User"
HRM = "HR Manager"
PAYROLL_OFFICER = "Payroll Officer"
NEW_ROLES = ()
# the HR Officer's Verify submits the sheet and Reopen cancels it; the
# Payroll Officer reads which branches have verified
PERMISSIONS = {DOCTYPE: {HR_OFFICER: ("read", "write", "submit", "cancel", "print", "report")}}

VERIFIERS = (HR_OFFICER, HRM)
# who may verify or reopen any branch's sheet; anyone else only their own branch's (verifier_errors)
OVERSEERS = (HRM, "System Manager")

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in VERIFIERS),
    *({"state": VERIFIED, "allow_edit": role, "status": VERIFIED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in VERIFIERS),
    *({"state": REOPENED, "allow_edit": role, "status": REOPENED, "style": "Danger", "send_email": 0,
       "doc_status": "2"} for role in VERIFIERS),
)

TRANSITIONS = (
    *({"state": DRAFT, "action": VERIFY, "next_state": VERIFIED, "allowed": role} for role in VERIFIERS),
    *({"state": VERIFIED, "action": REOPEN, "next_state": REOPENED, "allowed": role} for role in VERIFIERS),
)

# the signature the sheet's one step leaves: who read it and verified it, and when (verified_by is stamped as it
# is submitted, attendance_verification.sheet_before_submit)
STAMPS = {DRAFT: ("prepared_by", "prepared_on")}
ALL_STAMP_FIELDS = ("prepared_by", "prepared_on", "verified_by", "verified_on")


def compute_stamps(old_state, new_state, user, now, current):
    """The signatures after a step: the leaving step stamped with who and
    when; a new sheet has none."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, now)))
    return values


def step_errors(old_state, new_state, facts):
    """What a step needs.

    facts:
      sheet_errors    what the sheet itself lacks (rules.sheet_errors)
      people          how many are on it
      issues          [text] of what is still to put right
      changed         [text] of the people whose figures moved since they were read
    """
    if old_state == new_state or new_state != VERIFIED:
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


def verifier_errors(user, roles, branch_officers, branch):
    """Who may verify or reopen a branch's sheet: its own HR Officers (people.people_for: those whose User
    Permissions hold them to the branch, else those serving every branch), or the HR Manager, who serves every
    branch (Luuka, 16 Nov 2026: "attendace verification should be done by the HR officer for each branch")."""
    if user == "Administrator" or set(roles or ()) & set(OVERSEERS) or user in (branch_officers or ()):
        return []
    return ["Only the HR Officer of %s, or the HR Manager, verifies or reopens its attendance." % (branch or
                                                                                                "this branch")]


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
