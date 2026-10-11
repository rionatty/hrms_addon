# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The attendance review of 11 Oct 2026: the shifts already on a site,
marked from the clock, are given what the clock needs of them
(shifts.fill_clock_settings):

  a clock-out counts for longer after the shift ends, so somebody who
    worked on is not left with a clock-in alone, which reads as absent
  late arrivals and early departures are marked, past a grace
  work on a day off is marked, which the special overtime needs

Only a setting still at Frappe HR's default is changed. The new Attendance
fields are synced first: fixtures follow the patches on a migrate. Safe to
run twice."""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import shifts


def execute():
    sync_fixtures("hrms_addon")
    for doctype in ("Shift Type", "Attendance"):
        frappe.clear_cache(doctype=doctype)
    changed = shifts.fill_clock_settings()
    for name, fields in sorted(changed.items()):
        print("HRMS Addon: %s now has %s" % (name, ", ".join(fields)))
