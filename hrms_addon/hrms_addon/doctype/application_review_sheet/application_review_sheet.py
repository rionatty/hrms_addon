# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A supervisor's trainees from one session: how each applies the training (level 3); submitted, each answer
goes to that trainee's Training Application Review in the background (learning_sheets.py)."""

from frappe.model.document import Document


class ApplicationReviewSheet(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.review_sheet_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_cancel(self)
