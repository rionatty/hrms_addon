# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The board's measures: targets, traffic lights, the seven board KPIs, the
eight health ratings, the drafted insight of each slide and the check of
HR's own words against the figures. No Frappe import
(scripts/verify_board_kpis.py); board_pack.py and board_dashboard.py feed it
board_pack_rules.summary() of each quarter.

  Board KPI Target   a metric's target for the company or one plant, from a
                     date (to a date): the direction that is better, how far
                     off it turns Watch (amber band) and Action Needed (red
                     band)
  a metric's light   against its target where there is one; else against
                     the same quarter a year before (or the quarter before):
                     no worse, On Track; worse by more than the tolerance,
                     Watch; by more than twice it, Action Needed
  an area's rating   the worst light of its metrics; HR may set another,
                     saying why
"""

import datetime
import re

ON_TRACK, WATCH, ACTION, BUILDING = "On Track", "Watch", "Action Needed", "Building"
LIGHTS = (ON_TRACK, WATCH, ACTION)
LOWER, HIGHER = "Lower is Better", "Higher is Better"
QUARTERS = ("Q1", "Q2", "Q3", "Q4")

# metric -> (summary field, unit, direction, how it is shown)
METRIC_DEFS = {
    "Monthly Attrition": ("attrition", "% a month", LOWER, "pct"),
    "Casual Churn": ("casual_churn", "% a quarter", LOWER, "pct"),
    "Permanent Churn": ("permanent_churn", "% a quarter", LOWER, "pct"),
    "Permanent Share": ("permanent_share", "%", HIGHER, "pct"),
    "Regrettable Exits": ("regrettable", "people", LOWER, "count"),
    "Staff Cost to Revenue": ("staff_cost_share", "%", LOWER, "pct"),
    "Overtime Share of Wage Bill": ("overtime_share", "%", LOWER, "pct"),
    "Labour Cost per kg": ("cost_per_kg", "UGX", LOWER, "money"),
    "Revenue per Employee": ("revenue_per_employee", "UGX a quarter", HIGHER, "money"),
    "Output per Employee": ("output_per_employee", "kg a month", HIGHER, "count"),
    "Revenue to Wage Cost": ("revenue_to_wage", "times", HIGHER, "ratio"),
    "LTIFR": ("ltifr", "per million hours", LOWER, "ratio"),
    "Incidents": ("incidents", "incidents", LOWER, "count"),
    "Training Hours per Employee": ("training_per_employee", "hours a quarter", HIGHER, "ratio"),
    "Absence Rate": ("absence_rate", "% of days", LOWER, "pct"),
    "Clock Attendance": ("clock_share", "% of days", HIGHER, "pct"),
    "Time to Fill": ("time_to_fill", "days", LOWER, "count"),
    "90-Day Retention": ("retention_90", "%", HIGHER, "pct"),
    "Succession Coverage": ("succession_coverage", "%", HIGHER, "pct"),
    "Skills Gap": ("skills_gap", "% of critical skills", LOWER, "pct"),
    "Data Issues": ("data_issues", "records", LOWER, "count"),
    "Overdue Safety Actions": ("capa_overdue", "actions", LOWER, "count"),
}
METRIC_NAMES = tuple(METRIC_DEFS)
# the seven KPIs the board asked for, in its own order: (number, name, the metric that reads it)
BOARD_KPIS = (
    ("01", "Workforce productivity & ROI", "Revenue per Employee"),
    ("02", "Regrettable attrition", "Regrettable Exits"),
    ("03", "AI / digital adoption impact", "Clock Attendance"),
    ("04", "Quality of hire", "90-Day Retention"),
    ("05", "Revenue / cost per employee", "Revenue to Wage Cost"),
    ("06", "Talent risk & succession coverage", "Succession Coverage"),
    ("07", "Skills gap against strategy", "Skills Gap"),
)
# the eight areas the board rates, and the metrics each is rated by
AREA_METRICS = (
    ("Workforce Stability", ("Permanent Share", "Permanent Churn")),
    ("Talent Acquisition", ("Time to Fill", "90-Day Retention")),
    ("Retention & Turnover", ("Monthly Attrition", "Casual Churn", "Regrettable Exits")),
    ("Safety (EHS)", ("LTIFR", "Incidents")),
    ("Compensation & Payroll", ("Staff Cost to Revenue", "Overtime Share of Wage Bill", "Labour Cost per kg")),
    ("Learning & Capability", ("Training Hours per Employee", "Skills Gap")),
    ("Compliance & Governance", ("Data Issues", "Overdue Safety Actions")),
    ("HR Digitalisation", ("Clock Attendance",)),
)
AREAS = tuple(area for area, _metrics in AREA_METRICS)
# the scorecard's metrics, plant by plant (board_dashboard.py)
SCORECARD = ("Monthly Attrition", "Casual Churn", "Staff Cost to Revenue", "Labour Cost per kg",
             "Overtime Share of Wage Bill", "LTIFR", "Training Hours per Employee", "Absence Rate")
# the dashboard's cards, in order
CARDS = ("Head Count", "Monthly Attrition", "Casual Churn", "Regrettable Exits", "Staff Cost to Revenue",
         "Revenue per Employee", "Labour Cost per kg", "Overtime Share of Wage Bill", "LTIFR",
         "Training Hours per Employee", "Clock Attendance", "Succession Coverage")
# a card that is not a metric with a target
EXTRA_CARDS = {"Head Count": ("head_count", "people", None, "count")}
# the pay figures, only for those who may see money
MONEY_METRICS = ("Staff Cost to Revenue", "Labour Cost per kg", "Overtime Share of Wage Bill",
                 "Revenue per Employee", "Revenue to Wage Cost")
# a trend no worse than this (relative, percent) is On Track where there is no target
TOLERANCE = 10.0
ACTION_STATUSES = ("Not Started", "On Track", "At Risk", "Done", "Dropped")
OPEN_ACTIONS = ("Not Started", "On Track", "At Risk")


def definition(metric):
    """(summary field, unit, direction, kind) of a metric or a card."""
    return METRIC_DEFS.get(metric) or EXTRA_CARDS.get(metric) or (None, "", None, "count")


# ── Targets ───────────────────────────────────────────────────────────
def target_errors(row):
    """What is wrong with a Board KPI Target: [message]."""
    errors = []
    if row.get("metric") not in METRIC_DEFS:
        errors.append("Pick a metric from the list.")
    start, end = _date(row.get("from_date")), _date(row.get("to_date"))
    if start and end and end < start:
        errors.append("The target ends before it starts.")
    amber, red = row.get("amber_band"), row.get("red_band")
    if _num(amber) < 0 or _num(red) < 0:
        errors.append("A band is how far off the target, never below nought.")
    if red not in (None, "") and _num(red) < _num(amber):
        errors.append("The red band is at least the amber band.")
    return errors


def target_for(targets, metric, branch, first, last):
    """The target that stands for the metric over the period: the plant's own
    before the company's, the latest start first. targets: [{"metric",
    "branch", "from_date", "to_date", "target", "direction", "amber_band",
    "red_band"}]."""
    first, last = _date(first), _date(last)
    found = [row for row in targets or () if row.get("metric") == metric
             and (not row.get("branch") or row.get("branch") == branch)
             and _date(row.get("from_date")) and _date(row.get("from_date")) <= last
             and (not _date(row.get("to_date")) or _date(row.get("to_date")) >= first)]
    if not found:
        return None
    found.sort(key=lambda row: (bool(row.get("branch")), _date(row.get("from_date"))), reverse=True)
    return found[0]


def light(value, target):
    """On Track, Watch or Action Needed against a target; None with no value
    or no target. Off target by up to the amber band is still On Track, by
    more than the red band Action Needed, between them Watch."""
    if value is None or not target:
        return None
    goal = _num(target.get("target"))
    worse = (_num(value) - goal) if target.get("direction") != HIGHER else (goal - _num(value))
    amber = _num(target.get("amber_band"))
    red = _num(target.get("red_band")) if target.get("red_band") not in (None, "") else amber
    if worse <= amber:
        return ON_TRACK
    if worse <= red:
        return WATCH
    return ACTION


def trend_light(value, before, direction, tolerance=TOLERANCE):
    """With no target: against the period before. No worse, On Track; worse
    by more than the tolerance, Watch; by more than twice it, Action Needed."""
    if value is None or before is None or not direction:
        return None
    value, before = _num(value), _num(before)
    worse = (value - before) if direction == LOWER else (before - value)
    if worse <= 0:
        return ON_TRACK
    if not before:
        return WATCH
    relative = 100.0 * worse / abs(before)
    if relative <= tolerance:
        return ON_TRACK
    return WATCH if relative <= 2 * tolerance else ACTION


def worst(lights):
    found = [entry for entry in lights if entry in LIGHTS]
    return max(found, key=LIGHTS.index) if found else None


# ── Each metric, read ─────────────────────────────────────────────────
def read_metric(metric, now, before=None, last_year=None, target=None, tolerance=TOLERANCE):
    """{metric, value, unit, direction, target, light, basis, previous,
    last_year, change}: now, before and last_year are summaries (dicts of
    figures), before the quarter before."""
    field, unit, direction, _kind = definition(metric)
    value = (now or {}).get(field)
    previous = (before or {}).get(field)
    year_ago = (last_year or {}).get(field)
    out = {"metric": metric, "value": value, "unit": unit, "direction": direction,
           "target": _num(target.get("target")) if target else None, "previous": previous, "last_year": year_ago,
           "change": _change(value, previous)}
    if target:
        out["light"] = light(value, target)
        out["basis"] = "%s against a target of %s" % (show(metric, value), show(metric, target.get("target")))
    else:
        compare, against = (year_ago, "a year before") if year_ago is not None else (previous, "the quarter before")
        out["light"] = trend_light(value, compare, direction, tolerance)
        out["basis"] = "%s against %s %s" % (show(metric, value), show(metric, compare), against) \
            if compare is not None and value is not None else ("%s, no target set" % show(metric, value)
                                                                 if value is not None else "No data")
    return out


def show(metric, value):
    """A metric's value as the board reads it."""
    if value is None:
        return "–"
    kind = definition(metric)[3]
    value = float(value)
    if kind == "pct":
        return "%.1f%%" % value
    if kind == "money":
        return "UGX {:,.0f}".format(value) if abs(value) < 1e6 else "UGX {:,.1f}M".format(value / 1e6)
    if kind == "ratio":
        return "{:,.2f}".format(value).rstrip("0").rstrip(".")
    return "{:,.0f}".format(value)


