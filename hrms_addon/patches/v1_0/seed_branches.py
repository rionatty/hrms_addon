# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed Luuka's branches (Kawempe, Namanve, Matugga) on sites that already have the app.

Every approval now goes to the document's own branch (org_rules.py), so the
Job Requisition and the Job Opening need a Branch to pick. Adds only what is
missing, ignoring case. New installs are seeded by pick_lists.after_install.
"""

from hrms_addon.hrms_addon.pick_lists import seed_branches


def execute():
    seed_branches()
