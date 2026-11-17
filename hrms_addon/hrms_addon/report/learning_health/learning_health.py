# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Learning Health (the blueprint's HR Command Centre): each plant's learning and
capability health over the last twelve months, from required training done,
certificates valid, attendance, the trainees' reaction, how they apply it,
competency and critical skills covered; the whole company first.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_value, learning_value_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    found = learning_value.health_by_plant(filters)
    columns = [{"fieldname": "plant", "label": _("Plant"), "fieldtype": "Data", "width": 150},
               {"fieldname": "score", "label": _("Health"), "fieldtype": "Float", "precision": 1, "width": 90},
               {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100}]
    columns += [{"fieldname": key, "label": _(label), "fieldtype": "Percent", "width": 130}
                for key, label in rules.HEALTH_PARTS]
    return columns, found, None, chart(found)


def chart(rows):
    have = [row for row in rows if row["score"] is not None]
    if not have:
        return None
    return {"data": {"labels": [row["plant"] for row in have],
                     "datasets": [{"name": _("Health"), "values": [row["score"] for row in have]}]},
            "type": "bar", "colors": ["#1F3864"]}