# ── The seven KPIs and the eight ratings ──────────────────────────────
def board_kpis(now, before=None, last_year=None, targets=None, first=None, last=None, plants=None, by_plant=None):
    """The seven KPIs, each with its reading, what it tells the board (a
    draft for HR) and its light. by_plant: {plant: summary} for the
    readings that name the plants."""
    out = []
    for number, name, metric in BOARD_KPIS:
        target = target_for(targets, metric, None, first, last)
        read = read_metric(metric, now, before, last_year, target)
        read.update({"number": number, "name": name, "reading": reading(metric, now, before, by_plant or {}),
                     "tells": tells(metric, read)})
        if read["value"] is None:
            read["light"] = BUILDING
        out.append(read)
    return out


def area_ratings(now, before=None, last_year=None, targets=None, first=None, last=None, tolerance=TOLERANCE):
    """Each area's rating, from the worst light of its metrics, and the basis
    the board reads: [{area, rating, basis, metrics}]."""
    out = []
    for area, metrics in AREA_METRICS:
        reads = [read_metric(metric, now, before, last_year, target_for(targets, metric, None, first, last), tolerance)
                 for metric in metrics]
        rating = worst(read["light"] for read in reads)
        basis = "; ".join("%s %s" % (read["metric"], read["basis"]) for read in reads if read["value"] is not None)
        out.append({"area": area, "rating": rating or "", "basis": basis or "No data", "metrics": reads})
    return out


