# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Shift Scorecard (the workbook's Production Dashboard and Labour Cost
sheets): the shift reports of a period by section, supervisor, week, day or
shift. Their average score, the weakest factor, output against target,
uptime and the main downtime reason, attendance, PPE, safety, the money
lost to waste and complaints, and labour cost against its budget. The first
row is the whole selection.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules

GROUPS = {"Section": "work_section", "Supervisor": "supervisor", "Week": "week", "Day": "report_date",
          "Shift": "shift"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    s = excellence.settings()
    rows = excellence.shift_rows(start, end, filters.get("company"), filters.get("branch"),
                                 filters.get("work_section"), filters.get("shift"))
    by = filters.get("group_by") or "Section"
    groups = {}
    for row in rows:
        row.week = rules.week_label(row.report_date)
        groups.setdefault(key_of(row, by), []).append(row)
    data = [line(_("All"), rows, s, by, bold=1)] if rows else []
    for key in sorted(groups, key=lambda value: str(value)):
        data.append(line(key, groups[key], s, by))
    return columns(by), data, None, chart(data[1:]), summary(rows, s)


def key_of(row, by):
    if by == "Supervisor":
        return row.supervisor_name or row.supervisor or _("No Supervisor")
    return row.get(GROUPS[by]) or ""


def line(key, rows, s, by, bold=0):
    t = rules.totals(rows, s)
    a = rules.averages(t)
    one_unit = len(t["by_unit"]) == 1
    unit = next(iter(t["by_unit"])) if one_unit else ""
    pct = lambda value: round(value * 100, 1) if value is not None else None  # noqa: E731
    return {
        "group": key, "bold": bold, "shifts": t["count"], "score": a["score"], "status": rules.rag(a["score"], s),
        "weakest": rules.FACTOR_LABELS.get(a["weakest"], ""), "achievement": pct(a["achievement"]),
        "output": t["actual"] if one_unit else None, "unit": unit, "uptime": pct(a["uptime"]),
        "hours_lost": t["hours_lost"], "top_downtime": a["top_downtime"] or "",
        "attendance": pct(a["attendance"]), "ppe": pct(a["ppe"]), "incidents": t["incidents"],
        "near_misses": t["near_misses"], "waste": t["waste"], "complaints": t["complaints"],
        "money_lost": a["money_lost"], "labour": t["labour"], "ot_cost": t["ot_cost"], "ot_share": pct(a["ot_share"]),
        "labour_per_unit": (t["labour"] / t["actual"]) if one_unit and t["actual"] else None,
        "budget_variance": pct(a["budget_variance"]), "absence_cost": t["absence_cost"],
    }


def columns(by):
    group = {"fieldname": "group", "label": _(by), "fieldtype": "Data", "width": 200}
    if by == "Section":
        group.update({"fieldtype": "Link", "options": "Work Section"})
    elif by == "Day":
        group.update({"fieldtype": "Date", "width": 110})
    return [
        group,
        {"fieldname": "shifts", "label": _("Shifts"), "fieldtype": "Int", "width": 70},
        {"fieldname": "score", "label": _("Score"), "fieldtype": "Float", "precision": 1, "width": 80},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "weakest", "label": _("Weakest Area"), "fieldtype": "Data", "width": 130},
        {"fieldname": "achievement", "label": _("Achievement %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "output", "label": _("Output"), "fieldtype": "Float", "precision": 0, "width": 100},
        {"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 60},
        {"fieldname": "uptime", "label": _("Uptime %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "hours_lost", "label": _("Machine Hours Lost"), "fieldtype": "Float", "precision": 1,
         "width": 110},
        {"fieldname": "top_downtime", "label": _("Main Downtime Reason"), "fieldtype": "Data", "width": 150},
        {"fieldname": "attendance", "label": _("Attendance %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "ppe", "label": _("PPE %"), "fieldtype": "Percent", "width": 80},
        {"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 80},
        {"fieldname": "near_misses", "label": _("Near Misses"), "fieldtype": "Int", "width": 90},
        {"fieldname": "waste", "label": _("Waste"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "complaints", "label": _("Complaints"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "money_lost", "label": _("Money Lost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "labour", "label": _("Labour Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_cost", "label": _("Overtime Cost"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "ot_share", "label": _("Overtime %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "labour_per_unit", "label": _("Labour Cost per Unit"), "fieldtype": "Currency",
         "width": 120},
        {"fieldname": "budget_variance", "label": _("Against Budget %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "absence_cost", "label": _("Paid Absence Cost"), "fieldtype": "Currency", "width": 120},
    ]


def chart(data):
    have = [row for row in data if row["score"] is not None][:30]
    if not have:
        return None
    return {"data": {"labels": [str(row["group"]) for row in have],
                     "datasets": [{"name": _("Score"), "values": [row["score"] for row in have]}]},
            "type": "bar", "colors": ["#1F3864"], "barOptions": {"spaceRatio": 0.4}}


def summary(rows, s):
    t = rules.totals(rows, s)
    a = rules.averages(t)
    return [
        {"value": a["score"], "label": _("Average Score"), "datatype": "Float",
         "indicator": {"On Target": "Green", "Attention": "Orange"}.get(rules.rag(a["score"], s), "Red")},
        {"value": a["money_lost"], "label": _("Money Lost"), "datatype": "Currency"},
        {"value": t["hours_lost"], "label": _("Machine Hours Lost"), "datatype": "Float"},
        {"value": t["labour"], "label": _("Labour Cost"), "datatype": "Currency"},
        {"value": t["incidents"], "label": _("Safety Incidents"), "datatype": "Int",
         "indicator": "Red" if t["incidents"] else "Green"},
    ]
