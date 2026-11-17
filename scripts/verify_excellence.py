"""Verify Manufacturing Excellence (batch 8, 17 Nov 2026), without a bench:

    python scripts/verify_excellence.py

The plant's HR Manufacturing Excellence workbook (v3.2) on the desk: a Work Section master under a plant and a
department (decided with the user), a Shift Report per section, shift and day with its weighted score, the People
Log, the HR Intervention register, the cause of a disciplinary case with the Employment Act's limits, and the
HR Excellence, shift and supervisor scorecards.

  1  the rules: the settings, weeks and periods, a shift's figures (the workbook's own demo row), the period's
     sums, the eight pillars and the supervisor's index, the case's cause and legal flags, repeat cases, an
     intervention's state, a section's roster
  2  the paper: every field the rules, the glue and the reports name is on its doctype, every list the same
  3  the glue: what it fills, what it refuses, who may ask it
  4  wiring: the hooks, the Employee's section, the reports' roles
"""
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []
D = datetime.date


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def options(name, field):
    return [option for option in (fields(name)[field].get("options") or "").split("\n") if option]


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


def near(value, expected, tolerance=0.05):
    return value is not None and abs(value - expected) <= tolerance


R = load("excellence_rules")
S = R.settings_from({})

# ── 1. The rules ──────────────────────────────────────────────────────
check("settings: the workbook's weights by default",
      [S["weight_" + key] for key in R.FACTOR_KEYS] == [25, 15, 10, 12, 8, 10, 8, 12]
      and [S["pillar_" + key] for key in R.PILLAR_KEYS] == [15, 20, 15, 15, 15, 10, 5, 5]
      and [S["sup_" + key] for key in R.SUPERVISOR_KEYS] == [15, 15, 15, 15, 10, 10, 10, 10])
check("settings: green from 90, amber from 75", (S["green_from"], S["amber_from"]) == (90, 75))
check("settings: percentages become fractions", near(S["attendance_target"], 0.95, 1e-9)
      and near(S["staffing_low"], 0.9, 1e-9) and near(S["overtime_ceiling"], 0.08, 1e-9))
check("settings: a value saved as 0 stays 0, one never saved takes its default",
      R.settings_from({"weight_complaints": 0})["weight_complaints"] == 0
      and R.settings_from({"weight_complaints": None})["weight_complaints"] == 10)
check("settings: the defaults are clean", R.settings_errors({}) == [], R.settings_errors({}))
check("settings: weights must total 100", any("Shift score" in error for error in R.settings_errors({"weight_output": 30})))
check("settings: a weight cannot be negative",
      any("negative" in error for error in R.settings_errors({"pillar_skills": -5, "pillar_safety": 30})))
check("settings: green above amber", any("Green" in error for error in R.settings_errors({"green_from": 70})))
check("settings: the staffing band the right way round",
      any("staffing" in error for error in R.settings_errors({"staffing_low": 120})))
check("settings: a shift has hours", any("Hours per Shift" in error for error in R.settings_errors({"shift_hours": 0})))

check("weeks: week 1 starts on the year's first Monday", R.first_monday(2026) == D(2026, 1, 5)
      and R.first_monday(2024) == D(2024, 1, 1))
check("weeks: 2 Nov 2026 is W44, as on the plant's dashboards", R.week_of(D(2026, 11, 2)) == (2026, 44)
      and R.week_label(D(2026, 11, 8)) == "2026-W44" and R.week_label(D(2026, 11, 9)) == "2026-W45")
check("weeks: a day before the first Monday is the year before's", R.week_of(D(2026, 1, 4)) == (2025, 52))
check("periods: a week, a month, a quarter",
      R.period_bounds(R.WEEK, 2026, 44) == (D(2026, 11, 2), D(2026, 11, 8))
      and R.period_bounds(R.MONTH, 2026, "February") == (D(2026, 2, 1), D(2026, 2, 28))
      and R.period_bounds(R.MONTH, 2026, 12) == (D(2026, 12, 1), D(2026, 12, 31))
      and R.period_bounds(R.QUARTER, 2026, "Q4") == (D(2026, 10, 1), D(2026, 12, 31)))