def override_errors(row):
    """A rating or status HR set themselves needs their reason."""
    if _int(row.get("override")) and not (row.get("override_reason") or "").strip():
        return ["Say why the rating differs from the figures."]
    return []


def settle(row, computed_field, final_field):
    """The final rating: HR's where they overrode it, else the computed one."""
    if not _int(row.get("override")):
        value = row.get(computed_field) or ""
        if isinstance(row, dict):
            row[final_field] = value
        else:
            setattr(row, final_field, value)
    return row


def reading(metric, now, before, by_plant):
    now, before = now or {}, before or {}
    if metric == "Revenue per Employee":
        parts = ["Revenue %s per employee (%s on the quarter)" % (
            show(metric, now.get("revenue_per_employee")), signed(_change(now.get("revenue_per_employee"),
                                                                         before.get("revenue_per_employee")), "%"))]
        outputs = ["%s %s kg" % (plant, "{:,.0f}".format(figures["output_per_employee"]))
                   for plant, figures in sorted(by_plant.items()) if figures.get("output_per_employee")]
        if outputs:
            parts.append("Output per employee a month: " + ", ".join(outputs))
        return ". ".join(parts)
    if metric == "Regrettable Exits":
        exits = _num(now.get("exits"))
        return "%s regrettable exits (quarter before: %s); %s of all exits" % (
            show(metric, now.get("regrettable")), show(metric, before.get("regrettable")),
            "%.1f%%" % (100.0 * _num(now.get("regrettable")) / exits) if exits else "–")
    if metric == "Clock Attendance":
        return "%s of attendance days recorded by the clock" % show(metric, now.get("clock_share"))
    if metric == "90-Day Retention":
        return "%s of the hires due their 90 days in the quarter stayed (%s hires)" % (
            show(metric, now.get("retention_90")), show("Incidents", now.get("retention_cohort")))
    if metric == "Revenue to Wage Cost":
        return "Revenue %s against wage cost %s per employee for the quarter" % (
            show("Revenue per Employee", now.get("revenue_per_employee")),
            show("Revenue per Employee", now.get("wage_per_employee")))
    if metric == "Succession Coverage":
        return "%s of %s critical roles covered; %s successors ready now; %s top talent at high flight risk" % (
            show("Incidents", now.get("covered_roles")), show("Incidents", now.get("critical_roles")),
            show("Incidents", now.get("ready_now")), show("Incidents", now.get("top_talent_at_risk")))
    if metric == "Skills Gap":
        return "%s of critical skills assessed below the level the job needs (%s assessed)" % (
            show(metric, now.get("skills_gap")), show("Incidents", now.get("skills_assessed")))
    return show(metric, (now or {}).get(definition(metric)[0]))


