# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The lines Luuka's own payroll has, on the salaried structure (31 Oct 2026).

The user set the site's September 2026 Salary Register beside Luuka's own
("there are some components that are missing in our salary structure"),
then asked for it in the code ("add through code why do i need to add
manually"). Nobody is exempted: Luuka's payroll left seven people without
NSSF and charged one a flat 40% PAYE, and those "are mistakes no one should
be exempted", so NSSF and PAYEE stay as they are.

  Union Dues            a deduction of 3% of the salary earned (Basic as
                        the slip has it) for an employee ticked Union Member
  Leave Advance         the deduction leave advances are recovered to
  Recovery              (leave_advances.recovery_component), made now so
                        the structure can name it
  payment days          a recovery, an encashment and a settlement are taken
                        in full, never cut for the days not worked: Luuka's
                        September payroll recovers 40% of the full salary
                        from those absent, the advance as it was given.
                        Advance Recovery, Loan Repayment, Penalty Recovery,
                        Leave Encashment and Terminal Benefits stop depending
                        on payment days, on the component and on every
                        structure's line of it
  Luuka Salaried        Taxable Salary reads Overtime 1.0 by the abbreviation
  2026-27               it has now and counts Special Overtime and Overtime
                        3; the lines Luuka's payroll has are added. Their
                        amounts come, as before, from the Overtime Slip,
                        Additional Salary or the module that owns them.

A component or a line already there is left as it is. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import salary_structure_rules as rules

COMPONENT = "Salary Component"
STRUCTURE = "Luuka Salaried 2026-27"
# on the salary earned, as every deduction is ("all the deduction are done on the salary earned which is calculated
# based on working days"): Basic as the slip has it, cut for the days not worked, so the line itself is not cut again
UNION_DUES = {"salary_component": "Union Dues", "salary_component_abbr": "UD", "type": "Deduction",
              "depends_on_payment_days": 0, "is_tax_applicable": 0, "amount_based_on_formula": 1,
              "formula": "floor(BS * 0.03 + 0.500001) if custom_union_member else 0",
              "description": "Union dues: 3% of the salary earned, for an employee ticked Union Member."}
NOT_BY_DAYS = ("Advance Recovery", "Loan Repayment", "Penalty Recovery", "Leave Encashment", "Terminal Benefits")
TAXABLE = "Taxable Salary"
OVERTIME = ("SOT", "OT3")
LINES = (("earnings", "Special Overtime"), ("earnings", "Overtime 3"),
         ("deductions", "Advance Recovery"), ("deductions", "Additional Advance"),
         ("deductions", "Arrears Deductions"), ("deductions", "Leave Advance Recovery"),
         ("deductions", "Other Deduction"), ("deductions", "Penalties"), ("deductions", "Loan Repayment"),
         ("deductions", "Union Dues"))


def execute():
    if not frappe.db.exists("DocType", COMPONENT):
        return
    make_components()
    take_in_full()
    add_lines()


def make_components():
    if not frappe.db.exists(COMPONENT, UNION_DUES["salary_component"]):
        component = frappe.get_doc(dict(UNION_DUES, doctype=COMPONENT))
        component.flags.ignore_permissions = True
        component.insert()
    from hrms_addon.hrms_addon import leave_advances

    leave_advances.recovery_component()


def take_in_full():
    for name in NOT_BY_DAYS:
        if frappe.db.get_value(COMPONENT, name, "depends_on_payment_days"):
            frappe.db.set_value(COMPONENT, name, "depends_on_payment_days", 0, update_modified=False)
    # a structure's line keeps the flag its component had when the line was made
    for line in frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure",
                                                         "salary_component": ["in", list(NOT_BY_DAYS)],
                                                         "depends_on_payment_days": 1}, pluck="name"):
        frappe.db.set_value("Salary Detail", line, "depends_on_payment_days", 0, update_modified=False)


def add_lines():
    if not frappe.db.exists("Salary Structure", STRUCTURE):
        return
    structure = frappe.get_doc("Salary Structure", STRUCTURE)
    if structure.docstatus == 2:
        return
    changed = False
    abbrs = set(frappe.get_all(COMPONENT, pluck="salary_component_abbr"))
    for line in structure.get("earnings") or []:
        if line.salary_component == TAXABLE and line.formula:
            formula = rules.taxable_formula(line.formula, abbrs, OVERTIME)
            if formula != line.formula:
                line.formula = formula
                changed = True
    have = {line.salary_component for table in ("earnings", "deductions") for line in structure.get(table) or []}
    for table, name in LINES:
        if name not in have and frappe.db.exists(COMPONENT, name):
            structure.append(table, {"salary_component": name})
            changed = True
    if changed:
        structure.flags.ignore_permissions = True
        structure.save()
