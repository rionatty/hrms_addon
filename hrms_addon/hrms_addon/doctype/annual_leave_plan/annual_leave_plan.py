# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Annual Leave Plan: who takes leave when, for the year coming."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import leave


class AnnualLeavePlan(Document):
    def validate(self):
        leave.plan_validate(self)

    def on_submit(self):
        leave.plan_on_submit(self)

    def on_cancel(self):
        leave.plan_on_cancel(self)
