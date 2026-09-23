# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A penalty for property lost or damaged, recovered from the payroll
(minutes §4.11, LPL/HR/39)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import penalties


class EmployeePenalty(Document):
    def validate(self):
        penalties.penalty_validate(self)

    def on_submit(self):
        penalties.penalty_on_submit(self)

    def on_cancel(self):
        penalties.penalty_on_cancel(self)
