# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's word, before the shift, that they will be late."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import attendance


class LateArrivalNotice(Document):
    def validate(self):
        attendance.late_notice_validate(self)

    def on_submit(self):
        attendance.late_notice_on_submit(self)

    def on_cancel(self):
        attendance.late_notice_on_cancel(self)
