# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A section's shift on its plant's day sheet."""

from frappe.model.document import Document


class PlantDaySheetRow(Document):
    pass


def on_doctype_update():
    """One row a section and shift on a sheet, held by the database too."""
    from hrms_addon.hrms_addon import excellence_sheet

    excellence_sheet.add_keys()
