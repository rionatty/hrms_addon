# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's pay as their salary structure works it out.

The gross is Frappe HR's own figure. The Salary Structure Assignment
evaluates the structure's formulas with its Base and Variable and counts
what a salary slip counts as gross (calculate_ctc_and_gross, shown on the
assignment as Annual Gross Earning). Statistical components are not part of
it, and every earning is taken at full payment days.

An allowance paid every month outside the structure, as a recurring
Additional Salary (House Rent and Transport at Luuka), is part of the gross
too; a payment made once (overtime, a bonus) is not. The rule is in
pay_rules.py.
"""

import frappe
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import pay_rules as rules

ASSIGNMENT = "Salary Structure Assignment"
ADDITIONAL = "Additional Salary"


def assignment_on(employee, on=None):
    """The employee's submitted Salary Structure Assignment in force on
    `on`, or their latest when no day is given. None when they have none."""
    filters = {"employee": employee, "docstatus": 1}
    if on:
        filters["from_date"] = ["<=", str(getdate(on))]
    names = frappe.get_all(ASSIGNMENT, filters=filters, pluck="name",
                           order_by="from_date desc", limit=1)
    return names[0] if names else None


def monthly_gross(employee, on=None):
    """The monthly gross of the employee's salary structure, from the
    assignment in force on `on` (the latest when no day is given), with the
    allowances they are paid every month besides it. 0 when the employee
    has no assignment."""
    name = assignment_on(employee, on) if employee else None
    if not name:
        return 0
    assignment = frappe.get_doc(ASSIGNMENT, name)
    frequency = frappe.db.get_value("Salary Structure", assignment.get("salary_structure"), "payroll_frequency")
    if hasattr(type(assignment), "calculate_ctc_and_gross"):
        assignment.calculate_ctc_and_gross()
        structure = flt(assignment.annual_gross_earning) / rules.periods_in_year(frequency)
    else:
        structure = _previewed_gross(assignment, on)
    allowances = standing_allowances(employee, on)
    # what the structure pays per component matters only to an allowance that
    # takes a component's place
    replacing = any(int(flt(row.get("overwrite"))) for row in allowances)
    period = rules.gross_per_period(structure, allowances, _structure_amounts(assignment) if replacing else {})
    return flt(rules.per_month(period, frequency), 2)


def standing_allowances(employee, on=None):
    """The earnings the employee is paid every pay period as recurring
    Additional Salary, in force on `on` (today when no day is given)."""
    day = getdate(on) if on else getdate(today())
    found = frappe.get_all(ADDITIONAL, filters={"employee": employee, "docstatus": 1, "is_recurring": 1,
                                                "from_date": ["<=", str(day)]},
                           fields=["salary_component", "amount", "type", "is_recurring", "disabled", "from_date",
                                   "to_date", "overwrite_salary_structure_amount"], limit_page_length=0)
    rows = [{"salary_component": row.salary_component, "amount": row.amount, "type": row.type,
             "is_recurring": row.is_recurring, "disabled": row.disabled, "from_date": row.from_date,
             "to_date": row.to_date, "overwrite": row.overwrite_salary_structure_amount} for row in found]
    components = {row["salary_component"] for row in rows if row["salary_component"]}
    return rules.standing(rows, day, {name for name in components if _not_counted(name)})


def _not_counted(component):
    """A component a salary slip leaves out of its gross."""
    flags = frappe.db.get_value("Salary Component", component, ["statistical_component", "do_not_include_in_total"],
                                as_dict=True)
    return bool(flags and (flags.get("statistical_component") or flags.get("do_not_include_in_total")))


def _structure_amounts(assignment):
    """{component: what the structure pays for it in a period}, for the
    earnings a slip counts in its gross; nothing on a Frappe HR that cannot
    say."""
    if not hasattr(type(assignment), "_evaluate_all_components"):
        return {}
    _data, rows = assignment._evaluate_all_components()
    return {row.get("salary_component"): flt(row.get("default_amount")) for row in rows.get("earnings") or []
            if not row.get("statistical_component") and not row.get("do_not_include_in_total")}


def assignment_gross(assignment):
    """The monthly gross a Salary Structure Assignment (saved or not) works
    out to from its structure alone; None on a Frappe HR that cannot say."""
    if not hasattr(type(assignment), "calculate_ctc_and_gross"):
        return None
    assignment.calculate_ctc_and_gross()
    return flt(flt(assignment.annual_gross_earning) / 12, 2)


def _previewed_gross(assignment, on):
    """For a Frappe HR without calculate_ctc_and_gross: the gross of a salary
    slip previewed from the structure (full payment days), without the
    month's additional salary."""
    from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

    slip = make_salary_slip(assignment.salary_structure, employee=assignment.employee,
                            posting_date=str(getdate(on)) if on else None, for_preview=1)
    return flt(sum(flt(row.amount) for row in slip.get("earnings") or []
                   if not row.get("additional_salary") and not row.get("do_not_include_in_total")), 2)
