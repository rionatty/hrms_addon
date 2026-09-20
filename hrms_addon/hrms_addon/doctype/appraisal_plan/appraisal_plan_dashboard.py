# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of an Appraisal Plan: the cycles its quarters opened and the
appraisals raised under it."""


def get_data():
    return {
        "fieldname": "custom_plan",
        "transactions": [
            {"label": "The Round", "items": ["Appraisal Cycle", "Appraisal"]},
        ],
    }
