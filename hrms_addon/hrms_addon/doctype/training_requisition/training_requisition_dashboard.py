# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Training Requisition: the forms it took up, the
assessment that took it up, and the session booked for it."""


def get_data():
    return {
        "fieldname": "requisition",
        "internal_links": {
            "Training Needs Form": ["target_employees", "needs_form"],
            "Training Needs Assessment": "assessment",
            "Training Event": "training_event",
        },
        "transactions": [
            {"label": "The Employees' Forms", "items": ["Training Needs Form"]},
            {"label": "What Followed", "items": ["Training Needs Assessment", "Training Event"]},
        ],
    }
