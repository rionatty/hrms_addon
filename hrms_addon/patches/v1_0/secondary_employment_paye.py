# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""PAYE at a flat rate for an employee whose main employer is another
(8 Nov 2026; the Income Tax regulations, as URA restated them on
9 September 2026: 40% of a second job's pay, with no tax-free amount).

The PAYE component, and every structure's PAYE line worked out from taxable
pay less LST, give Payroll Settings' Secondary Employment PAYE Rate of
taxable pay less LST when the employee's Secondary Employment is ticked, and
the bands as before otherwise (secondary_employment.py gives a formula the
rate; secondary_employment_rules.secondary_formula writes the condition). A
line worked out another way, like the USD structure's, is left as it is and
named in the migrate's output. A formula that already reads the rate is left
as it is. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import secondary_employment_rules as rules


def execute():
    if not frappe.db.exists("DocType", "Salary Component"):
        return
    for name in rules.PAYE_LINES:
        if frappe.db.exists("Salary Component", name):
            formula = frappe.db.get_value("Salary Component", name, "formula")
            wrapped = rules.secondary_formula(formula)
            if wrapped != formula:
                frappe.db.set_value("Salary Component", name, "formula", wrapped, update_modified=False)
    left = set()
    for line in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure",
                                                         "salary_component": ["in", list(rules.PAYE_LINES)]},
                               fields=["name", "parent", "formula"]):
        wrapped = rules.secondary_formula(line.formula)
        if wrapped != line.formula:
            frappe.db.set_value("Salary Detail", line.name, "formula", wrapped, update_modified=False)
        elif line.formula and rules.RATE_NAME not in line.formula:
            left.add(line.parent)
    if left:
        print("HRMS Addon: PAYE stays on its bands for a second job in %s: their PAYE line is not worked out from "
              "taxable pay less LST" % ", ".join(sorted(left)))
