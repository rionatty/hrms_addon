# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""How strongly a job specification is required, e.g. Essential, Desirable.

One of the pick lists behind the Job Description tables on Job Title. The
values Luuka's JDs use are seeded once (hrms_addon/hrms_addon/pick_lists.py);
after that the list is HR's to add to, rename or trim.

A new weight or must-have changes every applicant's screening, so the open
openings' applicants are screened again (cv_screening.priority_on_update).
"""

from frappe.model.document import Document

from hrms_addon.hrms_addon import cv_screening


class JDRequirementPriority(Document):
    def on_update(self):
        cv_screening.priority_on_update(self)
