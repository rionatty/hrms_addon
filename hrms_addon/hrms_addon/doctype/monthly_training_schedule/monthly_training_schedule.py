# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Monthly Training Schedule: the month's trainings drawn from the calendar; submitting it books a Training Event for each and tells the HODs, trainers and trainees.

The logic lives in hrms_addon/hrms_addon/training.py (rules in the tested
training_rules.py and the *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import training


class MonthlyTrainingSchedule(Document):
    def validate(self):
        training.schedule_validate(self)

    def on_submit(self):
        training.schedule_on_submit(self)

    def on_cancel(self):
        training.schedule_on_cancel(self)
