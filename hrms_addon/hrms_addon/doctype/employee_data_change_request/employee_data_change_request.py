# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""LPL/HR/34 and LPL/HR/33: a request to change where the pay goes."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import employee_data


class EmployeeDataChangeRequest(Document):
    def validate(self):
        employee_data.request_validate(self)

    def on_submit(self):
        employee_data.request_on_submit(self)

    def on_cancel(self):
        employee_data.request_on_cancel(self)
