# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A signature given on a document."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import signatures


class SignatureLog(Document):
    def validate(self):
        signatures.log_validate(self)
