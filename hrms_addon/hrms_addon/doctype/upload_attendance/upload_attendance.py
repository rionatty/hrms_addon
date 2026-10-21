# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Upload Attendance: a month of attendance from one sheet (attendance_upload.py)."""

import frappe
from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance_upload


class UploadAttendance(Document):
    def onload(self):
        attendance_upload.upload_onload(self)

    def validate(self):
        attendance_upload.upload_validate(self)

    def on_trash(self):
        attendance_upload.upload_on_trash(self)

    @frappe.whitelist()
    def start_import(self):
        return attendance_upload.start_import(self)
