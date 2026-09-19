# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Settings for probation, contract alerts and letters.

The logic lives in hrms_addon/hrms_addon/probation.py (rules in the tested *_rules.py
and *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import probation


class OnboardingSettings(Document):
    def validate(self):
        probation.validate_settings(self)
