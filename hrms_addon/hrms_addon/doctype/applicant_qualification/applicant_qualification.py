# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A professional or other qualification of a candidate or employee.

Child table of Job Applicant and Employee (their Bio-Data tabs). Rules for the tabs as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class ApplicantQualification(Document):
    pass
