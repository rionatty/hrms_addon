# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a role is accountable for under one management system standard (ISO 9001, ISO 22000, ...).

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDISOResponsibility(Document):
    pass
