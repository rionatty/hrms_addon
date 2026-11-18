# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One plant's day: a row for each section and shift, the people from the clock, one approval."""

from frappe.model.document import Document


class PlantDaySheet(Document):
    def autoname(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_autoname(self)

    def validate(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_on_update(self)

    def before_submit(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_before_submit(self)

    def on_submit(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_on_submit(self)

    def on_cancel(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_on_cancel(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import excellence_sheet

        excellence_sheet.sheet_on_trash(self)
