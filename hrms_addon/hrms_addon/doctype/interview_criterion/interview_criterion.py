# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A criterion on the Candidate Interview Evaluation / Score Form (LPL/HR/17).

Every score sheet a panel member opens starts with the criteria that are not
disabled, in their group's order and then their own
(hrms_addon/hrms_addon/interview_rules.py sheet_rows). Seeded once with the
form's 17 criteria; HR's to change after that.
"""

import frappe
from frappe.model.document import Document

from hrms_addon.hrms_addon import jd_rules


class InterviewCriterion(Document):
    def before_insert(self):
        # a criterion added without a Display Order goes after the others
        if not self.sort_order:
            self.sort_order = jd_rules.next_display_order(frappe.get_all("Interview Criterion", pluck="sort_order"))
