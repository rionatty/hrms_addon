# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Manufacturing Excellence page (page/manufacturing_excellence): one call
for everything on it, read from the stored summaries and kept for five
minutes for each user and choice of plant and period.

  the HR Excellence sheet's twelve tiles and the Dashboard's eleven, each
  against its target; the one-line verdict; the three plants side by side;
  the sections against the fourteen indicators with the signals that occur
  together and the intervention to look at; the red flags; thirteen weeks and
  twelve months; the money lost and the downtime by reason; Day against
  Night; the labour cost flags; and the lowest five of each, each opening the
  record behind it

What a user may read decides what they see: the summaries through their
permissions (a plant-restricted user sees their plant), the cases only for
those who may read them.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import excellence_rules as rules, excellence_summary as summary

PAGE_ROLES = ("System Manager", "HR Manager", "HR User", rules.ME_OFFICER, "Production Manager", "General Manager",
              "Executive Director", "Auditor")
CACHE_SECONDS = 300
TOP = 5
DAY = summary.DAY


@frappe.whitelist()
def data(company=None, branch=None, period_type=None, year=None, value=None, refresh=0):
    if not set(frappe.get_roles()) & set(PAGE_ROLES):
        frappe.throw(_("The Manufacturing Excellence page is for HR, production and management."),
                     frappe.PermissionError)
    period_type = period_type if period_type in rules.PERIOD_TYPES else rules.WEEK
    if not year or not value:
        year, value = default_period(period_type, today())
    key = "hrms_addon:me_page:%s" % "|".join(str(part or "") for part in (company, branch, period_type, year, value))
    if not cint(refresh):
        kept = frappe.cache.get_value(key, user=frappe.session.user)
        if kept:
            return kept
    found = build(company, branch, period_type, year, value)
    frappe.cache.set_value(key, found, user=frappe.session.user, expires_in_sec=CACHE_SECONDS)
    return found


def default_period(period_type, day):
    """Last whole week; this month; this quarter."""
    from frappe.utils import add_days

    if period_type == rules.WEEK:
        return rules.week_of(add_days(rules.week_start(day), -7))
    return rules.period_now(period_type, day)


def build(company, branch, period_type, year, value):
    start, end = rules.period_bounds(period_type, int(year), value if period_type != rules.WEEK else int(value))
    label = rules.week_label(start) if period_type == rules.WEEK else (
        "%s %s" % (value, year) if period_type == rules.MONTH else "%s %s" % (value, year))
    facts, s = summary.period_facts(start, end, company, branch)
    card = rules.pillars(facts, s)
    filters = summary.scope_filters(start, end, company, branch)
    by_section = summary.section_totals(filters)
    scored = rules.section_scores(by_section, s)
    heat, _s = summary.section_rows(start, end, company, branch, week=label if period_type == rules.WEEK else None)
    can_cases = bool(frappe.has_permission(summary.CASE, "read"))
    return {
        "period": {"type": period_type, "year": int(year), "value": value, "label": label, "start": str(start),
                   "end": str(end)},
        "plants": _plants(company),
        "branch": branch, "company": company,
        "production": rules.production_tiles(facts["totals"], scored, s),
        "hr": _hide_cases(rules.hr_tiles(card, facts, s), can_cases),
        "verdict": rules.verdict(scored),
        "status": card["status"], "composite": card["composite"],
        "pillars": card["pillars"],
        "comparison": _comparison(start, end, company, s),
        "heat": [_heat_row(row) for row in heat],
        "heat_columns": [list(column) for column in rules.HEAT_COLUMNS],
        "red_flags": _red_flags(card, start, end, company, branch, can_cases, s),
        "weeks": [dict(row, start=str(row["start"])) for row in summary.week_trend(today(), company, branch)],
        "months": summary.month_trend(today(), company, branch),
        "money": [{"section": row["section"], "label": rules.section_label(row["section"]),
                   "waste": row["totals"]["waste_value"], "complaints": row["totals"]["complaint_value"]}
                  for row in sorted(scored, key=lambda row: -row["totals"]["money_lost"])],
        "downtime": rules.downtime_breakdown(summary.downtime(start, end, company, branch)),
        "shifts": _day_and_night(filters, s),
        "labour": _labour(start, end, company, branch, period_type),
        "top": _top(scored, start, end, company, branch, can_cases, s),
        "can_cases": can_cases,
        "settings": {"green_from": s["green_from"], "amber_from": s["amber_from"]},
    }