check("periods: six working days a week", R.working_days(D(2026, 11, 2), D(2026, 11, 8), 6) == 6
      and R.working_days(D(2026, 11, 2), D(2026, 11, 15), 6) == 12 and R.working_days(D(2026, 11, 9), D(2026, 11, 2)) == 0)

# the workbook's demo row 5: Extrusion, Day shift, 2 Nov 2026
SECTION = {"labour_rate": 20000.0, "overtime_rate": 3750.0, "crew_per_shift": 46,
           "labour_budget_per_unit": 200}
ENTRY = {"target": 8000, "actual_output": 7173, "housekeeping": 88, "machines": 12, "machines_running": 11,
         "stop_hours": 2, "downtime_reason": "No Order", "waste_value": 217000, "complaint_value": 0,
         "safety_incidents": 0, "near_misses": 1, "staff_planned": 46, "staff_on_shift": 44, "unauthorised_absent": 0,
         "late_arrivals": 1, "early_departures": 1, "wearing_ppe": 44, "ot_hours": 24}
F = R.shift_figures(ENTRY, SECTION, S)
check("shift: machine hours and the hours lost", (F["machine_hours"], F["hours_lost"]) == (144, 14),
      (F["machine_hours"], F["hours_lost"]))
check("shift: the eight factors as the workbook's", near(F["factors"]["output"], 89.6625, 1e-6)
      and F["factors"]["waste"] == 0 and F["factors"]["complaints"] == 100
      and near(F["factors"]["uptime"], 90.2778, 1e-3) and near(F["factors"]["attendance"], 95.6522, 1e-3)
      and F["factors"]["safety"] == 100 and F["factors"]["housekeeping"] == 88 and F["factors"]["ppe"] == 100,
      F["factors"])
check("shift: the score 79.9, Attention, waste its weakest", (F["score"], F["status"], F["weakest"])
      == (79.9, R.ATTENTION, "waste"), (F["score"], F["status"], F["weakest"]))
check("shift: labour cost, its budget and the paid absence", near(F["labour_cost"], 970000, 0.01)
      and F["labour_budget"] == 1434600 and near(F["absence_cost"], 40000, 0.01), F["labour_cost"])
check("shift: per unit, per person, staffing adequacy", near(F["labour_per_unit"], 135.23, 0.01)
      and near(F["output_per_person"], 163.02, 0.01) and near(F["adequacy"], 44 / 46.0, 1e-9))
check("shift: Machines Running left empty means all of them", R.shift_figures(
    dict(ENTRY, machines_running=None, stop_hours=0), SECTION, S)["hours_lost"] == 0)
check("shift: a section with no machines is never down",
      R.shift_figures(dict(ENTRY, machines=0, machines_running=0, stop_hours=0), SECTION, S)["factors"]["uptime"] == 100)
check("shift: each safety incident takes 25 points",
      R.shift_figures(dict(ENTRY, safety_incidents=2), SECTION, S)["factors"]["safety"] == 50)
check("shift: a quarter of the week's waste limit in a week is 75 points a shift on average",
      near(R.shift_figures(dict(ENTRY, waste_value=1000000 / 12.0 / 4), SECTION, S)["factors"]["waste"], 75, 1e-6))
check("shift: green from 90", R.rag(90, S) == R.ON_TARGET and R.rag(89.9, S) == R.ATTENTION
      and R.rag(74.9, S) == R.CRITICAL and R.rag(None, S) == R.NO_DATA)
check("shift: what it refuses", len(R.entry_errors({"machines": 3, "machines_running": 4, "staff_on_shift": 5,
                                                    "wearing_ppe": 6, "staff_planned": 5, "unauthorised_absent": 1,
                                                    "housekeeping": 101, "stop_hours": 2})) == 5,
      R.entry_errors({"machines": 3, "machines_running": 4, "staff_on_shift": 5, "wearing_ppe": 6, "staff_planned": 5,
                      "unauthorised_absent": 1, "housekeeping": 101, "stop_hours": 2}))
