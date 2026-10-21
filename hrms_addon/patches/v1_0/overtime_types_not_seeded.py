# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The four Overtime Types the migrate used to make are taken off the site
where nobody uses them (Luuka, 21 Oct 2026: "dont predefine any overtime
type you should pick from the one assigned"). The types are Luuka's own,
and a person's is the one that lists them.

A seeded type is kept where it lists employees, or where a request, an
attendance, a slip or a shift names it: somebody has taken it up, and HR
delete it from the list once they are done with it. Frappe keeps what is
deleted under Deleted Documents. Safe to run twice.
"""

import frappe

TYPE = "Overtime Type"
SEEDED = ("Weekday Overtime", "Rest Day Overtime", "Public Holiday Overtime",
          "Weekday Overtime (Above UGX 500,000)")


def execute():
    if not frappe.db.table_exists(TYPE):
        return
    for name in SEEDED:
        if not frappe.db.exists(TYPE, name):
            continue
        if frappe.db.exists("Overtime Type Employee", {"parenttype": TYPE, "parent": name}):
            print("HRMS Addon: the Overtime Type %s is kept: it lists employees." % name)
            continue
        frappe.db.savepoint("seeded_overtime_type")
        try:
            frappe.delete_doc(TYPE, name, ignore_permissions=True)
        except frappe.LinkExistsError:
            frappe.db.rollback(save_point="seeded_overtime_type")
            print("HRMS Addon: the Overtime Type %s is kept: it is in use. Delete it from the list once it is not."
                  % name)
