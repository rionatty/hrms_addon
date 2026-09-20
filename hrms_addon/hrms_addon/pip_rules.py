# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance Improvement Plan: what happens to an employee who scores
below the pass mark.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_performance.py exercises them without a bench.

The recommendation Luuka made (the test script, 20 Sep 2026):

  "Introduce Performance Improvement Plans (PIPs) for employees scoring
   below 60. After the appraisal period, a PIP recommendation should be
   sent to the appraiser and HR; the managers are then notified and an
   agreement is made on how performance can be improved, guiding the
   employee and holding them accountable."

So a PIP is an agreement, not a punishment: each gap has a standard to
reach, the support the company will give, how it will be measured, and a
date it is looked at again. It runs for a period, is reviewed at least
once, and ends in a decision.
"""

import datetime

DEFAULT_MONTHS = 3
MIN_REVIEWS = 1

DRAFT, AGREED, IN_PROGRESS, CLOSED, CANCELLED = "Draft", "Agreed", "In Progress", "Closed", "Cancelled"
STATUSES = (DRAFT, AGREED, IN_PROGRESS, CLOSED, CANCELLED)

IMPROVED, NOT_IMPROVED, EXTENDED = "Improved", "Not Improved", "Extended"
OUTCOMES = (IMPROVED, NOT_IMPROVED, EXTENDED)

# how a review of one objective reads
MET, PARTLY, NOT_MET = "Met", "Partly Met", "Not Met"
PROGRESS = (MET, PARTLY, NOT_MET)
# the outcome a set of reviews suggests, before the managers decide
# "most" is a majority of what was looked at
MET_SHARE_FOR_IMPROVED = 0.5


def end_date(start, months=DEFAULT_MONTHS):
    """The day a plan of `months` starting on `start` runs to."""
    day = _date(start)
    index = day.month - 1 + int(months or DEFAULT_MONTHS)
    year, month = day.year + index // 12, index % 12 + 1
    last = (datetime.date(year + month // 12, month % 12 + 1, 1) - datetime.timedelta(days=1)).day
    return datetime.date(year, month, min(day.day, last)) - datetime.timedelta(days=1)


def plan_errors(facts):
    """Problems with a PIP as it is agreed.

    facts: "employee", "start_date", "end_date", "objectives"
    ([{"area", "expected_standard", "support", "measure", "review_date"}]),
    "supervisor".
    """
    errors = []
    if not facts.get("employee"):
        errors.append("Name the employee the plan is for.")
    if not facts.get("supervisor"):
        errors.append("Name the supervisor who will guide the employee through the plan.")
    start, end = facts.get("start_date"), facts.get("end_date")
    if not start:
        errors.append("Set the date the plan starts.")
    if not end:
        errors.append("Set the date the plan runs to.")
    if start and end and str(end) < str(start):
        errors.append("The plan cannot end (%s) before it starts (%s)." % (end, start))
    objectives = facts.get("objectives") or []
    if not objectives:
        errors.append("List what must improve: each area, the standard to reach, and how it will be measured.")
    for row in objectives:
        missing = [label for key, label in (("area", "area to improve"), ("expected_standard", "expected standard"),
                                            ("measure", "how it is measured"))
                   if not (row.get(key) or "").strip()]
        if missing:
            errors.append("Every line of the plan needs its %s: %s."
                          % (", ".join(missing), (row.get("area") or "?")))
            break
    for row in objectives:
        review = row.get("review_date")
        if review and start and str(review) < str(start):
            errors.append("A review date (%s) falls before the plan starts." % review)
            break
        if review and end and str(review) > str(end):
            errors.append("A review date (%s) falls after the plan ends." % review)
            break
    return errors


def close_errors(facts):
    """Problems with closing a PIP.

    facts: "reviews" ([{"reviewed_on", "progress"}]), "outcome", "remarks",
    "end_date", "today".
    """
    errors = []
    reviews = facts.get("reviews") or []
    if len(reviews) < MIN_REVIEWS:
        errors.append("Record at least one review meeting before closing the plan.")
    if facts.get("outcome") not in OUTCOMES:
        errors.append("Say how the plan ended: %s." % ", ".join(OUTCOMES))
    if not (facts.get("remarks") or "").strip():
        errors.append("Write what was agreed at the end of the plan.")
    if facts.get("outcome") == EXTENDED and not facts.get("new_end_date"):
        errors.append("Set the new end date the plan is extended to.")
    if facts.get("outcome") == EXTENDED and facts.get("new_end_date") and facts.get("end_date") \
            and str(facts["new_end_date"]) <= str(facts["end_date"]):
        errors.append("An extension must run past the plan's current end (%s)." % facts["end_date"])
    return errors


def suggested_outcome(reviews):
    """What the reviews suggest: Improved when most of what was looked at
    was met, otherwise Not Improved. None until something is reviewed."""
    marks = [row.get("progress") for row in reviews or [] if row.get("progress") in PROGRESS]
    if not marks:
        return None
    met = sum(1 for mark in marks if mark == MET)
    return IMPROVED if met / len(marks) > MET_SHARE_FOR_IMPROVED else NOT_IMPROVED


def due_reviews(rows, today):
    """The plan lines whose review date has come and that nobody has looked
    at yet."""
    day = _date(today)
    return [row for row in rows or []
            if row.get("review_date") and _date(row["review_date"]) <= day and not row.get("reviewed_on")]


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
