# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Let HR User (the HR Officer) add Skills, on sites that already have the app.

The Bio-Data tab records the skills a candidate lists, picked from the Skill
list; HRMS lets HR User only read it. Run once; see
bio_data.allow_hr_user_to_add_skills.
"""

from hrms_addon.hrms_addon.bio_data import allow_hr_user_to_add_skills


def execute():
    allow_hr_user_to_add_skills()
