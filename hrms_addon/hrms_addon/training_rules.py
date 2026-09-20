# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training and development rules: Luuka's To-Be training process.

No Frappe import, like the other *_rules.py modules, so scripts/verify_training.py
exercises them without a bench.

The flowchart, and the test script's cases 1 to 10:

  1-2  the Head of Department raises a Training Requisition (topic, skills,
       target employees); the HR Officer is told
  3-4  the HR Officer prepares the Training Needs Assessment (objectives,
       methods) from the requisitions; the HR Manager then the General
       Manager approve it, or return it for amendment
  5    approved needs are consolidated into the Training Calendar
       (LPL/TRAINING/01: course, trainer, budget, duration, month, target
       group); the General Manager approves it
  6    a month before, the HR Officer is reminded of next month's trainings
  7    the Monthly Training Schedule is drawn from the calendar; each line
       becomes a Training Event (date, time, venue, trainer, participants);
       the HOD, the trainers and the trainees are told, and reminded a week,
       a day and the morning before
  8-9  on the day the attendance list (LPL/TRG/FRM03) is printed; after,
       attendance is marked, the signed sheet attached, and the evaluation
       forms (LPL/TRG/FRM05) printed
  10   each participant's evaluation is keyed in; the report consolidates
       them across events, branches and periods
"""

import calendar
import datetime

# ── Training Evaluation Form (LPL/TRG/FRM05) ─────────────────────────
# Section A, in the form's order (seeded as the Training Evaluation Item list)
EVALUATION_ITEMS = (
    "Course content / syllabus was organised and easy to follow",
    "Course relevance",
    "Training methodology by the trainer",
    "The trainer was knowledgeable",
    "Trainer met the training objectives / expectations",
    "Understood what the trainer was training",
    "Adequate time for questions and discussion",
    "Training presentation, handouts, materials",
    "Venue, refreshments",
    "Class participation and interaction was encouraged",
)
TRAINING_MASTERS = {"Training Evaluation Item": ("item", EVALUATION_ITEMS)}
# the form's five columns, worth 5 down to 1
RATINGS = ("Excellent", "Very Good", "Good", "Average", "Below Average")
RATING_VALUES = {"Excellent": 5, "Very Good": 4, "Good": 3, "Average": 2, "Below Average": 1}
TOP_RATING = 5
# Section B, in the form's order: (fieldname, the question)
QUESTIONS = (
    ("expectations", "What were your expectations at the beginning of the training / what did you want to learn?"),
    ("learnt", "What new knowledge and skills have you learnt / acquired from the training?"),
    ("application", "How will you apply the knowledge learnt on the job / in your department?"),
    ("remaining_gaps", "What other training needs / gaps do you still have that are still challenging you to execute your roles?"),
    ("trainer_recommendations", "Suggest recommendations in which the trainers should improve, if any."),
    ("hr_recommendations", "Suggest ways in which the Human Resource office should improve in organising / implementing training, if any."),
)

# ── The process ───────────────────────────────────────────────────────
METHODS = ("Internal", "External", "On the Job", "Online", "Workshop", "Coaching")
PRIORITIES = ("High", "Medium", "Low")
MONTHS = tuple(calendar.month_name[1:])  # January .. December
REQUISITION_STATUSES = ("Draft", "Submitted", "In Assessment", "Scheduled", "Closed", "Cancelled")
# the Monthly Training Schedule's reminders: days before the training
REMINDER_DAYS = (7, 1, 0)
# the calendar's: a month before, the HR Officer draws up the schedule
CALENDAR_REMINDER_MONTHS = 1
# the session, as Frappe HR's Training Event knows it
EVENT_SCHEDULED, EVENT_COMPLETED, EVENT_CANCELLED = "Scheduled", "Completed", "Cancelled"
PRESENT, ABSENT = "Present", "Absent"
# The Training Event's `type` is a Select (Seminar, Theory, Workshop, ...):
# what each of our methods books as
EVENT_TYPES = {"Internal": "Workshop", "External": "Seminar", "On the Job": "Workshop", "Online": "Internet",
               "Workshop": "Workshop", "Coaching": "Theory"}
SESSION_STARTS, SESSION_ENDS = datetime.time(7, 0), datetime.time(9, 0)  # the usual 07:00 to 09:00

# ── Who works on Frappe HR's training documents ──────────────────────
# Frappe HR leaves creating and submitting them to the HR Manager. At Luuka
# the branch HR Officer (HR User) books a session, submits it once held and
# keys in and submits each evaluation; the Head of Department, or the
# supervisor who raised the requisition, confirms the participants on the
# draft session. Granted on every migrate, never revoked (workflows.py).
NEW_ROLES = ("Head of Department", "Supervisor")
PERMISSIONS = {
    "Training Event": {
        "HR User": ("read", "write", "create", "submit"),
        "Head of Department": ("read", "write"),
        "Supervisor": ("read", "write"),
    },
    "Training Feedback": {"HR User": ("read", "write", "create", "submit")},
    "Training Program": {"HR User": ("read", "write", "create")},
}


def score(ratings):
    """The evaluation's Section A as a percentage: the ratings given,
    Excellent 5 down to Below Average 1, over what they could have scored.
    None when nothing is rated."""
    values = [RATING_VALUES[r] for r in ratings if r in RATING_VALUES]
    if not values:
        return None
    return round(100.0 * sum(values) / (TOP_RATING * len(values)), 1)


def band(percent):
    """The overall rating of a percentage, on the form's scale."""
    if percent is None:
        return None
    for floor, name in ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average")):
        if percent >= floor:
            return name


