# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One plant's casuals paid by the hour, for a week, approved by its General Manager before the weekly payroll
pays it (casual_hours.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import casual_hours


class CasualHoursSheet(Document):
    def validate(self):
        casual_hours.sheet_validate(self)

    def before_submit(self):
        casual_hours.sheet_before_submit(self)

    def before_cancel(self):
        casual_hours.sheet_before_cancel(self)

    def on_cancel(self):
        casual_hours.sheet_on_cancel(self)
