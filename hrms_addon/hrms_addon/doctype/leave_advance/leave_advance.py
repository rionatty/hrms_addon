# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Advance: part of the salary paid ahead of an approved leave and taken back from the payroll (minutes 4.4)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import leave_advances


class LeaveAdvance(Document):
    def validate(self):
        leave_advances.advance_validate(self)

    def before_update_after_submit(self):
        leave_advances.advance_before_update(self)

    def on_submit(self):
        leave_advances.advance_on_submit(self)

    def on_cancel(self):
        leave_advances.advance_on_cancel(self)