def _hide_cases(tiles, can_cases):
    if can_cases:
        return tiles
    for tile in tiles:
        if tile["key"] == "er_flags":
            tile.update(value=None, light=rules.GREY, note=_("For HR"))
    return tiles


def _plants(company):
    filters = {"is_active": 1}
    if company:
        filters["company"] = company
    return sorted(set(frappe.get_list(summary.SECTION, filters=filters, pluck="branch", limit_page_length=0))
                  - {None, ""})


def _comparison(start, end, company, s):
    """Each plant the user may read: its score (its sections' average), money
    lost, attendance, PPE, overtime and incidents."""
    filters = summary.scope_filters(start, end, company)
    plants = {}
    for (branch, section, _unit), totals in summary.grouped(filters, ("branch", "work_section", "unit")).items():
        plants.setdefault(branch, {})[section] = totals
    found = []
    for branch, sections in sorted(plants.items()):
        scored = rules.section_scores(sections, s)
        t = rules.add_totals(*sections.values())
        a = rules.averages(t, s)
        score = rules.plant_score([row["score"] for row in scored])
        found.append({"branch": branch, "score": score, "status": rules.rag(score, s),
                      "money_lost": t["money_lost"], "attendance": a["attendance"], "ppe": a["ppe"],
                      "ot_share": a["ot_share"], "incidents": t["safety_incidents"], "hours_lost": t["hours_lost"],
                      "labour": t["labour_cost"], "verdict": rules.verdict(scored)})
    return found


def _heat_row(row):
    found = {key: row.get(key) for key, _label in rules.HEAT_COLUMNS}
    found.update(section=row["section"], label=rules.section_label(row["section"]), branch=row["branch"],
                 signals=row["signals"], keys=row["keys"], count=row["count"], alert=row["alert"],
                 intervention=row["intervention"], week_record=row["week_record"], score=row["score"],
                 pillar=rules.INTERVENTION_PILLARS.get(row["intervention"], ""),
                 kpi=rules.SIGNAL_KPIS.get(row["intervention"], ""))
    return found


def _red_flags(card, start, end, company, branch, can_cases, s):
    flags = [{"text": flag, "route": None} for flag in card["red_flags"]]
    filters = summary.scope_filters(start, end, company, branch)
    filters["safety_incidents"] = [">", 0]
    for row in frappe.get_list(DAY, filters=filters, fields=["shift_report", "work_section", "summary_date", "shift",
                                                             "safety_incidents"],
                               order_by="summary_date desc", limit_page_length=10):
        flags.append({"text": _("{0} incident(s): {1} {2} {3}").format(
            cint(row.safety_incidents), rules.section_label(row.work_section), row.summary_date, row.shift),
            "route": ["Form", "Shift Report", row.shift_report]})
    if can_cases:
        case_filters = {"docstatus": 0, "legal_flags": ["is", "set"]}
        for field, value in (("company", company), ("branch", branch)):
            if value:
                case_filters[field] = value
        for row in frappe.get_list(summary.CASE, filters=case_filters, fields=["name", "employee_name", "legal_flags"],
                                   order_by="aware_on asc", limit_page_length=10):
            flags.append({"text": "%s: %s" % (row.employee_name or row.name, (row.legal_flags or "").splitlines()[0]),
                          "route": ["Form", summary.CASE, row.name]})
    return flags


