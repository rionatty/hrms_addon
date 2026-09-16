# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One stakeholder of a Job Description and what the role deals with them about.

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDStakeholder(Document):
    pass
