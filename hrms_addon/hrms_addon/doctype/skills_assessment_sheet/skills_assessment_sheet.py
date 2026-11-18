# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A section's people against its skills, a level each; submitted, each becomes or updates that employee's
Competency Assessment in the background (learning_sheets.py)."""

from frappe.model.document import Document


class SkillsAssessmentSheet(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.skills_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import learning_sheets

        learning_sheets.sheet_on_cancel(self)
