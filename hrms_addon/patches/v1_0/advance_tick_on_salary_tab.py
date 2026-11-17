"""Salary Advance Set by Hand sits at the top of the Employee's Salary tab, under the Payroll Cost Center (Luuka,
18 Nov 2026: "add them under salary tab"), not in a Salary Advance section of its own below Bank Loan. The section
is dropped from the fixtures; removing a record from a fixture file does not delete it from a site that imported it,
hence this patch. It runs before migrate syncs the fixtures, which then move the tick. Safe on a site that never had
it."""

import frappe


def execute():
    frappe.delete_doc_if_exists("Custom Field", "Employee-custom_salary_advance_section")
