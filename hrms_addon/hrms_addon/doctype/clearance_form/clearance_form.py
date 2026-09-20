# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Clearance Form (LPL/HR/22): the ten boxes an employee is cleared through."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import exits


class ClearanceForm(Document):
    def validate(self):
        exits.clearance_validate(self)

    def on_submit(self):
        exits.clearance_on_submit(self)

    def on_cancel(self):
        exits.clearance_on_cancel(self)
