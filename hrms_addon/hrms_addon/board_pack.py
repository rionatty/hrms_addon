# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The HR board pack on the site (Luuka's quarterly HR Board Report). The
quarter's rules are in board_pack_rules.py, the measures in
board_kpi_rules.py, the facts in board_facts.py; the deck and the workbook
are made by board_deck.py.

  Board Report Settings   the hours in a day, the months built each night,
                          the trend tolerance, the wage bill's component
                          groups (seeded from the components' names)
  Board Finance Figures   a quarter's revenue, output and staff cost by plant
                          and month, typed by Finance (decided 17 Nov 2026)
  Board KPI Target        a metric's target for the company or a plant
  Board Action            the strategic people agenda, carried quarter to
                          quarter with its progress
  HR Board Report         the quarter's figures from the facts of its months,
                          the quarter before, the same quarter a year before
                          and the eight quarters to it; the seven KPIs and the
                          eight ratings worked out, HR's own where they say
                          why; each slide's insight drafted; HR's words checked
                          against the figures. Approved, it locks its months.
"""

import datetime
import json
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now, today

from hrms_addon.hrms_addon import board_facts, board_facts_rules as facts_rules, board_kpi_rules as kpi
from hrms_addon.hrms_addon import board_pack_rules as rules

SETTINGS = "Board Report Settings"
FINANCE = "Board Finance Figures"
FINANCE_LINE = "Board Finance Line"
SNAPSHOT = "HR Monthly Snapshot"
REPORT = "HR Board Report"
TARGET = "Board KPI Target"
ACTION = "Board Action"
BOARD_ROLE = "Board Member"
# the report's words the deck prints, each checked against the figures
TEXTS = ("headline", "head_count_insight", "recruitment_insight", "exits_insight", "churn_insight", "yoy_insight",
         "wage_insight", "overtime_insight", "labour_insight", "ceo_view", "ld_insight", "ehs_insight")
QUARTERS_SHOWN = 8


# ── Settings ──────────────────────────────────────────────────────────
def settings():
    """board_facts.settings and the monthly attrition target."""
    out = board_facts.settings()
    found = kpi.target_for(_targets(None), "Monthly Attrition", None, today(), today())
    out["target"] = flt(found.get("target")) if found else 5.0
    return out


def settings_validate(doc):
    seen = set()
    for row in doc.get("component_groups") or []:
        if row.salary_component in seen:
            frappe.throw(_("{0} is listed twice.").format(row.salary_component), title=_(SETTINGS))
        seen.add(row.salary_component)
    if cint(doc.get("refresh_months")) < 0:
        frappe.throw(_("Months Built Again Each Night cannot be below nought."), title=_(SETTINGS))


def setup_on_migrate():
    """The earnings' groups from their names, once; then HR's. The board's
    role, and the monthly attrition target the board set (5% a month), once."""
    try:
        doc = frappe.get_single(SETTINGS)
        if not doc.get("component_groups"):
            for name in frappe.get_all("Salary Component", filters={"type": "Earning"}, pluck="name",
                                       order_by="name asc"):
                group = rules.component_group(name)
                if group != "Other":
                    doc.append("component_groups", {"salary_component": name, "component_group": group})
            doc.flags.ignore_permissions = True
            doc.save()
        if not frappe.db.exists("Role", BOARD_ROLE):
            frappe.get_doc({"doctype": "Role", "role_name": BOARD_ROLE, "desk_access": 1}).insert(
                ignore_permissions=True)
        if frappe.db.exists("DocType", TARGET) and not frappe.db.exists(TARGET, {"metric": "Monthly Attrition"}):
            for company in frappe.get_all("Company", pluck="name"):
                frappe.get_doc({"doctype": TARGET, "company": company, "metric": "Monthly Attrition",
                                "from_date": "2025-01-01", "target": 5, "direction": kpi.LOWER, "amber_band": 0,
                                "red_band": 1}).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="HRMS Addon: setting up the board pack")


@frappe.whitelist(methods=["POST"])
def build_from_settings():
    """The settings' Build the Months button."""
    doc = frappe.get_single(SETTINGS)
    doc.check_permission("write")
    if not doc.get("build_company") or not doc.get("build_from"):
        frappe.throw(_("Pick the company and the first month."), title=_(SETTINGS))
    return board_facts.build_months(doc.build_company, doc.build_from)


# ── What Finance type ─────────────────────────────────────────────────
def finance_autoname(doc):
    doc.name = "%s %s %s" % (doc.year, doc.quarter, doc.company)


def finance_validate(doc):
    months = {datetime.date(year, month, 1) for year, month in rules.quarter_months(doc.year, doc.quarter)}
    seen = set()
    for row in doc.get("lines") or []:
        row.month_start = getdate(row.month_start).replace(day=1) if row.month_start else None
        if row.month_start not in months:
            frappe.throw(_("Row {0}: {1} is not a month of {2} {3}.").format(
                row.idx, frappe.utils.format_date(row.month_start), doc.quarter, doc.year), title=_(FINANCE))
        if (row.branch, row.month_start) in seen:
            frappe.throw(_("Row {0}: {1} is in twice for that month.").format(row.idx, row.branch), title=_(FINANCE))
        seen.add((row.branch, row.month_start))


@frappe.whitelist(methods=["POST"])
def add_finance_lines(name):
    """A line for each plant with people, for each month of the quarter.
    Returns how many were added."""
    doc = frappe.get_doc(FINANCE, name)
    doc.check_permission("write")
    have = {(row.branch, getdate(row.month_start)) for row in doc.get("lines") or []}
    added = 0
    for plant in _plants(doc.company):
        for year, month in rules.quarter_months(doc.year, doc.quarter):
            first = datetime.date(year, month, 1)
            if (plant, first) not in have:
                doc.append("lines", {"branch": plant, "month_start": first})
                added += 1
    doc.save()
    return added


def _plants(company):
    return sorted(plant for plant in frappe.get_all(
        "Employee", filters={"company": company, "status": "Active", "branch": ["is", "set"]}, pluck="branch",
        distinct=True) if plant)


# ── Targets and actions ───────────────────────────────────────────────
def target_autoname(doc):
    doc.name = "%s %s %s" % (doc.metric, doc.branch or _("All Plants"), getdate(doc.from_date))


def target_validate(doc):
    for message in kpi.target_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(TARGET))
    unit, direction = kpi.definition(doc.metric)[1:3]
    doc.unit = unit
    if not doc.get("direction"):
        doc.direction = direction


