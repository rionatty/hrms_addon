# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The roles the contract-management documents need on a site that has this
app already: the Candidate Preamble's signatories and the Legal Manager who
witnesses the renewal and salary letters.

after_migrate builds the workflow (positions.setup_workflows_on_migrate) and
creates them too, so this only matters where that has not run yet. Both are
idempotent.
"""

import frappe

from hrms_addon.hrms_addon import position_approval


def execute():
    for role in position_approval.NEW_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
