# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LMS phase 3, delivery: the rules, without a Frappe import
(scripts/verify_learning_delivery.py). learning_delivery.py reads and writes
the site.

The blueprint's sections 4.4 and 4.5 on Frappe HR's own Training Event,
Training Feedback and Training Result (17 Nov 2026). Requests and their
approval stay as they are: the Training Needs Assessment, then the Training
Calendar (decided with the user).

  attendance    who was invited, who came, the no-shows and the hours each
                session gave (LPL/TRG/FRM03, the attendance form, is its print)
  Level 1       the trainees' evaluation forms (LPL/TRG/FRM05), as now
  Level 2       the Training Result's marks against the programme's pass mark,
                as now; a trainee who did not pass is told, with their
                supervisor and HR, so the training is booked again
  Level 3       a Training Application Review for each trainee who came,
                raised for their supervisor a set number of days after the
                session: did they apply it, did their behaviour change, did
                their competency improve
  Level 4       a Training Impact Review for each KPI the programme names,
                raised for HR after the session: the KPI before and after.
                Where the KPI is one the Shift Reports carry (waste, downtime,
                safety, PPE, attendance, output, the shift score), it is
                worked out from the trainees' section
"""

import datetime

# ── Level 3: the supervisor's review ──────────────────────────────────
PENDING, DONE = "Pending", "Done"
REVIEW_STATUSES = (PENDING, DONE)
APPLIED = (("Applied in Full", 100), ("Applied in Part", 50), ("Not Applied", 0))
BEHAVIOUR = (("1 No Change", 0), ("2 Little Change", 25), ("3 Some Change", 50), ("4 Clear Change", 75),
             ("5 Marked Change", 100))
COMPETENCY = (("Improved", 100), ("Partly Improved", 50), ("Not Improved", 0))
REVIEW_ANSWERS = (("applied", dict(APPLIED)), ("behaviour", dict(BEHAVIOUR)), ("competency", dict(COMPETENCY)))
REVIEW_DAYS_TO_ANSWER = 14
# a session that ended long before the system began asks nobody: only those
# whose day came within this many days are raised
CATCH_UP_DAYS = 30


def review_score(review):
    """The three answers' average, out of 100; None until all three are in."""
    scores = [values.get(review.get(field)) for field, values in REVIEW_ANSWERS]
    if any(score is None for score in scores):
        return None
    return round(sum(scores) / 3.0, 1)


def review_errors(review):
    errors = []
    for field, values in REVIEW_ANSWERS:
        value = review.get(field)
        if value and value not in values:
            errors.append("{0} is not one of the answers.".format(value))
    if review.get("applied") == "Not Applied" and not (review.get("comments") or "").strip():
        errors.append("Say why it was not applied.")
    return errors


def raise_on(event_end, days):
    event_end = _date(event_end)
    return event_end + datetime.timedelta(days=int(days)) if event_end else None


def due_now(event_end, days, today):
    """Whether a review falls to be raised today: its day has come, and not
    so long ago that the session was before the system."""
    day, today = raise_on(event_end, days), _date(today)
    return bool(day and today and day <= today and (today - day).days <= CATCH_UP_DAYS)


def reviewees(event):
    """The trainees a session raises a review for: those marked present."""
    return [row.get("employee") for row in event.get("employees") or ()
            if row.get("employee") and row.get("attendance") == "Present"]


# ── Level 4: the impact on the floor ──────────────────────────────────
HIGHER, LOWER = "Higher", "Lower"
OTHER = "Other"
# KPI, which way is better, how the Shift Reports give it
IMPACT_KPIS = (
    ("Waste Value", LOWER, "waste"),
    ("Complaint Value", LOWER, "complaints"),
    ("Machine Hours Lost", LOWER, "hours_lost"),
    ("Safety Incidents", LOWER, "incidents"),
    ("PPE Compliance %", HIGHER, "ppe"),
    ("Attendance %", HIGHER, "attendance"),
    ("Output per Person-Shift", HIGHER, "output_per_person"),
    ("Shift Score", HIGHER, "score"),
    (OTHER, None, None),
)
KPI_NAMES = tuple(name for name, _better, _how in IMPACT_KPIS)
KPI_BETTER = {name: better for name, better, _how in IMPACT_KPIS if better}
KPI_FROM_SHIFTS = {name: how for name, _better, how in IMPACT_KPIS if how}
IMPROVED, WORSE, NO_CHANGE = "Improved", "Worse", "No Change"
OPEN, MEASURED = "Open", "Measured"


def impact_windows(start, end, window):
    """(before from, before to, after from, after to): the `window` days before
    the session began and the same after it ended."""
    start, end = _date(start), _date(end)
    days = datetime.timedelta(days=int(window))
    one = datetime.timedelta(days=1)
    return start - days, start - one, end + one, end + days