def tells(metric, read):
    """What a KPI's light tells the board, drafted for HR to change."""
    state = read.get("light")
    if read.get("value") is None:
        return "Not yet measured: the records it is read from are not in the system yet."
    moved = read.get("change")
    better = moved is not None and ((moved < 0) == (read.get("direction") == LOWER)) and moved != 0
    trend = "improving" if better else ("unchanged" if not moved else "worsening")
    if state is None:
        return "No target set yet, and %s." % trend
    if state == ON_TRACK:
        return "On track and %s." % trend
    if state == WATCH:
        return "Short of where it should be and %s: watch next quarter." % trend
    return "Off target and %s: needs a plan." % trend


# ── The insight drafted for each slide ────────────────────────────────
def insights(figures):
    """{report field: a draft} from the quarter's figures; each a plain
    statement of what the figures show, for HR to keep or rewrite."""
    out = {}
    head = _total(figures.get("head_count"))
    rows = [row for row in figures.get("head_count") or [] if row.get("plant")]
    if head:
        lead = max(rows, key=lambda row: _num(row.get("qoq")), default=None) if rows else None
        text = "Head count %s %s (%s) on the quarter to %s" % (
            "rose" if _num(head.get("qoq")) > 0 else "fell" if _num(head.get("qoq")) < 0 else "held",
            whole(abs(_num(head.get("qoq")))), signed(_change(head.get("total"),
                                                             _num(head.get("total")) - _num(head.get("qoq"))), "%"),
            whole(head.get("total")))
        if lead and _num(lead.get("qoq")) > 0:
            text += ", led by %s (%s)" % (lead["plant"], signed(lead.get("qoq")))
        text += ". Permanent share %s from %s to %s." % (
            _moved(head.get("permanent_share_start"), head.get("permanent_share_end")),
            pct(head.get("permanent_share_start")), pct(head.get("permanent_share_end")))
        out["head_count_insight"] = text
    hires = _total(figures.get("recruitment"))
    exits = _total(figures.get("exits"))
    if hires:
        share = 100.0 * _num(hires.get("replacements")) / _num(hires.get("total")) if _num(hires.get("total")) else 0
        text = "%s hires: %s replaced leavers (%s), %s added capacity" % (
            whole(hires.get("total")), whole(hires.get("replacements")), pct(share, 0), whole(hires.get("additions")))
        if _num(hires.get("unclassified")):
            text += " and %s had no requisition" % whole(hires.get("unclassified"))
        text += "."
        if exits:
            text += " Hires %s exits (%s against %s)." % (
                "outnumbered" if _num(hires.get("total")) > _num(exits.get("total")) else
                "matched" if _num(hires.get("total")) == _num(exits.get("total")) else "fell short of",
                whole(hires.get("total")), whole(exits.get("total")))
        out["recruitment_insight"] = text
    if exits:
        months = exits.get("months") or []
        rates = [entry.get("rate") for entry in months]
        text = "Monthly attrition ran %s, a quarter average of %s against a target of %s" % (
            " → ".join(pct(rate) for rate in rates), pct(exits.get("average")), pct(figures.get("target"), 0))
        over = [row["plant"] for row in figures.get("exits") or [] if row.get("plant") and row.get("over_target")]
        text += ("; over target in a month: %s." % ", ".join(over)) if over else "; no plant over target in any month."
        if exits.get("last_year_average") is not None:
            text += " A year before: %s." % pct(exits.get("last_year_average"))
        out["exits_insight"] = text
    churn = _total(figures.get("churn"))
    if churn:
        text = "Permanent churn %s a quarter, casual churn %s" % (pct(churn["permanent"][1]), pct(churn["casual"][1]))
        if churn.get("permanent_last_year"):
            text += " (a year before: %s and %s)" % (pct(churn["permanent_last_year"][1]),
                                                     pct(churn["casual_last_year"][1]))
        if churn.get("casual_share_of_exits") is not None:
            text += ". Casuals are %s of the workforce and %s of leavers" % (
                pct(churn.get("casual_share_of_workforce"), 0), pct(churn.get("casual_share_of_exits"), 0))
        recon = _total(figures.get("reconciliation"))
        if recon:
            text += ". The movements %s the head count%s." % (
                "reconcile to" if not _num(recon.get("variance")) else "miss",
                "" if not _num(recon.get("variance")) else " by %s" % signed(recon.get("variance")))
        out["churn_insight"] = text
    pay = _total(figures.get("wage_bill"))
    if pay:
        text = "Wage bill %s for the quarter (%s on the quarter, %s on a year before)" % (
            money(pay.get("wage_bill")), signed(pay.get("qoq"), "%"), signed(pay.get("yoy"), "%"))
        if pay.get("cost_per_kg"):
            text += "; cost per kg %s" % whole(pay.get("cost_per_kg"))
            if pay.get("previous_cost_per_kg"):
                text += " against %s the quarter before" % whole(pay.get("previous_cost_per_kg"))
        out["wage_insight"] = text + "."
        drivers = sorted((row for row in figures.get("components") or [] if row.get("share_of_increase")),
                         key=lambda row: -_num(row.get("share_of_increase")))[:2]
        text = "Overtime of every kind %s, %s of the wage bill" % (money(pay.get("overtime")),
                                                                    pct(pay.get("overtime_share")))
        if pay.get("overtime_last_year"):
            text += " (%s on a year before)" % signed(_change(pay.get("overtime"), pay.get("overtime_last_year")), "%")
        if drivers:
            text += ". Most of the increase: " + ", ".join("%s %s" % (row["group"], pct(row["share_of_increase"], 0))
                                                           for row in drivers)
        out["overtime_insight"] = text + "."
    labour = _total(figures.get("labour_cost"))
    if labour and labour.get("share") is not None:
        text = "Staff cost %s of revenue (quarter before: %s)" % (pct(labour.get("share")),
                                                                  pct(labour.get("previous_share")))
        worst_plant = max((row for row in figures.get("labour_cost") or [] if row.get("plant") and row.get("share")),
                          key=lambda row: _num(row.get("share")), default=None)
        if worst_plant:
            text += "; highest at %s (%s)" % (worst_plant["plant"], pct(worst_plant.get("share")))
        out["labour_insight"] = text + "."
    safety = _total(figures.get("safety"))
    if safety:
        text = "%s incidents (%s a year before), %s lost time, %s near misses reported" % (
            whole(safety.get("total")), whole(safety.get("last_year")), whole(safety.get("lost_time")),
            whole(safety.get("near_misses")))
        if safety.get("ltifr") is not None:
            text += "; LTIFR %s" % show("LTIFR", safety.get("ltifr"))
        out["ehs_insight"] = text + "."
    if head and pay:
        out["yoy_insight"] = "Head count %s and the wage bill %s on a year before." % (
            signed(_change(head.get("total"), (figures.get("monthly_head_count_last_year") or [None])[-1]), "%"),
            signed(pay.get("yoy"), "%"))
    parts = [out[key].split(". ")[0] for key in ("head_count_insight", "labour_insight", "exits_insight")
             if out.get(key)]
    if parts:
        out["headline"] = ". ".join(part.rstrip(".") for part in parts) + "."
    if labour and labour.get("revenue_per_employee"):
        out["ceo_view"] = "Revenue per employee %s (%s on the quarter); staff cost %s of revenue." % (
            money(labour.get("revenue_per_employee")),
            signed(_change(labour.get("revenue_per_employee"), labour.get("previous_revenue_per_employee")), "%"),
            pct(labour.get("share")))
    return out


