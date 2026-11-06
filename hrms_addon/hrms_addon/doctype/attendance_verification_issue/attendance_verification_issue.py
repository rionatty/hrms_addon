# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What stops a branch's Attendance Verification: a run of days nobody marked, or a request still on its way."""

from frappe.model.document import Document


class AttendanceVerificationIssue(Document):
    pass
