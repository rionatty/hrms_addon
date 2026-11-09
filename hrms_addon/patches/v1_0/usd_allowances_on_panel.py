# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A USD salary's allowances are added with the assignment's Add Allowance, in
shillings, as any employee's are (Luuka, 10 Nov 2026: "you have removed the
button add allowances?"). The USD slip pays each at the month's rate and the
gross-up takes them with the USD pay (currency_payroll_rules.ALLOWANCES).

So what stood in their place before goes:
  - an amount typed in the assignment's UGX Allowance field becomes an
    allowance on Add Allowance, from the assignment's first day, under the
    UGX Allowance component, unless the employee has one running already;
  - the UGX Allowance line be1a403 put on every USD structure is taken off;
  - the structures' tax lines are written again (usd_gross_up), now reading
    the month's allowances;
  - the field itself is removed.
Each step is named in the migrate's output. Safe to run twice.
"""

import frappe
from frappe.utils import flt, getdate

from hrms_addon.hrms_addon import currency_payroll_rules as rules
from hrms_addon.patches.v1_0 import usd_gross_up

ASSIGNMENT = "Salary Structure Assignment"
FIELD = "%s-%s" % (ASSIGNMENT, rules.OLD_ALLOWANCE_FIELD)


def execute():
    if not frappe.db.exists("DocType", "Salary Structure"):
        return
    component = usd_gross_up.ensure_allowance_component()
    if component and frappe.db.has_column(ASSIGNMENT, rules.OLD_ALLOWANCE_FIELD):
        move_typed_allowances(component)
    take_off_structure_line()
    usd_gross_up.execute()
    if frappe.db.exists("Custom Field", FIELD):
        frappe.delete_doc("Custom Field", FIELD, ignore_permissions=True, force=True)
        print("HRMS Addon: the UGX Allowance field is gone: a USD salary's allowances are on Add Allowance")


def move_typed_allowances(component):
    """Each amount typed in an assignment's UGX Allowance field, as an allowance on Add Allowance."""
    from hrms_addon.hrms_addon import currency_payroll, standing_allowances

    for row in frappe.get_all(ASSIGNMENT, filters={"docstatus": 1, rules.OLD_ALLOWANCE_FIELD: [">", 0]},
                              fields=["name", "employee", "company", "currency", "from_date",
                                      rules.OLD_ALLOWANCE_FIELD], order_by="from_date asc"):
        if not rules.foreign(row.currency, currency_payroll.company_currency(row.company)):
            continue
        running = frappe.db.exists("Additional Salary", {
            "employee": row.employee, "salary_component": component, "docstatus": 1, "disabled": 0,
            "is_recurring": 1, "to_date": [">=", getdate(row.from_date)]})
        if running:
            print("HRMS Addon: %s has a %s running already (%s): %s's amount left as it is"
                  % (row.employee, component, running, row.name))
            continue
        made = standing_allowances._new(row.employee, component, flt(row.get(rules.OLD_ALLOWANCE_FIELD)),
                                        row.from_date)
        print("HRMS Addon: %s's UGX Allowance of %s a month is now an allowance on Add Allowance (%s)"
              % (row.employee, flt(row.get(rules.OLD_ALLOWANCE_FIELD)), made.name))


def take_off_structure_line():
    """The UGX Allowance line on each USD structure: the allowance is paid by its own Additional Salary now."""
    structures = sorted({row.parent for row in frappe.get_all("Salary Detail", filters={
        "parenttype": "Salary Structure", "abbr": rules.PAY_ABBR}, fields=["parent"])})
    for name in structures:
        lines = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Structure", "parent": name,
                                                         "abbr": rules.ALLOWANCE_ABBR}, pluck="name")
        for line in lines:
            frappe.db.delete("Salary Detail", {"name": line})
        if lines:
            frappe.clear_document_cache("Salary Structure", name)
            print("HRMS Addon: %s's UGX Allowance line taken off: the allowance is on Add Allowance" % name)
