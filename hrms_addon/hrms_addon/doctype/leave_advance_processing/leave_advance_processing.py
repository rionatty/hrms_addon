# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Advance Processing: the Payroll Officer's file of approved leave advances for Finance, and its bank entry."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import leave_advances


class LeaveAdvanceProcessing(Document):
    def validate(self):
        leave_advances.run_validate(self)

    def before_submit(self):
        leave_advances.run_before_submit(self)

    def on_submit(self):
        leave_advances.run_on_submit(self)

    def on_cancel(self):
        leave_advances.run_on_cancel(self)
