# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What the payroll took, marked back onto what it was taken for.

A staff loan (loans.py), a penalty (penalties.py), an advance
(advances.py) and a leave advance (leave_advances.py) are each recovered
through Additional Salary deductions, one a month. The Salary Slip that
carries a deduction is the proof it was taken: when the slip is
submitted, that month is marked recovered on the loan, penalty or advance
and what is outstanding falls; when the slip is cancelled, the month is
unmarked and the balance goes back up.

Once a day, anything a slip took that is not marked yet is caught up —
slips submitted before this was installed, or while it failed.

A deduction can be cancelled by itself while what it recovers stands (1 Nov
2026; Luuka: "its should allow canceling"). Frappe refuses a cancel while a
submitted document's row names the deduction, but runs on_cancel first, so
the row lets go there. It keeps the name of what was cancelled, so nothing
makes that month's deduction again, and the amount stays outstanding. A
deduction a submitted slip has taken is still refused: that money is paid.
Amending the cancelled deduction puts the new one back on the row.
"""

import frappe
from frappe import _
from frappe.utils import today

# the child table a schedule is kept in -> the documents that keep one there
SCHEDULES = {
    "Loan Repayment": ("Employee Loan", "Employee Penalty"),
    "Advance Recovery": ("Employee Advance",),
    "Leave Advance Recovery": ("Leave Advance",),
}
# a schedule's row: what it takes in a month, and the deduction cancelled by itself. A Data field, for a Link to a
# cancelled deduction would refuse the document it is on
INSTALMENT = {"Loan Repayment": "total", "Advance Recovery": "amount", "Leave Advance Recovery": "amount"}
CANCELLED = "cancelled_deduction"


def _refreshers():
    from hrms_addon.hrms_addon import advances, leave_advances, loans, penalties

    return {"Employee Loan": loans.refresh_recovered, "Employee Penalty": penalties.refresh_recovered,
            "Employee Advance": advances.refresh_recovered, "Leave Advance": leave_advances.refresh_recovered}


def slip_on_submit(doc, method=None):
    mark(_deductions(doc), 1)


def slip_on_cancel(doc, method=None):
    mark(_deductions(doc), 0)


def _deductions(slip):
    return [row.get("additional_salary") for row in slip.get("deductions") or [] if row.get("additional_salary")]


def addition_on_cancel(doc, method=None):
    """An Additional Salary cancelled. The instalment it is, of a document
    still standing, lets go of it (_let_go). And if a draft salary slip took
    it up, Frappe HR leaves its line on the slip, which would still pay or
    deduct it, so the slips to make again are named."""
    _let_go(doc)
    slips = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 0,
                                                     "additional_salary": doc.name},
                           pluck="parent", distinct=True, limit_page_length=0)
    if slips:
        frappe.msgprint(_("{0} is still on draft Salary Slip {1}. Delete the slip and create it again.").format(
            doc.get("salary_component"), ", ".join(slips)), title=_("Salary Slip"), indicator="orange")


def _let_go(deduction):
    """The row of a submitted loan, penalty or advance naming this deduction,
    which would refuse its cancel. A document being cancelled has taken its
    deductions back itself, and one taking back a payment lets go first."""
    for child, parents in SCHEDULES.items():
        for row in frappe.get_all(child, filters={"additional_salary": deduction.name, "parenttype": ["in", list(parents)],
                                                  "recovered": ["!=", 1]}, fields=["name", "parent", "parenttype"]):
            if frappe.db.get_value(row.parenttype, row.parent, "docstatus") != 1:
                continue
            frappe.db.set_value(child, row.name, {"additional_salary": None, CANCELLED: deduction.name},
                                update_modified=False)
            frappe.msgprint(_("{0} will not be deducted. It stays outstanding on {1}.").format(
                deduction.name, row.parent), title=_("Additional Salary"), indicator="orange")


def addition_on_submit(doc, method=None):
    """A cancelled deduction amended: the new one is that month's instalment,
    so the slip that takes it marks the month recovered."""
    if not doc.get("amended_from"):
        return
    for child, parents in SCHEDULES.items():
        for name in frappe.get_all(child, filters={CANCELLED: doc.amended_from, "parenttype": ["in", list(parents)]},
                                   pluck="name"):
            frappe.db.set_value(child, name, {"additional_salary": doc.name, CANCELLED: None,
                                              "payroll_date": doc.payroll_date, INSTALMENT[child]: doc.amount},
                                update_modified=False)


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
