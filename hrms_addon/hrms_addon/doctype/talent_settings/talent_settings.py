# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent Settings (talent blueprint, section 3)."""

from frappe.model.document import Document


class TalentSettings(Document):
    def validate(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.settings_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.master_on_update(self)
