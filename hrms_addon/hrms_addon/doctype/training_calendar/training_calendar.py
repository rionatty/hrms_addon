# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Training Calendar: the planner (LPL/TRAINING/01) drawn from the approved needs, approved by the General Manager, then the Board; a month before each training the HR Officer is reminded to schedule it.

The logic lives in hrms_addon/hrms_addon/training.py (rules in the tested
training_rules.py and the *_approval.py modules).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import training


class TrainingCalendar(Document):
    def validate(self):
        training.calendar_validate(self)

    def on_submit(self):
        training.calendar_on_submit(self)

    def on_cancel(self):
        training.calendar_on_cancel(self)
