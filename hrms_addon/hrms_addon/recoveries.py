# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the payroll took, marked back onto what it was taken for.

A staff loan (loans.py), a penalty (penalties.py) and an advance
(advances.py) are each recovered through Additional Salary deductions, one
a month. The Salary Slip that carries a deduction is the proof it was
taken: when the slip is submitted, that month is marked recovered on the
loan, penalty or advance and what is outstanding falls; when the slip is
cancelled, the month is unmarked and the balance goes back up.

Once a day, anything a slip took that is not marked yet is caught up —
slips submitted before this was installed, or while it failed.
"""

import frappe
from frappe import _
from frappe.utils import today

# the child table a schedule is kept in -> the documents that keep one there
SCHEDULES = {
    "Loan Repayment": ("Employee Loan", "Employee Penalty"),
    "Advance Recovery": ("Employee Advance",),
}


def _refreshers():
    from hrms_addon.hrms_addon import advances, loans, penalties

    return {"Employee Loan": loans.refresh_recovered, "Employee Penalty": penalties.refresh_recovered,
            "Employee Advance": advances.refresh_recovered}


def slip_on_submit(doc, method=None):
    mark(_deductions(doc), 1)


def slip_on_cancel(doc, method=None):
    mark(_deductions(doc), 0)


def _deductions(slip):
    return [row.get("additional_salary") for row in slip.get("deductions") or [] if row.get("additional_salary")]


def mark(additional_salaries, recovered, parent=None):
    """Mark the schedule rows these deductions pay as recovered (1) or not
    (0), and bring each document they belong to up to date."""
    if not additional_salaries:
        return 0
    refresh = _refreshers()
    touched = set()
    for child, parents in SCHEDULES.items():
        filters = {"additional_salary": ["in", list(additional_salaries)], "parenttype": ["in", list(parents)]}
        if parent:
            filters["parent"] = parent
        for row in frappe.get_all(child, filters=filters, fields=["name", "parent", "parenttype", "recovered"]):
            if int(row.recovered or 0) == recovered:
                continue
            frappe.db.set_value(child, row.name, "recovered", recovered, update_modified=False)
            touched.add((row.parenttype, row.parent))
    for parenttype, name in sorted(touched):
        refresh[parenttype](name)
    return len(touched)


def catch_up(parent=None):
    """Months a submitted slip has taken that are not marked yet."""
    names = []
    for child, parents in SCHEDULES.items():
        filters = {"recovered": ["!=", 1], "additional_salary": ["is", "set"],
                   "parenttype": ["in", list(parents)], "payroll_date": ["<=", today()]}
        if parent:
            filters["parent"] = parent
        names += frappe.get_all(child, filters=filters, pluck="additional_salary", limit_page_length=0)
    if not names:
        return 0
    taken = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 1,
                                                     "additional_salary": ["in", names]},
                           pluck="additional_salary", limit_page_length=0)
    return mark(set(taken), 1, parent)


@frappe.whitelist(methods=["POST"])
def catch_up_for(doctype, name):
    """The form's Mark Recovered button: this one document, now."""
    if doctype not in _refreshers():
        frappe.throw(_("{0} is not recovered from the payroll.").format(doctype))
    frappe.has_permission(doctype, "write", name, throw=True)
    return catch_up(parent=name)


def daily():
    catch_up()
    frappe.db.commit()
