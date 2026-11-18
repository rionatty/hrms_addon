# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Downtime and Money Lost (the workbook's Machines and Downtime, and its
money lost charts): why machines stood, from the submitted shifts' downtime
by reason and machine, and where the money went to waste and complaints.

  By Reason       hours lost, the share of all hours lost, the shifts it hit,
                  its category and whether it was planned
  By Machine      the same by machine
  By Section      hours lost, machine use and uptime by section
  Money Lost      waste and complaints by section
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules, excellence_summary as summary

VIEWS = ("By Reason", "By Machine", "By Section", "Money Lost")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    s = excellence.settings()
    view = filters.get("view") or VIEWS[0]
    scope = (start, end, filters.get("company"), filters.get("branch"), filters.get("work_section"),
             filters.get("shift"))
    if view in (VIEWS[0], VIEWS[1]):
        by = "downtime_reason" if view == VIEWS[0] else "machine"
        rows = rules.downtime_breakdown(summary.downtime(*scope, by=by))
        data = [dict(row, share=round(row["share"] * 100, 1)) for row in rows]
        label = _("Reason") if by == "downtime_reason" else _("Machine")
        columns = [
            {"fieldname": "reason", "label": label, "fieldtype": "Link",
             "options": "Downtime Reason" if by == "downtime_reason" else "Machine", "width": 200},
            {"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 120},
            {"fieldname": "planned", "label": _("Planned"), "fieldtype": "Check", "width": 80},
            {"fieldname": "hours", "label": _("Machine Hours Lost"), "fieldtype": "Float", "precision": 1,
             "width": 130},
            {"fieldname": "share", "label": _("Share of Hours Lost"), "fieldtype": "Percent", "width": 130},
            {"fieldname": "shifts", "label": _("Shifts Hit"), "fieldtype": "Int", "width": 90},
        ]
        if by == "machine":
            columns = [column for column in columns if column["fieldname"] not in ("category", "planned")]
        chart = {"data": {"labels": [row["reason"] or rules.NO_REASON for row in data[:15]],
                          "datasets": [{"name": _("Machine Hours Lost"), "values": [row["hours"] for row in data[:15]]}]},
                 "type": "bar", "colors": ["#1F3864"]} if data else None
        return columns, data, None, chart
    totals = summary.section_totals(summary.scope_filters(*scope))
    data = []
    for section, t in sorted(totals.items()):
        a = rules.averages(t, s)
        data.append({"section": section, "shifts": t["shifts"], "machines": round(t["machines"] / t["shifts"], 1)
                     if t["shifts"] else 0, "running": round(t["machines_running"] / t["shifts"], 1) if t["shifts"]
                     else 0, "machine_use": round(a["machine_use"] * 100, 1) if a["machine_use"] is not None else None,
                     "hours_lost": t["hours_lost"], "uptime": round(a["uptime"] * 100, 1)
                     if a["uptime"] is not None else None, "waste": t["waste_value"],
                     "complaints": t["complaint_value"], "money_lost": t["money_lost"]})
    if view == VIEWS[3]:
        data.sort(key=lambda row: -row["money_lost"])
        columns = [
            {"fieldname": "section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
             "width": 180},
            {"fieldname": "waste", "label": _("Waste"), "fieldtype": "Currency", "width": 130},
            {"fieldname": "complaints", "label": _("Complaints"), "fieldtype": "Currency", "width": 130},
            {"fieldname": "money_lost", "label": _("Money Lost"), "fieldtype": "Currency", "width": 130},
        ]
        chart = {"data": {"labels": [rules.section_label(row["section"]) for row in data],
                          "datasets": [{"name": _("Waste"), "values": [row["waste"] for row in data]},
                                       {"name": _("Complaints"), "values": [row["complaints"] for row in data]}]},
                 "type": "bar", "barOptions": {"stacked": 1}, "colors": ["#1F3864", "#C9A227"]} if data else None
        return columns, data, None, chart
    columns = [
        {"fieldname": "section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section", "width": 180},
        {"fieldname": "shifts", "label": _("Shifts"), "fieldtype": "Int", "width": 70},
        {"fieldname": "machines", "label": _("Machines"), "fieldtype": "Float", "precision": 1, "width": 90},
        {"fieldname": "running", "label": _("Running a Shift"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "machine_use", "label": _("Machine Use %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "hours_lost", "label": _("Machine Hours Lost"), "fieldtype": "Float", "precision": 1,
         "width": 130},
        {"fieldname": "uptime", "label": _("Uptime %"), "fieldtype": "Percent", "width": 90},
    ]
    return columns, data
