# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview Shortlist screening: steps 10 and 11 of Luuka's resourcing process.

  10. The HR Officer reviews and screens the applicants and shares the data
      with the HOD for further review.
  11. The HOD does the second and final screening.

No Frappe import, like the other approval modules, so scripts/verify_interviews.py
walks every path without a bench. workflows.py builds the Workflow from it on
every migrate (interviews.setup_shortlist_workflow_on_migrate).

    Draft --Share with HOD--> Pending HOD Screening --Approve--> Screened (submitted)
    Pending HOD Screening --Return to HR--> Returned to HR --Revise--> Draft
    Screened --Cancel--> Cancelled (the HR Manager)

A submitted document under a workflow is cancelled through the workflow:
Frappe's own Cancel leaves the state as it was (Document skips validation,
and with it the workflow, on cancel), so the list would go on calling a
cancelled shortlist Screened.

The HOD is named on the shortlist (the requisition's HOD by default) and the
shortlist is assigned to them when it is shared, so only that HOD is told;
the workflow's own emails, which go to everyone holding the role, stay off.
"""

DOCTYPE = "Interview Shortlist"
WORKFLOW_NAME = "Interview Shortlist Screening"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_HOD = "Pending HOD Screening"
SCREENED = "Screened"
RETURNED = "Returned to HR"
CANCELLED = "Cancelled"

SHARE = "Share with HOD"
APPROVE = "Approve"
RETURN = "Return to HR"
REVISE = "Revise"
CANCEL = "Cancel"
ACTIONS = (SHARE, APPROVE, RETURN, REVISE, CANCEL)

# Who screens first (the HR Officer is HR User) and shares
PREPARERS = ("HR User", "HR Manager")
# Who does the second and final screening
SCREENER = "Head of Department"
# Who may cancel a screened shortlist (the DocType gives only them cancel)
CANCELLER = "HR Manager"

# The requisition workflow creates this role too; ensured here as well
NEW_ROLES = (SCREENER,)

# The HOD edits the list (removing candidates, adding remarks) and their
# approval submits it. HR's own roles are in the DocType.
PERMISSIONS = {DOCTYPE: {SCREENER: ("read", "write", "submit")}}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    {"state": PENDING_HOD, "allow_edit": SCREENER, "status": PENDING_HOD, "style": "Warning", "send_email": 0},
    {"state": SCREENED, "allow_edit": "HR Manager", "status": SCREENED, "style": "Success", "send_email": 0, "doc_status": "1"},
    *({"state": RETURNED, "allow_edit": role, "status": RETURNED, "style": "Danger", "send_email": 0} for role in PREPARERS),
    {"state": CANCELLED, "allow_edit": CANCELLER, "status": CANCELLED, "style": "Danger", "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SHARE, "next_state": PENDING_HOD, "allowed": role} for role in PREPARERS),
    {"state": PENDING_HOD, "action": APPROVE, "next_state": SCREENED, "allowed": SCREENER},
    {"state": PENDING_HOD, "action": RETURN, "next_state": RETURNED, "allowed": SCREENER},
    *({"state": RETURNED, "action": REVISE, "next_state": DRAFT, "allowed": role} for role in PREPARERS),
    {"state": SCREENED, "action": CANCEL, "next_state": CANCELLED, "allowed": CANCELLER},
)

# Who screened, and when: HR when sharing, the HOD when approving
STAMPS = {
    DRAFT: ("hr_screened_by", "hr_screened_on"),
    PENDING_HOD: ("hod_screened_by", "hod_screened_on"),
}
STAMP_FIELDS = ("hr_screened_by", "hr_screened_on", "hod_screened_by", "hod_screened_on")


def next_states(state, roles):
    """[(action, next state)] the holder of `roles` may take from `state`."""
    roles = set(roles or ())
    return [(t["action"], t["next_state"]) for t in TRANSITIONS if t["state"] == state and t["allowed"] in roles]


def compute_stamps(old_state, new_state, user, today, current):
    """Every screening sign-off's value after this save.

    Sharing records the HR screener; the HOD's approval records the HOD. A
    return keeps HR's and records nothing, a revision starts over, a new
    shortlist has none, and otherwise the stored values stand, so a date
    typed in does not survive the save.
    """
    if not old_state:
        return dict.fromkeys(STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in STAMP_FIELDS}
    if old_state == new_state:
        return values
    if old_state == RETURNED and new_state == DRAFT:
        return dict.fromkeys(STAMP_FIELDS)
    if old_state in STAMPS and new_state != RETURNED:
        who, when = STAMPS[old_state]
        values[who], values[when] = user, today
    return values


def screening_errors(old_state, new_state, head_of_department, hod_comments):
    """Problems with a transition: sharing needs the HOD who is to screen, and
    returning needs the HOD's reason, which is all HR has to go on."""
    if old_state == new_state:
        return []
    if new_state == PENDING_HOD and not head_of_department:
        return ["Name the Head of Department who does the second screening before sharing the shortlist."]
    if new_state == RETURNED and not (hod_comments or "").strip():
        return ["Write in HOD's Comments what HR should change before returning the shortlist."]
    return []


def assignee(old_state, new_state, head_of_department, owner):
    """Who the shortlist is assigned to after this save: the HOD when it is
    shared, back to whoever prepared it when returned, nobody otherwise."""
    if old_state == new_state:
        return None
    if new_state == PENDING_HOD:
        return head_of_department or None
    if new_state == RETURNED:
        return owner or None
    return None
