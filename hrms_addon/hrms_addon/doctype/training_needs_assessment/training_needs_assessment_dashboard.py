# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Training Needs Assessment: the requisitions it took
up and the calendar it was consolidated into."""


def get_data():
    return {
        "fieldname": "assessment",
        "internal_links": {"Training Requisition": ["requisitions", "requisition"], "Training Calendar": "calendar"},
        "transactions": [
            {"label": "Requisitions", "items": ["Training Requisition"]},
            {"label": "Consolidated Into", "items": ["Training Calendar"]},
        ],
    }
