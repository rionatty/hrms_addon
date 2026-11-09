# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The UGX Allowance as a line of every USD structure (Luuka, 9 Nov 2026:
"allowances should be on the salary structure"), on a site where
usd_gross_up has already run: its component made if the site has none, and
the structure's lines written again (usd_gross_up.execute, safe to run
twice)."""

from hrms_addon.patches.v1_0 import usd_gross_up


def execute():
    usd_gross_up.execute()
