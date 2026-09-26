# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Interview rules: Luuka's Candidate Interview Evaluation / Score Form
(LPL/HR/17), filled in by each panel member on HRMS's Interview Feedback.

No Frappe import, like jd_rules.py, so scripts/verify_interviews.py can
exercise it without a bench.

Each panel member scores every criterion 1 to 5 on the form's scale:

    Excellent = 5    Very Good = 4    Good = 3    Average = 2    Below Average = 1

A criterion counts as much as its weight: the round (Interview Type) lists
the criteria it scores and weighs them from the JD, where an Essential
competency counts three times a Desirable one. A round with no list of its
own scores the general list, each criterion once. The sheet's percentage is
the weighted score earned over the most that could have been earned, and
its rating is the scale's name for the average score, rounded: 4.5 and up
Excellent, 3.5 Very Good, 2.5 Good, 1.5 Average. (The paper form put
Average at 50-59% of the maximum, which a candidate scored 2 on everything,
40%, never reaches.)

N/A: a round with its own list has already said what applies, so every
row there is scored. On the general list N/A leaves a criterion out, and
the panel member says why in its comments.
"""

import datetime
import re

# LPL/HR/17's criteria, grouped and ordered as the form prints them. Only
# the seed for the Interview Criteria Group and Interview Criterion masters:
# HR can add, rename, reorder and switch off criteria afterwards. The form's
# Appearance and Health are not seeded, and are switched off where they
# were (RETIRED_CRITERIA): Uganda's Employment Act 2006, section 6, makes
# a decision on HIV status or disability unlawful, and a panel's view of
# health or looks is exactly that risk. Fitness for the work is a doctor's
# check after the offer, where the JD asks for one.
CRITERIA_GROUPS = ("Education", "Working Experience", "Personality")
RETIRED_CRITERIA = ("Appearance", "Health")
# never scored at interview, whatever the list says: HR can keep such a
# criterion, switched off, but not switch it on
PROTECTED_CRITERIA = ("health", "health status", "medical", "medical condition", "medical history", "hiv status",
                      "disability", "pregnancy", "religion", "tribe", "gender", "sex", "marital status", "age",
                      "appearance")
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
)

SCORES = ("1", "2", "3", "4", "5")
NOT_APPLICABLE = "N/A"
SCORE_OPTIONS = ("",) + SCORES + (NOT_APPLICABLE,)
TOP_SCORE = 5

# The scale's names, best first, each with the lowest percentage of the
# maximum it covers: an average score of 4.5 is 90%, 3.5 is 70%, 2.5 is 50%
# and 1.5 is 30%, so each name covers the average scores that round to it
BANDS = ((90, "Excellent"), (70, "Very Good"), (50, "Good"), (30, "Average"), (0, "Below Average"))
# what an Offer needs where the round sets no pass mark: a Good sheet
OFFER_FLOOR = 50
# a criterion counts 1 to 5 times; a JD priority with no weight counts once
WEIGHTS = (1, 2, 3, 4, 5)
# the criteria group a JD's competencies are scored under
JD_GROUP = "Job Competencies"

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

    rows: dicts or objects with a `score` of "1" to "5", "N/A" or blank, and
    the criterion's `weight` (1 when there is none).
    Returns {total, maximum, percent, band, scored, not_applicable, blank}:
      total    the 1-5 scores added up, each times its weight
      maximum  5 times the weight of every criterion scored 1-5 (N/A and
               blank rows add nothing)
      percent  total over maximum, 0 to 100, to 2 decimals
      band     the scale's name for that percentage ("" when nothing is scored)
    """
    total = maximum = scored = not_applicable = blank = 0
    for row in rows or []:
        score = _text(_get(row, "score"))
        if score in SCORES:
            weight = _weight(_get(row, "weight"))
            total += int(score) * weight
            maximum += TOP_SCORE * weight
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


