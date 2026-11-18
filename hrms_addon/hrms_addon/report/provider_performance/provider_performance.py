# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Provider Performance (the brief's section 12): the training providers ranked
on cost, quality, participant feedback, learning outcomes and business impact,
each weighed in Learning Settings, over the sessions each gave in the period
(their rating rows on Training Provider); with what they cost, how their last
sessions compare with those before, and their accreditations.
"""

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from hrms_addon.hrms_addon import learning_providers, learning_providers_rules as rules

COLUMNS = [
    {"fieldname": "rank", "label": _("Rank"), "fieldtype": "Int", "width": 60},
    {"fieldname": "provider", "label": _("Provider"), "fieldtype": "Link", "options": "Training Provider", "width": 190},
    {"fieldname": "provider_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
    {"fieldname": "score", "label": _("Score"), "fieldtype": "Float", "precision": 1, "width": 80},
    {"fieldname": "cost_score", "label": _("Cost"), "fieldtype": "Float", "precision": 1, "width": 75},
    {"fieldname": "quality_score", "label": _("Quality"), "fieldtype": "Float", "precision": 1, "width": 80},
    {"fieldname": "feedback_score", "label": _("Feedback"), "fieldtype": "Float", "precision": 1, "width": 85},
    {"fieldname": "learning_score", "label": _("Learning"), "fieldtype": "Float", "precision": 1, "width": 85},
    {"fieldname": "impact_score", "label": _("Impact"), "fieldtype": "Float", "precision": 1, "width": 80},
    {"fieldname": "trend", "label": _("Trend"), "fieldtype": "Float", "precision": 1, "width": 75},
    {"fieldname": "sessions", "label": _("Sessions"), "fieldtype": "Int", "width": 80},
    {"fieldname": "trainees", "label": _("Trainees"), "fieldtype": "Int", "width": 80},
    {"fieldname": "spend", "label": _("Spend"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "cost_per_trainee", "label": _("Cost per Trainee"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "accreditation", "label": _("Accreditation"), "fieldtype": "Data", "width": 110},
]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    since = getdate(filters.get("from_date") or add_months(today(), -12))
    until = getdate(filters.get("to_date") or today())
    found = learning_providers.figures_by_provider(since, until)
    names = frappe.get_list("Training Provider", filters={"name": ["in", list(found) or [""]]},
                            fields=["name", "provider_type"], limit_page_length=0)
    kinds = {row.name: row.provider_type for row in names}
    found = {name: figures for name, figures in found.items() if name in kinds}
    data = rules.rank(found, learning_providers.settings_weights())
    standing = {}
    for row in frappe.get_all("Training Provider Accreditation",
                              filters={"parenttype": "Training Provider", "parent": ["in", list(found) or [""]]},
                              fields=["parent", "expiry_date"], limit_page_length=0):
        status = rules.expiry_status(row.expiry_date, today())
        order = rules.EXPIRY_STATUSES.index(status)
        if row.parent not in standing or order > rules.EXPIRY_STATUSES.index(standing[row.parent]):
            standing[row.parent] = status
    for row in data:
        row["provider_type"] = kinds.get(row["provider"])
        row["accreditation"] = _(standing.get(row["provider"], "")) if standing.get(row["provider"]) else ""
    return COLUMNS, data, None, chart(data)


def chart(data):
    shown = [row for row in data if row["score"] is not None][:10]
    if not shown:
        return None
    return {"type": "bar", "colors": ["#14395E"], "height": 240,
            "data": {"labels": [row["provider"][:24] for row in shown],
                     "datasets": [{"name": _("Score"), "values": [row["score"] for row in shown]}]}}
