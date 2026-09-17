# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Seed Uganda's districts and more spoken languages.

The online Job Application Form (/apply) asks candidates for their home and
current district and the languages they speak. A candidate can only pick an
existing value, so these two lists must be filled before the form is used;
they started empty (District) and with three values (Spoken Language).

Adds only what is missing: seed_plan skips any value already there, ignoring
case, so the values HR added themselves are kept.
"""

from hrms_addon.hrms_addon import bio_data_rules
from hrms_addon.hrms_addon.pick_lists import seed_masters

MASTERS = ("District", "Spoken Language")


def execute():
    seed_masters({master: bio_data_rules.BIO_DATA_MASTERS[master] for master in MASTERS})
