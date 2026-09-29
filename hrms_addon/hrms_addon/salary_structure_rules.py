# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's Salary Structure and its assignments, once other documents
point at them.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_salary_structures.py exercises them without a bench.

A COMPONENT ADDED TO A SUBMITTED STRUCTURE

A submitted structure takes a new component (a new allowance or a new
deduction) without being cancelled, which would mean cancelling every
assignment on it first. The row is checked as Frappe HR checks a component
before submit and takes what its component gives it, the way Frappe HR's
set_missing_values fills it. The structure's totals of the fixed amounts
follow the rows, as the form works them out. None is taken off: a
component is stopped by giving it the condition 0, since the condition and
the formula can already change after submit.

CANCELLING AN ASSIGNMENT TO CORRECT IT

An onboarding and a position change keep the assignment (and the
structure) they made as a record. Cancelling the assignment to correct it
cancels neither of them nor what follows them (the probation evaluation,
the reviews, the contract), and the assignment that replaces it takes its
place on them: its amendment, or a new one for the same employee from the
same date.
"""

import re

# Frappe HR's COMPONENT_PARENTFIELDS, and what each table takes
TABLES = ("earnings", "deductions", "employer_contributions")
TYPE_FOR = {"earnings": "Earning", "deductions": "Deduction", "employer_contributions": "Employer Contribution"}
LABELS = {"earnings": "Earnings", "deductions": "Deductions", "employer_contributions": "Employer Contributions"}

# documents that keep the assignment or the structure they made, as a record
RECORDS = ("Employee Onboarding", "Employee Position Change")
# where each keeps the assignment
ASSIGNMENT_LINKS = (("Employee Onboarding", "custom_salary_structure_assignment"),
                    ("Employee Position Change", "salary_structure_assignment"))

# what a new row takes from its component (Frappe HR's set_missing_values):
# these always, and these only while the row has no amount or formula
FROM_COMPONENT = ("depends_on_payment_days", "variable_based_on_taxable_salary", "is_tax_applicable",
                  "is_flexible_benefit")
IF_MISSING = ("amount_based_on_formula", "formula", "amount")
COMPONENT_FIELDS = ("type", "disabled") + FROM_COMPONENT + IF_MISSING

# the structure's totals of the fixed amounts: the form works them out again
# as soon as a row's amount is set, so they change with the rows
TOTALS = ("total_earning", "total_deduction", "net_pay")


def removed_rows(before, now):
    """The rows a save would take off a submitted structure:
    [(table, idx, component)].

    before, now: {table: [{"name", "idx", "salary_component"}]}"""
    gone = []
    for table in TABLES:
        kept = {row.get("name") for row in now.get(table) or []}
        gone += [(table, row.get("idx"), row.get("salary_component")) for row in before.get(table) or []
                 if row.get("name") not in kept]
    return gone


def added_rows(before, now):
    """{table: [rows]} a save adds to a submitted structure."""
    added = {}
    for table in TABLES:
        had = {row.get("name") for row in before.get(table) or []}
        rows = [row for row in now.get(table) or [] if not row.get("name") or row.get("name") not in had]
        if rows:
            added[table] = rows
    return added


def defaults_for(row, component):
    """{field: value} a new row takes from its component, as Frappe HR's
    set_missing_values gives it before submit."""
    if not component:
        return {}
    values = {field: component.get(field) for field in FROM_COMPONENT if row.get(field) != component.get(field)}
    if not (row.get("amount") or row.get("formula")):
        values.update({field: component.get(field) for field in IF_MISSING})
    return values


def row_errors(table, row, component, others, payment_days_abbrs=()):
    """Problems with a row added to a submitted structure, as messages.

    component: {"type", "disabled", "variable_based_on_taxable_salary"} of
    its Salary Component, or None when there is none of that name;
    others: the components already in the table; payment_days_abbrs: the
    abbreviations of the structure's components that depend on payment
    days."""
    errors = []
    where = "%s row %s" % (LABELS.get(table, table), row.get("idx") or "")
    name = row.get("salary_component")
    if not name:
        return ["%s: choose the salary component." % where]
    if not component:
        return ["%s: there is no salary component %s." % (where, name)]
    if int(component.get("disabled") or 0):
        errors.append("%s: %s is disabled." % (where, name))
    wanted = TYPE_FOR.get(table)
    if wanted and component.get("type") != wanted:
        errors.append("%s: %s is %s, not %s." % (where, name, _article(component.get("type")), _article(wanted)))
    if name in (others or ()):
        errors.append("%s: %s is already on the structure." % (where, name))
    variable = row.get("variable_based_on_taxable_salary", component.get("variable_based_on_taxable_salary"))
    if int(variable or 0) and (row.get("amount") or row.get("formula")):
        errors.append("%s: %s is worked out from the taxable salary, so it takes no amount or formula."
                      % (where, name))
    formula = row.get("formula") or ""
    if formula and int(row.get("depends_on_payment_days") or 0) and \
            any(_uses(formula, abbr) for abbr in payment_days_abbrs if abbr):
        errors.append("%s: %s depends on payment days and its formula uses a component that already does; "
                      "it would be cut twice." % (where, name))
    return errors


def replaced(cancelled, assignment):
    """Whether a submitted assignment takes the place of a cancelled one on
    the records that kept it: it is its amendment, or it is for the same
    employee from the same date.

    cancelled, assignment: {"name", "employee", "from_date", "amended_from"}"""
    if not cancelled or cancelled.get("name") == assignment.get("name"):
        return False
    if assignment.get("amended_from") == cancelled.get("name"):
        return True
    return bool(cancelled.get("employee")) and cancelled.get("employee") == assignment.get("employee") \
        and str(cancelled.get("from_date") or "") == str(assignment.get("from_date") or "")


def totals(earnings, deductions, timesheet=0):
    """{total_earning, total_deduction, net_pay} of the rows' fixed amounts,
    as Frappe HR's form works them out (calculate_totals): no net pay on a
    structure paid from timesheets.

    earnings, deductions: the rows' amounts"""
    earned = sum(float(amount or 0) for amount in earnings or ())
    deducted = sum(float(amount or 0) for amount in deductions or ())
    return {"total_earning": earned, "total_deduction": deducted,
            "net_pay": 0.0 if int(timesheet or 0) else earned - deducted}


def _uses(formula, abbr):
    """Whether a formula names an abbreviation as a whole word."""
    return re.search(r"\b%s\b" % re.escape(abbr), formula) is not None


def _article(kind):
    kind = kind or "no kind"
    return ("an %s" if kind[:1].lower() in "aeiou" else "a %s") % kind.lower()
