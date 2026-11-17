# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A KPI before and after a training (LMS phase 3, 17 Nov 2026)."""

from frappe.model.document import Document


class TrainingImpactReview(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_delivery

        learning_delivery.impact_validate(self)
