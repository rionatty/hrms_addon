# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Safety Incident workflow: review items 12 and 16 (Luuka, 5 Nov 2026).

  12. "On safety, the EHS officers are 3 i.e one per plant. Need make their
      approval fixed."
  16. "Under safety, the incident report and investigation report differ.
      Need acknowledge these two reports in the system"

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (safety.setup_workflows_on_migrate).

    Draft (whoever reports the accident: the supervisor, the head of
           department, HR or the EHS Officer)
      --Send to EHS Officer--> Pending EHS Officer (the plant's own, filled
                 in from who holds the role there: nobody picks another)
      --Approve--> Pending HR (the incident report attached)
      --Acknowledge--> Recorded (submitted: HR have the incident report, and
                 the sick leave the doctor gave is raised)
      --Submit Investigation--> Investigated (the investigation report, the
                 root cause and the findings)
      --Acknowledge Investigation--> Closed (HR have the investigation report)
    Pending EHS Officer, Pending HR --Return--> Draft (Return Remarks)
    Investigated --Return Investigation--> Recorded (Investigation Remarks)
    Recorded, Investigated, Closed --Cancel--> Cancelled (the HR Manager)

The plant's EHS Officer is the one who approves the incident report and
submits the investigation, or the HR Manager when the officer is away.
Nobody else, whatever their role: step_errors refuses anyone who is not the
officer named on the incident, and safety.py names the officer itself. Each
report has its own two signatures, the officer's and HR's acknowledgement,
stamped with who and when.

No state sends Frappe's own workflow email, which goes to every holder of
the next role: the glue tells the plant's officer and HR by name.

