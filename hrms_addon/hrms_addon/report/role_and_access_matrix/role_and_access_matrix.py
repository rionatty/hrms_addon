# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Role and Access Matrix (Security & Access Control): who may do what,
on which document, at which permission level.

It reads the permissions the site actually has rather than the ones this
app asked for, which is the only version worth auditing. A row that is
read-only is marked so, and the Auditor's rows should all be.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import security, security_rules as rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    rows = security.audit()
    if filters.get("role"):
        rows = [row for row in rows if row["role"] == filters.role]
    if filters.get("document"):
        rows = [row for row in rows if row["document"] == filters.document]
    if filters.get("read_only_roles_only"):
        rows = [row for row in rows if row["role"] in rules.READ_ONLY_ROLES]
    if filters.get("level_one_only"):
        rows = [row for row in rows if row["level"] == rules.PROTECTED_LEVEL]
    return columns(), rows


def columns():
    return [
        {"label": _("Document"), "fieldname": "document", "fieldtype": "Link",
         "options": "DocType", "width": 220},
        {"label": _("Role"), "fieldname": "role", "fieldtype": "Link", "options": "Role",
         "width": 200},
        {"label": _("Level"), "fieldname": "level", "fieldtype": "Int", "width": 70},
        {"label": _("May"), "fieldname": "allowed", "fieldtype": "Data", "width": 320},
        {"label": _("Read Only"), "fieldname": "read_only", "fieldtype": "Check", "width": 90},
    ]
