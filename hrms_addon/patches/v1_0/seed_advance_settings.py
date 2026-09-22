# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Advance Settings, saved once with the minutes' own numbers.

A Single that has never been saved shows its DocType defaults on the form
but stores nothing, and a report reading the table would find it empty.
Saving it once writes every default down where the advances read them.

It also fills in who is not a regular employee — every Employment Type
whose name says casual, which is how the attendance register already
tells a casual from a permanent (attendance_rules.tallies). Luuka can add
Probation, Intern or anything else they do not advance on the page itself.

A site that has already saved the page keeps what it saved. Safe to run
twice.
"""

import frappe

SETTINGS = "Advance Settings"


def execute():
    if not frappe.db.exists("DocType", SETTINGS):
        return
    stored = frappe.db.get_singles_dict(SETTINGS) or {}
    doc = frappe.get_single(SETTINGS)
    touched = not stored
    if not doc.get("not_regular_types") and frappe.db.exists("DocType", "Employment Type"):
        for name in frappe.get_all("Employment Type", pluck="name", order_by="name asc",
                                   limit_page_length=0):
            if "casual" in (name or "").lower():
                doc.append("not_regular_types", {"employment_type": name})
                touched = True
    if touched:
        doc.flags.ignore_permissions = True
        doc.save()
