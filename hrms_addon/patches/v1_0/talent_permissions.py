# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent's permissions as the blueprint (section 8) has them, on a site
whose rules already live in Custom DocPerm (security.setup_on_migrate copies
them there, after which a doctype's own permissions no longer reach it).

  the Talent Council   reads and approves: it no longer creates, deletes,
                       cancels or amends placements or development plans, nor
                       creates or deletes reviews, nor deletes critical roles
  the executives       read placements, reviews and critical roles, the
                       boxes included, for Talent Command
  a Head of Department names successors (the bench is at level 1); the boxes
                       and flight risks on the bench are at level 2, for HR
                       and the council

This is the one place talent takes rights away, because the blueprint asks
for it. Safe to run twice.
"""

import frappe

RULES = (
    # doctype, role, level, rights on, rights off
    ("Talent Placement", "Talent Council", 0, ("read", "write", "submit"), ("create", "delete", "cancel", "amend")),
    ("Talent Placement", "General Manager", 0, ("read", "report", "print"), ()),
    ("Talent Placement", "Executive Director", 0, ("read", "report", "print"), ()),
    ("Talent Placement", "General Manager", 1, ("read",), ()),
    ("Talent Placement", "Executive Director", 1, ("read",), ()),
    ("Talent Program", "Talent Council", 0, ("read", "write", "submit"), ("create", "delete", "cancel", "amend")),
    ("Talent Review", "Talent Council", 0, ("read", "write"), ("create", "delete")),
    ("Talent Review", "General Manager", 0, ("read", "report", "print"), ()),
    ("Talent Review", "Executive Director", 0, ("read", "report", "print"), ()),
    ("Succession Position", "Talent Council", 0, ("read", "write", "create", "submit"), ("delete",)),
    ("Succession Position", "General Manager", 0, ("read", "report", "print"), ()),
    ("Succession Position", "Executive Director", 0, ("read", "report", "print"), ()),
    ("Succession Position", "General Manager", 1, ("read",), ()),
    ("Succession Position", "Executive Director", 1, ("read",), ()),
    ("Succession Position", "Head of Department", 1, ("read", "write"), ()),
    ("Succession Position", "System Manager", 2, ("read", "write"), ()),
    ("Succession Position", "HR Manager", 2, ("read", "write"), ()),
    ("Succession Position", "HR User", 2, ("read",), ()),
    ("Succession Position", "Talent Council", 2, ("read",), ()),
)
PTYPES = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "print", "email",
          "share")


def execute():
    from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
    from frappe.permissions import setup_custom_perms

    touched = set()
    for doctype, role, level, on, off in RULES:
        if not (frappe.db.exists("DocType", doctype) and frappe.db.exists("Role", role)):
            continue
        setup_custom_perms(doctype)
        name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": level,
                                                      "if_owner": 0}, "name")
        if not name:
            if not on:
                continue
            doc = frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType",
                                  "parentfield": "permissions", "role": role, "permlevel": level})
            doc.insert(ignore_permissions=True)
            name = doc.name
        values = {ptype: 1 for ptype in on if ptype in PTYPES}
        values.update({ptype: 0 for ptype in off if ptype in PTYPES})
        if level:
            # a higher level grants reading and writing only
            values = {ptype: value for ptype, value in values.items() if ptype in ("read", "write")}
        frappe.db.set_value("Custom DocPerm", name, values, update_modified=False)
        touched.add(doctype)
    for doctype in sorted(touched):
        validate_permissions_for_doctype(doctype)
        frappe.clear_cache(doctype=doctype)
