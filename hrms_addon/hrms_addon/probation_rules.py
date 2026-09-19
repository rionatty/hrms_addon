# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""End of probation evaluation / confirmation form (LPL/HR/32) rules.

No Frappe import, like the other *_rules.py modules, so scripts/verify_probation.py
exercises them without a bench.

The form: the employee rates every ratable factor (Section A) and the
probation objectives / KPIs (Section B) first, then the supervisor rates
them too and the supervisor's rating counts. Section A weighs 60, Section B
40, and the total places the employee in a band. A factor that does not fit
the job is rated N/A and left out.

Rating scale: Excellent=5 (90-100%), Very Good=4 (75-89%), Good=3 (60-74%),
Average=2 (50-59%), Below average=1 (49% and below).
"""

import datetime

# Section A, in the form's order (seeded as the Probation Factor list)
FACTORS = (
    "Job performance, work output, quality of work",
    "Job knowledge level so far learnt, following SOPs etc",
    "Initiative, creativity, new things, changes brought by the new staff",
    "Attendance and time management",
    "Effective communication and giving feedback",
    "Problem / conflict solving / resolution",
    "Teamwork / inter-personal relations",
    "Managing people / supervising subordinates",
    "Attitude, dependability, flexibility, engagement / passion, admitting mistakes",
    "Capacity to learn, be trained, implement skills learnt",
    "General discipline / conduct",
    "Participation in housekeeping / hygiene practices",
    "Participates in cost cutting measures",
)
# seeded once as the Probation Factor list (pick_lists.py), then HR's
PROBATION_MASTERS = {"Probation Factor": ("factor_name", FACTORS)}
NOT_APPLICABLE = "N/A"
RATINGS = ("1", "2", "3", "4", "5", NOT_APPLICABLE)
TOP_RATING = 5
FACTORS_WEIGHT, OBJECTIVES_WEIGHT = 60, 40
# (lowest total %, band), highest first: the form's Section C
BANDS = ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average"))
# The form lists up to eight probation objectives / KPIs
MAX_OBJECTIVES = 8

CONFIRM, EXTEND, TERMINATE = "Confirm", "Extend Probation", "Terminate"
DECISIONS = (CONFIRM, EXTEND, TERMINATE)

# The Employee's probation status (custom_probation_status)
ON_PROBATION, EXTENDED, CONFIRMED, NOT_CONFIRMED = "On Probation", "Extended", "Confirmed", "Not Confirmed"
PROBATION_STATUSES = (ON_PROBATION, EXTENDED, CONFIRMED, NOT_CONFIRMED)
STATUS_AFTER = {CONFIRM: CONFIRMED, EXTEND: EXTENDED, TERMINATE: NOT_CONFIRMED}


def section_percent(ratings):
    """The percentage a section's ratings give, N/A and blanks left out;
    None when nothing in it is rated."""
    scores = [int(r) for r in ratings if r not in (None, "", NOT_APPLICABLE)]
    if not scores:
        return None
    return 100.0 * sum(scores) / (TOP_RATING * len(scores))


def scores(factor_ratings, objective_ratings):
    """Section C from the supervisor's ratings: {"factors": out of 60,
    "objectives": out of 40, "total": percent}. A section with nothing rated
    scores None and the total is taken over the other alone."""
    factors, objectives = section_percent(factor_ratings), section_percent(objective_ratings)
    rated = [(pct, weight) for pct, weight in ((factors, FACTORS_WEIGHT), (objectives, OBJECTIVES_WEIGHT)) if pct is not None]
    total = round(sum(pct * weight for pct, weight in rated) / sum(weight for _, weight in rated), 1) if rated else None
    return {
        "factors": round(factors * FACTORS_WEIGHT / 100, 1) if factors is not None else None,
        "objectives": round(objectives * OBJECTIVES_WEIGHT / 100, 1) if objectives is not None else None,
        "total": total,
    }


def band(total):
    """The overall rating of a total percentage (None: not rated yet)."""
    if total is None:
        return None
    return next(name for floor, name in BANDS if total >= floor)


def passed(total, pass_mark):
    return total is not None and total >= pass_mark


def add_months(day, months):
    """`day` plus whole calendar months, the day of month kept where the
    month has it (31 January + 1 month = 28 or 29 February)."""
    day = _date(day)
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last = (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(day.day, last))


def probation_end(date_of_joining, months):
    """End of probation: the joining date plus the probation period."""
    return add_months(date_of_joining, months)


def objectives_from_kras(kras, limit=MAX_OBJECTIVES):
    """Probation objectives / KPIs taken from the Job Title's Key Result
    Areas (the form: in line with the departmental objectives), each once,
    at most `limit`."""
    objectives = []
    for text in kras:
        text = " ".join(str(text or "").split())
        if text and text not in objectives:
            objectives.append(text)
    return objectives[:limit]


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
