# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence: the rules, without a Frappe import
(scripts/verify_excellence.py). The excellence*.py modules read and write the
site.

Built from the plant's HR Manufacturing Excellence workbook (v3.2, Oct 2026),
batch 8 of the six-files plan, and rebuilt on 18 Nov 2026 after the client
called the first build shallow. What is modelled, and where:

  Work Section       a production section of a plant, under a department.
                     Its standards (target, crew, machines, labour budget and
                     rates, waste and complaint limits) are dated rows, read
                     by date, so a past period reads the standard in force
                     then. Its roster is dated too: who supervises, or is the
                     production officer, on which shift, from when to when
  Plant Day Sheet    one per plant and date: a row for each section and shift
                     (about 20), the typed shift figures, the people columns
                     from the clock, one approval. It writes the Shift Reports
  Shift Report       one per section, shift and date: its crew from the clock
                     (each person rostered, present or not, late, early,
                     overtime, what the day cost), its downtime events by
                     machine and reason, its output lines by order. Scored on
                     eight weighted factors
  Section Day        what each submitted shift adds to its section's day,
  Summary            and the section's week (Section Week Summary, the
                     workbook's Weekly Summary) and downtime by reason. Every
                     scorecard reads these with GROUP BY
  Plant Order        an order released to the floor: the Order Feasibility
                     report sets its labour and losses against its value
  People Log         coaching, toolbox talks, recognition, suggestions, pulse
                     surveys and HR observations, with who took part
  HR Intervention    a workforce issue, HR's assessment, the intervention, one
                     owner and a target date, the signal that raised it, and
                     its KPI read week by week
  HR Partner Brief   the week for the Monday production meeting: the money,
                     where it went, who to coach, the talking points, the
                     signals and the nine questions for the Plant Manager
  Disciplinary Case  the cause classified first; the Employment Act's limits
                     flagged (15 days to impose a penalty, s.62(5); at most
                     15 days' suspension in six months, s.62(4))

A period is scored from its totals, as the workbook's Weekly Summary
(column V) and Supervisor Dashboard (column F) do: the output factor is the
period's output over its target, the waste factor its waste over the limit
for the shifts it ran, and so on. A plant is the average of its sections'
scores (the workbook's Dashboard). The HR Excellence score weighs eight
pillars; a pillar with no data is left out and the others re-weighted: no
data is not poor performance. A safety incident, an open legal flag or a
grievance open too long marks the period critical whatever the score.

Settings hold percentages as typed (95 for 95%); settings_from turns them
into fractions for the sums.
"""

import datetime
import re

ME_OFFICER = "Manufacturing Excellence Officer"
NEW_ROLES = (ME_OFFICER,)
PERMISSIONS = {}

DAY, NIGHT, BOTH = "Day", "Night", "Both"
SHIFTS = (DAY, NIGHT)
ROSTER_SHIFTS = (DAY, NIGHT, BOTH)
UNITS = ("Kg", "Pcs", "Metres", "Lots", "Jobs")
DIRECT, INDIRECT = "Direct", "Indirect"
LABOUR_TYPES = (DIRECT, INDIRECT)
ON_TARGET, ATTENTION, CRITICAL, NO_DATA = "On Target", "Attention", "Critical", "No Data"
RED_FLAG = "Critical: Red Flag"
STATUSES = (ON_TARGET, ATTENTION, CRITICAL)

# the shift score's eight factors: key, label, the HR partner's first move
# when it is the weakest
FACTORS = (
    ("output", "Output", "Review the shift plan, job cards and material with the supervisor; agree a realistic plan."),
    ("waste", "Waste", "Find the root cause of the rejects with the supervisor; retrain operators on the SOP."),
    ("complaints", "Complaints", "Trace the complaint to the shift and operator; run a quality refresher."),
    ("uptime", "Machine Uptime", "Review stopped machines with Maintenance and Planning; fix the top reason first."),
    ("attendance", "Attendance", "Hold return to work talks; plan leave; keep a relief pool for gaps."),
    ("safety", "Safety", "Investigate within 24 hours; hold a toolbox talk; check training and certificates."),
    ("housekeeping", "Housekeeping", "Walk the area with the supervisor; give each area an owner."),
    ("ppe", "PPE", "Check PPE at shift start; issue or replace it; warn repeat cases."),
)
FACTOR_KEYS = tuple(key for key, _label, _action in FACTORS)
FACTOR_LABELS = {key: label for key, label, _action in FACTORS}
FACTOR_ACTIONS = {key: action for key, _label, action in FACTORS}

PILLARS = (
    ("planning", "Workforce Planning and Deployment"),
    ("productivity", "Labour Productivity and Cost"),
    ("attendance", "Attendance and Reliability"),
    ("skills", "Skills and Competency"),
    ("supervision", "Supervisory Effectiveness"),
    ("safety", "Safety and Wellbeing"),
    ("relations", "Employee Relations and Engagement"),
    ("interventions", "HR Intervention Effectiveness"),
)
PILLAR_KEYS = tuple(key for key, _label in PILLARS)
PILLAR_LABELS = dict(PILLARS)

# the supervisor's people-management index: what is in their hands, not
# machines, materials or orders; and the development focus its weakest part
# points to
SUPERVISOR_PARTS = (
    ("reporting", "Shift Reporting"),
    ("attendance", "Attendance"),
    ("ppe", "PPE Enforcement"),
    ("safety", "Safety Leadership"),
    ("housekeeping", "Housekeeping"),
    ("conduct", "Team Conduct"),
    ("closure", "Actions Closed on Time"),
    ("coaching", "Coaching"),
)
SUPERVISOR_KEYS = tuple(key for key, _label in SUPERVISOR_PARTS)
SUPERVISOR_LABELS = dict(SUPERVISOR_PARTS)
DEVELOPMENT_FOCUS = {
    "reporting": "Shift Reporting Discipline",
    "attendance": "Attendance Management",
    "ppe": "PPE Enforcement",
    "safety": "Safety Leadership",
    "housekeeping": "Housekeeping Standards",
    "conduct": "Employee Conduct Management",
    "closure": "Corrective Action Closure",
    "coaching": "Coaching and Team Development",
}
STRONG, DEVELOPING, NEEDS_COACHING = "Strong", "Developing", "Needs Coaching"

# Downtime Reason, as first seeded: the names the Shift Report's list had, so
# what was saved before is still a reason; (name, category, planned)
DOWNTIME_CATEGORIES = ("Mechanical", "Electrical", "Utilities", "Materials", "Planning", "People", "Changeover",
                       "Maintenance", "Other")
DOWNTIME_SEED = (
    ("Mechanical Breakdown", "Mechanical", 0),
    ("Electrical Breakdown", "Electrical", 0),
    ("Power Outage", "Utilities", 0),
    ("No Raw Material", "Materials", 0),
    ("No Order", "Planning", 0),
    ("No Operator", "People", 0),
    ("Changeover", "Changeover", 0),
    ("Planned Maintenance", "Maintenance", 1),
    ("Other", "Other", 0),
)
DOWNTIME_REASONS = tuple(name for name, _category, _planned in DOWNTIME_SEED)
NO_REASON = "No Reason Given"

# the people on a shift, as the clock has them
PRESENT, HALF_DAY, WORK_FROM_HOME = "Present", "Half Day", "Work From Home"
ON_LEAVE, ABSENT, NOT_MARKED = "On Leave", "Absent", "Not Marked"
CREW_STATUSES = (PRESENT, HALF_DAY, WORK_FROM_HOME, ON_LEAVE, ABSENT, NOT_MARKED)
AT_WORK = (PRESENT, HALF_DAY, WORK_FROM_HOME)
PERMANENT, CASUAL = "Permanent", "Casual"
EMPLOYMENTS = (PERMANENT, CASUAL)

# the dated roster
SUPERVISOR, PRODUCTION_OFFICER = "Supervisor", "Production Officer"
ROSTER_ROLES = (SUPERVISOR, PRODUCTION_OFFICER)

# a section's standards, dated (Section Standard); the Work Section's own
# fields of the same names show the one in force today
STANDARD_FIELDS = ("target_per_shift", "crew_per_shift", "machines", "approved_establishment",
                   "labour_budget_per_unit", "labour_rate", "overtime_rate", "waste_limit", "complaint_limit")
STANDARD_LABELS = {
    "target_per_shift": "Target per Shift", "crew_per_shift": "Crew per Shift", "machines": "Machines",
    "approved_establishment": "Approved Establishment", "labour_budget_per_unit": "Labour Budget per Unit",
    "labour_rate": "Labour Cost per Person-Shift", "overtime_rate": "Overtime Cost per Hour",
    "waste_limit": "Waste Limit per Week", "complaint_limit": "Complaint Limit per Week",
}

# ── Discipline ────────────────────────────────────────────────────────
NEGLIGENCE, MISCONDUCT = "Negligence", "Deliberate Misconduct"
INADEQUATE_SUPERVISION = "Inadequate Supervision"
CAUSES = (
    ("Operational Mistake", "Coaching on the job and an SOP refresher. No sanction."),
    ("Skills Gap", "Retraining and a competency reassessment. No sanction."),
    (NEGLIGENCE, "Disciplinary route, after investigation and a hearing."),
    (MISCONDUCT, "Disciplinary route, after investigation and a hearing."),
    ("System or Process Failure", "Fix the process or SOP. No sanction on anyone."),
    ("Unclear Instructions", "Clarify the instructions and brief the supervisor. No sanction."),
    (INADEQUATE_SUPERVISION, "Coach the supervisor. No sanction on the employee."),
)
CAUSE_NAMES = tuple(name for name, _route in CAUSES)
ROUTES = dict(CAUSES)
CONDUCT_CAUSES = (NEGLIGENCE, MISCONDUCT)
PROCESS_CAUSES = ("System or Process Failure", "Unclear Instructions", INADEQUATE_SUPERVISION)
GROSS = "Gross"
SANCTIONED = "Sanctioned"
GRIEVANCE_DONE = ("Resolved", "Closed", "Invalid")
CASE_TYPES = ("Disciplinary", "Grievance", "Attendance", "Safety")
CASE_CLOSED = ("Closed", "Cancelled")
CASE_DECIDING = ("Charge Issued", "Hearing Scheduled")
# the tracker's flags
REPEAT, OVERDUE, DECISION_DUE = "Repeat", "Overdue", "Decision Due"
TRACKER_VIEWS = ("Employees with Repeat Cases", "Cases with Flags", "By Section", "By Cause", "By Case Type",
                 "By Shift", "By Employment", "By Supervisor")
TRACKER_KEYS = {"By Section": "work_section", "By Cause": "cause", "By Case Type": "case_type", "By Shift": "shift",
                "By Employment": "employment", "By Supervisor": "supervisor_on_shift"}

# ── People Log ────────────────────────────────────────────────────────
TOOLBOX, COACHING, RECOGNITION = "Toolbox Talk", "Operator Coaching", "Recognition"
SUGGESTION, IMPLEMENTED = "Employee Suggestion", "Suggestion Implemented"
SAFETY_TRAINING, PULSE = "Safety Training", "Pulse Survey"
COACHING_RECEIVED, LEADERSHIP = "Supervisor Coaching Received", "Leadership Development"
LOG_TYPES = (TOOLBOX, COACHING, RECOGNITION, SUGGESTION, IMPLEMENTED, SAFETY_TRAINING, COACHING_RECEIVED,
             LEADERSHIP, PULSE, "HR Observation", "Exit Interview")
COACHING_TYPES = (TOOLBOX, COACHING, RECOGNITION)
DEVELOPMENT_TYPES = (COACHING_RECEIVED, LEADERSHIP)

# ── HR Intervention ───────────────────────────────────────────────────
SOURCES = ("HR Intervention", "Supervisor Corrective Action")
INTERVENTIONS = ("Capacity and Deployment Review", "Competency and Work Allocation Review",
                 "Targeted Coaching and Reassessment", "Attendance Review and Engagement",
                 "Safety Accountability and Refresher", "Leadership and Relations Review", "Retention Risk Review",
                 "Supervisory Effectiveness Review", "Process or SOP Correction", "Other")
OPEN, IN_PROGRESS, COMPLETED, CLOSED = "Open", "In Progress", "Completed", "Closed"
INTERVENTION_STATUSES = (OPEN, IN_PROGRESS, COMPLETED, CLOSED)
DONE = (COMPLETED, CLOSED)
HIGHER, LOWER = "Higher", "Lower"
KPIS = (
    ("Attendance %", HIGHER), ("Unauthorised Absence", LOWER), ("Overtime % of Labour Cost", LOWER),
    ("Overtime Hours", LOWER), ("Labour Cost per Unit", LOWER), ("Output per Person-Shift", HIGHER),
    ("PPE Compliance %", HIGHER), ("Safety Incidents", LOWER), ("Waste Value", LOWER), ("Complaint Value", LOWER),
    ("Training Coverage %", HIGHER), ("Repeat Incidents", LOWER), ("Open Grievances", LOWER),
    ("Supervisor People Score", HIGHER), ("Turnover %", LOWER), ("Pulse Score %", HIGHER),
)
KPI_NAMES = tuple(name for name, _better in KPIS)
KPI_DIRECTION = dict(KPIS)
IMPROVED, WORSE, NO_CHANGE = "Improved", "Worse", "No Change"
AUTO, MANUAL = "Auto", "Manual"
READING_SOURCES = (AUTO, MANUAL)
SIGNAL_SOURCES = ("Manual", "Section Signals", "Labour Cost Flag", "Red Flag", "Shift Score", "Repeat Cases")

# ── Plant Order ───────────────────────────────────────────────────────
ORDER_STATUSES = ("Open", "Running", "Completed", "Cancelled")
FEASIBLE, MARGINAL, NOT_FEASIBLE = "Feasible", "Marginal", "Not Feasible"
NO_OUTPUT, SET_BUDGET = "No Output Yet", "Set Budget"

# ── Labour cost flags (the workbook's Labour Cost sheet) ──────────────
OT_UP, OVER_BUDGET, UNAUTHORISED, FATIGUE = ("Overtime Up, Output Not", "Over Budget", "Unauthorised Absence",
                                             "Fatigue Risk")
LABOUR_FLAGS = (OT_UP, OVER_BUDGET, UNAUTHORISED, FATIGUE)
OT_RISE, OUTPUT_RISE, BUDGET_OVER = 0.10, 0.02, 0.10

# ── Section signals (the workbook's HR Excellence by section) ─────────
SIGNALS = (
    ("attendance", "Attendance below target"),
    ("unauthorised", "Unauthorised absence over the ceiling"),
    ("overtime", "Overtime over the ceiling"),
    ("ppe", "PPE below target"),
    ("competency", "Competency below target"),
    ("grievances", "Open grievances"),
    ("exits", "Exits in the period"),
    ("overstaffed", "Staffed over the band"),
)
SIGNAL_LABELS = dict(SIGNALS)
HEAT_COLUMNS = (
    ("headcount", "Head Count"), ("establishment", "Establishment"), ("variance", "Variance"),
    ("deployment", "Deployment"), ("attendance", "Attendance"), ("unauthorised", "Unauthorised Absence"),
    ("ot_share", "Overtime % of Labour"), ("budget_variance", "Labour against Budget"),
    ("output_per_person", "Output per Person-Shift"), ("ppe", "PPE"), ("competency", "Competency Coverage"),
    ("cases", "Cases"), ("open_grievances", "Open Grievances"), ("exits", "Exits"),
)

# ── Settings ──────────────────────────────────────────────────────────
WEIGHT_GROUPS = (
    ("Shift score", tuple("weight_" + key for key in FACTOR_KEYS)),
    ("HR Excellence", tuple("pillar_" + key for key in PILLAR_KEYS)),
    ("Supervisor", tuple("sup_" + key for key in SUPERVISOR_KEYS)),
)
DEFAULTS = {
    "weight_output": 25, "weight_waste": 15, "weight_complaints": 10, "weight_uptime": 12,
    "weight_attendance": 8, "weight_safety": 10, "weight_housekeeping": 8, "weight_ppe": 12,
    "pillar_planning": 15, "pillar_productivity": 20, "pillar_attendance": 15, "pillar_skills": 15,
    "pillar_supervision": 15, "pillar_safety": 10, "pillar_relations": 5, "pillar_interventions": 5,
    "sup_reporting": 15, "sup_attendance": 15, "sup_ppe": 15, "sup_safety": 15, "sup_housekeeping": 10,
    "sup_conduct": 10, "sup_closure": 10, "sup_coaching": 10,
    "green_from": 90, "amber_from": 75,
    "shift_hours": 12, "shifts_per_week": 12, "safety_penalty": 25, "conduct_penalty": 25,
    "waste_limit": 1000000, "complaint_limit": 1000000,
    "paid_days": 26, "ot_base_hours": 8, "ot_multiplier": 1.5,
    "lookback_months": 12, "penalty_limit_days": 15, "suspension_cap_days": 15, "suspension_window_days": 183,
    "case_days": 14,
    "attendance_target": 95, "unauthorised_ceiling": 1, "overtime_ceiling": 8, "fatigue_ot": 1.5, "ppe_target": 98,
    "staffing_low": 90, "staffing_high": 110, "coverage_target": 80, "closure_target": 90, "coaching_per_week": 1,
    "pulse_target": 70, "turnover_ceiling": 2, "red_flag_safety": 1, "reporting_target": 95,
    "housekeeping_target": 85, "budget_percent": 12, "marginal_band": 10, "hide_names": 0, "send_brief": 1,
}
# typed as percentages, used as fractions
PERCENT_KEYS = ("attendance_target", "unauthorised_ceiling", "overtime_ceiling", "ppe_target", "staffing_low",
                "staffing_high", "coverage_target", "closure_target", "pulse_target", "turnover_ceiling",
                "reporting_target", "housekeeping_target", "budget_percent", "marginal_band")


def settings_from(stored=None):
    """The settings with every value in place: a value never saved takes its
    default; percentages become fractions."""
    stored = stored or {}
    s = {}
    for key, default in DEFAULTS.items():
        value = stored.get(key)
        s[key] = default if value in (None, "") else _num(value)
    for key in PERCENT_KEYS:
        s[key] = s[key] / 100.0
    return s


def settings_errors(stored):
    """Problems with the settings as typed, as user-facing messages."""
    s = dict(DEFAULTS)
    s.update({key: value for key, value in (stored or {}).items() if key in DEFAULTS and value not in (None, "")})
    errors = []
    for label, keys in WEIGHT_GROUPS:
        if any(_num(s[key]) < 0 for key in keys):
            errors.append("The {0} weights cannot be negative.".format(label))
        total = sum(_num(s[key]) for key in keys)
        if round(total, 6) != 100:
            errors.append("The {0} weights total {1}, not 100.".format(label, _plain(total)))
    if not _num(s["amber_from"]) < _num(s["green_from"]) <= 100:
        errors.append("Green must start above Amber, and at most 100.")
    if not _num(s["staffing_low"]) < _num(s["staffing_high"]):
        errors.append("The staffing band's low end must be below its high end.")
    for key, label in (("shift_hours", "Hours per Shift"), ("shifts_per_week", "Shifts per Section per Week"),
                       ("paid_days", "Paid Days per Month"), ("ot_base_hours", "Normal Hours per Day")):
        if _num(s[key]) <= 0:
            errors.append("{0} must be more than 0.".format(label))
    if int(_num(s["shifts_per_week"])) > 14:
        errors.append("A section works at most 14 shifts a week.")
    if not 0 <= _num(s["budget_percent"]) <= 100:
        errors.append("The default labour and loss budget is a share of the order value, from 0 to 100.")
    if _num(s["marginal_band"]) < 0:
        errors.append("The marginal band cannot be negative.")
    return errors


# ── Weeks and periods ─────────────────────────────────────────────────
WEEK, MONTH, QUARTER = "Week", "Month", "Quarter"
PERIOD_TYPES = (WEEK, MONTH, QUARTER)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
QUARTERS = ("Q1", "Q2", "Q3", "Q4")


def first_monday(year):
    """Week 1 starts on the year's first Monday, as on the plant's dashboards
    (5 January 2026)."""
    day = datetime.date(int(year), 1, 1)
    return day + datetime.timedelta(days=(7 - day.weekday()) % 7)


def week_of(day):
    """(year, week number): days before the year's first Monday belong to the
    year before's last week."""
    day = _date(day)
    start = first_monday(day.year)
    year = day.year
    if day < start:
        year -= 1
        start = first_monday(year)
    return year, (day - start).days // 7 + 1


def week_label(day):
    year, number = week_of(day)
    return "%d-W%02d" % (year, number)


def week_start(day):
    """The Monday a day's week starts on."""
    day = _date(day)
    return day - datetime.timedelta(days=day.weekday())


def period_bounds(kind, year, value):
    """(first day, last day) of a week, month or quarter of a year."""
    year = int(year)
    if kind == WEEK:
        start = first_monday(year) + datetime.timedelta(days=7 * (int(value) - 1))
        return start, start + datetime.timedelta(days=6)
    if kind == MONTH:
        month = MONTHS.index(value) + 1 if value in MONTHS else int(value)
        return datetime.date(year, month, 1), _month_end(year, month)
    quarter = QUARTERS.index(value) + 1 if value in QUARTERS else int(value)
    return datetime.date(year, quarter * 3 - 2, 1), _month_end(year, quarter * 3)


def period_now(kind, today):
    """(year, value) of the week, month or quarter `today` is in."""
    today = _date(today)
    if kind == WEEK:
        return week_of(today)
    if kind == QUARTER:
        return today.year, QUARTERS[(today.month - 1) // 3]
    return today.year, MONTHS[today.month - 1]


def last_weeks(today, count=13):
    """The last `count` whole weeks before today's: [(label, first day, last
    day)], oldest first."""
    monday = week_start(today)
    found = []
    for back in range(count, 0, -1):
        start = monday - datetime.timedelta(days=7 * back)
        found.append((week_label(start), start, start + datetime.timedelta(days=6)))
    return found


def last_months(today, count=12):
    """The last `count` months up to and with today's: [(label, first day,
    last day)], oldest first."""
    today = _date(today)
    found = []
    for back in range(count - 1, -1, -1):
        first = add_months(today.replace(day=1), -back)
        found.append(("%s %d" % (MONTHS[first.month - 1][:3], first.year), first,
                      _month_end(first.year, first.month)))
    return found


def working_days(start, end, days_per_week=6):
    """The days in [start, end] the plant works: Monday on, `days_per_week` a
    week."""
    start, end = _date(start), _date(end)
    if not start or not end or end < start:
        return 0
    count, day = 0, start
    while day <= end:
        if day.weekday() < days_per_week:
            count += 1
        day += datetime.timedelta(days=1)
    return count


def rag(score, s):
    if score is None:
        return NO_DATA
    if score >= s["green_from"]:
        return ON_TARGET
    if score >= s["amber_from"]:
        return ATTENTION
    return CRITICAL


# ── A section's standards and roster, by date ─────────────────────────
def standard_on(rows, day, fallback=None):
    """The standard in force on a day: the latest row from that day or before,
    else the earliest row, else the fallback (the section's own fields)."""
    day = _date(day)
    dated = sorted((row for row in rows or () if _date(row.get("effective_from"))),
                   key=lambda row: _date(row.get("effective_from")))
    chosen = None
    for row in dated:
        if day is None or _date(row.get("effective_from")) <= day:
            chosen = row
    if chosen is None and dated:
        chosen = dated[0]
    source = chosen if chosen is not None else (fallback or {})
    found = {field: source.get(field) for field in STANDARD_FIELDS}
    found["effective_from"] = chosen.get("effective_from") if chosen is not None else None
    return found


def standard_errors(rows):
    errors, seen = [], set()
    for row in rows or ():
        day = _date(row.get("effective_from"))
        if not day:
            errors.append("Give each standard the date it applies from.")
            continue
        if day in seen:
            errors.append("Two standards apply from {0}.".format(day.isoformat()))
        seen.add(day)
        for field in STANDARD_FIELDS:
            if _num(row.get(field)) < 0:
                errors.append("{0} cannot be negative.".format(STANDARD_LABELS[field]))
    return errors


def standards_after_edit(rows, typed, today):
    """The standards after the section's own figures were changed: a change to
    what is in force today is kept as a standard from today, so the history
    stays. Returns (rows, changed). A section with no standards yet gets its
    first from what was typed."""
    rows = [dict(row) for row in rows or ()]
    today = _date(today)
    if not rows:
        if any(_num(typed.get(field)) for field in STANDARD_FIELDS):
            first = {field: typed.get(field) for field in STANDARD_FIELDS}
            first["effective_from"] = today
            return [first], True
        return rows, False
    current = standard_on(rows, today)
    changes = {field: typed.get(field) for field in STANDARD_FIELDS
               if typed.get(field) is not None and _num(typed.get(field)) != _num(current.get(field))}
    if not changes:
        return rows, False
    for row in rows:
        if _date(row.get("effective_from")) == today:
            row.update(changes)
            return rows, True
    fresh = {field: current.get(field) for field in STANDARD_FIELDS}
    fresh.update(changes)
    fresh["effective_from"] = today
    rows.append(fresh)
    return rows, True


def _covers(row, day):
    start, end = _date(row.get("from_date")), _date(row.get("to_date"))
    return bool(start) and start <= day and (end is None or day <= end)


def rostered(rows, day, shift=None, role=SUPERVISOR):
    """The employees on the roster on a day, for a role and a shift (a Both row
    covers both shifts), in the roster's order."""
    day = _date(day)
    found = []
    for row in rows or ():
        if (row.get("role") or SUPERVISOR) != role or not day or not _covers(row, day):
            continue
        if shift and row.get("shift") not in (shift, BOTH, None, ""):
            continue
        if row.get("employee") and row.get("employee") not in found:
            found.append(row.get("employee"))
    return found


def lead_on(rows, day, shift, role=SUPERVISOR):
    """Who leads a section's shift on a day: the first rostered on that shift,
    else the first rostered on any shift; None with nobody rostered."""
    found = rostered(rows, day, shift, role) or rostered(rows, day, None, role)
    return found[0] if found else None


def roster_windows(rows, start, end, role=SUPERVISOR):
    """The roster rows of a role that touch [start, end], each clipped to it:
    [{"employee", "shift", "from", "to"}]."""
    start, end = _date(start), _date(end)
    found = []
    for row in rows or ():
        if (row.get("role") or SUPERVISOR) != role:
            continue
        begin, finish = _date(row.get("from_date")), _date(row.get("to_date"))
        if not begin or begin > end or (finish and finish < start):
            continue
        found.append({"employee": row.get("employee"), "shift": row.get("shift") or BOTH,
                      "from": max(begin, start), "to": min(finish, end) if finish else end})
    return found


def roster_errors(rows):
    errors = []
    rows = list(rows or ())
    for index, row in enumerate(rows):
        start, end = _date(row.get("from_date")), _date(row.get("to_date"))
        if not start:
            errors.append("Give {0} the date they start on the roster.".format(row.get("employee") or "each person"))
            continue
        if end and end < start:
            errors.append("{0}'s roster ends before it starts.".format(row.get("employee")))
        for other in rows[index + 1:]:
            if (other.get("employee"), other.get("role") or SUPERVISOR) != (row.get("employee"),
                                                                             row.get("role") or SUPERVISOR):
                continue
            shifts = {row.get("shift") or BOTH, other.get("shift") or BOTH}
            if len(shifts) == 2 and BOTH not in shifts:
                continue
            o_start, o_end = _date(other.get("from_date")), _date(other.get("to_date"))
            if o_start and (end is None or o_start <= end) and (o_end is None or start <= o_end):
                errors.append("{0} is on the roster twice for the same days.".format(row.get("employee")))
    return errors


def section_errors(section):
    errors = []
    for field in STANDARD_FIELDS:
        if _num(section.get(field)) < 0:
            errors.append("{0} cannot be negative.".format(STANDARD_LABELS[field]))
    errors += standard_errors(section.get("standards"))
    errors += roster_errors(section.get("assignments"))
    return errors


# ── The crew from the clock ───────────────────────────────────────────
def shift_of(shift_type=None, start_time=None):
    """Day or Night for a Shift Type: by its name, else by its start (from
    17:00 to before 05:00 is night)."""
    name = (shift_type or "").lower()
    if "night" in name:
        return NIGHT
    if "day" in name:
        return DAY
    start = str(start_time or "")
    if start:
        try:
            hour = int(start.split(":")[0])
        except ValueError:
            hour = 8
        if hour >= 17 or hour < 5:
            return NIGHT
    return DAY


def day_rate_of(monthly, s):
    """A person's day: their month's pay over the paid days."""
    return round(_num(monthly) / _num(s["paid_days"]), 2) if _num(s["paid_days"]) else 0.0


def overtime_rate_of(day_rate, s):
    """An hour of overtime: the day over the normal hours, at the multiplier."""
    if not _num(s["ot_base_hours"]):
        return 0.0
    return round(_num(day_rate) / _num(s["ot_base_hours"]) * _num(s["ot_multiplier"]), 2)


def crew_line(facts, day_rate, s):
    """One person rostered on a shift, from their attendance, their overtime
    and their day's pay. facts: status (the Attendance's, None when not
    marked), leave_type, paid_leave, late, early, late_minutes,
    early_minutes, attendance_ot_hours, ot_hours (an overtime request's, None
    when there is none), ot_amount (its cost, 0 when not costed)."""
    status = facts.get("status") or NOT_MARKED
    leave = bool(facts.get("leave_type")) or status == ON_LEAVE
    at_work = status in AT_WORK
    unauthorised = int(status in (ABSENT, NOT_MARKED) and not leave)
    rate = _num(day_rate)
    if facts.get("ot_hours") is not None:
        ot_hours = _num(facts.get("ot_hours"))
    else:
        ot_hours = _num(facts.get("attendance_ot_hours"))
    ot_cost = _num(facts.get("ot_amount")) or round(ot_hours * overtime_rate_of(rate, s), 2)
    paid_leave = facts.get("paid_leave")
    paid_leave = True if paid_leave is None else bool(paid_leave)
    return {
        "status": status, "on_shift": int(at_work), "unauthorised": unauthorised,
        "not_marked": int(status == NOT_MARKED),
        "late": int(bool(facts.get("late")) or _num(facts.get("late_minutes")) > 0) if at_work else 0,
        "early": int(bool(facts.get("early")) or _num(facts.get("early_minutes")) > 0) if at_work else 0,
        "late_minutes": int(_num(facts.get("late_minutes"))) if at_work else 0,
        "early_minutes": int(_num(facts.get("early_minutes"))) if at_work else 0,
        "ot_hours": round(ot_hours, 2), "ot_cost": round(ot_cost, 2), "day_rate": rate,
        "day_cost": rate if at_work else 0.0,
        "absence_cost": rate if (not at_work and leave and paid_leave) else 0.0,
    }


def crew_totals(rows):
    """The sums a shift takes from its crew, each with the names behind it."""
    t = {"planned": 0, "on_shift": 0, "absent": 0, "unauthorised": 0, "not_marked": 0, "late": 0, "early": 0,
         "ot_hours": 0.0, "ot_cost": 0.0, "regular": 0.0, "absence_cost": 0.0, "no_ppe": 0, "incidents": 0,
         "near_misses": 0}
    for row in rows or ():
        t["planned"] += 1
        at_work = row.get("status") in AT_WORK
        t["on_shift"] += int(at_work)
        t["absent"] += int(not at_work)
        t["unauthorised"] += int(_num(row.get("unauthorised")))
        t["not_marked"] += int(row.get("status") in (NOT_MARKED, None, ""))
        t["late"] += int(at_work and (_num(row.get("late_minutes")) > 0 or bool(_num(row.get("late")))))
        t["early"] += int(at_work and (_num(row.get("early_minutes")) > 0 or bool(_num(row.get("early")))))
        t["ot_hours"] += _num(row.get("ot_hours"))
        t["ot_cost"] += _num(row.get("ot_cost"))
        t["regular"] += _num(row.get("day_cost"))
        t["absence_cost"] += _num(row.get("absence_cost"))
        t["no_ppe"] += int(at_work and bool(_num(row.get("no_ppe"))))
        t["incidents"] += int(_num(row.get("incidents")))
        t["near_misses"] += int(_num(row.get("near_misses")))
    return t


def incident_shift(incident_on, day):
    """Which shift of `day` an incident logged at `incident_on` falls in: Day
    on the day itself before 19:00, Night from 19:00 or before 07:00 the
    morning after; None for another day."""
    when = _datetime(incident_on)
    day = _date(day)
    if not when or not day:
        return None
    if when.date() == day:
        return NIGHT if when.hour >= 19 else DAY
    if when.date() == day + datetime.timedelta(days=1) and when.hour < 7:
        return NIGHT
    return None


# ── One shift ─────────────────────────────────────────────────────────
def entry_errors(entry):
    """Problems with a shift as typed."""
    errors = []
    machines, running = int(_num(entry.get("machines"))), entry.get("machines_running")
    if running not in (None, "") and int(_num(running)) > machines:
        errors.append("More machines running than the section has ({0}).".format(machines))
    on_shift = int(_num(entry.get("staff_on_shift")))
    if int(_num(entry.get("wearing_ppe"))) > on_shift:
        errors.append("More people wearing full PPE than on shift.")
    if int(_num(entry.get("unauthorised_absent"))) > max(int(_num(entry.get("staff_planned"))) - on_shift, 0):
        errors.append("More unauthorised absences than people absent (planned less on shift).")
    if _num(entry.get("housekeeping")) > 100:
        errors.append("Housekeeping is a percentage, at most 100.")
    if _num(entry.get("stop_hours")) and not entry.get("downtime_reason") and not entry.get("has_downtime_rows"):
        errors.append("Give the main downtime reason for the stopped hours.")
    for field, label in (("actual_output", "Output"), ("waste_qty", "Waste Quantity"), ("waste_value", "Waste Value"),
                         ("complaint_value", "Complaint Value"), ("stop_hours", "Stopped Hours"),
                         ("ot_hours", "Overtime Hours"), ("housekeeping", "Housekeeping")):
        if _num(entry.get(field)) < 0:
            errors.append("{0} cannot be negative.".format(label))
    return errors


def caps(standard, s):
    """(waste, complaint) limit for one shift: the section's weekly limits in
    force (else the settings') spread over the shifts of a week."""
    shifts = _num(s["shifts_per_week"]) or 1
    waste = _num((standard or {}).get("waste_limit")) or _num(s["waste_limit"])
    complaint = _num((standard or {}).get("complaint_limit")) or _num(s["complaint_limit"])
    return waste / shifts, complaint / shifts


def shift_figures(entry, standard, s, crew=None, downtime_minutes=None):
    """Everything one shift works out, from what was typed or came from the
    clock, its section's standard in force and the settings: the workbook's
    Daily Entry, column for column. `crew`: crew_totals() when the crew came
    from the clock (its people and pay then stand); `downtime_minutes`: the
    sum of its downtime events, when there are any."""
    standard = standard or {}
    hours = _num(s["shift_hours"])
    machines = int(_num(entry.get("machines")))
    running = entry.get("machines_running")
    running = machines if running in (None, "") else int(_num(running))
    actual, target = _num(entry.get("actual_output")), _num(entry.get("target"))
    planned, on_shift = int(_num(entry.get("staff_planned"))), int(_num(entry.get("staff_on_shift")))
    wearing, unauthorised = int(_num(entry.get("wearing_ppe"))), int(_num(entry.get("unauthorised_absent")))
    rate, ot_rate = _num(standard.get("labour_rate")), _num(standard.get("overtime_rate"))
    crew_size, budget_rate = int(_num(standard.get("crew_per_shift"))), _num(standard.get("labour_budget_per_unit"))

    machine_hours = machines * hours
    if downtime_minutes is not None:
        hours_lost = _num(downtime_minutes) / 60.0
    else:
        hours_lost = max(0, machines - running) * hours + _num(entry.get("stop_hours"))
    uptime = 1.0 if not machine_hours else max(0.0, 1 - hours_lost / machine_hours)
    achievement = actual / target if target else 0.0
    attendance = on_shift / float(planned) if planned else 0.0
    ppe = wearing / float(on_shift) if on_shift else 0.0
    absent = max(0, planned - on_shift)
    if crew and crew.get("planned"):
        regular, ot_cost, absence_cost = crew["regular"], crew["ot_cost"], crew["absence_cost"]
    else:
        regular = on_shift * rate
        ot_cost = _num(entry.get("ot_hours")) * ot_rate
        absence_cost = max(0, absent - unauthorised) * rate
    labour = regular + ot_cost
    waste_cap, complaint_cap = caps(standard, s)

    factors = {
        "output": min(100.0, achievement * 100),
        "waste": max(0.0, 100 * (1 - _num(entry.get("waste_value")) / waste_cap)) if waste_cap else 100.0,
        "complaints": max(0.0, 100 * (1 - _num(entry.get("complaint_value")) / complaint_cap)) if complaint_cap
        else 100.0,
        "uptime": uptime * 100,
        "attendance": min(100.0, attendance * 100),
        "safety": max(0.0, 100 - int(_num(entry.get("safety_incidents"))) * _num(s["safety_penalty"])),
        "housekeeping": min(100.0, _num(entry.get("housekeeping"))),
        "ppe": min(100.0, ppe * 100),
    }
    score = round(sum(_num(s["weight_" + key]) * factors[key] for key in FACTOR_KEYS) / 100.0, 1)
    weakest = min(FACTOR_KEYS, key=lambda key: (factors[key], FACTOR_KEYS.index(key)))
    return {
        "machines_running": running, "machine_hours": machine_hours, "hours_lost": round(hours_lost, 2),
        "uptime": uptime, "achievement": achievement, "attendance": attendance, "ppe_rate": ppe,
        "not_wearing": max(0, on_shift - wearing), "regular_labour": round(regular, 2), "ot_cost": round(ot_cost, 2),
        "labour_cost": round(labour, 2), "labour_per_unit": labour / actual if actual else None,
        "machine_use": (running / float(machines)) if machines else None,
        "output_per_person": actual / on_shift if actual and on_shift else None,
        "absent": absent, "required_crew": crew_size, "adequacy": on_shift / float(crew_size) if crew_size else None,
        "labour_budget": actual * budget_rate, "absence_cost": round(absence_cost, 2),
        "waste_cap": waste_cap, "complaint_cap": complaint_cap,
        "factors": factors, "score": score, "status": rag(score, s), "weakest": weakest,
        "weakest_action": FACTOR_ACTIONS[weakest],
    }


def labour_rates(gross, heads, s):
    """(a person-shift's labour cost, an overtime hour's): a month's pay over
    the people paid and the paid days; overtime at the multiplier."""
    if not heads or not _num(s["paid_days"]):
        return 0.0, 0.0
    rate = _num(gross) / float(heads) / _num(s["paid_days"])
    return round(rate, 2), round(rate / _num(s["ot_base_hours"]) * _num(s["ot_multiplier"]), 2)


def allocate(lines, labour, ot_hours, ot_cost, complaints):
    """A shift's labour, overtime and complaints shared over its output lines
    in proportion to what each made (equally when nothing was made):
    [{"labour", "ot_hours", "ot_cost", "complaints"}], one a line."""
    weights = [max(0.0, _num(line.get("good_qty"))) for line in lines or ()]
    total = sum(weights)
    if not weights:
        return []
    shares = [weight / total for weight in weights] if total else [1.0 / len(weights)] * len(weights)
    return [{"labour": round(_num(labour) * share, 2), "ot_hours": round(_num(ot_hours) * share, 2),
             "ot_cost": round(_num(ot_cost) * share, 2), "complaints": round(_num(complaints) * share, 2)}
            for share in shares]


# ── What a submitted shift adds to its section's day ──────────────────
# the Section Day Summary's figures, summed by GROUP BY for any period
SUMMARY_FIELDS = (
    "shifts", "target", "actual_output", "machines", "machines_running", "machine_hours", "hours_lost",
    "waste_qty", "waste_value", "complaint_value", "waste_cap", "complaint_cap", "safety_incidents", "near_misses",
    "housekeeping", "staff_planned", "staff_on_shift", "absent", "unauthorised_absent", "not_marked",
    "late_arrivals", "early_departures", "wearing_ppe", "not_wearing", "ot_hours", "ot_cost", "regular_labour",
    "labour_cost", "budgeted_labour", "labour_budget", "absence_cost", "required_crew", "below_band", "shift_score",
) + tuple("factor_" + key for key in FACTOR_KEYS)
# the names the first build's readers (and the LMS's impact measures) use
LEGACY = {"count": "shifts", "actual": "actual_output", "waste": "waste_value", "complaints": "complaint_value",
          "incidents": "safety_incidents", "planned": "staff_planned", "on_shift": "staff_on_shift",
          "unauthorised": "unauthorised_absent", "late": "late_arrivals", "early": "early_departures",
          "wearing": "wearing_ppe", "labour": "labour_cost", "budget": "labour_budget", "required": "required_crew"}


def day_summary(entry, figures, s):
    """What one submitted shift adds to its section's day."""
    on_shift, required = _num(entry.get("staff_on_shift")), _num(figures.get("required_crew"))
    budget = _num(figures.get("labour_budget"))
    row = {
        "shifts": 1, "target": _num(entry.get("target")), "actual_output": _num(entry.get("actual_output")),
        "machines": _num(entry.get("machines")), "machines_running": _num(figures.get("machines_running")),
        "machine_hours": _num(figures.get("machine_hours")), "hours_lost": _num(figures.get("hours_lost")),
        "waste_qty": _num(entry.get("waste_qty")), "waste_value": _num(entry.get("waste_value")),
        "complaint_value": _num(entry.get("complaint_value")), "waste_cap": _num(figures.get("waste_cap")),
        "complaint_cap": _num(figures.get("complaint_cap")),
        "safety_incidents": _num(entry.get("safety_incidents")), "near_misses": _num(entry.get("near_misses")),
        "housekeeping": _num(entry.get("housekeeping")), "staff_planned": _num(entry.get("staff_planned")),
        "staff_on_shift": on_shift, "absent": _num(figures.get("absent")),
        "unauthorised_absent": _num(entry.get("unauthorised_absent")), "not_marked": _num(entry.get("not_marked")),
        "late_arrivals": _num(entry.get("late_arrivals")), "early_departures": _num(entry.get("early_departures")),
        "wearing_ppe": _num(entry.get("wearing_ppe")), "not_wearing": _num(figures.get("not_wearing")),
        "ot_hours": _num(entry.get("ot_hours")), "ot_cost": _num(figures.get("ot_cost")),
        "regular_labour": _num(figures.get("regular_labour")), "labour_cost": _num(figures.get("labour_cost")),
        "budgeted_labour": _num(figures.get("labour_cost")) if budget > 0 else 0.0, "labour_budget": budget,
        "absence_cost": _num(figures.get("absence_cost")), "required_crew": required,
        "below_band": int(bool(required) and on_shift / required < s["staffing_low"]),
        "shift_score": _num(figures.get("score")),
    }
    for key in FACTOR_KEYS:
        row["factor_" + key] = round(_num(figures["factors"][key]), 4)
    return row


def totals(rows, s=None):
    """The sums over summary rows (or GROUP BY results with the same names),
    with the first build's names beside them."""
    t = {field: 0.0 for field in SUMMARY_FIELDS}
    t["by_unit"] = {}
    for row in rows or ():
        for field in SUMMARY_FIELDS:
            t[field] += _num(row.get(field))
        unit = row.get("unit")
        if unit is not None:
            made = t["by_unit"].setdefault(unit, {"actual": 0.0, "on_shift": 0.0, "labour": 0.0, "target": 0.0})
            made["actual"] += _num(row.get("actual_output"))
            made["on_shift"] += _num(row.get("staff_on_shift"))
            made["labour"] += _num(row.get("labour_cost"))
            made["target"] += _num(row.get("target"))
    return _finish(t, s)


def add_totals(*parts):
    """Totals added together."""
    found = {field: 0.0 for field in SUMMARY_FIELDS}
    found["by_unit"] = {}
    for part in parts:
        for field in SUMMARY_FIELDS:
            found[field] += _num((part or {}).get(field))
        for unit, made in ((part or {}).get("by_unit") or {}).items():
            mine = found["by_unit"].setdefault(unit, {"actual": 0.0, "on_shift": 0.0, "labour": 0.0, "target": 0.0})
            for key in mine:
                mine[key] += _num(made.get(key))
    return _finish(found, next((part.get("_s") for part in parts if part and part.get("_s")), None))


def _finish(t, s):
    t["shifts"] = int(t["shifts"])
    for old, new in LEGACY.items():
        t[old] = t[new]
    t["money_lost"] = t["waste_value"] + t["complaint_value"]
    t["_s"] = s
    return t


def ratio(part, whole):
    return _num(part) / float(whole) if _num(whole) else None


def period_scores(t, s):
    """A period's score from its totals, as the workbook's Weekly Summary
    (column V) and Supervisor Dashboard (column F) work it out: each factor
    from the period's sums, not the average of its shifts' scores."""
    count = t.get("shifts") or 0
    if not count:
        return {"score": None, "exact": None, "status": NO_DATA, "factors": {key: None for key in FACTOR_KEYS},
                "weakest": None, "weakest_action": ""}
    target, actual = _num(t.get("target")), _num(t.get("actual_output"))
    machine_hours, lost = _num(t.get("machine_hours")), _num(t.get("hours_lost"))
    planned, on_shift = _num(t.get("staff_planned")), _num(t.get("staff_on_shift"))
    waste_cap, complaint_cap = _num(t.get("waste_cap")), _num(t.get("complaint_cap"))
    factors = {
        "output": min(100.0, (actual / target if target else 0.0) * 100),
        "waste": max(0.0, 100 * (1 - _num(t.get("waste_value")) / waste_cap)) if waste_cap else 100.0,
        "complaints": max(0.0, 100 * (1 - _num(t.get("complaint_value")) / complaint_cap)) if complaint_cap
        else 100.0,
        "uptime": (1.0 if not machine_hours else max(0.0, 1 - lost / machine_hours)) * 100,
        "attendance": min(100.0, (on_shift / planned if planned else 0.0) * 100),
        "safety": max(0.0, 100 - _num(t.get("safety_incidents")) * _num(s["safety_penalty"])),
        "housekeeping": min(100.0, _num(t.get("housekeeping")) / count),
        "ppe": min(100.0, (_num(t.get("wearing_ppe")) / on_shift if on_shift else 0.0) * 100),
    }
    score = sum(_num(s["weight_" + key]) * factors[key] for key in FACTOR_KEYS) / 100.0
    weakest = min(FACTOR_KEYS, key=lambda key: (factors[key], FACTOR_KEYS.index(key)))
    return {"score": round(score, 1), "exact": score, "status": rag(round(score, 1), s), "factors": factors,
            "weakest": weakest, "weakest_action": FACTOR_ACTIONS[weakest]}


def averages(t, s=None):
    """The ratios of a period's totals: its score from them (period_scores),
    rates as fractions, and the average of its shifts' own factors (the
    workbook's safety leadership and housekeeping read those)."""
    s = s or t.get("_s") or settings_from({})
    count = t.get("shifts") or 0
    scored = period_scores(t, s)
    shift_factors = {key: (_num(t.get("factor_" + key)) / count if count else None) for key in FACTOR_KEYS}
    planned, on_shift = _num(t.get("staff_planned")), _num(t.get("staff_on_shift"))
    return {
        "score": scored["score"], "status": scored["status"], "factors": scored["factors"],
        "weakest": scored["weakest"], "weakest_action": scored["weakest_action"],
        "shift_factors": shift_factors,
        "achievement": ratio(t.get("actual_output"), t.get("target")),
        "uptime": (1 - _num(t.get("hours_lost")) / _num(t.get("machine_hours"))) if _num(t.get("machine_hours"))
        else (1.0 if count else None),
        "attendance": ratio(on_shift, planned),
        "unauthorised": ratio(t.get("unauthorised_absent"), planned),
        "ppe": ratio(t.get("wearing_ppe"), on_shift),
        "deployment": ratio(on_shift, t.get("required_crew")),
        "ot_share": ratio(t.get("ot_cost"), t.get("labour_cost")),
        "budget_variance": (_num(t.get("budgeted_labour")) / _num(t.get("labour_budget")) - 1)
        if _num(t.get("labour_budget")) else None,
        "fatigue": ratio(t.get("ot_hours"), on_shift),
        "housekeeping": (_num(t.get("housekeeping")) / count / 100.0) if count else None,
        "money_lost": _num(t.get("waste_value")) + _num(t.get("complaint_value")),
        "labour_per_unit": ratio(t.get("labour_cost"), t.get("actual_output")),
        "output_per_person": ratio(t.get("actual_output"), on_shift),
        "machine_use": ratio(t.get("machines_running"), t.get("machines")),
    }


def plant_score(section_scores):
    """A plant's score: the average of its sections' scores (the workbook's
    Dashboard)."""
    scores = [score for score in section_scores if score is not None]
    return round(sum(scores) / len(scores), 1) if scores else None


def downtime_breakdown(rows):
    """Downtime by reason: rows [{"reason", "category", "planned", "minutes",
    "shifts"}] -> sorted, each with its hours, its share of the hours lost
    and the shifts it hit."""
    total = sum(_num(row.get("minutes")) for row in rows or ())
    found = []
    for row in rows or ():
        minutes = _num(row.get("minutes"))
        if minutes <= 0:
            continue
        found.append({"reason": row.get("reason") or NO_REASON, "category": row.get("category") or "",
                      "planned": int(_num(row.get("planned"))), "hours": round(minutes / 60.0, 2),
                      "share": minutes / total if total else 0.0, "shifts": int(_num(row.get("shifts")))})
    return sorted(found, key=lambda row: (-row["hours"], row["reason"]))


# ── Parts of the HR Excellence and supervisor scores ──────────────────
def attendance_part(attendance, unauthorised, s):
    """Attendance against its target, less ten points for each point of
    unauthorised absence over its ceiling."""
    if attendance is None:
        return None
    over = max(0.0, (unauthorised or 0.0) - s["unauthorised_ceiling"])
    return max(0.0, min(100.0, attendance / s["attendance_target"] * 100) - over * 1000)


def deployment_part(deployment, s):
    """100 inside the staffing band, four points off for each point outside."""
    if deployment is None:
        return None
    low, high = s["staffing_low"], s["staffing_high"]
    if low <= deployment <= high:
        return 100.0
    return max(0.0, 100 - min(abs(deployment - low), abs(deployment - high)) * 400)


def establishment_part(headcount, establishment):
    if not establishment:
        return None
    return max(0.0, 100 - abs(headcount / float(establishment) - 1) * 200)


def budget_part(variance):
    if variance is None:
        return None
    return 100.0 if variance <= 0 else max(0.0, 100 - variance * 200)


def overtime_part(share, s):
    if share is None:
        return None
    return 100.0 if share <= s["overtime_ceiling"] else max(0.0, 100 - (share - s["overtime_ceiling"]) * 500)


def fatigue_part(per_shift, s):
    if per_shift is None:
        return None
    return 100.0 if per_shift <= s["fatigue_ot"] else max(0.0, 100 - (per_shift - s["fatigue_ot"]) * 50)


def capped(value, target):
    if value is None or not target:
        return None
    return min(100.0, value / target * 100)


def closure_part(due, on_time):
    return 100.0 * on_time / due if due else None


def coaching_part(sessions, supervisors, weeks, s, has_shifts=True):
    if not has_shifts:
        return None
    wanted = max(1.0, s["coaching_per_week"] * max(1, supervisors) * max(weeks, 0))
    return min(100.0, sessions / wanted * 100)


def conduct_part(cases, s, has_shifts=True):
    """Twenty-five points off for each case put down to inadequate supervision."""
    if not has_shifts:
        return None
    return max(0.0, 100 - cases * _num(s["conduct_penalty"]))


def weighted(parts, weights):
    """The weighted average of the parts that have data, re-weighted: (score,
    the share of the weight that had data)."""
    have = [(parts[key], _num(weights.get(key))) for key in parts if parts[key] is not None]
    total = sum(weight for _score, weight in have)
    every = sum(_num(weights.get(key)) for key in parts)
    if not total:
        return None, 0.0
    return round(sum(score * weight for score, weight in have) / total, 1), (total / every if every else 0.0)


def _average(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 1) if values else None


def people_status(index, s):
    if index is None:
        return NO_DATA
    if index >= s["green_from"]:
        return STRONG
    if index >= s["amber_from"]:
        return DEVELOPING
    return NEEDS_COACHING


def supervisor_index(facts, s):
    """The supervisor's eight people-management parts, their index and the
    development focus. `facts`: "totals" (their shifts'), "due" and
    "reported" (shift rows due from them and entered; reported defaults to
    the shifts in the totals), "conduct_cases", "interventions_due",
    "interventions_on_time", "sessions", "supervisors", "weeks"."""
    t = facts["totals"]
    a = averages(t, s)
    has = bool(t.get("shifts"))
    due = facts.get("due") or 0
    reported = facts.get("reported")
    reported = t.get("shifts") if reported is None else reported
    parts = {
        "reporting": capped(min(reported, due), due) if due else None,
        "attendance": attendance_part(a["attendance"], a["unauthorised"], s),
        "ppe": capped(a["ppe"], s["ppe_target"]),
        "safety": a["shift_factors"]["safety"],
        "housekeeping": a["shift_factors"]["housekeeping"],
        "conduct": conduct_part(facts.get("conduct_cases") or 0, s, has),
        "closure": closure_part(facts.get("interventions_due") or 0, facts.get("interventions_on_time") or 0),
        "coaching": coaching_part(facts.get("sessions") or 0, facts.get("supervisors") or 1, facts.get("weeks") or 0,
                                  s, has),
    }
    index, share = weighted(parts, {key: s["sup_" + key] for key in SUPERVISOR_KEYS})
    have = [key for key in SUPERVISOR_KEYS if parts[key] is not None]
    weakest = min(have, key=lambda key: (parts[key], SUPERVISOR_KEYS.index(key))) if have else None
    return {"parts": parts, "index": index, "share": share, "status": rag(index, s),
            "band": people_status(index, s), "weakest_part": weakest,
            "focus": DEVELOPMENT_FOCUS.get(weakest, "") if weakest else ""}


def pillars(facts, s):
    """The HR Excellence scorecard for a period. `facts`:
      totals             the summaries' totals()
      headcount, establishment, direct_share
      coverage           (done, required) of the people's required training
      competency, critical  (competent, assessed) skills, all and critical
      due_reports, reported  shift rows due in the period so far, and entered
      conduct_cases      cases put down to inadequate supervision
      sessions, supervisors, weeks        coaching
      interventions_due, interventions_on_time, interventions_closed,
      interventions_improved, interventions_open_supervision,
      interventions_raised, interventions_completed, interventions_overdue,
      savings
      open_grievances, grievances_open_long, legal_flags, overdue_cases,
      cases, conduct_route, non_grievance_cases, coaching_route, repeats,
      days_to_resolve, pulse, exits, voluntary_exits, months,
      recognitions, suggestions, implemented, safety_trainings
    """
    t = facts["totals"]
    a = averages(t, s)
    has = bool(t.get("shifts"))
    supervision = supervisor_index({
        "totals": t, "due": facts.get("due_reports"), "reported": facts.get("reported"),
        "conduct_cases": facts.get("conduct_cases"), "interventions_due": facts.get("interventions_due"),
        "interventions_on_time": facts.get("interventions_on_time"), "sessions": facts.get("sessions"),
        "supervisors": facts.get("supervisors"), "weeks": facts.get("weeks")}, s)
    done, required = facts.get("coverage") or (0, 0)
    coverage = ratio(done, required)
    competent = ratio(*(facts.get("competency") or (0, 0)))
    critical = ratio(*(facts.get("critical") or (0, 0)))
    headcount, establishment = facts.get("headcount") or 0, facts.get("establishment") or 0
    interventions = facts.get("interventions_due") or 0
    closed = facts.get("interventions_closed") or 0
    effectiveness = None
    if interventions:
        improved = (facts.get("interventions_improved") or 0) / float(closed) if closed else 0.0
        effectiveness = 100 * (0.6 * (facts.get("interventions_on_time") or 0) / float(interventions) + 0.4 * improved)
    pulse = facts.get("pulse")
    relations = max(0.0, 100 - 10 * (facts.get("open_grievances") or 0) - 15 * (facts.get("legal_flags") or 0)
                    - 5 * (facts.get("overdue_cases") or 0))
    parts = {
        "planning": [deployment_part(a["deployment"], s), establishment_part(headcount, establishment)],
        "productivity": [budget_part(a["budget_variance"]), overtime_part(a["ot_share"], s)],
        "attendance": [attendance_part(a["attendance"], a["unauthorised"], s)],
        "skills": [capped(coverage, s["coverage_target"]), capped(competent, s["coverage_target"]),
                   capped(critical, s["coverage_target"])],
        "supervision": [supervision["index"]],
        "safety": [capped(a["ppe"], s["ppe_target"]), a["shift_factors"]["safety"],
                   a["shift_factors"]["housekeeping"], fatigue_part(a["fatigue"], s)],
        "relations": [relations, capped(pulse, s["pulse_target"]) if pulse is not None else None],
        "interventions": [effectiveness],
    }
    scores = {key: _average(parts[key]) for key in PILLAR_KEYS}
    composite, share = weighted(scores, {key: s["pillar_" + key] for key in PILLAR_KEYS})
    flags = red_flags(facts, t, s)
    status = NO_DATA if composite is None else (RED_FLAG if flags else rag(composite, s))
    months = facts.get("months") or 1
    turnover = ratio(facts.get("exits") or 0, headcount) if headcount else None
    due_reports = facts.get("due_reports")
    reported = facts.get("reported")
    reported = t.get("shifts") if reported is None else reported
    kpis = {
        "planning": [
            ("Active Head Count", headcount, None, None),
            ("Approved Establishment", establishment, None, None),
            ("Variance", headcount - establishment, 0,
             _check(abs(headcount - establishment) <= establishment * 0.05) if establishment else NO_DATA),
            ("Deployment (on shift over crew)", a["deployment"], s["staffing_low"],
             _check(a["deployment"] is not None and s["staffing_low"] <= a["deployment"] <= s["staffing_high"])
             if a["deployment"] is not None else NO_DATA),
            ("Shifts Below the Staffing Band", int(t["below_band"]) if has else None, 0,
             _check(t["below_band"] == 0) if has else NO_DATA),
            ("Direct Labour Share", facts.get("direct_share"), None, None),
        ],
        "productivity": [
            ("Output per Person-Shift (Kg)", _per(t, "Kg", "actual", "on_shift"), None, None),
            ("Output per Person-Shift (Pcs)", _per(t, "Pcs", "actual", "on_shift"), None, None),
            ("Labour Cost per Kg", _per(t, "Kg", "labour", "actual"), None, None),
            ("Total Labour Cost", t["labour_cost"] if has else None, None, None),
            ("Labour Cost against Budget", a["budget_variance"], 0,
             _check(a["budget_variance"] <= 0) if a["budget_variance"] is not None else NO_DATA),
            ("Overtime Cost", t["ot_cost"] if has else None, None, None),
            ("Overtime Share of Labour Cost", a["ot_share"], s["overtime_ceiling"],
             _check(a["ot_share"] <= s["overtime_ceiling"]) if a["ot_share"] is not None else NO_DATA),
            ("Paid Absence Cost", t["absence_cost"] if has else None, None, None),
        ],
        "attendance": [
            ("Attendance", a["attendance"], s["attendance_target"],
             _check(a["attendance"] >= s["attendance_target"]) if a["attendance"] is not None else NO_DATA),
            ("Absenteeism", (1 - a["attendance"]) if a["attendance"] is not None else None,
             1 - s["attendance_target"],
             _check(a["attendance"] >= s["attendance_target"]) if a["attendance"] is not None else NO_DATA),
            ("Unauthorised Absence", a["unauthorised"], s["unauthorised_ceiling"],
             _check(a["unauthorised"] <= s["unauthorised_ceiling"]) if a["unauthorised"] is not None else NO_DATA),
            ("Late Arrivals and Early Departures", int(t["late_arrivals"] + t["early_departures"]) if has else None,
             None, None),
            ("Shift Reports Entered", ratio(reported, due_reports) if due_reports else None, s["reporting_target"],
             _check(reported >= s["reporting_target"] * due_reports) if due_reports else NO_DATA),
        ],
        "skills": [
            ("Required Training Done", coverage, s["coverage_target"],
             _check(coverage >= s["coverage_target"]) if coverage is not None else NO_DATA),
            ("Requirements Not Done", (required - done) if required else None, 0,
             _check(required == done) if required else NO_DATA),
            ("Skills at the Level Needed", competent, s["coverage_target"],
             _check(competent >= s["coverage_target"]) if competent is not None else NO_DATA),
            ("Critical Skills at the Level Needed", critical, s["coverage_target"],
             _check(critical >= s["coverage_target"]) if critical is not None else NO_DATA),
        ],
        "supervision": [
            ("Supervisory Index", supervision["index"], s["green_from"],
             _check(supervision["index"] >= s["green_from"]) if supervision["index"] is not None else NO_DATA),
            ("Coaching Sessions", facts.get("sessions") or 0,
             max(1, facts.get("supervisors") or 1) * s["coaching_per_week"] * (facts.get("weeks") or 0), None),
            ("Actions Closed on Time", ratio(facts.get("interventions_on_time") or 0, interventions)
             if interventions else None, s["closure_target"],
             _check((facts.get("interventions_on_time") or 0) >= s["closure_target"] * interventions)
             if interventions else NO_DATA),
            ("Open Leadership Interventions", facts.get("interventions_open_supervision") or 0, None, None),
        ],
        "safety": [
            ("PPE Compliance", a["ppe"], s["ppe_target"],
             _check(a["ppe"] >= s["ppe_target"]) if a["ppe"] is not None else NO_DATA),
            ("Safety Incidents", int(t["safety_incidents"]) if has else None, 0,
             _check(t["safety_incidents"] == 0) if has else NO_DATA),
            ("Near Misses Reported", int(t["near_misses"]) if has else None, None, None),
            ("Housekeeping", a["housekeeping"], s["housekeeping_target"],
             _check(a["housekeeping"] >= s["housekeeping_target"]) if a["housekeeping"] is not None else NO_DATA),
            ("Overtime Hours per Person-Shift", a["fatigue"], s["fatigue_ot"],
             _check(a["fatigue"] <= s["fatigue_ot"]) if a["fatigue"] is not None else NO_DATA),
            ("Safety Trainings Logged", facts.get("safety_trainings") or 0, None, None),
        ],
        "relations": [
            ("Open Grievances", facts.get("open_grievances") or 0, 0, _check(not facts.get("open_grievances"))),
            ("Cases in the Period", facts.get("cases") or 0, None, None),
            ("Of Which Disciplinary Route", facts.get("conduct_route") or 0, None, None),
            ("Cases Routed to Coaching or a Process Fix",
             ratio(facts.get("coaching_route") or 0, facts.get("non_grievance_cases")), None, None),
            ("Repeat Cases", facts.get("repeats") or 0, 0, _check(not facts.get("repeats"))),
            ("Average Days to Decide", facts.get("days_to_resolve"), s["case_days"],
             _check(facts["days_to_resolve"] <= s["case_days"]) if facts.get("days_to_resolve") is not None
             else NO_DATA),
            ("Legal Flags Open", facts.get("legal_flags") or 0, 0, _check(not facts.get("legal_flags"))),
            ("Exits", facts.get("exits") or 0, None, None),
            ("Voluntary Exits", facts.get("voluntary_exits") or 0, None, None),
            ("Turnover", turnover, s["turnover_ceiling"] * max(1.0, months),
             _check(turnover <= s["turnover_ceiling"] * max(1.0, months)) if turnover is not None else NO_DATA),
            ("Recognitions", facts.get("recognitions") or 0, None, None),
            ("Suggestions (Implemented)", "%d (%d)" % (facts.get("suggestions") or 0, facts.get("implemented") or 0),
             None, None),
            ("Engagement Pulse (Last 3 Months)", pulse, s["pulse_target"],
             _check(pulse >= s["pulse_target"]) if pulse is not None else NO_DATA),
        ],
        "interventions": [
            ("Raised in the Period", facts.get("interventions_raised") or 0, None, None),
            ("Completed in the Period", facts.get("interventions_completed") or 0, None, None),
            ("Overdue Now", facts.get("interventions_overdue") or 0, 0, _check(not facts.get("interventions_overdue"))),
            ("Verified Improvements", facts.get("interventions_improved") or 0, None, None),
            ("Estimated Savings, Verified", facts.get("savings") or 0, None, None),
        ],
    }
    return {"pillars": [{"key": key, "label": PILLAR_LABELS[key], "weight": s["pillar_" + key], "score": scores[key],
                         "status": rag(scores[key], s)} for key in PILLAR_KEYS],
            "composite": composite, "share": share, "status": status, "red_flags": flags, "kpis": kpis,
            "supervision": supervision, "averages": a, "turnover": turnover, "coverage": coverage,
            "competent": competent, "critical": critical}


def red_flags(facts, t, s):
    """What marks a period critical whatever its score."""
    flags = []
    if t.get("shifts") and t["safety_incidents"] >= max(1, s["red_flag_safety"]):
        flags.append("{0} safety incident(s)".format(int(t["safety_incidents"])))
    if facts.get("legal_flags"):
        flags.append("{0} case(s) with a legal flag".format(facts["legal_flags"]))
    if facts.get("grievances_open_long"):
        flags.append("{0} grievance(s) open over {1} days".format(facts["grievances_open_long"], int(s["case_days"])))
    return flags


def _per(t, unit, top, bottom):
    made = (t.get("by_unit") or {}).get(unit)
    return ratio(made[top], made[bottom]) if made else None


def _check(ok):
    return "On Target" if ok else "Needs Attention"


# ── The executive view: tiles, verdict, signals, flags ───────────────
GREEN, AMBER, RED, GREY = "green", "amber", "red", "grey"
LIGHTS = {ON_TARGET: GREEN, ATTENTION: AMBER, CRITICAL: RED, RED_FLAG: RED, NO_DATA: GREY}


def light(ok, near=False):
    return GREEN if ok else (AMBER if near else RED)


def section_scores(section_totals, s):
    """[{"section", "score", "status", "weakest", "weakest_label",
    "weakest_action", "factors", "totals"}] for the sections with shifts,
    lowest first."""
    found = []
    for section, t in (section_totals or {}).items():
        if not t.get("shifts"):
            continue
        scored = period_scores(t, s)
        found.append({"section": section, "score": scored["score"], "status": scored["status"],
                      "weakest": scored["weakest"], "weakest_label": FACTOR_LABELS.get(scored["weakest"], ""),
                      "weakest_action": scored["weakest_action"], "factors": scored["factors"], "totals": t})
    return sorted(found, key=lambda row: (row["score"], row["section"]))


def verdict(scored):
    """The workbook's one line: how many sections on target, at attention and
    critical, and the lowest with its weakest area."""
    if not scored:
        return "No shifts recorded in the period."
    counts = {status: sum(1 for row in scored if row["status"] == status) for status in STATUSES}
    lowest = min(scored, key=lambda row: (row["score"], row["section"]))
    return "{0} on target, {1} attention, {2} critical. Lowest: {3} ({4}), weakest on {5}.".format(
        counts[ON_TARGET], counts[ATTENTION], counts[CRITICAL], section_label(lowest["section"]),
        _plain(lowest["score"]), lowest["weakest_label"])


def section_label(name):
    """A section's own name without its plant ("Lamination - Kawempe" is
    Lamination)."""
    return str(name or "").rsplit(" - ", 1)[0]


def production_tiles(t, scored, s):
    """The workbook Dashboard's eleven tiles for a period."""
    a = averages(t, s)
    plant = plant_score([row["score"] for row in scored])
    achievements = [ratio(row["totals"]["actual_output"], row["totals"]["target"]) for row in scored]
    achievements = [value for value in achievements if value is not None]
    achievement = sum(achievements) / len(achievements) if achievements else None
    housekeeping = [row["totals"]["housekeeping"] / row["totals"]["shifts"] / 100.0 for row in scored
                    if row["totals"]["shifts"]]
    housekeeping = sum(housekeeping) / len(housekeeping) if housekeeping else None
    over = sum(1 for row in scored if (row["totals"]["waste_cap"]
                                       and row["totals"]["waste_value"] >= row["totals"]["waste_cap"])
               or (row["totals"]["complaint_cap"] and row["totals"]["complaint_value"]
                   >= row["totals"]["complaint_cap"]))
    has = bool(t.get("shifts"))
    return [
        _tile("plant_score", "Overall Score", plant, "score", s["green_from"], LIGHTS[rag(plant, s)]),
        _tile("waste", "Waste and Rejects", t["waste_value"] if has else None, "money", None,
              GREY if not has else light(t["waste_value"] < t["waste_cap"] if t["waste_cap"] else True)),
        _tile("complaints", "Complaints", t["complaint_value"] if has else None, "money", None,
              GREY if not has else light(t["complaint_value"] < t["complaint_cap"] if t["complaint_cap"] else True)),
        _tile("achievement", "Achievement", achievement, "percent", 1.0,
              GREY if achievement is None else light(achievement >= 0.95, achievement >= 0.85)),
        _tile("uptime", "Machine Uptime", a["uptime"] if has else None, "percent", None,
              GREY if not has else light((a["uptime"] or 0) >= 0.9, (a["uptime"] or 0) >= 0.8)),
        _tile("incidents", "Safety Incidents", int(t["safety_incidents"]) if has else None, "count", 0,
              GREY if not has else light(not t["safety_incidents"])),
        _tile("attendance", "Attendance", a["attendance"], "percent", s["attendance_target"],
              GREY if a["attendance"] is None else light(a["attendance"] >= s["attendance_target"],
                                                         a["attendance"] >= s["attendance_target"] - 0.05)),
        _tile("ppe", "PPE Adherence", a["ppe"], "percent", s["ppe_target"],
              GREY if a["ppe"] is None else light(a["ppe"] >= s["ppe_target"], a["ppe"] >= s["ppe_target"] - 0.05)),
        _tile("not_wearing", "Not Wearing PPE", int(t["not_wearing"]) if has else None, "count", 0,
              GREY if not has else light(not t["not_wearing"], t["not_wearing"] <= 5)),
        _tile("housekeeping", "Housekeeping", housekeeping, "percent", s["housekeeping_target"],
              GREY if housekeeping is None else light(housekeeping >= s["housekeeping_target"],
                                                      housekeeping >= s["housekeeping_target"] - 0.1)),
        _tile("over_limit", "Sections over a Limit", over if has else None, "count", 0,
              GREY if not has else light(not over)),
    ]


def hr_tiles(card, facts, s):
    """The workbook HR Excellence sheet's twelve tiles."""
    a = card["averages"]
    t = facts["totals"]
    headcount, establishment = facts.get("headcount") or 0, facts.get("establishment") or 0
    open_flags = (facts.get("legal_flags") or 0) + (facts.get("open_grievances") or 0)
    index = card["supervision"]["index"]
    variance = a["budget_variance"]
    return [
        _tile("hr_score", "HR Excellence Score", card["composite"], "score", s["green_from"],
              LIGHTS[card["status"]]),
        _tile("attendance", "Attendance", a["attendance"], "percent", s["attendance_target"],
              GREY if a["attendance"] is None else light(a["attendance"] >= s["attendance_target"],
                                                         a["attendance"] >= s["attendance_target"] - 0.05)),
        _tile("ot_share", "Overtime % of Labour", a["ot_share"], "percent", s["overtime_ceiling"],
              GREY if a["ot_share"] is None else light(a["ot_share"] <= s["overtime_ceiling"],
                                                       a["ot_share"] <= s["overtime_ceiling"] * 1.25)),
        _tile("labour_per_kg", "Labour Cost per Kg", _per(t, "Kg", "labour", "actual"), "money", None,
              GREY if variance is None else light(variance <= 0, variance <= 0.1),
              note=("{0}% against budget".format(_plain(round(variance * 100, 1))) if variance is not None else "")),
        _tile("supervision", "Supervisory Index", index, "score", s["green_from"], LIGHTS[rag(index, s)]),
        _tile("ppe", "PPE Compliance", a["ppe"], "percent", s["ppe_target"],
              GREY if a["ppe"] is None else light(a["ppe"] >= s["ppe_target"], a["ppe"] >= s["ppe_target"] - 0.05)),
        _tile("competency", "Competency Coverage", card["competent"], "percent", s["coverage_target"],
              GREY if card["competent"] is None else light(card["competent"] >= s["coverage_target"],
                                                           card["competent"] >= s["coverage_target"] - 0.1)),
        _tile("er_flags", "Open ER Flags", open_flags, "count", 0, light(not open_flags),
              note="Legal flags and open grievances"),
        _tile("turnover", "Turnover", card["turnover"], "percent", s["turnover_ceiling"],
              GREY if card["turnover"] is None else light(card["turnover"] <= s["turnover_ceiling"])),
        _tile("overdue", "Interventions Overdue", facts.get("interventions_overdue") or 0, "count", 0,
              light(not facts.get("interventions_overdue"))),
        _tile("verified", "Verified Improvements", facts.get("interventions_improved") or 0, "count", None, GREEN),
        _tile("headcount", "Head Count against Establishment", "%d / %d" % (headcount, establishment), "text", None,
              GREY if not establishment else light(abs(headcount - establishment) <= establishment * 0.05)),
    ]


def _tile(key, label, value, kind, target, colour, note=""):
    return {"key": key, "label": label, "value": value, "kind": kind, "target": target, "light": colour,
            "note": note}


def section_signals(row, s):
    """The workforce signals that occur together in a section, and the
    intervention to look at first (the workbook's HR Excellence by section).
    row: deployment, attendance, unauthorised, ot_share, ppe, competency,
    open_grievances, exits."""
    if row.get("deployment") is None:
        return {"signals": [], "keys": [], "count": 0, "intervention": "", "alert": ""}
    found = []

    def has(key):
        return row.get(key) is not None

    if has("attendance") and row["attendance"] < s["attendance_target"]:
        found.append("attendance")
    if has("unauthorised") and row["unauthorised"] > s["unauthorised_ceiling"]:
        found.append("unauthorised")
    if has("ot_share") and row["ot_share"] > s["overtime_ceiling"]:
        found.append("overtime")
    if has("ppe") and row["ppe"] < s["ppe_target"]:
        found.append("ppe")
    if has("competency") and row["competency"] < s["coverage_target"]:
        found.append("competency")
    if _num(row.get("open_grievances")) > 0:
        found.append("grievances")
    if _num(row.get("exits")) > 0:
        found.append("exits")
    if row["deployment"] > s["staffing_high"]:
        found.append("overstaffed")
    if "overtime" in found:
        intervention = INTERVENTIONS[0]
    elif "attendance" in found:
        intervention = INTERVENTIONS[3]
    elif "grievances" in found:
        intervention = INTERVENTIONS[5]
    elif "exits" in found:
        intervention = INTERVENTIONS[6]
    elif "ppe" in found:
        intervention = INTERVENTIONS[4]
    elif "competency" in found:
        intervention = INTERVENTIONS[1]
    else:
        intervention = INTERVENTIONS[7]
    count = len(found)
    alert = "" if not count else ("1 signal: monitor" if count == 1
                                  else "{0} signals: {1}".format(count, intervention))
    return {"signals": [SIGNAL_LABELS[key] for key in found], "keys": found, "count": count,
            "intervention": intervention if count >= 2 else "", "alert": alert}


INTERVENTION_PILLARS = {INTERVENTIONS[0]: PILLAR_LABELS["planning"], INTERVENTIONS[1]: PILLAR_LABELS["skills"],
                        INTERVENTIONS[2]: PILLAR_LABELS["skills"], INTERVENTIONS[3]: PILLAR_LABELS["attendance"],
                        INTERVENTIONS[4]: PILLAR_LABELS["safety"], INTERVENTIONS[5]: PILLAR_LABELS["relations"],
                        INTERVENTIONS[6]: PILLAR_LABELS["relations"], INTERVENTIONS[7]: PILLAR_LABELS["supervision"],
                        INTERVENTIONS[8]: PILLAR_LABELS["productivity"]}
LABOUR_FLAG_INTERVENTION = {OT_UP: INTERVENTIONS[0], OVER_BUDGET: INTERVENTIONS[1], UNAUTHORISED: INTERVENTIONS[3],
                            FATIGUE: INTERVENTIONS[0]}
SIGNAL_KPIS = {INTERVENTIONS[0]: "Overtime % of Labour Cost", INTERVENTIONS[1]: "Training Coverage %",
               INTERVENTIONS[3]: "Attendance %", INTERVENTIONS[4]: "PPE Compliance %",
               INTERVENTIONS[5]: "Open Grievances", INTERVENTIONS[6]: "Turnover %",
               INTERVENTIONS[7]: "Supervisor People Score"}


def labour_flags(now, before, s):
    """The workbook Labour Cost sheet's flags for a section's week against the
    week before: [(flag, the intervention to look at)], the most pressing
    first."""
    if not now or not now.get("shifts"):
        return []
    found = []
    ot_change = (now["ot_cost"] / before["ot_cost"] - 1) if before and _num(before.get("ot_cost")) else None
    output_change = ((now["actual_output"] / before["actual_output"] - 1)
                     if before and _num(before.get("actual_output")) else None)
    if ot_change is not None and ot_change > OT_RISE and (output_change is None or output_change <= OUTPUT_RISE):
        found.append(OT_UP)
    variance = (now["budgeted_labour"] / now["labour_budget"] - 1) if _num(now.get("labour_budget")) else None
    if variance is not None and variance > BUDGET_OVER:
        found.append(OVER_BUDGET)
    if _num(now.get("staff_planned")) and now["unauthorised_absent"] / now["staff_planned"] > s["unauthorised_ceiling"]:
        found.append(UNAUTHORISED)
    if _num(now.get("staff_on_shift")) and now["ot_hours"] / now["staff_on_shift"] > s["fatigue_ot"]:
        found.append(FATIGUE)
    return [(flag, LABOUR_FLAG_INTERVENTION[flag]) for flag in found]


# ── Plant Day Sheet ───────────────────────────────────────────────────
PASTE_COLUMNS = (
    ("work_section", "Section"), ("shift", "Shift"), ("actual_output", "Actual Output"),
    ("housekeeping", "Housekeeping"), ("machines_running", "Machines Running"), ("stop_hours", "Stop Hours"),
    ("downtime_reason", "Main Downtime Reason"), ("waste_qty", "Waste Quantity"), ("waste_value", "Waste Value"),
    ("complaint_value", "Complaint Value"), ("wearing_ppe", "Wearing Full PPE"), ("not_worked", "Not Worked"),
    ("comment", "Comment"),
)
PASTE_NUMBERS = ("actual_output", "housekeeping", "machines_running", "stop_hours", "waste_qty", "waste_value",
                 "complaint_value", "wearing_ppe")
PASTE_TEXT = ("downtime_reason", "comment")
SHEET_TYPED = PASTE_NUMBERS + PASTE_TEXT + ("not_worked",)


def sheet_rows_to_add(sections, existing):
    """The (section, shift) rows a plant's day sheet lacks: every active
    reporting section, Day then Night, in the order the sections are given."""
    have = {(row.get("work_section"), row.get("shift")) for row in existing or ()}
    return [(section, shift) for section in sections for shift in SHIFTS if (section, shift) not in have]


def row_entered(row):
    """Whether a day sheet row has been entered: output or housekeeping typed
    (a section that did not work is marked Not Worked instead)."""
    return _num(row.get("actual_output")) > 0 or _num(row.get("housekeeping")) > 0


def sheet_state(rows):
    """{"entered", "not_worked", "missing", "missing_rows": [(section, shift)]}."""
    state = {"entered": 0, "not_worked": 0, "missing": 0, "missing_rows": []}
    for row in rows or ():
        if _num(row.get("not_worked")):
            state["not_worked"] += 1
        elif row_entered(row):
            state["entered"] += 1
        else:
            state["missing"] += 1
            state["missing_rows"].append((row.get("work_section"), row.get("shift")))
    return state


def sheet_errors(sheet_date, today, rows):
    errors = []
    day = _date(sheet_date)
    if day and _date(today) and day > _date(today):
        errors.append("A day sheet is for a day that has been worked.")
    seen = set()
    for row in rows or ():
        key = (row.get("work_section"), row.get("shift"))
        if key in seen:
            errors.append("{0} {1} is on the sheet twice.".format(section_label(key[0]), key[1]))
        seen.add(key)
        if _num(row.get("not_worked")) and row_entered(row):
            errors.append("{0} {1} is marked Not Worked but has figures.".format(section_label(key[0]), key[1]))
        checked = dict(row)
        if not _num(checked.get("staff_planned")) or not _num(checked.get("staff_on_shift")):
            # the people come from the clock: until they have, PPE is not checked against them
            checked["wearing_ppe"] = checked["unauthorised_absent"] = 0
        for message in entry_errors(checked):
            errors.append("{0} {1}: {2}".format(section_label(key[0]), key[1], message))
    return errors


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def parse_paste(text, rows):
    """Rows copied from a spreadsheet onto a day sheet. The first line may be a
    heading (the columns' names, in any order); without one the columns are
    PASTE_COLUMNS in order. Each line is matched to a row by section and
    shift. rows: [{"key", "work_section", "shift"}]. Returns {"updates":
    [{"key", "values"}], "errors": [...]}: a blank cell changes nothing."""
    lines = [line for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    errors, updates = [], []
    if not lines:
        return {"updates": updates, "errors": ["Nothing was pasted."]}
    names = {}
    for field, label in PASTE_COLUMNS:
        names[_norm(label)] = field
        names[_norm(field)] = field
    names.update({_norm("Section Name"): "work_section", _norm("Wearing PPE"): "wearing_ppe",
                  _norm("Output"): "actual_output", _norm("Downtime Reason"): "downtime_reason",
                  _norm("Housekeeping %"): "housekeeping", _norm("Stopped Hours"): "stop_hours"})
    first = lines[0].split("\t")
    heading = [names.get(_norm(cell)) for cell in first]
    if sum(1 for field in heading if field) >= 2 and "work_section" in heading and "shift" in heading:
        columns, body = heading, lines[1:]
    else:
        columns, body = [field for field, _label in PASTE_COLUMNS], lines
    index = {}
    for row in rows or ():
        section = row.get("work_section") or ""
        for alias in {_norm(section), _norm(section_label(section))}:
            index[(alias, row.get("shift"))] = row.get("key")
    shifts = {"day": DAY, "d": DAY, "night": NIGHT, "n": NIGHT}
    labels = dict(PASTE_COLUMNS)
    for number, line in enumerate(body, 1):
        cells = line.split("\t")
        record = {columns[i]: cells[i].strip() for i in range(min(len(columns), len(cells))) if columns[i]}
        shift = shifts.get(_norm(record.get("shift")))
        key = index.get((_norm(record.get("work_section")), shift))
        if not shift or key is None:
            errors.append("Line {0}: no {1} {2} on this sheet.".format(number, record.get("work_section") or "section",
                                                                      record.get("shift") or ""))
            continue
        values = {}
        for field in PASTE_NUMBERS:
            cell = record.get(field)
            if cell in (None, ""):
                continue
            try:
                values[field] = float(cell.replace(",", "").replace("%", "").strip())
            except ValueError:
                errors.append("Line {0}: {1} is not a number ({2}).".format(number, labels[field], cell))
        for field in PASTE_TEXT:
            if record.get(field):
                values[field] = record[field]
        if record.get("not_worked"):
            values["not_worked"] = int(_norm(record["not_worked"]) in ("yes", "y", "1", "true", "x"))
        updates.append({"key": key, "values": values})
    return {"updates": updates, "errors": errors}


# ── Plant Order and its feasibility ───────────────────────────────────
def order_errors(order):
    errors = []
    for field, label in (("order_qty", "Order Quantity"), ("order_value", "Order Value"),
                         ("budget_per_unit", "Budget per Unit")):
        if _num(order.get(field)) < 0:
            errors.append("{0} cannot be negative.".format(label))
    return errors


def order_budget(order, s):
    """The conversion cost a unit may carry: the order's own budget, else the
    unit price at the settings' share of the order value."""
    if _num(order.get("budget_per_unit")):
        return _num(order.get("budget_per_unit"))
    qty, value = _num(order.get("order_qty")), _num(order.get("order_value"))
    return value / qty * s["budget_percent"] if qty and value else None


def order_figures(order, progress, s):
    """The workbook's Order Feasibility, for one order: its progress, what
    running it has cost, whether that is within budget, and the cost to
    finish. progress: shifts, finishing_shifts, first, last, produced (in the
    finishing section), labour (regular and overtime), ot_hours, ot_cost,
    waste, complaints."""
    progress = progress or {}
    qty, value = _num(order.get("order_qty")), _num(order.get("order_value"))
    produced = _num(progress.get("produced"))
    labour, waste = _num(progress.get("labour")), _num(progress.get("waste"))
    complaints = _num(progress.get("complaints"))
    conversion = labour + waste + complaints
    price = value / qty if qty and value else None
    budget = order_budget(order, s)
    labour_unit = labour / produced if produced else None
    conversion_unit = conversion / produced if produced else None
    if not produced:
        feasibility = NO_OUTPUT
    elif not budget:
        feasibility = SET_BUDGET
    elif conversion_unit <= budget:
        feasibility = FEASIBLE
    elif conversion_unit <= budget * (1 + s["marginal_band"]):
        feasibility = MARGINAL
    else:
        feasibility = NOT_FEASIBLE
    balance = max(0.0, qty - produced) if qty else None
    finishing = _num(progress.get("finishing_shifts"))
    per_shift = produced / finishing if produced and finishing else None
    to_finish = (balance / per_shift) if balance is not None and per_shift else None
    cost_to_finish = balance * conversion_unit if balance is not None and conversion_unit is not None else None
    return {
        "unit_price": price, "budget_per_unit": budget, "shifts": int(_num(progress.get("shifts"))),
        "first": progress.get("first"), "last": progress.get("last"), "produced": produced,
        "complete": produced / qty if qty else None, "balance": balance, "labour": labour,
        "ot_hours": _num(progress.get("ot_hours")), "ot_cost": _num(progress.get("ot_cost")), "waste": waste,
        "complaints": complaints, "conversion": conversion, "labour_per_unit": labour_unit,
        "conversion_per_unit": conversion_unit,
        "labour_share": labour / (produced * price) if produced and price else None,
        "over_budget": conversion_unit - budget if conversion_unit is not None and budget else None,
        "feasibility": feasibility, "shifts_to_finish": to_finish, "cost_to_finish": cost_to_finish,
        "projected": conversion + cost_to_finish if cost_to_finish is not None else None,
    }


# ── Discipline: the cause and the law's limits ────────────────────────
def route_for(cause, severity=None):
    if severity == GROSS:
        return ROUTES[MISCONDUCT]
    return ROUTES.get(cause) or ""


def is_conduct(cause, severity=None):
    """Whether a case may go the disciplinary route: negligence, deliberate
    misconduct, or a gross act."""
    return cause in CONDUCT_CAUSES or severity == GROSS


def penalty_due_by(aware_on, s):
    aware_on = _date(aware_on)
    return aware_on + datetime.timedelta(days=int(_num(s["penalty_limit_days"]))) if aware_on else None


def suspended_before(cases, start, s, exclude=None):
    """Suspension days already served or set in the window before `start`
    (six months by default)."""
    start = _date(start)
    if not start:
        return 0
    since = start - datetime.timedelta(days=int(_num(s["suspension_window_days"])))
    total = 0
    for case in cases or ():
        if exclude and case.get("name") == exclude:
            continue
        begun = _date(case.get("suspension_from"))
        if begun and since < begun <= start:
            total += int(_num(case.get("suspension_days")))
    return total


def suspension_history(cases):
    """{employee: [their cases with a suspension]}, from one read of the cases."""
    found = {}
    for case in cases or ():
        if case.get("suspension_from") and _num(case.get("suspension_days")):
            found.setdefault(case.get("employee"), []).append(case)
    return found


def case_flags(case, today, s, before=0):
    """The legal flags on a case, as short messages: the 15-day limit, the
    suspension cap, a sanction on a cause that is not conduct, a decision
    with no cause."""
    flags = []
    today = _date(today)
    due = penalty_due_by(case.get("aware_on"), s)
    decided = _date(case.get("decided_on"))
    sanctioned = case.get("outcome") == SANCTIONED
    if due and not decided and today and today > due and case.get("status") not in CASE_CLOSED:
        flags.append("Past the {0} days to impose a penalty (s.62(5))".format(int(_num(s["penalty_limit_days"]))))
    if due and decided and sanctioned and decided > due:
        flags.append("Penalty decided after the {0} day limit (s.62(5))".format(int(_num(s["penalty_limit_days"]))))
    days = int(_num(case.get("suspension_days")))
    if days and case.get("suspension_from") and days + int(before or 0) > _num(s["suspension_cap_days"]):
        flags.append("Suspension over {0} days in six months (s.62(4))".format(int(_num(s["suspension_cap_days"]))))
    cause = case.get("cause")
    if sanctioned and cause and not is_conduct(cause, case.get("severity")):
        flags.append("Sanction on a cause that is not conduct")
    if (decided or case.get("outcome")) and not cause:
        flags.append("Cause not classified")
    return flags


def window_counts(cases, months):
    """{case name: its employee's cases in the look back window up to and with
    it}: each employee's cases sorted once and counted in one pass."""
    by_employee = {}
    for case in cases or ():
        day = _date(case.get("incident_date"))
        if day:
            by_employee.setdefault(case.get("employee"), []).append((day, case.get("name") or ""))
    found = {}
    for rows in by_employee.values():
        rows.sort()
        start = 0
        for end, (day, name) in enumerate(rows):
            since = add_months(day, -int(months))
            while rows[start][0] <= since:
                start += 1
            found[name] = end - start + 1
    return found


def tracker_flag(case, in_window, today, s):
    """The case's flag on the tracker, the most pressing first: a legal flag,
    Decision Due (charged or heard, not decided), Overdue (open longer than
    the target days), Repeat (two cases or more in the window)."""
    today = _date(today)
    legal = [line for line in (case.get("legal_flags") or "").splitlines() if line.strip()]
    open_case = case.get("status") not in CASE_CLOSED and not case.get("decided_on")
    if legal:
        return legal[0]
    if open_case and case.get("status") in CASE_DECIDING:
        return DECISION_DUE
    reported = _date(case.get("aware_on") or case.get("incident_date"))
    if open_case and reported and today and (today - reported).days > _num(s["case_days"]):
        return OVERDUE
    if in_window and in_window >= 2:
        return REPEAT
    return ""


def tracker_breakdown(cases, key, counts):
    """Cases grouped by one of their fields: {value: {"cases", "day", "night",
    "conduct", "coaching", "process", "grievances", "cost", "quantity",
    "repeats", "causes": {cause: n}}}."""
    found = {}
    for case in cases or ():
        value = case.get(key) or "Not Recorded"
        row = found.setdefault(value, {"cases": 0, "day": 0, "night": 0, "conduct": 0, "coaching": 0, "process": 0,
                                       "grievances": 0, "cost": 0.0, "quantity": 0.0, "repeats": 0, "causes": {}})
        row["cases"] += 1
        row["day"] += int(case.get("shift") == DAY)
        row["night"] += int(case.get("shift") == NIGHT)
        if case.get("case_type") == "Grievance":
            row["grievances"] += 1
        elif is_conduct(case.get("cause"), case.get("severity")):
            row["conduct"] += 1
        elif case.get("cause") in PROCESS_CAUSES:
            row["process"] += 1
        elif case.get("cause"):
            row["coaching"] += 1
        row["cost"] += _num(case.get("case_cost"))
        row["quantity"] += _num(case.get("quantity"))
        row["repeats"] += int((counts or {}).get(case.get("name"), 0) >= 2)
        cause = case.get("cause") or "Not Classified"
        row["causes"][cause] = row["causes"].get(cause, 0) + 1
    return found


def repeat_cases(cases, as_on, months):
    """Employees with two cases or more in the look back window to `as_on`:
    {employee: {"cases", "conduct", "causes": {cause: n}, "types", "cost",
    "last", "last_case"}}."""
    as_on = _date(as_on)
    since = add_months(as_on, -int(months))
    found = {}
    for case in cases or ():
        day = _date(case.get("incident_date"))
        if not day or not (since < day <= as_on):
            continue
        row = found.setdefault(case.get("employee"), {"cases": 0, "conduct": 0, "causes": {}, "cost": 0.0,
                                                      "last": None, "last_case": None, "types": {}})
        row["cases"] += 1
        if is_conduct(case.get("cause"), case.get("severity")):
            row["conduct"] += 1
        cause = case.get("cause") or "Not Classified"
        row["causes"][cause] = row["causes"].get(cause, 0) + 1
        kind = case.get("misconduct_type") or case.get("case_type") or ""
        row["types"][kind] = row["types"].get(kind, 0) + 1
        row["cost"] += _num(case.get("case_cost"))
        if row["last"] is None or day >= row["last"]:
            row["last"], row["last_case"] = day, case.get("name")
    return {employee: row for employee, row in found.items() if row["cases"] >= 2}


# ── HR Intervention ───────────────────────────────────────────────────
def intervention_state(row, today):
    """What an intervention works out: the KPI's change and whether that is an
    improvement, days open, overdue, closed on time."""
    today = _date(today)
    baseline, latest = row.get("baseline"), row.get("latest")
    change = result = None
    if baseline not in (None, "") and latest not in (None, "") and row.get("kpi"):
        change = round(_num(latest) - _num(baseline), 4)
        better = KPI_DIRECTION.get(row.get("kpi"), HIGHER)
        result = NO_CHANGE if change == 0 else (IMPROVED if (change > 0) == (better == HIGHER) else WORSE)
    raised, target = _date(row.get("raised_on")), _date(row.get("target_date"))
    closed = _date(row.get("closed_on")) if row.get("status") in DONE else None
    done = row.get("status") in DONE
    return {
        "change": change, "result": result,
        "days_open": ((closed or today) - raised).days if raised and (closed or today) else None,
        "overdue": int(bool(target and not done and today and today > target)),
        "on_time": ("Yes" if closed <= target else "Late") if closed and target else "",
    }


def intervention_errors(row):
    errors = []
    raised, target = _date(row.get("raised_on")), _date(row.get("target_date"))
    if raised and target and target < raised:
        errors.append("The target date is before the date raised.")
    closed = _date(row.get("closed_on"))
    if closed and raised and closed < raised:
        errors.append("The date closed is before the date raised.")
    if row.get("status") in DONE and not (row.get("actual_outcome") or "").strip():
        errors.append("Say what actually happened before closing it.")
    if row.get("verified") and row.get("status") not in DONE:
        errors.append("Only a completed intervention is verified.")
    return errors


def readings_baseline_latest(readings, baseline=None):
    """(baseline, latest) from an intervention's KPI readings: the first
    reading is the baseline unless one was typed; the newest the latest
    (None while the baseline is the only reading)."""
    dated = sorted((row for row in readings or () if row.get("value") not in (None, "")
                    and _date(row.get("reading_date"))), key=lambda row: _date(row.get("reading_date")))
    if not dated:
        return baseline, None
    typed = baseline not in (None, "")
    first, last = _num(dated[0].get("value")), _num(dated[-1].get("value"))
    return (baseline if typed else first), (last if typed or len(dated) > 1 else None)


def kpi_value(kpi, facts, s):
    """One of the sixteen KPIs an intervention tracks, for its scope and a
    week: fractions for the percentages. facts: "totals" and, as each needs,
    "coverage" (done, required), "repeats", "open_grievances",
    "people_score", "exits", "headcount", "pulse". None without data."""
    t = facts.get("totals") or totals([])
    a = averages(t, s)
    has = bool(t.get("shifts"))
    if kpi == "Attendance %":
        return a["attendance"]
    if kpi == "Unauthorised Absence":
        return t["unauthorised_absent"] if has else None
    if kpi == "Overtime % of Labour Cost":
        return a["ot_share"]
    if kpi == "Overtime Hours":
        return t["ot_hours"] if has else None
    if kpi == "Labour Cost per Unit":
        return a["labour_per_unit"]
    if kpi == "Output per Person-Shift":
        return a["output_per_person"]
    if kpi == "PPE Compliance %":
        return a["ppe"]
    if kpi == "Safety Incidents":
        return t["safety_incidents"] if has else None
    if kpi == "Waste Value":
        return t["waste_value"] if has else None
    if kpi == "Complaint Value":
        return t["complaint_value"] if has else None
    if kpi == "Training Coverage %":
        return ratio(*(facts.get("coverage") or (0, 0)))
    if kpi == "Repeat Incidents":
        return facts.get("repeats")
    if kpi == "Open Grievances":
        return facts.get("open_grievances")
    if kpi == "Supervisor People Score":
        return facts.get("people_score")
    if kpi == "Turnover %":
        return ratio(facts.get("exits") or 0, facts.get("headcount")) if facts.get("headcount") else None
    if kpi == "Pulse Score %":
        return facts.get("pulse")
    return None


# ── People Log ────────────────────────────────────────────────────────
def log_errors(log):
    errors = []
    if not 0 <= _num(log.get("score")) <= 100:
        errors.append("The score is a percentage, from 0 to 100.")
    seen = set()
    for row in log.get("attendees") or ():
        if row.get("employee") in seen:
            errors.append("{0} is listed twice.".format(row.get("employee")))
        seen.add(row.get("employee"))
    return errors


# ── HR Partner Brief ──────────────────────────────────────────────────
NINE_QUESTIONS = (
    "Right number of people in the right sections and shifts?",
    "Are employees skilled and competent enough?",
    "Are supervisors managing their teams well?",
    "What do absenteeism and overtime do to productivity and cost?",
    "Which workforce issues drive poor operational performance?",
    "Where are the employee relations and safety risks?",
    "What is HR doing about it?",
    "Are the interventions producing measurable improvement?",
    "Which workforce investments should management put first?",
)


def _money(value):
    return "{0:,.0f}".format(_num(value))


def _pct(value, places=0):
    if value is None:
        return "no data"
    return ("{0:." + str(places) + "f}%").format(value * 100)


def talking_points(f):
    """The brief's talking points for the production meeting, one a line.
    f: plant_score, plant_status, verdict, money_lost, over_limit, ppe,
    not_wearing, absent, attendance, incidents, hours_lost, top_reason,
    coach ({supervisor_name, section, shift, weakest} or None), labour,
    ot_cost, ot_share, not_feasible, cases, case_cost, legal_flags,
    open_grievances."""
    if f.get("plant_score") is None:
        return ["No shifts recorded for the week yet."]
    lines = ["Plant scored {0} ({1}). {2}".format(_plain(f["plant_score"]), f.get("plant_status") or "",
                                                 f.get("verdict") or "")]
    over = int(_num(f.get("over_limit")))
    lines.append("Money: {0} lost to waste and complaints. {1}".format(
        _money(f.get("money_lost")),
        "{0} section(s) reached a weekly limit; their supervisors bring a root cause and a fix.".format(over)
        if over else "Every section stayed inside its limits."))
    lines.append("PPE: {0} adherence; {1} person-shifts without full PPE. {2}".format(
        _pct(f.get("ppe")), int(_num(f.get("not_wearing"))),
        "Supervisors confirm a PPE check at every shift start; repeat names go to HR."
        if _num(f.get("not_wearing")) else "Keep the shift start PPE check."))
    lines.append("People: {0} person-shifts absent ({1} attendance). {2}".format(
        int(_num(f.get("absent"))), _pct(f.get("attendance")),
        "HR holds return to work talks and checks leave planning where it is worst."
        if _num(f.get("absent")) else "Full attendance."))
    lines.append("Safety: {0} incident(s). Machines: {1} machine hours lost, most to {2}.{3}".format(
        int(_num(f.get("incidents"))), _plain(round(_num(f.get("hours_lost")), 1)),
        f.get("top_reason") or "no reason given",
        " Investigation report due within 24 hours." if _num(f.get("incidents")) else ""))
    coach = f.get("coach")
    if coach:
        lines.append("Coaching focus: {0} ({1}, {2}), weakest on {3}.".format(
            coach.get("supervisor_name") or coach.get("supervisor"), section_label(coach.get("section")),
            coach.get("shift") or "", coach.get("weakest") or ""))
    lines.append("Labour: {0} spent on the floor, of which {1} overtime ({2}).{3}".format(
        _money(f.get("labour")), _money(f.get("ot_cost")), _pct(f.get("ot_share")),
        " {0} order(s) not feasible on Order Feasibility.".format(int(_num(f.get("not_feasible"))))
        if _num(f.get("not_feasible")) else ""))
    lines.append("Employee relations: {0} case(s) this week ({1}); {2} legal flag(s) and {3} open grievance(s) "
                 "need HR.".format(int(_num(f.get("cases"))), _money(f.get("case_cost")),
                                   int(_num(f.get("legal_flags"))), int(_num(f.get("open_grievances")))))
    return lines


def nine_questions(f):
    """The nine questions for the Plant Manager review, each answered from the
    week's figures. f: headcount, establishment, deployment, below_band,
    competent, critical, gaps, supervision, need_coaching, attendance,
    unauthorised, absence_cost, ot_cost, ot_share, budget_variance, signals
    ([(section, alert)]), open_grievances, legal_flags, repeats, incidents,
    near_misses, ppe, raised, open_interventions, overdue, improved, savings."""
    headcount, establishment = int(_num(f.get("headcount"))), int(_num(f.get("establishment")))
    signals = f.get("signals") or []
    answers = [
        "Head count {0} against an establishment of {1} ({2:+d}). Deployment {3} of the crew needed; {4} shift(s) "
        "below the staffing band.".format(headcount, establishment, headcount - establishment,
                                          _pct(f.get("deployment")), int(_num(f.get("below_band")))),
        ("No competency assessments yet: start with the critical roles." if f.get("competent") is None else
         "Coverage {0}; critical skills {1}; {2} gap(s).".format(_pct(f.get("competent")), _pct(f.get("critical")),
                                                                 int(_num(f.get("gaps"))))),
        "Supervisory index {0}. {1} supervisor(s) need leadership coaching this week.".format(
            _plain(f.get("supervision")) if f.get("supervision") is not None else "no data",
            int(_num(f.get("need_coaching")))),
        "Attendance {0}, unauthorised {1}; paid absence about {2}. Overtime {3}, {4} of labour; labour {5} against "
        "budget.".format(_pct(f.get("attendance"), 1), _pct(f.get("unauthorised"), 1), _money(f.get("absence_cost")),
                         _money(f.get("ot_cost")), _pct(f.get("ot_share"), 1), _pct(f.get("budget_variance"))),
        ("No section shows workforce signals together." if not signals else
         "; ".join("{0}: {1}".format(section_label(section), alert) for section, alert in signals[:2])),
        "Open grievances {0}; legal flags {1}; repeat incidents {2}. Safety incidents {3}, near misses reported {4}, "
        "PPE {5}.".format(int(_num(f.get("open_grievances"))), int(_num(f.get("legal_flags"))),
                          int(_num(f.get("repeats"))), int(_num(f.get("incidents"))),
                          int(_num(f.get("near_misses"))), _pct(f.get("ppe"))),
        "{0} intervention(s) started this week; {1} open in all; {2} overdue.".format(
            int(_num(f.get("raised"))), int(_num(f.get("open_interventions"))), int(_num(f.get("overdue")))),
        "{0} verified improvement(s); estimated verified savings {1}.".format(int(_num(f.get("improved"))),
                                                                              _money(f.get("savings"))),
        (signals[0][1] if signals else
         ("Build the skills assessments for the critical roles first." if f.get("competent") is None else
          "Sustain: keep coaching, cross training and attendance follow up.")),
    ]
    return list(zip(NINE_QUESTIONS, answers))


# ── The guide on the settings and the executive page ─────────────────
# (indicator, pillar, how it is worked out, where it comes from, owner, target)
KPI_DICTIONARY = (
    ("Active Head Count", "Workforce Planning and Deployment", "Active employees of the section or plant.",
     "Employee", "HR Manager", ""),
    ("Approved Establishment", "Workforce Planning and Deployment", "The sections' approved head count in force.",
     "Work Section standards", "HR Manager", ""),
    ("Variance", "Workforce Planning and Deployment", "Head count less establishment; within 5% is on target.",
     "Employee, Work Section", "HR Manager", "0"),
    ("Deployment", "Workforce Planning and Deployment", "Staff on shift over the standard crew.",
     "Shift Report crew", "HR Manager", "Staffing band"),
    ("Shifts Below the Staffing Band", "Workforce Planning and Deployment",
     "Shifts whose deployment fell below the band's low end.", "Shift Report", "HR Manager", "0"),
    ("Direct Labour Share", "Workforce Planning and Deployment", "Active employees of direct sections over all.",
     "Employee, Work Section", "HR Manager", ""),
    ("Output per Person-Shift", "Labour Productivity and Cost", "Output over person-shifts, within one unit.",
     "Shift Report", "HR Manager and Finance", ""),
    ("Labour Cost per Kg", "Labour Productivity and Cost", "Regular and overtime labour over kilograms made.",
     "Shift Report crew pay", "HR Manager and Finance", ""),
    ("Total Labour Cost", "Labour Productivity and Cost",
     "Each person's day rate from their salary structure while on shift, and their overtime.",
     "Shift Report crew", "HR Manager and Finance", ""),
    ("Labour Cost against Budget", "Labour Productivity and Cost",
     "Labour over output times the budget per unit, less one.", "Shift Report, Work Section standards",
     "HR Manager and Finance", "0 or below"),
    ("Overtime Cost", "Labour Productivity and Cost", "Overtime hours at each person's overtime rate.",
     "Overtime Request, Attendance", "HR Manager and Finance", ""),
    ("Overtime % of Labour Cost", "Labour Productivity and Cost", "Overtime cost over total labour cost.",
     "Shift Report", "HR Manager and Finance", "Overtime ceiling"),
    ("Paid Absence Cost", "Labour Productivity and Cost", "The day rate of people on paid leave.",
     "Attendance, Leave Application", "HR Manager and Finance", ""),
    ("Attendance", "Attendance and Reliability", "People on shift over people rostered.",
     "Attendance, Shift Assignment", "HR Manager and supervisors", "Attendance target"),
    ("Unauthorised Absence", "Attendance and Reliability", "Absent without leave over people rostered.",
     "Attendance", "HR Manager and supervisors", "Unauthorised absence ceiling"),
    ("Late Arrivals and Early Departures", "Attendance and Reliability", "People clocked in late or out early.",
     "Attendance", "HR Manager and supervisors", ""),
    ("Shift Reports Entered", "Attendance and Reliability", "Shift rows entered over shift rows due to date.",
     "Plant Day Sheet", "Manufacturing Excellence Officer", "95%"),
    ("Required Training Done", "Skills and Competency", "Required training done and still valid.",
     "Employee Training Requirement", "HR Training", "Coverage target"),
    ("Skills at the Level Needed", "Skills and Competency", "Current assessments at the level needed.",
     "Competency Assessment", "HR Training", "Coverage target"),
    ("Critical Skills at the Level Needed", "Skills and Competency", "The same, critical skills only.",
     "Competency Assessment", "HR Training", "Coverage target"),
    ("Supervisory Index", "Supervisory Effectiveness",
     "Reporting, attendance, PPE, safety, housekeeping, conduct, closure and coaching, weighted; parts with no "
     "data left out.", "Shift Report, Disciplinary Case, HR Intervention, People Log", "HR Manager", "Green band"),
    ("Coaching Sessions", "Supervisory Effectiveness", "Toolbox talks, operator coaching and recognition logged.",
     "People Log", "HR Manager", "Sessions per supervisor per week"),
    ("Actions Closed on Time", "Supervisory Effectiveness", "Interventions due by now, closed by their target date.",
     "HR Intervention", "HR Manager", "Closure target"),
    ("PPE Compliance", "Safety and Wellbeing", "People wearing full PPE over people on shift.",
     "Shift Report", "HR and QSHE", "PPE target"),
    ("Safety Incidents", "Safety and Wellbeing", "Incidents of the crew on the shift, near misses apart.",
     "Safety Incident", "HR and QSHE", "0"),
    ("Near Misses Reported", "Safety and Wellbeing", "Near misses logged; reporting is encouraged.",
     "Safety Incident", "HR and QSHE", ""),
    ("Housekeeping", "Safety and Wellbeing", "The shifts' housekeeping ratings, averaged.", "Shift Report",
     "HR and QSHE", "Housekeeping target"),
    ("Overtime Hours per Person-Shift", "Safety and Wellbeing", "Overtime hours over person-shifts.",
     "Shift Report", "HR and QSHE", "Fatigue watch"),
    ("Open Grievances", "Employee Relations and Engagement", "Grievances not yet resolved.", "Employee Grievance",
     "HR Manager", "0"),
    ("Repeat Cases", "Employee Relations and Engagement",
     "Cases of employees with two or more in the look back window.", "Disciplinary Case", "HR Manager", "0"),
    ("Legal Flags Open", "Employee Relations and Engagement",
     "Cases past the 15 days, over the suspension cap, sanctioned on a cause that is not conduct, or "
     "unclassified.", "Disciplinary Case", "HR Manager", "0"),
    ("Turnover", "Employee Relations and Engagement", "Exits over active head count; the ceiling pro rated by "
     "months.", "Employee", "HR Manager", "Turnover ceiling"),
    ("Engagement Pulse", "Employee Relations and Engagement", "Pulse surveys of the last three months, averaged.",
     "People Log", "HR Manager", "Pulse target"),
    ("Interventions Overdue", "HR Intervention Effectiveness", "Past their target date and not completed.",
     "HR Intervention", "HR Manager", "0"),
    ("Verified Improvements", "HR Intervention Effectiveness", "Verified, with the KPI moved the right way.",
     "HR Intervention", "HR Manager", ""),
    ("Shift Score", "Production", "Output, waste, complaints, uptime, attendance, safety, housekeeping and PPE, "
     "weighted; a period is scored from its totals.", "Shift Report", "Supervisor and General Manager",
     "Green band"),
    ("Machine Uptime", "Production", "Machine hours less hours lost, over machine hours.", "Shift Report downtime",
     "Production Officer", ""),
    ("HR Excellence Score", "All", "The eight pillars weighted, re-weighted over those with data; red flags "
     "override.", "All of the above", "HR Manager", "Green band"),
)
# (document, who enters, what, when, checked by, how it is used)
GUIDE = (
    ("Plant Day Sheet", "Manufacturing Excellence Officer", "Each section and shift's output, housekeeping, "
     "machines, downtime, waste, complaints and PPE; the people come from the clock.",
     "Every day by 10:00 for the day before", "Production Manager or General Manager",
     "Scorecards, labour cost, supervisor scores, order costing"),
    ("Shift Report", "Manufacturing Excellence Officer", "The detail of a shift: downtime events by machine and "
     "reason, output by order, the crew and who wore PPE.", "With the day sheet", "Production Officer",
     "Downtime analysis, Order Feasibility"),
    ("Disciplinary Case", "Manufacturing Excellence Officer and HR", "The facts, the cause classified first, "
     "quantity and cost, the order and the supervisor on shift; the due process.", "The day it happens",
     "HR Manager", "Fair handling, the case patterns, legal flags"),
    ("People Log", "Manufacturing Excellence Officer", "Toolbox talks, coaching, recognition, suggestions, safety "
     "training, pulse scores, exit talks, with who took part.", "Every week", "HR",
     "Coaching and engagement scores"),
    ("HR Intervention", "HR Manager or HR Business Partner", "Observation, implication, cause, assessment, "
     "intervention, owner, target date, the KPI and its readings, the evidence.",
     "Raised at the Monday meeting, reviewed weekly", "Plant Manager", "What HR does and whether it works"),
    ("Plant Order", "Planning", "Order number, customer, product, finishing section, quantity, value.",
     "When an order is released", "Finance", "Order Feasibility"),
    ("Monday rhythm", "HR Manager", "Open the Manufacturing Excellence page for last week, then the HR Partner "
     "Brief, the Supervisor Scorecard and the case patterns.", "Every Monday", "",
     "One intervention for each red or amber issue; last week's closed"),
)
GOVERNANCE = (
    ("No automatic discipline", "Nothing is applied from a score; the cause is classified first."),
    ("Hearing before dismissal", "A case is heard and the employee represented before a decision (s.66)."),
    ("15 days to impose a penalty", "A conduct case without a decision 15 days after the company became aware is "
     "flagged (s.62(5))."),
    ("Suspension cap", "More than 15 days' suspension in six months is flagged (s.62(4))."),
    ("Sanction on a cause that is not conduct", "A sanction on a case not classified as negligence or misconduct is "
     "flagged."),
    ("Mistakes are not misconduct", "Skills gaps, unclear instructions, inadequate supervision and process failures "
     "go to coaching, training or a process fix."),
    ("Fair comparisons", "The supervisor's people score leaves out output, machines, materials and orders. Output "
     "is compared per person-shift within one unit."),
    ("Confidentiality", "Cases are for HR; names can be hidden in the case reports from the settings."),
    ("Missing data", "Shown as No Data and left out of scores, never taken as poor performance."),
)


# ── Helpers ───────────────────────────────────────────────────────────
def add_months(day, months):
    day = _date(day)
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return datetime.date(year, month, min(day.day, _month_end(year, month).day))


def _month_end(year, month):
    following = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return following - datetime.timedelta(days=1)


def _plain(value):
    if value is None:
        return ""
    return ("%f" % value).rstrip("0").rstrip(".")


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


def _datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    text = str(value).replace("T", " ")
    for size, pattern in ((19, "%Y-%m-%d %H:%M:%S"), (16, "%Y-%m-%d %H:%M"), (10, "%Y-%m-%d")):
        try:
            return datetime.datetime.strptime(text[:size], pattern)
        except ValueError:
            continue
    return None


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
