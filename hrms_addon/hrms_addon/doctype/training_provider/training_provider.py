# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A training provider: its people, expertise, accreditations and contracts, and its rating per session
(learning_providers.py)."""

from frappe.model.document import Document


class TrainingProvider(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_providers

        learning_providers.provider_validate(self)