check("shift: a clean report has no errors", R.entry_errors(ENTRY) == [], R.entry_errors(ENTRY))
check("labour rates: gross over people over paid days; overtime at 1.5 the hour",
      R.labour_rates(52000000, 100, S) == (20000.0, 3750.0), R.labour_rates(52000000, 100, S))


def stored(entry, section, unit="Kg", **extra):
    """A Shift Report as the glue saves it."""
    figures = R.shift_figures(entry, section, S)
    row = dict(entry, unit=unit, score=figures["score"], labour_cost=figures["labour_cost"],
               ot_cost=figures["ot_cost"], labour_budget=figures["labour_budget"],
               absence_cost=figures["absence_cost"], machine_hours=figures["machine_hours"],
               hours_lost=figures["hours_lost"], required_crew=figures["required_crew"])
    row.update({"factor_" + key: value for key, value in figures["factors"].items()})
    row.update(extra)
    return row


NIGHT = dict(ENTRY, actual_output=6784, housekeeping=75, stop_hours=1, downtime_reason="No Raw Material", waste_value=623000,
             late_arrivals=2, early_departures=0, ot_hours=0, staff_on_shift=40, wearing_ppe=38, unauthorised_absent=2)
check("shift: only authorised absence is paid", near(R.shift_figures(NIGHT, SECTION, S)["absence_cost"],
                                                     4 * SECTION["labour_rate"], 0.01))
ROWS = [stored(ENTRY, SECTION), stored(NIGHT, SECTION)]
T = R.totals(ROWS, S)
A = R.averages(T)
check("period: the sums", (T["count"], T["on_shift"], T["planned"], T["wearing"], T["unauthorised"])
      == (2, 84, 92, 82, 2), (T["count"], T["on_shift"], T["planned"], T["wearing"], T["unauthorised"]))
check("period: attendance, PPE, deployment as fractions", near(A["attendance"], 84 / 92.0, 1e-9)
      and near(A["ppe"], 82 / 84.0, 1e-9) and near(A["deployment"], 84 / 92.0, 1e-9))
check("period: the main downtime reason is where most machine hours went", A["top_downtime"] == "No Order",
      T["downtime"])
check("period: overtime as a share of labour", near(A["ot_share"], T["ot_cost"] / T["labour"], 1e-12))
check("period: a shift below the staffing band", T["below_band"] == 1, T["below_band"])
check("period: labour against budget only where there is a budget", near(
    R.averages(R.totals(ROWS + [stored(ENTRY, dict(SECTION, labour_budget_per_unit=0))], S))["budget_variance"],
    A["budget_variance"], 1e-12))
check("period: no shifts, no averages", R.averages(R.totals([], S))["attendance"] is None
      and R.averages(R.totals([], S))["score"] is None)

check("parts: attendance less ten points a point of unauthorised absence over 1%",
      near(R.attendance_part(0.90, 0.0, S), 94.74, 0.01) and near(R.attendance_part(0.90, 0.02, S), 84.74, 0.01)
      and R.attendance_part(None, 0, S) is None)
check("parts: deployment 100 inside the band, four points a point outside",
      R.deployment_part(1.0, S) == 100 and near(R.deployment_part(0.8, S), 60) and near(R.deployment_part(1.2, S), 60))
check("parts: head count against the establishment", near(R.establishment_part(90, 100), 80)
      and R.establishment_part(5, 0) is None)
check("parts: labour over budget, overtime over its ceiling, fatigue", near(R.budget_part(0.1), 80)
      and R.budget_part(-0.05) == 100 and near(R.overtime_part(0.10, S), 90) and R.overtime_part(0.05, S) == 100
      and near(R.fatigue_part(2.0, S), 75) and R.fatigue_part(1.0, S) == 100)
check("parts: coaching against a session per supervisor per week", near(R.coaching_part(2, 2, 2, S), 50)
      and R.coaching_part(9, 1, 1, S) == 100 and R.coaching_part(1, 1, 1, S, has_shifts=False) is None)
check("parts: 25 off for each case put down to supervision", R.conduct_part(2, S) == 50 and R.conduct_part(5, S) == 0)
check("parts: re-weighted over the parts with data", R.weighted({"a": 80, "b": None}, {"a": 10, "b": 30})
      == (80.0, 0.25) and R.weighted({"a": None}, {"a": 10}) == (None, 0.0))

