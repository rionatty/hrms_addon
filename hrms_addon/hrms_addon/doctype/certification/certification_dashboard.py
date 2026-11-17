# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Certification: who holds it, and the rules that require it."""

from frappe import _


def get_data():
    return {
        "fieldname": "certification",
        "transactions": [{"label": _("Held and Required"), "items": ["Employee Certification", "Training Rule"]}],
    }
