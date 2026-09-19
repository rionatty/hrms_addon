# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Staff Onboarding Form (LPL/HR/04) at 30, 60 and 90 days.

The logic lives in hrms_addon/hrms_addon/reviews.py (rules in the tested *_rules.py
and *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import reviews


class OnboardingReview(Document):
    def validate(self):
        reviews.validate(self)
