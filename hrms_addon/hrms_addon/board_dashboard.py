# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Board Dashboard (page/board_dashboard): the quarter's KPIs with eight
quarters behind each, the plants' scorecard in traffic lights, and what keeps
the figures from adding up; every figure opens the report listing its
records. One call, cached for five minutes per user and choice: a GROUP BY
over the facts for the eight quarters (board_facts.month_figures), each
quarter worked out by board_pack_rules.summary and lit by board_kpi_rules.

Who sees it: HR, the General Manager, the Executive Director, the board and
the management view. Money (the wage bill, staff cost, revenue) only for
those who may see pay; a user held to plants (User Permission on Branch) sees
only theirs.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import board_facts, board_facts_rules as facts_rules, board_kpi_rules as kpi
from hrms_addon.hrms_addon import board_pack_rules as rules

ROLES = ("HR Manager", "HR User", "General Manager", "Executive Director", "Board Member", "Management Viewer",
         "System Manager")
MONEY_ROLES = ("HR Manager", "Payroll Officer", "General Manager", "Executive Director", "Board Member",
               "Management Viewer", "System Manager")
CACHE_SECONDS = 300
# the report each figure opens
DRILL = {
    "Head Count": "Board Head Count", "Monthly Attrition": "Board Leavers", "Casual Churn": "Board Leavers",
    "Regrettable Exits": "Board Leavers", "Staff Cost to Revenue": "Board Pay by Component",
    "Revenue per Employee": "Board Pay by Component", "Labour Cost per kg": "Board Pay by Component",
    "Overtime Share of Wage Bill": "Board Pay by Component", "LTIFR": "Board Incidents",
    "Training Hours per Employee": "Board Head Count", "Clock Attendance": "Board Head Count",
    "Succession Coverage": "Succession Coverage", "Absence Rate": "Board Head Count",
}
QUALITY_REPORT = "Board Data Quality"


def _reach():
    roles = set(frappe.get_roles())
    if not roles & set(ROLES):
        frappe.throw(_("The Board Dashboard is for HR, management and the board."), frappe.PermissionError)
    return {"money": bool(roles & set(MONEY_ROLES))}


def _held_plants():
    """The plants the user is held to, or None when they are held to none."""
    held = frappe.get_all("User Permission", filters={"user": frappe.session.user, "allow": "Branch"},
                          pluck="for_value")
    return set(held) if held else None


def _permitted(report):
    try:
        return frappe.get_cached_doc("Report", report).is_permitted()
    except Exception:
        return False


@frappe.whitelist()
def overview(company=None, year=None, quarter=None, branch=None):
    """The dashboard's figures, for the quarter and plant chosen."""
    reach = _reach()
    company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
    this_year, this_quarter = rules.quarter_of(today())
    year, quarter = int(year or this_year), quarter if quarter in rules.QUARTERS else this_quarter
    held = _held_plants()
    if branch and held is not None and branch not in held:
        frappe.throw(_("You are not permitted to see {0}.").format(branch), frappe.PermissionError)
    key = "hrms_addon:board_dashboard:%s:%s:%s:%s:%s" % (company, year, quarter, branch or "",
                                                         ",".join(sorted(held)) if held is not None else "*")
    user = frappe.session.user
    found = frappe.cache.get_value(key, user=user)
    if found:
        return found
    found = figures(company, year, quarter, branch, held, reach["money"])
    frappe.cache.set_value(key, found, user=user, expires_in_sec=CACHE_SECONDS)
    return found


