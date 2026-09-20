# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Needs Form: the individual questionnaire (LPL/TRG/FRM06) an employee fills in, or HR keys in from paper; the Head of Department takes them into a Training Requisition.

The logic lives in hrms_addon/hrms_addon/training.py (rules in the tested
training_rules.py and the *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import training


class TrainingNeedsForm(Document):
    def validate(self):
        training.needs_form_validate(self)

    def on_submit(self):
        training.needs_form_on_submit(self)

    def on_cancel(self):
        training.needs_form_on_cancel(self)
