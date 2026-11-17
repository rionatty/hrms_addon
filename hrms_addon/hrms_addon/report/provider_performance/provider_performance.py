# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Provider Performance: each training provider (the Supplier on the session,
else in-house) ranked by its benefit score, then by its cost per trainee.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_value, learning_value_rules as rules

VALUE_COLUMNS = [
    {"fieldname": "sessions", "label": _("Sessions"), "fieldtype": "Int", "width": 80},
    {"fieldname": "trainees", "label": _("Trainees"), "fieldtype": "Int", "width": 80},
    {"fieldname": "reaction", "label": _("Reaction %"), "fieldtype": "Percent", "width": 90},
    {"fieldname": "pass_rate", "label": _("Pass Rate %"), "fieldtype": "Percent", "width": 90},
    {"fieldname": "application", "label": _("Application %"), "fieldtype": "Percent", "width": 100},
    {"fieldname": "kpi_share", "label": _("KPIs Improved %"), "fieldtype": "Percent", "width": 110},
    {"fieldname": "score", "label": _("Benefit Score"), "fieldtype": "Float", "precision": 1, "width": 100},
    {"fieldname": "direct", "label": _("Direct Cost"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "time", "label": _("Trainees' Time"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "total", "label": _("Total Cost"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "per_trainee", "label": _("Cost per Trainee"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "benefit", "label": _("Benefit"), "fieldtype": "Currency", "width": 120},
    {"fieldname": "roi", "label": _("ROI %"), "fieldtype": "Percent", "width": 90},
]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    events = learning_value.sessions_in(filters)
    found = learning_value.value_by(events, lambda event: event.supplier or _("In-House"))
    data = rules.rank_providers([dict(row, provider=provider) for provider, row in found.items()])
    for rank, row in enumerate(data, 1):
        row["rank"] = rank
    columns = [{"fieldname": "rank", "label": _("Rank"), "fieldtype": "Int", "width": 60},
               {"fieldname": "provider", "label": _("Provider"), "fieldtype": "Data", "width": 200}]
    return columns + VALUE_COLUMNS, data