def _targets(company):
    filters = {"company": company} if company else {}
    if not frappe.db.exists("DocType", TARGET):
        return []
    return frappe.get_all(TARGET, filters=filters, fields=["metric", "branch", "from_date", "to_date", "target",
                                                           "direction", "amber_band", "red_band"],
                          limit_page_length=0)


def action_validate(doc):
    for message in kpi.action_errors(doc.as_dict()):
        frappe.throw(_(message), title=_(ACTION))
    doc.due_date = kpi.due_date(doc.due_year, doc.due_quarter)
    if doc.status in ("Done", "Dropped"):
        doc.done_on = doc.get("done_on") or today()
        if doc.status == "Done":
            doc.progress = 100
    else:
        doc.done_on = None


def _actions(company, year, quarter):
    fields = ["name", "imperative", "lever", "area", "action_owner_name", "status", "progress", "due_year",
              "due_quarter", "due_date", "done_on", "milestone", "progress_note"]
    rows = frappe.get_all(ACTION, filters={"company": company}, fields=fields, limit_page_length=0)
    return [{key: (str(value) if isinstance(value, datetime.date) else value) for key, value in row.items()}
            for row in kpi.actions_for(rows, year, quarter)]


# ── The quarter's figures ─────────────────────────────────────────────
def quarter_figures(company, year, quarter):
    """The quarter's tables, its KPIs and ratings, the eight quarters to it,
    and what is missing from them: every figure a GROUP BY over the facts."""
    year = int(year)
    shown = rules.quarters_back(year, quarter, QUARTERS_SHOWN)
    first = datetime.date(*rules.quarter_months(*shown[0])[0], 1)
    last = datetime.date(*rules.quarter_months(year, quarter)[-1], 1)
    window = facts_rules.months_between(first, last)
    by_month = board_facts.month_figures(company, first, last)
    ready = board_facts.ready(company, window)

    def month(y, m):
        day = datetime.date(y, m, 1)
        return by_month.get(day, {}) if ready.get(day) else None

    months = [(y, m) for y, m in rules.quarter_months(year, quarter)]
    taken = [month(y, m) for y, m in months]
    missing = [rules.MONTH_NAMES[m - 1] + " " + str(y) for (y, m), found in zip(months, taken) if found is None]
    first_year, first_month = months[0]
    before = month(*((first_year - 1, 12) if first_month == 1 else (first_year, first_month - 1)))
    last_year = [month(y - 1, m) for y, m in months]
    last_year = last_year if all(found is not None for found in last_year) else []
    previous = [month(y, m) for y, m in rules.quarter_months(*rules.quarter_before(year, quarter))]
    previous = previous if all(found is not None for found in previous) else []
    target = _attrition_target(company, months)
    plants = rules.plants_of([found for found in taken if found])
    figures = rules.quarter([found or {} for found in taken], before, last_year, plants, target, previous)
    opens = rules.month_bounds(*months[0])[0]
    closes = rules.month_bounds(*months[-1])[1]
    # the eight quarters to this one, for the trends and the lights
    trend = []
    for y, q in shown:
        found = [month(yy, mm) for yy, mm in rules.quarter_months(y, q)]
        complete = all(item is not None for item in found)
        trend.append({"year": y, "quarter": q, "label": rules.short_label(y, q), "complete": complete,
                      "summary": rules.summary(found) if complete else dict.fromkeys(rules.SUMMARY_FIELDS),
                      "plants": {plant: rules.summary(found, plant) for plant in plants} if complete else {}})
    now_summary = dict(rules.summary([found or {} for found in taken]))
    before_summary = dict(trend[-2]["summary"]) if len(trend) > 1 else {}
    year_summary = dict(trend[-5]["summary"]) if len(trend) > 4 else {}
    hiring_now = _hiring(company, opens, closes)
    now_summary.update(hiring_now)
    before_summary.update(_hiring(company, *_bounds(*rules.quarter_before(year, quarter))))
    year_summary.update(_hiring(company, *_bounds(year - 1, quarter)))
    talent = _talent(company, plants)
    now_summary.update(talent["totals"])
    quality = board_facts.data_quality(company, opens, closes)
    now_summary["data_issues"] = sum(quality.values())
    now_summary["capa_overdue"] = _capa_overdue(company, closes)
    targets = _targets(company)
    by_plant = {plant: rules.summary([found or {} for found in taken], plant) for plant in plants}
    series = {}
    for year_shown in (year - 1, year):
        series[str(year_shown)] = [round(sum(flt(f.get("overtime_all")) for f in (month(year_shown, m) or {}).values()),
                                         2) for m in range(1, months[-1][1] + 1)]
    figures.update({
        "label": rules.label(year, quarter), "year": year, "quarter": quarter, "company": company,
        "missing": missing, "before_missing": before is None, "last_year_missing": not last_year,
        "previous_missing": not previous,
        "overtime_series": series,
        "overtime_months": [rules.MONTH_NAMES[m - 1][:3] for m in range(1, months[-1][1] + 1)],
        "regrettable": _regrettable(company, opens, closes),
        "training_held": _training_held(company, opens, closes),
        "training_value": _training_value(company, opens, closes),
        "hazards": _hazards(company, opens, closes),
        "talent": talent,
        "hiring": hiring_now,
        "data_quality": [dict(row) for row in facts_rules.data_quality(quality)[0]],
        "trends": trend, "summary": now_summary, "by_plant": by_plant,
        "kpis": kpi.board_kpis(now_summary, before_summary, year_summary, targets, opens, closes, plants, by_plant),
        "ratings": kpi.area_ratings(now_summary, before_summary, year_summary, targets, opens, closes,
                                    settings()["tolerance"]),
        "actions": _actions(company, year, quarter),
        "targets": [{key: (str(value) if isinstance(value, datetime.date) else value) for key, value in row.items()}
                    for row in targets],
        "taken_on": now(),
    })
    figures["insights"] = kpi.insights(figures)
    return figures


