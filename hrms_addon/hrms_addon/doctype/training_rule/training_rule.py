# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A mandatory, onboarding or refresher training, or a certificate to hold (LMS blueprint flows 4.1, 4.2,
4.7 and 4.9). Saving one brings everyone it applies to up to date in the background."""

from frappe.model.document import Document


class TrainingRule(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning

        learning.rule_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import learning

        learning.rule_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import learning

        learning.rule_on_trash(self)
