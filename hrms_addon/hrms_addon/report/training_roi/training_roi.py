# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training ROI (LMS blueprint, section 4.10): each programme's sessions in the
period, what they cost (directly and in the trainees' time) and what they
brought: the benefit the impact reviews valued, the ROI where there is one,
and the benefit score from the four levels where there is not.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_value

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
    found = learning_value.value_by(events, lambda event: event.training_program or _("No Programme"))
    data = [dict(row, programme=programme) for programme, row in sorted(found.items())]
    columns = [{"fieldname": "programme", "label": _("Training Program"), "fieldtype": "Data", "width": 200}]
    return columns + VALUE_COLUMNS, data