def _day_and_night(filters, s):
    by_shift = {}
    for (shift, _unit), totals in summary.grouped(filters, ("shift", "unit")).items():
        by_shift.setdefault(shift, []).append(totals)
    found = []
    for shift in rules.SHIFTS:
        t = rules.add_totals(*by_shift.get(shift, []))
        a = rules.averages(t, s)
        found.append({"shift": shift, "score": a["score"], "status": a["status"], "person_shifts": t["staff_on_shift"],
                      "labour": t["labour_cost"], "ot_cost": t["ot_cost"], "ot_share": a["ot_share"],
                      "attendance": a["attendance"], "unauthorised": t["unauthorised_absent"], "ppe": a["ppe"],
                      "kg_per_person": rules._per(t, "Kg", "actual", "on_shift"), "money_lost": t["money_lost"],
                      "incidents": t["safety_incidents"]})
    return found


def _labour(start, end, company, branch, period_type):
    found = []
    for section, row in sorted(summary.labour_view(start, end, company, branch).items()):
        t = row["now"]
        found.append({"section": section, "label": rules.section_label(section), "labour": t["labour_cost"],
                      "ot_cost": t["ot_cost"], "ot_share": rules.ratio(t["ot_cost"], t["labour_cost"]),
                      "flags": [flag for flag, _intervention in row["flags"]],
                      "intervention": row["flags"][0][1] if row["flags"] else ""})
    return found


def _top(scored, start, end, company, branch, can_cases, s):
    sections = [{"label": rules.section_label(row["section"]), "value": row["score"], "note": row["weakest_label"],
                 "route": ["Form", "Work Section", row["section"]]} for row in scored[:TOP]]
    supervisors, _s = summary.supervisor_rows(start, end, company, branch)
    lowest = sorted((row for row in supervisors if row["score"] is not None), key=lambda row: row["score"])[:TOP]
    people = [{"label": row["supervisor_name"] or row["supervisor"], "value": row["score"],
               "note": "%s, %s" % (row["sections"], row["weakest"]), "route": ["Form", "Employee", row["supervisor"]]}
              for row in lowest]
    filters = summary.scope_filters(start, end, company, branch)
    shifts = frappe.get_list(DAY, filters=filters, fields=["shift_report", "work_section", "summary_date", "shift",
                                                           "waste_value", "complaint_value"],
                             order_by="waste_value desc", limit_page_length=TOP * 4)
    shifts = sorted(shifts, key=lambda row: -(flt(row.waste_value) + flt(row.complaint_value)))[:TOP]
    costly = [{"label": "%s %s %s" % (rules.section_label(row.work_section), row.summary_date, row.shift),
               "value": flt(row.waste_value) + flt(row.complaint_value), "note": _("Waste and complaints"),
               "route": ["Form", "Shift Report", row.shift_report]} for row in shifts]
    overdue_filters = {"overdue": 1, "status": ["not in", list(rules.DONE)]}
    for field, value in (("company", company), ("branch", branch)):
        if value:
            overdue_filters[field] = value
    overdue = [{"label": row.observation, "value": row.target_date, "note": row.intervention,
                "route": ["Form", "HR Intervention", row.name]}
               for row in frappe.get_list("HR Intervention", filters=overdue_filters,
                                          fields=["name", "observation", "target_date", "intervention"],
                                          order_by="target_date asc", limit_page_length=TOP)]
    cases = []
    if can_cases:
        case_filters = {"docstatus": 0, "status": ["not in", list(rules.CASE_CLOSED)]}
        for field, value in (("company", company), ("branch", branch)):
            if value:
                case_filters[field] = value
        rows = frappe.get_list(summary.CASE, filters=case_filters,
                               fields=["name", "employee_name", "legal_flags", "status", "aware_on", "incident_date",
                                       "decided_on"],
                               order_by="aware_on asc", limit_page_length=TOP * 4)
        for row in rows:
            flag = rules.tracker_flag(row, 0, today(), s)
            if flag:
                cases.append({"label": row.employee_name or row.name, "value": flag, "note": row.status,
                              "route": ["Form", summary.CASE, row.name]})
        cases = cases[:TOP]
    return {"sections": sections, "supervisors": people, "shifts": costly, "interventions": overdue, "cases": cases}
