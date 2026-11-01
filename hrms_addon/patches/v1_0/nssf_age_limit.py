# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""No NSSF from the age Payroll Settings' NSSF Age Limit sets, unless the
employee's NSSF Voluntary is ticked (1 Nov 2026; the NSSF Act s.6(1): an
eligible employee is below fifty-five).

The NSSF Employee and NSSF Employer 10% components, and every structure's
lines of them, give nothing once employee_age reaches nssf_age_limit
(nssf_age.py gives a formula both; nssf_age_rules.exempt_formula writes the
condition). The age stays in the settings, not in the formula. A formula
that already reads the limit is left as it is. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import nssf_age_rules as rules


def execute():
    if not frappe.db.exists("DocType", "Salary Component"):
        return
    for name in rules.NSSF_LINES:
        if frappe.db.exists("Salary Component", name):
            formula = frappe.db.get_value("Salary Component", name, "formula")
            wrapped = rules.exempt_formula(formula)
            if wrapped != formula:
                frappe.db.set_value("Salary Component", name, "formula", wrapped, update_modified=False)
    for line in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure",
                                                         "salary_component": ["in", list(rules.NSSF_LINES)]},
                               fields=["name", "formula"]):
        wrapped = rules.exempt_formula(line.formula)
        if wrapped != line.formula:
            frappe.db.set_value("Salary Detail", line.name, "formula", wrapped, update_modified=False)
