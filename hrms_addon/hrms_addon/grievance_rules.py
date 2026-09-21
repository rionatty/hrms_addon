# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Non-disciplinary concerns (5.4) and safety incidents.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_discipline.py exercises them without a bench.

The non-disciplinary chart is short and the whole of it is the timeline:

  1-2  the employee identifies a concern and reports it to the HR Officer
  3    the HR Officer raises it and assigns a suitable HOD, who is told
  4    the HOD books it and reviews it
  5    the system watches the timeline and tells the HOD when it is due
       Resolved?  No  -> back to the HOD to review again
                  Yes -> 6. the HR Officer updates and closes it

The test script adds the appeal: the employee accepts the outcome or
appeals it, and an appeal is heard by someone not already involved, the
same rule the disciplinary process follows.

The safety chart ends in two places this module has to name: a sick leave
for the day off, and a separation on medical grounds where the sickness
outlasts it.
"""

import datetime

SICK_LEAVE = "Sick Leave"

# how long a concern has before the HOD is chased, unless its Grievance
# Type says otherwise
DEFAULT_TIMELINE_DAYS = 14

OPEN, UNDER_REVIEW, RESOLVED, CLOSED, APPEALED, INVALID = (
    "Open", "Investigated", "Resolved", "Closed", "Appealed", "Invalid")

# the ladder and the misconduct the HR manual lists, seeded so HR can
# amend them rather than wait for a developer
ACTION_TYPES = (
    ("Verbal Warning", "Verbal Warning", 6, 0),
    ("First Warning Letter", "First Warning Letter", 12, 0),
    ("Second Warning Letter", "Second Warning Letter", 12, 0),
    ("Final Warning Letter", "Second Warning Letter", 12, 0),
    ("Suspension Without Pay", "Suspension", 24, 3),
    ("Summary Dismissal", "Dismissal", 0, 0),
)
MISCONDUCT = (
    ("Late Coming", "Minor"),
    ("Absence Without Leave", "Serious"),
    ("Desertion", "Gross"),
    ("Insubordination", "Serious"),
    ("Negligence of Duty", "Serious"),
    ("Breach of Safety Rules", "Serious"),
    ("Theft", "Gross"),
    ("Assault or Fighting", "Gross"),
    ("Being Under the Influence", "Gross"),
    ("Falsification of Records", "Gross"),
    ("Poor Workmanship", "Minor"),
)

# where a safety incident stands
DRAFT, RECORDED, ON_SICK_LEAVE, BACK, SEPARATED, CANCELLED = (
    "Draft", "Recorded", "On Sick Leave", "Back at Work", "Separated", "Cancelled")


# ── the concern ───────────────────────────────────────────────────────
def due_on(raised, days=DEFAULT_TIMELINE_DAYS):
    raised = _date(raised)
    if not raised:
        return None
    return raised + datetime.timedelta(days=int(days or DEFAULT_TIMELINE_DAYS))


def overdue(due, today, status=None):
    if status in (RESOLVED, CLOSED, INVALID):
        return False
    due, today = _date(due), _date(today)
    return bool(due and today and today > due)


def days_left(due, today):
    due, today = _date(due), _date(today)
    if not due or not today:
        return None
    return (due - today).days


def concern_errors(facts):
    """Problems with a non-disciplinary concern, as user-facing messages."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say whose concern it is.")
    if not facts.get("grievance_type"):
        errors.append("Say what kind of concern it is (Grievance Type).")
    if not _text(facts.get("description")):
        errors.append("Write the concern in the employee's own words.")
    if not facts.get("assigned_hod"):
        errors.append("Step 3: assign a suitable Head of Department, who is told and books it.")
    status = facts.get("status")
    if status in (RESOLVED, CLOSED) and not _text(facts.get("resolution")):
        errors.append("Say how the concern was resolved before closing it.")
    if facts.get("appeal_filed"):
        authority = facts.get("appeals_authority")
        if not authority:
            errors.append("Name who hears the appeal.")
        elif authority == facts.get("handler"):
            errors.append("An appeal is heard by someone who has not already handled the concern.")
    return errors


def escalate_to(due, today, chain=("Handler", "Department Head", "HR")):
    """One level up the chain as the timeline runs out: the handler while
    it is in hand, the department head once it is due, HR once it is
    past."""
    left = days_left(due, today)
    if left is None:
        return chain[0]
    if left > 0:
        return chain[0]
    if left == 0:
        return chain[1]
    return chain[2]


# ── the safety incident ───────────────────────────────────────────────
def incident_errors(facts):
    """Problems with a safety incident, as user-facing messages."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say who the accident happened to.")
    if not facts.get("incident_on"):
        errors.append("Say when it happened.")
    if not _text(facts.get("nature")):
        errors.append("Write what happened; the EHS Officer's report is the record of it.")
    if not facts.get("manageable") and not _text(facts.get("hospital")):
        errors.append("The employee was taken to hospital: say which one.")
    if facts.get("day_off_required"):
        if not facts.get("sick_from"):
            errors.append("Say when the sick leave starts.")
        if not int(facts.get("sick_days") or 0):
            errors.append("Say how many days of sick leave the doctor gave.")
    if facts.get("compensation_required") and not _num(facts.get("compensation_amount")):
        errors.append("Say how much compensation is being followed up.")
    return errors


def incident_status(docstatus, day_off, sick_leave, persists, separation):
    """Where the incident stands, from what has followed it."""
    if docstatus == 2:
        return CANCELLED
    if docstatus == 0:
        return DRAFT
    if separation or persists:
        return SEPARATED if separation else ON_SICK_LEAVE
    if day_off and sick_leave:
        return ON_SICK_LEAVE
    return RECORDED if day_off else BACK


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.date(*(int(part) for part in text.split("-")))
    except (ValueError, TypeError):
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip()
