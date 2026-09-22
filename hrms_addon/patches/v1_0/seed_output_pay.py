# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The three earnings output pay is written to, and Output Pay Settings
pointing at them (minutes §4.6).

Each is an Earning, taxable like any other pay, and made with "depends on
payment days" off: the output is already what was earned, and pro-rating
it by the days attended would take a missed day off twice.

A component somebody already made under the same name is left exactly as
it is, and so is a settings page somebody already filled in. Safe to run
twice.
"""

import frappe

SETTINGS = "Output Pay Settings"
COMPONENTS = (("per_meter_component", "Per Meter Earnings", "PME", "Per Meter"),
              ("per_piece_component", "Per Piece Earnings", "PPE", "Per Piece"),
              ("hourly_component", "Hourly Earnings", "HRE", "Hourly"))


def execute():
    if not frappe.db.exists("DocType", "Salary Component"):
        return
    for _field, name, abbr, section in COMPONENTS:
        if frappe.db.exists("Salary Component", name):
            continue
        component = frappe.get_doc({
            "doctype": "Salary Component", "salary_component": name, "salary_component_abbr": abbr,
            "type": "Earning", "depends_on_payment_days": 0, "is_tax_applicable": 1,
            "description": "%s pay, from the Output Pay Run (minutes §4.6)." % section})
        component.flags.ignore_permissions = True
        component.insert()
    if not frappe.db.exists("DocType", SETTINGS):
        return
    stored = frappe.db.get_singles_dict(SETTINGS) or {}
    doc = frappe.get_single(SETTINGS)
    touched = False
    for field, name, _abbr, _section in COMPONENTS:
        if not stored.get(field):
            doc.set(field, name)
            touched = True
    if not stored.get("standard_hours"):
        doc.standard_hours = 10
        touched = True
    if touched:
        doc.flags.ignore_permissions = True
        doc.save()
