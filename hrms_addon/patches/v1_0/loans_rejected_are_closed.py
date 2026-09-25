# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A loan request refused before 25 September 2026 was submitted as if it
ran: Running, the amount asked for owed (blocking every later request and
counted in a leaver's final settlement) and, where Accounts had set its
terms, payroll deductions made. It owes nothing and takes nothing.

Deductions a salary slip has already taken are left as they are and
written to the Error Log, to be refunded. Safe to run twice.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Employee Loan"):
        return
    from hrms_addon.hrms_addon import loans

    for name in frappe.get_all("Employee Loan", filters={"docstatus": 1, "approval_status": "Rejected"},
                               pluck="name"):
        doc = frappe.get_doc("Employee Loan", name)
        taken = [row.additional_salary for row in doc.repayments
                 if row.additional_salary and loans._taken(row.additional_salary)]
        loans.close_rejected(doc)
        if taken:
            frappe.log_error(title="HRMS Addon: refused loan %s had deductions taken" % name,
                             message="Refund these to the employee: %s" % ", ".join(taken))
