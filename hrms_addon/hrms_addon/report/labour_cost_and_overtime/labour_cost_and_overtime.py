# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Labour Cost and Overtime (the workbook's Labour Cost sheet), from the
submitted shifts' summaries.

  By Section    each section's person-shifts, regular and overtime labour,
                labour per unit against its budget, absence and its paid
                cost, overtime hours per person-shift, and against the period
                before of the same length: overtime cost and output. The
                four flags: Overtime Up, Output Not; Over Budget;
                Unauthorised Absence; Fatigue Risk; with the intervention to
                look at
  Day by Day    the plant's labour each day, Day and Night shift apart
  Day and Night the two shifts side by side
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules, excellence_summary as summary

VIEWS = ("By Section", "Day by Day", "Day and Night")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
    if end < start:
        frappe.throw(_("The period ends before it starts."))
    s = excellence.settings()
    view = filters.get("view") or VIEWS[0]
    if view == VIEWS[1]:
        return day_view(start, end, filters)
    if view == VIEWS[2]:
        return shift_view(start, end, filters, s)
    return section_view(start, end, filters, s)


def _pct(value):
    return round(value * 100, 1) if value is not None else None


def section_view(start, end, filters, s):
    rows = summary.labour_view(start, end, filters.get("company"), filters.get("branch"))
    data = []
    for section, row in sorted(rows.items()):
        t, before = row["now"], row["before"]
        a = rules.averages(t, s)
        days = t["shifts"] / 2.0 or 1
        unit = next(iter(t["by_unit"]), "") if t["by_unit"] else ""
        flags = row["flags"]
        data.append({
            "section": section, "shifts": t["shifts"], "person_shifts": t["staff_on_shift"],
            "average_staff": round(t["staff_on_shift"] / days, 1), "regular": t["regular_labour"],
            "ot_hours": t["ot_hours"], "ot_cost": t["ot_cost"], "labour": t["labour_cost"],
            "labour_per_day": round(t["labour_cost"] / days, 0), "ot_share": _pct(a["ot_share"]),
            "output": t["actual_output"], "unit": unit, "labour_per_unit": a["labour_per_unit"],
            "conversion_per_unit": ((t["labour_cost"] + t["money_lost"]) / t["actual_output"])
            if t["actual_output"] else None,
            "budget_variance": _pct(a["budget_variance"]), "absent": t["absent"],
            "unauthorised": t["unauthorised_absent"], "absence_cost": t["absence_cost"],
            "fatigue": round(a["fatigue"], 2) if a["fatigue"] is not None else None,
            "ot_change": _pct((t["ot_cost"] / before["ot_cost"] - 1) if before and before["ot_cost"] else None),
            "output_change": _pct((t["actual_output"] / before["actual_output"] - 1)
                                  if before and before["actual_output"] else None),
            "flag": ", ".join(flag for flag, _intervention in flags),
            "intervention": flags[0][1] if flags else "",
        })
    columns = [
        {"fieldname": "section", "label": _("Section"), "fieldtype": "Link", "options": "Work Section", "width": 160},
        {"fieldname": "shifts", "label": _("Shifts"), "fieldtype": "Int", "width": 70},
        {"fieldname": "person_shifts", "label": _("Person-Shifts"), "fieldtype": "Int", "width": 100},
        {"fieldname": "average_staff", "label": _("Average Staff a Day"), "fieldtype": "Float", "width": 110},
        {"fieldname": "regular", "label": _("Regular Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_hours", "label": _("Overtime Hours"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "ot_cost", "label": _("Overtime Cost"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "labour", "label": _("Total Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "labour_per_day", "label": _("Labour a Day"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "ot_share", "label": _("Overtime %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "output", "label": _("Output"), "fieldtype": "Float", "precision": 0, "width": 100},
        {"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 60},
        {"fieldname": "labour_per_unit", "label": _("Labour per Unit"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "conversion_per_unit", "label": _("Labour and Losses per Unit"), "fieldtype": "Currency",
         "width": 140},
        {"fieldname": "budget_variance", "label": _("Against Budget %"), "fieldtype": "Percent", "width": 110},
        {"fieldname": "absent", "label": _("Absent Person-Shifts"), "fieldtype": "Int", "width": 120},
        {"fieldname": "unauthorised", "label": _("Unauthorised"), "fieldtype": "Int", "width": 100},
        {"fieldname": "absence_cost", "label": _("Paid Absence Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "fatigue", "label": _("Overtime Hours per Person-Shift"), "fieldtype": "Float",
         "precision": 2, "width": 130},
        {"fieldname": "ot_change", "label": _("Overtime Cost against Before %"), "fieldtype": "Percent",
         "width": 130},
        {"fieldname": "output_change", "label": _("Output against Before %"), "fieldtype": "Percent", "width": 130},
        {"fieldname": "flag", "label": _("Flag"), "fieldtype": "Data", "width": 220},
        {"fieldname": "intervention", "label": _("Suggested HR Intervention"), "fieldtype": "Data", "width": 230},
    ]
    chart = {"data": {"labels": [rules.section_label(row["section"]) for row in data],
                      "datasets": [{"name": _("Regular Labour"), "values": [row["regular"] for row in data]},
                                   {"name": _("Overtime Cost"), "values": [row["ot_cost"] for row in data]}]},
             "type": "bar", "barOptions": {"stacked": 1}, "colors": ["#1F3864", "#C9A227"]} if data else None
    flagged = sum(1 for row in data if row["flag"])
    report_summary = [
        {"value": sum(row["labour"] for row in data), "label": _("Total Labour Cost"), "datatype": "Currency"},
        {"value": sum(row["ot_cost"] for row in data), "label": _("Overtime Cost"), "datatype": "Currency"},
        {"value": flagged, "label": _("Sections Flagged"), "datatype": "Int",
         "indicator": "Red" if flagged else "Green"},
    ]
    return columns, data, None, chart, report_summary


def day_view(start, end, filters):
    scope = summary.scope_filters(start, end, filters.get("company"), filters.get("branch"))
    by_day = {}
    for (day, shift), t in summary.grouped(scope, ("summary_date", "shift")).items():
        by_day.setdefault(str(day), {})[shift] = t
    data = []
    day = start
    while day <= end:
        shifts = by_day.get(str(day), {})
        t = rules.add_totals(*shifts.values())
        data.append({"day": day, "weekday": day.strftime("%a"), "section_shifts": t["shifts"],
                     "staff": t["staff_on_shift"], "regular": t["regular_labour"], "ot_hours": t["ot_hours"],
                     "ot_cost": t["ot_cost"], "labour": t["labour_cost"],
                     "day_labour": shifts.get(rules.DAY, {}).get("labour_cost", 0),
                     "night_labour": shifts.get(rules.NIGHT, {}).get("labour_cost", 0),
                     "ot_share": _pct(rules.ratio(t["ot_cost"], t["labour_cost"])), "waste": t["waste_value"],
                     "complaints": t["complaint_value"]})
        day = add_days(day, 1)
    columns = [
        {"fieldname": "day", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "weekday", "label": _("Day"), "fieldtype": "Data", "width": 60},
        {"fieldname": "section_shifts", "label": _("Section Shifts"), "fieldtype": "Int", "width": 100},
        {"fieldname": "staff", "label": _("Staff on Shift"), "fieldtype": "Int", "width": 100},
        {"fieldname": "regular", "label": _("Regular Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_hours", "label": _("Overtime Hours"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "ot_cost", "label": _("Overtime Cost"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "labour", "label": _("Total Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "day_labour", "label": _("Day Shift Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "night_labour", "label": _("Night Shift Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_share", "label": _("Overtime %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "waste", "label": _("Waste"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "complaints", "label": _("Complaints"), "fieldtype": "Currency", "width": 110},
    ]
    chart = {"data": {"labels": [str(row["day"]) for row in data],
                      "datasets": [{"name": _("Regular Labour"), "values": [row["regular"] for row in data]},
                                   {"name": _("Overtime Cost"), "values": [row["ot_cost"] for row in data]}]},
             "type": "bar", "barOptions": {"stacked": 1}, "colors": ["#1F3864", "#C9A227"]} if data else None
    return columns, data, None, chart


def shift_view(start, end, filters, s):
    scope = summary.scope_filters(start, end, filters.get("company"), filters.get("branch"))
    by_shift = {}
    for (shift, _unit), t in summary.grouped(scope, ("shift", "unit")).items():
        by_shift.setdefault(shift, []).append(t)
    data = []
    for shift in rules.SHIFTS:
        t = rules.add_totals(*by_shift.get(shift, []))
        a = rules.averages(t, s)
        data.append({"shift": shift, "person_shifts": t["staff_on_shift"], "labour": t["labour_cost"],
                     "ot_cost": t["ot_cost"], "ot_share": _pct(a["ot_share"]), "attendance": _pct(a["attendance"]),
                     "unauthorised": t["unauthorised_absent"], "ppe": _pct(a["ppe"]),
                     "kg_per_person": rules._per(t, "Kg", "actual", "on_shift"), "score": a["score"],
                     "money_lost": t["money_lost"], "incidents": t["safety_incidents"]})
    columns = [
        {"fieldname": "shift", "label": _("Shift"), "fieldtype": "Data", "width": 80},
        {"fieldname": "score", "label": _("Score"), "fieldtype": "Float", "precision": 1, "width": 80},
        {"fieldname": "person_shifts", "label": _("Person-Shifts"), "fieldtype": "Int", "width": 100},
        {"fieldname": "labour", "label": _("Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_cost", "label": _("Overtime Cost"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "ot_share", "label": _("Overtime %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "attendance", "label": _("Attendance %"), "fieldtype": "Percent", "width": 100},
        {"fieldname": "unauthorised", "label": _("Unauthorised Absent"), "fieldtype": "Int", "width": 120},
        {"fieldname": "ppe", "label": _("PPE %"), "fieldtype": "Percent", "width": 80},
        {"fieldname": "kg_per_person", "label": _("Kg per Person-Shift"), "fieldtype": "Float", "precision": 1,
         "width": 120},
        {"fieldname": "money_lost", "label": _("Money Lost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 80},
    ]
    return columns, data
