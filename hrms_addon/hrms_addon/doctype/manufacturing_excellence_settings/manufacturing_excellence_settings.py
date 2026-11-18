# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Manufacturing Excellence Settings: weights, bands, targets, limits, and the guide."""

from frappe.model.document import Document


class ManufacturingExcellenceSettings(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.settings_validate(self)
