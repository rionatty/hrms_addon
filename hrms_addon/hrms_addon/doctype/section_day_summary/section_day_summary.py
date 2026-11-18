# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What one submitted shift adds to its section's day. Written by the system."""

from frappe.model.document import Document


class SectionDaySummary(Document):
    pass


def on_doctype_update():
    from hrms_addon.hrms_addon import excellence_summary

    excellence_summary.add_indexes()
