# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One calibration sitting over a plant's or a department's placements."""

from frappe.model.document import Document


class CalibrationSession(Document):
    def validate(self):
        from hrms_addon.hrms_addon import calibration

        calibration.session_validate(self)

    def before_submit(self):
        from hrms_addon.hrms_addon import calibration

        calibration.session_before_submit(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import calibration

        calibration.session_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import calibration

        calibration.session_on_cancel(self)
