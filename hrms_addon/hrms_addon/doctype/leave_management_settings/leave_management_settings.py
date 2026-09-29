# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Management Settings: how leave is earned and allocated, and the leave advance rules."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import leave_accrual


class LeaveManagementSettings(Document):
    def validate(self):
        leave_accrual.settings_validate(self)