def _bounds(year, quarter):
    months = rules.quarter_months(year, quarter)
    return rules.month_bounds(*months[0])[0], rules.month_bounds(*months[-1])[1]


def _attrition_target(company, months):
    first, last = rules.month_bounds(*months[0])[0], rules.month_bounds(*months[-1])[1]
    found = kpi.target_for(_targets(company), "Monthly Attrition", None, first, last)
    return flt(found.get("target")) if found else None


def _hiring(company, first, last):
    """The quarter's hiring KPIs: of the hires whose 90th day fell in it,
    the share still there; and the days from requisition to joining."""
    first, last = getdate(first), getdate(last)
    joined_from = first - datetime.timedelta(days=90)
    hires = {row.employee: row.effective_date for row in frappe.get_all(
        "HR Movement", filters={"company": company, "movement_type": "Hire",
                                "effective_date": ["between", [joined_from, last]], "employee": ["is", "set"]},
        fields=["employee", "effective_date"], limit_page_length=0)}
    exits = {}
    if hires:
        exits = {row.employee: row.effective_date for row in frappe.get_all(
            "HR Movement", filters={"company": company, "movement_type": "Exit", "employee": ["in", list(hires)]},
            fields=["employee", "effective_date"], limit_page_length=0)}
    retention, cohort = kpi.retention_90(hires, exits, first, last)
    made = frappe.get_all("HR Movement", filters={"company": company, "movement_type": "Hire",
                                                  "effective_date": ["between", [first, last]],
                                                  "job_requisition": ["is", "set"]},
                          fields=["employee", "effective_date", "job_requisition", "job_applicant"],
                          limit_page_length=0)
    rows = []
    if made:
        requested = dict(frappe.get_all("Job Requisition", filters={"name": ["in", [r.job_requisition for r in made]]},
                                        fields=["name", "posting_date"], as_list=True))
        advertised = {}
        for row in frappe.get_all("Job Opening", filters={"job_requisition": ["in", [r.job_requisition for r in made]]},
                                  fields=["job_requisition", "posted_on", "creation"], limit_page_length=0):
            day = getdate(row.posted_on or row.creation)
            advertised[row.job_requisition] = min(day, advertised.get(row.job_requisition, day))
        offered = {}
        applicants = [r.job_applicant for r in made if r.job_applicant]
        if applicants:
            for row in frappe.get_all("Job Offer", filters={"job_applicant": ["in", applicants], "docstatus": 1},
                                      fields=["job_applicant", "offer_date"], limit_page_length=0):
                offered[row.job_applicant] = row.offer_date
        rows = [{"requested": requested.get(r.job_requisition), "advertised": advertised.get(r.job_requisition),
                 "offered": offered.get(r.job_applicant), "joined": r.effective_date} for r in made]
    fill = kpi.fill_days(rows)
    return {"retention_90": retention, "retention_cohort": cohort, "time_to_fill": fill.get("total"),
            "fill_to_advert": fill.get("to_advert"), "fill_to_offer": fill.get("to_offer"),
            "fill_to_join": fill.get("to_join"), "filled_hires": fill.get("hires")}


