# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the Job Applicant Bio-Data pick lists on sites that already have the app.

District, Relationship, Spoken Language and Examination Level are new
masters behind the Bio-Data tab (Pre-Interview Bio-Data Form, LPL/HR/19).
post_model_sync: the master tables exist only after the model sync.
"""

from hrms_addon.hrms_addon.pick_lists import seed_bio_data_masters


def execute():
    seed_bio_data_masters()