def score_sheet_errors(rows, recommendation, submitting, round_criteria=False):
    """Problems with a score sheet, as user-facing messages.

    A draft may leave scores and the recommendation blank; submitting may
    not. A score outside the scale and a criterion listed twice are wrong
    either way. round_criteria: the rows are the round's own list, which has
    already said what applies, so none of them is N/A; on the general list
    an N/A needs its reason in the row's comments.
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
        elif score == NOT_APPLICABLE and round_criteria:
            errors.append("%s: this round scores every criterion on its list, from 1 to 5." % label)
        elif submitting and not score:
            errors.append("%s: score it from 1 to 5%s." % (label, "" if round_criteria else ", or N/A where it does not apply"))
        elif submitting and score == NOT_APPLICABLE and not _text(_get(row, "comments")):
            errors.append("%s: say in its comments why it does not apply." % label)
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


def submission_errors(summary, recommendation, comments, no_conflict, answers, pass_mark):
    """What a sheet needs before it is submitted, besides its scores.

    summary: score_summary's. comments: the panel member's comments on the
    candidate's suitability. no_conflict: they have ticked that they have no
    personal or family relationship with the candidate. answers: the
    interview's questions (question, score). pass_mark: the percentage an
    Offer needs on this round, None for the round's default (a Good sheet).
    """
    errors = []
    if not no_conflict:
        errors.append("Tick that you have no personal or family relationship with this candidate. If you have one, "
                      "tell HR instead of scoring.")
    for index, row in enumerate(answers or [], start=1):
        if _text(_get(row, "score")) not in SCORES:
            errors.append("Question %d: score the answer from 1 to 5." % index)
    if not _text(comments):
        errors.append("Write your comments on the candidate's suitability for the position.")
    floor = OFFER_FLOOR if pass_mark in (None, "") else float(pass_mark)
    if recommendation == "Offer" and (summary or {}).get("maximum") and float(summary.get("percent") or 0) < floor:
        errors.append("The sheet scores %s%% (%s), under the %s%% an Offer needs: recommend Shortlist or Reject, "
                      "or check the scores." % (_number(summary["percent"]), summary.get("band"), _number(floor)))
    return errors


def pass_percent(expected_rating):
    """The round's pass mark as a percentage, from its Expected Average Rating
    (Frappe stores a star rating as 0 to 1: 3 stars is 0.6, 60%); None when
    the round sets none."""
    try:
        value = float(expected_rating or 0)
    except (TypeError, ValueError):
        return None
    return round(value * 100, 2) if value > 0 else None


def question_summary(answers):
    """The interview's questions as scored: {scored, total, maximum, percent}."""
    scores = [int(score) for score in (_text(_get(row, "score")) for row in answers or []) if score in SCORES]
    maximum = TOP_SCORE * len(scores)
    return {"scored": len(scores), "total": sum(scores), "maximum": maximum,
            "percent": round(sum(scores) * 100.0 / maximum, 2) if maximum else 0.0}


def sheet_rows(criteria):
    """The rows a new score sheet starts with, in the form's order.

    criteria: dicts with name, criteria_group, group_order, sort_order and
    disabled, one per Interview Criterion. Switched-off criteria are left
    out; the rest follow their group's display order, then their own, then
    their name. Each counts once.
    """
    active = [c for c in criteria or [] if not _get(c, "disabled")]
    active.sort(key=lambda c: (_int(_get(c, "group_order")), _int(_get(c, "sort_order")), _text(_get(c, "name")).lower()))
    return [{"criteria_group": _get(c, "criteria_group"), "criterion": _get(c, "name"), "weight": 1} for c in active]


def criterion_errors(name, disabled):
    """A criterion that must never be scored cannot be switched on."""
    if disabled or _plain(name) not in PROTECTED_CRITERIA:
        return []
    return ["%s is not scored at interview: keep it switched off (Disabled). Where the job needs it, fitness for the "
            "work is a doctor's check after the offer." % _text(name)]


def round_criteria_plan(competencies, weights, general, existing):
    """The criteria a round starts with, from its JD.

    competencies: the JD's competency rows (competency, priority), in order.
    weights: {priority: weight}, from JD Requirement Priority. general: the
    general list's rows (criterion), in order. existing: the Interview
    Criterion names already there, in any case.
    Returns (rows, to_create): rows [{criterion, weight}], the JD's
    competencies first, weighed by their priority, then the general list
    once each, nothing twice (ignoring case) and nothing that is never
    scored; to_create: the competencies not yet in the list of criteria.
    """
    known = {_text(name).lower(): name for name in existing or () if _text(name)}
    rows, seen, to_create = [], set(), []
    for row in competencies or ():
        name = _text(_get(row, "competency"))
        if not name or name.lower() in seen or _plain(name) in PROTECTED_CRITERIA:
            continue
        seen.add(name.lower())
        criterion = known.get(name.lower())
        if criterion is None:
            criterion = known[name.lower()] = name
            to_create.append(name)
        rows.append({"criterion": criterion, "weight": _weight((weights or {}).get(_get(row, "priority")))})
    for row in general or ():
        name = _text(_get(row, "criterion"))
        if not name or name.lower() in seen or _plain(name) in PROTECTED_CRITERIA:
            continue
        seen.add(name.lower())
        rows.append({"criterion": name, "weight": 1})
    return rows, to_create


