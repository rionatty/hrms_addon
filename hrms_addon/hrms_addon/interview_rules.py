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

import re

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


# ── The interview shortlist ───────────────────────────────────────────
# One per Job Opening, listing the applicants invited to interview the way
# Luuka's shortlist sheet does: name and contacts, then education, work
# experience, and certifications and licences, each written out from the
# applicant's Pre-Interview Bio-Data (LPL/HR/19) so HR does not retype it.

# Applicants who can still be shortlisted: not already turned down or hired
SHORTLISTABLE_STATUSES = ("Open", "Replied", "Hold", "Shortlisted")


def contact_line(name, phone, email):
    """'Mark Henry, 0781669900, markhenry@gmail.com', leaving out what is blank."""
    return ", ".join(part for part in (_text(name), _text(phone), _text(email)) if part)


def qualification_lines(qualifications, certification_types, certifications):
    """The applicant's qualifications as the shortlist lists them, one per line.

    certifications=False gives the Education Qualification column, True the
    Certifications and Licences column: a row counts as a certification when
    its type is one of certification_types. Each line reads
    '<study / program>, <institution> (<year / period>)', most recent first;
    the award stands in when no program is given.
    """
    kinds = {_text(t).lower() for t in certification_types or []}
    picked = [row for row in qualifications or []
              if (_text(_get(row, "qualification_type")).lower() in kinds) == bool(certifications)]
    lines = []
    for row in _most_recent_first(picked, lambda row: _latest_year(_get(row, "period"))):
        title = _text(_get(row, "program")) or _text(_get(row, "award"))
        place = _text(_get(row, "institution"))
        period = _text(_get(row, "period"))
        line = ", ".join(part for part in (title, place) if part)
        if period:
            line = "%s (%s)" % (line, period) if line else period
        if line:
            lines.append(line)
    return "\n".join(lines)


def experience_lines(history):
    """Employment history as the shortlist lists it, one job per line, most recent
    first: '<position>, <workplace> (<from> - <to>)', 'Present' when no end is given."""
    lines = []
    for row in _most_recent_first(history or [], _job_recency):
        position, workplace = _text(_get(row, "position")), _text(_get(row, "workplace"))
        start, end = _text(_get(row, "from_year")), _text(_get(row, "to_year"))
        line = ", ".join(part for part in (position, workplace) if part)
        if start or end:
            tenure = "%s - %s" % (start or "?", end or "Present")
            line = "%s (%s)" % (line, tenure) if line else tenure
        if line:
            lines.append(line)
    return "\n".join(lines)


def shortlist_errors(job_opening, rows, opening_of, submitting):
    """Problems with a shortlist, as user-facing messages.

    rows: dicts or objects with job_applicant. opening_of: {applicant: the
    Job Opening they applied for}, looked up by the caller. A draft may be
    empty; a submitted shortlist may not.
    """
    rows = list(rows or [])
    if not rows:
        return ["Add the applicants invited to interview (Get Applicants lists everyone who applied)."] if submitting else []
    errors, seen = [], {}
    for index, row in enumerate(rows, start=1):
        applicant = _text(_get(row, "job_applicant"))
        if not applicant:
            continue
        if applicant in seen:
            errors.append("Row %d: %s is already listed in row %d." % (index, applicant, seen[applicant]))
            continue
        seen[applicant] = index
        applied_for = _text((opening_of or {}).get(applicant))
        if job_opening and applied_for != _text(job_opening):
            errors.append("Row %d: %s applied for %s, not this opening." % (index, applicant, applied_for or "no opening"))
    return errors


def interview_slots(start, minutes, count):
    """`count` back-to-back interview slots of `minutes` from `start`.

    start: 'HH:MM' or 'HH:MM:SS'. Returns [('HH:MM:SS', 'HH:MM:SS')], or
    raises ValueError when the length is not positive or the day runs out.
    """
    minutes = _int(minutes)
    if minutes <= 0:
        raise ValueError("Each interview needs a length in minutes.")
    parts = [int(p) for p in _text(start).split(":")]
    if len(parts) < 2 or not (0 <= parts[0] < 24 and 0 <= parts[1] < 60):
        raise ValueError("The first interview needs a start time.")
    begin = parts[0] * 60 + parts[1]
    if begin + minutes * count > 24 * 60:
        raise ValueError("%d interviews of %d minutes from %02d:%02d run past midnight." % (count, minutes, parts[0], parts[1]))
    return [(_clock(begin + i * minutes), _clock(begin + (i + 1) * minutes)) for i in range(count)]


def _clock(total_minutes):
    return "%02d:%02d:00" % divmod(total_minutes, 60)


def _latest_year(text):
    years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", _text(text))
    return int(years[-1]) if years else None


# ── The interview report ──────────────────────────────────────────────
# One per Job Opening and interview day, like Luuka's interview report: the
# panel, each candidate with their qualifications, experience and the panel's
# verdict, and the recommendations, forwarded to the Executive Director
# through the Human Resource Manager (interview_report_approval.py).


def band_for_percent(percent):
    """The scale's name for a percentage, such as a panel's average ("" for none)."""
    if percent is None:
        return ""
    value = round(float(percent), 2)
    for floor, name in BANDS:
        if value >= floor:
            return name
    return BANDS[-1][1]


