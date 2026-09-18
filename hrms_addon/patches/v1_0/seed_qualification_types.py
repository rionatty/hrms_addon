# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed Qualification Type on sites that already have the app.

The Bio-Data's qualifications now say whether each is academic or a
certification / licence, which the interview shortlist lists in its own
column. post_model_sync: the master table exists only after the model sync.
New installs are seeded by pick_lists.after_install.
"""

from hrms_addon.hrms_addon.pick_lists import seed_qualification_types


def execute():
    seed_qualification_types()
