# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's signature, on file."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import signatures


class EmployeeSignature(Document):
    def validate(self):
        signatures.signature_validate(self)
