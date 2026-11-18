# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One rater's view of one placement's potential."""

from frappe.model.document import Document


class PotentialAssessment(Document):
    def validate(self):
        from hrms_addon.hrms_addon import potential

        potential.assessment_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import potential

        potential.assessment_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import potential

        potential.assessment_on_cancel(self)
