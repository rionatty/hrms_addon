# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Penalty workflow (Reward and Compensation, §4.11).

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (penalties.setup_workflows_on_migrate).

    Draft (the supervisor reports the case, or HR for them)
      --Report--> Pending Hearing       (the HR Officer hears it with the
                                          employee and the supervisor)
      --Found Liable--> Pending Employee Consent   (the instalments agreed;
                                                    LPL/HR/39)
      --Clear--> Not Liable (submitted: nothing is deducted)
      --Consent--> Pending HR Manager   (who forwards it, and signs as Head
                                          HR, in whose presence it is made)
      --Forward--> Pending Executive Director
      --Approve--> Pending HR Officer   ("then sent back to the Human
                                          Resource Officer")
      --Send to Payroll--> Recovering (submitted: each instalment becomes a
                                       deduction on the payroll)
    Pending Employee Consent --Dispute--> Pending Hearing (the employee does
                                          not agree to what was decided)
    the HR Manager and the Executive Director --Return--> Pending Hearing
    the Executive Director --Reject--> Rejected
    the HR Officer, before the hearing --Return--> Draft
"""

DOCTYPE = "Employee Penalty"
WORKFLOW_NAME = "Employee Penalty"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "approval_status"

DRAFT = "Draft"
PENDING_HEARING = "Pending Hearing"
PENDING_CONSENT = "Pending Employee Consent"
PENDING_HRM = "Pending HR Manager"
PENDING_ED = "Pending Executive Director"
PENDING_HR_OFFICER = "Pending HR Officer"
RECOVERING = "Recovering"
NOT_LIABLE = "Not Liable"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

REPORT = "Report"
FIND_LIABLE = "Found Liable"
CLEAR = "Clear"
CONSENT = "Consent"
DISPUTE = "Dispute"
FORWARD = "Forward"
APPROVE = "Approve"
SEND = "Send to Payroll"
RETURN = "Return"
REJECT = "Reject"
CANCEL = "Cancel"
ACTIONS = (REPORT, FIND_LIABLE, CLEAR, CONSENT, DISPUTE, FORWARD, APPROVE, SEND, RETURN, REJECT, CANCEL)

SUPERVISOR = "Supervisor"
HR_OFFICER, HRM = "HR User", "HR Manager"
ED = "Executive Director"
EMPLOYEE = "Employee"
PAYROLL = "Payroll Officer"
PREPARERS = (SUPERVISOR, HR_OFFICER, HRM)
NEW_ROLES = (SUPERVISOR, ED, PAYROLL)
# the DocType carries every role's rights
PERMISSIONS = {}

PENDING_STATES = (PENDING_HEARING, PENDING_CONSENT, PENDING_HRM, PENDING_ED, PENDING_HR_OFFICER)
# the order the desks sign in: sending a case back to one clears its
# signature and every one after it, so each is given again
ORDER = (DRAFT, PENDING_HEARING, PENDING_CONSENT, PENDING_HRM, PENDING_ED, PENDING_HR_OFFICER)

STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": DRAFT, "style": "", "send_email": 0} for role in PREPARERS),
    *({"state": PENDING_HEARING, "allow_edit": role, "status": PENDING_HEARING, "style": "Warning",
       "send_email": 1} for role in (HR_OFFICER, HRM)),
    # HR record the consent of somebody with no login, with the form they signed
    *({"state": PENDING_CONSENT, "allow_edit": role, "status": PENDING_CONSENT, "style": "Warning",
       "send_email": 1} for role in (EMPLOYEE, HR_OFFICER)),
    {"state": PENDING_HRM, "allow_edit": HRM, "status": PENDING_HRM, "style": "Warning", "send_email": 1},
    {"state": PENDING_ED, "allow_edit": ED, "status": PENDING_ED, "style": "Warning", "send_email": 1},
    *({"state": PENDING_HR_OFFICER, "allow_edit": role, "status": PENDING_HR_OFFICER, "style": "Warning",
       "send_email": 1} for role in (HR_OFFICER, HRM)),
    *({"state": RECOVERING, "allow_edit": role, "status": RECOVERING, "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (HR_OFFICER, HRM)),
    *({"state": NOT_LIABLE, "allow_edit": role, "status": NOT_LIABLE, "style": "Info", "send_email": 0,
       "doc_status": "1"} for role in (HR_OFFICER, HRM)),
    {"state": REJECTED, "allow_edit": ED, "status": REJECTED, "style": "Danger", "send_email": 0,
     "doc_status": "1"},
    {"state": CANCELLED, "allow_edit": HRM, "status": CANCELLED, "style": "Danger", "send_email": 0,
     "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": REPORT, "next_state": PENDING_HEARING, "allowed": role} for role in PREPARERS),
    *({"state": PENDING_HEARING, "action": FIND_LIABLE, "next_state": PENDING_CONSENT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HEARING, "action": CLEAR, "next_state": NOT_LIABLE, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_HEARING, "action": RETURN, "next_state": DRAFT, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    *({"state": PENDING_CONSENT, "action": CONSENT, "next_state": PENDING_HRM, "allowed": role}
      for role in (EMPLOYEE, HR_OFFICER)),
    *({"state": PENDING_CONSENT, "action": DISPUTE, "next_state": PENDING_HEARING, "allowed": role}
      for role in (EMPLOYEE, HR_OFFICER)),
    {"state": PENDING_HRM, "action": FORWARD, "next_state": PENDING_ED, "allowed": HRM},
    {"state": PENDING_HRM, "action": RETURN, "next_state": PENDING_HEARING, "allowed": HRM},
    {"state": PENDING_ED, "action": APPROVE, "next_state": PENDING_HR_OFFICER, "allowed": ED},
    {"state": PENDING_ED, "action": RETURN, "next_state": PENDING_HEARING, "allowed": ED},
    {"state": PENDING_ED, "action": REJECT, "next_state": REJECTED, "allowed": ED},
    *({"state": PENDING_HR_OFFICER, "action": SEND, "next_state": RECOVERING, "allowed": role}
      for role in (HR_OFFICER, HRM)),
    {"state": RECOVERING, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM},
)

# who acted at each desk, stamped as the case leaves it
STAMPS = {
    DRAFT: ("reported_by", "reported_on"),
    PENDING_HEARING: ("heard_by", "heard_on"),
    PENDING_CONSENT: ("consent_by", "consent_on"),
    PENDING_HRM: ("hrm_by", "hrm_on"),
    PENDING_ED: ("ed_by", "ed_on"),
    PENDING_HR_OFFICER: ("sent_by", "sent_on"),
}
ALL_STAMP_FIELDS = tuple(field for pair in STAMPS.values() for field in pair)
REMARK_FIELDS = {
    PENDING_HRM: ("hrm_remarks", "HR Manager"),
    PENDING_ED: ("ed_remarks", "Executive Director"),
}
ROLE_WAITING = {
    PENDING_HEARING: HR_OFFICER,
    PENDING_CONSENT: EMPLOYEE,
    PENDING_HRM: HRM,
    PENDING_ED: ED,
    PENDING_HR_OFFICER: HR_OFFICER,
}


def is_backwards(old_state, new_state):
    return old_state in ORDER and new_state in ORDER and ORDER.index(new_state) < ORDER.index(old_state)


def compute_stamps(old_state, new_state, user, today, current):
    if not old_state:
        return dict.fromkeys(ALL_STAMP_FIELDS)
    values = {field: (current or {}).get(field) for field in ALL_STAMP_FIELDS}
    if old_state == new_state:
        return values
    if is_backwards(old_state, new_state):
        for state in ORDER[ORDER.index(new_state):]:
            values.update(dict.fromkeys(STAMPS.get(state, ())))
        return values
    if old_state in STAMPS:
        values.update(zip(STAMPS[old_state], (user, today)))
    return values


def step_errors(old_state, new_state, facts):
    """Problems with a step, as user-facing messages.

    facts: "return_remarks", "finding" and the remark fields.
    """
    if old_state == new_state:
        return []
    errors = []
    if is_backwards(old_state, new_state):
        if not _text(facts.get("return_remarks")):
            errors.append("Write in Return Remarks why the case goes back."
                          if old_state != PENDING_CONSENT else
                          "Write in Return Remarks what the employee does not agree to.")
        return errors
    if new_state == PENDING_CONSENT and facts.get("finding") != "Liable":
        errors.append("The finding is Liable before the employee is asked to consent.")
    if new_state == NOT_LIABLE and facts.get("finding") != "Not Liable":
        errors.append("Set the finding to Not Liable to clear the employee.")
    if new_state == REJECTED and old_state in REMARK_FIELDS:
        field, who = REMARK_FIELDS[old_state]
        if not _text(facts.get(field)):
            errors.append("Write the %s's remarks saying why the penalty is refused." % who)
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
