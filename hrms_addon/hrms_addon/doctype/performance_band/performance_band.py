# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A performance band of the nine-box grid (talent blueprint, section 3)."""

from frappe.model.document import Document


class PerformanceBand(Document):
    def validate(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.band_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.band_on_update(self)
