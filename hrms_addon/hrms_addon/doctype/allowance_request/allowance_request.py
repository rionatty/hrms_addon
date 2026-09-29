# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's request for an allowance, LPL.HR.31 and the minutes' others (allowances.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import allowances


class AllowanceRequest(Document):
    def validate(self):
        allowances.request_validate(self)

    def on_submit(self):
        allowances.request_on_submit(self)

    def on_cancel(self):
        allowances.request_on_cancel(self)