def panel_summary(sheets):
    """What a candidate's panel made of them, from their submitted score sheets.

    sheets: dicts or objects with the sheet's percent, its maximum (0 when
    nothing was scored) and its recommendation. Returns {count, average,
    band, tally, decision}: the average of the scored sheets' percentages,
    the recommendations counted in the form's order ("Offer 3, Reject 1"),
    and the decision when more than half the panel agreed on it ("" when
    they did not, for HR to settle).
    """
    sheets = list(sheets or [])
    percents = [float(_get(s, "percent") or 0) for s in sheets if _int(_get(s, "maximum"))]
    average = round(sum(percents) / len(percents), 2) if percents else None
    counts = {}
    for sheet in sheets:
        recommendation = _text(_get(sheet, "recommendation"))
        if recommendation in RECOMMENDATIONS:
            counts[recommendation] = counts.get(recommendation, 0) + 1
    voted = sum(counts.values())
    decision = next((r for r in RECOMMENDATIONS if counts.get(r, 0) * 2 > voted), "")
    return {
        "count": len(sheets),
        "average": average,
        "band": band_for_percent(average),
        "tally": ", ".join("%s %d" % (r, counts[r]) for r in RECOMMENDATIONS if counts.get(r)),
        "decision": decision,
    }


def salary_remark(currency, low, high):
    """'Expects UGX 2,600,000 to 2,700,000 a month.' from the application's
    expected salary range ("" when none was given)."""
    amounts = [float(v) for v in (low, high) if v and float(v) > 0]
    if not amounts:
        return ""
    prefix = (_text(currency) + " ") if _text(currency) else ""
    text = " to ".join("{:,.0f}".format(v) for v in sorted(set(amounts)))
    return "Expects %s%s a month." % (prefix, text)


def report_errors(candidates, recommendations, complete):
    """Problems with an interview report, as user-facing messages.

    complete: the report is past Draft (sent for approval or beyond), so it
    must list the candidates, a decision for each, and the panel's
    recommendations. A candidate twice or a decision off the form is wrong
    either way.
    """
    candidates = list(candidates or [])
    errors, seen = [], {}
    for index, row in enumerate(candidates, start=1):
        applicant = _text(_get(row, "job_applicant"))
        decision = _text(_get(row, "decision"))
        if applicant in seen:
            errors.append("Row %d: %s is already listed in row %d." % (index, applicant, seen[applicant]))
        elif applicant:
            seen[applicant] = index
        if decision and decision not in RECOMMENDATIONS:
            errors.append("Row %d: the decision must be Offer, Shortlist or Reject, not %s." % (index, decision))
        elif complete and not decision:
            errors.append("Row %d (%s): choose the panel's decision." % (index, _text(_get(row, "applicant_name")) or applicant))
    if complete:
        if not candidates:
            errors.append("List the candidates interviewed (Get Interview Results fills them in).")
        if not _text(recommendations):
            errors.append("Write the panel's recommendations before sending the report on.")
    return errors


# What the approved report makes of each applicant (Job Applicant.status):
# HRMS marks a cleared interview's applicant Accepted and a rejected one
# Rejected (Interview.get_job_applicant_status), and Shortlist means another
# interview. The Job Offer moves them on from there.
APPLICANT_STATUSES = {"Offer": "Accepted", "Shortlist": "Shortlisted", "Reject": "Rejected"}


def applicant_status_after(decision, current):
    """An applicant's status once the report is approved, or None to leave it.

    Only an applicant still undecided moves: one already Accepted or Rejected
    (by a Job Offer, say, or by hand) keeps their status.
    """
    status = APPLICANT_STATUSES.get(_text(decision))
    if not status or current not in SHORTLISTABLE_STATUSES or current == status:
        return None
    return status


def offer_plan(rows, existing):
    """Who on an approved report gets a Job Offer: the panel's Offer decisions.

    rows:     the report's candidates (job_applicant, decision, job_offer).
    existing: {applicant: offer} for each applicant who already has a Job
              Offer that is not cancelled (HRMS allows one).
    Returns (to_create, to_link): applicants who need a draft offer, and
    [(applicant, offer)] rows to point at the offer they already have. A row
    already pointing at its live offer is left alone.
    """
    to_create, to_link = [], []
    for row in rows or []:
        applicant = _get(row, "job_applicant")
        if _get(row, "decision") != "Offer" or not applicant:
            continue
        offer = (existing or {}).get(applicant)
        if offer and _get(row, "job_offer") == offer:
            continue
        if offer:
            to_link.append((applicant, offer))
        else:
            to_create.append(applicant)
    return to_create, to_link


def _job_recency(row):
    """A job with no end is the current one; otherwise its end year, then its start year."""
    if not _text(_get(row, "to_year")) and _text(_get(row, "from_year")):
        return 9999
    return _latest_year(_get(row, "to_year")) or _latest_year(_get(row, "from_year"))


def _most_recent_first(rows, year_of):
    """Newest first; rows with no year keep their order, after the dated ones."""
    dated = [(year_of(row), index, row) for index, row in enumerate(rows)]
    return [row for year, index, row in sorted(dated, key=lambda d: (d[0] is None, -(d[0] or 0), d[1]))]


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _text(value):
    return "" if value is None else str(value).strip()


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
