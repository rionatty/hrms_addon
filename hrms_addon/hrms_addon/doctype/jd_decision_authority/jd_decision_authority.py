# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One decision area of a Job Description: what the role may decide, and within what limits.

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDDecisionAuthority(Document):
    pass
