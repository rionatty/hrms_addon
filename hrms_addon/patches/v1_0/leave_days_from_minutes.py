# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The leave types, set to the minutes of 16 and 20 July 2026 (Reward and
Compensation, §4.3).

They were first seeded from the Employment Act's minima: sick leave 30
days, compassionate 7, annual capped at 21, without-pay unlimited. The
minutes say sick leave is 60 days at full pay and 120 more at half pay,
compassionate 4, without-pay at most 60, and annual 21, 28 or 30 with the
unused days of administration staff carried forward with no maximum.

A cap of 21 on Annual Leave was worse than a wrong number: Frappe HR
refuses an allocation over the type's maximum and cuts carried-forward
days back to it, so the 28- and 30-day allowances could not be given and
the carry-forward was quietly eaten.

A type is changed only where it still holds exactly what the seed first
wrote — one Luuka has set up themselves is left as they set it. The
half-pay sick leave is made if it is missing. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import leave, leave_rules as rules


def execute():
    if not frappe.db.exists("DocType", "Leave Type"):
        return
    leave.seed_leave_types()  # makes Sick Leave (Half Pay), and any other that is missing
    for name, former in rules.FORMER_DAYS.items():
        if not frappe.db.exists("Leave Type", name):
            continue
        if int(frappe.db.get_value("Leave Type", name, "max_leaves_allowed") or 0) != former:
            continue
        values = leave.leave_type_values(name)
        if name == rules.ANNUAL:
            # only the cap is the seed's to take back; the rest is Luuka's
            values = {"max_leaves_allowed": values["max_leaves_allowed"]}
        if name == rules.UNPAID and frappe.db.get_value("Leave Type", name, "max_continuous_days_allowed"):
            values.pop("max_continuous_days_allowed", None)
        frappe.db.set_value("Leave Type", name, values)