FACTS = {"totals": T, "headcount": 90, "establishment": 100, "direct_share": 1.0, "coverage": (40, 50),
         "due_reports": 2, "conduct_cases": 0, "sessions": 2, "supervisors": 2, "weeks": 1,
         "interventions_due": 2, "interventions_on_time": 2, "interventions_closed": 2, "interventions_improved": 1,
         "open_grievances": 0, "legal_flags": 0, "overdue_cases": 0, "pulse": 0.7, "exits": 1, "months": 0.23}
CARD = R.pillars(FACTS, S)
SCORES = {pillar["key"]: pillar["score"] for pillar in CARD["pillars"]}
check("pillars: all eight scored when everything has data", all(SCORES[key] is not None for key in R.PILLAR_KEYS),
      SCORES)
check("pillars: skills is the share of required training done against 80%", SCORES["skills"] == 100.0
      and R.pillars(dict(FACTS, coverage=(30, 50)), S)["pillars"][3]["score"] == 75.0)
check("pillars: interventions weigh closure 60 and verified improvement 40",
      SCORES["interventions"] == 80.0, SCORES["interventions"])
check("pillars: relations is 100 less 10 a grievance, 15 a legal flag, 5 an overdue case, beside the pulse",
      R.pillars(dict(FACTS, open_grievances=1, legal_flags=1, overdue_cases=1, pulse=None), S)["pillars"][6]["score"]
      == 70.0)
check("pillars: the composite weighs the pillars", near(CARD["composite"], sum(
    SCORES[key] * S["pillar_" + key] for key in R.PILLAR_KEYS) / 100.0, 0.1) and near(CARD["share"], 1.0, 1e-9))
EMPTY = R.pillars({"totals": R.totals([], S)}, S)
check("pillars: no data is not poor performance", [pillar["key"] for pillar in EMPTY["pillars"]
                                                   if pillar["score"] is not None] == ["relations"]
      and EMPTY["composite"] == 100.0 and near(EMPTY["share"], 0.05, 1e-9), EMPTY["pillars"])
UNSAFE = R.pillars(dict(FACTS, totals=R.totals([stored(dict(ENTRY, safety_incidents=1), SECTION)], S)), S)
check("pillars: a safety incident marks the period critical whatever the score",
      UNSAFE["status"] == R.RED_FLAG and UNSAFE["red_flags"], UNSAFE["status"])
check("pillars: an open legal flag or a grievance open too long is a red flag too",
      len(R.pillars(dict(FACTS, legal_flags=1, grievances_open_long=2), S)["red_flags"]) == 2)
check("pillars: every KPI row is (label, value, target, status)",
      all(len(row) == 4 for rows in CARD["kpis"].values() for row in rows) and set(CARD["kpis"]) == set(R.PILLAR_KEYS))
SUP = R.supervisor_index({"totals": T, "due": 4, "conduct_cases": 1, "sessions": 1, "supervisors": 1, "weeks": 1,
                          "interventions_due": 0}, S)
check("supervisor: reporting is reports over those due", SUP["parts"]["reporting"] == 50.0, SUP["parts"])
check("supervisor: no intervention due leaves closure out", SUP["parts"]["closure"] is None
      and near(SUP["share"], 0.9, 1e-9))
check("supervisor: no shift due leaves reporting out",
      R.supervisor_index({"totals": T, "due": 0}, S)["parts"]["reporting"] is None)

check("cause: only negligence, misconduct or a gross act go the disciplinary route",
      R.is_conduct(R.NEGLIGENCE) and R.is_conduct(R.MISCONDUCT) and R.is_conduct("Operational Mistake", "Gross")
      and not R.is_conduct("Skills Gap") and not R.is_conduct(None))
check("cause: each has its route", R.route_for("System or Process Failure").startswith("Fix the process")
      and R.route_for(None) == "" and R.route_for("Skills Gap", "Gross") == R.ROUTES[R.MISCONDUCT])
