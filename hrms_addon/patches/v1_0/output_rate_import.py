"""Sizes and Work Units may be imported (Data Import): the doctype allows it
(output_rate.json), and those who keep it may import into it. On a site where
the security setup has made Custom DocPerm rules for it, Frappe reads only
those, so the import right is granted there too. Safe to run twice."""

import frappe

DOCTYPE = "Output Rate"
IMPORTERS = ("System Manager", "HR Manager", "Payroll Officer", "HR User")


def execute():
    if not frappe.db.exists("DocType", DOCTYPE) or not frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}):
        return
    from hrms_addon.hrms_addon import security

    security.grant({DOCTYPE: {role: ("import",) for role in IMPORTERS}})
