# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The employer's own share of pay, Luuka's NSSF 10%, as rules with no Frappe import (on the site: employer_costs.py;
scripts/verify_employer_costs.py).

WHY

Frappe HR v16 works the employer's share out on the slip, as an Employer Contribution line (the USD structure's NSSF
Employer Contribution) or as a deduction left out of the total (Luuka Salaried's NSSF Employer 10%), and its payroll books
neither as it should. Its accrual entry posts only the earnings and the deductions: an Employer Contribution line is never
posted, so the cost and what is owed to NSSF never reach the books; and a deduction left out of the total but kept in the
accounts is credited to its account and taken off Payroll Payable too, so what is owed to staff comes out short by it and
the cost is still not booked.

WHAT IS DONE

A component's account row gains a Cost Account, the expense the employer's share is booked to. With the payroll's accrual
entry each such line of its slips is booked: its Cost Account debited, its own account (NSSF Payable) credited, by the same
cost centres as the rest of the employee's pay. Where Frappe HR has already credited the line and taken it off Payroll
Payable, only the debit is added, which puts Payroll Payable back at the net pay. An Employer Contribution line whose
component has no Cost Account stops the payroll and says so, as Frappe HR stops one with no account: left alone it would go
unbooked again.
"""

EMPLOYER = "employer_contributions"
DEDUCTIONS = "deductions"
EXPENSE = "Expense"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _flag(value):
    return bool(int(_num(value)))


def employer_lines(rows, cost_accounts):
    """The employer's share on the slips, and the components whose Cost Account is missing.
    rows: slip lines [{"parentfield", "salary_component", "amount", "do_not_include_in_total", "do_not_include_in_accounts",
    "employee", "salary_structure"}]; cost_accounts: {component: its Cost Account for the payroll's company}.
    Each line: {"employee", "structure", "component", "amount", "cost_account", "posted"}, posted where Frappe HR's own
    entry has already credited it and taken it off Payroll Payable."""
    lines, missing = [], set()
    for row in rows or []:
        amount = _num(row.get("amount"))
        component = row.get("salary_component")
        if not amount or not component:
            continue
        cost = (cost_accounts or {}).get(component)
        where = row.get("parentfield")
        if where == EMPLOYER:
            if not cost:
                missing.add(component)
                continue
            posted = False
        elif where == DEDUCTIONS and _flag(row.get("do_not_include_in_total")) and cost:
            posted = not _flag(row.get("do_not_include_in_accounts"))
        else:
            continue
        lines.append({"employee": row.get("employee"), "structure": row.get("salary_structure"), "component": component,
                      "amount": amount, "cost_account": cost, "posted": posted})
    return lines, sorted(missing)


def missing_message(components, company):
    return ("Set the Cost Account of %s for %s (Salary Component > Accounts): the employer's share is booked to it."
            % (", ".join(components), company))


def cost_account_errors(row_company, account):
    """Why an account cannot be a component's Cost Account for a company. account: {"name", "company", "is_group",
    "root_type"}, or None where it does not exist."""
    if not account:
        return []
    errors = []
    if account.get("company") != row_company:
        errors.append("%s is not an account of %s." % (account.get("name"), row_company))
    if _flag(account.get("is_group")):
        errors.append("%s is a group account." % account.get("name"))
    if account.get("root_type") != EXPENSE:
        errors.append("%s is not an expense account: the employer's share is a cost." % account.get("name"))
    return errors
