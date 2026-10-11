# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A shift's own hours (Luuka, 11 Oct 2026: "add parameter set for
overtime hours, currently it is two hours"). Each Shift Type now says how
long it is and how many of its hours are overtime; the Day and Night shifts
already on the site are given the twelve with two they have always been
read as, so nothing changes until HR change it. A shift left blank, the
office day included, goes on being read as twelve with two.

The fields are synced first: fixtures follow the patches on a migrate.
Safe to run twice."""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import shifts


def execute():
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype="Shift Type")
    shifts.fill_shift_hours()
