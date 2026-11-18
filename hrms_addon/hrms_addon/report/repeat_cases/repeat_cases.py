# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Repeat Cases (the workbook's Offender Tracker): the employee relations
cases of a period, for HR.

  Employees with Repeat Cases   two cases or more in the look back window:
                                cases, conduct cases, cost, the last case,
                                its type and cause, and its flag
  Cases with Flags              each case with a legal flag, Decision Due
                                (charged or heard, not decided), Overdue (open
                                past the target days) or Repeat
  By Section, Cause, Case Type, Shift, Employment, Supervisor
                                the cases grouped: Day and Night, the
                                disciplinary route against coaching or a
                                process fix, grievances, cost, quantity
                                affected, repeat flags, the main cause

Names are left out when the Manufacturing Excellence Settings say so. The
cases are read through the user's permissions, so only those who may read
cases see any.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from hrms_addon.hrms_addon import excellence, excellence_rules as rules, excellence_summary as summary


def execute(filters=None):
    filters = frappe._dict(filters or {})
    s = excellence.settings()
    end = getdate(filters.get("to_date") or filters.get("as_on") or today())
    start = getdate(filters.get("from_date") or rules.add_months(end, -int(s["lookback_months"])))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    view = filters.get("view") or rules.TRACKER_VIEWS[0]
    hide = cint(s["hide_names"])
    since = rules.add_months(start, -int(s["lookback_months"]))
    every = summary.cases_between(since, end, filters.get("company"), filters.get("branch"),
                                  filters.get("work_section"))
    counts = rules.window_counts(every, s["lookback_months"])
    period = [row for row in every if start <= getdate(row.incident_date) <= end]
    message = _("Cases from {0} to {1}.").format(frappe.format_value(start, {"fieldtype": "Date"}),
                                                 frappe.format_value(end, {"fieldtype": "Date"}))
    if view == rules.TRACKER_VIEWS[0]:
        return repeat_view(every, end, s, hide) + (message,)
    if view == rules.TRACKER_VIEWS[1]:
        return flag_view(period, counts, s, hide) + (message,)
    key = rules.TRACKER_KEYS.get(view, "work_section")
    return breakdown_view(period, key, counts, filters, view) + (message,)


def _who(row, hide):
    return "" if hide else (row.employee_name or "")


