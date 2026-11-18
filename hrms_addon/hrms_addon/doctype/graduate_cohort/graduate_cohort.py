# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A graduate intake and its milestones."""

from frappe.model.document import Document


class GraduateCohort(Document):
    def validate(self):
        from hrms_addon.hrms_addon import graduates

        graduates.cohort_validate(self)
