# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The travel allowance a grade draws at a destination."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import grades


class PerDiemRate(Document):
    def validate(self):
        grades.rate_validate(self)
