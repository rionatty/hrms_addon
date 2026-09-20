# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A ZKTeco clocking machine (Manufacturing Excellence 4.2, Reward & Compensation 4.2)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import devices


class AttendanceDevice(Document):
    def validate(self):
        devices.device_validate(self)
