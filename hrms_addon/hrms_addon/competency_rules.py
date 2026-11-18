# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 4, capability: the rules, without a Frappe import
(scripts/verify_competency.py). competency.py reads and writes the site.

The blueprint's section 4.8 and the plant's Skills Matrix (HR Manufacturing
Excellence workbook v3.2), 17 Nov 2026, on Frappe HR's own Skill master:

  Skill                  gains a type, a plant and section, whether it is
                         critical, the level it needs (4, competent on one's
                         own, unless set), how often it is reassessed and the
                         certificate it needs, if any. A job title may need a
                         different level (Designation Skill)
  Competency Assessment  an employee's level in a skill, 1 to 5, by whom and
                         when. The latest is the one that counts; it is
                         Competent at or above the level needed, with a valid
                         certificate where one is needed and while it is not
                         due again; else Gap, Certificate Needed or
                         Reassessment Due
  cover                  each skill's competent people: none is No Cover, one a
                         Single Point of Failure, fewer than the people needed
                         per shift times the shifts is Thin
"""

import datetime

LEVELS = (("1 Awareness", 1), ("2 Basic Understanding", 2), ("3 Works Under Supervision", 3),
          ("4 Competent Independently", 4), ("5 Can Train and Supervise", 5))
LEVEL_NAMES = tuple(name for name, _value in LEVELS)
LEVEL_VALUE = dict(LEVELS)
DEFAULT_REQUIRED = 4
DEFAULT_REASSESS_MONTHS = 12
SKILL_TYPES = ("Machine or Area", "Technical", "Safety", "Quality", "Behavioural", "Leadership")

COMPETENT, GAP, CERTIFICATE, REASSESS, SUPERSEDED = (
    "Competent", "Gap", "Certificate Needed", "Reassessment Due", "Superseded")
STATUSES = (COMPETENT, GAP, CERTIFICATE, REASSESS, SUPERSEDED)
NO_COVER, SINGLE, THIN, OK, NOT_ASSESSED = "No Cover", "Single Point of Failure", "Thin", "OK", "Not Assessed"
COVERS = (NO_COVER, SINGLE, THIN, OK, NOT_ASSESSED)
DEFAULTS = {"cover_per_shift": 2, "cover_shifts": 2}


def level_of(name):
    """A level's number from its name (or the number itself)."""
    if name in LEVEL_VALUE:
        return LEVEL_VALUE[name]
    try:
        value = int(str(name or "").split(" ")[0])
    except ValueError:
        return None
    return value if 1 <= value <= 5 else None


def level_name(value):
    value = level_of(value)
    return LEVEL_NAMES[value - 1] if value else None


def required_level(skill, role_levels=None, designation=None):
    """The level a skill needs of someone: their job title's, else the
    skill's own, else 4."""
    role = (role_levels or {}).get(designation)
    return level_of(role) or level_of(skill.get("custom_required_level")) or DEFAULT_REQUIRED


def next_due(assessed_on, months):
    assessed_on = _date(assessed_on)
    if not assessed_on:
        return None
    months = int(_num(months)) or DEFAULT_REASSESS_MONTHS
    return add_months(assessed_on, months)


def status_of(level, required, due, today, needs_certificate=False, has_certificate=True):
    """Where an employee stands in a skill, the most pressing first: a
    certificate missing, then a reassessment overdue, then below the level."""
    today, due = _date(today), _date(due)
    if needs_certificate and not has_certificate:
        return CERTIFICATE
    if due and today and today > due:
        return REASSESS
    return COMPETENT if (level_of(level) or 0) >= required else GAP


def current(assessments):
    """The assessment that counts for each (employee, skill): the latest by
    date, then the one made last. Returns {(employee, skill): assessment}."""
    found = {}
    for row in assessments or ():
        key = (row.get("employee"), row.get("skill"))
        mark = (str(_date(row.get("assessed_on")) or ""), str(row.get("creation") or ""), str(row.get("name") or ""))
        if key not in found or mark > found[key][0]:
            found[key] = (mark, row)
    return {key: row for key, (_mark, row) in found.items()}


def cover(competent, s=None):
    """A skill's cover from how many people are competent in it."""
    s = s or DEFAULTS
    if competent is None:
        return NOT_ASSESSED
    if competent == 0:
        return NO_COVER
    if competent == 1:
        return SINGLE
    if competent < int(s["cover_per_shift"]) * int(s["cover_shifts"]):
        return THIN
    return OK


def coverage(rows):
    """(at the level needed, assessed) over current assessments: the share the
    HR Excellence scorecard reads."""
    rows = [row for row in rows or () if row.get("status") != SUPERSEDED]
    return sum(1 for row in rows if row.get("status") == COMPETENT), len(rows)


def score_of(rows):
    """An employee's competency score, out of 100: each skill assessed, its
    level against the level it needs (at most all of it), averaged. None
    while nothing is assessed."""
    rows = [row for row in rows or () if row.get("status") != SUPERSEDED and level_of(row.get("level"))]
    if not rows:
        return None
    parts = [min(1.0, level_of(row.get("level")) / float(level_of(row.get("required_level")) or DEFAULT_REQUIRED))
             for row in rows]
    return round(100.0 * sum(parts) / len(parts), 1)


