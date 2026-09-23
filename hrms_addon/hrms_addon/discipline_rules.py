# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Disciplinary grievances (5.3): the ladder, the hearing and the sanction.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_discipline.py exercises them without a bench.

The chart walks one rung at a time, and every rung is the same four steps:
an incident is reported, it is investigated and heard, and if it happened
something is issued and signed for.

  1-2  the supervisor reports it; the HR Officer investigates and hears it
       Did it happen?  No  -> the case closes
                       Yes -> Summary dismissal? Yes -> the termination
                              process (exits.py). No  -> a verbal warning
  4-7   it happens again: investigated, heard, a First Warning Letter
        issued, signed by the employee and the signed copy filed
  8-11  again: a Second Warning Letter, signed and filed
  12-14 again: suspension without pay, then a hearing where management
        decides
  15    Termination? Yes -> the termination process. No -> pardoned, and
        the behaviour watched

The test script adds what the chart leaves implicit: a misconduct has a
severity, an investigating officer is appointed and is never the person
who decides, a hearing is called at least 48 hours ahead, a sanction has
a life after which it is spent, and a fresh case inside a live sanction
starts one rung higher than the last.

LPL/HR/30 is the warning letter and LPL/HR/03 the hearing registration
form — the panel, their job titles and their signatures.
"""

import datetime

# ── the ladder, in the chart's own order ──────────────────────────────
VERBAL = "Verbal Warning"
FIRST_WARNING = "First Warning Letter"
SECOND_WARNING = "Second Warning Letter"
SUSPENSION = "Suspension"
DISMISSAL = "Dismissal"
LADDER = (VERBAL, FIRST_WARNING, SECOND_WARNING, SUSPENSION, DISMISSAL)

# how long each rung stands against an employee before it is spent
VALIDITY_MONTHS = {VERBAL: 6, FIRST_WARNING: 12, SECOND_WARNING: 12, SUSPENSION: 24, DISMISSAL: 0}

MINOR, SERIOUS, GROSS = "Minor", "Serious", "Gross"
SEVERITIES = (MINOR, SERIOUS, GROSS)
# only gross misconduct may be dismissed on the first offence, which is
# the chart's "Summary Dismissal?" at the foot of the first hearing
SUMMARY_DISMISSAL_SEVERITY = GROSS

# the states a case passes
DRAFT, INVESTIGATING, CHARGED, HEARING, DECIDED, CLOSED, CANCELLED = (
    "Draft", "Under Investigation", "Charge Issued", "Hearing Scheduled", "Decided", "Closed",
    "Cancelled")

# what the investigation can say
CASE_TO_ANSWER, NO_CASE = "Case to answer", "No case"
RECOMMENDATIONS = (CASE_TO_ANSWER, NO_CASE)

# what the panel can decide
SANCTIONED, DISMISSED, PARDONED = "Sanctioned", "Dismissed", "Pardoned"
OUTCOMES = (SANCTIONED, DISMISSED, PARDONED)

# a hearing is called at least this far ahead, and an appeal may be filed
# for this long after the decision
HEARING_NOTICE_HOURS = 48
APPEAL_WINDOW_DAYS = 14
# the suspension the chart draws
DEFAULT_SUSPENSION_DAYS = 3


def rung_of(action):
    return LADDER.index(action) if action in LADDER else -1


def next_rung(current):
    """One step up the ladder. Dismissal is the top; there is nothing above
    it."""
    at = rung_of(current)
    if at < 0:
        return LADDER[0]
    return LADDER[min(at + 1, len(LADDER) - 1)]


def sanction_spent(issued_on, action, today, months=None):
    """A sanction stands for a while and is then spent: after that a fresh
    case starts at the bottom of the ladder again."""
    issued, today = _date(issued_on), _date(today)
    if not issued or not today:
        return True
    life = VALIDITY_MONTHS.get(action, 0) if months is None else int(months)
    if not life:
        return True
    return today > add_months(issued, life)


def escalate(live_sanctions, severity, today):
    """Where a fresh case starts.

    live_sanctions: rows of "action", "issued_on", "validity_months".
    Gross misconduct goes straight to dismissal; otherwise the case starts
    one rung above the highest sanction still live, or at the bottom where
    none is.
    """
    if severity == SUMMARY_DISMISSAL_SEVERITY:
        return DISMISSAL
    live = [row for row in live_sanctions or []
            if not sanction_spent(row.get("issued_on"), row.get("action"), today,
                                  row.get("validity_months"))]
    if not live:
        return LADDER[0]
    highest = max(live, key=lambda row: rung_of(row.get("action")))
    return next_rung(highest.get("action"))


def case_errors(facts):
    """Problems with a case as it is opened, as user-facing messages."""
    errors = []
    if not facts.get("employee"):
        errors.append("Say who the case is against.")
    if not facts.get("misconduct_type"):
        errors.append("Say what the misconduct is (Misconduct Type).")
    if not facts.get("incident_date"):
        errors.append("Say when the incident happened.")
    elif facts.get("today") and _date(facts["incident_date"]) > _date(facts["today"]):
        errors.append("The incident cannot be in the future.")
    if not _text(facts.get("allegation")):
        errors.append("Write the allegation: what the employee is said to have done.")
    if not facts.get("reported_by"):
        errors.append("Say who reported it.")
    severity = facts.get("severity")
    if severity and severity not in SEVERITIES:
        errors.append("%r is not a severity: %s." % (severity, ", ".join(SEVERITIES)))
    return errors


def investigation_errors(facts):
    """The investigation the chart runs before every rung."""
    errors = []
    if not facts.get("investigating_officer"):
        errors.append("Appoint an investigating officer before the investigation starts.")
    if not _text(facts.get("investigation_report")):
        errors.append("Write the investigation report before the case goes further.")
    recommendation = facts.get("recommendation")
    if not recommendation:
        errors.append("The investigating officer recommends either %r or %r." % RECOMMENDATIONS)
    elif recommendation not in RECOMMENDATIONS:
        errors.append("%r is not a recommendation." % recommendation)
    return errors


def hearing_errors(facts):
    """A hearing is called in time, before a panel, by people who did not
    gather the evidence.

    facts: "hearing_on", "notified_on", "panel" (rows of member),
    "investigating_officer", "notice_hours".
    """
    errors = []
    hearing = _datetime(facts.get("hearing_on"))
    if not hearing:
        errors.append("Say when the hearing is.")
    else:
        told = _datetime(facts.get("notified_on"))
        hours = float(facts.get("notice_hours") or HEARING_NOTICE_HOURS)
        if told and (hearing - told).total_seconds() < hours * 3600:
            errors.append("A hearing is called at least %g hours ahead; this one gives %g."
                          % (hours, round((hearing - told).total_seconds() / 3600.0, 1)))
    panel = [row for row in facts.get("panel") or [] if row.get("member")]
    if not panel:
        errors.append("A hearing sits before a panel (LPL/HR/03): name who is on it.")
    officer = facts.get("investigating_officer")
    if officer and officer in {row.get("member") for row in panel}:
        errors.append("The person who gathered the evidence does not decide the case: "
                      "take the investigating officer off the panel.")
    return errors


def decision_errors(facts):
    """What the panel must record before the case is decided."""
    errors = []
    outcome = facts.get("outcome")
    if not outcome:
        errors.append("Say what the panel decided.")
    elif outcome not in OUTCOMES:
        errors.append("%r is not an outcome: %s." % (outcome, ", ".join(OUTCOMES)))
    if not _text(facts.get("hearing_minutes")):
        errors.append("Record the hearing: what was said and by whom.")
    if not _text(facts.get("employee_response")):
        errors.append("Record the employee's own response; they are heard before they are judged.")
    if outcome == SANCTIONED and not facts.get("action_type"):
        errors.append("Say which sanction was applied.")
    if facts.get("action_type") == SUSPENSION and not int(facts.get("suspension_days") or 0):
        errors.append("A suspension needs the number of days it runs for.")
    return errors


def appeal_errors(facts):
    """An appeal is heard by someone who has not touched the case."""
    errors = []
    authority = facts.get("appeals_authority")
    if not authority:
        errors.append("Name who hears the appeal.")
        return errors
    involved = {facts.get("investigating_officer"), facts.get("decided_by")}
    involved |= {row.get("member") for row in facts.get("panel") or []}
    if authority in {who for who in involved if who}:
        errors.append("The appeal is heard by someone who has not already acted in the case.")
    if not _text(facts.get("appeal_grounds")):
        errors.append("Say on what grounds the appeal is made.")
    return errors


def appeal_window_closed(decided_on, today, days=APPEAL_WINDOW_DAYS):
    """Whether the time to appeal has run out, so the case can close itself."""
    decided, today = _date(decided_on), _date(today)
    if not decided or not today:
        return False
    return (today - decided).days > int(days or APPEAL_WINDOW_DAYS)


def suspension_dates(start, days):
    """The suspension the letter prints: from, to, and the day they report
    back, both ends of the suspension counted."""
    start = _date(start)
    days = int(days or 0)
    if not start or days < 1:
        return {"from": start, "to": None, "report_back": None}
    end = start + datetime.timedelta(days=days - 1)
    return {"from": start, "to": end, "report_back": end + datetime.timedelta(days=1)}


def ends_in_termination(outcome, action):
    """The chart's "Termination?" — the two ways a case reaches the
    involuntary exit."""
    return outcome == DISMISSED or action == DISMISSAL


def add_months(day, months):
    day = _date(day)
    if not day:
        return None
    month = day.month - 1 + int(months)
    year = day.year + month // 12
    month = month % 12 + 1
    return datetime.date(year, month, min(day.day, _days_in_month(year, month)))


def _days_in_month(year, month):
    if month == 12:
        return 31
    return (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day


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


def _datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if not value:
        return None
    text = str(value).replace("T", " ")
    for shape in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(text[:len("2026-01-01 00:00:00")], shape)
        except ValueError:
            continue
    return None


def _text(value):
    return (value or "").strip()
