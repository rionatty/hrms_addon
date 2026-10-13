# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Overtime Request workflow: LPL/HR/14 approved as every other request is.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (attendance.setup_workflows_on_migrate).
Luuka, 12 Oct 2026: "make the approval like normal approval not like this".
The request had buttons of its own (Authorise, Check the Cost); it now has
the Actions menu every other request has.

    Draft (the supervisor, the section head or HR who raises it)
      --Submit--> Requested   (waits for the authorising officer)
      --Approve--> Authorised (waits for HR, who see what it costs)
      --Approve--> Costed     (approved and submitted, the cost on it)
    Requested or Authorised --Return--> Draft (the reason in Return Remarks)
    Requested or Authorised --Reject--> Rejected (the reason in the remarks
                                        of whoever refuses)
    Costed or Sent to Payroll --Cancel--> Cancelled (its hours taken back)

Sent to Payroll is not an approval. It is set when the hours are written
onto the attendance (overtime.send): by the system as the day's attendance
comes in, or by HR from the form.
"""

DOCTYPE = "Overtime Request"
WORKFLOW_NAME = "Overtime Request"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
REQUESTED = "Requested"
AUTHORISED = "Authorised"
COSTED = "Costed"
SENT = "Sent to Payroll"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

SUBMIT = "Submit"
APPROVE = "Approve"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (SUBMIT, APPROVE, RETURN, REJECT, CANCEL)

PREPARERS = ("Supervisor", "Head of Department", "Production Manager", "HR User", "HR Manager")
AUTHORISERS = ("Production Manager", "Head of Department", "HR Manager")
HR = ("HR User", "HR Manager")
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department", "Production Manager")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (REQUESTED, AUTHORISED)
# a state the hours can still be refused or returned from, and who holds it
WAITING_ON = {REQUESTED: AUTHORISERS, AUTHORISED: HR}

# no state mails the document: it carries people's hourly pay once it is costed
STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": REQUESTED, "allow_edit": role, "status": REQUESTED, "style": "Warning", "send_email": 0}
      for role in AUTHORISERS),
    *({"state": AUTHORISED, "allow_edit": role, "status": AUTHORISED, "style": "Warning", "send_email": 0}
      for role in HR),
    {"state": COSTED, "allow_edit": HRM, "status": COSTED, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": SENT, "allow_edit": HRM, "status": SENT, "style": "Success", "send_email": 0, "doc_status": "1"},
    {"state": REJECTED, "allow_edit": HRM, "status": REJECTED, "style": "Danger", "send_email": 0, "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SUBMIT, "next_state": REQUESTED, "allowed": role} for role in PREPARERS),
    *({"state": REQUESTED, "action": APPROVE, "next_state": AUTHORISED, "allowed": role} for role in AUTHORISERS),
    *({"state": REQUESTED, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in AUTHORISERS),
    *({"state": REQUESTED, "action": REJECT, "next_state": REJECTED, "allowed": role} for role in AUTHORISERS),
    *({"state": AUTHORISED, "action": APPROVE, "next_state": COSTED, "allowed": role} for role in HR),
    *({"state": AUTHORISED, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in HR),
    *({"state": AUTHORISED, "action": REJECT, "next_state": REJECTED, "allowed": role} for role in HR),
    {"state": COSTED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
    {"state": SENT, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# Who signs as each step is passed: state left -> (by, on)
STAMPS = {
    REQUESTED: ("authorised_by", "authorised_on"),
    AUTHORISED: ("costed_by", "costed_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# where whoever refuses says why: state left -> (field, who)
REMARK_FIELDS = {
    REQUESTED: ("authority_remarks", "authorising officer"),
    AUTHORISED: ("cost_remarks", "HR"),
}


def docstatus_of(state):
    """0, 1 or 2: what a document at this state is."""
    for row in STATES:
        if row["state"] == state:
            return int(row.get("doc_status", "0"))
    return 0


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after this save: the step just passed is signed by
    `user` today (an approval or a refusal alike: it is who decided), a
    return to Draft clears them all, and anything typed into a signature
    reverts to what it was (`current`)."""
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
    """Problems with a step, as user-facing messages. facts:
    "return_remarks", "authority_remarks", "cost_remarks"."""
    if old_state == new_state:
        return []
    if new_state == DRAFT and old_state in PENDING_STATES:
        if not _text(facts.get("return_remarks")):
            return ["Write in Return Remarks what must be put right before returning the request."]
        return []
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            return ["Write the %s's remarks saying why the overtime is refused." % who]
    return []


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def stage_of(docstatus, status):
    """Where a request raised before the workflow stands on it: (state,
    docstatus). It was submitted the moment it was raised; on the workflow
    it is submitted when HR approve it, so one that was waiting to be
    authorised or costed goes back to a draft at that step, for whoever
    holds it to take from the Actions menu."""
    docstatus = int(docstatus or 0)
    if docstatus == 2:
        return CANCELLED, 2
    if docstatus == 0:
        return DRAFT, 0
    if status in (COSTED, SENT, REJECTED):
        return status, 1
    if status == AUTHORISED:
        return AUTHORISED, 0
    return REQUESTED, 0


def _text(value):
    return (value or "").strip()
