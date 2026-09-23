# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's standing request for a monthly salary advance."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import salary_advances


class SalaryAdvanceRequest(Document):
    def validate(self):
        salary_advances.request_validate(self)

    def on_submit(self):
        salary_advances.request_on_submit(self)

    def on_cancel(self):
        salary_advances.request_on_cancel(self)
