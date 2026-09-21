# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The shift allowance an employee earned in a cycle."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import shifts


class ShiftAllowance(Document):
    def validate(self):
        shifts.allowance_validate(self)

    def on_submit(self):
        shifts.allowance_on_submit(self)

    def on_cancel(self):
        shifts.allowance_on_cancel(self)
