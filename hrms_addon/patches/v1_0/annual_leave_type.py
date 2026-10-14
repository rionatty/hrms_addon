# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave Management Settings' Annual Leave Type, filled where it is empty
with the leave type the site's leave policies give for annual leave
(Luuka's own "Annual"), so the settings show what the leave module reads.
Nothing is filled where the policies name none, or more than one that might
be it. Safe to run twice."""

import frappe

SETTINGS = "Leave Management Settings"


def execute():
    from hrms_addon.hrms_addon import leave

    if not frappe.db.exists("DocType", SETTINGS) or not frappe.get_meta(SETTINGS).has_field("annual_leave_type"):
        return
    if frappe.db.get_single_value(SETTINGS, "annual_leave_type"):
        return
    found = leave.found_annual_type()
    if found and frappe.db.exists("Leave Type", found):
        frappe.db.set_single_value(SETTINGS, "annual_leave_type", found)
