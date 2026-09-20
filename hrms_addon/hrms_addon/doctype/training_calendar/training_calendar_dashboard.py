# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Training Calendar: the assessments behind it and the
monthly schedules drawn from it."""


def get_data():
    return {
        "fieldname": "training_calendar",
        "internal_links": {"Training Needs Assessment": ["entries", "assessment"]},
        "transactions": [
            {"label": "Drawn From", "items": ["Training Needs Assessment"]},
            {"label": "Scheduled As", "items": ["Monthly Training Schedule"]},
        ],
    }
