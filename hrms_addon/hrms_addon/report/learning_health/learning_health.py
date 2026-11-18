# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Learning Health (the brief's HR Command Centre, section 27): the Learning
and Capability Health Score of the plants the user may see, the whole of
them first, from the brief's nine parts (mandatory compliance, certification
compliance, training coverage, competency coverage, attendance, assessment
performance, training effectiveness, budget utilisation and critical skills
coverage), each weighed in Learning Settings. Counted as the Learning Command
Centre counts (learning_centre.counts_by_unit).
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_centre, learning_centre_rules as rules, learning_rules

PART_LABELS = dict(zip(rules.PARTS, [label for _key, label in learning_rules.HEALTH_PARTS]))


def execute(filters=None):
    filters = frappe._dict(filters or {})
    plants = learning_centre.permitted_plants()
    if filters.get("branch"):
        if plants is not None and filters.branch not in plants:
            frappe.throw(_("Not permitted to see {0}.").format(filters.branch), frappe.PermissionError)
        plants = [filters.branch]
    units = learning_centre.counts_by_unit(filters.get("company"), filters.get("month"), plants)
    weights = learning_centre._weights()
    by_plant, whole = {}, rules.blank()
    for (branch, _department), counts in units.items():
        rules.add(by_plant.setdefault(branch, rules.blank()), counts)
        rules.add(whole, counts)
    rows = [_row(_("All Plants"), whole, weights)] if len(by_plant) > 1 or not filters.get("branch") else []
    rows += [_row(branch or _("No Plant"), counts, weights) for branch, counts in sorted(by_plant.items())]
    columns = [{"fieldname": "plant", "label": _("Plant"), "fieldtype": "Data", "width": 150},
               {"fieldname": "score", "label": _("Health"), "fieldtype": "Float", "precision": 1, "width": 90},
               {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100}]
    columns += [{"fieldname": key, "label": _(PART_LABELS[key]), "fieldtype": "Percent", "width": 130}
                for key in rules.PARTS]
    return columns, rows, None, chart(rows)


def _row(label, counts, weights):
    from hrms_addon.hrms_addon import learning

    s = learning.settings()
    parts = rules.parts_of(counts)
    score, status = rules.health(parts, weights, s["matrix_green_from"], s["matrix_amber_from"])
    return dict(parts, plant=label, score=score, status=status)


def chart(rows):
    have = [row for row in rows if row["score"] is not None]
    if not have:
        return None
    return {"data": {"labels": [row["plant"] for row in have],
                     "datasets": [{"name": _("Health"), "values": [row["score"] for row in have]}]},
            "type": "bar", "colors": ["#1F3864"]}
