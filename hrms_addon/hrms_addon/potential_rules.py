# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Potential, rated criterion by criterion and rater by rater (the talent
blueprint, section 3: "Potential Assessment ... Nine Box Placement", and
section 2: "Read competency levels and learning agility").

No Frappe import (scripts/verify_talent_potential.py); potential.py reads
and writes the site.

  Potential Criterion   what potential is judged on: a name, a weight and a
                        descriptor for each level, 1 to 5, and where its
                        evidence comes from (the employee's competency
                        levels or how fast they rise, or the appraisal's
                        competencies)
  Potential Assessment  one rater's view of one placement: a Potential
                        Rating row per criterion, 1 to 5, with the evidence
                        and where the score came from
  the placement         the weighted mean of each rater, averaged over the
                        raters, out of a hundred (a 3 is 60, a 4 is 80, the
                        lines of the potential bands); flagged where the
                        raters are further apart than Talent Settings allow
"""

import datetime

LOW, HIGH = 1.0, 5.0
TO_HUNDRED = 20.0
MANUAL, COMPETENCY, APPRAISAL = "Manual", "Competency Assessment", "Appraisal"
SOURCES = (MANUAL, COMPETENCY, APPRAISAL)
# where a criterion's evidence is read from
LEVELS, GROWTH, APPRAISAL_COMPETENCIES = "Competency Levels", "Competency Growth", "Appraisal Competencies"
EVIDENCE_FROM = (LEVELS, GROWTH, APPRAISAL_COMPETENCIES)
RATER_ROLES = ("Line Manager", "Head of Department", "HR", "Talent Council", "Peer")
DEFAULT_SPREAD = 1.0
GROWTH_DAYS = 365

# the criteria the module starts with; each HR's to change
SEED = (
    {"criterion": "Ability", "weight": 1, "evidence_from": LEVELS, "levels": (
        "Struggles with what the current role asks",
        "Manages parts of the role with help",
        "Fully able in the current role",
        "Handles work above the current role",
        "Ready for work two levels up")},
    {"criterion": "Aspiration", "weight": 1, "evidence_from": None, "levels": (
        "Shows no wish to grow",
        "Open to growth when asked",
        "Wants to grow within the role",
        "Seeks a bigger role and prepares for it",
        "Drives own growth towards leadership")},
    {"criterion": "Engagement", "weight": 1, "evidence_from": None, "levels": (
        "Does the minimum",
        "Engaged at times",
        "Committed to the team and the plant",
        "Committed, and lifts others",
        "Champions the company and its goals")},
    {"criterion": "Learning Agility", "weight": 1, "evidence_from": GROWTH, "levels": (
        "Repeats the same approach whatever happens",
        "Learns slowly from experience",
        "Learns from experience and applies it",
        "Learns fast in new situations",
        "Turns new lessons into results quickly")},
)


# ── The criteria ──────────────────────────────────────────────────────
def criterion_errors(facts):
    """facts: "weight", "levels": [{"level", "descriptor"}]."""
    errors = []
    if _number(facts.get("weight")) < 0:
        errors.append("A weight is 0 or more.")
    seen = []
    for row in facts.get("levels") or []:
        level = int(_number(row.get("level")))
        if not 1 <= level <= 5:
            errors.append("Levels run from 1 to 5.")
        elif level in seen:
            errors.append("Level %d is described twice." % level)
        seen.append(level)
    if facts.get("evidence_from") and facts["evidence_from"] not in EVIDENCE_FROM:
        errors.append("Evidence comes from %s." % ", ".join(EVIDENCE_FROM))
    return errors


def weights_of(criteria):
    """{criterion: weight} of the active criteria weighing more than nought."""
    return {row.get("name"): _number(row.get("weight")) for row in criteria or ()
            if row.get("name") and int(_number(1 if row.get("active") is None else row.get("active")))
            and _number(row.get("weight")) > 0}


# ── One rater's assessment ────────────────────────────────────────────
def assessment_errors(facts, criteria):
    """facts: "placement", "rater", "rater_role", "ratings": [{"criterion",
    "score"}]; criteria: {criterion: weight} of the active ones, each to be
    rated once, 1 to 5."""
    errors = []
    if not facts.get("placement"):
        errors.append("Say whose placement this assessment is for.")
    if not facts.get("rater"):
        errors.append("An assessment is somebody's: say who rates.")
    if facts.get("rater_role") and facts["rater_role"] not in RATER_ROLES:
        errors.append("The rater is one of: %s." % ", ".join(RATER_ROLES))
    seen = set()
    for row in facts.get("ratings") or []:
        name = row.get("criterion")
        if not name:
            errors.append("A rating names its criterion.")
            continue
        if name in seen:
            errors.append("%s is rated twice." % name)
        seen.add(name)
        if row.get("score") in (None, "") or not LOW <= _number(row.get("score")) <= HIGH:
            errors.append("%s is rated 1 to 5." % name)
    missing = [name for name in criteria or {} if name not in seen]
    if missing:
        errors.append("Rate %s as well." % _and(sorted(missing)))
    return errors


def weighted_mean(ratings, weights, places=2):
    """One rater's 1 to 5: the scores weighed as their criteria say. A
    criterion no longer weighed (or never kept) counts once, so an old
    assessment still reads. places=None keeps every decimal, for the score
    out of a hundred."""
    given = [(_number(row.get("score")), weights.get(row.get("criterion"), 1.0) if weights else 1.0)
             for row in ratings or [] if row.get("score") not in (None, "") and _number(row.get("score")) > 0]
    total = sum(weight for _score, weight in given)
    if not given or not total:
        return None
    mean = sum(score * weight for score, weight in given) / total
    return mean if places is None else round(mean, places)


def placement_potential(assessments, weights, spread_allowed=None):
    """The placement's potential from the raters' submitted assessments.

    assessments: [{"rater", "ratings": [{"criterion", "score"}]}]. Returns
    {"score" (out of 100), "mean" (1 to 5), "raters", "spread", "disagree",
    "criteria": [{"criterion", "weight", "average", "lowest", "highest",
    "raters"}]}, or a blank result where nobody has rated."""
    means = []
    by_criterion = {}
    for assessment in assessments or []:
        mean = weighted_mean(assessment.get("ratings"), weights, places=None)
        if mean is None:
            continue
        means.append(mean)
        for row in assessment.get("ratings") or []:
            if row.get("score") in (None, ""):
                continue
            by_criterion.setdefault(row.get("criterion"), []).append(_number(row.get("score")))
    if not means:
        return {"score": None, "mean": None, "raters": 0, "spread": None, "disagree": 0, "criteria": []}
    exact = sum(means) / len(means)
    mean = round(exact, 2)
    spread = round(max(means) - min(means), 2)
    allowed = _number(spread_allowed) if spread_allowed not in (None, "") and _number(spread_allowed) > 0 \
        else DEFAULT_SPREAD
    order = list(weights or {}) + sorted(name for name in by_criterion if name not in (weights or {}))
    return {"score": round(exact * TO_HUNDRED, 2), "mean": mean, "raters": len(means), "spread": spread,
            "disagree": 1 if len(means) > 1 and spread > allowed else 0,
            "criteria": [{"criterion": name, "weight": (weights or {}).get(name, 0.0),
                          "average": round(sum(scores) / len(scores), 2), "lowest": min(scores),
                          "highest": max(scores), "raters": len(scores)}
                         for name in order for scores in [by_criterion.get(name)] if scores]}


def one_per_rater(existing, rater):
    """Whether a rater already has a live assessment of the placement."""
    return rater in set(existing or ())


# ── The evidence, and the score it suggests ───────────────────────────
def from_levels(levels):
    """The employee's competency levels in L&D (1 to 5, the latest of each
    skill) as a suggested score: their average."""
    given = [_number(level) for level in levels or [] if _number(level) > 0]
    return round(sum(given) / len(given), 1) if given else None


def from_appraisal(levels_out_of_ten):
    """The appraisal's competency evidence (out of ten) on the 1 to 5 scale."""
    given = [_number(level) for level in levels_out_of_ten or [] if _number(level) > 0]
    if not given:
        return None
    return round(max(LOW, min(HIGH, sum(given) / len(given) / 2.0)), 1)


