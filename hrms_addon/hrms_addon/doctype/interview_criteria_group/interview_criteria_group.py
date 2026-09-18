# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A group of criteria on the Candidate Interview Evaluation / Score Form
(LPL/HR/17). Seeded once with the form's groups; HR's to change after that.
"""

import frappe
from frappe.model.document import Document

from hrms_addon.hrms_addon import jd_rules


class InterviewCriteriaGroup(Document):
    def before_insert(self):
        # a group added without a Display Order goes after the others
        if not self.sort_order:
            self.sort_order = jd_rules.next_display_order(frappe.get_all("Interview Criteria Group", pluck="sort_order"))
