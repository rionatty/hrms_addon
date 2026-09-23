# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Late Arrival Notice workflow: the minutes' recommendation that
"employees who communicate their late coming in advance should be given a
full day" (Reward and Compensation, §7; the attendance test script says the
same).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (attendance.setup_workflows_on_migrate).

    Draft (the employee, their supervisor taking a call, or HR)
      --Notify--> Pending Supervisor      (the time it was sent is the time
                                           the notice was given)
      --Acknowledge--> Acknowledged (submitted: the day is a full day, and
                                     the arrival is not counted late)
      --Decline--> Declined               (the supervisor says why)
"""

DOCTYPE = "Late Arrival Notice"
WORKFLOW_NAME = "Late Arrival Notice"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
PENDING_SUPERVISOR = "Pending Supervisor"
ACKNOWLEDGED = "Acknowledged"
DECLINED = "Declined"
CANCELLED = "Cancelled"

NOTIFY = "Notify"
ACKNOWLEDGE = "Acknowledge"
DECLINE = "Decline"
CANCEL = "Cancel"
ACTIONS = (NOTIFY, ACKNOWLEDGE, DECLINE, CANCEL)

PREPARERS = ("Employee", "Supervisor", "HR User", "HR Manager")
SUPERVISORS = ("Supervisor", "Head of Department")
HRM = "HR Manager"
NEW_ROLES = ("Supervisor", "Head of Department")
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_SUPERVISOR,)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "allow_edit": role, "status": PENDING_SUPERVISOR, "style": "Warning",
       "send_email": 1} for role in SUPERVISORS),
    *({"state": ACKNOWLEDGED, "allow_edit": role, "status": ACKNOWLEDGED, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in SUPERVISORS),
    *({"state": DECLINED, "allow_edit": role, "status": DECLINED, "style": "Danger", "send_email": 0}
      for role in SUPERVISORS),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": NOTIFY, "next_state": PENDING_SUPERVISOR, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_SUPERVISOR, "action": ACKNOWLEDGE, "next_state": ACKNOWLEDGED, "allowed": role}
      for role in SUPERVISORS),
    *({"state": PENDING_SUPERVISOR, "action": DECLINE, "next_state": DECLINED, "allowed": role}
      for role in SUPERVISORS),
    {"state": ACKNOWLEDGED, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# who acted, stamped as the notice leaves each state
STAMPS = {
    PENDING_SUPERVISOR: ("acknowledged_by", "acknowledged_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
ROLE_WAITING = {PENDING_SUPERVISOR: "Supervisor"}


def compute_stamps(old_state, new_state, user, today, current):
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state != new_state and old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """facts: "supervisor_remarks"."""
    if old_state != new_state and new_state == DECLINED and not _text(facts.get("supervisor_remarks")):
        return ["Write the supervisor's remarks saying why the notice is not accepted."]
    return []


def next_states(state, roles):
    roles = set(roles or ())
    out = []
    for transition in TRANSITIONS:
        if transition["state"] != state or transition["allowed"] not in roles:
            continue
        if (transition["action"], transition["next_state"]) not in out:
            out.append((transition["action"], transition["next_state"]))
    return out


def _text(value):
    return (value or "").strip()
