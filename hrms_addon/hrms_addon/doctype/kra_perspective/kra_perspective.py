# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A Balanced Scorecard perspective. KRAs are grouped by it on Job Descriptions.

One of the pick lists behind the KRA form. The values Luuka started with are
seeded once (hrms_addon/hrms_addon/kra_masters.py); after that the list is
HR's to add to, rename or trim.
"""

import frappe
from frappe.model.document import Document

from hrms_addon.hrms_addon import jd_rules


class KRAPerspective(Document):
    def before_insert(self):
        # No Display Order given: list it after the existing perspectives.
        if not self.sort_order:
            self.sort_order = jd_rules.next_display_order(frappe.get_all("KRA Perspective", pluck="sort_order"))
