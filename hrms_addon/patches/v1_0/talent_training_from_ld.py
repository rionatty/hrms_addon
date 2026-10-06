# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent's training brought back from L&D (Luuka, 6 Oct 2026: "Link each
talent requisition to its plan ... the matching action on each attendee's
plan gets its Completed On date").

- Each Training Requisition a development plan raised names the plan.
- Each session already booked on one shows on the plan as it stands: who
  attended, their marks, and the plan's actions of its topic done the day
  it was held (talent.sync_training).

A session that cannot be read is logged and left, so the migrate goes on.
Safe to run twice.
"""

import frappe

from hrms_addon.hrms_addon import talent


def execute():
    for plan in frappe.get_all(talent.PROGRAM, filters={"training_requisition": ["is", "set"], "docstatus": ["<", 2]},
                               fields=["name", "training_requisition"]):
        if not frappe.db.get_value(talent.REQUISITION, plan.training_requisition, "talent_program"):
            frappe.db.set_value(talent.REQUISITION, plan.training_requisition, "talent_program", plan.name,
                                update_modified=False)
    raised = frappe.get_all(talent.REQUISITION, filters={"talent_program": ["is", "set"], "docstatus": ["<", 2]},
                            fields=["name", "training_event"])
    sessions = {row.training_event for row in raised if row.training_event}
    needs = frappe.get_all("Training Need", filters={"requisition": ["in", [row.name for row in raised]]},
                           pluck="name") if raised else []
    entries = frappe.get_all("Training Calendar Entry", filters={"need_row": ["in", needs]},
                             pluck="name") if needs else []
    if entries:
        sessions |= set(frappe.get_all("Training Event", filters={"custom_calendar_entry": ["in", entries],
                                                                  "docstatus": ["<", 2]}, pluck="name"))
    for session in sorted(sessions):
        try:
            talent.sync_training(session)
        except Exception:
            frappe.log_error(title="HRMS Addon: a talent training brought back at migrate")
