"""Pay Category: Monthly is now Regular, Luuka's own word for an employee on a
salary (5 Nov 2026: "pay category should change from monthly to regular"). The
fixtures take Monthly off the list, so a record left on it could not be saved,
and the advances keep a copy of the category that moves with it."""

import frappe

KEPT = (("Employee", "custom_pay_category"), ("Employee Advance", "custom_pay_category"),
        ("Leave Advance", "pay_category"), ("Salary Advance Processing Employee", "pay_category"))


def execute():
    for doctype, field in KEPT:
        if frappe.db.has_column(doctype, field):
            frappe.db.set_value(doctype, {field: "Monthly"}, field, "Regular", update_modified=False)
