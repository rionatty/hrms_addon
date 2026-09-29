# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The self-appraisal as Appraisal Settings say, on the appraisals already
raised.

The patch that brought the self-appraisal in turned it on for every
appraisal and sent the plan's drafts to the employee, whatever the setting
said, and each appraisal then kept that for good. Now an appraisal the
supervisor does not have yet follows the setting:

1. Every open appraisal in Draft or waiting on a self-appraisal follows
   Appraisal Settings as they are (appraisals.follow_settings): with the
   self-appraisal off, one waiting on the employee goes on to the
   supervisor, who is told.
2. An appraisal further on keeps the self-appraisal only where the employee
   gave one; the rest were never self-appraised.

Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import appraisal_approval as approval, appraisals


def execute():
    appraisals.follow_settings()
    _never_self_appraised()


def _never_self_appraised():
    rows = frappe.get_all("Appraisal", filters={"docstatus": ["!=", 2], approval.SELF_FIELD: 1},
                          fields=["name", "docstatus", approval.STATE_FIELD])
    further = [row.name for row in rows
               if (row.get(approval.STATE_FIELD) or (approval.DRAFT if not row.docstatus else approval.COMPLETED))
               not in approval.BEFORE_SUPERVISOR]
    gave = appraisals.gave_self_appraisal(further)
    for name in further:
        if name not in gave:
            frappe.db.set_value("Appraisal", name, approval.SELF_FIELD, 0, update_modified=False)