def round_criteria_errors(rows, disabled=()):
    """Problems with a round's own list of criteria: one twice, a weight off
    1 to 5, one switched off, one never scored."""
    errors, seen = [], {}
    off = {_text(name).lower() for name in disabled or ()}
    for index, row in enumerate(rows or [], start=1):
        criterion = _text(_get(row, "criterion"))
        if not criterion:
            continue
        key = criterion.lower()
        if key in seen:
            errors.append("Score Sheet row %d: %s is already in row %d." % (index, criterion, seen[key]))
            continue
        seen[key] = index
        if _int(_get(row, "weight")) not in WEIGHTS:
            errors.append("Score Sheet row %d (%s): the weight must be 1 to 5, not %s."
                          % (index, criterion, _text(_get(row, "weight")) or "0"))
        if key in off:
            errors.append("Score Sheet row %d: %s is switched off in the list of criteria." % (index, criterion))
        elif _plain(criterion) in PROTECTED_CRITERIA:
            errors.append("Score Sheet row %d: %s is not scored at interview." % (index, criterion))
    return errors


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


def language_line(row):
    """'English (read, write, speak)', from one of the applicant's language rows."""
    abilities = [label for fieldname, label in (("can_read", "read"), ("can_write", "write"), ("can_speak", "speak"))
                 if _get(row, fieldname)]
    language = _text(_get(row, "language"))
    return "%s (%s)" % (language, ", ".join(abilities)) if abilities and language else language


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


# ── Booking a round ───────────────────────────────────────────────────
# the attendance HR records on an interview, and how a candidate is met
ATTENDANCE = ("Attended", "No-Show", "Withdrew")
ABSENT = ("No-Show", "Withdrew")
MODES = ("In Person", "Video Call", "Phone Call")


def plan_slots(first_day, start, minutes, count, gap=0, lunch=None, day_end=None, is_working_day=None, max_days=60):
    """`count` interview slots of `minutes`, `gap` minutes apart, from `start`
    on `first_day`: none across the lunch break or past the day's end, the
    rest carried to the next working day at the same start time.

    first_day: 'YYYY-MM-DD'. start, day_end and lunch (from, to): 'HH:MM[:SS]',
    or a timedelta as the database returns a Time. is_working_day: a
    function of 'YYYY-MM-DD'; every day is one without it.
    Returns [('YYYY-MM-DD', 'HH:MM:SS', 'HH:MM:SS')], or raises ValueError.
    """
    minutes, gap = _int(minutes), max(_int(gap), 0)
    if minutes <= 0:
        raise ValueError("Each interview needs a length in minutes.")
    begin = _minutes_of(start)
    if begin is None:
        raise ValueError("The first interview needs a start time.")
    end = _minutes_of(day_end) or 24 * 60
    lunch_from, lunch_to = (_minutes_of(lunch[0]), _minutes_of(lunch[1])) if lunch else (None, None)
    if lunch_from is None or lunch_to is None:
        lunch_from = lunch_to = None
    elif lunch_to <= lunch_from:
        raise ValueError("The lunch break must end after it starts.")

    def clear_of_lunch(at):
        if lunch_from is not None and at < lunch_to and at + minutes > lunch_from:
            return lunch_to
        return at

    if clear_of_lunch(begin) + minutes > end:
        raise ValueError("An interview of %d minutes does not fit between %s and %s."
                         % (minutes, _clock(begin)[:5], _clock(end)[:5]))
    day = datetime.date.fromisoformat(_text(first_day)[:10])
    if is_working_day and not is_working_day(day.isoformat()):
        raise ValueError("%s is not a working day." % day.isoformat())
    slots, at, days = [], clear_of_lunch(begin), 0
    while len(slots) < count:
        at = clear_of_lunch(at)
        if at + minutes > end:
            day, days = day + datetime.timedelta(days=1), days + 1
            while is_working_day and not is_working_day(day.isoformat()) and days <= max_days:
                day, days = day + datetime.timedelta(days=1), days + 1
            if days > max_days:
                raise ValueError("There is no working day for these interviews in the next %d days." % max_days)
            at = clear_of_lunch(begin)
            continue
        slots.append((day.isoformat(), _clock(at), _clock(at + minutes)))
        at += minutes + gap
    return slots


