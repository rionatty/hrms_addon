# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Cancelling an advance run, the part Salary Advance Processing
(salary_advances.py) and Leave Advance Processing (leave_advances.py) share.

The rules are in advance_run_rules.py.

  recovered_on          the salary slip that has already taken a recovery
  take_back_bank_entry  the run's bank entry, deleted or cancelled with it
  journal_on_cancel     Finance cancelling the bank entry on its own
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import advance_run_rules as rules

ENTRY = "Journal Entry"


def recovered_on(doctype, names):
    """(advance, salary slip) for the first of these advances a submitted
    salary slip has taken a recovery of, or None."""
    names = [name for name in names if name]
    if not names:
        return None
    deductions = frappe.get_all("Additional Salary", filters={"ref_doctype": doctype, "ref_docname": ["in", names],
                                                              "docstatus": 1},
                                fields=["name", "ref_docname"], order_by="ref_docname asc", limit_page_length=0)
    if not deductions:
        return None
    taken = frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 1,
                                                     "additional_salary": ["in", [row.name for row in deductions]]},
                           fields=["parent", "additional_salary"], limit_page_length=0)
    return rules.first_taken([(row.name, row.ref_docname) for row in deductions],
                             {row.additional_salary: row.parent for row in taken})


def take_back_bank_entry(doc, title):
    """The run's bank entry goes with the run. Returns what was done."""
    name = doc.get("journal_entry")
    if not name or not frappe.db.exists(ENTRY, name):
        return rules.NOTHING
    step = rules.bank_entry_step(frappe.db.get_value(ENTRY, name, "docstatus"),
                                 frappe.has_permission(ENTRY, "cancel", name))
    if step == rules.REFUSE:
        frappe.throw(_("Bank entry {0} is posted. Finance cancel it first.").format(name), title=_(title))
    if step == rules.CANCEL:
        # _cancel, not cancel: ERPNext queues the cancel of an entry of more
        # than 100 lines for later, and the advances it pays cannot be taken
        # back while it stands
        frappe.get_doc(ENTRY, name)._cancel()
        frappe.msgprint(_("Bank entry {0} is cancelled.").format(name), alert=True)
    elif step == rules.DELETE:
        # a document something names cannot be deleted: the run lets go first
        doc.db_set("journal_entry", None, update_modified=False)
        frappe.delete_doc(ENTRY, name, ignore_permissions=True)
    return step


def journal_on_cancel(doc, method=None):
    """A run's bank entry cancelled on its own: the run that names it is not
    a document to cancel first. What the payment put on the payroll comes
    off (advances.payment_on_cancel, leave_advances.payment_on_cancel)."""
    doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + rules.BANK_ENTRY_KEPT_BY
