# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview rules: Luuka's Candidate Interview Evaluation / Score Form
(LPL/HR/17), filled in by each panel member on HRMS's Interview Feedback.

No Frappe import, like jd_rules.py, so scripts/verify_interviews.py can
exercise it without a bench.

Each panel member scores every criterion 1 to 5, or N/A where it does not
apply to the role, on the form's scale:

    Excellent = 5 (90-100%)    Very Good = 4 (75-89%)    Good = 3 (60-74%)
    Average = 2 (50-59%)       Below Average = 1 (49% and below)

The sheet's percentage is the score earned over the most that could have
been earned on the criteria actually scored, so an N/A neither helps nor
hurts, and the same scale then names the overall result.
"""

# LPL/HR/17's criteria, grouped and ordered as the form prints them. Only
# the seed for the Interview Criteria Group and Interview Criterion masters:
# HR can add, rename, reorder and switch off criteria afterwards.
CRITERIA_GROUPS = ("Education", "Working Experience", "Personality", "Appearance", "Health")
CRITERIA = (
    ("Education", "Technical Qualification skills"),
    ("Working Experience", "Job knowledge"),
    ("Working Experience", "Job experience"),
    ("Working Experience", "Leadership/supervisory skills"),
    ("Working Experience", "Customer care skills"),
    ("Working Experience", "Computer skills"),
    ("Working Experience", "Team work skills"),
    ("Working Experience", "Communication skills"),
    ("Working Experience", "Training/learning ability"),
    ("Personality", "Candidate's attitude"),
    ("Personality", "Energy, Drive, Enthusiasm"),
    ("Personality", "Problem Solving Skills"),
    ("Personality", "Self Confidence"),
    ("Personality", "Ability to work under pressure"),
    ("Personality", "Interests & Hobbies"),
    ("Appearance", "Appearance"),
    ("Health", "Health"),
)

SCORES = ("1", "2", "3", "4", "5")
NOT_APPLICABLE = "N/A"
SCORE_OPTIONS = ("",) + SCORES + (NOT_APPLICABLE,)
TOP_SCORE = 5

# The scale's names, best first, each with the lowest percentage it covers
BANDS = ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average"))

# The form's three recommendations. HRMS's Interview Feedback records a
# Cleared / Rejected result: Shortlist means another interview, so the
# candidate goes through this one.
RECOMMENDATIONS = ("Offer", "Shortlist", "Reject")
RECOMMENDATION_MEANINGS = {"Offer": "Selected", "Shortlist": "To be interviewed again", "Reject": "Not selected"}
RESULTS = {"Offer": "Cleared", "Shortlist": "Cleared", "Reject": "Rejected"}


def band_for(total, maximum):
    """The scale's name for `total` out of `maximum`, "" when nothing was scored.

    Compared in whole numbers (total x 100 against floor x maximum), so a
    sheet exactly on a boundary, 27 of 30 = 90%, is never let down by
    floating point.
    """
    if not maximum:
        return ""
    for floor, name in BANDS:
        if total * 100 >= floor * maximum:
            return name
    return BANDS[-1][1]


def score_summary(rows):
    """The totals of one score sheet.

    rows: dicts or objects with a `score` of "1" to "5", "N/A" or blank.
    Returns {total, maximum, percent, band, scored, not_applicable, blank}:
      total    the 1-5 scores added up
      maximum  5 for every criterion scored 1-5 (N/A and blank rows add nothing)
      percent  total over maximum, 0 to 100, to 2 decimals
      band     the scale's name for that percentage ("" when nothing is scored)
    """
    total = maximum = scored = not_applicable = blank = 0
    for row in rows or []:
        score = _text(_get(row, "score"))
        if score in SCORES:
            total += int(score)
            maximum += TOP_SCORE
            scored += 1
        elif score == NOT_APPLICABLE:
            not_applicable += 1
        else:
            blank += 1
    return {
        "total": total,
        "maximum": maximum,
        "percent": round(total * 100.0 / maximum, 2) if maximum else 0.0,
        "band": band_for(total, maximum),
        "scored": scored,
        "not_applicable": not_applicable,
        "blank": blank,
    }


def average_rating(summary):
    """The sheet as HRMS's 0-1 Rating: 78% shows as 3.9 of 5 stars on the Interview."""
    return round(summary["total"] / float(summary["maximum"]), 4) if summary["maximum"] else 0.0


