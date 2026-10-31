# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Overtime in full, Leave Advance without a formula, and the pay NSSF, LST
and PAYE are worked out on (31 Oct 2026; the user: "please fix them").

  overtime        Overtime, and every component an Overtime Type pays into,
                  stops depending on payment days: overtime is paid in full,
                  never cut for the days not worked. On the component and on
                  every structure's line of it.
  Leave Advance   loses its formula (base * .6) and "amount based on
                  formula": on a structure line it would take 60% of
                  everybody's pay. A leave advance is recovered by the Leave
                  Advance module, the amount it gave.
  pay bases       on every structure's LST, NSSF and PAYEE lines
                  (salary_structure_rules.PAY_BASES): the Car Benefit, never
                  in gross pay, is no longer taken off it again for NSSF and
                  LST, and is taxed; Sacco withdrawals are neither taxed nor
                  charged NSSF. A formula not written on the old base is left
                  as it is.

Safe to run twice: what is already right is not touched.
"""

import frappe

from hrms_addon.hrms_addon import salary_structure_rules as rules

COMPONENT = "Salary Component"
OVERTIME = "Overtime"
LEAVE_ADVANCE = "Leave Advance"


def execute():
    if not frappe.db.exists("DocType", COMPONENT):
        return
    overtime_in_full()
    leave_advance_without_formula()
    correct_pay_bases()


def overtime_in_full():
    names = {OVERTIME}
    if frappe.db.exists("DocType", "Overtime Type"):
        names |= set(frappe.get_all("Overtime Type", filters={"overtime_salary_component": ["is", "set"]},
                                    pluck="overtime_salary_component"))
    names = sorted(name for name in names if frappe.db.exists(COMPONENT, name))
    for name in names:
        if frappe.db.get_value(COMPONENT, name, "depends_on_payment_days"):
            frappe.db.set_value(COMPONENT, name, "depends_on_payment_days", 0, update_modified=False)
    for line in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "salary_component": ["in", names],
                                                         "depends_on_payment_days": 1}, pluck="name"):
        frappe.db.set_value("Salary Detail", line, "depends_on_payment_days", 0, update_modified=False)


def leave_advance_without_formula():
    if frappe.db.exists(COMPONENT, LEAVE_ADVANCE) and (frappe.db.get_value(COMPONENT, LEAVE_ADVANCE, "formula")
                                                       or frappe.db.get_value(COMPONENT, LEAVE_ADVANCE,
                                                                              "amount_based_on_formula")):
        frappe.db.set_value(COMPONENT, LEAVE_ADVANCE, {"formula": "", "amount_based_on_formula": 0},
                            update_modified=False)
    for line in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "salary_component": LEAVE_ADVANCE,
                                                         "amount_based_on_formula": 1}, pluck="name"):
        frappe.db.set_value("Salary Detail", line, {"formula": "", "amount_based_on_formula": 0}, update_modified=False)


def correct_pay_bases():
    lines = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure",
                                                     "salary_component": ["in", list(rules.PAY_BASES)]},
                           fields=["name", "salary_component", "formula"])
    for line in lines:
        formula = rules.pay_base_formula(line.salary_component, line.formula)
        if formula != line.formula:
            frappe.db.set_value("Salary Detail", line.name, "formula", formula, update_modified=False)
