# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The annual appraisal plan: the quarters, their windows and their deadlines (test case 1)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import appraisals


class AppraisalPlan(Document):
    def validate(self):
        appraisals.plan_validate(self)

    def on_submit(self):
        appraisals.plan_on_submit(self)

    def on_cancel(self):
        appraisals.plan_on_cancel(self)
