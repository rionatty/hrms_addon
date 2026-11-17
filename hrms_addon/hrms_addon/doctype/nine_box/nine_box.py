# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A cell of the nine-box grid (talent blueprint, section 4)."""

from frappe.model.document import Document


class NineBox(Document):
    def validate(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.box_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.master_on_update(self)