# ── HR's own words against the figures ───────────────────────────────
RISE = ("rose", "rise", "rising", "grew", "grow", "growing", "increased", "increase", "increasing", "up", "higher",
        "climbed", "jumped")
FALL = ("fell", "fall", "falling", "dropped", "drop", "declined", "decline", "decreased", "decrease", "down", "lower",
        "shrank", "reduced")
FLAT = ("held", "flat", "steady", "unchanged", "stable")
# what each insight field speaks of: (field label, [(words naming the figure, the figure's change)])
SUBJECTS = {
    "head_count_insight": ("head count", "workforce"),
    "recruitment_insight": ("hires", "hiring", "recruitment"),
    "exits_insight": ("attrition", "exits", "leavers"),
    "churn_insight": ("churn",),
    "wage_insight": ("wage bill", "payroll", "cost per kg"),
    "overtime_insight": ("overtime",),
    "labour_insight": ("staff cost", "labour cost", "revenue"),
    "yoy_insight": ("head count", "wage bill", "exits", "hires"),
}


def facts_of(figures):
    """{subject words: the change it made, in percent or in units} and every
    number the slides print, which HR's words may quote."""
    head, hires, exits = _total(figures.get("head_count")), _total(figures.get("recruitment")), \
        _total(figures.get("exits"))
    pay, labour = _total(figures.get("wage_bill")), _total(figures.get("labour_cost"))
    changes = {}
    if head:
        changes["head count"] = changes["workforce"] = _num(head.get("qoq"))
    if hires:
        changes["hires"] = changes["hiring"] = changes["recruitment"] = _change(hires.get("total"),
                                                                                hires.get("previous"))
    if exits:
        rates = [entry.get("rate") for entry in exits.get("months") or [] if entry.get("rate") is not None]
        changes["attrition"] = (rates[-1] - rates[0]) if len(rates) > 1 else None
        changes["exits"] = changes["leavers"] = _change(exits.get("total"), exits.get("last_year"))
    if pay:
        changes["wage bill"] = changes["payroll"] = pay.get("qoq")
        changes["overtime"] = _change(pay.get("overtime"), pay.get("overtime_last_year"))
        changes["cost per kg"] = _change(pay.get("cost_per_kg"), pay.get("previous_cost_per_kg"))
    if labour:
        changes["staff cost"] = changes["labour cost"] = (_num(labour.get("share")) - _num(labour.get("previous_share"))
                                                         if labour.get("previous_share") is not None else None)
        changes["revenue"] = _change(labour.get("revenue"), labour.get("previous_revenue"))
    churn = _total(figures.get("churn"))
    if churn and churn.get("casual_last_year"):
        changes["churn"] = _num(churn["casual"][1]) - _num(churn["casual_last_year"][1])
    return changes, set(_numbers_in(figures))


