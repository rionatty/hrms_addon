# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance management: Luuka's appraisal round, on the shape of the
Supervisory Skills Evaluation Form (LPL/HR/18 Rev 01, 01-11-2024).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_performance.py exercises them without a bench.

THE FORM

  Section A   twelve ratable factors, each rated by the employee and then
              by the supervisor, worth 60 of the 100
  Section B   up to eight performance objectives / KPIs for the period,
              in line with the department's, rated the same way, worth 40
  Section C   the two sections added up as a percentage, and the band it
              falls in
  General     four questions the employee answers, then comments and
              signatures: Employee, Supervisor, HR Manager, Production
              Manager, General Manager

The engine is the one the probation form uses (probation_rules.py): the
same company, the same scale, the same bands. It is written out again here
rather than imported, because the two forms are free to drift — the
probation form already carries a thirteenth factor this one does not.

THE ROUND (the flowchart, and the test script's cases 1 to 10)

  1   the HR Officer draws up the Annual Appraisal Plan: the year, the
      quarters, their windows and their deadlines
  2   the plan is watched, and the HR Officer told when a quarter is due
  3   the appraisals are raised for the quarter's employees; the template
      can be printed or exported; the supervisor and the employee are told
  4   the supervisor rates the employee in the system, or fills the
      exported sheet and the HR Officer uploads it
  5   the HR Officer prepares the appraisal report and shares it with top
      management
  6   management decides: promotion, salary increase, a Performance
      Improvement Plan, or nothing
  7   a PIP is drawn up and followed
  8   a salary increase updates the salary structure
  9   a promotion is executed and recorded
  10  anyone else's appraisal is closed

Cases 8 and 9 are the Employee Position Change this app already has
(position_rules.py), so a decision raises one of those rather than
inventing another way to change pay or designation.
"""

import calendar
import datetime

# ── Section A of LPL/HR/18, in the form's order ──────────────────────
FACTORS = (
    "Job performance, work output, quality of work",
    "Job knowledge level so far learnt, following SOPs etc",
    "Initiative, creativity, new things, changes brought by the supervisor",
    "Attendance and time management",
    "Effective communication and giving feedback",
    "Problem / conflict solving / resolution",
    "Teamwork / inter-personal relations",
    "Managing people / supervising subordinates",
    "Attitude, dependability, flexibility, engagement / passion, admitting mistakes",
    "Capacity to learn, be trained, implement skills learnt",
    "General discipline / conduct",
    "Participation in housekeeping / hygiene practices",
)
APPRAISAL_MASTERS = {"Appraisal Factor": ("factor_name", FACTORS)}

# The form's General section, in its order: (fieldname, the question)
QUESTIONS = (
    ("roles", "List down the roles and responsibilities of your position in the company."),
    ("skills", "What are the skills you possess as a supervisor?"),
    ("achievements", "Can you share any achievements from the time you were appointed a supervisor?"),
    ("challenges", "Can you share any challenges faced?"),
)

NOT_APPLICABLE = "N/A"
RATINGS = ("1", "2", "3", "4", "5", NOT_APPLICABLE)
TOP_RATING = 5
# what each rating means, as the form prints the scale
RATING_LABELS = {"5": "Excellent (90-100%)", "4": "Very Good (75-89%)", "3": "Good (60-74%)",
                 "2": "Average (50-59%)", "1": "Below Average (40% and below)"}
FACTORS_WEIGHT, OBJECTIVES_WEIGHT = 60, 40
# (lowest total %, band), highest first: the form's Section C
BANDS = ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average"))
MAX_OBJECTIVES = 8

# ── The round ─────────────────────────────────────────────────────────
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
ANNUAL = "Annual"
# the appraisal is quarterly and the year is the average of the four
QUARTERS_IN_YEAR = len(QUARTERS)
# the recommendation: a soft deadline on the 25th, then a hard one
SOFT_DEADLINE_DAY = 25
# reminders before the hard deadline: a week, a day, and on the day
REMINDER_DAYS = (7, 1, 0)

# What management may decide (the flowchart's four ways out)
PROMOTION, INCREASE, PIP, CLOSE = "Promotion", "Salary Increase", "Performance Improvement Plan", "Close"
DECISIONS = (PROMOTION, INCREASE, PIP, CLOSE)
# the recommendation: below 60 the employee goes on a PIP
PIP_BELOW = 60
# a decision that is carried out by an Employee Position Change
POSITION_CHANGE_FOR = {PROMOTION: "Promotion", INCREASE: "Salary Increment"}

STATUSES = ("Draft", "Pending Supervisor", "Pending HR Manager", "Pending Production Manager",
            "Pending General Manager", "Completed", "Cancelled")
CYCLE_STATUSES = ("Not Started", "In Progress", "Completed")

# the columns of the sheet the supervisor fills away from the system
SHEET_COLUMNS = ("Appraisal", "Employee", "Employee Name", "Section", "No.", "Item",
                 "Employee Rating", "Supervisor Rating", "Supervisor Comment")
SECTION_A, SECTION_B = "A. Ratable Factors", "B. Objectives / KPIs"


def section_percent(ratings):
    """The percentage a section's ratings give, N/A and blanks left out;
    None when nothing in it is rated."""
    scores = [int(rating) for rating in ratings if rating not in (None, "", NOT_APPLICABLE)]
    if not scores:
        return None
    return 100.0 * sum(scores) / (TOP_RATING * len(scores))


def scores(factor_ratings, objective_ratings):
    """Section C from the supervisor's ratings: {"factors": out of 60,
    "objectives": out of 40, "total": percent}. A section with nothing rated
    scores None and the total is taken over the other alone."""
    factors, objectives = section_percent(factor_ratings), section_percent(objective_ratings)
    rated = [(percent, weight) for percent, weight in ((factors, FACTORS_WEIGHT), (objectives, OBJECTIVES_WEIGHT))
             if percent is not None]
    total = round(sum(percent * weight for percent, weight in rated) / sum(weight for _, weight in rated), 1) \
        if rated else None
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


def annual_average(quarter_totals):
    """The year's appraisal: the average of the quarters appraised, as the
    recommendation asks. None until at least one quarter is scored."""
    totals = [float(total) for total in quarter_totals if total is not None]
    if not totals:
        return None
    return round(sum(totals) / len(totals), 1)


def recommended(total):
    """What the score alone suggests before management meets: below 60 a
    Performance Improvement Plan, otherwise nothing is suggested — a
    promotion or an increase is management's to decide, not the score's."""
    if total is None:
        return None
    return PIP if total < PIP_BELOW else CLOSE


def quarter_window(year, quarter):
    """(first day, last day) of a quarter of `year`."""
    index = QUARTERS.index(quarter)
    first_month = index * 3 + 1
    last_month = first_month + 2
    return (datetime.date(year, first_month, 1),
            datetime.date(year, last_month, calendar.monthrange(year, last_month)[1]))


def deadlines(year, quarter, soft_day=SOFT_DEADLINE_DAY):
    """(soft, hard) deadlines for appraising a quarter: the soft one on the
    25th of the month after it closes, the hard one at that month's end."""
    _first, last = quarter_window(year, quarter)
    month_index = last.month  # the month after the quarter, zero-based on the year
    year_after, month = (last.year + 1, 1) if month_index == 12 else (last.year, month_index + 1)
    last_day = calendar.monthrange(year_after, month)[1]
    return datetime.date(year_after, month, min(soft_day, last_day)), datetime.date(year_after, month, last_day)


