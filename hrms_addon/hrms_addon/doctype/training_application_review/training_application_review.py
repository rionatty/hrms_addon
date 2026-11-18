# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How a trainee applies a training, as their supervisor sees it (LMS phase 3, 17 Nov 2026)."""

from frappe.model.document import Document


class TrainingApplicationReview(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_delivery

        learning_delivery.review_validate(self)


def on_doctype_update():
    """The composite indexes it is looked up by (learning.INDEXES)."""
    from hrms_addon.hrms_addon import learning

    learning.add_indexes("Training Application Review")
