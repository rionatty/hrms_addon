# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The readiness scale of succession (talent blueprint, section 6)."""

from frappe.model.document import Document


class ReadinessLevel(Document):
    def validate(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.readiness_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import talent_masters

        talent_masters.master_on_update(self)
