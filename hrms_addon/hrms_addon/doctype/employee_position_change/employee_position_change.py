# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Candidate Preamble Promotion Form and the letter it ends in: a promotion, a change of designation or a salary review."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import positions


class EmployeePositionChange(Document):
    def validate(self):
        positions.change_validate(self)

    def on_submit(self):
        positions.change_on_submit(self)

    def on_cancel(self):
        positions.change_on_cancel(self)
