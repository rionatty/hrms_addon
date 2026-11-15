# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Delete Imported Records, on a Data Import (public/js/data_import.js). The rules are import_undo_rules.py.

Luuka, 15 Nov 2026, after importing 723 Salary Advance Requests as drafts: "add a button to delete data impported
through data import to allow quick deletion".

The records are those the import's log says it made (Data Import Log, success) that are still there. They are deleted
in the background, newest first, a submitted one cancelled first. Each is committed on its own, so a record that
cannot go (another document links to it, or the user may not cancel or delete it) stays without stopping the rest.
Each goes to Deleted Document, as Frappe's own delete does, so it can be restored. The user sees the progress and then
a message, and the import keeps a comment of it.

Only for an import that inserted new records, and only for someone who may delete that document type. Every cancel
and delete is the user's own, checked by Frappe as if done by hand.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import import_undo_rules as rules

IMPORT = "Data Import"
LOG = "Data Import Log"
TITLE = "Delete Imported Records"
JOB = "hrms_addon_import_undo::%s"


@frappe.whitelist()
def made(data_import):
    """What the button needs: the document type, and how many records the import made are still there. Nothing when
    the import or the user cannot have it."""
    run = _undoable(data_import)
    if not run:
        return {}
    return {"doctype": run.reference_doctype, "count": len(still_there(run))}


@frappe.whitelist(methods=["POST"])
def delete_made(data_import):
    """Starts deleting in the background. Returns how many records it will try."""
    from frappe.utils.background_jobs import is_job_enqueued

    run = _undoable(data_import)
    if not run:
        frappe.throw(_("Only the records a finished import inserted can be deleted here, by someone who may delete "
                       "them."), title=_(TITLE))
    names = still_there(run)
    if not names:
        frappe.throw(_("Nothing this import made is left to delete."), title=_(TITLE))
    if is_job_enqueued(JOB % run.name):
        frappe.throw(_("These records are already being deleted."), title=_(TITLE))
    frappe.enqueue("hrms_addon.hrms_addon.import_undo.delete_in_background", queue="long", timeout=7200,
                   job_id=JOB % run.name, deduplicate=True, data_import=run.name)
    return len(names)


def _undoable(data_import):
    run = frappe.get_doc(IMPORT, data_import)
    run.check_permission("read")
    if not rules.undoable(run.import_type, run.status) or not run.reference_doctype:
        return None
    if not frappe.has_permission(run.reference_doctype, "delete"):
        return None
    return run


def still_there(run):
    """The records the import's log says it made that are still there, newest first."""
    logged = frappe.get_all(LOG, filters={"data_import": run.name, "success": 1}, fields=["docname"],
                            order_by="log_index desc, creation desc", limit_page_length=0)
    names = list(dict.fromkeys(row.docname for row in logged if row.docname))
    if not names:
        return []
    there = set(frappe.get_all(run.reference_doctype, filters={"name": ["in", names]}, pluck="name",
                               limit_page_length=0))
    return [name for name in names if name in there]


def delete_in_background(data_import):
    """Deletes the records, each on its own, and tells the user how it went."""
    from frappe.utils import escape_html

    run = frappe.get_doc(IMPORT, data_import)
    doctype, names = run.reference_doctype, still_there(run)
    deleted, failed = 0, []
    for number, name in enumerate(names, 1):
        try:
            doc = frappe.get_doc(doctype, name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc(doctype, name)
            frappe.db.commit()
            deleted += 1
        except Exception as error:
            # this one stays as it was, cancel and all; the rest go on
            frappe.db.rollback()
            failed.append((name, rules.reason(error)))
        frappe.clear_messages()
        if number % 10 == 0 or number == len(names):
            frappe.publish_progress(number * 100.0 / len(names), title=_("Deleting {0}").format(_(doctype)),
                                    description=name)
    said = "<br>".join(escape_html(line) for line in rules.result_lines(doctype, len(names), deleted, failed))
    run.add_comment("Info", said)
    frappe.db.commit()
    frappe.msgprint(said, title=_(TITLE), indicator="orange" if failed else "green", realtime=True)
