# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Calibration Movers (test case 7): every placement the peer group moved
in calibration, from which box to which, who moved it, when and why. It
names boxes, so it is for HR and the Talent Council."""

import frappe
from frappe import _

from hrms_addon.hrms_addon import talent_reports


def execute(filters=None):
    filters = frappe._dict(filters or {})
    talent_reports.check_boxes()
    conditions = {"parenttype": "Talent Review"}
    if filters.get("talent_review"):
        conditions["parent"] = filters.talent_review
    rows = frappe.get_all("Talent Calibration Entry", filters=conditions, fields=[
        "parent", "placement", "employee", "employee_name", "from_box", "to_box", "moved_by", "moved_on", "reason"],
        order_by="moved_on desc", limit=0)
    for row in rows:
        row["direction"] = _("Up") if (row.to_box or 0) > (row.from_box or 0) else _("Down")
    summary = [{"value": len(rows), "label": _("Moves"), "datatype": "Int", "indicator": "Blue"}]
    return columns(), rows, None, None, summary


def columns():
    return [
        {"label": _("Talent Review"), "fieldname": "parent", "fieldtype": "Link", "options": "Talent Review",
         "width": 160},
        {"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
        {"label": _("From Box"), "fieldname": "from_box", "fieldtype": "Int", "width": 85},
        {"label": _("To Box"), "fieldname": "to_box", "fieldtype": "Int", "width": 75},
        {"label": _("Up or Down"), "fieldname": "direction", "fieldtype": "Data", "width": 90},
        {"label": _("Why"), "fieldname": "reason", "fieldtype": "Data", "width": 320},
        {"label": _("Moved By"), "fieldname": "moved_by", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": _("On"), "fieldname": "moved_on", "fieldtype": "Date", "width": 100},
        {"label": _("Placement"), "fieldname": "placement", "fieldtype": "Link", "options": "Talent Placement",
         "width": 140},
    ]
