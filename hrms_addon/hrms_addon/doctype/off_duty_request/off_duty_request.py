# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LPL/HR/25: an employee's request for a day off."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance


class OffDutyRequest(Document):
    def validate(self):
        attendance.off_duty_validate(self)

    def on_submit(self):
        attendance.off_duty_on_submit(self)

    def on_cancel(self):
        attendance.off_duty_on_cancel(self)
