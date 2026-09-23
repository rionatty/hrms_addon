# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The month's salary advances, processed together."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import salary_advances


class SalaryAdvanceProcessing(Document):
    def validate(self):
        salary_advances.run_validate(self)

    def before_submit(self):
        salary_advances.run_before_submit(self)

    def on_submit(self):
        salary_advances.run_on_submit(self)

    def on_cancel(self):
        salary_advances.run_on_cancel(self)
