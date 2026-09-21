# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance Analytics (Dashboards & Reports, case 5): how the appraisal
round is going, per department and per plant.

Completion is counted against the people who were due an appraisal, not
against the appraisals that exist — a department where nobody has started
reads nought per cent here, and reads as an empty list anywhere else.

The band distribution is read from the appraisal's own band, which comes
off whichever of Luuka's two forms the employee is on (appraisal_rules and
bsc_rules), so this report does not decide a band and cannot disagree with
the form that did.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import appraisal_rules

BANDS = tuple(name for _floor, name in appraisal_rules.BANDS)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"status": "Active"}
    for field in ("company", "branch", "department"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    employees = frappe.get_list("Employee", filters=conditions,
                                fields=["name", "branch", "department"], limit_page_length=0)
    if not employees:
        return columns(), []
    by_employee = {row.name: row for row in employees}

    appraisal_filters = {"employee": ["in", list(by_employee)]}
    if filters.get("appraisal_cycle"):
        appraisal_filters["appraisal_cycle"] = filters.appraisal_cycle
    appraisals = frappe.get_all(
        "Appraisal", filters=appraisal_filters,
        fields=["employee", "docstatus", "custom_total_score", "custom_band",
                "custom_form_type"], limit=20000)

    groups = {}
    for employee in employees:
        key = _key(employee, filters)
        groups.setdefault(key, _blank(key))["due"] += 1
    for row in appraisals:
        employee = by_employee.get(row.employee)
        if not employee:
            continue
        group = groups.setdefault(_key(employee, filters), _blank(_key(employee, filters)))
        group["started"] += 1
        if row.docstatus != 1:
            continue
        group["completed"] += 1
        group["scores"].append(flt(row.custom_total_score))
        if row.custom_band in BANDS:
            group[_band_field(row.custom_band)] += 1
        if flt(row.custom_total_score) < appraisal_rules.PIP_BELOW:
            group["below_the_mark"] += 1

    rows = []
    for group in groups.values():
        scores = group.pop("scores")
        group["average_score"] = round(sum(scores) / len(scores), 2) if scores else None
        group["completion"] = round(group["completed"] * 100.0 / group["due"], 1) \
            if group["due"] else 0
        group["outstanding"] = group["due"] - group["completed"]
        rows.append(group)
    rows.sort(key=lambda row: (row["completion"], str(row["group"])))
    return columns(), rows


def _key(employee, filters):
    if filters.get("by_plant"):
        return employee.branch or _("No Plant")
    return employee.department or _("No Department")


def _blank(key):
    row = {"group": key, "due": 0, "started": 0, "completed": 0, "below_the_mark": 0,
           "scores": []}
    for band in BANDS:
        row[_band_field(band)] = 0
    return row


def _band_field(band):
    return "band_" + band.lower().replace(" ", "_")


def columns():
    out = [
        {"label": _("Department or Plant"), "fieldname": "group", "fieldtype": "Data",
         "width": 200},
        {"label": _("Due"), "fieldname": "due", "fieldtype": "Int", "width": 80},
        {"label": _("Started"), "fieldname": "started", "fieldtype": "Int", "width": 90},
        {"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
        {"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Int",
         "width": 110},
        {"label": _("Completion %"), "fieldname": "completion", "fieldtype": "Percent",
         "width": 110},
        {"label": _("Average Score"), "fieldname": "average_score", "fieldtype": "Float",
         "precision": 2, "width": 120},
    ]
    for band in BANDS:
        out.append({"label": _(band), "fieldname": _band_field(band), "fieldtype": "Int",
                    "width": 110})
    out.append({"label": _("Below the Mark"), "fieldname": "below_the_mark",
                "fieldtype": "Int", "width": 130})
    return out
