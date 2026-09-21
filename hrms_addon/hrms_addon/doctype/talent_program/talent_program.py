# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's talent development programme, and its review."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class TalentProgram(Document):
    def validate(self):
        talent.program_validate(self)

    def on_submit(self):
        talent.program_on_submit(self)

    def on_cancel(self):
        talent.program_on_cancel(self)
