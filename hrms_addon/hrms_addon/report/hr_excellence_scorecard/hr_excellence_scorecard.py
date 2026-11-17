# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""HR Excellence Scorecard (the plant's HR Manufacturing Excellence workbook,
its HR Excellence sheet): eight pillars weighed into one score for a week,
month or quarter, a plant, a section and a shift, each with the figures
behind it. A pillar with no data is left out and the others re-weighted; a
safety incident, a legal flag or a grievance open too long marks the period
critical whatever the score (excellence_rules.pillars).
"""

import frappe
from frappe import _
from frappe.utils import fmt_money, getdate, today

from hrms_addon.hrms_addon import excellence, excellence_rules as rules

PERCENT = {
    "Deployment (on shift over crew)", "Direct Labour Share", "Labour Cost against Budget",
    "Overtime Share of Labour Cost", "Attendance", "Unauthorised Absence", "Shift Reports Entered",
    "Required Training Done", "Actions Closed on Time", "PPE Compliance", "Housekeeping",
    "Cases Routed to Coaching or a Process Fix", "Turnover", "Engagement Pulse (Last 3 Months)",
}
MONEY = {"Labour Cost per Kg", "Total Labour Cost", "Overtime Cost", "Paid Absence Cost",
         "Estimated Savings, Verified"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = period(filters)
    facts, s = excellence.period_facts(start, end, filters.get("company"), filters.get("branch"),
                                       filters.get("work_section"), filters.get("shift"))
    card = rules.pillars(facts, s)
    return columns(), rows(card), message(card, start, end), chart(card), summary(card, facts)


def period(filters):
    kind = filters.get("period_type") or rules.MONTH
    day = getdate(today())
    year = int(filters.get("year") or day.year)
    if kind == rules.WEEK:
        value = int(filters.get("week") or rules.week_of(day)[1])
    elif kind == rules.QUARTER:
        value = filters.get("quarter") or rules.QUARTERS[(day.month - 1) // 3]
    else:
        value = filters.get("month") or rules.MONTHS[day.month - 1]
    return rules.period_bounds(kind, year, value)


def columns():
    return [
        {"fieldname": "measure", "label": _("Measure"), "fieldtype": "Data", "width": 330},
        {"fieldname": "weight", "label": _("Weight"), "fieldtype": "Data", "width": 80},
        {"fieldname": "score", "label": _("Score"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "value", "label": _("Value"), "fieldtype": "Data", "width": 140},
        {"fieldname": "target", "label": _("Target"), "fieldtype": "Data", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
    ]


def shown(label, value):
    if value is None:
        return _("No Data")
    if isinstance(value, str):
        return value
    if label in PERCENT:
        return "{0}%".format(round(value * 100, 1))
    if label in MONEY:
        return fmt_money(value, precision=0)
    return "{0:,}".format(int(value)) if float(value).is_integer() else "{0:,.2f}".format(value)


def rows(card):
    data = [{"id": "score", "parent_id": None, "indent": 0, "measure": _("HR Excellence Score"),
             "weight": "100", "score": card["composite"], "status": _(card["status"]), "bold": 1,
             "value": _("{0}% of the weight has data").format(round(card["share"] * 100))}]
    for pillar in card["pillars"]:
        key = pillar["key"]
        data.append({"id": key, "parent_id": None, "indent": 0, "measure": _(pillar["label"]),
                     "weight": rules._plain(pillar["weight"]), "score": pillar["score"],
                     "status": _(pillar["status"]), "bold": 1})
        for label, value, target, status in card["kpis"][key]:
            data.append({"id": key + ":" + label, "parent_id": key, "indent": 1, "measure": _(label),
                         "value": shown(label, value),
                         "target": shown(label, target) if target is not None else "",
                         "status": _(status) if status else ""})
    return data


def message(card, start, end):
    when = "{0} to {1}".format(frappe.format_value(start, {"fieldtype": "Date"}),
                               frappe.format_value(end, {"fieldtype": "Date"}))
    if card["red_flags"]:
        return "{0}. {1}: {2}".format(when, _("Red flags"), "; ".join(card["red_flags"]))
    return when


def chart(card):
    have = [pillar for pillar in card["pillars"] if pillar["score"] is not None]
    if not have:
        return None
    return {"data": {"labels": [_(pillar["label"]) for pillar in have],
                     "datasets": [{"name": _("Score"), "values": [pillar["score"] for pillar in have]}]},
            "type": "bar", "colors": ["#1F3864"], "barOptions": {"spaceRatio": 0.4}}


def summary(card, facts):
    t = facts["totals"]
    a = rules.averages(t)
    light = {"On Target": "Green", "Attention": "Orange"}.get(card["status"], "Red")
    return [
        {"value": card["composite"], "label": _("HR Excellence Score"), "datatype": "Float", "indicator": light},
        {"value": round(a["attendance"] * 100, 1) if a["attendance"] is not None else None,
         "label": _("Attendance %"), "datatype": "Float"},
        {"value": round(a["ot_share"] * 100, 1) if a["ot_share"] is not None else None,
         "label": _("Overtime % of Labour"), "datatype": "Float"},
        {"value": round(a["ppe"] * 100, 1) if a["ppe"] is not None else None, "label": _("PPE %"),
         "datatype": "Float"},
        {"value": facts.get("legal_flags") or 0, "label": _("Legal Flags Open"), "datatype": "Int",
         "indicator": "Red" if facts.get("legal_flags") else "Green"},
        {"value": t["count"], "label": _("Shift Reports"), "datatype": "Int"},
    ]
