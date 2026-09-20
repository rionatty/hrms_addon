# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Needs Assessment: the HR Officer's consolidation of the requisitions into needs with objectives and methods, approved by the HR Manager then the General Manager.

The logic lives in hrms_addon/hrms_addon/training.py (rules in the tested
training_rules.py and the *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import training


class TrainingNeedsAssessment(Document):
    def validate(self):
        training.assessment_validate(self)

    def on_submit(self):
        training.assessment_on_submit(self)

    def on_cancel(self):
        training.assessment_on_cancel(self)
