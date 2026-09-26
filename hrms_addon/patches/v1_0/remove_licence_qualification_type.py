# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Job Application Form no longer offers Licence as a qualification
type. The seeded type is deleted where nobody has used it; one an applicant
or an employee already carries (their Applicant Qualification rows) stays,
as their record says it. Safe to run twice.
"""

import frappe

TYPE = "Licence"


def execute():
    if not frappe.db.exists("Qualification Type", TYPE):
        return
    if frappe.db.exists("Applicant Qualification", {"qualification_type": TYPE}):
        return
    try:
        frappe.delete_doc("Qualification Type", TYPE, ignore_permissions=True)
    except frappe.LinkExistsError:
        # linked from somewhere else after all: it stays
        frappe.clear_messages()
