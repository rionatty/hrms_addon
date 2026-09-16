# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One requirement of the ideal job holder: a qualification, training or certification, or experience.

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDJobSpecification(Document):
    pass
