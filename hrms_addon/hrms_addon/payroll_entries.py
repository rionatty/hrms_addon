# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll run's salary slips made again on the same run, where Frappe HR
asks for the run to be cancelled and amended (the rules: payroll_entry_rules.py;
scripts/verify_payroll_recreate.py).

  recreate_salary_slips   Recreate Salary Slips on the run
                          (public/js/payroll_entry.js): its draft slips are
                          deleted and made again in the background, from the
                          salary structure, attendance and additional salary
                          as they are now

The run shows Queued while it works, as it does while Frappe HR makes slips,
and Failed with the reason where it cannot finish, as Frappe HR shows it.
Frappe HR's Create Salary Slips then makes those still missing, and the
button deletes and makes them all again.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import payroll_entry_rules as rules
from hrms_addon.hrms_addon import payroll_months

DOCTYPE = "Payroll Entry"
SLIP = "Salary Slip"
REMAKE = "hrms_addon.hrms_addon.payroll_entries.remake"
TIMEOUT = 3000  # seconds to delete the drafts of a large run, one by one


@frappe.whitelist(methods=["POST"])
def recreate_salary_slips(payroll_entry):
    """The run's draft slips deleted and made again in the background. Returns how many drafts there were."""
    run = frappe.get_doc(DOCTYPE, payroll_entry)
    run.check_permission("write")
    payroll_months.refuse_closed(run)
    submitted = frappe.db.count(SLIP, {"payroll_entry": run.name, "docstatus": 1})
    posted = len(frappe.get_all("Journal Entry Account", filters={"reference_type": DOCTYPE, "reference_name": run.name,
                                                                 "docstatus": ["<", 2]}, pluck="parent", distinct=True))
    why = rules.why_not_recreate(run.docstatus, run.status, run.salary_slips_submitted, submitted, posted)
    if why:
        frappe.throw(_(why), title=_("Recreate Salary Slips"))
    # each branch's days verified first, as when the slips were first made (attendance_verification.py)
    from hrms_addon.hrms_addon import attendance_verification

    attendance_verification.refuse_payroll(run)
    drafts = frappe.db.count(SLIP, {"payroll_entry": run.name, "docstatus": 0})
    run.db_set({"status": rules.RUNNING, "salary_slips_created": 0, "error_message": ""})
    frappe.enqueue(REMAKE, queue="long", timeout=TIMEOUT, payroll_entry=run.name, enqueue_after_commit=True)
    return drafts


def remake(payroll_entry):
    """The background half: the drafts deleted with the user's own permissions, then the slips made as Frappe HR
    makes them on submit. Where it cannot finish, the run shows Failed and why, as Frappe HR shows it."""
    run = frappe.get_doc(DOCTYPE, payroll_entry)
    try:
        for name in frappe.get_all(SLIP, filters={"payroll_entry": run.name, "docstatus": 0}, pluck="name"):
            frappe.delete_doc(SLIP, name)
        frappe.db.commit()
        run.reload()
        run.create_salary_slips()
    except Exception as error:
        frappe.db.rollback()
        from hrms.payroll.doctype.payroll_entry.payroll_entry import log_payroll_failure

        log_payroll_failure("recreation", run, error)
        frappe.db.commit()
