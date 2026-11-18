# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Shift Scorecard (the workbook's Weekly Summary and Production Dashboard):
the submitted shifts of a period by section, plant, supervisor, week, day or
shift. Each group is scored from its totals, as the workbook does, with its
weakest factor, output against target, uptime and the main downtime reason,
attendance, PPE, safety, the money lost to waste and complaints, and labour
cost against its budget. The first row is the whole selection. Read from the
stored summaries with GROUP BY.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules, excellence_summary as summary
from hrms_addon.hrms_addon.queries import aggregate

GROUPS = {"Section": "work_section", "Plant": "branch", "Supervisor": "supervisor", "Week": "week",
          "Day": "summary_date", "Shift": "shift"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    s = excellence.settings()
    scope = summary.scope_filters(start, end, filters.get("company"), filters.get("branch"),
                                  filters.get("work_section"), filters.get("shift"))
    by = filters.get("group_by") or "Section"
    field = GROUPS.get(by, "work_section")
    groups = {}
    for (key, _unit), totals in summary.grouped(scope, (field, "unit")).items():
        groups.setdefault(key, []).append(totals)
    whole = summary.scope_totals(scope)
    reasons = main_reasons(scope, field)
    names = _names([key for key in groups if key]) if field == "supervisor" else {}
    data = [line(_("All"), whole, s, bold=1, reason=main_reasons(scope, None).get(None, ""))] if whole["shifts"] else []
    for key in sorted(groups, key=lambda value: str(value or "")):
        label = names.get(key) or key or (_("No Supervisor") if field == "supervisor" else "")
        data.append(line(label, rules.add_totals(*groups[key]), s, reason=reasons.get(key, "")))
    return columns(by), data, None, chart(data[1:]), report_summary(whole, s)


def _names(employees):
    return dict(frappe.get_all("Employee", filters={"name": ["in", employees]}, fields=["name", "employee_name"],
                               as_list=True)) if employees else {}


def main_reasons(scope, field):
    """{group: the reason that cost it most machine hours}; one group when no
    field is given."""
    if field == "supervisor":
        return {}
    by = [field] if field else []
    found = {}
    rows = frappe.get_list(summary.DOWNTIME, filters=scope,
                           fields=by + ["downtime_reason", aggregate("SUM", "minutes", "minutes")],
                           group_by=", ".join(by + ["downtime_reason"]), order_by=None, limit_page_length=0)
    for row in rows:
        key = row.get(field) if by else None
        best = found.get(key)
        if best is None or flt(row.get("minutes")) > best[1]:
            found[key] = (row.get("downtime_reason") or rules.NO_REASON, flt(row.get("minutes")))
    return {key: value[0] for key, value in found.items()}


def line(key, t, s, bold=0, reason=""):
    a = rules.averages(t, s)
    one_unit = len(t["by_unit"]) == 1
    unit = next(iter(t["by_unit"])) if one_unit else ""
    pct = lambda value: round(value * 100, 1) if value is not None else None  # noqa: E731
    return {
        "group": key, "bold": bold, "shifts": t["shifts"], "score": a["score"], "status": a["status"],
        "weakest": rules.FACTOR_LABELS.get(a["weakest"], ""), "achievement": pct(a["achievement"]),
        "output": t["actual_output"] if one_unit else None, "unit": unit, "uptime": pct(a["uptime"]),
        "hours_lost": t["hours_lost"], "top_downtime": reason or "",
        "attendance": pct(a["attendance"]), "ppe": pct(a["ppe"]), "not_wearing": t["not_wearing"],
        "incidents": t["safety_incidents"], "near_misses": t["near_misses"], "waste": t["waste_value"],
        "complaints": t["complaint_value"], "money_lost": t["money_lost"], "labour": t["labour_cost"],
        "ot_cost": t["ot_cost"], "ot_share": pct(a["ot_share"]),
        "labour_per_unit": (t["labour_cost"] / t["actual_output"]) if one_unit and t["actual_output"] else None,
        "budget_variance": pct(a["budget_variance"]), "absence_cost": t["absence_cost"],
    }


def columns(by):
    group = {"fieldname": "group", "label": _(by), "fieldtype": "Data", "width": 200}
    if by == "Section":
        group.update({"fieldtype": "Link", "options": "Work Section"})
    elif by == "Plant":
        group.update({"fieldtype": "Link", "options": "Branch"})
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
        {"fieldname": "not_wearing", "label": _("Not Wearing PPE"), "fieldtype": "Int", "width": 100},
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


def report_summary(t, s):
    a = rules.averages(t, s)
    return [
        {"value": a["score"], "label": _("Score from the Totals"), "datatype": "Float",
         "indicator": {"On Target": "Green", "Attention": "Orange"}.get(a["status"], "Red")},
        {"value": t["money_lost"], "label": _("Money Lost"), "datatype": "Currency"},
        {"value": t["hours_lost"], "label": _("Machine Hours Lost"), "datatype": "Float"},
        {"value": t["labour_cost"], "label": _("Labour Cost"), "datatype": "Currency"},
        {"value": t["safety_incidents"], "label": _("Safety Incidents"), "datatype": "Int",
         "indicator": "Red" if t["safety_incidents"] else "Green"},
    ]
