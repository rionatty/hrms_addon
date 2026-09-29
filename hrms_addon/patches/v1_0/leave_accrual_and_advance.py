# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Leave earned by the days worked, and the Leave Advance on its own.

1. Leave Management Settings take the leave advance rules Advance Settings
   held (60% of gross, the Per Meter months, more than 19 days, regular
   staff only, no loans, the employment types that are not regular), once,
   so nothing Luuka had set is lost; Advance Settings no longer shows them.
2. Annual Leave becomes earned leave (Frappe HR's own Is Earned Leave,
   monthly, on the last day, not rounded), which is what the leave earned
   by the days worked is read from. Not where Annual Leave already has an
   allocation made through a Leave Policy Assignment for this year or later:
   Frappe HR would then credit it again each month on top of the full year
   and refuse, every month, for everyone. HR tick it there themselves once
   those allocations are replaced.
"""

import frappe
from frappe.utils import getdate, today

from hrms_addon.hrms_addon import leave_advance_rules

SETTINGS = "Leave Management Settings"
ANNUAL = "Annual Leave"
MOVED = {"leave_percent": "advance_percent", "leave_per_meter_months": "per_meter_months",
         "leave_more_than_days": "more_than_days", "leave_regular_only": "regular_only", "leave_no_loans": "no_loans"}


def execute():
    if frappe.db.exists("DocType", SETTINGS):
        _settings()
    _annual_leave()


def _settings():
    if frappe.db.get_singles_dict(SETTINGS):
        return  # saved before: Luuka's own
    doc = frappe.get_single(SETTINGS)
    if frappe.db.exists("DocType", "Advance Settings"):
        stored = frappe.db.get_singles_dict("Advance Settings") or {}
        moved = {new: stored[old] for old, new in MOVED.items() if stored.get(old) not in (None, "")}
        # values the settings would refuse stay at their defaults rather than
        # stopping the migrate; HR can set them on the form
        if not leave_advance_rules.settings_errors(leave_advance_rules.settings_from(moved)):
            for field, value in moved.items():
                doc.set(field, value)
        for kind in frappe.get_all("Advance Employment Type", filters={"parent": "Advance Settings",
                                                                      "parenttype": "Advance Settings"},
                                   pluck="employment_type"):
            doc.append("not_regular_types", {"employment_type": kind})
    doc.recovery_component = leave_advance_rules.RECOVERY_COMPONENT
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    # an employment type deleted since must not stop the migrate either; the
    # form checks the links when it is next saved
    doc.flags.ignore_links = True
    doc.save()


def _annual_leave():
    if not frappe.db.exists("Leave Type", ANNUAL):
        return
    if frappe.db.get_value("Leave Type", ANNUAL, "is_earned_leave"):
        return
    start = getdate("%d-01-01" % getdate(today()).year)
    if frappe.get_all("Leave Allocation", filters={"leave_type": ANNUAL, "docstatus": 1, "to_date": [">=", start],
                                                   "leave_policy_assignment": ["is", "set"]}, limit=1):
        return
    frappe.db.set_value("Leave Type", ANNUAL, {"is_earned_leave": 1, "earned_leave_frequency": "Monthly",
                                               "allocate_on_day": "Last Day", "rounding": ""})
