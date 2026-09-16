# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A previous job of a candidate.

Child table of Job Applicant (Bio-Data tab). Rules for the tab as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class ApplicantEmploymentHistory(Document):
    pass
