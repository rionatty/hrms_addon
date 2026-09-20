# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A staff loan, recovered from the payroll (LPL/HR/39)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import loans


class EmployeeLoan(Document):
    def validate(self):
        loans.loan_validate(self)

    def on_submit(self):
        loans.loan_on_submit(self)

    def on_cancel(self):
        loans.loan_on_cancel(self)
