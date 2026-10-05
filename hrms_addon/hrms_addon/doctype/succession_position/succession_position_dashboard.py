# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a succession plan: the development plans drawn up for its
successors, its holder's exit, and what fills the role when they go: the
promotion drafted for a successor, or the requisition for a replacement and
the opening it became."""


def get_data():
    return {
        "fieldname": "succession_position",
        "non_standard_fieldnames": {
            "Job Requisition": "custom_succession_position",
            "Employee Separation": "custom_succession_position",
        },
        "internal_links": {"Job Opening": "job_opening"},
        "transactions": [
            {"label": "Successors", "items": ["Talent Program", "Graduate Trainee Program"]},
            {"label": "Holder's Exit", "items": ["Employee Separation"]},
            {"label": "Filling the Role", "items": ["Employee Position Change", "Job Requisition", "Job Opening"]},
        ],
    }
