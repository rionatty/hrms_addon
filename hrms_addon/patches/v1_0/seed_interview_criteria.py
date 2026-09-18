# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the interview score sheet's groups and criteria (LPL/HR/17) on sites
that already have the app. post_model_sync: the master tables exist only
after the model sync. New installs are seeded by interviews.after_install.
"""

from hrms_addon.hrms_addon.interviews import seed_interview_criteria


def execute():
    seed_interview_criteria()
