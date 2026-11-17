# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Rule: what it requires of each employee."""

from frappe import _


def get_data():
    return {
        "fieldname": "training_rule",
        "transactions": [{"label": _("Required"), "items": ["Employee Training Requirement"]}],
    }
