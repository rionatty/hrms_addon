# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee suspended from duty, and the letter that tells them (Disciplinary Grievancy, test case 6)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import suspensions


class EmployeeSuspension(Document):
    def validate(self):
        suspensions.suspension_validate(self)

    def on_submit(self):
        suspensions.suspension_on_submit(self)

    def on_cancel(self):
        suspensions.suspension_on_cancel(self)