def kpi_from_totals(kpi, totals, averages):
    """A KPI from the Shift Reports' totals() and averages() for a window; None
    when the window has no shift reports."""
    how = KPI_FROM_SHIFTS.get(kpi)
    if not how or not totals.get("count"):
        return None
    if how in ("waste", "complaints", "hours_lost", "incidents"):
        return round(_num(totals.get(how)), 2)
    if how in ("ppe", "attendance"):
        value = averages.get(how)
        return round(value * 100, 1) if value is not None else None
    if how == "output_per_person":
        return round(_num(totals.get("actual")) / totals["on_shift"], 2) if totals.get("on_shift") else None
    return averages.get("score")


def impact_result(better, baseline, after):
    """(change, change as a percentage of the baseline, the result)."""
    if baseline in (None, "") or after in (None, "") or not better:
        return None, None, ""
    change = round(_num(after) - _num(baseline), 4)
    percent = round(100.0 * change / _num(baseline), 1) if _num(baseline) else None
    if change == 0:
        return change, percent, NO_CHANGE
    return change, percent, IMPROVED if (change > 0) == (better == HIGHER) else WORSE


def impact_errors(review):
    errors = []
    if review.get("kpi") == OTHER and not (review.get("kpi_name") or "").strip():
        errors.append("Name the KPI.")
    if review.get("kpi") == OTHER and not review.get("better"):
        errors.append("Say whether higher or lower is better.")
    for first, last, label in (("baseline_from", "baseline_to", "before"), ("after_from", "after_to", "after")):
        if _date(review.get(first)) and _date(review.get(last)) and _date(review.get(last)) < _date(review.get(first)):
            errors.append("The {0} period ends before it starts.".format(label))
    if _date(review.get("baseline_to")) and _date(review.get("after_from")) and \
            _date(review.get("after_from")) <= _date(review.get("baseline_to")):
        errors.append("The after period must start after the before period ends.")
    return errors


def main_section(sections):
    """The section most of the trainees work in, for measuring the impact."""
    counted = {}
    for section in sections or ():
        if section:
            counted[section] = counted.get(section, 0) + 1
    if not counted:
        return None
    return max(sorted(counted), key=lambda section: counted[section])


# ── Attendance ────────────────────────────────────────────────────────
def attendance_of(event, hours):
    """A session's invited, present, absent, unmarked, no-show rate and the
    hours it gave in all."""
    rows = [row for row in event.get("employees") or () if row.get("employee")]
    present = sum(1 for row in rows if row.get("attendance") == "Present")
    absent = sum(1 for row in rows if row.get("attendance") == "Absent")
    marked = present + absent
    return {"invited": len(rows), "present": present, "absent": absent, "unmarked": len(rows) - marked,
            "no_show": round(100.0 * absent / marked, 1) if marked else None,
            "hours": round(present * _num(hours), 2)}


def day_columns(start, end, most=5):
    """The FRM03 form's signature columns: a column for each day the session
    runs, at least one and at most `most`."""
    first, last = _date(start), _date(end)
    if not first:
        return 1
    days = ((last - first).days + 1) if last and last >= first else 1
    return max(1, min(int(most), days))


# ── Level 2: who did not pass ─────────────────────────────────────────
def newly_failed(rows, before_rows, not_effective):
    """The employees whose result is now Not Effective and was not before."""
    was = {row.get("employee") for row in before_rows or () if row.get("custom_effective") == not_effective}
    return [row.get("employee") for row in rows or ()
            if row.get("custom_effective") == not_effective and row.get("employee") not in was]


# ── Effectiveness, programme by programme ─────────────────────────────
def effectiveness(events, results, reviews, impacts, pass_word):
    """Kirkpatrick's four levels for one programme's sessions:
    events   [{"present", "evaluation_score"}]
    results  [{"effective"}]           the Training Result rows
    reviews  [{"status", "score", "applied"}]
    impacts  [{"result"}]"""
    scored = [_num(event.get("evaluation_score")) for event in events if event.get("evaluation_score")]
    assessed = [row for row in results if row.get("effective")]
    passed = sum(1 for row in assessed if row.get("effective") == pass_word)
    done = [review for review in reviews if review.get("status") == DONE]
    measured = [impact for impact in impacts if impact.get("result")]
    return {
        "sessions": len(events), "trainees": sum(int(_num(event.get("present"))) for event in events),
        "reaction": round(sum(scored) / len(scored), 1) if scored else None,
        "assessed": len(assessed), "pass_rate": round(100.0 * passed / len(assessed), 1) if assessed else None,
        "reviews": len(reviews), "reviews_done": len(done),
        "application": round(sum(_num(review.get("score")) for review in done) / len(done), 1) if done else None,
        "applied_rate": round(100.0 * sum(1 for review in done if review.get("applied") != "Not Applied")
                              / len(done), 1) if done else None,
        "kpis": len(measured), "kpis_improved": sum(1 for impact in measured if impact.get("result") == IMPROVED),
    }


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
