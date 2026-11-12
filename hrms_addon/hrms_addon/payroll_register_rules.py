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

The Employees tab shows each employee's figures beside them (Luuka: "under
employee tab add number of working days, paid days, absent, and absent amount
and basic salary", "per employee"), read from their slip. The days are the
calendar's, Sundays and holidays included, as the slip shows them
(pay_days_rules.calendar_days). The Basic Salary is the month's whole Basic,
before anything is taken off for days not paid, as Luuka's own Basic Salary
column has it. A row with no slip yet shows what its slip will
(slip_figures_rules.py).
"""

AMOUNT = "Currency"
# the register's own amounts, shown whatever they come to; every other amount column is a salary component's
TOTALS = ("absent_amount", "gross_pay", "total_loan_repayment", "total_deduction", "net_pay")
# a row of the Employees table's figure, and the slip's field it is read from
SLIP_FIGURES = {"custom_working_days": "custom_days_in_period", "custom_paid_days": "custom_days_paid",
                "custom_absent_days": "absent_days", "custom_absent_amount": "custom_absent_amount",
                # a weekly casual's hours (Luuka, 12 Nov 2026: "add hours worked on the weekly payroll")
                "custom_hours_worked": "custom_weekly_hours"}
BASIC_SALARY = "custom_basic_salary"
# a row with nothing to show: Frappe sends a blank number as nought all the same
NO_FIGURES = dict.fromkeys((*SLIP_FIGURES, BASIC_SALARY), 0)


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


def figures_of(slips, basics):
    """{employee: the figures for their row of the Employees table}. slips: the payroll's, with their name, employee
    and the fields SLIP_FIGURES names; basics: {slip name: the month's Basic on it}."""
    figures = {}
    for slip in slips or []:
        row = {field: _num(slip.get(source)) for field, source in SLIP_FIGURES.items()}
        row[BASIC_SALARY] = _num((basics or {}).get(slip.get("name")))
        figures[slip.get("employee")] = row
    return figures


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
