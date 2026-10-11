# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""An Off Duty Request the Supervisor, the Section Manager or the HR Manager
refused was saved as Approved: refusing submits the form, and the submit
step wrote "Approved" whatever had been decided. So a refused day printed
as off duty on the register, was left out of the absences a salary advance
counts, and the employee was told it was approved.

The workflow's own state was always right, and the status is put back to
it. Nothing else is touched: no attendance was ever marked from these.
Safe to run twice."""

import frappe


def execute():
    if not frappe.db.has_column("Off Duty Request", "workflow_state"):
        return
    wrong = frappe.get_all("Off Duty Request", filters={"workflow_state": "Rejected", "status": ["!=", "Rejected"],
                                                        "docstatus": 1}, pluck="name")
    for name in wrong:
        frappe.db.set_value("Off Duty Request", name, "status", "Rejected", update_modified=False)
    if wrong:
        print("HRMS Addon: %d refused off-duty request(s) now read Rejected: %s" % (len(wrong), ", ".join(wrong)))
