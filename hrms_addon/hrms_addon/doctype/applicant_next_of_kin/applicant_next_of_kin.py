# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A next of kin of a candidate or employee, from the Bio-Data forms.

Child table of Job Applicant and Employee (their Bio-Data tabs). Rules for the tabs as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class ApplicantNextofKin(Document):
    pass
