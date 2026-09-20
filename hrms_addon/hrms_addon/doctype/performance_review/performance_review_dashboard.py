# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Performance Review: the cycle it reports on, and what
its decisions raised."""


def get_data():
    return {
        "fieldname": "custom_performance_review",
        "internal_links": {"Appraisal Cycle": "appraisal_cycle", "Appraisal Plan": "plan"},
        "transactions": [
            {"label": "What It Reports On", "items": ["Appraisal Cycle", "Appraisal Plan"]},
            {"label": "What Was Decided", "items": ["Appraisal"]},
        ],
    }
