# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A graduate trainee from hire to confirmation."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import talent


class GraduateTraineeProgram(Document):
    def validate(self):
        talent.trainee_validate(self)

    def on_submit(self):
        talent.trainee_on_submit(self)

    def on_cancel(self):
        talent.trainee_on_cancel(self)
