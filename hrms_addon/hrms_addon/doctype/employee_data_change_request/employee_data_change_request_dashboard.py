# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Employee Data Change Request: whose record it changes."""


def get_data():
    return {
        "fieldname": "employee_data_change_request",
        "internal_links": {"Employee": "employee"},
        "transactions": [
            {"label": "Whose Record", "items": ["Employee"]},
        ],
    }
