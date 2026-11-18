# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A section's shift: its crew from the clock, downtime events, output by order, and its score. Submitted with its plant's day sheet, or by itself once checked."""

from frappe.model.document import Document


class ShiftReport(Document):
    def validate(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_on_update(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_on_cancel(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import excellence

        excellence.shift_on_trash(self)
