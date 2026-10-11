# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Pay Slip beside Luuka's own (12 Oct 2026). Their slip calls four
lines by other names than the site's Salary Components carry (HRA, NSSF,
PAYE, Advance Salary) and prints the deductions NSSF, PAYE, Local Service
Tax, then the advance. Each component now has a Name on Pay Slip and an
Order on Pay Slip, and this fills them for those lines where they are still
blank (payslip.seed_slip_names). The fields are synced first: fixtures
follow the patches on a migrate. Safe to run twice."""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import payslip


def execute():
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Salary Component")
    for name, values in sorted(payslip.seed_slip_names().items()):
        print("HRMS Addon: %s on the Pay Slip: %s" % (name, values))
