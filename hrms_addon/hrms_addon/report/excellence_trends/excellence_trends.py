# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Excellence Trends (the workbook's Trends sheet), from the stored summaries.

  13 Weeks    the plant score (its sections' average), waste, complaints,
              PPE, attendance and safety incidents, week by week
  12 Months   attendance, unauthorised absence, overtime hours and share of
              labour, labour cost and its cost per kg, cases, grievances,
              exits and recognitions, month by month
"""

import frappe
from frappe import _
from frappe.utils import today

from hrms_addon.hrms_addon import excellence_summary as summary

VIEWS = ("13 Weeks", "12 Months")


def _pct(value):
    return round(value * 100, 1) if value is not None else None


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if (filters.get("view") or VIEWS[0]) == VIEWS[1]:
        return months(filters)
    return weeks(filters)


def weeks(filters):
    rows = summary.week_trend(today(), filters.get("company"), filters.get("branch"))
    data = [{"period": row["week"], "score": row["score"], "waste": row["waste"], "complaints": row["complaints"],
             "ppe": _pct(row["ppe"]), "attendance": _pct(row["attendance"]), "incidents": row["incidents"],
             "money_lost": row["money_lost"]} for row in rows]
    columns = [
        {"fieldname": "period", "label": _("Week"), "fieldtype": "Data", "width": 100},
        {"fieldname": "score", "label": _("Plant Score"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "waste", "label": _("Waste"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "complaints", "label": _("Complaints"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "money_lost", "label": _("Money Lost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ppe", "label": _("PPE %"), "fieldtype": "Percent", "width": 80},
        {"fieldname": "attendance", "label": _("Attendance %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "incidents", "label": _("Safety Incidents"), "fieldtype": "Int", "width": 110},
    ]
    chart = {"data": {"labels": [row["period"] for row in data],
                      "datasets": [{"name": _("Plant Score"), "values": [row["score"] or 0 for row in data]},
                                   {"name": _("Attendance %"), "values": [row["attendance"] or 0 for row in data]},
                                   {"name": _("PPE %"), "values": [row["ppe"] or 0 for row in data]}]},
             "type": "line", "colors": ["#1F3864", "#C9A227", "#5E8C61"],
             "lineOptions": {"regionFill": 0, "dotSize": 4}}
    scored = [row["score"] for row in data if row["score"] is not None]
    report_summary = [
        {"value": round(sum(scored) / len(scored), 1) if scored else None, "label": _("Average Plant Score"),
         "datatype": "Float"},
        {"value": sum(row["money_lost"] for row in data), "label": _("Money Lost in 13 Weeks"),
         "datatype": "Currency"},
    ]
    return columns, data, None, chart, report_summary


def months(filters):
    rows = summary.month_trend(today(), filters.get("company"), filters.get("branch"))
    data = [{"period": row["month"], "attendance": _pct(row["attendance"]), "unauthorised": _pct(row["unauthorised"]),
             "ot_hours": row["ot_hours"], "ot_share": _pct(row["ot_share"]), "labour": row["labour"],
             "labour_per_kg": row["labour_per_kg"], "cases": row["cases"], "grievances": row["grievances"],
             "exits": row["exits"], "recognitions": row["recognitions"]} for row in rows]
    columns = [
        {"fieldname": "period", "label": _("Month"), "fieldtype": "Data", "width": 100},
        {"fieldname": "attendance", "label": _("Attendance %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "unauthorised", "label": _("Unauthorised Absence %"), "fieldtype": "Percent", "width": 140},
        {"fieldname": "ot_hours", "label": _("Overtime Hours"), "fieldtype": "Float", "precision": 0, "width": 110},
        {"fieldname": "ot_share", "label": _("Overtime % of Labour"), "fieldtype": "Percent", "width": 130},
        {"fieldname": "labour", "label": _("Labour Cost"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "labour_per_kg", "label": _("Labour per Kg"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "cases", "label": _("Cases"), "fieldtype": "Int", "width": 70},
        {"fieldname": "grievances", "label": _("Grievances"), "fieldtype": "Int", "width": 90},
        {"fieldname": "exits", "label": _("Exits"), "fieldtype": "Int", "width": 70},
        {"fieldname": "recognitions", "label": _("Recognitions"), "fieldtype": "Int", "width": 100},
    ]
    chart = {"data": {"labels": [row["period"] for row in data],
                      "datasets": [{"name": _("Attendance %"), "values": [row["attendance"] or 0 for row in data]},
                                   {"name": _("Overtime % of Labour"), "values": [row["ot_share"] or 0
                                                                                   for row in data]}]},
             "type": "line", "colors": ["#1F3864", "#C9A227"], "lineOptions": {"regionFill": 0, "dotSize": 4}}
    return columns, data, None, chart
