# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One punch read off a ZKTeco machine, and what became of it."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import devices


class AttendanceDeviceLog(Document):
    def validate(self):
        devices.log_validate(self)
