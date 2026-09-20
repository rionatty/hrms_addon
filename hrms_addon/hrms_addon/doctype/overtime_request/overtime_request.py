# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LPL/HR/14: a request for overtime and the coupons that follow it."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance


class OvertimeRequest(Document):
    def validate(self):
        attendance.overtime_validate(self)

    def on_submit(self):
        attendance.overtime_on_submit(self)

    def on_cancel(self):
        attendance.overtime_on_cancel(self)
