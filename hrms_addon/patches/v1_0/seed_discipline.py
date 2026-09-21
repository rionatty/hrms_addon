# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The disciplinary ladder and the misconduct Luuka's HR manual lists, on
a site that has the app already; a fresh install gets them from
after_install.

They are seeded as master data rather than written into the code so HR can
amend them without a developer, which is what the Organisation & System
Setup script asks for.
"""

import frappe

from hrms_addon.hrms_addon import discipline


def execute():
    made = discipline.seed_discipline_masters()
    if made:
        frappe.db.commit()
        print("HRMS Addon: seeded %d disciplinary master(s)" % len(made))
