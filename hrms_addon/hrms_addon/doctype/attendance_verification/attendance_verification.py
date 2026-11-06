# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A branch's attendance for a payroll, signed off by its General Manager before payroll pays it
(attendance_verification.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance_verification


class AttendanceVerification(Document):
    def validate(self):
        attendance_verification.sheet_validate(self)

    def before_submit(self):
        attendance_verification.sheet_before_submit(self)

    def on_submit(self):
        attendance_verification.sheet_on_submit(self)

    def before_cancel(self):
        attendance_verification.sheet_before_cancel(self)

    def on_cancel(self):
        attendance_verification.sheet_on_cancel(self)
