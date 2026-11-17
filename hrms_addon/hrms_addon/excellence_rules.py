# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence: the rules, without a Frappe import
(scripts/verify_excellence.py). excellence.py reads and writes the site.

Built from the plant's HR Manufacturing Excellence workbook (v3.2, Oct 2026),
batch 8 of the six-files plan, 17 Nov 2026. Decided with the user: a Work
Section master of its own under a plant and a department, with a section on
the Employee.

  Work Section     a production section of a plant: its unit, standard
                   target and crew per shift, machines, approved
                   establishment, labour budget per unit, labour rates and
                   the supervisors who lead its Day and Night shifts
  Shift Report     one per section per shift per day: output, machines and
                   downtime, waste, complaints, safety, staff, absence, PPE
                   and overtime. Its score weighs eight factors
  People Log       coaching, toolbox talks, recognition, suggestions, pulse
                   surveys and HR observations
  HR Intervention  a workforce issue: what was seen, HR's assessment, the
                   intervention, one owner, a target date and the KPI that
                   shows whether it worked
  Disciplinary     the cause is classified first: only negligence and
  Case             deliberate misconduct (or a gross act) go the
                   disciplinary route. The Employment Act's limits are
                   flagged: a penalty within 15 days of becoming aware
                   (s.62(5)), no more than 15 days' suspension in six
                   months (s.62(4))

The HR Excellence score weighs eight pillars. A pillar with no data is left
out and the others re-weighted: "no data" is not poor performance. A safety
incident, an open legal flag or a grievance open too long marks the period
critical whatever the score.

