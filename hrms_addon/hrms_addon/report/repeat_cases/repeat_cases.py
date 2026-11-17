# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Repeat Cases (the workbook's Offender Tracker): employees with two
disciplinary cases or more in the look-back window, with their section,
how many went the disciplinary route, the cause seen most and what the
cases cost. Names can be hidden before the report leaves HR.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import excellence, excellence_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    s = excellence.settings()
    as_on = getdate(filters.get("as_on") or today())
    since = rules.add_months(as_on, -int(s["lookback_months"]))
    conditions = {"docstatus": ["<", 2], "incident_date": ["between", [since, as_on]]}
    for field in ("company", "branch", "work_section"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    cases = frappe.get_list(excellence.CASE, filters=conditions, limit_page_length=0,
                            fields=["name", "employee", "employee_name", "work_section", "incident_date", "cause",
                                    "severity", "case_cost"])
    found = rules.repeat_cases(cases, as_on, s["lookback_months"])
    names = {case.employee: (case.employee_name, case.work_section) for case in cases}
    hide = int(filters.get("hide_names") or 0)
    data = []
    for employee, row in sorted(found.items(), key=lambda item: (-item[1]["cases"], -item[1]["cost"])):
        cause = max(sorted(row["causes"]), key=lambda name: row["causes"][name])
        data.append({"employee": employee, "employee_name": "" if hide else names[employee][0],
                     "work_section": names[employee][1], "cases": row["cases"], "conduct": row["conduct"],
                     "main_cause": cause, "cost": row["cost"], "last_case": row["last_case"],
                     "last_date": row["last"]})
    return columns(hide), data, _("Cases from {0} to {1}.").format(
        frappe.format_value(since, {"fieldtype": "Date"}), frappe.format_value(as_on, {"fieldtype": "Date"}))


def columns(hide):
    found = [{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee",
              "width": 120}]
    if not hide:
        found.append({"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180})
    return found + [
        {"fieldname": "work_section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
         "width": 170},
        {"fieldname": "cases", "label": _("Cases"), "fieldtype": "Int", "width": 70},
        {"fieldname": "conduct", "label": _("Disciplinary Route"), "fieldtype": "Int", "width": 120},
        {"fieldname": "main_cause", "label": _("Main Cause"), "fieldtype": "Data", "width": 170},
        {"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "last_case", "label": _("Latest Case"), "fieldtype": "Link", "options": "Disciplinary Case",
         "width": 150},
        {"fieldname": "last_date", "label": _("Latest On"), "fieldtype": "Date", "width": 100},
    ]
