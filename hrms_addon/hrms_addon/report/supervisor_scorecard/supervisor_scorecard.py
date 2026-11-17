# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Supervisor Scorecard (the workbook's Supervisor Dashboard): each
supervisor's production score, and their people-management index from what
is in their hands: shift reports entered for the shifts they lead,
attendance, PPE, safety, housekeeping, their team's conduct, actions closed
on time and coaching. Machines, materials and orders are left out.
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
        line = {key: row[key] for key in ("supervisor", "supervisor_name", "sections", "shifts", "due", "score",
                                          "score_status", "index", "status")}
        for key in rules.SUPERVISOR_KEYS:
            value = row["parts"][key]
            line["part_" + key] = round(value, 1) if value is not None else None
        data.append(line)
    return columns(s), data, None, chart(data)


def columns(s):
    found = [
        {"fieldname": "supervisor", "label": _("Supervisor"), "fieldtype": "Link", "options": "Employee",
         "width": 120},
        {"fieldname": "supervisor_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
        {"fieldname": "sections", "label": _("Sections"), "fieldtype": "Data", "width": 170},
        {"fieldname": "shifts", "label": _("Shifts Reported"), "fieldtype": "Int", "width": 100},
        {"fieldname": "due", "label": _("Shifts Due"), "fieldtype": "Int", "width": 90},
        {"fieldname": "score", "label": _("Production Score"), "fieldtype": "Float", "precision": 1, "width": 110},
        {"fieldname": "score_status", "label": _("Production Status"), "fieldtype": "Data", "width": 120},
    ]
    for key, label in rules.SUPERVISOR_PARTS:
        found.append({"fieldname": "part_" + key,
                      "label": "{0} ({1})".format(_(label), rules._plain(s["sup_" + key])),
                      "fieldtype": "Float", "precision": 1, "width": 120})
    found += [
        {"fieldname": "index", "label": _("People Index"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
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
