# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A year's training budget and its use (LMS phase 5, 17 Nov 2026)."""

from frappe.model.document import Document


class TrainingBudget(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import learning_value

        learning_value.budget_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import learning_value

        learning_value.budget_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import learning_value

        learning_value.budget_on_update(self)
