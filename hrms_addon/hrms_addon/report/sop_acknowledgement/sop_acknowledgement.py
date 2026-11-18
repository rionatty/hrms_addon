# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""SOP Acknowledgement (the brief's section 17): each plant, section or piece
of content, how many it was assigned to, how many have read and acknowledged
the version they hold, how many are still to and how many of those are late.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import learning_library


def execute(filters=None):
    filters = frappe._dict(filters or {})
    label = filters.get("group_by") or "Plant"
    data = learning_library.acknowledgement(filters)
    for row in data:
        row["group"] = row["group"] or _("Not Set")
    columns = [
        {"fieldname": "group", "label": _(label), "fieldtype": "Data", "width": 200},
        {"fieldname": "assigned", "label": _("Assigned"), "fieldtype": "Int", "width": 90},
        {"fieldname": "done", "label": _("Acknowledged"), "fieldtype": "Int", "width": 110},
        {"fieldname": "pending", "label": _("Still To"), "fieldtype": "Int", "width": 90},
        {"fieldname": "overdue", "label": _("Late"), "fieldtype": "Int", "width": 70},
        {"fieldname": "share", "label": _("Acknowledged %"), "fieldtype": "Percent", "width": 120},
    ]
    return columns, data