def _talent(company, plants):
    """Succession and talent risk by plant: the critical roles, how many are
    covered, the successors ready now, the top talent and those of them at
    high flight risk; the share of critical skills below the job's level."""
    keys = ("critical_roles", "covered_roles", "at_risk_roles", "gap_roles", "ready_now", "single_person_roles",
            "top_talent", "top_talent_at_risk", "high_potential")
    by_plant = {plant: dict.fromkeys(keys, 0) for plant in plants}
    totals = dict.fromkeys(keys, 0)

    def add(plant, field, count=1):
        mine = by_plant.setdefault(plant or rules.NO_PLANT, dict.fromkeys(keys, 0))
        mine[field] += count
        totals[field] += count

    try:
        meta = frappe.get_meta("Succession Position")
        fields = ["name", "branch", "designation", "department"] + [field for field in (
            "coverage", "ready_now", "single_person_role", "review_year", "status") if meta.has_field(field)]
        latest = {}
        for row in frappe.get_all("Succession Position", filters={"company": company, "docstatus": 1},
                                  fields=fields, limit_page_length=0):
            if row.get("status") == "Cancelled":
                continue
            key = (row.designation, row.department, row.branch)
            if key not in latest or cint(row.get("review_year")) >= cint(latest[key].get("review_year")):
                latest[key] = row
        for row in latest.values():
            add(row.branch, "critical_roles")
            add(row.branch, {"Covered": "covered_roles", "At Risk": "at_risk_roles"}.get(row.get("coverage"),
                                                                                          "gap_roles"))
            add(row.branch, "ready_now", cint(row.get("ready_now")))
            add(row.branch, "single_person_roles", cint(row.get("single_person_role")))
    except Exception:
        frappe.log_error(title="HRMS Addon: the board pack's succession figures")
    try:
        meta = frappe.get_meta("Talent Placement")
        fields = ["name", "employee", "branch", "modified"] + [field for field in (
            "top_talent", "flight_risk", "calibrated_potential", "potential_band") if meta.has_field(field)]
        latest = {}
        for row in frappe.get_all("Talent Placement", filters={"company": company, "docstatus": 1}, fields=fields,
                                  order_by="modified asc", limit_page_length=0):
            latest[row.employee] = row
        for row in latest.values():
            if cint(row.get("top_talent")):
                add(row.branch, "top_talent")
                if row.get("flight_risk") == "High":
                    add(row.branch, "top_talent_at_risk")
            if (row.get("calibrated_potential") or row.get("potential_band")) == "High":
                add(row.branch, "high_potential")
    except Exception:
        frappe.log_error(title="HRMS Addon: the board pack's talent figures")
    gaps, assessed = 0, 0
    try:
        latest = {}
        for row in frappe.get_all("Competency Assessment", filters={"company": company, "critical": 1},
                                  fields=["employee", "skill", "status", "modified"], order_by="modified asc",
                                  limit_page_length=0):
            latest[(row.employee, row.skill)] = row
        assessed = len(latest)
        gaps = sum(1 for row in latest.values() if row.status != "Competent")
    except Exception:
        frappe.log_error(title="HRMS Addon: the board pack's skills figures")
    totals.update({
        "succession_coverage": round(100.0 * totals["covered_roles"] / totals["critical_roles"], 1)
        if totals["critical_roles"] else None,
        "skills_gap": round(100.0 * gaps / assessed, 1) if assessed else None, "skills_assessed": assessed})
    return {"totals": totals, "plants": by_plant}


