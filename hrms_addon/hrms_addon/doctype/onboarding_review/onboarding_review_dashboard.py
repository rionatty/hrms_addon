# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Onboarding Review: the employee and the onboarding it
belongs to."""


def get_data():
    return {
        "fieldname": "employee",
        "internal_links": {"Employee": "employee", "Employee Onboarding": "onboarding"},
        "transactions": [{"label": "Where It Came From", "items": ["Employee", "Employee Onboarding"]}],
    }
