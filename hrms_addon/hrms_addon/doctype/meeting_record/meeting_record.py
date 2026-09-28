# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Meeting Record: a meeting and who attended it, for the Meeting Attendance Form (LPL/HR/33)."""

from frappe import _
from frappe.model.document import Document


class MeetingRecord(Document):
    def validate(self):
        from hrms_addon.hrms_addon import training

        training._twice_or_throw(self.get("participants"), _("Participants"))
