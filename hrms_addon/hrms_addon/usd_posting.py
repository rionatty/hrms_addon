# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in USD posted in shillings to the shilling (Luuka, 10 Nov 2026: "basic pay is in usd the rest supposed
to be posted in UGX"). The rules are in usd_posting_rules.py.

Frappe HR builds the payroll's accrual entry from the slips' lines, each its dollars at the payroll's rate
(payroll_entry.make_accrual_jv_entry). Before the entry is saved, each line that was worked out in shillings posts
those shillings instead: the USD structure's tax lines (Tax Paid by Company, PAYE, NSSF 5% and 10%, LST) and an
Additional Salary recorded in shillings (an allowance, an advance or loan recovered). The employer's NSSF that
employer_costs.py books is moved the same way. Basic, and the net pay owed in dollars, stay as they are; what is left
between debit and credit goes to the company's Round Off account.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import (currency_payroll, currency_payroll_rules, employer_costs, usd_posting_rules as rules,
                                   usd_sheet)

SLIP = "Salary Slip"
ABBRS = {"cover": currency_payroll_rules.COVER_ABBR, "lst": currency_payroll_rules.LST_ABBR,
         "paye": currency_payroll_rules.PAYE_ABBR, "nssf": currency_payroll_rules.NSSF_ABBR,
         "nssf_employer": currency_payroll_rules.NSSF_EMPLOYER_ABBR}


class PayrollEntryUsdPosting:
    """The accrual entry of a payroll in another currency, in the company's own to the shilling."""

    def make_journal_entry(self, accounts, currencies, *args, **kwargs):
        if kwargs.get("submitted_salary_slips") and kwargs.get("voucher_type", "Journal Entry") == "Journal Entry":
            accounts = in_shillings(self, accounts)
        return super().make_journal_entry(accounts, currencies, *args, **kwargs)


def in_shillings(run, accounts):
    """The accrual entry's rows, each line worked out in shillings at those shillings, and the Round Off row."""
    home = currency_payroll.company_currency(run.company)
    if not currency_payroll_rules.foreign(run.get("currency"), home) or not flt(run.get("exchange_rate")):
        return accounts
    lines = _lines(run, flt(run.exchange_rate), home)
    gaps = rules.deltas(lines)
    if not gaps:
        return accounts
    names = {row.get("account") for row in accounts} | {line["account"] for line in lines}
    home_accounts = {name for name in names if name and frappe.get_cached_value(
        "Account", name, "account_currency") == home}
    company = frappe.get_cached_value("Company", run.company, ["round_off_account", "round_off_cost_center"],
                                      as_dict=True) or frappe._dict()
    round_off = {"account": company.round_off_account,
                 "cost_center": company.round_off_cost_center or run.get("cost_center")}
    try:
        rows, _unplaced = rules.apply(accounts, gaps, home_accounts, round_off)
    except ValueError:
        frappe.throw(_(rules.round_off_message(run.company)))
    if len(rows) > len(accounts):
        # the Round Off row, with the project and dimensions Frappe HR gives its own rows
        from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

        rows[-1]["project"] = run.get("project")
        run.update_accounting_dimensions(rows[-1], get_accounting_dimensions() or [])
    return rows


def _lines(run, rate, home):
    """The slips' lines that were worked out in shillings, as Frappe HR books them (get_salary_components) and as
    employer_costs.py books the employer's share."""
    slips = [slip.name for slip in run.get_sal_slip_list(ss_status=1, as_dict=True) or []]
    if not slips:
        return []
    of_employee = {row.employee: row.name for row in frappe.get_all(
        SLIP, filters={"name": ["in", slips]}, fields=["name", "employee"], limit_page_length=0)}
    worked = {}

    def figures(employee):
        name = of_employee.get(employee)
        if name and name not in worked:
            worked[name] = usd_sheet.worked_out(frappe.get_doc(SLIP, name))[1]
        return worked.get(name) or {}

    lines = []
    for component_type, side in (("earnings", rules.DEBIT), ("deductions", rules.CREDIT)):
        for item in run.get_salary_components(component_type) or []:
            parts = rules.line_parts(_abbr(item.salary_component), figures(item.employee),
                                     _recorded(item.get("additional_salary"), home), ABBRS)
            if not parts:
                continue
            reference = run.get_advance_deduction(component_type, item) if component_type == "deductions" else None
            lines.append({"account": run.get_salary_component_account(item.salary_component), "side": side,
                          "reference": reference or None, "dollars": item.amount, "rate": rate, "parts": parts,
                          "cost_centers": run.get_payroll_cost_centers_for_employee(item.employee,
                                                                                    item.salary_structure)})
    for line in employer_costs.employer_lines(run):
        parts = rules.line_parts(_abbr(line["component"]), figures(line["employee"]), None, ABBRS)
        if not parts:
            continue
        centers = run.get_payroll_cost_centers_for_employee(line["employee"], line["structure"])
        common = {"reference": None, "dollars": line["amount"], "rate": rate, "parts": parts, "cost_centers": centers}
        lines.append(dict(common, account=line["cost_account"], side=rules.DEBIT))
        if not line["posted"]:
            lines.append(dict(common, account=run.get_salary_component_account(line["component"]), side=rules.CREDIT))
    return lines


def _abbr(component):
    return frappe.get_cached_value("Salary Component", component, "salary_component_abbr")


def _recorded(additional_salary, home):
    """An Additional Salary's amount where it was recorded in the company's currency, else None."""
    if not additional_salary:
        return None
    amount, currency = frappe.db.get_value("Additional Salary", additional_salary, ["amount", "currency"]) or (0, None)
    return flt(amount) if (currency or home) == home else None
