"""Attendance Verification is verified by each branch's HR Officer (Luuka, 16 Nov 2026: "attendace verification
should be done by the HR officer for each branch"). A sheet left waiting for the General Manager goes back to Draft,
for its HR Officer to verify, and the General Manager's to-do on it is closed. Safe to run twice."""

import frappe

DOCTYPE = "Attendance Verification"
WAS_WAITING = "Pending General Manager"


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    waiting = sorted(set(frappe.get_all(DOCTYPE, filters={"docstatus": 0, "workflow_state": WAS_WAITING}, pluck="name"))
                     | set(frappe.get_all(DOCTYPE, filters={"docstatus": 0, "status": WAS_WAITING}, pluck="name")))
    for name in waiting:
        frappe.db.set_value(DOCTYPE, name, {"workflow_state": "Draft", "status": "Draft"}, update_modified=False)
    if waiting:
        for todo in frappe.get_all("ToDo", filters={"reference_type": DOCTYPE, "reference_name": ["in", waiting],
                                                    "status": "Open"}, pluck="name"):
            frappe.db.set_value("ToDo", todo, "status", "Cancelled", update_modified=False)
