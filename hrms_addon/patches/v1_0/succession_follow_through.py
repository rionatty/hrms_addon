# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a confirmed succession plan leads to (Luuka, 6 Oct 2026: "where
does this lead to after you have set this, which module should be
connected").

- A plan whose holder has an exit raised takes their last day from it, and
  the exit names the plan.
- Each confirmed plan: a development plan drafted for every successor not
  ready yet, and its holder's exit acted on once it is 90 days away (a
  promotion or a replacement's requisition drafted, HR and the council
  told), as the daily watch would the next morning.

A plan that cannot be acted on is logged and left for the daily watch, so
the migrate goes on. Safe to run twice.
"""

import frappe
from frappe.utils.fixtures import sync_fixtures

from hrms_addon.hrms_addon import talent


def execute():
    # the exit's and the requisition's links to the plan exist first:
    # fixtures are synced only after every patch
    sync_fixtures("hrms_addon")
    frappe.clear_cache(doctype=talent.SEPARATION)
    frappe.clear_cache(doctype=talent.JOB_REQUISITION)
    for position in frappe.get_all(talent.POSITION, filters={"docstatus": ["<", 2], "incumbent": ["is", "set"]},
                                   fields=["name", "incumbent", "retirement_or_exit_due"]):
        found = talent._exit_of(position.incumbent)
        if not found.get("name"):
            continue
        if str(position.retirement_or_exit_due or "") != str(found.custom_relieving_date):
            frappe.db.set_value(talent.POSITION, position.name,
                                {"retirement_or_exit_due": found.custom_relieving_date, "exit_alerted": 0},
                                update_modified=False)
        frappe.db.set_value(talent.SEPARATION, found.name, "custom_succession_position", position.name,
                            update_modified=False)
    for name in frappe.get_all(talent.POSITION, filters={"docstatus": 1}, pluck="name"):
        try:
            doc = frappe.get_doc(talent.POSITION, name)
            talent._plan_successor_development(doc)
            talent._act_on_exit(doc)
        except Exception:
            frappe.log_error(title="HRMS Addon: a succession plan's follow-through at migrate")
