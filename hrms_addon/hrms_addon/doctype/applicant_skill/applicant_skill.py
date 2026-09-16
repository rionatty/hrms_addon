# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A skill a candidate has, from the Skill list Job Descriptions and interviews use.

Child table of Job Applicant (Bio-Data tab). Rules for the tab as a whole
live in hrms_addon/hrms_addon/bio_data_rules.py.
"""

from frappe.model.document import Document


class ApplicantSkill(Document):
    pass
