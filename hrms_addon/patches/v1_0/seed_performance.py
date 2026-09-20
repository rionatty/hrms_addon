# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Performance management on a site that has this app already:

  * Section A of the Supervisory Skills Evaluation Form (LPL/HR/18) as the
    Appraisal Factor list;
  * the roles the form's signatories need — the Production Manager above
    all, who does not appear anywhere else.

after_migrate builds the workflow and creates the roles too
(appraisals.setup_workflows_on_migrate), so this only matters where that
has not run yet. Both are idempotent.
"""

import frappe

from hrms_addon.hrms_addon import appraisal_approval
from hrms_addon.hrms_addon.pick_lists import seed_appraisal_masters


def execute():
    for role in appraisal_approval.NEW_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    seed_appraisal_masters()
