# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A session's trainees, their pre and post tests (level 2); submitted, the attempt that counts for each goes to
Frappe HR's Training Result in the background (learning_sheets.py)."""

from frappe.model.document import Document


class TrainingResultsSheet(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.results_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_cancel(self)
