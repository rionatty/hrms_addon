# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the training module on sites that already have the app: the items of
Section A of the Training Evaluation Form (LPL/TRG/FRM05). New installs are
seeded by pick_lists.seed_training_masters in after_install.
"""

from hrms_addon.hrms_addon.pick_lists import seed_training_masters


def execute():
    seed_training_masters()