The incident's own Status says where the employee stands (on sick leave,
back at work); the workflow's state goes in Approval Status beside it.
"""

DOCTYPE = "Safety Incident"
WORKFLOW_NAME = "Safety Incident"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_EHS = "Pending EHS Officer"
PENDING_HR = "Pending HR"
RECORDED = "Recorded"
INVESTIGATED = "Investigated"
CLOSED = "Closed"
CANCELLED = "Cancelled"

SEND = "Send to EHS Officer"
APPROVE = "Approve"
ACKNOWLEDGE = "Acknowledge"
SUBMIT_INVESTIGATION = "Submit Investigation"
ACKNOWLEDGE_INVESTIGATION = "Acknowledge Investigation"
RETURN = "Return"
RETURN_INVESTIGATION = "Return Investigation"
CANCEL = "Cancel"
ACTIONS = (SEND, APPROVE, ACKNOWLEDGE, SUBMIT_INVESTIGATION, ACKNOWLEDGE_INVESTIGATION, RETURN,
           RETURN_INVESTIGATION, CANCEL)

EHS = "EHS Officer"
HR_OFFICER, HRM = "HR User", "HR Manager"
HR = (HR_OFFICER, HRM)
# who reports an accident
REPORTERS = ("Supervisor", "Head of Department", HR_OFFICER, HRM, EHS)
# who acts for the plant's EHS Officer: the officer, or the HR Manager
OFFICERS = (EHS, HRM)
NEW_ROLES = (EHS, "Supervisor", "Head of Department")
# the Safety Incident is ours: who may do what is in its DocType
PERMISSIONS = {}

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in REPORTERS),
    *({"state": PENDING_EHS, "allow_edit": role, "status": PENDING_EHS, "style": "Warning", "send_email": 0}
      for role in OFFICERS),
    *({"state": PENDING_HR, "allow_edit": role, "status": PENDING_HR, "style": "Warning", "send_email": 0}
      for role in HR),
    *({"state": RECORDED, "allow_edit": role, "status": RECORDED, "style": "Info", "send_email": 0, "doc_status": "1"}
      for role in (EHS,) + HR),
    *({"state": INVESTIGATED, "allow_edit": role, "status": INVESTIGATED, "style": "Warning", "send_email": 0,
       "doc_status": "1"} for role in HR),
    *({"state": CLOSED, "allow_edit": role, "status": CLOSED, "style": "Success", "send_email": 0, "doc_status": "1"}
      for role in (EHS,) + HR),
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": SEND, "next_state": PENDING_EHS, "allowed": role} for role in REPORTERS),
    *({"state": PENDING_EHS, "action": APPROVE, "next_state": PENDING_HR, "allowed": role} for role in OFFICERS),
    *({"state": PENDING_EHS, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in OFFICERS),
    *({"state": PENDING_HR, "action": ACKNOWLEDGE, "next_state": RECORDED, "allowed": role} for role in HR),
    *({"state": PENDING_HR, "action": RETURN, "next_state": DRAFT, "allowed": role} for role in HR),
    *({"state": RECORDED, "action": SUBMIT_INVESTIGATION, "next_state": INVESTIGATED, "allowed": role}
      for role in OFFICERS),
    *({"state": INVESTIGATED, "action": ACKNOWLEDGE_INVESTIGATION, "next_state": CLOSED, "allowed": role}
      for role in HR),
    *({"state": INVESTIGATED, "action": RETURN_INVESTIGATION, "next_state": RECORDED, "allowed": role}
      for role in HR),
    *({"state": state, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM}
      for state in (RECORDED, INVESTIGATED, CLOSED)),
)

# each report's two signatures: who left the state forward, and when
STAMPS = {
    PENDING_EHS: ("incident_report_by", "incident_report_on"),
    PENDING_HR: ("incident_acknowledged_by", "incident_acknowledged_on"),
    RECORDED: ("investigated_by", "investigated_on"),
    INVESTIGATED: ("investigation_acknowledged_by", "investigation_acknowledged_on"),
}
FORWARD = {PENDING_EHS: PENDING_HR, PENDING_HR: RECORDED, RECORDED: INVESTIGATED, INVESTIGATED: CLOSED}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
# the incident report's signatures, cleared when it is returned to its reporter
INCIDENT_STAMP_FIELDS = STAMPS[PENDING_EHS] + STAMPS[PENDING_HR]
# where the plant's EHS Officer acts now or next: the officer named on the
# incident is the one who holds the role for the plant today
OFFICER_STATES = (DRAFT, PENDING_EHS, RECORDED)
PENDING_STATES = (PENDING_EHS, PENDING_HR, INVESTIGATED)
ROLE_WAITING = {PENDING_EHS: EHS, PENDING_HR: HR_OFFICER, RECORDED: EHS, INVESTIGATED: HR_OFFICER}


def officer_fixed(old_state, new_state):
    """Whether the save names the plant's EHS Officer again: while the
    officer is still to act on the incident, and as they act."""
    return new_state in OFFICER_STATES or old_state in OFFICER_STATES


def compute_stamps(old_state, new_state, user, today, current):
    """The signatures after a step. current: the ones the incident had
    before it, as saved (never as typed on the form)."""
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if FORWARD.get(old_state) == new_state:
        values.update(zip(STAMPS[old_state], (user, today)))
    elif new_state == DRAFT:
        values.update(dict.fromkeys(INCIDENT_STAMP_FIELDS))
    elif old_state == INVESTIGATED and new_state == RECORDED:
        values.update(dict.fromkeys(STAMPS[RECORDED]))
    return values


def step_errors(old_state, new_state, facts):
    """What a step needs, and who may take it. facts: "user", "is_hrm",
    "ehs_officer" (the plant's, as safety.py names it), "branch", and the
    reports and texts "incident_report", "investigation_report",
    "root_cause", "findings", "return_remarks", "investigation_remarks"."""
    if old_state == new_state or not new_state:
        return []
    user, officer = facts.get("user"), facts.get("ehs_officer")
    for_plant = bool(user) and (user == officer or bool(facts.get("is_hrm")))
    plant = facts.get("branch") or "the employee's"
    errors = []
    if new_state == PENDING_EHS:
        if not officer:
            errors.append("No EHS Officer serves the %s plant: give one the EHS Officer role and a Branch User "
                          "Permission for the plant." % plant)
    elif old_state == PENDING_EHS:
        if not for_plant:
            errors.append("The incident report is for %s, the %s plant's EHS Officer, to approve or return (or the "
                          "HR Manager)." % (officer or "the EHS Officer", plant))
        if new_state == PENDING_HR and not facts.get("incident_report"):
            errors.append("Attach the incident report before approving it.")
    elif old_state == RECORDED and new_state == INVESTIGATED:
        if not for_plant:
            errors.append("The investigation report is submitted by %s, the %s plant's EHS Officer (or the HR "
                          "Manager)." % (officer or "the EHS Officer", plant))
        if not facts.get("investigation_report"):
            errors.append("Attach the investigation report.")
        if not _text(facts.get("root_cause")):
            errors.append("Say what caused the accident (Root Cause).")
        if not _text(facts.get("findings")):
            errors.append("Write the investigation's findings and what is done so it does not happen again.")
    if new_state == DRAFT and old_state in (PENDING_EHS, PENDING_HR) and not _text(facts.get("return_remarks")):
        errors.append("Write in Return Remarks what must be put right before returning the incident.")
    if old_state == INVESTIGATED and new_state == RECORDED and not _text(facts.get("investigation_remarks")):
        errors.append("Write in Investigation Remarks what the investigation must still answer.")
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


def _text(value):
    return (value or "").strip()