def booking_plan(listed, chosen, already, statuses, earlier_round, cleared):
    """Who is booked for a round, in the shortlist's order.

    listed: the shortlist's applicants; chosen: the ones HR ticked (none:
    everyone); already: those who have this round; statuses: {applicant:
    Job Applicant status}; earlier_round: the round follows another for the
    same job; cleared: those who cleared that earlier round.
    Returns {"book", "already", "out", "not_cleared"}: the ones to book, the
    ones who have the round, the ones no longer in the running with their
    status, and the ones who have not cleared the round before.
    """
    already, cleared = set(already or ()), set(cleared or ())
    plan = {"book": [], "already": [], "out": [], "not_cleared": []}
    for applicant in to_book(listed, chosen, ()):
        status = _text((statuses or {}).get(applicant))
        if applicant in already:
            plan["already"].append(applicant)
        elif status not in SHORTLISTABLE_STATUSES:
            plan["out"].append((applicant, status or "unknown"))
        elif earlier_round and applicant not in cleared:
            plan["not_cleared"].append(applicant)
        else:
            plan["book"].append(applicant)
    return plan


def clashes(slots, panel, busy, leave):
    """Why the panel cannot sit these slots: a panel member in another
    interview at the same time, or on leave that day.

    slots: [(date, from, to)]; panel: users; busy: [(user, date, from, to,
    interview)] of their other interviews; leave: [(user, from_date, to_date)].
    Returns one message per clash.
    """
    panel = [user for user in panel or () if user]
    messages = []
    for user, date, start, finish, interview in busy or ():
        if user not in panel:
            continue
        for day, slot_start, slot_end in slots or ():
            if _text(date)[:10] == day and _minutes_of(start) < _minutes_of(slot_end) \
                    and _minutes_of(slot_start) < _minutes_of(finish):
                message = "%s sits on another interview (%s) on %s from %s to %s." % (
                    user, interview, day, _clock(_minutes_of(start))[:5], _clock(_minutes_of(finish))[:5])
                if message not in messages:
                    messages.append(message)
                break
    days = sorted({day for day, _start, _end in slots or ()})
    for user, from_date, to_date in leave or ():
        if user not in panel:
            continue
        away = [day for day in days if _text(from_date)[:10] <= day <= _text(to_date)[:10]]
        if away:
            message = "%s is on leave on %s." % (user, ", ".join(away))
            if message not in messages:
                messages.append(message)
    return messages


def slot_over(scheduled_on, to_time, now):
    """True once the interview's slot has ended. now: 'YYYY-MM-DD HH:MM[:SS]'."""
    day, finish, clock = _text(scheduled_on)[:10], _minutes_of(to_time), _minutes_of(_text(now)[11:19])
    today = _text(now)[:10]
    return bool(day) and (day < today or (day == today and finish is not None and clock is not None and finish <= clock))


def status_for_attendance(attendance, status):
    """The Interview's status once HR records who came, or None to leave it:
    a no-show or a withdrawal is Cancelled; someone who came is Under Review
    while the panel scores."""
    attendance = _text(attendance)
    if attendance in ABSENT:
        return "Cancelled" if status != "Cancelled" else None
    if attendance == "Attended" and status in ("Pending", "Cancelled"):
        return "Under Review"
    return None


def invitation_sms(company, designation, date, time, mode, venue):
    """The invitation as one text message: what for, when and where."""
    where = {"Video Call": " by video call", "Phone Call": " by phone"}.get(_text(mode)) or (
        " at %s" % _text(venue) if _text(venue) else "")
    return "%s: interview for %s on %s at %s%s. Details by email." % (
        _text(company) or "Interview", _text(designation), _text(date), _text(time), where)


