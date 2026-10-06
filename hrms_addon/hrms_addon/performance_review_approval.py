# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance Review workflow (Performance Management, test cases 5, 6
and 10): the appraisal results of a quarter, approved by management.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (appraisals.setup_workflows_on_migrate).

    Draft (the HR Officer puts the results of a quarter and a plant on it,
           from the Appraisal Results report or the form's Get Appraisals,
           each with the outcome the score suggests as its decision, and
           changes any that should be otherwise)
      --Send to Management--> Pending General Manager
      --Approve--> Pending Executive Director
      --Approve--> Approved (submitted: each decision is carried out: a
                   promotion or a salary increase as an Employee Position
                   Change, a PIP as its own plan, the rest closed)
    Pending General Manager or Pending Executive Director --Return--> Draft
    Approved --Cancel--> Cancelled

Management may change a decision while the review is with them: what they
approve is what is carried out, and what HR proposed is kept beside it
(proposed_decision, written as the review leaves Draft). Each signature is
stamped with who and when; a return clears them all and says why.
"""

DOCTYPE = "Performance Review"
WORKFLOW_NAME = "Performance Review Approval"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
PENDING_GM = "Pending General Manager"
PENDING_ED = "Pending Executive Director"
APPROVED = "Approved"
CANCELLED = "Cancelled"

SEND = "Send to Management"
APPROVE = "Approve"
RETURN = "Return"
CANCEL = "Cancel"
ACTIONS = (SEND, APPROVE, RETURN, CANCEL)

HR_OFFICER = "HR User"
HRM = "HR Manager"
GM = "General Manager"
ED = "Executive Director"
NEW_ROLES = (GM, ED)
# the Executive Director's approval files the review, which takes submit
PERMISSIONS = {DOCTYPE: {GM: ("read", "write"), ED: ("read", "write", "submit")}}

HR = (HR_OFFICER, HRM)
PENDING_STATES = (PENDING_GM, PENDING_ED)
STATUSES = (DRAFT, PENDING_GM, PENDING_ED, APPROVED, CANCELLED)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in HR),
    {"state": PENDING_GM, "allow_edit": GM, "status": PENDING_GM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    *({"state": APPROVED, "allow_edit": role, "status": APPROVED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (ED, HRM)),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_GM, "allowed": role} for role in HR),
    {"state": PENDING_GM, "action": APPROVE, "next_state": PENDING_ED, "allowed": GM},
    {"state": PENDING_GM, "action": RETURN, "next_state": DRAFT, "allowed": GM},
    {"state": PENDING_ED, "action": APPROVE, "next_state": APPROVED, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": DRAFT, "allowed": ED},
    {"state": APPROVED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# the signature each step leaves, stamped as the review leaves that step
STAMPS = {
    DRAFT: ("sent_by", "shared_on"),
    PENDING_GM: ("gm_by", "gm_on"),
    PENDING_ED: ("decided_by", "decided_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# who is waiting at each step, and the remarks that step writes
ROLE_WAITING = {PENDING_GM: GM, PENDING_ED: ED}
REMARK_FIELDS = {PENDING_GM: "gm_remarks", PENDING_ED: "management_remarks"}


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after a step: the leaving step stamped with who and
    when; a return to Draft clears them all, as the review starts over."""
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
    """What a step needs. facts: "rows" (the employees, each with its
    "decision" and name), "return_remarks", "unfinished" (the names of
    those whose appraisal is not completed: a decision is made on a final
    score only)."""
    if old_state == new_state:
        return []
    errors = []
    rows = facts.get("rows") or []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks what must be put right.")
        return errors
    if new_state in PENDING_STATES + (APPROVED,):
        if not rows:
            errors.append("There are no appraisal results on the review. Get them first.")
        undecided = [_text(row.get("employee_name")) or _text(row.get("employee")) for row in rows
                     if not _text(row.get("decision"))]
        if undecided:
            errors.append("Every employee needs a decision before the review goes on: %s." % _list(undecided))
        unfinished = [_text(name) for name in facts.get("unfinished") or ()]
        if unfinished:
            errors.append("These appraisals are not completed yet: %s. Take them off the review, or wait until "
                          "they are." % _list(unfinished))
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


def _list(names, most=5):
    shown = ", ".join(names[:most])
    return shown + (" and %d more" % (len(names) - most) if len(names) > most else "")


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))
