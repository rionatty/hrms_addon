# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A rotation supervisor's assessment of a trainee's stint."""

from frappe.model.document import Document


class RotationAssessment(Document):
    def validate(self):
        from hrms_addon.hrms_addon import graduates

        graduates.rotation_assessment_validate(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import graduates

        graduates.rotation_assessment_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import graduates

        graduates.rotation_assessment_on_cancel(self)
