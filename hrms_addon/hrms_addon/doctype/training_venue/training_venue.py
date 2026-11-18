# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A room or hall training is held in, with its seats (learning_attendance.py)."""

from frappe.model.document import Document


class TrainingVenue(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_attendance

        learning_attendance.venue_validate(self)
