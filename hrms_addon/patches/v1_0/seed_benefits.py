# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The five lines LPL.HR.31 prints and the standard claims Luuka pay, on a
site that has the app already; a fresh install gets them from after_install.

The standard claims are created at nil and marked standard, because what
each is worth is Luuka's to set, not ours to guess.
"""

import frappe

from hrms_addon.hrms_addon import allowances, benefits


def execute():
    made = allowances.seed_allowance_lines() + benefits.seed_standard_claims()
    if made:
        frappe.db.commit()
        print("HRMS Addon: seeded expense claim types %s" % ", ".join(made))
