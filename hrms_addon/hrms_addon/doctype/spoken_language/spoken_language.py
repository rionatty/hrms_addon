# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A language a candidate reads, writes or speaks.

One of the pick lists behind the Bio-Data tab of Job Applicant. Seeded once
(hrms_addon/hrms_addon/pick_lists.py); after that the list is HR's to add to,
rename or trim.
"""

from frappe.model.document import Document


class SpokenLanguage(Document):
    pass
