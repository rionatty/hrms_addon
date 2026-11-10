"""A casual's hourly rate leaves the employee's record for an Hourly Rate of its own,
which only HR open (Luuka, 10 Nov 2026: "what if the employee updates his her
personal rate?"). Each rate already on an employee becomes their Hourly Rate
from the day they joined, so a slip worked out again pays the days it paid;
then the field goes from the employee. Safe to run twice."""

import frappe
from frappe.utils import getdate

FIELD = "custom_hourly_rate"
CUSTOM_FIELD = "Employee-custom_hourly_rate"
RATE = "Hourly Rate"
# where a casual has no joining date: before any weekly payroll
EARLIEST = "2025-01-01"


def execute():
    if not frappe.db.exists("DocType", RATE):
        return
    if frappe.db.has_column("Employee", FIELD):
        have = set(frappe.get_all(RATE, pluck="employee", limit_page_length=0))
        for row in frappe.get_all("Employee", filters={FIELD: [">", 0]},
                                  fields=["name", FIELD, "date_of_joining"], limit_page_length=0):
            if row.name in have:
                continue
            rate = frappe.get_doc({"doctype": RATE, "employee": row.name, "rate": row.get(FIELD),
                                   "from_date": getdate(row.date_of_joining or EARLIEST),
                                   "notes": "Moved from the employee's record."})
            rate.flags.ignore_permissions = True
            rate.insert()
    if frappe.db.exists("Custom Field", CUSTOM_FIELD):
        frappe.delete_doc("Custom Field", CUSTOM_FIELD, ignore_permissions=True, force=True)
