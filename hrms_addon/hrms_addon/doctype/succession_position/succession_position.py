# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A critical role and the bench behind it."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class SuccessionPosition(Document):
    def validate(self):
        talent.position_validate(self)

    def on_submit(self):
        talent.position_on_submit(self)

    def on_cancel(self):
        talent.position_on_cancel(self)
