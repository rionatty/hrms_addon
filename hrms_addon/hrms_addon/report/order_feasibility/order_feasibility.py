# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Order Feasibility (the workbook's Order Feasibility sheet): each order
released to the floor, its progress from the submitted shifts that made it,
what running it has cost (the shifts' labour and overtime shared over their
output lines, the waste on its lines, its share of complaints) against its
value, and whether that is Feasible, Marginal or Not Feasible against the
conversion cost a unit may carry: the order's own budget, else the settings'
share of the order value. And the shifts and the cost to finish it.

The orders are read through the user's permissions (their finishing
section's plant); their output lines in one read.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hrms_addon.hrms_addon import excellence, excellence_rules as rules

ORDER, LINE = "Plant Order", "Shift Output"
LIGHTS = {rules.FEASIBLE: "green", rules.MARGINAL: "orange", rules.NOT_FEASIBLE: "red"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = order_rows(filters)
    return columns(), data, None, chart(data), summary(data)


def order_rows(filters):
    s = excellence.settings()
    conditions = {}
    for field in ("company", "branch", "finishing_section"):
        if filters.get(field):
            conditions[field] = filters.get(field)
    conditions["status"] = filters.get("status") or ["in", ["Open", "Running"]]
    orders = frappe.get_list(ORDER, filters=conditions, limit_page_length=0, order_by="released_on asc",
                             fields=["name", "customer", "product", "finishing_section", "branch", "unit", "order_qty",
                                     "order_value", "budget_per_unit", "status", "released_on", "due_on"])
    if not orders:
        return []
    progress = {row.name: {"shifts": set(), "finishing": set(), "first": None, "last": None, "produced": 0.0,
                           "labour": 0.0, "ot_hours": 0.0, "ot_cost": 0.0, "waste": 0.0, "complaints": 0.0}
                for row in orders}
    finishing = {row.name: row.finishing_section for row in orders}
    for line in frappe.get_all(LINE, filters={"plant_order": ["in", list(progress)], "docstatus": 1,
                                              "parenttype": "Shift Report"},
                               fields=["plant_order", "parent", "work_section", "report_date", "good_qty",
                                       "waste_value", "labour_share", "ot_hours_share", "ot_cost_share",
                                       "complaint_share"], limit_page_length=0):
        mine = progress[line.plant_order]
        mine["shifts"].add(line.parent)
        day = getdate(line.report_date) if line.report_date else None
        if day:
            mine["first"] = min(mine["first"], day) if mine["first"] else day
            mine["last"] = max(mine["last"], day) if mine["last"] else day
        if line.work_section == finishing[line.plant_order]:
            mine["produced"] += flt(line.good_qty)
            mine["finishing"].add(line.parent)
        mine["labour"] += flt(line.labour_share)
        mine["ot_hours"] += flt(line.ot_hours_share)
        mine["ot_cost"] += flt(line.ot_cost_share)
        mine["waste"] += flt(line.waste_value)
        mine["complaints"] += flt(line.complaint_share)
    data = []
    for order in orders:
        mine = progress[order.name]
        figures = rules.order_figures(order, dict(mine, shifts=len(mine["shifts"]),
                                                  finishing_shifts=len(mine["finishing"])), s)
        row = dict(order)
        row.update(figures)
        row["complete"] = round(figures["complete"] * 100, 1) if figures["complete"] is not None else None
        row["labour_share"] = round(figures["labour_share"] * 100, 2) if figures["labour_share"] is not None else None
        data.append(row)
    if filters.get("feasibility"):
        data = [row for row in data if row["feasibility"] == filters.get("feasibility")]
    return data


def columns():
    return [
        {"fieldname": "name", "label": _("Order"), "fieldtype": "Link", "options": ORDER, "width": 130},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Data", "width": 150},
        {"fieldname": "product", "label": _("Product"), "fieldtype": "Data", "width": 170},
        {"fieldname": "finishing_section", "label": _("Finishing Section"), "fieldtype": "Link",
         "options": "Work Section", "width": 150},
        {"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 60},
        {"fieldname": "order_qty", "label": _("Order Quantity"), "fieldtype": "Float", "precision": 0, "width": 110},
        {"fieldname": "order_value", "label": _("Order Value"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "budget_per_unit", "label": _("Budget per Unit"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "shifts", "label": _("Shifts Run"), "fieldtype": "Int", "width": 80},
        {"fieldname": "first", "label": _("First Shift"), "fieldtype": "Date", "width": 100},
        {"fieldname": "last", "label": _("Last Shift"), "fieldtype": "Date", "width": 100},
        {"fieldname": "produced", "label": _("Made"), "fieldtype": "Float", "precision": 0, "width": 100},
        {"fieldname": "complete", "label": _("Complete %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "balance", "label": _("Balance"), "fieldtype": "Float", "precision": 0, "width": 100},
        {"fieldname": "labour", "label": _("Labour"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "ot_hours", "label": _("Overtime Hours"), "fieldtype": "Float", "precision": 1, "width": 100},
        {"fieldname": "ot_cost", "label": _("Overtime Cost"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "waste", "label": _("Waste"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "complaints", "label": _("Complaints"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "conversion", "label": _("Conversion Cost"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "labour_per_unit", "label": _("Labour per Unit"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "conversion_per_unit", "label": _("Conversion per Unit"), "fieldtype": "Currency",
         "width": 120},
        {"fieldname": "unit_price", "label": _("Unit Price"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "labour_share", "label": _("Labour % of Value Made"), "fieldtype": "Percent", "width": 130},
        {"fieldname": "over_budget", "label": _("Over Budget per Unit"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "feasibility", "label": _("Feasibility"), "fieldtype": "Data", "width": 110},
        {"fieldname": "shifts_to_finish", "label": _("Shifts to Finish"), "fieldtype": "Float", "precision": 1,
         "width": 100},
        {"fieldname": "cost_to_finish", "label": _("Cost to Finish"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "projected", "label": _("Projected Conversion Cost"), "fieldtype": "Currency", "width": 140},
    ]


def chart(data):
    have = [row for row in data if row.get("conversion_per_unit") is not None and row.get("budget_per_unit")][:20]
    if not have:
        return None
    return {"data": {"labels": [row["name"] for row in have],
                     "datasets": [{"name": _("Conversion per Unit"), "values": [row["conversion_per_unit"]
                                                                                for row in have]},
                                  {"name": _("Budget per Unit"), "values": [row["budget_per_unit"] for row in have]}]},
            "type": "bar", "colors": ["#1F3864", "#C9A227"]}


def summary(data):
    counts = {label: sum(1 for row in data if row["feasibility"] == label)
              for label in (rules.FEASIBLE, rules.MARGINAL, rules.NOT_FEASIBLE)}
    return [{"value": counts[label], "label": _(label), "datatype": "Int",
             "indicator": {"green": "Green", "orange": "Orange", "red": "Red"}[LIGHTS[label]]} for label in counts] + [
        {"value": sum(flt(row.get("cost_to_finish")) for row in data), "label": _("Cost to Finish"),
         "datatype": "Currency"}]
