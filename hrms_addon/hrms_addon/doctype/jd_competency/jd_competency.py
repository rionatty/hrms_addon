# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One competency a Job Description requires, from the Skill list Employee Skill Maps and interviews use.

Child table of Designation (Job Description tab). Rules for the table as a
whole live in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDCompetency(Document):
    pass
