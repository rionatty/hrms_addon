# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Submit, Cancel, Edit and Delete from a list, on any number of records.

Frappe's own two methods stand in for these (hooks.py,
override_whitelisted_methods); the rules are in bulk_rules.py
(scripts/verify_bulk.py).

  submit_cancel_or_update_docs   up to 500 exactly as Frappe does them;
                                 beyond, batches of 500, each a job of its
                                 own on the long queue, where Frappe refused
                                 ("Bulk operations only support up to 500
                                 documents")
  delete_items                   up to 10 while the user waits, as Frappe
                                 does; beyond, batches of 500 on the long
                                 queue, where Frappe ran one job the default
                                 queue stops after five minutes

Cancelling or deleting more attendance than one batch goes to Attendance
Deletion instead (attendance_deletions.py): Frappe queues a background job for
every record it deletes, and the queue holds 500.

Every record is still worked by Frappe's own code: its permissions and checks,
one at a time, saved as it goes, a failure written to the Error Log and the
rest carried on.
"""

import json

import frappe
from frappe import _
from frappe.desk.doctype.bulk_update import bulk_update

from hrms_addon.hrms_addon import bulk_rules as rules

ATTENDANCE = "Attendance"
BULK_ACTION = "frappe.desk.doctype.bulk_update.bulk_update._bulk_action"
DELETE_BULK = "frappe.desk.reportview.delete_bulk"


@frappe.whitelist(methods=["POST"])
def submit_cancel_or_update_docs(doctype, docnames, action="submit", data=None, task_id=None):
    """Frappe's Submit, Cancel and Edit from a list, with no cap on how many."""
    if isinstance(docnames, str):
        docnames = frappe.parse_json(docnames)
    if action == "cancel":
        _not_this_much_attendance(doctype, docnames)
    if len(docnames) <= rules.BATCH:
        return bulk_update.submit_cancel_or_update_docs(doctype, docnames, action=action, data=data, task_id=task_id)
    parts = rules.batches(docnames)
    for part in parts:
        frappe.enqueue(BULK_ACTION, doctype=doctype, docnames=part, action=action, data=data, task_id=task_id,
                       queue="long", timeout=rules.TIMEOUT)
    frappe.msgprint(_("{0} records queued in {1} batches.").format(len(docnames), len(parts)), alert=True)


@frappe.whitelist(methods=["POST", "DELETE"])
def delete_items():
    """Frappe's Delete from a list, in batches where it would run one job that could be stopped half way."""
    from frappe.desk import reportview

    items = sorted(json.loads(frappe.form_dict.get("items")), reverse=True)
    doctype = frappe.form_dict.get("doctype")
    _not_this_much_attendance(doctype, items)
    if len(items) <= rules.DELETE_NOW:
        return reportview.delete_bulk(doctype, items)
    for part in rules.batches(items):
        frappe.enqueue(DELETE_BULK, doctype=doctype, items=part, queue="long", timeout=rules.TIMEOUT)
    return None


def _not_this_much_attendance(doctype, names):
    if doctype == ATTENDANCE and len(names) > rules.BATCH:
        frappe.throw(_("Use {0} for more than {1} attendance records at a time.").format(
            frappe.utils.get_link_to_form("Attendance Deletion", "new", _("Attendance Deletion")), rules.BATCH))