def levels_gained(history, today, days=GROWTH_DAYS):
    """How many skill levels the employee rose in the last year: for each
    skill assessed more than once in it, the latest level less the first.
    history: [{"skill", "level", "assessed_on"}]. None with nothing to compare."""
    start = _day(today) - datetime.timedelta(days=days) if _day(today) else None
    by_skill = {}
    for row in sorted(history or [], key=lambda row: str(row.get("assessed_on") or "")):
        when = _day(row.get("assessed_on"))
        if not when or (start and when < start) or _number(row.get("level")) <= 0:
            continue
        by_skill.setdefault(row.get("skill"), []).append(_number(row.get("level")))
    compared = [levels for levels in by_skill.values() if len(levels) > 1]
    if not compared:
        return None
    return int(sum(max(0.0, levels[-1] - levels[0]) for levels in compared))


def from_growth(gained):
    """Levels gained in a year as a suggested learning agility score."""
    if gained is None:
        return None
    if gained >= 4:
        return 5.0
    if gained >= 2:
        return 4.0
    return 3.0 if gained == 1 else 2.0


def suggestion(evidence_from, levels=None, appraisal=None, history=None, today=None):
    """(score, source, evidence) a criterion's evidence suggests, or
    (None, Manual, None) where there is none to read. Competency levels fall
    back on the appraisal's competencies for somebody L&D has not assessed."""
    if evidence_from == LEVELS:
        score = from_levels([row.get("level") for row in levels or []])
        if score is not None:
            named = ", ".join("%s %s" % (row.get("skill"), int(_number(row.get("level"))))
                              for row in (levels or [])[:8])
            return score, COMPETENCY, "Competency levels: %s" % named
        evidence_from = APPRAISAL_COMPETENCIES
    if evidence_from == GROWTH:
        gained = levels_gained(history, today)
        score = from_growth(gained)
        if score is not None:
            return score, COMPETENCY, "%d skill level(s) gained in the last year" % gained
        return None, MANUAL, None
    if evidence_from == APPRAISAL_COMPETENCIES:
        score = from_appraisal([row.get("level") for row in appraisal or []])
        if score is not None:
            named = ", ".join("%s %s" % (row.get("competency"), _number(row.get("level")))
                              for row in (appraisal or [])[:6])
            return score, APPRAISAL, "Appraisal competencies out of 10: %s" % named
    return None, MANUAL, None


def source_after_edit(score, suggested, source):
    """A score the rater changed from what the evidence suggested is the
    rater's own."""
    if suggested in (None, "") or score in (None, ""):
        return source or MANUAL
    return source if abs(_number(score) - _number(suggested)) < 0.05 else MANUAL


# ── Moving the old potential across ───────────────────────────────────
OLD = (("ability", "Ability"), ("aspiration", "Aspiration"), ("engagement", "Engagement"))


def from_old(values):
    """Ability, aspiration and engagement out of ten, as 1 to 5 ratings: the
    potential they make out of a hundred is the same as before."""
    out = []
    for field, criterion in OLD:
        value = values.get(field)
        if value in (None, "") or _number(value) <= 0:
            continue
        out.append({"criterion": criterion, "score": round(max(LOW, min(HIGH, _number(value) / 2.0)), 2),
                    "source": MANUAL})
    return out


# ── Small helpers ─────────────────────────────────────────────────────
def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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


def _and(items):
    items = [str(item) for item in items]
    if len(items) == 1:
        return items[0]
    return "%s and %s" % (", ".join(items[:-1]), items[-1])
