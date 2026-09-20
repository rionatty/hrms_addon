# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""My Alerts rail: what the logged-in user has to act on.

The rules are in alerts_rules.py (no Frappe import, tested by
scripts/verify_alerts.py); the rail itself is public/js/hrms_addon_alerts.js.

  my_alerts      the user's open assignments (ToDo) and unread notifications,
                 most urgent first, each with the band colouring its row
  mark_read      a notification the user has read (their own only)
  mark_all_read  the same for every one of theirs

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
    alerts = _assignments(day) + _notifications(day)
    alerts = rules.order(alerts, day)
    total, band = rules.badge(alerts)
    return {"alerts": alerts[:limit], "counts": rules.counts(alerts), "total": total, "band": band}


def _assignments(day):
    """Open ToDos: what the user has been given to do."""
    rows = frappe.get_all(
        "ToDo",
        filters={"allocated_to": frappe.session.user, "status": "Open"},
        fields=["name", "reference_type", "reference_name", "description", "date", "priority", "creation"],
        order_by="modified desc",
        limit=LIMIT,
    )
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
    } for row in rows]


def _notifications(day):
    """Unread Notification Logs: what the user has been told."""
    rows = frappe.get_all(
        "Notification Log",
        filters={"for_user": frappe.session.user, "read": 0},
        fields=["name", "subject", "type", "document_type", "document_name", "from_user", "creation"],
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
