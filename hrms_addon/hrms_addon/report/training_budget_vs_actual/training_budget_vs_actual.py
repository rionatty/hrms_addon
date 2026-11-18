# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Budget vs Actual (the brief's section 13): the year's budget lines
against what the sessions held cost and what those to come are expected to
cost, by plant, department, category, programme, provider, month, cost type or
cost centre; the forecast for the year, what remains and how much is used.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_value, learning_value_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    label = filters.get("group_by") if filters.get("group_by") in rules.GROUP_KEY else "Plant"
    data = learning_value.budget_vs_actual(filters)
    for row in data:
        row["group"] = row["group"] or _("Not Set")
    columns = [
        {"fieldname": "group", "label": _(label), "fieldtype": "Data", "width": 190},
        {"fieldname": "budget", "label": _("Budget"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "actual", "label": _("Actual"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "committed", "label": _("Committed"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "forecast", "label": _("Forecast"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "remaining", "label": _("Remaining"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "utilisation", "label": _("Used %"), "fieldtype": "Percent", "width": 90},
        {"fieldname": "variance", "label": _("Budget less Forecast"), "fieldtype": "Currency", "width": 150},
    ]
    return columns, data, None, chart(data), summary(data)


def chart(data):
    shown = data[:12]
    if not shown:
        return None
    return {"type": "bar", "colors": ["#B8C2CF", "#14395E", "#E8A317"], "height": 260,
            "data": {"labels": [str(row["group"])[:24] for row in shown],
                     "datasets": [{"name": _("Budget"), "values": [row["budget"] for row in shown]},
                                  {"name": _("Actual"), "values": [row["actual"] for row in shown]},
                                  {"name": _("Forecast"), "values": [row["forecast"] for row in shown]}]}}


def summary(data):
    budget = sum(row["budget"] for row in data)
    used = sum(row["actual"] + row["committed"] for row in data)
    return [
        {"value": budget, "label": _("Budget"), "datatype": "Currency"},
        {"value": sum(row["actual"] for row in data), "label": _("Actual"), "datatype": "Currency"},
        {"value": sum(row["forecast"] for row in data), "label": _("Forecast"), "datatype": "Currency"},
        {"value": round(100.0 * used / budget, 1) if budget else 0, "label": _("Used %"), "datatype": "Percent"},
    ]
