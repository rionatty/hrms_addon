# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A round of nine-box talent reviews."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class TalentReview(Document):
    def validate(self):
        talent.review_validate(self)