check("cause: the case doctype's causes are the rules'", options("Disciplinary Case", "cause") == list(R.CAUSE_NAMES))
check("15 days: a penalty is due 15 days after becoming aware", R.penalty_due_by(D(2026, 11, 1), S) == D(2026, 11, 16)
      and R.penalty_due_by(None, S) is None)
OPEN_CASE = {"aware_on": D(2026, 11, 1), "status": "Under Investigation"}
check("15 days: an open case past them is flagged",
      any("s.62(5)" in flag for flag in R.case_flags(OPEN_CASE, D(2026, 11, 17), S))
      and R.case_flags(OPEN_CASE, D(2026, 11, 16), S) == [])
check("15 days: a closed case is not chased", R.case_flags(dict(OPEN_CASE, status="Closed"), D(2026, 12, 1), S) == [])
check("15 days: a penalty decided after them is flagged",
      any("after" in flag for flag in R.case_flags(dict(OPEN_CASE, decided_on=D(2026, 11, 20), outcome=R.SANCTIONED,
                                                         cause=R.NEGLIGENCE), D(2026, 11, 20), S)))
check("suspension: days in the six months before count against the 15",
      R.suspended_before([{"name": "A", "suspension_from": D(2026, 8, 1), "suspension_days": 10},
                          {"name": "B", "suspension_from": D(2026, 1, 1), "suspension_days": 14},
                          {"name": "C", "suspension_from": D(2026, 11, 1), "suspension_days": 3}],
                         D(2026, 11, 1), S, exclude="C") == 10)
check("suspension: over 15 days in six months is flagged",
      any("s.62(4)" in flag for flag in R.case_flags({"suspension_days": 6, "suspension_from": D(2026, 11, 1)},
                                                     D(2026, 11, 1), S, before=10))
      and not R.case_flags({"suspension_days": 5, "suspension_from": D(2026, 11, 1)}, D(2026, 11, 1), S, before=10))
check("cause: a sanction on a cause that is not conduct is flagged, a decision with no cause too",
      "Sanction on a cause that is not conduct" in R.case_flags(
          {"outcome": R.SANCTIONED, "cause": "Skills Gap", "decided_on": D(2026, 11, 2), "aware_on": D(2026, 11, 1)},
          D(2026, 11, 2), S)
      and "Cause not classified" in R.case_flags({"outcome": "Pardoned", "decided_on": D(2026, 11, 2)},
                                                 D(2026, 11, 2), S))
CASES = [{"name": "C1", "employee": "E1", "incident_date": D(2026, 3, 1), "cause": R.NEGLIGENCE, "case_cost": 1000},
         {"name": "C2", "employee": "E1", "incident_date": D(2026, 10, 1), "cause": "Skills Gap", "case_cost": 500},
         {"name": "C3", "employee": "E2", "incident_date": D(2026, 10, 2), "cause": R.NEGLIGENCE},
         {"name": "C4", "employee": "E2", "incident_date": D(2025, 1, 2), "cause": R.NEGLIGENCE}]
REPEATS = R.repeat_cases(CASES, D(2026, 11, 17), 12)
check("repeat cases: two in the window, the older one outside it not counted", set(REPEATS) == {"E1"}
      and REPEATS["E1"]["cases"] == 2 and REPEATS["E1"]["conduct"] == 1 and REPEATS["E1"]["cost"] == 1500
      and REPEATS["E1"]["last_case"] == "C2", REPEATS)

ROW = {"raised_on": D(2026, 10, 12), "target_date": D(2026, 11, 13), "status": R.IN_PROGRESS,
       "kpi": "Overtime % of Labour Cost", "baseline": 0.11, "latest": 0.09}
STATE = R.intervention_state(ROW, D(2026, 11, 17))
check("intervention: overtime down is an improvement", (STATE["change"], STATE["result"]) == (-0.02, R.IMPROVED),
      STATE)
check("intervention: attendance down is not", R.intervention_state(dict(ROW, kpi="Attendance %"), D(2026, 11, 1))[
    "result"] == R.WORSE)
