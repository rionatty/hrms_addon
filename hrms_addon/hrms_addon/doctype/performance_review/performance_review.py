# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The appraisal report to top management and the decision it ends in (test cases 5, 6 and 10)."""

from frappe.model.document import Document

from hrms_addon.hrms_addon import appraisals


class PerformanceReview(Document):
    def validate(self):
        appraisals.review_validate(self)

    def on_submit(self):
        appraisals.review_on_submit(self)

    def on_cancel(self):
        appraisals.review_on_cancel(self)
