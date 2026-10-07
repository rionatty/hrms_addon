# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employee Grievance workflow: the non-disciplinary grievance (5.4 and the
test sheet's Non Disciplinary cases 1 to 11) on Frappe HR's own Employee
Grievance.

No Frappe import, like the other approval modules; workflows.py builds the
Workflow from it on every migrate (grievances.setup_on_migrate).

    Draft (the employee, or HR for them; numbered LPL-GRV-YYYY- when first
    saved)
      --Raise--> Open (the employee is told it is received, HR are told it
                 is waiting)
      --Route to Handler--> Under Review (the handler, from the Grievance
                 Type unless HR name one, is told and given it to do; the
                 clock starts)
      --Resolve--> Resolved (findings, cause, outcome and remedy; the
                 employee is told and asked to accept or appeal)
      --Accept--> Closed (filed)
      --Appeal--> Appealed (heard by someone who has not acted in it)
      --Decide Appeal--> Appeal Decided (filed)
    Open --Mark Invalid--> Invalid (filed, with the reason)
    Under Review --Return to HR--> Open (the handler says why)
    Resolved --Reopen--> Under Review (not resolved: back to the handler)
    Closed, Appeal Decided, Invalid --Cancel--> Cancelled

Frappe HR files a grievance only once it is Resolved or Invalid, so it
stays a draft while it is handled and is filed at the end. Each state also
writes Frappe HR's own status (FRAPPE_STATUS), which their submit rule,
lists and reports read.
"""

import re

DOCTYPE = "Employee Grievance"
WORKFLOW_NAME = "Employee Grievance"
STATE_FIELD = "workflow_state"
STATUS_FIELD = "status"

DRAFT = "Draft"
OPEN = "Open"
UNDER_REVIEW = "Under Review"
RESOLVED = "Resolved"
CLOSED = "Closed"
APPEALED = "Appealed"
APPEAL_DECIDED = "Appeal Decided"
INVALID = "Invalid"
CANCELLED = "Cancelled"
# the states a grievance is filed in (docstatus 1)
FILED = (CLOSED, APPEAL_DECIDED, INVALID)
# the states a grievance is in someone's hands against its due date
TIMED = (UNDER_REVIEW, APPEALED)

RAISE = "Raise"
ROUTE = "Route to Handler"
MARK_INVALID = "Mark Invalid"
RETURN = "Return to HR"
RESOLVE = "Resolve"
ACCEPT = "Accept"
REOPEN = "Reopen"
APPEAL = "Appeal"
DECIDE_APPEAL = "Decide Appeal"
CANCEL = "Cancel"
ACTIONS = (RAISE, ROUTE, MARK_INVALID, RETURN, RESOLVE, ACCEPT, REOPEN, APPEAL, DECIDE_APPEAL, CANCEL)

EMPLOYEE = "Employee"
HR_OFFICER = "HR User"
HRM = "HR Manager"
HOD = "Head of Department"
GM = "General Manager"
ED = "Executive Director"
HR = (HR_OFFICER, HRM)
# who may handle a grievance: a Head of Department, or HR themselves
HANDLER_ROLES = (HOD,) + HR
# who may hear an appeal, the first not already involved: the plant's
# General Manager, the HR Manager, the Executive Director
AUTHORITIES = (GM, HRM, ED)
NEW_ROLES = (HOD, GM, ED)

# Frappe HR's own status for each state: their lists and reports read it,
# and they file a grievance only at Resolved or Invalid
FRAPPE_STATUS = {DRAFT: "Open", OPEN: "Open", UNDER_REVIEW: "Investigated", RESOLVED: "Resolved",
                 CLOSED: "Resolved", APPEALED: "Investigated", APPEAL_DECIDED: "Resolved", INVALID: "Invalid",
                 CANCELLED: "Cancelled"}
FRAPPE_STATUSES = ("Open", "Investigated", "Resolved", "Invalid", "Cancelled")

# Frappe HR gives the Employee and the HR Officer no submit, and the
# handler and the appeal's authority nothing at all. Whoever takes a step
# into a filed state needs submit: the employee accepting, HR marking it
# invalid, the General Manager or the Executive Director deciding an appeal
PERMISSIONS = {DOCTYPE: {
    EMPLOYEE: ("read", "write", "create", "submit"),
    HR_OFFICER: ("read", "write", "create", "submit"),
    HOD: ("read", "write"),
    GM: ("read", "write", "submit"),
    ED: ("read", "write", "submit"),
}}
# the decision fields sit at level one (case 11): the employee who raised
# the grievance reads them and changes none of them
LEVEL = 1
LEVEL_ONE = {EMPLOYEE: ("read",), HR_OFFICER: ("read", "write"), HRM: ("read", "write"),
             HOD: ("read", "write"), GM: ("read", "write"), ED: ("read", "write"),
             "System Manager": ("read", "write"), "Auditor": ("read",), "Management Viewer": ("read",)}
DECISION_FIELDS = ("resolution_detail", "resolved_by", "resolution_date", "employee_responsible")
DECISION_CUSTOM_FIELDS = ("custom_assigned_hod", "custom_due_on", "custom_meeting_notes", "custom_remedy",
                          "custom_appeals_authority", "custom_appeal_outcome")
# who may delete a grievance once it is raised (delete_errors)
DELETERS = (HRM, "System Manager")
# the employee's own account of the grievance: once raised, only HR change it
STATEMENT_FIELDS = ("raised_by", "date", "subject", "description", "grievance_type", "custom_informal_notes")

# no state sends Frappe's own workflow email: it goes, with the print, to
# every holder of the next role who can read the grievance, which with no
# Department User Permissions is every head of department. The glue tells
# the handler, HR and the employee by name (grievances.py)
STATES = (
    *({"state": DRAFT, "allow_edit": role, "status": FRAPPE_STATUS[DRAFT], "style": "", "send_email": 0}
      for role in (EMPLOYEE,) + HR),
    *({"state": OPEN, "allow_edit": role, "status": FRAPPE_STATUS[OPEN], "style": "Warning", "send_email": 0}
      for role in HR),
    *({"state": UNDER_REVIEW, "allow_edit": role, "status": FRAPPE_STATUS[UNDER_REVIEW], "style": "Warning",
       "send_email": 0} for role in HANDLER_ROLES),
    *({"state": RESOLVED, "allow_edit": role, "status": FRAPPE_STATUS[RESOLVED], "style": "Info", "send_email": 0}
      for role in (EMPLOYEE,) + HR),
    *({"state": APPEALED, "allow_edit": role, "status": FRAPPE_STATUS[APPEALED], "style": "Warning",
       "send_email": 0} for role in HR + (GM, ED)),
    *({"state": CLOSED, "allow_edit": role, "status": FRAPPE_STATUS[CLOSED], "style": "Success", "send_email": 0,
       "doc_status": "1"} for role in (EMPLOYEE,) + HR),
    *({"state": APPEAL_DECIDED, "allow_edit": role, "status": FRAPPE_STATUS[APPEAL_DECIDED], "style": "Success",
       "send_email": 0, "doc_status": "1"} for role in (HRM, GM, ED)),
    *({"state": INVALID, "allow_edit": role, "status": FRAPPE_STATUS[INVALID], "style": "Danger", "send_email": 0,
       "doc_status": "1"} for role in HR),
    {"state": CANCELLED, "allow_edit": HRM, "status": FRAPPE_STATUS[CANCELLED], "style": "Danger",
     "send_email": 0, "doc_status": "2"},
)

TRANSITIONS = (
    *({"state": DRAFT, "action": RAISE, "next_state": OPEN, "allowed": role} for role in (EMPLOYEE,) + HR),
    *({"state": OPEN, "action": ROUTE, "next_state": UNDER_REVIEW, "allowed": role} for role in HR),
    *({"state": OPEN, "action": MARK_INVALID, "next_state": INVALID, "allowed": role} for role in HR),
    *({"state": UNDER_REVIEW, "action": RESOLVE, "next_state": RESOLVED, "allowed": role} for role in HANDLER_ROLES),
    {"state": UNDER_REVIEW, "action": RETURN, "next_state": OPEN, "allowed": HOD},
    *({"state": RESOLVED, "action": ACCEPT, "next_state": CLOSED, "allowed": role} for role in (EMPLOYEE,) + HR),
    *({"state": RESOLVED, "action": REOPEN, "next_state": UNDER_REVIEW, "allowed": role} for role in (EMPLOYEE,) + HR),
    *({"state": RESOLVED, "action": APPEAL, "next_state": APPEALED, "allowed": role} for role in (EMPLOYEE,) + HR),
    *({"state": APPEALED, "action": DECIDE_APPEAL, "next_state": APPEAL_DECIDED, "allowed": role}
      for role in (HRM, GM, ED)),
    *({"state": state, "action": CANCEL, "next_state": CANCELLED, "allowed": HRM}
      for state in (CLOSED, APPEAL_DECIDED, INVALID)),
)


def step_errors(old_state, new_state, facts):
    """What a step needs, and who may take it. facts: "user", "is_hr",
    "is_hrm", "raiser" (the raising employee's user), "handler" and
    "handler_roles", "authority" and "authority_roles", "involved" (users
    who have acted in it), and the texts "subject", "description",
    "grievance_type", "meeting_notes", "cause", "outcome", "remedy",
    "remarks" (Return or Reopen), "appeal_grounds", "appeal_outcome"."""
    if old_state == new_state or not new_state:
        return []
    user, is_hr = facts.get("user"), bool(facts.get("is_hr"))
    own = bool(user) and user == facts.get("raiser")
    handles = is_hr or (bool(user) and user == facts.get("handler"))
    errors = []
    if new_state == OPEN and old_state in (None, DRAFT):
        if not (own or is_hr):
            errors.append("A grievance is raised by the employee it belongs to, or by HR for them.")
        for field, message in (("grievance_type", "Say what kind of grievance it is (Grievance Type)."),
                               ("subject", "Give the grievance a subject."),
                               ("description", "Write the grievance in the employee's own words.")):
            if not _text(facts.get(field)):
                errors.append(message)
    elif new_state == UNDER_REVIEW and old_state == OPEN:
        errors += handler_errors(facts)
    elif new_state == INVALID:
        if not _text(facts.get("outcome")):
            errors.append("Say in the Resolution Details why the grievance is not taken up.")
    elif new_state == RESOLVED:
        if not handles:
            errors.append("The grievance is resolved by its handler, or by HR.")
        for field, message in (("meeting_notes", "Record the meeting notes and findings."),
                               ("cause", "Say what caused the grievance."),
                               ("outcome", "Say what the outcome is (Resolution Details)."),
                               ("remedy", "Say what the remedy is.")):
            if not _text(facts.get(field)):
                errors.append(message)
    elif new_state == OPEN and old_state == UNDER_REVIEW:
        if not handles:
            errors.append("Only its handler hands a grievance back to HR.")
        if not _text(facts.get("remarks")):
            errors.append("Say in the remarks why it goes back to HR.")
    elif old_state == RESOLVED and new_state in (CLOSED, UNDER_REVIEW, APPEALED):
        if not (own or is_hr):
            errors.append("The employee who raised the grievance answers its outcome, or HR for them.")
        if new_state == UNDER_REVIEW and not _text(facts.get("remarks")):
            errors.append("Say in the remarks what is still not resolved.")
        if new_state == APPEALED:
            if not _text(facts.get("appeal_grounds")):
                errors.append("Write the grounds of the appeal.")
            errors += authority_errors(facts)
    elif new_state == APPEAL_DECIDED:
        if not (user and user == facts.get("authority")) and not facts.get("is_hrm"):
            errors.append("The appeal is decided by who hears it, or by the HR Manager.")
        if not _text(facts.get("appeal_outcome")):
            errors.append("Write the appeal's outcome.")
    return errors


def handler_errors(facts):
    """The handler a grievance goes to: named, not the employee who raised
    it, and able to resolve it (a Head of Department, or HR)."""
    handler = facts.get("handler")
    if not handler:
        return ["Name the handler: the Grievance Type has no usual handler."]
    if handler == facts.get("raiser"):
        return ["A grievance is not handled by the employee who raised it."]
    if not set(facts.get("handler_roles") or ()) & set(HANDLER_ROLES):
        return ["The handler must hold the Head of Department role, or an HR role."]
    return []


def authority_errors(facts):
    """Who hears an appeal: named, holding a role that decides appeals, and
    not already involved in the grievance (case 9)."""
    authority = facts.get("authority")
    if not authority:
        return ["Name who hears the appeal: nobody who holds the role is free of the grievance."]
    if authority in set(facts.get("involved") or ()):
        return ["An appeal is heard by someone who has not already acted in the grievance."]
    if not set(facts.get("authority_roles") or ()) & set(AUTHORITIES):
        return ["The appeal is heard by the General Manager, the HR Manager or the Executive Director."]
    return []


def change_errors(state, changed, facts):
    """A save that takes no step: who may change what. `changed` names the
    fields the save changes."""
    changed, is_hr = set(changed or ()), bool(facts.get("is_hr"))
    errors = []
    if state not in (None, DRAFT) and not is_hr and changed & set(STATEMENT_FIELDS):
        errors.append("Once raised, only HR change the grievance as it was raised.")
    if "custom_assigned_hod" in changed and state == UNDER_REVIEW:
        errors += handler_errors(facts) if is_hr else ["Only HR hand a grievance to another handler."]
    if "custom_appeals_authority" in changed and state == APPEALED:
        errors += authority_errors(facts) if is_hr else ["Only HR change who hears the appeal."]
    if "custom_due_on" in changed and not is_hr:
        errors.append("Only HR move the date a grievance is due.")
    return errors


def step_changes(old_state, new_state, facts, day, due):
    """What a step writes on the grievance: the clock started (`due`, the
    day it is due back), the resolver, the employee's answer. The remarks
    stay for whoever has it next after a Return or a Reopen, and are
    cleared by any other step."""
    if old_state == new_state or not new_state:
        return {}
    changes = {} if (old_state, new_state) in ((UNDER_REVIEW, OPEN), (RESOLVED, UNDER_REVIEW)) \
        else {"custom_return_remarks": None}
    if new_state == UNDER_REVIEW:
        changes.update({"custom_booked_on": day, "custom_due_on": due, "custom_escalation": ""})
        if old_state == OPEN:
            changes["custom_reported_to"] = facts.get("user")
        if old_state == RESOLVED:
            changes.update({"resolved_by": None, "resolution_date": None})
    elif new_state == OPEN and old_state == UNDER_REVIEW:
        changes.update({"custom_booked_on": None, "custom_due_on": None, "custom_escalation": ""})
    elif new_state == RESOLVED:
        # the due date and how far it was escalated stay, the record of
        # whether it was resolved in time
        changes.update({"resolved_by": facts.get("user"), "resolution_date": day})
    elif new_state == CLOSED:
        changes["custom_outcome_accepted"] = 1
    elif new_state == APPEALED:
        changes.update({"custom_appeal_filed": 1, "custom_appealed_on": day, "custom_due_on": due,
                        "custom_escalation": ""})
    return changes


def stage_of(docstatus, status, handler=None, appealed=False):
    """The stage a grievance raised before this workflow stands at
    (patches/v1_0/grievances_on_workflow.py): a draft is Resolved where
    it is resolved, Under Review where a handler has it, else Open for HR
    to route; a filed one Invalid, Appeal Decided where it was appealed,
    else Closed."""
    if docstatus == 2:
        return CANCELLED
    if docstatus == 1:
        if status == "Invalid":
            return INVALID
        return APPEAL_DECIDED if appealed else CLOSED
    if status == "Resolved":
        return RESOLVED
    if status in ("Invalid", "Cancelled"):
        return OPEN
    return UNDER_REVIEW if handler else OPEN


def delete_errors(state, roles):
    """A draft its writer may delete, as Frappe HR lets them; once raised,
    a grievance is a record, deleted by the HR Manager alone."""
    if state in (None, DRAFT, CANCELLED) or set(roles or ()) & set(DELETERS):
        return []
    return ["A raised grievance is kept on the record: only the HR Manager deletes one."]


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
    """The words in a value, a Text Editor's markup taken off: an editor
    left empty still holds a paragraph."""
    if value is None:
        return ""
    text = re.sub(r"<[^>]*>", " ", str(value)).replace("&nbsp;", " ")
    return text.strip()
