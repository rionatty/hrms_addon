# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One planned leave moved to new dates, approved by the supervisor and the
HOD (leave_plan_change_approval.py). The glue is in leave.py."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import leave


class LeavePlanChange(Document):
    def validate(self):
        leave.change_validate(self)

    def on_submit(self):
        leave.change_on_submit(self)

    def on_cancel(self):
        leave.change_on_cancel(self)
