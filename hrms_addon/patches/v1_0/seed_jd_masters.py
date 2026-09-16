# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the Job Description tables' pick lists on sites that already have the app.

The Relationship, Type, Level and Horizon dropdowns of the Job Description
tables change from fixed Select options to Links to masters HR can extend,
and the new ISO Responsibilities, Ideal Job Specifications and Competency
Framework tables pick from lists of their own.

ORDER MATTERS (patches.txt). After jd_text_sections_to_tables, so every
value it moved into the tables is seeded too. Before
jd_profile_sections_to_tables, whose rows use the seeded standards,
specification types and competency categories. Both are post_model_sync:
the master tables exist only after the model sync.
"""

from hrms_addon.hrms_addon.pick_lists import seed_jd_masters


def execute():
    seed_jd_masters()