check("intervention: past its target date and still open is overdue", STATE["overdue"] == 1 and STATE["days_open"] == 36)
DONE = R.intervention_state(dict(ROW, status=R.CLOSED, closed_on=D(2026, 11, 10)), D(2026, 11, 17))
check("intervention: closed by its date is on time, and no longer overdue",
      (DONE["on_time"], DONE["overdue"], DONE["days_open"]) == ("Yes", 0, 29), DONE)
check("intervention: closed after it is late",
      R.intervention_state(dict(ROW, status=R.COMPLETED, closed_on=D(2026, 11, 14)), D(2026, 11, 17))["on_time"]
      == "Late")
check("intervention: what it refuses", len(R.intervention_errors(
    {"raised_on": D(2026, 11, 5), "target_date": D(2026, 11, 1), "status": R.CLOSED, "closed_on": D(2026, 11, 2)}))
      == 3 and R.intervention_errors({"status": R.OPEN, "verified": 1}) == ["Only a completed intervention is verified."])

ROSTER = [{"employee": "S1", "shift": "Day", "active": 0}, {"employee": "S2", "shift": "Day", "active": 1},
          {"employee": "S3", "shift": "Day", "active": 1}]
check("roster: the first active supervisor on the shift leads it", R.lead_supervisor(ROSTER, "Day") == "S2")
check("roster: with nobody on the shift, the section's first active", R.lead_supervisor(ROSTER, "Night") == "S2"
      and R.leads(ROSTER) == {"Day": "S2"} and R.lead_supervisor([], "Day") is None)
check("roster: a supervisor once a shift", len(R.section_errors({"supervisors": ROSTER + [ROSTER[1]]})) == 1
      and R.section_errors({"crew_per_shift": -1}) == ["Crew per Shift cannot be negative."])

# ── 2. The paper ──────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "excellence.py")
SHIFT = fields("Shift Report")
shift_fields = re.search(r"SHIFT_FIELDS = (\[.*?\])( \+ \[.*?\])", GLUE, re.S)
named = [name for name in eval(shift_fields.group(1)) if name != "name"] + ["factor_" + key for key in R.FACTOR_KEYS]
check("paper: every Shift Report field the scorecards read is on it", set(named) <= set(SHIFT), set(named) - set(SHIFT))
check("paper: every field the glue sets on a Shift Report is on it",
      {"machine_hours", "hours_lost", "not_wearing", "regular_labour", "ot_cost", "required_crew", "labour_budget",
       "absence_cost", "score", "status", "labour_cost", "labour_per_unit", "output_per_person", "uptime",
       "achievement", "attendance_rate", "ppe_rate", "adequacy", "weakest_area", "weakest_action", "week",
       "title"} <= set(SHIFT))
check("paper: what the Shift Report must have typed", all(SHIFT[name].get("reqd") for name in (
    "report_date", "shift", "work_section", "actual_output", "housekeeping", "waste_value", "staff_on_shift",
    "wearing_ppe")))
check("paper: the Shift Report's lists are the rules'", options("Shift Report", "shift") == list(R.SHIFTS)
      and options("Shift Report", "downtime_reason") == list(R.DOWNTIME_REASONS)
      and options("Shift Report", "status") == [R.ON_TARGET, R.ATTENTION, R.CRITICAL])
check("paper: a Shift Report is checked by submitting it", doctype("Shift Report").get("is_submittable") == 1)
SETTINGS = fields("Manufacturing Excellence Settings")
check("paper: every setting the rules read is on the settings, with its default", all(
    key in SETTINGS and float(SETTINGS[key]["default"]) == float(value) for key, value in R.DEFAULTS.items()),
    [key for key in R.DEFAULTS if key not in SETTINGS])
check("paper: the percentages are typed as percentages",
      all(SETTINGS[key]["fieldtype"] == "Percent" for key in R.PERCENT_KEYS))
SECTION_FIELDS = fields("Work Section")
check("paper: the Work Section has what the rules and glue read", {
    "section_name", "branch", "department", "company", "unit", "labour_type", "shift_reports", "counts_to_output",
    "is_active", "target_per_shift", "crew_per_shift", "machines", "approved_establishment",
    "labour_budget_per_unit", "labour_rate", "overtime_rate", "rates_note", "supervisors"} <= set(SECTION_FIELDS))
