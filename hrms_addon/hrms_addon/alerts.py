# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""My Alerts rail: what the logged-in user has to act on.

The rules are in alerts_rules.py (no Frappe import, tested by
scripts/verify_alerts.py); the rail itself is public/js/hrms_addon_alerts.js.

  my_alerts           the user's open assignments (ToDo) and unread
                      notifications, most urgent first, each with the band
                      colouring its row; an assignment whose work is done
                      (rules.attended) is closed and left out
  mark_read           a notification the user has read (their own only)
  mark_all_read       the same for every one of theirs
  mark_document_read  the user's notifications about a document they have
                      opened: seen there, so attended to
  close_assignment    one of the user's own assignments, done
  install_alert_type  after_migrate: the HR Alert notification type, which
                      Frappe emails (people.notify)

WHOSE ALERTS

Every query here is filtered on frappe.session.user and nothing accepts a
user to look at: the rail shows one person their own work, and asking for
somebody else's must not be a matter of changing a parameter.
"""

import frappe
from frappe import _
from frappe.utils import cint, strip_html, today

from hrms_addon.hrms_addon import alerts_rules as rules

# How many of each to read. The rail is a glance, not a list view; the count
# in its header is the honest total, taken before the cut.
LIMIT = 40


@frappe.whitelist()
def my_alerts(limit=LIMIT):
    """{"alerts": [...], "counts": {...}, "total": n, "band": "overdue"} for
    the logged-in user."""
    limit = max(1, min(cint(limit) or LIMIT, 100))
    day = today()
    alerts = rules.order(_assignments(day) + _notifications(day), day)
    _, band = rules.badge(alerts)
    # the header counts what is still to be dealt with: every assignment and
    # every notification still unread, which is now all the list holds
    outstanding = [alert for alert in alerts if alert["kind"] == rules.ASSIGNMENT or alert.get("unread")]
    return {"alerts": alerts[:limit], "counts": rules.counts(alerts), "total": len(outstanding),
            "band": rules.badge(outstanding)[1] if outstanding else band}


def _assignments(day):
    """Open ToDos: what the user has been given to do. One whose work is done
    is closed on the way, so Frappe's own ToDo list agrees with the rail."""
    rows = frappe.get_all(
        "ToDo",
        filters={"allocated_to": frappe.session.user, "status": "Open"},
        fields=["name", "reference_type", "reference_name", "description", "date", "priority", "creation"],
        order_by="modified desc",
        limit=LIMIT,
    )
    seen, open_rows = {}, []
    for row in rows:
        key = (row.reference_type, row.reference_name)
        if row.reference_type and row.reference_name:
            if key not in seen:
                seen[key] = rules.attended(_facts(row.reference_type, row.reference_name))
            if seen[key]:
                _close(row.name)
                continue
        open_rows.append(row)
    return [{
        "kind": rules.ASSIGNMENT,
        "key": row.name,
        "title": rules.title(strip_html(row.description or "")) or _("An assignment"),
        "doctype": row.reference_type,
        "docname": row.reference_name,
        "due": str(row.date) if row.date else None,
        "priority": row.priority,
        "created": str(row.creation),
        "urgency": rules.urgency(row.date, day, row.priority),
        "when": rules.when(row.date, day),
    } for row in open_rows]


def _facts(doctype, name):
    """What rules.attended needs to know about an assignment's document."""
    from frappe.model.workflow import get_transitions, get_workflow_name

    if not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
        return {"exists": False}
    doc = frappe.get_doc(doctype, name)
    workflow = get_workflow_name(doctype)
    state_field = frappe.db.get_value("Workflow", workflow, "workflow_state_field") if workflow else None
    facts = {"exists": True, "docstatus": doc.docstatus,
             "workflow": bool(workflow and state_field and doc.get(state_field))}
    if facts["workflow"]:
        try:
            facts["can_act"] = bool(get_transitions(doc))
        except Exception:
            facts["can_act"] = True  # cannot tell: the assignment stays
    return facts


def _close(name):
    """An assignment whose work is done, closed as Frappe closes one."""
    todo = frappe.get_doc("ToDo", name)
    todo.status = "Closed"
    todo.flags.ignore_permissions = True
    todo.save()


def _notifications(day):
    """The user's own notifications still unread, newest first: one read, or
    whose document they have opened, has been attended to and leaves the
    rail (Frappe's own panel still lists it)."""
    rows = frappe.get_all(
        "Notification Log",
        filters={"for_user": frappe.session.user, "read": 0},
        fields=["name", "subject", "type", "document_type", "document_name", "from_user", "creation", "read"],
        order_by="creation desc",
        limit=LIMIT,
    )
    return [{
        "kind": rules.NOTIFICATION,
        "key": row.name,
        "title": rules.title(strip_html(row.subject or "")) or _("A notification"),
        "doctype": row.document_type,
        "docname": row.document_name,
        "due": None,
        "priority": None,
        "created": str(row.creation),
        "urgency": rules.urgency(None, day),
        "when": "",
        "type": row.type,
        "unread": 0 if row.read else 1,
    } for row in rows]


@frappe.whitelist(methods=["POST"])
def mark_read(name):
    """One of the user's own notifications, read."""
    owner = frappe.db.get_value("Notification Log", name, "for_user")
    if owner != frappe.session.user:
        frappe.throw(_("Not your notification."), frappe.PermissionError)
    frappe.db.set_value("Notification Log", name, "read", 1, update_modified=False)


@frappe.whitelist(methods=["POST"])
def mark_all_read():
    """Every unread notification of the user's, read."""
    for name in frappe.get_all("Notification Log", filters={"for_user": frappe.session.user, "read": 0}, pluck="name"):
        frappe.db.set_value("Notification Log", name, "read", 1, update_modified=False)


@frappe.whitelist(methods=["POST"])
def mark_document_read(doctype: str, name: str) -> int:
    """The user's unread notifications about a document they have just
    opened: seen there, so they leave the rail. How many."""
    names = frappe.get_all("Notification Log", filters={"for_user": frappe.session.user, "read": 0,
                                                        "document_type": doctype, "document_name": name}, pluck="name")
    for log in names:
        frappe.db.set_value("Notification Log", log, "read", 1, update_modified=False)
    return len(names)


@frappe.whitelist(methods=["POST"])
def close_assignment(name: str):
    """One of the user's own assignments, done (their own only)."""
    if frappe.db.get_value("ToDo", name, "allocated_to") != frappe.session.user:
        frappe.throw(_("Not your assignment."), frappe.PermissionError)
    _close(name)


def install_alert_type():
    """after_migrate: the app's own Notification Type, made once. Frappe emails
    every type but its own Alert; a site where it is disabled keeps it so."""
    if frappe.db.exists("DocType", "Notification Type") and not frappe.db.exists("Notification Type",
                                                                                rules.EMAILED_TYPE):
        frappe.get_doc({"doctype": "Notification Type", "type_name": rules.EMAILED_TYPE, "enabled": 1}).insert(
            ignore_permissions=True)
