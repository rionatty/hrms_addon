# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Something potential is rated on."""

from frappe.model.document import Document


class PotentialCriterion(Document):
    def validate(self):
        from hrms_addon.hrms_addon import potential

        potential.criterion_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import potential

        potential.criterion_on_update(self)
