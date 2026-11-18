"""The board reads the board pack (18 Nov 2026): the Board Member role, and its right to read the HR Board Report and
the month builds. Those two doctypes already carry their rules as Custom DocPerm on a site where security.py has run,
so the role named in their JSON never reaches it: it is granted here, as security.grant grants."""

import frappe

READ = ("read", "report", "print", "export")


def execute():
    from hrms_addon.hrms_addon import security

    if not frappe.db.exists("Role", "Board Member"):
        frappe.get_doc({"doctype": "Role", "role_name": "Board Member", "desk_access": 1}).insert(
            ignore_permissions=True)
    security.grant({doctype: {"Board Member": READ} for doctype in ("HR Board Report", "HR Monthly Snapshot")
                    if frappe.db.exists("DocType", doctype)})
