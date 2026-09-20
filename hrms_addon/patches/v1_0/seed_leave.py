# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The five kinds of leave LPL/HR/15 offers, on a site that has the app
already; a fresh install gets them from after_install.

A Leave Type Luuka has already set up is left exactly as it is — the days
seeded here are the Employment Act minima, and what an employee is really
owed is their Leave Allocation.
"""

import frappe

from hrms_addon.hrms_addon import leave


def execute():
    made = leave.seed_leave_types()
    if made:
        frappe.db.commit()
        print("HRMS Addon: seeded leave types %s" % ", ".join(made))
