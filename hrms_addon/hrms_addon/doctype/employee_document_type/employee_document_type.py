# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A kind of document an employee has to hold."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import documents


class EmployeeDocumentType(Document):
    def validate(self):
        documents.type_validate(self)
