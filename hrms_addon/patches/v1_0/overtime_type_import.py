"""Overtime Types may be imported by those who keep them (Luuka, 11 Nov 2026:
"Overtime Type is not available for data import"). Frappe HR's Overtime Type
allows import, but gives no role the import right, so only Administrator saw
it in Data Import, and the casuals' Overtime Type could not be imported by HR.
The HR Manager and the System Manager, who make and change the types, are
given it (security.grant, as Role Permission Manager would). Safe to run twice."""

import frappe

DOCTYPE = "Overtime Type"
IMPORTERS = ("System Manager", "HR Manager")


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    from hrms_addon.hrms_addon import security

    security.grant({DOCTYPE: {role: ("import",) for role in IMPORTERS}})
