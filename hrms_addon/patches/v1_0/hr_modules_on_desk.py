# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's modules on the desk itself, not inside Frappe HR's tile.

The Frappe HR tile is taken off the desk in HRMS Addon Branding > Desk
Modules, which leaves each of its modules (Leaves, Payroll, Loans and the
rest) a tile of its own on the desk; a module taken off before stays off.
Saved desktops follow (desk_modules.apply). Ticking Frappe HR again there
puts the tile back.

Where the CyveTech UI app decides the desk, this does nothing.
"""

import frappe

from hrms_addon.hrms_addon import desk_modules


def execute():
    if not desk_modules.available():
        return
    group = desk_modules.app_tile("hrms")
    if not group:
        return
    if not desk_modules.saved_rows():
        # never filled in: the table comes in with the desk as it is now
        settings = frappe.get_single(desk_modules.SETTINGS)
        desk_modules.refresh_rows(settings)
        settings.flags.ignore_permissions = True
        settings.flags.ignore_mandatory = True
        settings.save()
    frappe.db.set_value(desk_modules.CHILD, {"parenttype": desk_modules.SETTINGS, "parent": desk_modules.SETTINGS,
                                             "parentfield": desk_modules.TABLE, "module": group},
                        "show_on_desk", 0, update_modified=False)
    desk_modules.apply()