def text_flags(texts, figures, labels=None):
    """[(field, what the figures say)] where HR's words go against them: a
    figure said to rise that fell, to fall that rose, or to hold that moved;
    and a percentage no slide prints."""
    changes, numbers = facts_of(figures)
    flags = []
    for field, text in (texts or {}).items():
        if not (text or "").strip():
            continue
        name = (labels or {}).get(field, field)
        lowered = text.lower()
        for subject in SUBJECTS.get(field, ()):
            moved = changes.get(subject)
            if moved is None:
                continue
            for said in _claims(lowered, subject):
                if said == "rise" and moved < 0:
                    flags.append((name, "Says %s rose; the figures show it fell (%s)." % (subject, signed(moved))))
                elif said == "fall" and moved > 0:
                    flags.append((name, "Says %s fell; the figures show it rose (%s)." % (subject, signed(moved))))
                elif said == "flat" and abs(moved) >= 2:
                    flags.append((name, "Says %s held; the figures show it moved (%s)." % (subject, signed(moved))))
        for quoted in re.findall(r"(\d+(?:\.\d+)?)\s?%", text):
            value = float(quoted)
            if not any(abs(value - abs(number)) <= 0.15 for number in numbers):
                flags.append((name, "%s%% is not a figure of the quarter." % quoted))
    seen, out = set(), []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            out.append(flag)
    return out


