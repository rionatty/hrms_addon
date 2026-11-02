# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Attendance Deletion: a month of attendance deleted without slowing the site (attendance_deletions.py)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance_deletions


class AttendanceDeletion(Document):
    def onload(self):
        attendance_deletions.deletion_onload(self)

    def validate(self):
        attendance_deletions.deletion_validate(self)

    def on_trash(self):
        attendance_deletions.deletion_on_trash(self)


def on_doctype_update():
    attendance_deletions.add_indexes()