Settings hold percentages as typed (95 for 95%); settings_from turns them
into fractions for the sums.
"""

import datetime

ME_OFFICER = "Manufacturing Excellence Officer"
NEW_ROLES = (ME_OFFICER,)
PERMISSIONS = {}

DAY, NIGHT, BOTH = "Day", "Night", "Both"
SHIFTS = (DAY, NIGHT)
UNITS = ("Kg", "Pcs", "Metres", "Lots", "Jobs")
DIRECT, INDIRECT = "Direct", "Indirect"
LABOUR_TYPES = (DIRECT, INDIRECT)
ON_TARGET, ATTENTION, CRITICAL, NO_DATA = "On Target", "Attention", "Critical", "No Data"
RED_FLAG = "Critical: Red Flag"

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
# machines, materials or orders
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

DOWNTIME_REASONS = ("Mechanical Breakdown", "Electrical Breakdown", "Power Outage", "No Raw Material", "No Order",
                    "No Operator", "Changeover", "Planned Maintenance", "Other")

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
GROSS = "Gross"
SANCTIONED = "Sanctioned"
GRIEVANCE_DONE = ("Resolved", "Closed", "Invalid")

# ── People Log ────────────────────────────────────────────────────────
TOOLBOX, COACHING, RECOGNITION = "Toolbox Talk", "Operator Coaching", "Recognition"
SUGGESTION, IMPLEMENTED = "Employee Suggestion", "Suggestion Implemented"
SAFETY_TRAINING, PULSE = "Safety Training", "Pulse Survey"
LOG_TYPES = (TOOLBOX, COACHING, RECOGNITION, SUGGESTION, IMPLEMENTED, SAFETY_TRAINING, "Supervisor Coaching Received",
             "Leadership Development", PULSE, "HR Observation", "Exit Interview")
COACHING_TYPES = (TOOLBOX, COACHING, RECOGNITION)

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
}
# typed as percentages, used as fractions
PERCENT_KEYS = ("attendance_target", "unauthorised_ceiling", "overtime_ceiling", "ppe_target", "staffing_low",
                "staffing_high", "coverage_target", "closure_target", "pulse_target", "turnover_ceiling",
                "reporting_target")


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


# ── One shift ─────────────────────────────────────────────────────────
def rag(score, s):
    if score is None:
        return NO_DATA
    if score >= s["green_from"]:
        return ON_TARGET
    if score >= s["amber_from"]:
        return ATTENTION
    return CRITICAL


def entry_errors(entry):
    """Problems with a shift report as typed."""
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
    if _num(entry.get("stop_hours")) and not entry.get("downtime_reason"):
        errors.append("Give the main downtime reason for the stopped hours.")
    for field, label in (("actual_output", "Output"), ("waste_qty", "Waste Quantity"), ("waste_value", "Waste Value"),
                         ("complaint_value", "Complaint Value"), ("stop_hours", "Stopped Hours"),
                         ("ot_hours", "Overtime Hours"), ("housekeeping", "Housekeeping")):
        if _num(entry.get(field)) < 0:
            errors.append("{0} cannot be negative.".format(label))
    return errors


def shift_figures(entry, section, s):
    """Everything a shift report works out, from what was typed, its section
    and the settings. The workbook's Daily Entry, column for column."""
    section = section or {}
    hours = _num(s["shift_hours"])
    machines = int(_num(entry.get("machines")))
    running = entry.get("machines_running")
    running = machines if running in (None, "") else int(_num(running))
    actual, target = _num(entry.get("actual_output")), _num(entry.get("target"))
    planned, on_shift = int(_num(entry.get("staff_planned"))), int(_num(entry.get("staff_on_shift")))
    wearing, unauthorised = int(_num(entry.get("wearing_ppe"))), int(_num(entry.get("unauthorised_absent")))
    rate, ot_rate = _num(section.get("labour_rate")), _num(section.get("overtime_rate"))
    crew, budget_rate = int(_num(section.get("crew_per_shift"))), _num(section.get("labour_budget_per_unit"))

    machine_hours = machines * hours
    hours_lost = max(0, machines - running) * hours + _num(entry.get("stop_hours"))
    uptime = 1.0 if not machine_hours else max(0.0, 1 - hours_lost / machine_hours)
    achievement = actual / target if target else 0.0
    attendance = on_shift / float(planned) if planned else 0.0
    ppe = wearing / float(on_shift) if on_shift else 0.0
    regular = on_shift * rate
    ot_cost = _num(entry.get("ot_hours")) * ot_rate
    labour = regular + ot_cost
    absent = max(0, planned - on_shift)
    shifts = _num(s["shifts_per_week"]) or 1
    waste_cap, complaint_cap = _num(s["waste_limit"]) / shifts, _num(s["complaint_limit"]) / shifts

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
    score = sum(_num(s["weight_" + key]) * factors[key] for key in FACTOR_KEYS) / 100.0
    weakest = min(FACTOR_KEYS, key=lambda key: (factors[key], FACTOR_KEYS.index(key)))
    return {
        "machines_running": running, "machine_hours": machine_hours, "hours_lost": hours_lost,
        "uptime": uptime, "achievement": achievement, "attendance": attendance, "ppe_rate": ppe,
        "not_wearing": max(0, on_shift - wearing), "regular_labour": regular, "ot_cost": ot_cost,
        "labour_cost": labour, "labour_per_unit": labour / actual if actual else None,
        "machine_use": (running / float(machines)) if machines else None,
        "output_per_person": actual / on_shift if actual and on_shift else None,
        "absent": absent, "required_crew": crew, "adequacy": on_shift / float(crew) if crew else None,
        "labour_budget": actual * budget_rate, "absence_cost": max(0, absent - unauthorised) * rate,
        "factors": factors, "score": round(score, 1), "status": rag(round(score, 1), s), "weakest": weakest,
        "weakest_action": FACTOR_ACTIONS[weakest],
    }


def labour_rates(gross, heads, s):
    """(a person-shift's labour cost, an overtime hour's): a month's gross pay
    over the people paid and the paid days; overtime at the multiplier."""
    if not heads or not _num(s["paid_days"]):
        return 0.0, 0.0
    rate = _num(gross) / float(heads) / _num(s["paid_days"])
    return round(rate, 2), round(rate / _num(s["ot_base_hours"]) * _num(s["ot_multiplier"]), 2)


# ── A period: the sums the scorecards read ────────────────────────────
SUMMED = ("on_shift", "planned", "required", "unauthorised", "late", "early", "wearing", "incidents", "near_misses",
          "ot_hours", "labour", "ot_cost", "budgeted_labour", "budget", "absence_cost", "waste", "complaints",
          "machine_hours", "hours_lost", "target", "actual")


