# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Clearance Forms not yet cleared, brought up to how the form works since
13 Oct 2026.

Until then no form could leave Draft (nothing could sign a box), so every
one on a site is still open. Two things on them were wrong:

  the remark a tool of work or the handover line was drawn up with (the
  serial number, who takes the work over) counted as the employee having
  accounted for the item. It is now kept as the remark the form was drawn up
  with, where it still stands as it was written.

  Leave Balance added up every allocation the employee ever had, of every
  leave type. On a form still in Draft it is worked out again: the Annual
  Leave still to take on the last day, which is what the settlement pays.

The new field is synced first: a doctype's own fields are in place by the
time a post_model_sync patch runs. A form that cannot be read is left as it
is and named in the log. Safe to run twice."""

import frappe
from frappe.utils import flt

FORM = "Clearance Form"


def execute():
    from hrms_addon.hrms_addon import clearance_approval, exits, talent, talent_rules

    if not frappe.db.exists("DocType", FORM) or not frappe.get_meta("Clearance Item").has_field("drawn_remarks"):
        return
    for name in frappe.get_all(FORM, filters={"docstatus": 0}, pluck="name"):
        try:
            doc = frappe.get_doc(FORM, name)
            issued = {tool.tool: exits._issued(tool) for tool in exits._tools(doc.employee)}
            handover = talent.handover_for(doc.employee)
            for row in doc.get("items") or []:
                said = (row.get("remarks") or "").strip()
                if not said or row.get("drawn_remarks"):
                    continue
                if (row.get("tool") and said == (issued.get(row.tool) or "")) or (
                        row.section == "A" and row.item == talent_rules.HANDOVER_ITEM and said == (handover or "")):
                    row.db_set("drawn_remarks", said, update_modified=False)
            values = exits._progress(doc)
            if (doc.get("workflow_state") or clearance_approval.DRAFT) == clearance_approval.DRAFT:
                values["leave_balance"] = flt(exits._leave_balance(doc.employee, doc.get("leaving_date")))
            doc.db_set(values, update_modified=False)
        except Exception:
            frappe.log_error(title="HRMS Addon: Clearance Form %s not brought up to date" % name)
