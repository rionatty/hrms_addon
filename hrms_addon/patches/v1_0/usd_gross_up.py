# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The USD structure works out the tax the company pays the grossed-up way
(8 Nov 2026; Income Tax Act s.19(1)(c) and s.58: tax an employer pays for an
employee is the employee's income too), as Luuka's own expatriate payroll
does (currency_payroll_rules.usd_gross_up_formulas).

Every structure with a USD Pay line has its Tax Paid by Company, LST, PAYE,
NSSF Employee and NSSF employer lines written over, found by abbreviation
whatever the site calls the components. A line the structure lacks is added
from its component, as the desk adds one, and named in the migrate's output;
so is a line no component is abbreviated for. The UGX Allowance component,
which Add Allowance offers first on a USD salary, is made here when the site
has none, its accounts those of House Rent Allowance. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import currency_payroll_rules as rules

# what a structure's line takes from its component (Salary Detail's fetch_from)
FETCHED = ("statistical_component", "is_tax_applicable", "is_flexible_benefit", "variable_based_on_taxable_salary",
           "depends_on_payment_days", "do_not_include_in_total", "exempted_from_income_tax",
           "do_not_include_in_accounts", "accrual_component")


def ensure_allowance_component():
    """The UGX Allowance earning, made when the site has none by name or abbreviation, with the accounts of
    the first allowance the site has (rules.ALLOWANCE_ACCOUNTS_FROM), so the payroll can post it. Returns its
    name."""
    if frappe.db.exists("Salary Component", rules.ALLOWANCE_COMPONENT):
        return rules.ALLOWANCE_COMPONENT
    found = frappe.db.get_value("Salary Component", {"salary_component_abbr": rules.ALLOWANCE_ABBR}, ["name"],
                                as_dict=True)
    if found:
        return found.name
    accounts = []
    for source in rules.ALLOWANCE_ACCOUNTS_FROM:
        accounts = frappe.get_all("Salary Component Account", filters={"parent": source,
                                                                       "parenttype": "Salary Component"},
                                  fields=["company", "account"])
        if accounts:
            break
    component = frappe.get_doc(dict(rules.ALLOWANCE_FLAGS, doctype="Salary Component",
                                    salary_component=rules.ALLOWANCE_COMPONENT,
                                    salary_component_abbr=rules.ALLOWANCE_ABBR,
                                    description="Shillings a month on a USD salary, paid with it at the month's rate.",
                                    accounts=[{"company": row.company, "account": row.account} for row in accounts]))
    component.insert(ignore_permissions=True)
    if not accounts:
        print("HRMS Addon: %s has no account: set one under its Accounts before the payroll posts it"
              % rules.ALLOWANCE_COMPONENT)
    return component.name


def execute():
    if not frappe.db.exists("DocType", "Salary Structure"):
        return
    ensure_allowance_component()
    lines = rules.usd_gross_up_formulas()
    structures = sorted({row.parent for row in frappe.get_all("Salary Detail", filters={
        "parenttype": "Salary Structure", "abbr": rules.PAY_ABBR}, fields=["parent"])})
    for name in structures:
        have = {row.abbr: row for row in frappe.get_all("Salary Detail", filters={
            "parenttype": "Salary Structure", "parent": name}, fields=["name", "abbr", "formula"])}
        added, lacking = [], []
        for abbr, (table, formula) in lines.items():
            row = have.get(abbr)
            if row:
                if row.formula != formula:
                    frappe.db.set_value("Salary Detail", row.name, {"formula": formula, "amount_based_on_formula": 1},
                                        update_modified=False)
                continue
            component = frappe.db.get_value("Salary Component", {"salary_component_abbr": abbr},
                                            ["name"] + list(FETCHED), as_dict=True)
            if not component:
                lacking.append(abbr)
                continue
            structure = frappe.get_doc("Salary Structure", name)
            row = structure.append(table, dict({field: component.get(field) for field in FETCHED},
                                               salary_component=component.name, abbr=abbr,
                                               amount_based_on_formula=1, formula=formula))
            row.docstatus = structure.docstatus
            row.db_insert()
            added.append(component.name)
        frappe.clear_document_cache("Salary Structure", name)
        if added:
            print("HRMS Addon: %s had no %s line: added" % (name, ", ".join(added)))
        if lacking:
            print("HRMS Addon: %s still has no line abbreviated %s: no component has that abbreviation"
                  % (name, ", ".join(lacking)))
