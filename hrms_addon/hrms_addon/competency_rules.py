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
