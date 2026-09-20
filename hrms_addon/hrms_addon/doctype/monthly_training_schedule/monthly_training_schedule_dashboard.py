# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Monthly Training Schedule: the calendar it came from
and the sessions it booked."""


def get_data():
    return {
        "fieldname": "custom_schedule",
        "internal_links": {"Training Calendar": "training_calendar", "Training Event": ["lines", "training_event"]},
        "transactions": [
            {"label": "From", "items": ["Training Calendar"]},
            {"label": "Sessions Booked", "items": ["Training Event"]},
        ],
    }
