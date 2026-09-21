# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A travel destination and the currency its allowance is paid in."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import grades


class TravelDestination(Document):
    def validate(self):
        grades.destination_validate(self)
