# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Qualification Type

One of the pick lists behind the Bio-Data tab of Job Applicant: what kind of
qualification a row of Professional / Other Qualifications is. Seeded once
(hrms_addon/hrms_addon/pick_lists.py), then HR's to add to, rename or trim. The
interview shortlist lists the types marked "Certification or Licence" in their
own column.
"""

from frappe.model.document import Document


class QualificationType(Document):
    pass
