"""The casuals' weekly structure, its Casual Overtime line and the Casual
Overtime earning, made on the deploy rather than on the first weekly payroll's
Get Employees (Luuka, 11 Nov 2026: "i cant see casual overtime"), so they are
there to see, and the casuals' Overtime Type can name the earning. Each company
with casuals gets its own (weekly_pay.structure_for, which makes nothing twice).
A company whose structure cannot be made is logged and the rest go on: a
deploy is never stopped by it. Safe to run twice."""

import frappe

from hrms_addon.hrms_addon import weekly_pay_rules as rules


def execute():
    if not frappe.db.has_column("Employee", "custom_pay_category"):
        return
    from hrms_addon.hrms_addon import weekly_pay

    companies = sorted(set(frappe.get_all("Employee", filters={"custom_pay_category": ["in", list(rules.CATEGORIES)]},
                                          pluck="company", limit_page_length=0)) - {None, ""})
    for company in companies:
        frappe.db.savepoint("casual_overtime_ready")
        try:
            weekly_pay.structure_for(company)
        except Exception:
            frappe.db.rollback(save_point="casual_overtime_ready")
            frappe.log_error(title="HRMS Addon: the casuals' weekly structure for %s" % company)
            print("HRMS Addon: the casuals' weekly structure for %s was not made: see the Error Log" % company)