def _capa_overdue(company, day):
    if not frappe.get_meta("Safety Incident").has_field("capa_due"):
        return 0
    return frappe.db.count("Safety Incident", {"company": company, "docstatus": ["<", 2],
                                               "capa_status": ["!=", "Closed"],
                                               "capa_due": ["between", ["2000-01-01", day]]})


def _regrettable(company, first, last):
    """The quarter's regrettable losses: who, what, where and how long."""
    return [{"name": row.employee_name or row.employee, "designation": row.designation, "plant": row.branch,
             "years": row.tenure_years} for row in frappe.get_all(
        "HR Movement", filters={"company": company, "movement_type": "Exit", "regrettable": 1,
                                "effective_date": ["between", [first, last]]},
        fields=["employee", "employee_name", "designation", "branch", "tenure_years"], order_by="effective_date asc",
        limit_page_length=0)]


def _training_held(company, first, last):
    """The sessions held in the quarter, with how many attended: two queries."""
    events = frappe.get_all("Training Event", filters={"company": company, "docstatus": 1,
                                                       "event_status": ["!=", "Cancelled"],
                                                       "start_time": ["between", ["%s 00:00:00" % first,
                                                                                  "%s 23:59:59" % last]]},
                            fields=["name", "event_name", "training_program", "start_time"], order_by="start_time asc",
                            limit_page_length=0)
    present = {}
    if events:
        for row in frappe.get_all("Training Event Employee", filters={"parenttype": "Training Event",
                                                                      "parent": ["in", [e.name for e in events]],
                                                                      "attendance": "Present"},
                                  fields=["parent"], limit_page_length=0):
            present[row.parent] = present.get(row.parent, 0) + 1
    return [{"event": event.event_name or event.name, "programme": event.training_program,
             "day": str(getdate(event.start_time)), "attended": present.get(event.name, 0)} for event in events]


def _training_value(company, first, last):
    """Each programme of the quarter, its four levels and its value, as the
    learning module works them out (learning_value.value_by)."""
    try:
        from hrms_addon.hrms_addon import learning_value

        events = learning_value.sessions_in({"from_date": first, "to_date": last, "company": company})
        found = learning_value.value_by(events, lambda event: event.training_program or event.event_name)
    except Exception:
        frappe.log_error(title="HRMS Addon: the board pack's training value")
        return []
    rows = []
    for programme, value in found.items():
        rows.append({"programme": programme, "trainees": value.get("trainees"), "sessions": value.get("sessions"),
                     "participation": 1 if value.get("trainees") else 0,
                     "learning": 1 if value.get("pass_rate") is not None else 0,
                     "application": 1 if value.get("application") is not None else 0,
                     "result": 1 if value.get("kpis_improved") or flt(value.get("benefit")) else 0,
                     "pass_rate": value.get("pass_rate"), "applied_rate": value.get("applied_rate"),
                     "score": value.get("score"), "cost": value.get("total"), "roi": value.get("roi")})
    return sorted(rows, key=lambda row: (-(flt(row.get("score"))), str(row["programme"])))


