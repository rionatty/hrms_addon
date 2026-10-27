# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The module pages: what waits for the user among a module's documents.

public/js/hrms_addon_module_pages.js puts a header over each module's
workspace, in the desk home's look; the rest of what it shows comes with
the boot (theme.boot_session), and the cards under it are Frappe's own. The
rules are in module_pages_rules.py (scripts/verify_module_pages.py).

  summary   what waits for the logged-in user among the documents the
            module's page and menu open, the doctypes of what waits, and
            the desk home's tab of dashboards for the module, where the
            user has it (dashboards.py)

WHOSE ALERTS

The user's own, read as My Alerts reads them (alerts.py): nothing here takes
a user to look at. The workspace named only says which documents to count.

NEVER AN ERROR

A module's page opens whatever happens here: a part that cannot be read is
left out and written to the Error Log, and the header still comes.
"""

import frappe
from frappe.utils import today

from hrms_addon.hrms_addon import alerts, alerts_rules, home_rules, module_pages_rules as rules


@frappe.whitelist()
def summary(workspace: str):
    """What waits for the logged-in user among the module's documents."""
    names = _or([], _doctypes, workspace)
    mine = rules.mine_in(_or([], _alerts, names) if names else [], names)
    # the doctypes of what waits, which the user's own lists are kept to when they open them from here
    return {"workspace": workspace, "waiting": home_rules.waiting(mine, rules.SHOWN),
            "doctypes": rules.doctypes(alert.get("doctype") for alert in mine),
            # the desk home's tab of dashboards for this module, where the user has it
            "dashboard": _or(None, _dashboard, workspace)}


def _or(fallback, read, *args):
    """What `read` gives, or `fallback` where it cannot be read. Logged with
    defer_insert: a GET is rolled back, and the log has to outlive it."""
    try:
        return read(*args)
    except Exception:
        frappe.log_error(title="Module page: %s" % getattr(read, "__name__", "read"), defer_insert=True)
        return fallback


def _dashboard(workspace):
    """The desk home's tab for the module, where the user has it; asked here, under the guard, so the header comes
    whatever happens to the dashboards."""
    from hrms_addon.hrms_addon import dashboards

    return dashboards.tab_of_workspace(workspace)


def _doctypes(workspace):
    """The doctypes the module opens: its menu (Workspace Sidebar, which
    Frappe draws down the left), then its page's cards and shortcuts."""
    names = []
    if frappe.db.exists("DocType", "Workspace Sidebar") and frappe.db.exists("Workspace Sidebar", workspace):
        names += [row.link_to for row in frappe.get_doc("Workspace Sidebar", workspace).items
                  if row.link_type == "DocType"]
    if frappe.db.exists("Workspace", workspace):
        page = frappe.get_doc("Workspace", workspace)
        names += [row.link_to for row in page.links if row.type == "Link" and row.link_type == "DocType"]
        names += [row.link_to for row in page.shortcuts if row.type == "DocType"]
    return rules.doctypes(names)


def _alerts(names):
    """The user's own assignments and unread notifications about documents of
    those doctypes, most urgent first, as My Alerts orders them."""
    day = today()
    return alerts_rules.order(alerts._assignments(day, names) + alerts._notifications(day, names), day)
