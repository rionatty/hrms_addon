# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed the second part of the onboarding on sites that already have the app.

The Tool Providers (the department's own tools prepared by its Head of
Department), the ratable factors of the End of probation evaluation form
(LPL/HR/32), and Onboarding Settings saved with their defaults (six months'
probation, three months' extension, a 60% pass mark, contract alerts a year,
a quarter and a month before the end). New installs are seeded by
pick_lists.after_install and probation.after_install.
"""

from hrms_addon.hrms_addon.pick_lists import seed_onboarding_masters
from hrms_addon.hrms_addon.probation import save_default_settings


def execute():
    seed_onboarding_masters()
    save_default_settings()
