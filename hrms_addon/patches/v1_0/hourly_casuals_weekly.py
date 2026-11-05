"""Pay Category: those tagged Hourly are now Weekly (Luuka, 5 Nov 2026). Weekly is
what the weekly payroll picks people by (weekly_pay.py), and the fixtures take
Hourly off the list, so a record left on it could not be saved."""

import frappe


def execute():
    if frappe.db.has_column("Employee", "custom_pay_category"):
        frappe.db.set_value("Employee", {"custom_pay_category": "Hourly"}, "custom_pay_category", "Weekly",
                            update_modified=False)
