# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Probation Evaluation: the evaluation an extension made,
and where this one came from."""


def get_data():
    return {
        "fieldname": "extension_of",
        "internal_links": {"Employee": "employee", "Employee Onboarding": "onboarding"},
        "transactions": [
            {"label": "Extension", "items": ["Probation Evaluation"]},
            {"label": "Where It Came From", "items": ["Employee", "Employee Onboarding"]},
        ],
    }