def _hazards(company, first, last):
    """{plant: the hazard behind most incidents, "" for the company}: one GROUP BY."""
    out = {}
    for row in frappe.db.sql(
            """SELECT COALESCE(`branch`, '') AS plant, `hazard`, SUM(`incidents`) AS incidents
            FROM `tabHR Safety Fact`
            WHERE `company` = %(company)s AND `month` BETWEEN %(first)s AND %(last)s
                AND `severity` <> 'Near Miss' AND COALESCE(`hazard`, '') <> ''
            GROUP BY COALESCE(`branch`, ''), `hazard`
            ORDER BY SUM(`incidents`) DESC""",
            {"company": company, "first": facts_rules.month_start(first), "last": facts_rules.month_start(last)},
            as_dict=True):
        out.setdefault(facts_rules.plant(row.plant), row.hazard)
        out.setdefault("", row.hazard)
    return out


# ── The quarter's report ──────────────────────────────────────────────
def report_validate(doc):
    if not doc.get("title"):
        doc.title = _("HR Board Report {0}").format(rules.label(doc.year, doc.quarter))
    if doc.is_new():
        if not doc.get("ratings"):
            doc.set("ratings", [{"area": area} for area in kpi.AREAS])
        if not doc.get("metrics"):
            doc.set("metrics", [{"number": number, "metric": name, "measure": metric}
                                for number, name, metric in kpi.BOARD_KPIS])
    for row in list(doc.get("ratings") or []) + list(doc.get("metrics") or []):
        for message in kpi.override_errors(row):
            frappe.throw(_("{0}: {1}").format(row.get("area") or row.get("metric"), _(message)), title=_(REPORT))
    for row in doc.get("ratings") or []:
        kpi.settle(row, "computed_rating", "rating")
    for row in doc.get("metrics") or []:
        kpi.settle(row, "computed_status", "status")
    doc.status = {0: "Draft", 1: "Approved", 2: "Cancelled"}[cint(doc.docstatus)]


def report_before_submit(doc):
    """Approved, the figures are those of the facts now, and every month of
    the quarter must be in them."""
    figures = quarter_figures(doc.company, doc.year, doc.quarter)
    if figures["missing"]:
        frappe.throw(_("{0}: build these months first.").format(", ".join(figures["missing"])), title=_(REPORT))
    _take(doc, figures)


def report_on_submit(doc):
    doc.db_set("status", "Approved", update_modified=False)
    months = [datetime.date(y, m, 1) for y, m in rules.quarter_months(doc.year, doc.quarter)]
    board_facts.lock(doc.company, months, doc.name)
    _record_actions(doc)


def report_on_cancel(doc):
    doc.db_set("status", "Cancelled", update_modified=False)
    board_facts.unlock(doc.name)


def _record_actions(doc):
    """Each action the pack showed, as it stood when the board approved it:
    a row for the quarter on the action."""
    for row in _actions(doc.company, doc.year, doc.quarter):
        action = frappe.get_doc(ACTION, row["name"])
        update = next((line for line in action.get("updates") or []
                       if cint(line.year) == cint(doc.year) and line.quarter == doc.quarter), None)
        values = {"year": doc.year, "quarter": doc.quarter, "status": action.status, "progress": action.progress,
                  "note": action.progress_note, "updated_on": today()}
        if update:
            update.update(values)
        else:
            action.append("updates", values)
        action.flags.ignore_permissions = True
        action.save()


