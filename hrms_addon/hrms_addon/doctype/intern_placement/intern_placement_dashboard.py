# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Intern Placement: the supervisor the intern reports to."""


def get_data():
    return {
        "fieldname": "intern_placement",
        "internal_links": {"Employee": "supervisor"},
        "transactions": [
            {"label": "Supervision", "items": ["Employee"]},
        ],
    }