def totals(rows, s):
    """The sums over shift reports: each row is one report's typed values with
    its worked figures (the fields excellence.py reads back)."""
    t = {key: 0.0 for key in SUMMED}
    t.update({"count": 0, "below_band": 0, "score": 0.0, "factors": {key: 0.0 for key in FACTOR_KEYS},
              "by_unit": {}, "downtime": {}})
    for row in rows or ():
        t["count"] += 1
        on_shift, required = _num(row.get("staff_on_shift")), _num(row.get("required_crew"))
        t["on_shift"] += on_shift
        t["planned"] += _num(row.get("staff_planned"))
        t["required"] += required
        t["unauthorised"] += _num(row.get("unauthorised_absent"))
        t["late"] += _num(row.get("late_arrivals"))
        t["early"] += _num(row.get("early_departures"))
        t["wearing"] += _num(row.get("wearing_ppe"))
        t["incidents"] += _num(row.get("safety_incidents"))
        t["near_misses"] += _num(row.get("near_misses"))
        t["ot_hours"] += _num(row.get("ot_hours"))
        t["labour"] += _num(row.get("labour_cost"))
        t["ot_cost"] += _num(row.get("ot_cost"))
        if _num(row.get("labour_budget")) > 0:
            t["budgeted_labour"] += _num(row.get("labour_cost"))
            t["budget"] += _num(row.get("labour_budget"))
        t["absence_cost"] += _num(row.get("absence_cost"))
        t["waste"] += _num(row.get("waste_value"))
        t["complaints"] += _num(row.get("complaint_value"))
        t["machine_hours"] += _num(row.get("machine_hours"))
        t["hours_lost"] += _num(row.get("hours_lost"))
        t["target"] += _num(row.get("target"))
        t["actual"] += _num(row.get("actual_output"))
        t["score"] += _num(row.get("score"))
        if required and on_shift / required < s["staffing_low"]:
            t["below_band"] += 1
        for key in FACTOR_KEYS:
            t["factors"][key] += _num(row.get("factor_" + key))
        unit = row.get("unit") or ""
        made = t["by_unit"].setdefault(unit, {"actual": 0.0, "on_shift": 0.0, "labour": 0.0, "target": 0.0})
        made["actual"] += _num(row.get("actual_output"))
        made["on_shift"] += on_shift
        made["labour"] += _num(row.get("labour_cost"))
        made["target"] += _num(row.get("target"))
        reason = row.get("downtime_reason")
        if reason and _num(row.get("hours_lost")):
            t["downtime"][reason] = t["downtime"].get(reason, 0.0) + _num(row.get("hours_lost"))
    return t


def ratio(part, whole):
    return part / float(whole) if whole else None


def averages(t):
    """The averages of a period's sums: scores out of 100, rates as fractions."""
    count = t["count"]
    factors = {key: (t["factors"][key] / count if count else None) for key in FACTOR_KEYS}
    weakest = (min(FACTOR_KEYS, key=lambda key: (factors[key], FACTOR_KEYS.index(key))) if count else None)
    return {
        "score": round(t["score"] / count, 1) if count else None,
        "factors": factors, "weakest": weakest,
        "achievement": ratio(t["actual"], t["target"]),
        "uptime": (1 - t["hours_lost"] / t["machine_hours"]) if t["machine_hours"] else (1.0 if count else None),
        "attendance": ratio(t["on_shift"], t["planned"]),
        "unauthorised": ratio(t["unauthorised"], t["planned"]),
        "ppe": ratio(t["wearing"], t["on_shift"]),
        "deployment": ratio(t["on_shift"], t["required"]),
        "ot_share": ratio(t["ot_cost"], t["labour"]),
        "budget_variance": (t["budgeted_labour"] / t["budget"] - 1) if t["budget"] else None,
        "fatigue": ratio(t["ot_hours"], t["on_shift"]),
        "money_lost": t["waste"] + t["complaints"],
        "top_downtime": (max(sorted(t["downtime"]), key=lambda reason: t["downtime"][reason])
                         if t["downtime"] else None),
    }


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