def result_for(recommendation):
    """HRMS's Cleared / Rejected result for a recommendation ("" for none)."""
    return RESULTS.get(recommendation or "", "")


def score_sheet_errors(rows, recommendation, submitting):
    """Problems with a score sheet, as user-facing messages.

    A draft may leave scores and the recommendation blank; submitting may
    not. A score outside the scale and a criterion listed twice are wrong
    either way.
    """
    rows = list(rows or [])
    errors = []
    seen = {}
    for index, row in enumerate(rows, start=1):
        criterion = _text(_get(row, "criterion"))
        score = _text(_get(row, "score"))
        label = "Row %d (%s)" % (index, criterion) if criterion else "Row %d" % index
        if score not in SCORE_OPTIONS:
            errors.append("%s: the score must be 1 to 5 or N/A, not %s." % (label, score))
        elif submitting and not score:
            errors.append("%s: score it from 1 to 5, or N/A where it does not apply." % label)
        if criterion:
            key = criterion.lower()
            if key in seen:
                errors.append("%s is already scored in row %d." % (label, seen[key]))
            else:
                seen[key] = index

    if recommendation and recommendation not in RECOMMENDATIONS:
        errors.append("The recommendation must be Offer, Shortlist or Reject, not %s." % recommendation)
    if submitting:
        if not rows:
            errors.append("There is nothing to score: add the criteria under Interview Criterion first.")
        elif all(_text(_get(row, "score")) == NOT_APPLICABLE for row in rows):
            errors.append("Score at least one criterion from 1 to 5: every row is N/A.")
        if not recommendation:
            errors.append("Choose a recommendation: Offer, Shortlist or Reject.")
    return errors


def sheet_rows(criteria):
    """The rows a new score sheet starts with, in the form's order.

    criteria: dicts with name, criteria_group, group_order, sort_order and
    disabled, one per Interview Criterion. Switched-off criteria are left
    out; the rest follow their group's display order, then their own, then
    their name.
    """
    active = [c for c in criteria or [] if not _get(c, "disabled")]
    active.sort(key=lambda c: (_int(_get(c, "group_order")), _int(_get(c, "sort_order")), _text(_get(c, "name")).lower()))
    return [{"criteria_group": _get(c, "criteria_group"), "criterion": _get(c, "name")} for c in active]


def criterion_averages(sheets):
    """Each criterion's average 1-5 score across the panel's sheets.

    sheets: one list of score rows per submitted sheet. N/A and blank
    scores are left out, and so is a criterion nobody scored. Returns
    [(criterion, average)] in the order the criteria first appear.
    """
    sums, counts, order = {}, {}, []
    for rows in sheets or []:
        for row in rows or []:
            criterion, score = _get(row, "criterion"), _text(_get(row, "score"))
            if not criterion or score not in SCORES:
                continue
            if criterion not in sums:
                order.append(criterion)
                sums[criterion] = counts[criterion] = 0
            sums[criterion] += int(score)
            counts[criterion] += 1
    return [(criterion, round(sums[criterion] / float(counts[criterion]), 2)) for criterion in order]


def criteria_seed_plan(existing_groups, existing_criteria, groups=CRITERIA_GROUPS, criteria=CRITERIA):
    """Records to create so the masters hold LPL/HR/17's groups and criteria.

    existing_groups / existing_criteria: the names already in each master.
    Names are compared ignoring case (the database collation would refuse
    both "Health" and "health"), and a criterion joins its group under the
    group's existing spelling. Display orders are 10, 20, ... in the form's
    order. Returns (group records, criterion records), ready to insert.
    """
    group_names = {str(name).strip().lower(): name for name in existing_groups or [] if name}
    group_records = []
    for position, group in enumerate(groups, start=1):
        if group.lower() not in group_names:
            group_names[group.lower()] = group
            group_records.append({"doctype": "Interview Criteria Group", "group_name": group, "sort_order": position * 10})

    taken = {str(name).strip().lower() for name in existing_criteria or [] if name}
    criterion_records = []
    for position, (group, criterion) in enumerate(criteria, start=1):
        if criterion.lower() in taken:
            continue
        taken.add(criterion.lower())
        criterion_records.append({
            "doctype": "Interview Criterion",
            "criterion_name": criterion,
            "criteria_group": group_names.get(group.lower(), group),
            "sort_order": position * 10,
        })
    return group_records, criterion_records


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _text(value):
    return "" if value is None else str(value).strip()


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
