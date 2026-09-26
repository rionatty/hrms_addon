# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A criterion on the Candidate Interview Evaluation / Score Form (LPL/HR/17).

A score sheet on a round with no list of its own starts with the criteria
that are not disabled, in their group's order and then their own
(hrms_addon/hrms_addon/interview_rules.py sheet_rows). Seeded once with the
form's criteria; HR's to change after that, except that health, looks and
personal traits cannot be switched on (interview_rules.PROTECTED_CRITERIA).
"""

import frappe
from frappe import _
from frappe.model.document import Document

from hrms_addon.hrms_addon import interview_rules, jd_rules


class InterviewCriterion(Document):
    def validate(self):
        errors = interview_rules.criterion_errors(self.criterion_name or self.name, self.disabled)
        if errors:
            frappe.throw("<br>".join(_(message) for message in errors), title=_("Interview Criterion"))

    def before_insert(self):
        # a criterion added without a Display Order goes after the others
        if not self.sort_order:
            self.sort_order = jd_rules.next_display_order(frappe.get_all("Interview Criterion", pluck="sort_order"))