def consolidate(evaluations):
    """The consolidated evaluation report of a training: the average of each
    item over the evaluations that rated it, the overall percentage, how it
    reads, and how many took part.

    evaluations: [{"items": {item: rating}, "score": percent}]
    Returns {"items": [(item, average percent, how many)], "score", "band", "count"}.
    """
    per_item = {}
    for evaluation in evaluations:
        for item, rating in (evaluation.get("items") or {}).items():
            if rating in RATING_VALUES:
                per_item.setdefault(item, []).append(RATING_VALUES[rating])
    items = [(item, round(100.0 * sum(values) / (TOP_RATING * len(values)), 1), len(values))
             for item, values in per_item.items()]
    scores = [e["score"] for e in evaluations if e.get("score") is not None]
    overall = round(sum(scores) / len(scores), 1) if scores else None
    return {"items": items, "score": overall, "band": band(overall), "count": len(evaluations)}


def requisition_errors(facts):
    """Problems with a requisition as it is submitted, as user-facing messages.

    facts: "topic", "skills", "employees" (count), "justification".
    """
    errors = []
    if not (facts.get("topic") or "").strip():
        errors.append("Give the training a topic.")
    if not (facts.get("skills") or "").strip():
        errors.append("Say which skills or knowledge the training must give (Required Skills).")
    if not facts.get("employees"):
        errors.append("List the employees to be trained (Target Employees).")
    return errors


def assessment_errors(facts):
    """Problems with a Training Needs Assessment going for approval.

    facts: "needs" ([{"topic", "method", "objectives"}]), "objectives".
    """
    errors = []
    needs = facts.get("needs") or []
    if not needs:
        errors.append("List the training needs (from the requisitions, or typed) before sending the assessment for approval.")
    for row in needs:
        if not (row.get("topic") or "").strip():
            errors.append("Every training need must have a topic.")
            break
    for row in needs:
        if not row.get("method"):
            errors.append("Propose the training method for every need (Internal, External, On the Job, Online...).")
            break
    if not (facts.get("objectives") or "").strip():
        errors.append("State the training objectives before sending the assessment for approval.")
    return errors


def calendar_rows(needs, year):
    """The Training Calendar rows an approved assessment gives: one per
    need, keyed by its topic, carrying what the planner shows.

    needs: [{"topic", "section", "trainer", "trainer_type", "budget", "duration", "month", "target_group",
             "assessment", "need_row"}]
    """
    rows = []
    for need in needs:
        rows.append({
            "course": need.get("topic"),
            "section": need.get("section"),
            "trainer": need.get("trainer"),
            "trainer_type": need.get("trainer_type") or ("External" if need.get("method") == "External" else "Internal"),
            "budget": need.get("budget") or 0,
            "duration": need.get("duration"),
            "planned_month": need.get("month"),
            "planned_year": year,
            "target_group": need.get("target_group"),
            "assessment": need.get("assessment"),
            "need_row": need.get("need_row"),
        })
    return rows


