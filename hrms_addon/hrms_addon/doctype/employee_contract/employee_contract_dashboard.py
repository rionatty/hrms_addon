# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Employee Contract: the contract that renews it (the
chain runs the other way through Renewal Of), the employee it is for and the
onboarding it was drafted by."""


def get_data():
    return {
        "fieldname": "renewal_of",
        "internal_links": {"Employee": "employee", "Employee Onboarding": "onboarding"},
        "transactions": [
            {"label": "Renewal", "items": ["Employee Contract"]},
            {"label": "Where It Came From", "items": ["Employee", "Employee Onboarding"]},
        ],
    }
