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

# ── Training Needs Form (LPL/TRG/FRM06) ──────────────────────────────
# Its questions, in the form's order: (key, question, required). The key ties
# an answer to what reads it: a Training Requisition takes the skills answer
# as the employee's skill areas.
NEEDS_QUESTIONS = (
    ("responsibilities", "Primary job responsibilities", 1),
    ("skill_areas", "Skills / training areas that will benefit your work progress", 1),
    ("industry_trends", "Emerging trends or advancements you would like training on", 0),
    ("collaboration_areas", "Areas where inter-departmental collaboration could benefit your work", 0),
    ("training_feedback", "Feedback or suggestions on the existing training programmes", 0),
    ("comments", "Additional comments on your training needs", 0),
)
SKILLS_QUESTION = "skill_areas"


def needs_rows(rows):
    """A Training Needs Form's question rows: every question once, in the
    form's order, each with the answer it was given. rows: what the form
    holds (question_key, answer)."""
    answers = {}
    for row in rows or ():
        key = str(row.get("question_key") or "")
        if key and key not in answers:
            answers[key] = row.get("answer") or ""
    return [{"question_key": key, "question": question, "required": required, "answer": answers.get(key, "")}
            for key, question, required in NEEDS_QUESTIONS]


def needs_errors(rows):
    """The required questions left without an answer, as messages."""
    return ["Answer question %d: %s." % (index, row["question"]) for index, row in enumerate(rows, 1)
            if row.get("required") and not str(row.get("answer") or "").strip()]

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
# keys in and submits each evaluation, then downloads the Training Report,
# which Frappe exports, prints and makes a PDF of only for those who may do
# so with its Training Event (Frappe HR gives HR User neither); the Head of
# Department, or the supervisor who raised the requisition, confirms the
# participants on the draft session. Granted on every migrate, never
# revoked (workflows.py).
NEW_ROLES = ("Head of Department", "Supervisor")
PERMISSIONS = {
    "Training Event": {
        "HR User": ("read", "write", "create", "submit", "report", "export", "print"),
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

    facts: "topics" ([{"topic", "required_skills"}]), "employees" (count).
    """
    errors = []
    topics = facts.get("topics") or []
    if not topics:
        errors.append("List the training topics (Training Topics).")
    elif any(not (row.get("topic") or "").strip() for row in topics):
        errors.append("Every row of Training Topics needs its topic.")
    if topics and any(not (row.get("required_skills") or "").strip() for row in topics):
        errors.append("Say which skills or knowledge each topic must give (Required Skills).")
    if not facts.get("employees"):
        errors.append("List the employees to be trained (Target Employees).")
    return errors


def topics_summary(topics, limit=140):
    """The requisition's topics in one line, for its list and its messages."""
    text = ", ".join((row.get("topic") or "").strip() for row in topics or () if (row.get("topic") or "").strip())
    return text if len(text) <= limit else text[:limit - 3].rstrip(", ") + "..."


def need_rows(requisition, topics):
    """The Training Needs rows one requisition gives: one per topic, each
    naming its requisition. requisition: "requisition", "department",
    "preferred_month", "target_group"; topics: the requisition's rows."""
    return [{
        "topic": (row.get("topic") or "").strip(), "section": requisition.get("department"),
        "method": row.get("method"), "trainer": row.get("trainer"), "budget": row.get("budget") or 0,
        "duration": row.get("duration"), "month": requisition.get("preferred_month"),
        "target_group": requisition.get("target_group"), "objectives": row.get("required_skills"),
        "requisition": requisition.get("requisition"),
    } for row in topics or () if (row.get("topic") or "").strip()]


# ── Nobody twice ──────────────────────────────────────────────────────
def duplicates(values):
    """The values listed more than once, each once, in the order they first
    repeat; blanks aside."""
    seen, twice = set(), []
    for value in values or ():
        if not value:
            continue
        if value in seen and value not in twice:
            twice.append(value)
        seen.add(value)
    return twice


# ── The result: only those who attended, marks and effectiveness ─────
def result_errors(employees, participants):
    """Who a Training Result may not list: someone never booked for the
    session, or booked and not present. employees: the result's rows' employees;
    participants: {employee: attendance} of the Training Event.
    Returns [(employee, "not booked" | "absent")]."""
    out = []
    for employee in employees or ():
        if not employee:
            continue
        if employee not in (participants or {}):
            out.append((employee, "not booked"))
        elif (participants or {}).get(employee) != PRESENT:
            out.append((employee, "absent"))
    return out


EFFECTIVE, NOT_EFFECTIVE = "Effective", "Not Effective"
PASS_MARK = 50


def effectiveness(marks, pass_mark=PASS_MARK):
    """Effective when the marks reach the programme's pass mark (50 when it
    has none); None while no marks are given."""
    if marks in (None, ""):
        return None
    return EFFECTIVE if float(marks) >= (float(pass_mark or 0) or PASS_MARK) else NOT_EFFECTIVE


def trainers_line(names, limit=140):
    """A session's trainers in Frappe HR's one Trainer Name field."""
    text = ", ".join(name.strip() for name in names or () if (name or "").strip())
    return text if len(text) <= limit else text[:limit - 3].rstrip(", ") + "..."


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
    unless told otherwise. The hours come as the form sends them ("7:00:00"),
    as the database keeps them (a timedelta) or as a time."""
    day = _date(day)
    return (datetime.datetime.combine(day, _time(starts) if starts not in (None, "") else SESSION_STARTS),
            datetime.datetime.combine(day, _time(ends) if ends not in (None, "") else SESSION_ENDS))


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


# ── The Training Report (case 10) ─────────────────────────────────────
# What the HR Officer downloads once a training's evaluations are keyed in
# (report/training_report): one report, four views of the same trainings.
#   Trainings         a row per session: who was booked and came, the
#                     evaluation and how it reads, the marks and how many
#                     reached the pass mark
#   Participants      a row per person booked: attendance, evaluation, result
#   Evaluation Items  the consolidated evaluation form: how each item was
#                     rated, then the overall
#   Comments          every comment on an item and every answer to Section B,
#                     training by training, in the form's order
# The figures on top are the same in every view.
TRAININGS, PARTICIPANTS, ITEMS, COMMENTS = "Trainings", "Participants", "Evaluation Items", "Comments"
VIEWS = (TRAININGS, PARTICIPANTS, ITEMS, COMMENTS)
# a session stays a draft until it is held (training.py): submitted is held
HELD, SCHEDULED, CANCELLED = "Held", "Scheduled", "Cancelled"
NOT_MARKED = "Not Marked"
OVERALL = "Overall"
# the trainings on the chart: the latest held
CHART_TRAININGS = 12
NAVY, BLUE, SKY, GOLD, RED, GREY = "#14395E", "#3B78B5", "#9DBCE0", "#E8A317", "#D9534F", "#B8C2CF"
RATING_COLOURS = (NAVY, BLUE, SKY, GOLD, RED)  # Excellent down to Below Average


def rating_field(rating):
    """The column counting one of the form's five ratings."""
    return "rated_" + rating.lower().replace(" ", "_")


# each view's columns: (fieldname, label, fieldtype, options, width)
REPORT_COLUMNS = {
    TRAININGS: (
        ("training_event", "Training", "Link", "Training Event", 210),
        ("training_program", "Training Program", "Link", "Training Program", 180),
        ("branch", "Plant", "Link", "Branch", 110),
        ("department", "Department", "Link", "Department", 150),
        ("from_date", "From", "Date", None, 100),
        ("to_date", "To", "Date", None, 100),
        ("trainer", "Trainers", "Data", None, 160),
        ("status", "Status", "Data", None, 100),
        ("participants", "Participants", "Int", None, 105),
        ("present", "Present", "Int", None, 85),
        ("absent", "Absent", "Int", None, 85),
        ("attendance_rate", "Attendance %", "Percent", None, 115),
        ("evaluations", "Evaluations", "Int", None, 105),
        ("evaluation_score", "Evaluation Score", "Percent", None, 130),
        ("rating", "Rating", "Data", None, 115),
        ("assessed", "Assessed", "Int", None, 95),
        ("average_marks", "Average Marks", "Percent", None, 120),
        ("effective", "Effective", "Int", None, 90),
        ("effectiveness", "Effectiveness %", "Percent", None, 125),
    ),
    PARTICIPANTS: (
        ("training_event", "Training", "Link", "Training Event", 210),
        ("training_program", "Training Program", "Link", "Training Program", 170),
        ("from_date", "From", "Date", None, 100),
        ("branch", "Plant", "Link", "Branch", 110),
        ("employee", "Employee", "Link", "Employee", 120),
        ("employee_name", "Employee Name", "Data", None, 170),
        ("department", "Department", "Link", "Department", 150),
        ("attendance", "Attendance", "Data", None, 105),
        ("training_feedback", "Evaluation", "Link", "Training Feedback", 150),
        ("evaluation_score", "Evaluation Score", "Percent", None, 130),
        ("rating", "Rating", "Data", None, 115),
        ("marks", "Marks", "Percent", None, 90),
        ("result", "Result", "Data", None, 115),
    ),
    ITEMS: (("item", "Item Assessed", "Data", None, 330),)
    + tuple((rating_field(rating), rating, "Int", None, 105) for rating in RATINGS)
    + (("responses", "Responses", "Int", None, 100),
       ("score", "Score", "Percent", None, 90),
       ("rating", "Rating", "Data", None, 115)),
    COMMENTS: (
        ("training_event", "Training", "Link", "Training Event", 210),
        ("employee", "Employee", "Link", "Employee", 120),
        ("employee_name", "Employee Name", "Data", None, 170),
        ("question", "Question", "Data", None, 300),
        ("answer", "Answer", "Data", None, 420),
    ),
}


def training_status(docstatus, event_status):
    """Held once the session is submitted, Cancelled when Frappe HR's status
    says so, otherwise still Scheduled."""
    if event_status == EVENT_CANCELLED:
        return CANCELLED
    return HELD if docstatus == 1 else SCHEDULED


def narrow(events, participants, evaluations, results, department=None):
    """The trainings as one department's people had them: only its people,
    their evaluations and results, and the trainings they were booked on.
    Everything as it is without a department.

    events: [{"name", ...}]; participants: [{"training_event", "employee",
    "department", ...}]; evaluations and results: [{"training_event",
    "employee", ...}]."""
    if not department:
        return list(events), list(participants), list(evaluations), list(results)
    people = [row for row in participants if row.get("department") == department]
    booked = {(row.get("training_event"), row.get("employee")) for row in people}
    trainings = {row.get("training_event") for row in people}

    def theirs(rows):
        return [row for row in rows if (row.get("training_event"), row.get("employee")) in booked]

    return [event for event in events if event.get("name") in trainings], people, theirs(evaluations), theirs(results)


def training_rows(events, participants, evaluations, results):
    """A row per training, in the order given: who was booked, who came, the
    consolidated evaluation and how it reads, the marks and how many reached
    the pass mark. Attendance is a share of those booked, once it is held.

    evaluations: [{"training_event", "employee", "items": {item: rating},
    "score"}]; results: [{"training_event", "employee", "marks", "effective"}]."""
    people, forms, marks = _by_event(participants), _by_event(evaluations), _by_event(results)
    rows = []
    for event in events:
        name = event.get("name")
        booked = people.get(name, [])
        present = sum(1 for row in booked if row.get("attendance") == PRESENT)
        status = training_status(event.get("docstatus"), event.get("event_status"))
        evaluation = consolidate(forms.get(name, []))
        assessed = _assessed(marks.get(name, []))
        effective = sum(1 for row in assessed if row.get("effective") == EFFECTIVE)
        rows.append({
            "training_event": name, "training_program": event.get("training_program"),
            "branch": event.get("branch"), "department": event.get("department"),
            "from_date": _day(event.get("start")), "to_date": _day(event.get("end")),
            "trainer": event.get("trainer"), "status": status,
            "participants": len(booked), "present": present,
            "absent": sum(1 for row in booked if row.get("attendance") == ABSENT),
            "attendance_rate": _share(present, len(booked)) if status == HELD else None,
            "evaluations": evaluation["count"], "evaluation_score": evaluation["score"], "rating": evaluation["band"],
            "assessed": len(assessed), "average_marks": _mean([row.get("marks") for row in assessed]),
            "effective": effective, "effectiveness": _share(effective, len(assessed)),
        })
    return rows


def participant_rows(events, participants, evaluations, results):
    """A row per person booked on a training, training by training in the
    order given and in the order they were booked: whether they came, their
    evaluation and their result."""
    people = _by_event(participants)
    forms = {(row.get("training_event"), row.get("employee")): row for row in evaluations}
    marks = {(row.get("training_event"), row.get("employee")): row for row in _assessed(results)}
    rows = []
    for event in events:
        for person in people.get(event.get("name"), []):
            key = (event.get("name"), person.get("employee"))
            form, result = forms.get(key) or {}, marks.get(key) or {}
            rows.append({
                "training_event": event.get("name"), "training_program": event.get("training_program"),
                "from_date": _day(event.get("start")), "branch": event.get("branch"),
                "employee": person.get("employee"), "employee_name": person.get("employee_name"),
                "department": person.get("department"), "attendance": person.get("attendance") or NOT_MARKED,
                "training_feedback": form.get("name"), "evaluation_score": form.get("score"),
                "rating": band(form.get("score")), "marks": result.get("marks"), "result": result.get("effective"),
            })
    return rows


def item_rows(evaluations, order=()):
    """The consolidated evaluation form: for each item, how many rated it
    Excellent down to Below Average, how many rated it at all, its score and
    how it reads; the items in the form's order (order: the Training
    Evaluation Item list), any other after them, then the overall over every
    evaluation, scored as the training's own score is (consolidate)."""
    tallies = {}
    for form in evaluations:
        for item, rating in (form.get("items") or {}).items():
            if rating in RATING_VALUES:
                tallies.setdefault(item, dict.fromkeys(RATINGS, 0))[rating] += 1
    items = [item for item in order if item in tallies] + [item for item in tallies if item not in order]
    rows = [_item_row(item, tallies[item]) for item in items]
    if rows:
        overall = consolidate(evaluations)
        row = _item_row(OVERALL, {rating: sum(tallies[item][rating] for item in items) for rating in RATINGS})
        row.update({"responses": overall["count"], "score": overall["score"], "rating": overall["band"]})
        rows.append(row)
    return rows


def _item_row(item, tally):
    given = sum(tally.values())
    score = round(100.0 * sum(RATING_VALUES[rating] * count for rating, count in tally.items())
                  / (TOP_RATING * given), 1) if given else None
    row = {"item": item, "responses": given, "score": score, "rating": band(score)}
    row.update({rating_field(rating): tally.get(rating, 0) for rating in RATINGS})
    return row


def comment_rows(events, evaluations, questions, order=()):
    """Every comment on an item and every answer to Section B, as the form
    runs: training by training, Section A's items (in order, any other
    after them), then each question with everyone's answer under it, by
    name. questions: [(field, label)]; evaluations carry "comments"
    {item: text} and "answers" {field: text}."""
    forms = _by_event(evaluations)
    rows = []
    for event in events:
        theirs = sorted(forms.get(event.get("name"), []),
                        key=lambda form: str(form.get("employee_name") or form.get("employee") or ""))
        said = {item for form in theirs for item, text in (form.get("comments") or {}).items() if (text or "").strip()}
        items = [item for item in order if item in said] + sorted(said - set(order))
        asked = [(item, item, "comments") for item in items] + [(field, label, "answers") for field, label in questions]
        for key, question, where in asked:
            for form in theirs:
                text = ((form.get(where) or {}).get(key) or "").strip()
                if text:
                    rows.append({"training_event": event.get("name"), "employee": form.get("employee"),
                                 "employee_name": form.get("employee_name"), "question": question, "answer": text})
    return rows


def summary(trainings, participants, evaluations, results):
    """The figures on top, the same in every view, over the trainings held:
    how many were held and are still to come, how many people were
    trained, attendance, the evaluation and how many reached the pass mark."""
    held = [row for row in trainings if row["status"] == HELD]
    names = {row["training_event"] for row in held}
    booked = sum(row["participants"] for row in held)
    present = sum(row["present"] for row in held)
    trained = {row.get("employee") for row in participants
               if row.get("training_event") in names and row.get("attendance") == PRESENT}
    evaluation = consolidate([form for form in evaluations if form.get("training_event") in names])
    assessed = _assessed([row for row in results if row.get("training_event") in names])
    effective = sum(1 for row in assessed if row.get("effective") == EFFECTIVE)
    return {
        "held": len(held), "scheduled": sum(1 for row in trainings if row["status"] == SCHEDULED),
        "trained": len(trained), "attendance": _share(present, booked),
        "evaluation_score": evaluation["score"], "rating": evaluation["band"],
        "effectiveness": _share(effective, len(assessed)),
    }


def tone(percent):
    """The colour of a percentage, on the evaluation form's own scale: Very
    Good and above green, Good and Average orange, Below Average red."""
    name = band(percent)
    if name is None:
        return "Grey"
    return {"Excellent": "Green", "Very Good": "Green", "Good": "Orange", "Average": "Orange"}.get(name, "Red")


def summary_cards(figures):
    """The report summary: (label, value, datatype, colour)."""
    return [
        ("Trainings Held", figures["held"], "Int", "Blue"),
        ("Scheduled", figures["scheduled"], "Int", "Blue"),
        ("People Trained", figures["trained"], "Int", "Blue"),
        ("Attendance", figures["attendance"], "Percent", tone(figures["attendance"])),
        ("Evaluation Score", figures["evaluation_score"], "Percent", tone(figures["evaluation_score"])),
        ("Effectiveness", figures["effectiveness"], "Percent", tone(figures["effectiveness"])),
    ]


def chart(view, trainings, rows):
    """The chart over a view, or None: attendance and the evaluation score of
    the latest trainings held; who came, of those booked on a held training;
    how the ratings fell, over every item."""
    if view == TRAININGS:
        held = [row for row in trainings if row["status"] == HELD][-CHART_TRAININGS:]
        if not held:
            return None
        return {"type": "bar", "colors": [NAVY, GOLD], "height": 260,
                "data": {"labels": [_short(row["training_program"] or row["training_event"]) for row in held],
                         "datasets": [{"name": "Attendance %", "values": [row["attendance_rate"] or 0 for row in held]},
                                      {"name": "Evaluation Score", "values": [row["evaluation_score"] or 0 for row in held]}]}}
    if view == PARTICIPANTS:
        held = {row["training_event"] for row in trainings if row["status"] == HELD}
        kinds = (PRESENT, ABSENT, NOT_MARKED)
        counts = [sum(1 for row in rows if row["training_event"] in held and row["attendance"] == kind) for kind in kinds]
        if not sum(counts):
            return None
        return {"type": "donut", "colors": [BLUE, RED, GREY], "height": 260,
                "data": {"labels": list(kinds), "datasets": [{"values": counts}]}}
    if view == ITEMS:
        overall = rows[-1] if rows and rows[-1]["item"] == OVERALL else None
        if not overall or not sum(overall[rating_field(rating)] for rating in RATINGS):
            return None
        return {"type": "donut", "colors": list(RATING_COLOURS), "height": 260,
                "data": {"labels": list(RATINGS), "datasets": [{"values": [overall[rating_field(rating)] for rating in RATINGS]}]}}
    return None


def _assessed(results):
    """The results with a verdict: Frappe keeps a blank mark as 0, so a row is
    assessed when its marks were judged, not when they read as a number."""
    return [row for row in results if row.get("effective") in (EFFECTIVE, NOT_EFFECTIVE)]


def _by_event(rows):
    out = {}
    for row in rows:
        out.setdefault(row.get("training_event"), []).append(row)
    return out


def _share(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def _mean(values):
    values = [float(value) for value in values if value not in (None, "")]
    return round(sum(values) / len(values), 1) if values else None


def _short(text, limit=24):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _day(value):
    return _date(value) if value else None


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def _time(value):
    if isinstance(value, datetime.datetime):
        return value.time()
    if isinstance(value, datetime.time):
        return value
    if isinstance(value, datetime.timedelta):
        return (datetime.datetime.min + value).time()
    parts = str(value).strip().split(":")
    return datetime.time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0,
                         int(float(parts[2])) if len(parts) > 2 else 0)