def next_month(today):
    """(year, month name) of the month after `today`."""
    day = _date(today)
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return year, MONTHS[month - 1]


def due_for_schedule(rows, today):
    """The calendar rows planned for next month that nobody has been reminded
    of yet: the HR Officer draws up the schedule a month before.

    rows: [{"planned_year", "planned_month", "reminded_on", "scheduled"}]
    """
    year, month = next_month(today)
    return [row for row in rows
            if int(row.get("planned_year") or 0) == year and row.get("planned_month") == month
            and not row.get("reminded_on") and not row.get("scheduled")]


def session_times(day, starts=None, ends=None):
    """(start, end) datetimes of a session on `day`, at the usual hours
    unless told otherwise."""
    day = _date(day)
    return (datetime.datetime.combine(day, starts or SESSION_STARTS),
            datetime.datetime.combine(day, ends or SESSION_ENDS))


def schedule_errors(facts):
    """Problems with a Monthly Training Schedule as it is submitted (which
    books the Training Events).

    facts: "lines" ([{"course", "date", "venue", "trainer", "participants"}]), "month", "year".
    """
    errors = []
    lines = facts.get("lines") or []
    if not lines:
        errors.append("Add the trainings for the month before submitting the schedule.")
    for line in lines:
        missing = [label for key, label in (("course", "course"), ("date", "date"), ("venue", "venue"), ("trainer", "trainer"))
                   if not line.get(key)]
        if missing:
            errors.append("Every training on the schedule needs its %s: %s." % (", ".join(missing), line.get("course") or "?"))
            break
    for line in lines:
        if line.get("date") and facts.get("month") and facts.get("year"):
            day = _date(line["date"])
            if (day.year, MONTHS[day.month - 1]) != (int(facts["year"]), facts["month"]):
                errors.append("%s is dated %s, outside %s %s." % (line.get("course") or "A training", day,
                                                                  facts["month"], facts["year"]))
                break
    # participants are not asked for here: each session starts with the
    # requisition's target employees and the Head of Department adds to them
    # on the Training Event (the flowchart's step 8)
    return errors


def reminders_due(start, today, sent):
    """The reminders to send today for a session starting on `start`: a week
    before, a day before and on the day (REMINDER_DAYS), each once. A session
    first seen inside several gets one, the nearest."""
    if not start:
        return []
    left = (_date(start) - _date(today)).days
    if left < 0:
        return []
    done = {int(n) for n in str(sent or "").replace(",", " ").split() if n.strip().isdigit()}
    due = [days for days in REMINDER_DAYS if left <= days and days not in done]
    return due[-1:]  # the nearest threshold reached, marked below


def record_reminders(sent, days_reached):
    """The reminders_sent field after sending: every threshold at or beyond
    the one reached, so a missed earlier one is not sent late."""
    done = {int(n) for n in str(sent or "").replace(",", " ").split() if n.strip().isdigit()}
    if days_reached:
        nearest = min(days_reached)
        done |= {days for days in REMINDER_DAYS if days >= nearest}
    return ", ".join(str(n) for n in sorted(done, reverse=True))


def event_name(course, day, branch=None):
    """A Training Event's name: the course, the day and, where several
    plants run it, the branch — within Frappe's 140 characters."""
    parts = [str(course or "Training")[:80], str(_date(day))]
    if branch:
        parts.append(str(branch)[:30])
    return " - ".join(parts)


def attendance_days(start, end):
    """The days a training runs, for the attendance sheet's Day 1, 2, 3 columns
    (at least one, at most the three the form has)."""
    if not start or not end:
        return 1
    days = (_date(end) - _date(start)).days + 1
    return max(1, min(days, 3))


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
