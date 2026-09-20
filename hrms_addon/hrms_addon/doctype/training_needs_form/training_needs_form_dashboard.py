# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Connections of a Training Needs Form: the requisition that took it up."""


def get_data():
    return {
        "fieldname": "needs_form",
        "internal_links": {"Training Requisition": "requisition"},
        "transactions": [{"label": "Taken Up By", "items": ["Training Requisition"]}],
    }
