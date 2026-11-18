# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How likely somebody is to leave, as assessed on a day."""

from frappe.model.document import Document


class FlightRiskAssessment(Document):
    def validate(self):
        from hrms_addon.hrms_addon import retention

        retention.assessment_validate(self)

    def after_insert(self):
        from hrms_addon.hrms_addon import retention

        retention.assessment_after_insert(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import retention

        retention.assessment_on_trash(self)
