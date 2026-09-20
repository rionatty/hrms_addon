# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Requisition: the Head of Department asks for training (topic, required skills, target employees); the branch HR Officer is told and takes it into a Training Needs Assessment.

The logic lives in hrms_addon/hrms_addon/training.py (rules in the tested
training_rules.py and the *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import training


class TrainingRequisition(Document):
    def validate(self):
        training.requisition_validate(self)

    def on_submit(self):
        training.requisition_on_submit(self)

    def on_cancel(self):
        training.requisition_on_cancel(self)
