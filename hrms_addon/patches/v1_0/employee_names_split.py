# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Employees made from an onboarding or a job offer carry the whole name in
First Name, where HRMS maps it. It is split into First, Middle and Last
Name as a new one now is (bio_data.split_name), wherever nothing has been
put in Middle or Last Name since. The full name stays as it is.

Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import bio_data_rules


def execute():
    if not frappe.get_meta("Employee").has_field("job_applicant"):
        return
    for row in frappe.get_all("Employee", filters={"job_applicant": ["is", "set"]},
                              fields=["name", "first_name", "middle_name", "last_name"]):
        if row.middle_name or row.last_name:
            continue
        parts = bio_data_rules.name_parts(row.first_name)
        if parts.get("middle_name") or parts.get("last_name"):
            frappe.db.set_value("Employee", row.name, parts, update_modified=False)