def figures(company, year, quarter, branch=None, held=None, money=True):
    shown = rules.quarters_back(year, quarter, 8)
    first = datetime.date(*rules.quarter_months(*shown[0])[0], 1)
    last = datetime.date(*rules.quarter_months(year, quarter)[-1], 1)
    window = facts_rules.months_between(first, last)
    by_month = board_facts.month_figures(company, first, last)
    ready = board_facts.ready(company, window)
    if held is not None:
        by_month = {month: {plant: values for plant, values in found.items() if plant in held}
                    for month, found in by_month.items()}

    def months_of(y, q):
        found = [by_month.get(datetime.date(y, m, 1), {}) if ready.get(datetime.date(y, m, 1)) else None
                 for y, m in rules.quarter_months(y, q)]
        return found if all(item is not None for item in found) else None

    quarters = [(y, q, months_of(y, q)) for y, q in shown]
    plants = rules.plants_of([month for _y, _q, months in quarters if months for month in months])
    scope = branch or None
    summaries = [rules.summary(months, scope) if months else None for _y, _q, months in quarters]
    opens, closes = rules.month_bounds(*rules.quarter_months(year, quarter)[0])[0], rules.quarter_end(year, quarter)
    now = dict(summaries[-1] or {})
    from hrms_addon.hrms_addon import board_pack

    talent = board_pack._talent(company, plants)
    if branch:
        mine = talent["plants"].get(branch) or {}
        now["succession_coverage"] = round(100.0 * mine["covered_roles"] / mine["critical_roles"], 1)             if mine.get("critical_roles") else None
    else:
        now.update(talent["totals"])
    targets = board_pack._targets(company)
    cards = []
    for metric in kpi.CARDS:
        if not money and metric in kpi.MONEY_METRICS:
            continue
        field, unit, direction, _kind = kpi.definition(metric)
        series = [(summary or {}).get(field) for summary in summaries]
        value = now.get(field)
        target = kpi.target_for(targets, metric, branch, opens, closes) if direction else None
        before = series[-2] if len(series) > 1 else None
        year_ago = series[-5] if len(series) > 4 else None
        light = kpi.light(value, target) if target else kpi.trend_light(
            value, year_ago if year_ago is not None else before, direction)
        report = DRILL.get(metric)
        cards.append({"metric": metric, "value": value, "display": kpi.show(metric, value), "unit": unit,
                      "direction": direction, "light": light, "target": target.get("target") if target else None,
                      "previous": before, "last_year": year_ago, "change": kpi.change(value, before),
                      "series": series, "route": _route(report, company, opens, closes, branch)})
    metrics = [metric for metric in kpi.SCORECARD if money or metric not in kpi.MONEY_METRICS]
    company_now = rules.summary(quarters[-1][2], None) if quarters[-1][2] else {}
    rows = []
    for plant in [plant for plant in plants if not branch or plant == branch]:
        summary = rules.summary(quarters[-1][2], plant) if quarters[-1][2] else {}
        cells = []
        for metric in metrics:
            field, _unit, direction, _kind = kpi.definition(metric)
            value = (summary or {}).get(field)
            target = kpi.target_for(targets, metric, plant, opens, closes)
            light = kpi.light(value, target) if target else kpi.trend_light(value, (company_now or {}).get(field),
                                                                            direction)
            cells.append({"metric": metric, "value": value, "display": kpi.show(metric, value), "light": light,
                          "route": _route(DRILL.get(metric), company, opens, closes, plant)})
        rows.append({"plant": plant, "cells": cells})
    counts = board_facts.data_quality(company, opens, closes)
    quality, issues = facts_rules.data_quality(counts)
    for row in quality:
        row["route"] = _route(QUALITY_REPORT, company, opens, closes, None, check=row["key"])
    return {"company": company, "year": year, "quarter": quarter, "label": rules.label(year, quarter),
            "branch": branch or "", "plants": plants, "money": money,
            "quarters": [rules.short_label(y, q) for y, q, _months in quarters],
            "complete": [months is not None for _y, _q, months in quarters],
            "missing": [rules.MONTH_NAMES[m - 1] + " " + str(y) for y, m in rules.quarter_months(year, quarter)
                        if not ready.get(datetime.date(y, m, 1))],
            "cards": cards, "scorecard": {"metrics": metrics, "rows": rows}, "quality": quality, "issues": issues,
            "today": today()}


def _route(report, company, opens, closes, branch=None, **extra):
    if not report or not _permitted(report):
        return None
    filters = {"company": company, "from_date": str(getdate(opens)), "to_date": str(getdate(closes))}
    if branch:
        filters["branch"] = branch
    filters.update({key: value for key, value in extra.items() if value})
    return ["query-report", report, filters]
