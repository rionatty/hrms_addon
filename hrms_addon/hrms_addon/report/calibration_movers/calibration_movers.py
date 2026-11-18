# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Calibration Movers (test case 7): every move of the calibration log,
insert only (calibration.py): proposed on the board or in a session,
applied when a session was submitted, moved straight, not agreed or taken
off. From which box to which, on which axis, who moved it, when and why.
It names boxes, so it is for HR and the Talent Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports

EVENTS = ("Moved", "Applied", "Proposed", "Not Agreed", "Reverted")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    conditions = {}
    for field in ("talent_review", "calibration_session", "branch", "department", "event"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    rows = frappe.get_list("Talent Calibration Log", filters=conditions, fields=[
        "name", "talent_review", "calibration_session", "placement", "employee", "employee_name", "branch",
        "department", "event", "source", "from_box", "to_box", "axis", "moved_by", "moved_on", "reason"],
        order_by="moved_on desc", limit_page_length=0)
    for row in rows:
        row["direction"] = _("Up") if (row.to_box or 0) > (row.from_box or 0) else _("Down") \
            if (row.to_box or 0) < (row.from_box or 0) else ""
    summary = [{"value": len([row for row in rows if row.event == event]), "label": _(event), "datatype": "Int",
                "indicator": {"Moved": "Blue", "Applied": "Green", "Proposed": "Orange"}.get(event, "Grey")}
               for event in EVENTS]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Talent Review"), "fieldname": "talent_review", "fieldtype": "Link", "options": "Talent Review",
         "width": 160},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("Plant"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 100},
        {"label": _("Event"), "fieldname": "event", "fieldtype": "Data", "width": 90},
        {"label": _("From Box"), "fieldname": "from_box", "fieldtype": "Int", "width": 85},
        {"label": _("To Box"), "fieldname": "to_box", "fieldtype": "Int", "width": 75},
        {"label": _("Axis"), "fieldname": "axis", "fieldtype": "Data", "width": 100},
        {"label": _("Why"), "fieldname": "reason", "fieldtype": "Data", "width": 300},
        {"label": _("By"), "fieldname": "moved_by", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": _("On"), "fieldname": "moved_on", "fieldtype": "Datetime", "width": 150},
        {"label": _("Session"), "fieldname": "calibration_session", "fieldtype": "Link",
         "options": "Calibration Session", "width": 140},
        {"label": _("Placement"), "fieldname": "placement", "fieldtype": "Link", "options": "Talent Placement",
         "width": 140},
    ]
