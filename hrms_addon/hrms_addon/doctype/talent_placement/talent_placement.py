# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One employee's nine-box placement."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class TalentPlacement(Document):
    def validate(self):
        talent.placement_validate(self)

    def on_submit(self):
        talent.placement_on_submit(self)

    def on_cancel(self):
        talent.placement_on_cancel(self)