check("paper: the section's units and labour types are the rules'", options("Work Section", "unit") == list(R.UNITS)
      and options("Work Section", "labour_type") == list(R.LABOUR_TYPES))
check("paper: the roster row", set(fields("Work Section Supervisor")) == {"employee", "employee_name", "shift", "active"})
LOG = fields("People Log")
check("paper: the People Log's types are the rules'", options("People Log", "log_type") == list(R.LOG_TYPES))
check("paper: the People Log has what the glue reads", {"log_date", "week", "log_type", "work_section", "shift",
                                                        "branch", "company", "supervisor", "employee", "topic",
                                                        "score", "participants", "recorded_by"} <= set(LOG))
HRI = fields("HR Intervention")
check("paper: the intervention's lists are the rules'", options("HR Intervention", "source") == list(R.SOURCES)
      and options("HR Intervention", "intervention") == list(R.INTERVENTIONS)
      and options("HR Intervention", "kpi") == list(R.KPI_NAMES)
      and options("HR Intervention", "status") == list(R.INTERVENTION_STATUSES)
      and options("HR Intervention", "pillar") == [label for _key, label in R.PILLARS])
check("paper: the intervention has what the glue reads and sets", {
    "raised_on", "target_date", "closed_on", "status", "on_time", "verified", "result", "pillar", "overdue",
    "estimated_saving", "change", "days_open", "responsible", "observation", "kpi", "baseline", "latest",
    "supervisor", "work_section", "branch", "company", "actual_outcome"} <= set(HRI))
check("paper: only those who check the evidence tick Verified", HRI["verified"].get("permlevel") == 1 and {
    perm["role"] for perm in doctype("HR Intervention")["permissions"] if perm.get("permlevel") == 1 and perm.get("write")}
      == {"HR Manager", "Production Manager", "General Manager"})
CASE = fields("Disciplinary Case")
check("paper: the case has its cause and the legal limits", {
    "cause", "suggested_route", "case_cost", "aware_on", "penalty_due_by", "legal_flags", "work_section",
    "shift"} <= set(CASE) and CASE["work_section"].get("fetch_from") == "employee.custom_work_section"
      and CASE["aware_on"].get("default") == "Today")
check("paper: the case's worked-out fields are read only", all(CASE[name].get("read_only") for name in (
    "suggested_route", "penalty_due_by", "legal_flags")))
order = doctype("Disciplinary Case")["field_order"]
check("paper: the cause after the investigation, before the charge",
      order.index("investigated_on") < order.index("cause_section") < order.index("charge_section"))

# ── 3. The glue ───────────────────────────────────────────────────────


def body(name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@frappe)|\Z)" % re.escape(name), GLUE, re.S)
    return found.group(0) if found else ""


check("glue: the rates are worked out only by someone who may change the section",
      'doc.check_permission("write")' in body("rates_from_payroll")
      and "@frappe.whitelist()\ndef rates_from_payroll" in GLUE)
check("glue: the rates from the month just ended, submitted slips, in company currency",
      '"docstatus": 1' in body("rates_from_payroll") and "base_gross_pay" in body("rates_from_payroll")
      and "add_days(first, -1)" in body("rates_from_payroll"))
check("glue: a section's defaults only to someone who may read it", 'doc.check_permission("read")'
      in body("section_defaults") and "@frappe.whitelist()\ndef section_defaults" in GLUE)
check("glue: an employee moved to another plant loses the section",
      "plant != doc.branch" in body("employee_validate") and "doc.set(EMPLOYEE_SECTION, None)" in body("employee_validate"))
shift_body = body("shift_validate")
check("glue: a Shift Report takes what was left empty from its section, and its supervisor from the roster",
      'doc.get(field) in (None, "")' in shift_body and "rules.lead_supervisor" in shift_body)
check("glue: one Shift Report a section, shift and day", '"docstatus": ["<", 2]' in shift_body
      and '"name": ["!=", doc.name or ""]' in shift_body)
