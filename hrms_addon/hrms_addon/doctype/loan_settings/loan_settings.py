# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's rules for staff loans, as settings."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import loans


class LoanSettings(Document):
    def validate(self):
        loans.settings_validate(self)
