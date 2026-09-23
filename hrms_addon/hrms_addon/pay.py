# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An employee's pay as their salary structure works it out.

The gross is Frappe HR's own figure. The Salary Structure Assignment
evaluates the structure's formulas with its Base and Variable and counts
what a salary slip counts as gross (calculate_ctc_and_gross, shown on the
assignment as Annual Gross Earning). Statistical components and additional
salary are not part of it, and every earning is taken at full payment days.
"""

import frappe
from frappe.utils import flt, getdate


def assignment_on(employee, on=None):
    """The employee's submitted Salary Structure Assignment in force on
    `on`, or their latest when no day is given. None when they have none."""
    filters = {"employee": employee, "docstatus": 1}
    if on:
        filters["from_date"] = ["<=", str(getdate(on))]
    names = frappe.get_all("Salary Structure Assignment", filters=filters, pluck="name",
                           order_by="from_date desc", limit=1)
    return names[0] if names else None


def monthly_gross(employee, on=None):
    """The monthly gross of the employee's salary structure, from the
    assignment in force on `on` (the latest when no day is given). 0 when
    the employee has no assignment."""
    name = assignment_on(employee, on) if employee else None
    if not name:
        return 0
    assignment = frappe.get_doc("Salary Structure Assignment", name)
    if hasattr(type(assignment), "calculate_ctc_and_gross"):
        assignment.calculate_ctc_and_gross()
        return flt(flt(assignment.annual_gross_earning) / 12, 2)
    return _previewed_gross(assignment, on)


def _previewed_gross(assignment, on):
    """For a Frappe HR without calculate_ctc_and_gross: the gross of a salary
    slip previewed from the structure (full payment days), without the
    month's additional salary."""
    from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

    slip = make_salary_slip(assignment.salary_structure, employee=assignment.employee,
                            posting_date=str(getdate(on)) if on else None, for_preview=1)
    return flt(sum(flt(row.amount) for row in slip.get("earnings") or []
                   if not row.get("additional_salary") and not row.get("do_not_include_in_total")), 2)