def plan_errors(facts):
    """Problems with an Annual Appraisal Plan as it is submitted.

    facts: "year", "quarters" ([{"quarter", "from_date", "to_date",
    "soft_deadline", "hard_deadline"}]), "appraisal_template", "company".
    """
    errors = []
    year = facts.get("year")
    if not year:
        errors.append("Set the year the plan covers.")
    if not facts.get("company"):
        errors.append("Name the company the plan is for.")
    quarters = facts.get("quarters") or []
    if not quarters:
        errors.append("List the quarters to be appraised: use Fill the Year, or add them by hand.")
    seen = set()
    for row in quarters:
        name = row.get("quarter")
        if name not in QUARTERS:
            errors.append("Every row must name a quarter (%s)." % ", ".join(QUARTERS))
            break
        if name in seen:
            errors.append("%s is listed twice." % name)
            break
        seen.add(name)
    for row in quarters:
        if not (row.get("from_date") and row.get("to_date")):
            errors.append("Give the window each quarter is appraised over (%s)." % (row.get("quarter") or "?"))
            break
        if str(row["to_date"]) < str(row["from_date"]):
            errors.append("%s ends before it starts." % (row.get("quarter") or "A quarter"))
            break
    for row in quarters:
        soft, hard = row.get("soft_deadline"), row.get("hard_deadline")
        if not hard:
            errors.append("Give the hard deadline for %s: the appraisals must be in by then."
                          % (row.get("quarter") or "each quarter"))
            break
        if soft and str(soft) > str(hard):
            errors.append("%s's soft deadline is after its hard deadline." % (row.get("quarter") or "A quarter"))
            break
        if row.get("to_date") and str(hard) < str(row["to_date"]):
            errors.append("%s's hard deadline falls inside the quarter it appraises." % (row.get("quarter") or "A quarter"))
            break
    return errors


