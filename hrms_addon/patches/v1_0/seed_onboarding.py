# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed Luuka's onboarding on sites that already have the app.

The two Employee Onboarding Templates (standard and production) and the
Workplace Rules and Regulations (LPL/HR/05, as Terms and Conditions the
onboarding's print format prints). Adds only what is missing; new installs
are seeded by onboarding.after_install.
"""

from hrms_addon.hrms_addon.onboarding import seed_onboarding


def execute():
    seed_onboarding()
