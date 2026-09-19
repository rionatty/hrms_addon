# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Luuka's organisation, as far as approvals go.

No Frappe import, like the other *_rules.py modules, so the verifiers read
it without a bench.

Luuka runs three branches (plants). Each has its own Heads of Department,
supervisors, HR Officer and General Manager; the HR Manager and the
Executive Director serve all three. An approval therefore goes to the
document's own branch, never to everyone holding a role:

  * each document carries its Branch (and Department): the Job Requisition
    from the requester, the Job Opening from the requisition, and the
    interview documents from the opening;
  * each branch-level user holds Branch User Permissions (HODs and
    supervisors Department ones as well; an HOD may be given more than one
    branch). Frappe applies them to what a user sees and may approve, and a
    workflow only notifies role holders who may open the document
    (frappe/workflow/doctype/workflow_action get_users_next_action_data).

The HR Manager and the Executive Director hold no such permissions, so
they see every branch.
"""

BRANCHES = ("Kawempe", "Namanve", "Matugga")

# The Branch master (ERPNext's), seeded once like the other pick lists
ORG_MASTERS = {"Branch": ("branch", BRANCHES)}

# A Department's Position Category decides a requisition's route (the To-Be
# resourcing narration): administrative positions go to the HR Manager and
# the Executive Director, the others through the branch's General Manager as
# well (requisition_approval.py).
ADMINISTRATIVE = "Administrative"
NON_ADMINISTRATIVE = "Non-Administrative"
POSITION_CATEGORIES = (NON_ADMINISTRATIVE, ADMINISTRATIVE)