def _claims(text, subject):
    """The directions said of a subject: a direction word within six words
    after it, or within three before it."""
    out = []
    for match in re.finditer(re.escape(subject), text):
        after = text[match.end():].split()[:6]
        before = text[:match.start()].split()[-3:]
        for word in [word.strip(".,;:()") for word in after + before]:
            if word in RISE:
                out.append("rise")
                break
            if word in FALL:
                out.append("fall")
                break
            if word in FLAT:
                out.append("flat")
                break
    return out


def _numbers_in(value):
    """Every number in the figures, and each rounded as the slides print it."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        yield round(float(value), 1)
        yield float(round(value))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _numbers_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _numbers_in(item)


# ── Board actions ─────────────────────────────────────────────────────
def due_date(year, quarter):
    """The last day of the quarter an action is due in."""
    if not year or quarter not in QUARTERS:
        return None
    month = QUARTERS.index(quarter) * 3 + 3
    following = datetime.date(int(year) + (month == 12), 1 if month == 12 else month + 1, 1)
    return following - datetime.timedelta(days=1)


def action_errors(row):
    errors = []
    if row.get("status") not in ACTION_STATUSES:
        errors.append("Pick a status from the list.")
    if not 0 <= _num(row.get("progress")) <= 100:
        errors.append("Progress is between 0 and 100.")
    raised, due = (row.get("raised_year"), row.get("raised_quarter")), (row.get("due_year"), row.get("due_quarter"))
    if all(raised) and all(due) and (int(due[0]), QUARTERS.index(due[1])) < (int(raised[0]), QUARTERS.index(raised[1])):
        errors.append("An action is due no earlier than the quarter it was raised in.")
    return errors


def actions_for(actions, year, quarter):
    """The actions a quarter's pack shows: every one still open, and those
    done or dropped within the quarter; the most pressing first."""
    first = datetime.date(int(year), QUARTERS.index(quarter) * 3 + 1, 1)
    last = due_date(year, quarter)
    shown = [row for row in actions or () if row.get("status") in OPEN_ACTIONS
             or (_date(row.get("done_on")) and first <= _date(row.get("done_on")) <= last)]
    order = {"At Risk": 0, "Not Started": 1, "On Track": 2, "Done": 3, "Dropped": 4}
    return sorted(shown, key=lambda row: (order.get(row.get("status"), 5), str(_date(row.get("due_date")) or "9"),
                                          row.get("imperative") or ""))


def overdue(row, today):
    return row.get("status") in OPEN_ACTIONS and _date(row.get("due_date")) and _date(row.get("due_date")) < _date(today)


# ── Hiring: 90 days and time to fill ──────────────────────────────────
def retention_90(hires, exits, first, last):
    """Of the hires whose 90th day fell in the period, the share still there
    on it. hires: {employee: joined}; exits: {employee: relieved}."""
    first, last = _date(first), _date(last)
    cohort = [employee for employee, joined in (hires or {}).items()
              if _date(joined) and first <= _date(joined) + datetime.timedelta(days=90) <= last]
    if not cohort:
        return None, 0
    stayed = [employee for employee in cohort
              if not (_date((exits or {}).get(employee))
                      and _date(exits[employee]) < _date(hires[employee]) + datetime.timedelta(days=90))]
    return round(100.0 * len(stayed) / len(cohort), 1), len(cohort)


def fill_days(rows):
    """Average days, requisition to joining and each step between:
    rows [{"requested", "advertised", "offered", "joined"}]."""
    steps = {"to_advert": ("requested", "advertised"), "to_offer": ("advertised", "offered"),
             "to_join": ("offered", "joined"), "total": ("requested", "joined")}
    out = {}
    for key, (start, end) in steps.items():
        days = [(_date(row.get(end)) - _date(row.get(start))).days for row in rows or ()
                if _date(row.get(start)) and _date(row.get(end)) and _date(row.get(end)) >= _date(row.get(start))]
        out[key] = round(sum(days) / len(days)) if days else None
    out["hires"] = len([row for row in rows or () if _date(row.get("requested"))])
    return out


# ── Numbers as the board reads them ───────────────────────────────────
def whole(value):
    return "–" if value is None else "{:,.0f}".format(float(value))


def pct(value, places=1):
    return "–" if value is None else ("{:.%df}%%" % places).format(float(value))


def money(value):
    if value is None:
        return "–"
    value = float(value)
    return "UGX {:,.2f}B".format(value / 1e9) if abs(value) >= 1e9 else "UGX {:,.0f}M".format(value / 1e6)


def signed(value, suffix=""):
    if value is None:
        return "–"
    value = float(value)
    text = ("{:,.1f}" if suffix == "%" or value != int(value) else "{:,.0f}").format(abs(value))
    return ("+" if value > 0 else "−" if value < 0 else "") + text + suffix


def _moved(before, after):
    if before is None or after is None:
        return "stood"
    return "rose" if after > before else "fell" if after < before else "held"


def _total(rows):
    return next((row for row in rows or [] if row.get("plant") is None), None)


def change(now, before):
    """The change from before to now, as a percentage; None where either is missing or before is nought."""
    return _change(now, before)


def _change(now, before):
    if now is None or before in (None, 0, 0.0):
        return None
    return round(100.0 * (_num(now) - _num(before)) / abs(_num(before)), 1)


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


def _int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
