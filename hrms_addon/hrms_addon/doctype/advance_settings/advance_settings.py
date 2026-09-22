# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's rules for the three advances, as settings."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import advances


class AdvanceSettings(Document):
    def validate(self):
        advances.settings_validate(self)
