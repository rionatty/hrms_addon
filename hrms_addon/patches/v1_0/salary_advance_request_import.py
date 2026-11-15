"""Salary advance requests may be imported (Data Import) by the HR Manager (Luuka, 15 Nov 2026: "add salary advance
import file under data import"). The doctype allows it (salary_advance_request.json); on a site where the security
setup has made Custom DocPerm rules for it, Frappe reads only those, so the import right is granted there too. A
request imported with Submit After Import comes in approved (salary_advances._approved_on_import). Safe to run
twice."""

import frappe

DOCTYPE = "Salary Advance Request"


def execute():
    if not frappe.db.exists("DocType", DOCTYPE) or not frappe.db.exists("Custom DocPerm", {"parent": DOCTYPE}):
        return
    from hrms_addon.hrms_addon import security
    from hrms_addon.hrms_addon.advance_request_approval import IMPORTERS

    security.grant({DOCTYPE: {role: ("import",) for role in IMPORTERS}})
