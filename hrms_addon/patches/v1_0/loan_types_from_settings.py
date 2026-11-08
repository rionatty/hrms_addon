"""The kinds of loan become Luuka's own list, Employee Loan Type (review
item 25). The three the minutes named are made from what Loan Settings held
for them, so nothing a site set is lost, with a SACCO loan and a bank loan;
every loan made before is the company's own."""

import frappe

from hrms_addon.hrms_addon import loan_rules as rules

TYPE = "Employee Loan Type"


def execute():
    if not frappe.db.exists("DocType", TYPE):
        return
    # the old figures stay in the database after their fields have gone
    stored = dict(frappe.db.get_singles_dict("Loan Settings") or {})
    for values in rules.seed_types(stored):
        if frappe.db.exists(TYPE, values["loan_type_name"]):
            continue
        doc = frappe.get_doc(dict(values, doctype=TYPE))
        doc.flags.ignore_permissions = True
        doc.insert()
    for name in frappe.get_all("Employee Loan", filters={"processed_by": ["is", "not set"]}, pluck="name"):
        frappe.db.set_value("Employee Loan", name, "processed_by", rules.COMPANY, update_modified=False)
