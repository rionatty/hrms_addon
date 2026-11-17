# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Category: the requirements and certifications in it."""

from frappe import _


def get_data():
    return {
        "fieldname": "training_category",
        "transactions": [{"label": _("In This Category"), "items": ["Employee Training Requirement", "Certification"]}],
    }
