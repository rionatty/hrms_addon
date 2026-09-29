# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A kind of allowance: how it is worked out and who pays it (allowances.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import allowances


class AllowanceType(Document):
    def validate(self):
        allowances.type_validate(self)
