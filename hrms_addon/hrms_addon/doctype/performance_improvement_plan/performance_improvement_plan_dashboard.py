# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Performance Improvement Plan: whose it is, and the
appraisal it follows from."""


def get_data():
    return {
        "fieldname": "improvement_plan",
        "internal_links": {"Employee": "employee", "Appraisal": "appraisal",
                           "Performance Review": "performance_review"},
        "transactions": [
            {"label": "Whose Plan", "items": ["Employee"]},
            {"label": "Where It Came From", "items": ["Appraisal", "Performance Review"]},
        ],
    }