check("glue: no Shift Report for a shift still to come", "> getdate(today())" in shift_body)
check("glue: the case's flags as the rules have them, the suspension window from the other cases",
      "rules.case_flags(doc.as_dict(), today(), s, _suspended_before(doc, s))" in body("case_validate")
      and '"docstatus": ["<", 2]' in body("_suspended_before"))
check("glue: an intervention turning overdue is told to its owner once",
      'state["overdue"] and not cint(row.overdue)' in body("daily"))
check("glue: the scorecards read the shift reports through the user's permissions",
      "frappe.get_list(SHIFT_REPORT" in body("shift_rows"))
check("glue: a pulse score is a percentage, read as a fraction", "/ 100.0" in body("_pulse"))
check("glue: a resignation is a voluntary exit", '"Resigned"' in body("period_facts"))

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("wiring: the case's cause and flags on validate", re.search(
    r'"Disciplinary Case": \{\s*"validate": "hrms_addon\.hrms_addon\.excellence\.case_validate"', HOOKS))
check("wiring: the Employee's section checked on validate", "hrms_addon.hrms_addon.excellence.employee_validate" in HOOKS)
check("wiring: every day, and the role at migrate", '"hrms_addon.hrms_addon.excellence.daily"' in HOOKS
      and '"hrms_addon.hrms_addon.excellence.setup_on_migrate"' in HOOKS)
check("wiring: the Employee's section ships as a fixture", '"Employee-custom_work_section"' in HOOKS)
fixture = [row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
           if row.get("name") == "Employee-custom_work_section"]
check("wiring: the section is a link to Work Section", len(fixture) == 1 and fixture[0]["options"] == "Work Section"
      and fixture[0]["fieldtype"] == "Link")
for name, controller in (("Work Section", ("section_autoname", "section_validate")),
                         ("Shift Report", ("shift_validate",)), ("People Log", ("log_validate",)),
                         ("HR Intervention", ("intervention_validate",)),
                         ("Manufacturing Excellence Settings", ("settings_validate",))):
    folder = name.lower().replace(" ", "_")
    source = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    for call in controller:
        check("wiring: %s calls excellence.%s" % (name, call), "excellence.%s(self)" % call in source
              and "\ndef %s(" % call in GLUE)
check("wiring: the role is made at migrate", R.NEW_ROLES == (R.ME_OFFICER,)
      and "workflows.grant_on_migrate(rules" in body("setup_on_migrate"))
for report, roles in (("Repeat Cases", {"HR Manager", "HR User"}),
                      ("HR Excellence Scorecard", {R.ME_OFFICER, "HR Manager", "Production Manager"})):
    folder = report.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    check("wiring: %s is for %s" % (report, sorted(roles)), roles <= {row["role"] for row in spec["roles"]})
repeat = read("hrms_addon", "hrms_addon", "report", "repeat_cases", "repeat_cases.py")
CASE_READERS = {perm["role"] for perm in doctype("Disciplinary Case")["permissions"] if perm.get("read")}
check("wiring: Repeat Cases reads the cases through the user's permissions, only for those who may read cases,"
      " and can hide names", "frappe.get_list(excellence.CASE" in repeat and "hide_names" in repeat
      and {row["role"] for row in json.load(open(os.path.join(APP, "report", "repeat_cases", "repeat_cases.json"),
                                                 encoding="utf-8"))["roles"]} <= CASE_READERS)
EMPLOYEE_JS = read("hrms_addon", "public", "js", "employee.js")
check("wiring: the Employee form offers the plant's sections", 'set_query("custom_work_section"' in EMPLOYEE_JS)
# Frappe opens a script report only to someone who may report on its doctype
for folder in ("hr_excellence_scorecard", "shift_scorecard", "supervisor_scorecard", "repeat_cases"):
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    reporters = {perm["role"] for perm in doctype(spec["ref_doctype"])["permissions"]
                 if perm.get("report") and not perm.get("permlevel")}
    check("wiring: everyone %s is for may report on %s" % (spec["name"], spec["ref_doctype"]),
          {row["role"] for row in spec["roles"]} <= reporters,
          {row["role"] for row in spec["roles"]} - reporters)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_excellence: OK")
