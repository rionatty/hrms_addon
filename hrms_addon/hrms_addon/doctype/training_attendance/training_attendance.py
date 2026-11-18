# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's attendance at a session on one of its days (learning_attendance.py)."""

from frappe.model.document import Document


class TrainingAttendance(Document):
    def validate(self):
        from hrms_addon.hrms_addon import learning_attendance

        learning_attendance.attendance_validate(self)

    def on_update(self):
        from hrms_addon.hrms_addon import learning_attendance

        learning_attendance.attendance_on_update(self)

    def on_trash(self):
        from hrms_addon.hrms_addon import learning_attendance

        learning_attendance.attendance_on_trash(self)


def on_doctype_update():
    """Looked up by session and day, plant and day; one row per employee per session per day."""
    from hrms_addon.hrms_addon import learning

    learning.add_indexes("Training Attendance")
