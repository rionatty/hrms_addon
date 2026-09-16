# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One Balanced Scorecard perspective of a Job Description.

Child table of Designation (custom_jd_key_result_areas). Validation of the
table as a whole — one row per perspective, weightings totalling 100% —
lives in hrms_addon/hrms_addon/jd_rules.py.
"""

from frappe.model.document import Document


class JDKeyResultArea(Document):
    pass
