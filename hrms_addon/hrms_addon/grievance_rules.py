# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Non-disciplinary grievances (5.4) and safety incidents.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_grievances.py and scripts/verify_discipline.py exercise them
without a bench.

The grievance's stages and who takes each are in grievance_approval.py.
This is its timeline (the test sheet's Non Disciplinary cases 3 and 10):
once routed, a grievance is due back within its Grievance Type's days; as
the date nears it is at risk and goes one level up the chain, from the
handler to the head of the employee's department, and once it is past HR
are told as well. An appeal goes from who hears it straight to HR.

The safety chart ends in two places this module has to name: a sick leave
for the day off, and a separation on medical grounds where the sickness
outlasts it.
"""

import datetime

SICK_LEAVE = "Sick Leave"

# how long a grievance has once routed, unless its Grievance Type says
# otherwise, and how near its date it is at risk
DEFAULT_TIMELINE_DAYS = 14
AT_RISK_DAYS = 2

# the workflow states a grievance is in someone's hands against its date
# (grievance_approval.TIMED)
UNDER_REVIEW, APPEALED = "Under Review", "Appealed"
TIMED = (UNDER_REVIEW, APPEALED)

# how far up the chain it has gone; each level is told once
NOT_ESCALATED, AT_RISK, BREACHED = "", "At Risk", "Breached"
ESCALATIONS = (NOT_ESCALATED, AT_RISK, BREACHED)
HANDLER, DEPARTMENT_HEAD, HR = "handler", "department_head", "hr"

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


# ── the grievance ─────────────────────────────────────────────────────
def due_on(start, days=DEFAULT_TIMELINE_DAYS):
    start = _date(start)
    if not start:
        return None
    return start + datetime.timedelta(days=int(days or DEFAULT_TIMELINE_DAYS))


def days_left(due, today):
    due, today = _date(due), _date(today)
    if not due or not today:
        return None
    return (due - today).days


def overdue(due, today, state):
    """Past its date while it is still in someone's hands."""
    left = days_left(due, today)
    return state in TIMED and left is not None and left < 0


def escalation(due, today, state):
    """How far up the chain the timeline takes it: at risk within
    AT_RISK_DAYS of its date, breached once past it."""
    left = days_left(due, today)
    if state not in TIMED or left is None or left > AT_RISK_DAYS:
        return NOT_ESCALATED
    return AT_RISK if left >= 0 else BREACHED


def escalates(current, level):
    """Is `level` further up the chain than where it has been taken?"""
    def rank(value):
        return ESCALATIONS.index(value) if value in ESCALATIONS else 0
    return rank(level) > rank(current)


def told_at(level, appeal=False):
    """Who hears of it at each level: the handler, and one level up, the
    head of the employee's department while it is at risk, and HR once it
    is breached. An appeal goes from who hears it straight to HR."""
    if level == AT_RISK:
        return (HANDLER,) if appeal else (HANDLER, DEPARTMENT_HEAD)
    if level == BREACHED:
        return (HANDLER, HR) if appeal else (HANDLER, DEPARTMENT_HEAD, HR)
    return ()


def department_heads(holders, branch, department):
    """The heads of this department: the Head of Department role's holders
    whose User Permissions hold them to it, in this branch or in every
    branch. A head held to no department heads none in particular, so a
    grievance is never spread to every head on the site.

    holders: [{"user", "branches", "departments"}] (people.holders)."""
    if not department:
        return []
    return sorted(h["user"] for h in holders or ()
                  if department in h["departments"] and (not h["branches"] or branch in h["branches"]))


def appeal_authority(candidates, involved):
    """Who hears an appeal: the first of the candidates (the plant's General
    Manager, the HR Manager, the Executive Director) who has not already
    acted in the grievance (case 9)."""
    involved = {user for user in involved or () if user}
    for user in candidates or ():
        if user and user not in involved:
            return user
    return None


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
