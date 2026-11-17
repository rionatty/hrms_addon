"""The employee's salary, bank and salary advance details are changed by HR alone (Luuka, 17 Nov 2026: "some of the
critical employee information HR manager and HR officer shuld be the ones to edit"). The security setup had given
Payroll write at that level beside read; Payroll keep the read. Once, by Luuka's own decision: security.py itself
grants and never revokes. A deploy then says any other role that can change an Employee (security._warn_about_leaks).
Safe to run twice."""

import frappe

from hrms_addon.hrms_addon import security_rules as rules


def execute():
    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return
    changed = frappe.get_all("Custom DocPerm", filters={
        "parent": "Employee", "permlevel": rules.PROTECTED_LEVEL, "write": 1,
        "role": ["not in", list(rules.EDITOR_ROLES + rules.ADMIN_ROLES)]}, pluck="name")
    for name in changed:
        frappe.db.set_value("Custom DocPerm", name, "write", 0, update_modified=False)
    if changed:
        frappe.clear_cache(doctype="Employee")
