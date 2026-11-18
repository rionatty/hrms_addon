# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What losing a critical role's holder would cost."""

from frappe.model.document import Document


class CriticalityFactor(Document):
    def on_update(self):
        from hrms_addon.hrms_addon import succession_risk

        succession_risk.factor_on_update(self)
