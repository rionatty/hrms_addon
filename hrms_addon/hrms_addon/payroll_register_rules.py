# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""One payroll's Salary Register, for the Salary Register tab on the Payroll
Entry (payroll_register.py).

No Frappe import, like the other *_rules.py modules, so
scripts/verify_payroll_register.py exercises it without a bench.

Frappe HR's Salary Register is asked for a period and a company, so it lists
every payroll run in them. On a payroll's own tab (1 Nov 2026; Luuka: "add a
tab for salary register here") it is kept to that payroll's salary slips,
and a salary component none of them has is given no column, as the register
gives none to a component no slip in it has.
"""

AMOUNT = "Currency"
# the register's own amounts, shown whatever they come to; every other amount column is a salary component's
TOTALS = ("absent_amount", "gross_pay", "total_loan_repayment", "total_deduction", "net_pay")


def register_of(columns, data, slips):
    """(columns, rows): the register's rows for the slips named, and its columns less any salary component none of
    those rows has an amount for."""
    slips = set(slips or ())
    rows = [row for row in data or [] if isinstance(row, dict) and row.get("salary_slip_id") in slips]
    kept = [column for column in columns or [] if isinstance(column, dict) and (
        column.get("fieldtype") != AMOUNT or column.get("fieldname") in TOTALS
        or any(_num(row.get(column.get("fieldname"))) for row in rows))]
    return kept, rows


def sheet(columns, rows):
    """The register as a spreadsheet's rows: the column labels, then a row per slip, hidden columns left out."""
    shown = [column for column in columns or [] if not column.get("hidden")]
    return [[column.get("label") for column in shown]] + [
        [row.get(column.get("fieldname")) for column in shown] for row in rows or []]


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