def repeat_view(cases, as_on, s, hide):
    found = rules.repeat_cases(cases, as_on, s["lookback_months"])
    latest = {row.name: row for row in cases}
    data = []
    counts = rules.window_counts(cases, s["lookback_months"])
    for employee, row in sorted(found.items(), key=lambda item: (-item[1]["cases"], -item[1]["cost"])):
        last = latest.get(row["last_case"]) or {}
        data.append({"employee": employee, "employee_name": _who(last, hide) if last else "",
                     "work_section": last.get("work_section"), "shift": last.get("shift"), "cases": row["cases"],
                     "conduct": row["conduct"], "cost": row["cost"], "last_case": row["last_case"],
                     "last_date": row["last"], "last_type": last.get("misconduct_type") or last.get("case_type"),
                     "last_cause": last.get("cause") or _("Not Classified"),
                     "flag": rules.tracker_flag(last, counts.get(row["last_case"]), today(), s) if last else ""})
    columns = [{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee",
                "width": 120}]
    if not hide:
        columns.append({"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 180})
    columns += [
        {"fieldname": "work_section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
         "width": 170},
        {"fieldname": "shift", "label": _("Last Shift"), "fieldtype": "Data", "width": 80},
        {"fieldname": "cases", "label": _("Cases"), "fieldtype": "Int", "width": 70},
        {"fieldname": "conduct", "label": _("Disciplinary Route"), "fieldtype": "Int", "width": 120},
        {"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "last_case", "label": _("Latest Case"), "fieldtype": "Link", "options": "Disciplinary Case",
         "width": 150},
        {"fieldname": "last_date", "label": _("Latest On"), "fieldtype": "Date", "width": 100},
        {"fieldname": "last_type", "label": _("Latest Type"), "fieldtype": "Data", "width": 150},
        {"fieldname": "last_cause", "label": _("Latest Cause"), "fieldtype": "Data", "width": 150},
        {"fieldname": "flag", "label": _("Flag"), "fieldtype": "Data", "width": 200},
    ]
    return columns, data


def flag_view(cases, counts, s, hide):
    data = []
    for row in cases:
        flag = rules.tracker_flag(row, counts.get(row.name), today(), s)
        if not flag:
            continue
        data.append({"case": row.name, "incident_date": row.incident_date, "employee": row.employee,
                     "employee_name": _who(row, hide), "work_section": row.work_section, "shift": row.shift,
                     "case_type": row.case_type, "cause": row.cause or _("Not Classified"), "status": row.status,
                     "flag": flag, "cases_in_window": counts.get(row.name, 0)})
    order = {rules.DECISION_DUE: 1, rules.OVERDUE: 2, rules.REPEAT: 3}
    data.sort(key=lambda row: (order.get(row["flag"], 0), str(row["incident_date"])))
    columns = [
        {"fieldname": "case", "label": _("Case"), "fieldtype": "Link", "options": "Disciplinary Case", "width": 150},
        {"fieldname": "incident_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
    ]
    if not hide:
        columns.append({"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170})
    columns += [
        {"fieldname": "work_section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section",
         "width": 160},
        {"fieldname": "shift", "label": _("Shift"), "fieldtype": "Data", "width": 70},
        {"fieldname": "case_type", "label": _("Case Type"), "fieldtype": "Data", "width": 110},
        {"fieldname": "cause", "label": _("Cause"), "fieldtype": "Data", "width": 160},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "flag", "label": _("Flag"), "fieldtype": "Data", "width": 260},
        {"fieldname": "cases_in_window", "label": _("Cases in the Window"), "fieldtype": "Int", "width": 120},
    ]
    return columns, data


def breakdown_view(cases, key, counts, filters, view):
    grouped = rules.tracker_breakdown(cases, key, counts)
    names = {}
    if key == "supervisor_on_shift":
        names = {row.supervisor_on_shift: row.supervisor_on_shift_name for row in cases if row.supervisor_on_shift}
    open_grievances = {}
    if key == "work_section":
        for row in summary.grievance_rows(filters.get("company"), filters.get("branch"), filters.get("work_section")):
            open_grievances[row.custom_work_section] = open_grievances.get(row.custom_work_section, 0) + 1
    data = []
    for value, row in sorted(grouped.items(), key=lambda item: (-item[1]["cases"], str(item[0]))):
        cause = max(sorted(row["causes"]), key=lambda name: row["causes"][name])
        data.append({"group": names.get(value) or value, "cases": row["cases"], "day": row["day"],
                     "night": row["night"], "conduct": row["conduct"], "coaching": row["coaching"],
                     "process": row["process"], "grievances": row["grievances"] + open_grievances.get(value, 0),
                     "cost": row["cost"], "quantity": row["quantity"], "repeats": row["repeats"],
                     "main_cause": cause, "share": round(100.0 * row["cases"] / len(cases), 1) if cases else 0})
    columns = [
        {"fieldname": "group", "label": _(view.replace("By ", "")), "fieldtype": "Data", "width": 190},
        {"fieldname": "cases", "label": _("Cases"), "fieldtype": "Int", "width": 70},
        {"fieldname": "share", "label": _("Share of Cases"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "day", "label": _("Day"), "fieldtype": "Int", "width": 60},
        {"fieldname": "night", "label": _("Night"), "fieldtype": "Int", "width": 60},
        {"fieldname": "conduct", "label": _("Disciplinary Route"), "fieldtype": "Int", "width": 120},
        {"fieldname": "coaching", "label": _("Coaching or Training"), "fieldtype": "Int", "width": 120},
        {"fieldname": "process", "label": _("Process or Supervision"), "fieldtype": "Int", "width": 130},
        {"fieldname": "grievances", "label": _("Grievances"), "fieldtype": "Int", "width": 90},
        {"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "quantity", "label": _("Quantity Affected"), "fieldtype": "Float", "width": 120},
        {"fieldname": "repeats", "label": _("Repeat Flags"), "fieldtype": "Int", "width": 100},
        {"fieldname": "main_cause", "label": _("Main Cause"), "fieldtype": "Data", "width": 170},
    ]
    return columns, data
