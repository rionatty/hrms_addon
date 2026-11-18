# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A calibration move, written once and never changed."""

from frappe.model.document import Document


class TalentCalibrationLog(Document):
    def validate(self):
        from hrms_addon.hrms_addon import calibration

        calibration.log_validate(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import calibration

        calibration.log_on_trash(self)
