# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The graduate pipeline in depth (the talent blueprint, section 7): the
cohort each trainee joins and the 30, 60 and 90 day milestones it lays
down, the rotation supervisor's assessment at the end of each stint, the
mentor's sessions, and the funnel from recruited to confirmed.

No Frappe import (scripts/verify_graduates.py); graduates.py reads and
writes the site.
"""

import datetime

# the cohort's milestones unless HR keep others: (milestone, days after the
# trainee starts, the one that decides confirmation)
TEMPLATE = (("30-Day Review", 30, 0), ("60-Day Review", 60, 0), ("90-Day Review", 90, 1))
RECOMMENDATIONS = ("Continue Rotation", "Extend Rotation", "Ready for Placement", "Exit Programme")
CRITERIA = ("Technical learning", "Quality of work", "Initiative", "Teamwork", "Safety and discipline",
            "Attendance and punctuality")
STAGES = ("Recruited", "In Induction", "In Rotation", "Under Assessment", "Confirmed", "Exited")
MODES = ("In Person", "Online", "On the Job")
PROGRESS = ("On Track", "Some Concerns", "Off Track")
TO_HUNDRED = 20.0


# ── The cohort ────────────────────────────────────────────────────────
def template_errors(rows):
    """The cohort's milestones: each named, a day after the start, later
    than the one before, and one at most deciding confirmation."""
    errors = []
    days = []
    for row in rows or []:
        name = _text(row.get("milestone"))
        if not name:
            errors.append("A milestone needs a name.")
        day = int(_number(row.get("days_after_start")))
        if day <= 0:
            errors.append("%s falls a number of days after the start." % (name or "A milestone"))
        elif days and day <= days[-1]:
            errors.append("%s falls after the milestone before it." % (name or "A milestone"))
        days.append(day)
    if len([row for row in rows or [] if int(_number(row.get("final")))]) > 1:
        errors.append("Only one milestone decides confirmation.")
    return errors


def cohort_errors(facts):
    errors = template_errors(facts.get("milestones"))
    if facts.get("start_date") and facts.get("end_date") and str(facts["end_date"]) < str(facts["start_date"]):
        errors.append("A cohort cannot end before it starts.")
    return errors


def milestones_from(template, start):
    """The trainee's milestones from the cohort's template, each due its days
    after the trainee starts: [{"milestone", "due_on"}]."""
    begin = _day(start)
    if not begin:
        return []
    rows = template or [{"milestone": name, "days_after_start": days} for name, days, _final in TEMPLATE]
    return [{"milestone": _text(row.get("milestone")),
             "due_on": (begin + datetime.timedelta(days=int(_number(row.get("days_after_start"))))).isoformat()}
            for row in rows if _text(row.get("milestone")) and int(_number(row.get("days_after_start"))) > 0]


# ── The rotation supervisor's assessment ──────────────────────────────
def rotation_score(rows):
    """The criteria, 1 to 5 each, as a score out of a hundred."""
    given = [_number(row.get("score")) for row in rows or [] if _number(row.get("score")) > 0]
    return round(sum(given) / len(given) * TO_HUNDRED, 1) if given else None


def rotation_assessment_errors(facts):
    """facts: "trainee_program", "rotation" (the stint's row), "supervisor",
    "rotation_supervisor" (the stint's own), "criteria": [{"criterion",
    "score"}], "recommendation"."""
    errors = []
    if not facts.get("trainee_program"):
        errors.append("Say which trainee is assessed.")
    if not facts.get("rotation"):
        errors.append("Say which rotation is assessed.")
    if not facts.get("supervisor"):
        errors.append("The rotation supervisor assesses the stint.")
    elif facts.get("rotation_supervisor") and facts["supervisor"] != facts["rotation_supervisor"]:
        errors.append("The stint is assessed by its own rotation supervisor.")
    rows = facts.get("criteria") or []
    if not rows:
        errors.append("Score the trainee on the criteria.")
    for row in rows:
        if not 1 <= _number(row.get("score")) <= 5:
            errors.append("%s is scored 1 to 5." % (row.get("criterion") or "A criterion"))
    if facts.get("recommendation") not in RECOMMENDATIONS:
        errors.append("Recommend one of: %s." % ", ".join(RECOMMENDATIONS))
    return errors


def rotation_outcome(recommendation, strengths=None, development=None):
    """What the stint's row says of it, cut to 500 characters."""
    parts = [recommendation or ""]
    if _text(strengths):
        parts.append("Strengths: %s" % _text(strengths))
    if _text(development):
        parts.append("To develop: %s" % _text(development))
    return ". ".join(part for part in parts if part)[:500]


# ── The mentor's sessions ─────────────────────────────────────────────
def mentoring_errors(facts):
    """facts: "mentor", "mentee", "trainee_program", "talent_program",
    "session_date", "topics", "today"."""
    errors = []
    if not facts.get("mentor"):
        errors.append("Say who mentors.")
    if not (facts.get("trainee_program") or facts.get("talent_program")):
        errors.append("A session belongs to a graduate trainee or a development plan.")
    if facts.get("mentor") and facts.get("mentor") == facts.get("mentee"):
        errors.append("A mentor does not mentor themselves.")
    if not facts.get("session_date"):
        errors.append("Say when the session was held.")
    elif facts.get("today") and str(facts["session_date"])[:10] > str(facts["today"])[:10]:
        errors.append("A session is recorded once it is held.")
    if not _text(facts.get("topics")):
        errors.append("Say what was covered.")
    if facts.get("mode") and facts["mode"] not in MODES:
        errors.append("A session is %s." % ", ".join(MODES))
    return errors


def may_edit_session(user_employee, mentor, roles):
    """Only the mentor writes their sessions (System Manager aside)."""
    if "System Manager" in set(roles or ()):
        return True
    return bool(user_employee) and user_employee == mentor


# ── The funnel ────────────────────────────────────────────────────────
def funnel(rows):
    """Trainees by cohort and stage: [{"cohort", "total", "stages": {stage:
    n}, "confirmed_share", "exited_share"}], the latest cohort first.
    rows: [{"cohort", "stage", "n"}]."""
    found = {}
    for row in rows or []:
        cohort = row.get("cohort") or "No cohort"
        entry = found.setdefault(cohort, {stage: 0 for stage in STAGES})
        stage = row.get("stage") if row.get("stage") in STAGES else STAGES[0]
        entry[stage] += int(_number(row.get("n")))
    out = []
    for cohort, stages in found.items():
        total = sum(stages.values())
        out.append({"cohort": cohort, "total": total, "stages": stages,
                    "confirmed_share": _share(stages["Confirmed"], total),
                    "exited_share": _share(stages["Exited"], total)})
    return sorted(out, key=lambda row: str(row["cohort"]), reverse=True)


# ── Small helpers ─────────────────────────────────────────────────────
def _share(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "")[:10]
    try:
        return datetime.date(*(int(part) for part in text.split("-"))) if text else None
    except (TypeError, ValueError):
        return None
