# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How the Learning module counts and chases (LMS blueprint section 5)."""

from frappe.model.document import Document


class LearningSettings(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning

        learning.settings_validate(self)