def assessment_errors(row, today):
    errors = []
    if not level_of(row.get("level")):
        errors.append("Pick a level from 1 to 5.")
    assessed_on = _date(row.get("assessed_on"))
    if assessed_on and _date(today) and assessed_on > _date(today):
        errors.append("An assessment cannot be dated ahead.")
    if row.get("assessed_by") and row.get("assessed_by") == row.get("employee"):
        errors.append("Nobody assesses themselves.")
    return errors


def add_months(day, months):
    day = _date(day)
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    following = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return datetime.date(year, month, min(day.day, (following - datetime.timedelta(days=1)).day))


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ── One framework (18 Nov 2026) ───────────────────────────────────────
# the brief's competency categories; a skill's older type maps to one
CATEGORIES = ("Core", "Functional", "Technical", "Safety", "Leadership", "Behavioural")
TYPE_CATEGORY = {"Machine or Area": "Technical", "Technical": "Technical", "Safety": "Safety",
                 "Quality": "Functional", "Behavioural": "Behavioural", "Leadership": "Leadership"}
# what each level means where a skill says nothing of its own
DEFAULT_DESCRIPTORS = (
    (1, "Knows what the task is and why it matters; cannot do it yet."),
    (2, "Knows the steps and the safety rules; does parts of it with help."),
    (3, "Does the whole task with a skilled person checking."),
    (4, "Does the whole task alone, to standard, every shift."),
    (5, "Does it alone, sets it right when it goes wrong, and trains others."),
)


def profile_for(profiles, designation, work_section=None):
    """The role profile that applies: the job title's for the section, else
    the job title's for every section. profiles: [{"designation",
    "work_section", "skills": [{"skill", "required_level", "critical", "weight"}]}]."""
    exact = [row for row in profiles or () if row.get("designation") == designation
             and work_section and row.get("work_section") == work_section]
    general = [row for row in profiles or () if row.get("designation") == designation and not row.get("work_section")]
    return (exact or general or [None])[0]


def profile_level(profile, skill):
    """(required level, critical) a profile gives a skill, or (None, None)."""
    for row in (profile or {}).get("skills") or ():
        if row.get("skill") == skill:
            return level_of(row.get("required_level")), int(_num(row.get("critical"))) if row.get("critical") is not None \
                else None
    return None, None


def role_fit(assessments, profile):
    """How well someone fits a role's profile: {"fit" (out of 100, each skill
    its level against the level needed, weighed), "gaps": [(skill, needed,
    has)], "missing": [skill], "critical_gaps": [skill]}. assessments:
    {skill: level}."""
    rows = (profile or {}).get("skills") or ()
    if not rows:
        return {"fit": None, "gaps": [], "missing": [], "critical_gaps": []}
    total = parts = 0.0
    gaps, missing, critical = [], [], []
    for row in rows:
        needed = level_of(row.get("required_level")) or DEFAULT_REQUIRED
        weight = _num(row.get("weight")) or 1.0
        has = level_of((assessments or {}).get(row.get("skill")))
        total += weight
        parts += weight * min(1.0, (has or 0) / float(needed))
        if not has:
            missing.append(row.get("skill"))
        if (has or 0) < needed:
            gaps.append((row.get("skill"), needed, has or 0))
            if int(_num(row.get("critical"))):
                critical.append(row.get("skill"))
    return {"fit": round(100.0 * parts / total, 1) if total else None, "gaps": gaps, "missing": missing,
            "critical_gaps": critical}


def shift_need(skill_need, default_need, crew):
    """The competent people a skill needs on each shift: the skill's own
    number, else the settings'; never more than the section's crew."""
    need = int(_num(skill_need)) or int(_num(default_need)) or 1
    return min(need, int(_num(crew))) if int(_num(crew)) else need


def shift_cover(by_shift, need, shifts):
    """A skill's cover in a plant across its shifts: {"status", "short"}.
    by_shift: {shift: competent people}; shifts: the plant's shifts. No Cover
    where nobody holds it, a Single Point of Failure where one person does,
    Thin where a shift has fewer than needed, else OK."""
    total = sum(by_shift.values())
    if total == 0:
        return {"status": NO_COVER, "short": list(shifts or ())}
    if total == 1:
        return {"status": SINGLE, "short": [shift for shift in shifts or () if by_shift.get(shift, 0) < need]}
    short = [shift for shift in shifts or () if by_shift.get(shift, 0) < need]
    return {"status": THIN if short else OK, "short": short}


RISK = {NO_COVER: "red", SINGLE: "red", THIN: "amber", OK: "green", NOT_ASSESSED: "grey"}


def level_names_from(minimum):
    """The level names at or above a level, for a filter."""
    minimum = max(1, min(5, int(_num(minimum)) or 1))
    return list(LEVEL_NAMES[minimum - 1:])
