# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Supervisor Scorecard (the workbook's Supervisor Dashboard): every supervisor
on the roster in the period, or who ran a shift in it. Their production score
from their shifts' totals with its weakest area and what HR and the
supervisor do next; and their people-management index from what is in their
hands: shift rows entered for the shifts they lead, attendance, PPE, safety,
housekeeping, their team's conduct, actions closed on time and coaching, with
the development focus its weakest part points to, their open actions and the
leadership development they have had. Machines, materials and orders are
left out of the index. One read of each kind for all of them
(excellence_summary.supervisor_rows).
"""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    found, s = excellence.supervisor_rows(start, end, filters.get("company"), filters.get("branch"),
                                          filters.get("work_section"), filters.get("shift"))
    data = []
    for row in sorted(found, key=lambda row: (row["index"] is None, -(row["index"] or 0))):
        line = {key: row[key] for key in ("supervisor", "supervisor_name", "sections", "shift", "shifts", "due",
                                          "score", "score_status", "weakest", "next_step", "index", "status",
                                          "band", "focus", "open_actions", "development", "money_lost")}
        for key in rules.SUPERVISOR_KEYS:
            value = row["parts"][key]
            line["part_" + key] = round(value, 1) if value is not None else None
        data.append(line)
    return columns(s), data, None, chart(data), summary(data, s)


def columns(s):
    found = [
        {"fieldname": "supervisor", "label": _("Supervisor"), "fieldtype": "Link", "options": "Employee",
         "width": 120},
        {"fieldname": "supervisor_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "sections", "label": _("Sections"), "fieldtype": "Data", "width": 150},
        {"fieldname": "shift", "label": _("Shift"), "fieldtype": "Data", "width": 70},
        {"fieldname": "shifts", "label": _("Shifts Reported"), "fieldtype": "Int", "width": 100},
        {"fieldname": "due", "label": _("Shifts Due"), "fieldtype": "Int", "width": 90},
        {"fieldname": "score", "label": _("Production Score"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "score_status", "label": _("Production Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "weakest", "label": _("Weakest Area"), "fieldtype": "Data", "width": 130},
        {"fieldname": "next_step", "label": _("What HR and the Supervisor Do Next"), "fieldtype": "Data",
         "width": 260},
        {"fieldname": "money_lost", "label": _("Money Lost"), "fieldtype": "Currency", "width": 120},
    ]
    for key, label in rules.SUPERVISOR_PARTS:
        found.append({"fieldname": "part_" + key,
                      "label": "{0} ({1})".format(_(label), rules._plain(s["sup_" + key])),
                      "fieldtype": "Float", "precision": 1, "width": 120})
    found += [
        {"fieldname": "index", "label": _("People Index"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "band", "label": _("People Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "focus", "label": _("Development Focus"), "fieldtype": "Data", "width": 190},
        {"fieldname": "open_actions", "label": _("Open Actions"), "fieldtype": "Int", "width": 100},
        {"fieldname": "development", "label": _("Leadership Development Received"), "fieldtype": "Int",
         "width": 130},
    ]
    return found


def chart(data):
    have = [row for row in data if row["index"] is not None][:30]
    if not have:
        return None
    return {"data": {"labels": [row["supervisor_name"] or row["supervisor"] for row in have],
                     "datasets": [{"name": _("People Index"), "values": [row["index"] for row in have]},
                                  {"name": _("Production Score"), "values": [row["score"] or 0 for row in have]}]},
            "type": "bar", "colors": ["#1F3864", "#C9A227"]}


def summary(data, s):
    scored = [row["score"] for row in data if row["score"] is not None]
    people = [row["index"] for row in data if row["index"] is not None]
    return [
        {"value": round(sum(scored) / len(scored), 1) if scored else None, "label": _("Average Production Score"),
         "datatype": "Float"},
        {"value": sum(1 for value in scored if value < s["green_from"]), "label": _("Below Green"), "datatype": "Int",
         "indicator": "Orange"},
        {"value": sum(1 for value in people if value < s["amber_from"]), "label": _("Need Leadership Coaching"),
         "datatype": "Int", "indicator": "Red"},
    ]
