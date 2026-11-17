# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A certificate an employee may hold (LMS blueprint section 2): who issues it and how long it lasts."""

from frappe.model.document import Document


class Certification(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning

        learning.certification_validate(self)