def supervisor_index(facts, s):
    """The supervisor's eight people-management parts and their index. `facts`:
    "totals" (their shift reports'), "due" (shift reports due from them),
    "conduct_cases", "interventions_due", "interventions_on_time", "sessions",
    "supervisors", "weeks"."""
    t = facts["totals"]
    a = averages(t)
    has = bool(t["count"])
    parts = {
        "reporting": capped(t["count"], facts.get("due")) if facts.get("due") else None,
        "attendance": attendance_part(a["attendance"], a["unauthorised"], s),
        "ppe": capped(a["ppe"], s["ppe_target"]),
        "safety": a["factors"]["safety"],
        "housekeeping": a["factors"]["housekeeping"],
        "conduct": conduct_part(facts.get("conduct_cases") or 0, s, has),
        "closure": closure_part(facts.get("interventions_due") or 0, facts.get("interventions_on_time") or 0),
        "coaching": coaching_part(facts.get("sessions") or 0, facts.get("supervisors") or 1, facts.get("weeks") or 0,
                                  s, has),
    }
    index, share = weighted(parts, {key: s["sup_" + key] for key in SUPERVISOR_KEYS})
    return {"parts": parts, "index": index, "share": share, "status": rag(index, s)}


def pillars(facts, s):
    """The HR Excellence scorecard for a period. `facts`:
      totals             shift reports' totals()
      headcount, establishment, direct_share
      coverage           (done, required) of the people's required training
      due_reports        shift reports due in the period so far
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
    a = averages(t)
    has = bool(t["count"])
    supervision = supervisor_index({
        "totals": t, "due": facts.get("due_reports"), "conduct_cases": facts.get("conduct_cases"),
        "interventions_due": facts.get("interventions_due"),
        "interventions_on_time": facts.get("interventions_on_time"), "sessions": facts.get("sessions"),
        "supervisors": facts.get("supervisors"), "weeks": facts.get("weeks")}, s)
    done, required = facts.get("coverage") or (0, 0)
    coverage = ratio(done, required)
    # the skills assessed on the floor, all and critical (competency.py)
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
        "safety": [capped(a["ppe"], s["ppe_target"]), a["factors"]["safety"], a["factors"]["housekeeping"],
                   fatigue_part(a["fatigue"], s)],
        "relations": [relations, capped(pulse, s["pulse_target"]) if pulse is not None else None],
        "interventions": [effectiveness],
    }
    scores = {key: _average(parts[key]) for key in PILLAR_KEYS}
    composite, share = weighted(scores, {key: s["pillar_" + key] for key in PILLAR_KEYS})
    flags = red_flags(facts, t, s)
    status = NO_DATA if composite is None else (RED_FLAG if flags else rag(composite, s))
    months = facts.get("months") or 1
    turnover = ratio(facts.get("exits") or 0, headcount) if headcount else None
    kpis = {
        "planning": [
            ("Active Head Count", headcount, None, None),
            ("Approved Establishment", establishment, None, None),
            ("Variance", headcount - establishment, 0,
             _check(abs(headcount - establishment) <= establishment * 0.05) if establishment else NO_DATA),
            ("Deployment (on shift over crew)", a["deployment"], s["staffing_low"],
             _check(a["deployment"] is not None and s["staffing_low"] <= a["deployment"] <= s["staffing_high"])
             if a["deployment"] is not None else NO_DATA),
            ("Shifts Below the Staffing Band", t["below_band"] if has else None, 0,
             _check(t["below_band"] == 0) if has else NO_DATA),
            ("Direct Labour Share", facts.get("direct_share"), None, None),
        ],
        "productivity": [
            ("Output per Person-Shift (Kg)", _per(t, "Kg", "actual", "on_shift"), None, None),
            ("Output per Person-Shift (Pcs)", _per(t, "Pcs", "actual", "on_shift"), None, None),
            ("Labour Cost per Kg", _per(t, "Kg", "labour", "actual"), None, None),
            ("Total Labour Cost", t["labour"] if has else None, None, None),
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
            ("Unauthorised Absence", a["unauthorised"], s["unauthorised_ceiling"],
             _check(a["unauthorised"] <= s["unauthorised_ceiling"]) if a["unauthorised"] is not None else NO_DATA),
            ("Late Arrivals and Early Departures", (t["late"] + t["early"]) if has else None, None, None),
            ("Shift Reports Entered", ratio(t["count"], facts.get("due_reports")) if facts.get("due_reports")
             else None, s["reporting_target"],
             _check(t["count"] >= s["reporting_target"] * facts["due_reports"]) if facts.get("due_reports")
             else NO_DATA),
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
            ("Safety Incidents", t["incidents"] if has else None, 0,
             _check(t["incidents"] == 0) if has else NO_DATA),
            ("Near Misses Reported", t["near_misses"] if has else None, None, None),
            ("Housekeeping", (a["factors"]["housekeeping"] / 100.0) if has else None, None, None),
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
            "supervision": supervision}


def red_flags(facts, t, s):
    """What marks a period critical whatever its score."""
    flags = []
    if t["count"] and t["incidents"] >= max(1, s["red_flag_safety"]):
        flags.append("{0} safety incident(s)".format(int(t["incidents"])))
    if facts.get("legal_flags"):
        flags.append("{0} case(s) with a legal flag".format(facts["legal_flags"]))
    if facts.get("grievances_open_long"):
        flags.append("{0} grievance(s) open over {1} days".format(facts["grievances_open_long"], int(s["case_days"])))
    return flags


def _per(t, unit, top, bottom):
    made = t["by_unit"].get(unit)
    return ratio(made[top], made[bottom]) if made else None


def _check(ok):
    return "On Target" if ok else "Needs Attention"


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


def case_flags(case, today, s, before=0):
    """The legal flags on a case, as short messages: the 15-day limit, the
    suspension cap, a sanction on a cause that is not conduct, a decision
    with no cause."""
    flags = []
    today = _date(today)
    due = penalty_due_by(case.get("aware_on"), s)
    decided = _date(case.get("decided_on"))
    sanctioned = case.get("outcome") == SANCTIONED
    if due and not decided and today and today > due and case.get("status") not in ("Closed", "Cancelled"):
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


def repeat_cases(cases, as_on, months):
    """Employees with two cases or more in the look-back window to `as_on`:
    {employee: {"cases", "conduct", "causes": {cause: n}, "cost", "last"}}."""
    as_on = _date(as_on)
    since = add_months(as_on, -int(months))
    found = {}
    for case in cases or ():
        day = _date(case.get("incident_date"))
        if not day or not (since < day <= as_on):
            continue
        row = found.setdefault(case.get("employee"), {"cases": 0, "conduct": 0, "causes": {}, "cost": 0.0,
                                                      "last": None, "last_case": None})
        row["cases"] += 1
        if is_conduct(case.get("cause"), case.get("severity")):
            row["conduct"] += 1
        cause = case.get("cause") or "Not Classified"
        row["causes"][cause] = row["causes"].get(cause, 0) + 1
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


# ── Work Section ──────────────────────────────────────────────────────
def section_errors(section):
    errors = []
    for field, label in (("target_per_shift", "Target per Shift"), ("crew_per_shift", "Crew per Shift"),
                         ("machines", "Machines"), ("approved_establishment", "Approved Establishment"),
                         ("labour_budget_per_unit", "Labour Budget per Unit"), ("labour_rate", "Labour Rate"),
                         ("overtime_rate", "Overtime Rate")):
        if _num(section.get(field)) < 0:
            errors.append("{0} cannot be negative.".format(label))
    seen = set()
    for row in section.get("supervisors") or ():
        key = (row.get("employee"), row.get("shift"))
        if key in seen:
            errors.append("{0} is listed twice for the {1} shift.".format(row.get("employee"), row.get("shift")))
        seen.add(key)
    return errors


def lead_supervisor(supervisors, shift):
    """Who leads a shift: the first active supervisor on it, else the first
    active one of the section."""
    active = [row for row in supervisors or () if int(_num(row.get("active", 1)))]
    for row in active:
        if row.get("shift") == shift:
            return row.get("employee")
    return active[0].get("employee") if active else None


def leads(supervisors):
    """{(shift): employee} for the shifts a section's supervisors lead."""
    return {shift: lead_supervisor(supervisors, shift) for shift in SHIFTS
            if any(row.get("shift") == shift for row in supervisors or ()
                   if int(_num(row.get("active", 1))))}


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


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
