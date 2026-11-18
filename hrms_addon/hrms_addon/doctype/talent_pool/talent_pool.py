# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A pool of people grown for a kind of role."""

from frappe.model.document import Document


class TalentPool(Document):
    def validate(self):
        from hrms_addon.hrms_addon import talent_pools

        talent_pools.pool_validate(self)