def regret_due(status, sent_on, has_offer, email):
    """A regret email goes once, to an applicant turned down who was never
    offered the job (one who declined an offer is Rejected too)."""
    return _text(status) == "Rejected" and not sent_on and not has_offer and bool(_text(email))


def earlier_round(types, this_round):
    """The Interview Types of the round just before `this_round`, from the
    job's types [(name, round)]; several may share a round number."""
    this_round = _int(this_round)
    before = [(name, _int(number)) for name, number in types or () if 0 < _int(number) < this_round]
    last = max((number for _name, number in before), default=0)
    return [name for name, number in before if number == last]


# The two letters, seeded once as Email Templates (interviews.seed_interview_letters)
# and HR's to change after that. Frappe prints a key a template names but is
# not given as itself, so every key is always passed; free text is escaped.
INVITATION_TEMPLATE = "Interview Invitation"
REGRET_TEMPLATE = "Application Regret"
INVITATION_KEYS = ("applicant_name", "designation", "company", "date", "time", "mode", "venue", "meeting_link",
                   "what_to_bring", "interview")
REGRET_KEYS = ("applicant_name", "designation", "company")
INVITATION_SUBJECT = "Interview for {{ designation }}"
INVITATION_BODY = "".join((
    "<p>Dear {{ applicant_name | e }},</p>",
    "<p>Thank you for applying for the position of {{ designation }} at {{ company }}. "
    "We would like to invite you to an interview.</p>",
    "<p><b>Date:</b> {{ date }}<br><b>Time:</b> {{ time }}<br>",
    "{% if mode == 'Video Call' %}<b>Where:</b> by video call"
    "{% if meeting_link %}: <a href=\"{{ meeting_link | e }}\">{{ meeting_link | e }}</a>{% endif %}",
    "{% elif mode == 'Phone Call' %}<b>Where:</b> by phone, on the number you gave us",
    "{% else %}<b>Where:</b> {{ (venue or company) | e }}{% endif %}</p>",
    "{% if what_to_bring %}<p><b>Please bring:</b> {{ what_to_bring | e }}</p>{% endif %}",
    "<p>Please reply to this email to confirm that you will attend, or to ask for another time.</p>",
    "<p>Yours sincerely,<br>Human Resources<br>{{ company }}</p>",
))
REGRET_SUBJECT = "Your application for {{ designation }}"
REGRET_BODY = "".join((
    "<p>Dear {{ applicant_name | e }},</p>",
    "<p>Thank you for your interest in the position of {{ designation }} at {{ company }}, "
    "and for the time you gave to our recruitment process.</p>",
    "<p>After careful consideration, we will not be taking your application further on this occasion.</p>",
    "<p>We wish you every success.</p>",
    "<p>Yours sincerely,<br>Human Resources<br>{{ company }}</p>",
))


def to_book(applicants, chosen, already):
    """The applicants to book for an interview round, in the shortlist's
    order: the ones HR chose (everyone on the list when none is chosen),
    less the ones who already have that round."""
    chosen, already = set(chosen or ()), set(already or ())
    return [applicant for applicant in applicants or ()
            if (not chosen or applicant in chosen) and applicant not in already]


def _clock(total_minutes):
    return "%02d:%02d:00" % divmod(total_minutes, 60)


def _minutes_of(value):
    """Minutes since midnight of 'HH:MM[:SS]' or a timedelta; None for blank."""
    if value is None or value == "":
        return None
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds() // 60)
    parts = re.findall(r"[0-9]+", _text(value))
    if len(parts) < 2:
        return None
    hours, minutes = int(parts[0]), int(parts[1])
    if not (0 <= hours <= 24 and 0 <= minutes < 60):
        return None
    return hours * 60 + minutes


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


def _weight(value):
    """A criterion's weight, 1 to 5; blank or nonsense counts once."""
    weight = _int(value)
    return weight if weight in WEIGHTS else (WEIGHTS[-1] if weight > WEIGHTS[-1] else 1)


def _plain(name):
    """'HIV-status ' as 'hiv status': letters and single spaces, lower case."""
    return " ".join(re.sub(r"[^a-z]+", " ", _text(name).lower()).split())


def _number(value):
    """42.0 as '42', 42.5 as '42.5'."""
    return ("%.2f" % float(value)).rstrip("0").rstrip(".")


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _text(value):
    return "" if value is None else str(value).strip()


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