@frappe.whitelist(methods=["POST"])
def get_figures(name):
    """The quarter's figures taken into the report; the KPIs, the ratings and
    the drafted insights written where HR have written nothing yet."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("The report is approved: its figures stand."), title=_(REPORT))
    figures = quarter_figures(doc.company, doc.year, doc.quarter)
    _take(doc, figures)
    doc.save()
    return {"missing": figures["missing"], "last_year_missing": figures["last_year_missing"],
            "flags": len(doc.get("text_flags") or [])}


def _take(doc, figures):
    """The figures, KPIs, ratings and drafts put on the report."""
    doc.figures_json = json.dumps(figures, default=str)
    doc.built_on = now()
    for field, draft in (figures.get("insights") or {}).items():
        if doc.meta.has_field(field) and not (doc.get(field) or "").strip():
            doc.set(field, draft)
    if not (doc.get("regrettable_note") or "").strip() and figures["regrettable"]:
        doc.regrettable_note = "; ".join("%s (%s)" % (row["name"], ", ".join(
            str(value) for value in (row.get("designation"), row.get("plant"),
                                     ("%s yrs" % row["years"]) if row.get("years") else None) if value))
            for row in figures["regrettable"])
    ratings = {row.area: row for row in doc.get("ratings") or []}
    for found in figures["ratings"]:
        row = ratings.get(found["area"]) or doc.append("ratings", {"area": found["area"]})
        row.computed_rating = found["rating"]
        row.basis = found["basis"]
        if not (row.get("note") or "").strip():
            row.note = found["basis"].split("; ")[0]
        kpi.settle(row, "computed_rating", "rating")
    metrics = {row.number: row for row in doc.get("metrics") or []}
    for found in figures["kpis"]:
        row = metrics.get(found["number"]) or doc.append("metrics", {"number": found["number"]})
        row.metric, row.measure = found["name"], found["metric"]
        row.value, row.target, row.unit = found["value"], found["target"], found["unit"]
        row.computed_status = found["light"] or ""
        row.reading = found["reading"]
        if not (row.get("tells") or "").strip():
            row.tells = found["tells"]
        kpi.settle(row, "computed_status", "status")
    if not doc.get("training_value") and figures.get("training_value"):
        doc.set("training_value", [{"programme": row["programme"],
                                    "reach": "%s trainees, %s sessions" % (row.get("trainees") or 0,
                                                                          row.get("sessions") or 0),
                                    "participation": row["participation"], "learning": row["learning"],
                                    "application": row["application"], "result": row["result"],
                                    "evidence": _evidence(row), "score": round(flt(row.get("score")) / 20.0, 1)}
                                   for row in figures["training_value"]])
    typed = {field: doc.get(field) for field in TEXTS if (doc.get(field) or "").strip()
             and doc.get(field) != (figures.get("insights") or {}).get(field)}
    labels = {field: doc.meta.get_label(field) for field in TEXTS}
    doc.set("text_flags", [{"field_label": field, "issue": issue}
                           for field, issue in kpi.text_flags(typed, figures, labels)])


def _evidence(row):
    parts = []
    if row.get("pass_rate") is not None:
        parts.append(_("Passed {0}%").format(row["pass_rate"]))
    if row.get("applied_rate") is not None:
        parts.append(_("Applied {0}%").format(row["applied_rate"]))
    if row.get("roi") is not None:
        parts.append(_("ROI {0}%").format(row["roi"]))
    return ", ".join(parts)


def figures_of(doc):
    try:
        return json.loads(doc.get("figures_json") or "{}")
    except ValueError:
        return {}


@frappe.whitelist()
def download_deck(name):
    """The board pack as a PowerPoint deck."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("read")
    from hrms_addon.hrms_addon import board_deck

    content = board_deck.deck(doc, figures_of(doc), logo=_logo(doc.company))
    frappe.local.response.filename = "%s.pptx" % (doc.title or doc.name)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"


@frappe.whitelist()
def download_workbook(name):
    """The board pack's tables as an Excel workbook."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("read")
    from hrms_addon.hrms_addon import board_deck

    content = board_deck.workbook(doc, figures_of(doc))
    frappe.local.response.filename = "%s.xlsx" % (doc.title or doc.name)
    frappe.local.response.filecontent = content
    frappe.local.response.type = "binary"


def _logo(company):
    """The company's logo file on disk, for the deck's corner; None where
    there is none, and the deck keeps the place."""
    try:
        url = frappe.get_cached_value("Company", company, "company_logo")
        if not url:
            return None
        name = frappe.db.get_value("File", {"file_url": url}, "name")
        path = frappe.get_doc("File", name).get_full_path() if name else None
        return path if path and os.path.exists(path) else None
    except Exception:
        return None


@frappe.whitelist()
def report_actions(name):
    """The actions the report's quarter shows, for its form."""
    doc = frappe.get_doc(REPORT, name)
    doc.check_permission("read")
    return _actions(doc.company, doc.year, doc.quarter)
