# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One reporting relationship of a Job Description: a position that reports to this role, directly or indirectly.

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDReportingLine(Document):
    pass
