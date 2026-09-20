# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A gate pass: leaving the premises before the hours are done."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance


class GatePass(Document):
    def validate(self):
        attendance.gate_pass_validate(self)

    def on_submit(self):
        attendance.gate_pass_on_submit(self)

    def on_cancel(self):
        attendance.gate_pass_on_cancel(self)
