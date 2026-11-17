# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's level in a skill against the level it needs (LMS phase 4, 17 Nov 2026)."""

from frappe.model.document import Document


class CompetencyAssessment(Document):
    def validate(self):
        from hrms_addon.hrms_addon import competency

        competency.assessment_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import competency

        competency.assessment_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import competency

        competency.assessment_on_trash(self)
