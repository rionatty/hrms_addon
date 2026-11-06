# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The employer's own share of pay booked with the payroll (rules and why: employer_costs_rules.py;
scripts/verify_employer_costs.py).

  PayrollEntryEmployerCosts  the payroll's accrual entry books each employer's share of its slips: the component's
                             Cost Account debited, its own account credited, Payroll Payable left at the net pay
  component_validate         Salary Component validate: a Cost Account is an expense of the row's company
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import employer_costs_rules as rules

SLIP = "Salary Slip"
DETAIL = "Salary Detail"
COMPONENT = "Salary Component"
COMPONENT_ACCOUNT = "Salary Component Account"
COST_FIELD = "custom_cost_account"
TITLE = "Employer's Share"


class PayrollEntryEmployerCosts:
    def get_payable_amount_for_earnings_and_deductions(self, accounts, earnings, deductions, currencies, company_currency,
                                                       accounting_dimensions, precision, payable_amount,
                                                       employee_wise_accounting_enabled):
        payable_amount = super().get_payable_amount_for_earnings_and_deductions(
            accounts, earnings, deductions, currencies, company_currency, accounting_dimensions, precision, payable_amount,
            employee_wise_accounting_enabled)
        return book(self, accounts, currencies, company_currency, accounting_dimensions, precision, payable_amount,
                    employee_wise_accounting_enabled)


def book(doc, accounts, currencies, company_currency, accounting_dimensions, precision, payable_amount, employee_wise):
    """Add the employer's share of the payroll's slips to its accrual entry; the payable amount after it."""
    debits, credits = {}, {}
    for line in employer_lines(doc):
        for cost_center, percentage in doc.get_payroll_cost_centers_for_employee(line["employee"], line["structure"]).items():
            amount = flt(line["amount"]) * flt(percentage) / 100
            key = (line["cost_account"], cost_center)
            debits[key] = debits.get(key, 0) + amount
            if not line["posted"]:
                key = (doc.get_salary_component_account(line["component"]), cost_center)
                credits[key] = credits.get(key, 0) + amount
            elif employee_wise:
                # Frappe HR took it off this employee's pay to be paid: it is not theirs to lose
                doc.set_employee_based_payroll_payable_entries("earnings", line["employee"], amount)
    for entries, entry_type in ((debits, "debit"), (credits, "credit")):
        for (account, cost_center), amount in entries.items():
            payable_amount = doc.get_accounting_entries_and_payable_amount(
                account, cost_center or doc.cost_center, amount, currencies, company_currency, payable_amount,
                accounting_dimensions, precision, entry_type=entry_type, accounts=accounts)
    return payable_amount


def employer_lines(doc):
    """The employer's share on the slips this accrual entry is for, read for them all at once."""
    if not frappe.get_meta(COMPONENT_ACCOUNT).has_field(COST_FIELD):
        return []
    slips = doc.get_sal_slip_list(ss_status=1, as_dict=True) or []
    names = [slip.name for slip in slips]
    if not names:
        return []
    people = {row.name: row for row in frappe.get_all(SLIP, filters={"name": ["in", names]},
                                                     fields=["name", "employee", "salary_structure"], limit_page_length=0)}
    rows = frappe.get_all(DETAIL, filters={"parenttype": SLIP, "parent": ["in", names],
                                           "parentfield": ["in", [rules.EMPLOYER, rules.DEDUCTIONS]]},
                          fields=["parent", "parentfield", "salary_component", "amount", "do_not_include_in_total",
                                  "do_not_include_in_accounts"], limit_page_length=0)
    rows = [dict(row, employee=people[row.parent].employee, salary_structure=people[row.parent].salary_structure)
            for row in rows if row.parent in people]
    lines, missing = rules.employer_lines(rows, cost_accounts(doc.company, {row["salary_component"] for row in rows}))
    if missing:
        frappe.throw(_(rules.missing_message(missing, doc.company)), title=_(TITLE))
    return lines


def cost_accounts(company, components):
    """{component: its Cost Account for the company}."""
    if not components:
        return {}
    return {row.parent: row.get(COST_FIELD) for row in frappe.get_all(
        COMPONENT_ACCOUNT, filters={"parenttype": COMPONENT, "parent": ["in", sorted(components)], "company": company},
        fields=["parent", COST_FIELD], limit_page_length=0) if row.get(COST_FIELD)}


def component_validate(doc, method=None):
    """A Cost Account belongs to the row's company and is an expense ledger."""
    errors = []
    for row in doc.get("accounts") or []:
        account = row.get(COST_FIELD)
        if account:
            facts = frappe.db.get_value("Account", account, ["name", "company", "is_group", "root_type"], as_dict=True)
            errors += rules.cost_account_errors(row.get("company"), facts)
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
