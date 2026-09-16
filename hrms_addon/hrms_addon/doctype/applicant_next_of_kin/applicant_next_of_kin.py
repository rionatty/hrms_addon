# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A next of kin of a candidate, from the Pre-Interview Bio-Data Form.

Child table of Job Applicant (Bio-Data tab). Rules for the tab as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class ApplicantNextofKin(Document):
    pass
