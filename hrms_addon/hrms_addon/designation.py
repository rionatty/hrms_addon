# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Designation (Job Title) — Job Description template.

The JD fields themselves are fixtures (Job Description tab). This only
enforces the Balanced Scorecard rules from jd_rules.py.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import jd_rules


def validate(doc, method=None):
    errors = jd_rules.key_result_area_errors(doc.get("custom_jd_key_result_areas"))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Key Result Areas"))