def appraisal_errors(facts):
    """Problems with an appraisal at the step it is at.

    facts: "step" ("self", "supervisor"), "factors" and "objectives"
    ([{"item", "employee_rating", "supervisor_rating"}]), the four answers.
    """
    errors = []
    step = facts.get("step")
    factors, objectives = facts.get("factors") or [], facts.get("objectives") or []
    if step == "self":
        if not factors:
            errors.append("The ratable factors (Section A) are missing from the form.")
        unrated = [row["item"] for row in factors if not row.get("employee_rating")]
        if unrated:
            errors.append("Rate yourself on every factor, or N/A where it does not fit the job (Section A): %s."
                          % ", ".join(unrated[:3] + (["..."] if len(unrated) > 3 else [])))
        if not objectives:
            errors.append("List the objectives / KPIs for the period (Section B) before sending the form on.")
        else:
            unrated = [row["item"] for row in objectives if not row.get("employee_rating")]
            if unrated:
                errors.append("Rate yourself on every objective (Section B): %s."
                              % ", ".join(unrated[:3] + (["..."] if len(unrated) > 3 else [])))
        missing = [label for field, label in (("roles", "your roles and responsibilities"),
                                              ("skills", "the skills you possess"))
                   if not (facts.get(field) or "").strip()]
        if missing:
            errors.append("Answer the General questions: %s." % ", ".join(missing))
    if step == "supervisor":
        unrated = [row["item"] for row in factors + objectives if not row.get("supervisor_rating")]
        if unrated:
            errors.append("Give your rating for every factor and objective: %s."
                          % ", ".join(unrated[:3] + (["..."] if len(unrated) > 3 else [])))
        if len(objectives) > MAX_OBJECTIVES:
            errors.append("The form carries at most %d objectives; this one has %d." % (MAX_OBJECTIVES, len(objectives)))
    return errors


def due_quarters(rows, today):
    """The plan's quarters whose window has closed and whose appraisals are
    not raised yet: what the HR Officer is told about (case 2).

    rows: [{"quarter", "to_date", "appraisal_cycle", "notified_on"}]
    """
    day = _date(today)
    return [row for row in rows
            if row.get("to_date") and _date(row["to_date"]) <= day
            and not row.get("appraisal_cycle") and not row.get("notified_on")]


def reminders_due(hard_deadline, today, sent, soft_deadline=None):
    """The reminders to send today for a quarter closing on
    `hard_deadline`: a week before, a day before and on the day, each once,
    plus one on the soft deadline. A deadline first seen inside several
    thresholds gets the nearest."""
    if not hard_deadline:
        return []
    day, hard = _date(today), _date(hard_deadline)
    done = {n for n in str(sent or "").replace(",", " ").split() if n.strip()}
    due = []
    if soft_deadline and _date(soft_deadline) == day and "soft" not in done:
        due.append("soft")
    left = (hard - day).days
    if left >= 0:
        reached = [days for days in REMINDER_DAYS if left <= days and str(days) not in done]
        if reached:
            due.append(str(reached[-1]))
    return due


def record_reminders(sent, reached):
    """The reminders_sent field after sending: every threshold at or beyond
    the one reached, so a missed earlier one is not sent late."""
    done = {n for n in str(sent or "").replace(",", " ").split() if n.strip()}
    numbers = [int(n) for n in reached if str(n).isdigit()]
    if numbers:
        nearest = min(numbers)
        done |= {str(days) for days in REMINDER_DAYS if days >= nearest}
    if "soft" in [str(n) for n in reached]:
        done.add("soft")
    return ", ".join(sorted(done, key=lambda n: (n == "soft", -int(n) if n.isdigit() else 0)))


def sheet_rows(appraisal, employee, employee_name, factors, objectives):
    """The sheet the supervisor fills away from the system, one row per item
    (the flowchart's export/fill/upload branch)."""
    rows = []
    for index, row in enumerate(factors, 1):
        rows.append([appraisal, employee, employee_name, SECTION_A, index, row.get("item"),
                     row.get("employee_rating"), row.get("supervisor_rating"), row.get("supervisor_comment")])
    for index, row in enumerate(objectives, 1):
        rows.append([appraisal, employee, employee_name, SECTION_B, index, row.get("item"),
                     row.get("employee_rating"), row.get("supervisor_rating"), row.get("supervisor_comment")])
    return rows


def read_sheet(rows):
    """What an uploaded sheet says, keyed by appraisal:
    {appraisal: {"A": {item: (rating, comment)}, "B": {...}}}.

    The header row is skipped, blank rows ignored, and a rating that is not
    on the scale is left out rather than guessed at.
    """
    found = {}
    for row in rows or []:
        cells = list(row) + [None] * (len(SHEET_COLUMNS) - len(row))
        name, _employee, _employee_name, section, _no, item, _self, supervisor, comment = cells[:9]
        if not name or str(name).strip() == SHEET_COLUMNS[0]:
            continue
        if section not in (SECTION_A, SECTION_B):
            continue
        rating = str(supervisor).strip() if supervisor not in (None, "") else None
        if rating and rating.endswith(".0"):
            rating = rating[:-2]
        if rating not in RATINGS:
            rating = None
        key = "A" if section == SECTION_A else "B"
        found.setdefault(str(name).strip(), {"A": {}, "B": {}})[key][str(item).strip()] = (rating, comment)
    return found


def objectives_from_kras(kras, limit=MAX_OBJECTIVES):
    """Objectives taken from the Job Title's Key Result Areas, each once, at
    most `limit`: the form says they should be in line with the
    department's."""
    seen, out = set(), []
    for kra in kras:
        text = (kra or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])
