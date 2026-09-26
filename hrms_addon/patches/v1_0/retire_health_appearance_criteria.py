# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The score sheet no longer scores Appearance or Health
(interview_rules.RETIRED_CRITERIA): the seeded criteria are switched off,
once. Sheets already scored keep their rows; a criterion HR renamed is
theirs and stays as it is. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import interview_rules


def execute():
    retired = {name.lower() for name in interview_rules.RETIRED_CRITERIA}
    for name in frappe.get_all("Interview Criterion", filters={"disabled": 0}, pluck="name"):
        if name.lower() in retired:
            frappe.db.set_value("Interview Criterion", name, "disabled", 1, update_modified=False)
