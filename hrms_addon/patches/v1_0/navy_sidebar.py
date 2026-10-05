# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The navy sidebar (Luuka, 5 Oct 2026: "option A with golden highlighter").

The stylesheet ships the navy now, but HRMS Addon Theme Settings lays its
saved colours over it, and "Reset to Defaults" saves the defaults of the
day: a site that pressed it holds the old steel blue, which would keep the
sidebar as it was. Those are moved onto the new defaults. A colour someone
chose themselves is left as it is. Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import theme

SETTINGS = "HRMS Addon Theme Settings"


def execute():
    if not frappe.db.exists("DocType", SETTINGS):
        return
    for fieldname, former in theme.FORMER_DEFAULTS.items():
        saved = (frappe.db.get_single_value(SETTINGS, fieldname) or "").strip()
        if saved.upper() == former.upper():
            frappe.db.set_single_value(SETTINGS, fieldname, theme.DEFAULTS[fieldname])
    frappe.clear_cache(doctype=SETTINGS)
