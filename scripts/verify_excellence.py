"""Verify Manufacturing Excellence (batch 8, 17 Nov 2026; rebuilt 18 Nov 2026), without a bench:

    python scripts/verify_excellence.py

The plant's HR Manufacturing Excellence workbook (v3.2) on the desk, rebuilt after the client called the first
build shallow: periods scored from their totals as the workbook does, dated standards and roster, the crew from the
clock, a Plant Day Sheet a plant a day, downtime events and output lines, stored summaries read with GROUP BY, the
executive page, the HR Partner Brief, Order Feasibility, the labour cost flags and the case patterns.

  1  the rules, against the workbook's own W44 figures where it has them: the ten sections' Weekly Summary scores
     and the plant's, Lamination's eleven shifts (64.7 from the totals, not 72.3 the average of its shifts), the
     section signals and their intervention, the verdict, two orders' feasibility; the rest of the rules
  2  the paper: every field the rules, the glue and the reports name is on its doctype, every list the same
  3  the glue: what it fills, what it refuses, who may ask it, how it reads
  4  wiring: hooks, fixtures, patches, reports, the page, the menus
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
      and near(S["staffing_low"], 0.9, 1e-9) and near(S["budget_percent"], 0.12, 1e-9)
      and near(S["marginal_band"], 0.10, 1e-9) and near(S["housekeeping_target"], 0.85, 1e-9))
check("settings: a value saved as 0 stays 0, one never saved takes its default",
      R.settings_from({"weight_complaints": 0})["weight_complaints"] == 0
      and R.settings_from({"weight_complaints": None})["weight_complaints"] == 10)
check("settings: the defaults are clean", R.settings_errors({}) == [], R.settings_errors({}))
check("settings: weights must total 100", any("Shift score" in error for error in R.settings_errors({"weight_output": 30})))
check("settings: green above amber", any("Green" in error for error in R.settings_errors({"green_from": 70})))
check("settings: the order budget is a share", any("share of the order value" in error
                                                   for error in R.settings_errors({"budget_percent": 120})))
check("settings: names are hidden by a setting, not a tick on a report", R.DEFAULTS["hide_names"] == 0)

check("weeks: week 1 starts on the year's first Monday", R.first_monday(2026) == D(2026, 1, 5))
check("weeks: 2 Nov 2026 is W44, as on the plant's dashboards", R.week_of(D(2026, 11, 2)) == (2026, 44)
      and R.week_label(D(2026, 11, 8)) == "2026-W44" and R.week_start(D(2026, 11, 8)) == D(2026, 11, 2))
check("periods: a week, a month, a quarter", R.period_bounds(R.WEEK, 2026, 44) == (D(2026, 11, 2), D(2026, 11, 8))
      and R.period_bounds(R.MONTH, 2026, "February") == (D(2026, 2, 1), D(2026, 2, 28))
      and R.period_bounds(R.QUARTER, 2026, "Q4") == (D(2026, 10, 1), D(2026, 12, 31)))
weeks = R.last_weeks(D(2026, 11, 18), 13)
check("trends: thirteen whole weeks before this one, oldest first", len(weeks) == 13 and weeks[-1][0] == "2026-W45"
      and weeks[0][0] == "2026-W33", [row[0] for row in weeks][:2])
months = R.last_months(D(2026, 11, 18), 12)
check("trends: twelve months to this one", len(months) == 12 and months[-1][0] == "Nov 2026"
      and months[0][0] == "Dec 2025", months[0])

# the workbook's demo row 5: Extrusion, Day shift, 2 Nov 2026
STANDARD = {"labour_rate": 20000.0, "overtime_rate": 3750.0, "crew_per_shift": 46, "labour_budget_per_unit": 200}
ENTRY = {"target": 8000, "actual_output": 7173, "housekeeping": 88, "machines": 12, "machines_running": 11,
         "stop_hours": 2, "downtime_reason": "No Order", "waste_value": 217000, "complaint_value": 0,
         "safety_incidents": 0, "near_misses": 1, "staff_planned": 46, "staff_on_shift": 44, "unauthorised_absent": 0,
         "late_arrivals": 1, "early_departures": 1, "wearing_ppe": 44, "ot_hours": 24}
F = R.shift_figures(ENTRY, STANDARD, S)
check("shift: the workbook's demo shift scores 79.9, Attention, waste its weakest",
      (F["score"], F["status"], F["weakest"]) == (79.9, R.ATTENTION, "waste"), (F["score"], F["status"]))
check("shift: machine hours, hours lost, labour, budget, paid absence",
      (F["machine_hours"], F["hours_lost"]) == (144, 14) and near(F["labour_cost"], 970000, 0.01)
      and F["labour_budget"] == 1434600 and near(F["absence_cost"], 40000, 0.01))
check("shift: the waste limit of a shift is the week's over the shifts of a week",
      near(F["waste_cap"], 1000000 / 12.0, 1e-6)
      and near(R.shift_figures(ENTRY, dict(STANDARD, waste_limit=600000), S)["waste_cap"], 50000, 1e-6))
check("shift: downtime events stand for the hours lost when there are any",
      R.shift_figures(ENTRY, STANDARD, S, downtime_minutes=90)["hours_lost"] == 1.5)
CREW = R.crew_totals([
    {"status": "Present", "day_cost": 30000, "ot_hours": 2, "ot_cost": 11250, "late_minutes": 12},
    {"status": "Present", "day_cost": 25000, "no_ppe": 1, "incidents": 1},
    {"status": "On Leave", "absence_cost": 28000},
    {"status": "Absent", "unauthorised": 1},
    {"status": "Not Marked", "unauthorised": 1}])
check("crew: the sums with the names behind them", (CREW["planned"], CREW["on_shift"], CREW["absent"],
                                                    CREW["unauthorised"], CREW["not_marked"], CREW["late"],
                                                    CREW["no_ppe"], CREW["incidents"]) == (5, 2, 3, 2, 1, 1, 1, 1),
      CREW)
F2 = R.shift_figures(dict(ENTRY, staff_planned=5, staff_on_shift=2, wearing_ppe=1), STANDARD, S, crew=CREW)
check("crew: its people's pay is the shift's labour, not the section's rate",
      (F2["regular_labour"], F2["ot_cost"], F2["absence_cost"]) == (55000, 11250, 28000), F2["regular_labour"])
LINE = R.crew_line({"status": "Present", "late_minutes": 15, "attendance_ot_hours": 2}, 26000, S)
check("crew line: present, late, overtime from the attendance at the person's own rate",
      (LINE["on_shift"], LINE["late"], LINE["day_cost"], LINE["ot_hours"]) == (1, 1, 26000, 2)
      and near(LINE["ot_cost"], 2 * 26000 / 8.0 * 1.5, 0.01), LINE)
check("crew line: an overtime request's cost wins over the hours at the rate",
      R.crew_line({"status": "Present", "ot_hours": 3, "ot_amount": 9999}, 26000, S)["ot_cost"] == 9999)
check("crew line: paid leave is paid absence, absence without leave is unauthorised, unpaid leave costs nothing",
      R.crew_line({"status": "On Leave", "leave_type": "Annual"}, 26000, S)["absence_cost"] == 26000
      and R.crew_line({"status": "Absent"}, 26000, S)["unauthorised"] == 1
      and R.crew_line({"status": "On Leave", "leave_type": "LWP", "paid_leave": False}, 26000, S)["absence_cost"] == 0
      and R.crew_line({}, 26000, S)["status"] == R.NOT_MARKED)
check("crew: day and night from the Shift Type", R.shift_of("Night Shift") == R.NIGHT and R.shift_of("Day Shift")
      == R.DAY and R.shift_of("General", "19:00:00") == R.NIGHT and R.shift_of("General", "07:00:00") == R.DAY)
check("crew: an incident in the small hours belongs to the night before",
      R.incident_shift("2026-11-03 02:30:00", D(2026, 11, 2)) == R.NIGHT
      and R.incident_shift("2026-11-02 10:00:00", D(2026, 11, 2)) == R.DAY
      and R.incident_shift("2026-11-03 09:00:00", D(2026, 11, 2)) is None)
check("crew: a day is the month's pay over 26 days", R.day_rate_of(780000, S) == 30000)

# the workbook's W44 Lamination: the eleven shifts entered (Saturday night was not)
LAMINATION = {"crew_per_shift": 9, "labour_rate": 27864.38, "overtime_rate": 5224.57, "labour_budget_per_unit": 120}
SHIFTS = [(2285, 70, 2, 1, 252000, 0, 6, 5, 16), (2109, 95, 0, 0, 56000, 0, 5, 5, 16),
          (2279, 85, 2, 1, 210000, 0, 6, 6, 4), (2199, 75, 2, 0, 77000, 0, 6, 4, 0),
          (2529, 80, 0, 1, 350000, 0, 8, 8, 24), (2242, 92, 1, 3, 238000, 0, 8, 7, 0),
          (2097, 95, 0, 3, 196000, 0, 9, 8, 24), (2014, 90, 2, 0, 322000, 400000, 8, 7, 16),
          (2309, 80, 2, 2, 154000, 0, 7, 6, 16), (2104, 88, 1, 0, 105000, 0, 8, 8, 12),
          (2240, 92, 2, 0, 273000, 400000, 7, 7, 8)]
summaries, shift_scores = [], []
for actual, hk, running, stop, waste, complaints, on_shift, wearing, ot in SHIFTS:
    entry = {"target": 2500, "actual_output": actual, "housekeeping": hk, "machines": 2, "machines_running": running,
             "stop_hours": stop, "waste_value": waste, "complaint_value": complaints, "staff_planned": 9,
             "staff_on_shift": on_shift, "wearing_ppe": wearing, "ot_hours": ot, "safety_incidents": 0}
    figures = R.shift_figures(entry, LAMINATION, S)
    shift_scores.append(figures["score"])
    summaries.append(dict(R.day_summary(entry, figures, S), unit="Kg"))
T = R.totals(summaries, S)
P = R.period_scores(T, S)
check("W44 Lamination: the shifts score as the workbook's Daily Entry",
      shift_scores == [75.3, 70.1, 78.4, 74.5, 70.5, 71.9, 67.2, 67.0, 77.0, 73.2, 70.0], shift_scores)
check("W44 Lamination: from its totals the week scores 64.7, as the workbook's Weekly Summary and Supervisor "
      "Dashboard, not 72.3, the average of its shifts", near(P["exact"], 64.67428904428904, 1e-9)
      and P["score"] == 64.7 and P["status"] == R.CRITICAL and P["weakest"] == "waste"
      and round(sum(shift_scores) / len(shift_scores), 1) == 72.3, P["exact"])
check("W44 Lamination: the sums behind it", (T["shifts"], T["target"], T["actual_output"], T["hours_lost"],
                                             T["waste_value"], T["staff_planned"], T["staff_on_shift"],
                                             T["wearing_ppe"]) == (11, 27500, 24407, 107, 2233000, 99, 78, 71),
      (T["shifts"], T["hours_lost"]))
check("averages: read the score from the totals too, with the old names beside the new",
      R.averages(T)["score"] == 64.7 and T["count"] == 11 and T["actual"] == 24407 and T["on_shift"] == 78)

# the workbook's Weekly Summary, W44, all ten sections: (shifts, target, actual, hours lost, machine hours, waste,
# complaints, incidents, housekeeping average, planned, on shift, wearing) and its score (column V)
WEEK44 = {
    "Extrusion": ((12, 96000, 88222, 71.5, 1728, 10122000, 250000, 0, 84.75, 552, 543, 536), 78.4728204736835),
    "Flexo Printing": ((12, 36000, 34218, 108, 576, 2716000, 150000, 0, 81.41666666666667, 180, 166, 157),
                       77.25300870147255),
    "Roto Printing": ((12, 42000, 38052, 96, 432, 4081000, 800000, 0, 86.5, 396, 370, 364), 70.18348621348622),
    "Lamination": ((11, 27500, 24407, 107, 264, 2233000, 800000, 0, 85.63636363636364, 99, 78, 71), 64.67428904428904),
    "Slitting": ((12, 48000, 43306, 92.5, 720, 4305000, 250000, 1, 81.25, 240, 217, 207), 73.19387960829494),
    "Bag Making": ((12, 1800000, 1648809, 69, 3600, 1182000, 400000, 0, 80.5, 1092, 1060, 1050), 76.76248521839796),
    "BFM": ((12, 720000, 684945, 68, 1152, 488000, 1350000, 1, 83.66666666666667, 192, 168, 162), 75.51924107142855),
    "Recycle": ((12, 30000, 27420, 108, 432, 2541000, 0, 0, 84.08333333333333, 108, 86, 81), 76.24936261843239),
    "Quality Control": ((12, 720, 697, 0, 0, 0, 150000, 0, 78.16666666666667, 72, 41, 32), 89.87613143631435),
    "Maintenance": ((12, 120, 112, 0, 0, 0, 550000, 0, 82.58333333333333, 168, 151, 144), 90.07418479974771),
}
section_totals = {}
for section, (sums, _expected) in WEEK44.items():
    shifts, target, actual, lost, machine_hours, waste, complaints, incidents, hk, planned, on_shift, wearing = sums
    section_totals[section + " - Kawempe"] = R.totals([{
        "shifts": shifts, "target": target, "actual_output": actual, "hours_lost": lost,
        "machine_hours": machine_hours, "waste_value": waste, "complaint_value": complaints,
        "waste_cap": 1000000.0 * shifts / 12, "complaint_cap": 1000000.0 * shifts / 12, "safety_incidents": incidents,
        "housekeeping": hk * shifts, "staff_planned": planned, "staff_on_shift": on_shift, "wearing_ppe": wearing}], S)
wrong = {section: (round(R.period_scores(section_totals[section + " - Kawempe"], S)["exact"], 6), round(expected, 6))
         for section, (_sums, expected) in WEEK44.items()
         if not near(R.period_scores(section_totals[section + " - Kawempe"], S)["exact"], expected, 1e-6)}
check("W44: each of the ten sections scores from its totals what the workbook's Weekly Summary does", not wrong, wrong)
SCORED = R.section_scores(section_totals, S)
check("W44: the plant is the average of its sections, 77.2 as on the workbook's Dashboard",
      R.plant_score([row["score"] for row in SCORED]) == 77.2, R.plant_score([row["score"] for row in SCORED]))
check("W44: the verdict, as the workbook's Dashboard says it",
      R.verdict(SCORED) == "1 on target, 6 attention, 3 critical. Lowest: Lamination (64.7), weakest on Waste.",
      R.verdict(SCORED))
check("W44: Slitting's safety incident takes the week's safety factor to 75",
      R.period_scores(section_totals["Slitting - Kawempe"], S)["factors"]["safety"] == 75)
TILES = R.production_tiles(R.add_totals(*section_totals.values()), SCORED, S)
check("tiles: the Dashboard's eleven", len(TILES) == 11 and TILES[0]["value"] == 77.2
      and [tile["key"] for tile in TILES][-1] == "over_limit" and TILES[-1]["value"] == 8, [t["value"] for t in TILES])

# the workbook's HR Excellence by section, W44
LAM_ROW = {"deployment": 0.7878787878787878, "attendance": 0.7878787878787878, "unauthorised": 0.050505050505050504,
           "ot_share": 0.2463768115942029, "ppe": 0.9102564102564102, "competency": None, "open_grievances": 0,
           "exits": 0}
SIGNALS = R.section_signals(LAM_ROW, S)
check("signals: Lamination's four signals call for the capacity and deployment review, as on the workbook",
      SIGNALS["count"] == 4 and SIGNALS["intervention"] == "Capacity and Deployment Review"
      and SIGNALS["alert"] == "4 signals: Capacity and Deployment Review", SIGNALS)
FLEXO = R.section_signals({"deployment": 0.9222, "attendance": 0.9222222222222223, "unauthorised": 0.011111111111111112,
                           "ot_share": 0.07132867132867132, "ppe": 0.9457831325301205, "competency": 0,
                           "open_grievances": 0, "exits": 0}, S)
check("signals: Flexo's four call for the attendance review", FLEXO["count"] == 4
      and FLEXO["intervention"] == "Attendance Review and Engagement", FLEXO)
check("signals: one signal is to monitor; a section with no shifts has none",
      R.section_signals(dict(LAM_ROW, attendance=0.99, unauthorised=0, ot_share=0.01, ppe=0.99), S)["alert"]
      == "" and R.section_signals({"deployment": None}, S)["count"] == 0
      and R.section_signals(dict(LAM_ROW, attendance=0.99, unauthorised=0, ot_share=0.01), S)["alert"]
      == "1 signal: monitor")

NOW = R.totals([{"shifts": 12, "ot_cost": 1200000, "actual_output": 1000, "labour_cost": 9000000,
                 "budgeted_labour": 9000000, "labour_budget": 8000000, "staff_planned": 100,
                 "unauthorised_absent": 2, "staff_on_shift": 90, "ot_hours": 150}], S)
BEFORE = R.totals([{"shifts": 12, "ot_cost": 1000000, "actual_output": 1000}], S)
check("labour flags: overtime up with output flat, over budget, unauthorised absence, fatigue",
      [flag for flag, _intervention in R.labour_flags(NOW, BEFORE, S)]
      == [R.OT_UP, R.OVER_BUDGET, R.UNAUTHORISED, R.FATIGUE], R.labour_flags(NOW, BEFORE, S))
check("labour flags: output up with the overtime is not flagged; no week before, no comparison",
      R.OT_UP not in [flag for flag, _i in R.labour_flags(NOW, dict(BEFORE, actual_output=800), S)]
      and R.OT_UP not in [flag for flag, _i in R.labour_flags(NOW, None, S)])

# the workbook's Order Feasibility, rows 6 and 8
SHRINK = R.order_figures({"order_qty": 80000, "order_value": 760000000},
                         {"produced": 29233, "labour": 8611981.65972369, "waste": 4473000, "complaints": 250000,
                          "shifts": 9, "finishing_shifts": 4}, S)
check("orders: the shrink film order is feasible, with the workbook's figures",
      SHRINK["feasibility"] == R.FEASIBLE and near(SHRINK["budget_per_unit"], 1140, 1e-6)
      and near(SHRINK["conversion_per_unit"], 456.16192863283584, 1e-6)
      and near(SHRINK["shifts_to_finish"], 6.946533027742619, 1e-6)
      and near(SHRINK["cost_to_finish"], 23157972.630903177, 1e-3)
      and near(SHRINK["projected"], 36492954.29062687, 1e-3)
      and near(SHRINK["labour_share"], 0.031010309760683905, 1e-9), SHRINK)
BAGS = R.order_figures({"order_qty": 3000000, "order_value": 360000000},
                       {"produced": 1648809, "labour": 31825413.063746784, "waste": 6516000, "complaints": 550000}, S)
check("orders: the carrier bag order is not feasible", BAGS["feasibility"] == R.NOT_FEASIBLE
      and near(BAGS["over_budget"], 9.187579315582813, 1e-6), BAGS["over_budget"])
check("orders: marginal within the band, no output yet, a budget to set",
      R.order_figures({"budget_per_unit": 100}, {"produced": 10, "labour": 1050}, S)["feasibility"] == R.MARGINAL
      and R.order_figures({"budget_per_unit": 100}, {}, S)["feasibility"] == R.NO_OUTPUT
      and R.order_figures({}, {"produced": 10, "labour": 10}, S)["feasibility"] == R.SET_BUDGET)
SHARES = R.allocate([{"good_qty": 300}, {"good_qty": 100}], 4000, 8, 800, 400)
check("orders: a shift's labour shared over its lines by what each made",
      SHARES == [{"labour": 3000, "ot_hours": 6, "ot_cost": 600, "complaints": 300},
                 {"labour": 1000, "ot_hours": 2, "ot_cost": 200, "complaints": 100}], SHARES)

# standards and roster by date
ROWS = [{"effective_from": D(2026, 1, 1), "target_per_shift": 2500, "waste_limit": 1000000},
        {"effective_from": D(2026, 11, 9), "target_per_shift": 2800, "waste_limit": 800000}]
check("standards: a past period reads the standard in force then", R.standard_on(ROWS, D(2026, 11, 2))[
    "target_per_shift"] == 2500 and R.standard_on(ROWS, D(2026, 11, 10))["target_per_shift"] == 2800
      and R.standard_on(ROWS, D(2025, 6, 1))["target_per_shift"] == 2500
      and R.standard_on([], D(2026, 1, 1), {"target_per_shift": 7})["target_per_shift"] == 7)
EDITED, CHANGED = R.standards_after_edit(ROWS, {"target_per_shift": 3000, "waste_limit": 800000}, D(2026, 11, 18))
check("standards: changing what is in force keeps the history as a standard from today",
      CHANGED and len(EDITED) == 3 and EDITED[-1]["effective_from"] == D(2026, 11, 18)
      and EDITED[-1]["target_per_shift"] == 3000 and EDITED[1]["target_per_shift"] == 2800, EDITED)
check("standards: a section's first standard from what was typed", R.standards_after_edit(
    [], {"target_per_shift": 10}, D(2026, 11, 18))[0][0]["effective_from"] == D(2026, 11, 18)
      and R.standards_after_edit(ROWS, {"target_per_shift": 2800, "waste_limit": 800000}, D(2026, 11, 18))[1] is False)
check("standards: one a date, none negative", len(R.standard_errors(ROWS + [ROWS[0]])) == 1
      and R.standard_errors([{"effective_from": D(2026, 1, 1), "crew_per_shift": -1}]))
ROSTER = [{"employee": "S1", "role": "Supervisor", "shift": "Day", "from_date": D(2026, 1, 1), "to_date": D(2026, 10, 31)},
          {"employee": "S2", "role": "Supervisor", "shift": "Day", "from_date": D(2026, 11, 1)},
          {"employee": "S3", "role": "Supervisor", "shift": "Day", "from_date": D(2026, 11, 1)},
          {"employee": "S4", "role": "Supervisor", "shift": "Night", "from_date": D(2026, 1, 1)},
          {"employee": "P1", "role": "Production Officer", "shift": "Both", "from_date": D(2026, 1, 1)}]
check("roster: who led a shift on a past day", R.lead_on(ROSTER, D(2026, 10, 15), "Day") == "S1"
      and R.lead_on(ROSTER, D(2026, 11, 2), "Day") == "S2" and R.lead_on(ROSTER, D(2026, 11, 2), "Night") == "S4"
      and R.lead_on(ROSTER, D(2026, 11, 2), "Night", R.PRODUCTION_OFFICER) == "P1")
check("roster: every rostered supervisor, not only the first", R.rostered(ROSTER, D(2026, 11, 2), "Day") == ["S2", "S3"])
WINDOWS = R.roster_windows(ROSTER, D(2026, 10, 26), D(2026, 11, 8))
check("roster: the windows that touch a period, clipped to it", sorted(row["employee"] for row in WINDOWS)
      == ["S1", "S2", "S3", "S4"] and [row for row in WINDOWS if row["employee"] == "S1"][0]["to"] == D(2026, 10, 31))
check("roster: the same person twice for the same days is refused",
      len(R.roster_errors([ROSTER[1], dict(ROSTER[1], shift="Both")])) == 1 and not R.roster_errors(ROSTER))

# supervisors and pillars
SUP = R.supervisor_index({"totals": T, "due": 12, "reported": 11, "conduct_cases": 1, "sessions": 1,
                          "supervisors": 1, "weeks": 1, "interventions_due": 0}, S)
check("supervisor: reporting is rows entered over rows due; closure left out with none due; the weakest part is "
      "the development focus", near(SUP["parts"]["reporting"], 100 * 11 / 12.0, 1e-6) and SUP["parts"]["closure"] is None
      and SUP["focus"] == R.DEVELOPMENT_FOCUS[SUP["weakest_part"]] and SUP["band"] in (R.STRONG, R.DEVELOPING,
                                                                                      R.NEEDS_COACHING), SUP)
FACTS = {"totals": T, "headcount": 18, "establishment": 18, "coverage": (40, 50), "due_reports": 12, "reported": 11,
         "sessions": 2, "supervisors": 1, "weeks": 1, "interventions_due": 2, "interventions_on_time": 1,
         "interventions_closed": 2, "interventions_improved": 1, "pulse": 0.7, "exits": 0, "months": 0.23}
CARD = R.pillars(FACTS, S)
check("pillars: all eight scored; the productivity part reads the period's totals",
      all(pillar["score"] is not None for pillar in CARD["pillars"]) and CARD["averages"]["score"] == 64.7)
check("pillars: a safety incident marks the period critical whatever the score", R.pillars(
    dict(FACTS, totals=R.totals([dict(summaries[0], safety_incidents=1)], S)), S)["status"] == R.RED_FLAG)
HR = R.hr_tiles(CARD, FACTS, S)
check("tiles: the HR Excellence sheet's twelve", len(HR) == 12 and HR[0]["key"] == "hr_score"
      and HR[-1]["value"] == "18 / 18")
check("pillars: no data is not poor performance", R.pillars({"totals": R.totals([], S)}, S)["composite"] == 100.0)

# day sheet
check("sheet: every reporting section, Day then Night, what is not there yet",
      R.sheet_rows_to_add(["A", "B"], [{"work_section": "A", "shift": "Day"}])
      == [("A", "Night"), ("B", "Day"), ("B", "Night")])
STATE = R.sheet_state([{"work_section": "A", "shift": "Day", "actual_output": 10},
                       {"work_section": "A", "shift": "Night", "not_worked": 1},
                       {"work_section": "B", "shift": "Day"}])
check("sheet: entered, not worked, missing", (STATE["entered"], STATE["not_worked"], STATE["missing"],
                                              STATE["missing_rows"]) == (1, 1, 1, [("B", "Day")]), STATE)
check("sheet: a row not worked with figures, and one twice, are refused; PPE waits for the clock",
      len(R.sheet_errors(D(2026, 11, 2), D(2026, 11, 3), [
          {"work_section": "A - X", "shift": "Day", "not_worked": 1, "actual_output": 5},
          {"work_section": "A - X", "shift": "Day", "wearing_ppe": 9}])) == 2
      and R.sheet_errors(D(2026, 11, 4), D(2026, 11, 3), []) == ["A day sheet is for a day that has been worked."])
SHEET_ROWS = [{"key": "r1", "work_section": "Lamination - Kawempe", "shift": "Day"},
              {"key": "r2", "work_section": "Lamination - Kawempe", "shift": "Night"}]
PASTED = R.parse_paste("Section\tShift\tActual Output\tWaste Value\tMain Downtime Reason\n"
                       "Lamination\tDay\t2,285\t252000\tNo Order\nlamination\tN\t2109\t\t\nRecycle\tDay\t1\t1\t",
                       SHEET_ROWS)
check("paste: a heading in any order, sections by their own name, blanks change nothing, a stranger is said",
      PASTED["updates"] == [{"key": "r1", "values": {"actual_output": 2285.0, "waste_value": 252000.0,
                                                     "downtime_reason": "No Order"}},
                            {"key": "r2", "values": {"actual_output": 2109.0}}]
      and len(PASTED["errors"]) == 1, PASTED)
check("paste: without a heading, the columns in order", R.parse_paste("Lamination\tDay\t100\t80", SHEET_ROWS)[
    "updates"] == [{"key": "r1", "values": {"actual_output": 100.0, "housekeeping": 80.0}}])

# cases
CASES = [{"name": "C1", "employee": "E1", "incident_date": D(2026, 3, 1), "cause": R.NEGLIGENCE, "case_cost": 1000,
          "shift": "Day", "case_type": "Disciplinary", "work_section": "A", "status": "Closed", "decided_on": D(2026, 3, 5)},
         {"name": "C2", "employee": "E1", "incident_date": D(2026, 10, 1), "cause": "Skills Gap", "case_cost": 500,
          "shift": "Night", "case_type": "Disciplinary", "work_section": "A", "status": "Under Investigation",
          "aware_on": D(2026, 10, 1)},
         {"name": "C3", "employee": "E2", "incident_date": D(2026, 11, 2), "cause": R.NEGLIGENCE, "shift": "Day",
          "case_type": "Disciplinary", "work_section": "B", "status": "Hearing Scheduled", "aware_on": D(2026, 11, 10)},
         {"name": "C4", "employee": "E2", "incident_date": D(2025, 1, 2), "cause": R.NEGLIGENCE, "status": "Closed"}]
COUNTS = R.window_counts(CASES, 12)
check("cases: each case's count in the window, in one pass", COUNTS == {"C1": 1, "C2": 2, "C3": 1, "C4": 1}, COUNTS)
check("cases: the tracker's flags", R.tracker_flag(CASES[1], 2, D(2026, 11, 18), S) == R.OVERDUE
      and R.tracker_flag(CASES[2], 1, D(2026, 11, 18), S) == R.DECISION_DUE
      and R.tracker_flag(CASES[0], 2, D(2026, 11, 18), S) == R.REPEAT
      and R.tracker_flag(dict(CASES[1], legal_flags="Past the 15 days"), 2, D(2026, 11, 18), S) == "Past the 15 days")
BY = R.tracker_breakdown(CASES[:3], "work_section", COUNTS)
check("cases: by section, Day and Night, the route", BY["A"]["cases"] == 2 and BY["A"]["day"] == 1
      and BY["A"]["conduct"] == 1 and BY["A"]["coaching"] == 1 and BY["A"]["repeats"] == 1 and BY["B"]["cost"] == 0)
check("cases: repeat employees in the window", set(R.repeat_cases(CASES, D(2026, 11, 17), 12)) == {"E1"})
check("cases: the suspension history read once for all", len(R.suspension_history([
    {"employee": "E1", "suspension_from": D(2026, 9, 1), "suspension_days": 10},
    {"employee": "E1", "suspension_from": None}])["E1"]) == 1)
check("cases: past the 15 days and over the suspension cap are flagged", any("s.62(5)" in flag for flag in R.case_flags(
    {"aware_on": D(2026, 11, 1), "status": "Under Investigation"}, D(2026, 11, 17), S)) and any(
    "s.62(4)" in flag for flag in R.case_flags({"suspension_days": 6, "suspension_from": D(2026, 11, 1)},
                                               D(2026, 11, 1), S, before=10)))

# interventions
check("readings: the first is the baseline, the newest the latest", R.readings_baseline_latest(
    [{"reading_date": D(2026, 11, 9), "value": 0.09}, {"reading_date": D(2026, 10, 12), "value": 0.11}])
      == (0.11, 0.09) and R.readings_baseline_latest([{"reading_date": D(2026, 10, 12), "value": 0.11}]) == (0.11, None))
check("KPIs: the sixteen read from a week's figures", R.kpi_value("Attendance %", {"totals": T}, S) == 78 / 99.0
      and R.kpi_value("Waste Value", {"totals": T}, S) == 2233000
      and R.kpi_value("Turnover %", {"exits": 1, "headcount": 20}, S) == 0.05
      and R.kpi_value("Training Coverage %", {"coverage": (3, 4)}, S) == 0.75
      and all(name in R.KPI_NAMES for name in ("Supervisor People Score", "Pulse Score %")))
check("interventions: overtime down is an improvement", R.intervention_state(
    {"raised_on": D(2026, 10, 12), "target_date": D(2026, 11, 13), "status": R.IN_PROGRESS,
     "kpi": "Overtime % of Labour Cost", "baseline": 0.11, "latest": 0.09}, D(2026, 11, 17))["result"] == R.IMPROVED)

check("people log: someone listed twice is refused, a score is a percentage",
      R.log_errors({"attendees": [{"employee": "E1"}, {"employee": "E1"}]}) == ["E1 is listed twice."]
      and R.log_errors({"score": 120}) == ["The score is a percentage, from 0 to 100."])

# the brief
POINTS = R.talking_points({"plant_score": 77.2, "plant_status": R.ATTENTION, "verdict": "1 on target.",
                           "money_lost": 32368000, "over_limit": 8, "ppe": 0.97, "not_wearing": 76, "absent": 219,
                           "attendance": 0.93, "incidents": 2, "hours_lost": 720, "top_reason": "Changeover",
                           "labour": 95247703, "ot_cost": 6054253, "ot_share": 0.0636, "cases": 5, "legal_flags": 4,
                           "open_grievances": 1})
check("brief: the talking points from the week's figures", len(POINTS) >= 7 and "32,368,000" in POINTS[1]
      and "Changeover" in POINTS[4], POINTS[:2])
QUESTIONS = R.nine_questions({"headcount": 524, "establishment": 526, "deployment": 0.93, "below_band": 53,
                              "signals": [("Roto Printing - Kawempe", "5 signals: Attendance Review and Engagement")]})
check("brief: the nine questions, each answered", len(QUESTIONS) == 9 and "524" in QUESTIONS[0][1]
      and QUESTIONS[8][1].startswith("5 signals"), QUESTIONS[0])
check("brief: no data says so", R.talking_points({}) == ["No shifts recorded for the week yet."])

# plain words in what users see
SHOWN = [text for row in R.KPI_DICTIONARY + R.GUIDE + R.GOVERNANCE for text in row] + POINTS + [
    answer for _question, answer in QUESTIONS] + [R.verdict(SCORED)] + list(R.ROUTES.values())
check("plain words: no dashes used as punctuation in the guide, the brief or the verdict",
      not [text for text in SHOWN if "—" in text or " - " in text.replace(" - Kawempe", "")],
      [text for text in SHOWN if "—" in text][:2])
check("the guide: the KPI dictionary, who enters what, the rules", len(R.KPI_DICTIONARY) >= 30 and len(R.GUIDE) >= 6
      and len(R.GOVERNANCE) >= 8)

# ── 2. The paper ──────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "excellence.py")
SUMMARY = read("hrms_addon", "hrms_addon", "excellence_summary.py")
SHEET = read("hrms_addon", "hrms_addon", "excellence_sheet.py")
CLOCK = read("hrms_addon", "hrms_addon", "excellence_clock.py")
PAGE = read("hrms_addon", "hrms_addon", "excellence_page.py")
BRIEF = read("hrms_addon", "hrms_addon", "excellence_brief.py")
SHIFT = fields("Shift Report")
check("paper: every field the glue sets on a Shift Report is on it", {
    "machine_hours", "hours_lost", "not_wearing", "regular_labour", "ot_cost", "required_crew", "labour_budget",
    "absence_cost", "score", "status", "labour_cost", "labour_per_unit", "output_per_person", "uptime", "achievement",
    "attendance_rate", "ppe_rate", "adequacy", "weakest_area", "weakest_action", "week", "title", "absent",
    "shift_key", "not_marked", "plant_day_sheet", "clock_fetched_on", "crew", "downtime", "outputs",
    "production_officer"} <= set(SHIFT), {"absent", "shift_key"} - set(SHIFT))
check("paper: a shift report is unique by its key at the database, given up on cancel",
      SHIFT["shift_key"].get("unique") and SHIFT["shift_key"].get("no_copy")
      and 'doc.db_set("shift_key", None' in GLUE)
check("paper: the shift's downtime reason is the master's", SHIFT["downtime_reason"]["fieldtype"] == "Link"
      and SHIFT["downtime_reason"]["options"] == "Downtime Reason")
check("paper: the reasons first seeded are the old list's", list(R.DOWNTIME_REASONS) == [
    "Mechanical Breakdown", "Electrical Breakdown", "Power Outage", "No Raw Material", "No Order", "No Operator",
    "Changeover", "Planned Maintenance", "Other"])
check("paper: the filtered fields are indexed", all(SHIFT[name].get("search_index") for name in (
    "report_date", "work_section", "shift", "branch", "supervisor")) and fields("People Log")["log_date"].get(
    "search_index") and fields("People Log")["supervisor"].get("search_index"))
CREW_FIELDS = fields("Shift Crew")
check("paper: a crew row's figures", {"employee", "employment", "rostered_shift", "status", "unauthorised",
                                      "late_minutes", "early_minutes", "ot_hours", "ot_cost", "day_rate", "day_cost",
                                      "absence_cost", "no_ppe", "incidents", "near_misses", "attendance"}
      <= set(CREW_FIELDS) and options("Shift Crew", "status") == list(R.CREW_STATUSES)
      and not CREW_FIELDS["no_ppe"].get("read_only") and CREW_FIELDS["status"].get("read_only"))
check("paper: downtime events and output lines", {"machine", "downtime_reason", "category", "planned", "minutes"}
      <= set(fields("Shift Downtime")) and {"plant_order", "product", "machine", "good_qty", "waste_qty", "waste_value",
                                             "reject_reason", "labour_share", "ot_hours_share", "ot_cost_share",
                                             "complaint_share", "report_date", "work_section", "branch"}
      <= set(fields("Shift Output")))
check("paper: the masters", options("Downtime Reason", "category") == list(R.DOWNTIME_CATEGORIES)
      and {"planned", "owning_department"} <= set(fields("Downtime Reason"))
      and {"machine_code", "work_section", "branch", "capacity_per_shift"} <= set(fields("Machine"))
      and options("Plant Order", "status") == list(R.ORDER_STATUSES)
      and {"order_no", "customer", "product", "finishing_section", "order_qty", "order_value", "budget_per_unit"}
      <= set(fields("Plant Order")))
SECTION = fields("Work Section")
check("paper: the section's standards and roster by date", SECTION["standards"]["options"] == "Section Standard"
      and SECTION["assignments"]["options"] == "Section Assignment"
      and set(R.STANDARD_FIELDS) <= set(fields("Section Standard")) and set(R.STANDARD_FIELDS) <= set(SECTION)
      and options("Section Assignment", "role") == list(R.ROSTER_ROLES)
      and options("Section Assignment", "shift") == list(R.ROSTER_SHIFTS)
      and SECTION["supervisors"].get("read_only"))
ROW = fields("Plant Day Sheet Row")
check("paper: a day sheet row takes what is typed and shows what the clock and the report give",
      set(R.SHEET_TYPED) <= set(ROW) and {"staff_planned", "staff_on_shift", "unauthorised_absent", "not_marked",
                                          "late_arrivals", "early_departures", "ot_hours", "safety_incidents",
                                          "near_misses", "score", "status", "labour_cost", "shift_report",
                                          "supervisor", "target", "machines"} <= set(ROW)
      and ROW["work_section"].get("read_only") and ROW["staff_on_shift"].get("read_only"))
SHEET_SPEC = doctype("Plant Day Sheet")
check("paper: the day sheet, one approval", SHEET_SPEC.get("is_submittable") == 1 and {
    "branch", "sheet_date", "entered_rows", "missing_rows", "not_worked_rows", "plant_score", "clock_fetched_on",
    "job_status", "rows"} <= set(fields("Plant Day Sheet")))
for name in ("Section Day Summary", "Section Week Summary"):
    have = fields(name)
    check("paper: %s holds every sum the readers group by" % name, set(R.SUMMARY_FIELDS) <= set(have),
          set(R.SUMMARY_FIELDS) - set(have))
    check("paper: %s is named by its key and written by the system" % name,
          doctype(name).get("autoname") == "field:summary_key" and have["summary_key"].get("unique")
          and doctype(name).get("in_create") == 1)
check("paper: the downtime summary", {"summary_key", "downtime_reason", "category", "planned", "machine", "minutes",
                                      "shift_report", "branch", "work_section", "summary_date"}
      <= set(fields("Section Downtime Summary")))
check("paper: the week summary's scores", {"score", "status", "weakest_area", "output_score", "ppe_score",
                                           "er_cases"} <= set(fields("Section Week Summary")))
HRI = fields("HR Intervention")
check("paper: the intervention's readings and the signal that raised it", HRI["kpi_readings"]["options"]
      == "Intervention KPI Reading" and options("HR Intervention", "signal_source") == list(R.SIGNAL_SOURCES)
      and HRI["section_week"]["options"] == "Section Week Summary"
      and options("Intervention KPI Reading", "source") == list(R.READING_SOURCES)
      and options("HR Intervention", "kpi") == list(R.KPI_NAMES)
      and options("HR Intervention", "intervention") == list(R.INTERVENTIONS))
check("paper: the People Log's participants", fields("People Log")["attendees"]["options"] == "People Log Participant"
      and {"employee", "attended", "induction", "evidence"} <= set(fields("People Log Participant"))
      and options("People Log", "log_type") == list(R.LOG_TYPES))
CASE = fields("Disciplinary Case")
check("paper: the case's type, quantity and unit, order, supervisor on shift and employment",
      {"case_type", "quantity", "unit", "plant_order", "supervisor_on_shift", "employment", "cause", "aware_on",
       "penalty_due_by", "legal_flags", "work_section", "shift", "case_cost"} <= set(CASE)
      and options("Disciplinary Case", "case_type") == list(R.CASE_TYPES)
      and options("Disciplinary Case", "cause") == list(R.CAUSE_NAMES))
check("paper: one section everywhere: a Work Section beside the old section text",
      fields("Overtime Request")["work_section"]["options"] == "Work Section"
      and fields("Overtime Request")["section"]["fieldtype"] == "Data"
      and fields("Overtime Request Employee")["work_section"]["fetch_from"] == "employee.custom_work_section"
      and fields("Daily Production Report")["work_section"]["fetch_from"] == "supervisor.custom_work_section"
      and CASE["section"]["fieldtype"] == "Data")
SETTINGS = fields("Manufacturing Excellence Settings")
check("paper: every setting the rules read is on the settings, with its default", all(
    key in SETTINGS and float(SETTINGS[key]["default"]) == float(value) for key, value in R.DEFAULTS.items()),
    [key for key in R.DEFAULTS if key not in SETTINGS])
check("paper: the percentages are typed as percentages", all(SETTINGS[key]["fieldtype"] == "Percent"
                                                            for key in R.PERCENT_KEYS))
check("paper: the guide is on the settings", SETTINGS["guide_html"]["fieldtype"] == "HTML")
BRIEF_FIELDS = fields("HR Partner Brief")
check("paper: the brief's parts", {"week", "branch", "money_lost", "top_sections", "supervisors", "talking_points",
                                   "signals", "questions", "open_interventions", "overdue_interventions",
                                   "raised_interventions", "plant_score", "verdict", "notes"} <= set(BRIEF_FIELDS))

# ── 3. The glue ───────────────────────────────────────────────────────


def body(source, name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@frappe)|\Z)" % re.escape(name), source, re.S)
    return found.group(0) if found else ""


for source, name, method in ((GLUE, "excellence", "rates_from_payroll"), (GLUE, "excellence", "section_defaults"),
                             (GLUE, "excellence", "fetch_crew"), (SHEET, "excellence_sheet", "fetch_clock"),
                             (SHEET, "excellence_sheet", "paste_rows"), (BRIEF, "excellence_brief", "build"),
                             (BRIEF, "excellence_brief", "send")):
    check("glue: %s.%s is whitelisted and checks the user's right" % (name, method),
          "@frappe.whitelist()\ndef %s(" % method in source and "check_permission(" in body(source, method))
check("glue: the page is for its roles and kept five minutes for each user",
      "frappe.PermissionError" in body(PAGE, "data") and "frappe.cache.set_value(key, found, user=" in PAGE
      and "expires_in_sec=CACHE_SECONDS" in PAGE)
check("glue: the scorecards read the summaries through the user's permissions with GROUP BY",
      "frappe.get_list(doctype, filters=filters, fields=by + _sums(), group_by=" in SUMMARY
      and "aggregate(" in SUMMARY)
check("glue: no list of employee numbers where the rows carry the plant and section: cases, grievances, assessments",
      "employee\": [\"in\"" not in body(SUMMARY, "cases_between") and "custom_branch" in body(SUMMARY, "grievance_rows")
      and '"work_section"' in body(SUMMARY, "competency") and "raised_by" not in SUMMARY)
check("glue: one read of each kind for all the supervisors, none in the loop over them",
      "frappe." not in body(SUMMARY, "supervisor_rows").split("for person in people:")[1])
check("glue: repeat cases counted in one pass", "rules.window_counts(" in body(SUMMARY, "case_facts")
      and "for other in rows" not in SUMMARY)
check("glue: a case's legal flags as stored, kept current with the suspension history",
      "rules.case_flags(" not in body(SUMMARY, "case_facts") and "rules.suspension_history(" in body(
          GLUE, "refresh_case_flags") and "rules.suspended_before(history" in body(GLUE, "refresh_case_flags"))
check("glue: an intervention is written every night only when its overdue flag changes",
      'if state["overdue"] == cint(row.overdue):\n            continue' in body(GLUE, "daily")
      and "days_open" not in body(GLUE, "daily"))
check("glue: a submitted shift writes its summaries, a cancelled one takes them away",
      "excellence_summary.write_shift(doc)" in body(GLUE, "shift_on_submit")
      and "excellence_summary.remove_shift(doc)" in body(GLUE, "shift_on_cancel")
      and "rebuild_week(" in body(SUMMARY, "write_shift") and "rebuild_week(" in body(SUMMARY, "remove_shift"))
check("glue: a section's week from its days, scored from the totals",
      "rules.period_scores(t, s)" in body(SUMMARY, "rebuild_week"))
check("glue: the shift's standard and roster on its date", "section_standard(section, doc.report_date)"
      in body(GLUE, "shift_validate") and "rules.lead_on(rows, doc.report_date, doc.shift)" in body(GLUE, "shift_validate"))
check("glue: the clock: attendance, assignments, overtime, incidents, pay, read for the crew at once",
      all(name in CLOCK for name in ('"Attendance"', '"Shift Assignment"', '"Overtime Request Employee"',
                                     '"Safety Incident"', "pay.monthly_gross(employee, day)"))
      and "frappe.cache.set_value(key, kept" in CLOCK)
check("glue: the crew's PPE ticks are kept when it is fetched again", "ticked" in body(CLOCK, "fill"))
check("glue: the sheet's heavy work runs in the background, a shift at a time, with its progress",
      all("frappe.enqueue(" in body(SHEET, name) and 'queue="long"' in body(SHEET, name)
          and "deduplicate=True" in body(SHEET, name) for name in ("fetch_clock", "sheet_on_submit", "sheet_on_cancel"))
      and "frappe.db.commit()" in body(SHEET, "run_fetch") and "frappe.publish_progress(" in body(SHEET, "run_submit"))
check("glue: the approval refuses shifts neither entered nor marked Not Worked",
      'state["missing"]' in body(SHEET, "sheet_before_submit"))
check("glue: one row a section and shift on a sheet, at the database", "add_unique(ROW, [\"parent\", \"work_section\", "
                                                                         "\"shift\"]" in SHEET)
check("glue: the brief's Monday mail, one a person", "by_user.setdefault(user, []).append(doc)" in body(BRIEF, "send_all"))
check("glue: the board pack's slide", "\ndef board_slide(company, start, end, branch=None):" in BRIEF)
check("glue: the LMS still reads the shifts and their totals", "\ndef shift_rows(start, end, company=None, branch=None, "
                                                               "section=None, shift=None, supervisor=None):" in GLUE
      and "count" in R.LEGACY and "waste" in R.LEGACY)

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("wiring: the case's cause and flags on validate", re.search(
    r'"Disciplinary Case": \{\s*"validate": "hrms_addon\.hrms_addon\.excellence\.case_validate"', HOOKS))
check("wiring: the Overtime Request's Work Section on validate", re.search(
    r'"Overtime Request": \{\s*"validate": "hrms_addon\.hrms_addon\.excellence\.fill_section"', HOOKS))
check("wiring: every day, Monday morning, the nightly check, the role at migrate",
      '"hrms_addon.hrms_addon.excellence.daily"' in HOOKS and '"0 6 * * 1": ["hrms_addon.hrms_addon.excellence.weekly"]'
      in HOOKS and '"hrms_addon.hrms_addon.excellence_summary.nightly"' in HOOKS
      and '"hrms_addon.hrms_addon.excellence.setup_on_migrate"' in HOOKS)
FIXTURES = {row.get("name"): row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
check("wiring: the Employee's section is indexed; the grievance has its section", FIXTURES[
    "Employee-custom_work_section"].get("search_index") == 1 and FIXTURES[
    "Employee Grievance-custom_work_section"]["fetch_from"] == "raised_by.custom_work_section"
      and '"Employee Grievance-custom_work_section"' in HOOKS)
PATCHES = read("hrms_addon", "patches.txt")
for patch in ("excellence_masters_and_history", "excellence_shift_keys_and_lines", "excellence_section_links",
              "excellence_summaries", "excellence_indexes"):
    check("wiring: the patch %s is listed and there" % patch, "hrms_addon.patches.v1_0.%s" % patch in PATCHES
          and os.path.exists(os.path.join(PACKAGE, "patches", "v1_0", patch + ".py")))
for name, calls in (("Work Section", ("section_autoname", "section_validate")),
                    ("Shift Report", ("shift_validate", "shift_on_update", "shift_on_submit", "shift_on_cancel",
                                      "shift_on_trash")),
                    ("People Log", ("log_validate",)), ("HR Intervention", ("intervention_validate",)),
                    ("Machine", ("machine_validate",)), ("Plant Order", ("order_validate",)),
                    ("Manufacturing Excellence Settings", ("settings_validate",))):
    folder = name.lower().replace(" ", "_")
    source = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    for call in calls:
        check("wiring: %s calls excellence.%s" % (name, call), "excellence.%s(self)" % call in source
              and "\ndef %s(" % call in GLUE)
SHEET_PY = read("hrms_addon", "hrms_addon", "doctype", "plant_day_sheet", "plant_day_sheet.py")
for call in ("sheet_autoname", "sheet_validate", "sheet_on_update", "sheet_before_submit", "sheet_on_submit",
             "sheet_on_cancel", "sheet_on_trash"):
    check("wiring: the day sheet calls excellence_sheet.%s" % call, "excellence_sheet.%s(self)" % call in SHEET_PY
          and "\ndef %s(" % call in SHEET)
check("wiring: the role is made at migrate", R.NEW_ROLES == (R.ME_OFFICER,))
PAGE_SPEC = json.load(open(os.path.join(APP, "page", "manufacturing_excellence", "manufacturing_excellence.json"),
                           encoding="utf-8"))
PAGE_ROLES = {"System Manager", "HR Manager", "HR User", R.ME_OFFICER, "Production Manager", "General Manager",
              "Executive Director", "Auditor"}
check("wiring: the page and who may open it, the same roles its call lets in",
      PAGE_SPEC["name"] == "manufacturing-excellence" and {row["role"] for row in PAGE_SPEC["roles"]} == PAGE_ROLES
      and all('"%s"' % role in PAGE or role == R.ME_OFFICER for role in PAGE_ROLES))
PRINT = json.load(open(os.path.join(APP, "print_format", "hr_partner_brief", "hr_partner_brief.json"), encoding="utf-8"))
check("wiring: the brief's print", PRINT["doc_type"] == "HR Partner Brief" and PRINT["standard"] == "Yes"
      and PRINT["html"].startswith("{{ print_control(doc) }}\n"))
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for target in ("manufacturing-excellence", "Plant Day Sheet", "HR Partner Brief", "Plant Order", "Machine",
               "Downtime Reason", "Section Week Summary", "Section Day Summary", "Section Downtime Summary",
               "Order Feasibility", "Labour Cost and Overtime", "Downtime and Money Lost", "Excellence Trends"):
    check("wiring: %s is on the menu" % target, NAV.count('"%s"' % target) >= 2)
DASH = read("hrms_addon", "hrms_addon", "dashboards_rules.py")
check("wiring: the desk home chases day sheets with shifts missing and waiting for approval",
      '"day_sheets_missing"' in DASH and '"day_sheets_unapproved"' in DASH)
# Frappe opens a script report only to someone who may report on its doctype
for folder in ("hr_excellence_scorecard", "shift_scorecard", "supervisor_scorecard", "repeat_cases",
               "order_feasibility", "labour_cost_and_overtime", "downtime_and_money_lost", "excellence_trends"):
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    reporters = {perm["role"] for perm in doctype(spec["ref_doctype"])["permissions"]
                 if perm.get("report") and not perm.get("permlevel")}
    check("wiring: everyone %s is for may report on %s" % (spec["name"], spec["ref_doctype"]),
          {row["role"] for row in spec["roles"]} <= reporters, {row["role"] for row in spec["roles"]} - reporters)
repeat = read("hrms_addon", "hrms_addon", "report", "repeat_cases", "repeat_cases.py")
check("wiring: Repeat Cases hides names from the settings, with no tick of its own",
      's["hide_names"]' in repeat and "hide_names" not in read("hrms_addon", "hrms_addon", "report", "repeat_cases",
                                                              "repeat_cases.js"))
CASE_READERS = {perm["role"] for perm in doctype("Disciplinary Case")["permissions"] if perm.get("read")}
check("wiring: Repeat Cases only for those who may read cases", {row["role"] for row in json.load(open(
    os.path.join(APP, "report", "repeat_cases", "repeat_cases.json"), encoding="utf-8"))["roles"]} <= CASE_READERS)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_excellence: OK")
