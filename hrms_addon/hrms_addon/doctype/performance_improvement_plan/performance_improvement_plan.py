# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A Performance Improvement Plan: the agreement with an employee who scored below the pass mark (test case 7)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import pips


class PerformanceImprovementPlan(Document):
    def validate(self):
        pips.plan_validate(self)

    def on_submit(self):
        pips.plan_on_submit(self)

    def on_cancel(self):
        pips.plan_on_cancel(self)
