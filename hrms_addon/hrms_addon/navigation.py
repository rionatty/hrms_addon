# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Put what this app adds into Frappe HR's own workspaces and sidebars.

The lists are in navigation_rules.py (no Frappe import, tested by
scripts/verify_navigation.py). This writes them onto the Workspace and
Workspace Sidebar records on every migrate, after Frappe has re-imported
the standard ones.

WHY ON EVERY MIGRATE, AND WHY ADDING ONLY

Those records belong to Frappe HR, which ships them as JSON and rewrites
them whenever it is updated. So this never rewrites one: it adds a card, a
link or a sidebar entry where it is missing and leaves everything else as
it found it. Run again, it changes nothing (navigation_rules gives our
card blocks a name of their own rather than the random id Frappe uses).

A workspace that is not installed is skipped, so the app still installs on
a site without Frappe HR.
"""

import json

import frappe

from hrms_addon.hrms_addon import navigation_rules as rules


def setup_on_migrate():
    """after_migrate: the cards and sidebar entries, never failing the deploy.

    Not quiet either: HR losing its way to a document is worth noticing, so
    the reason goes to the migrate output as well as the Error Log.
    """
    savepoint = "hrms_addon_navigation"
    frappe.db.savepoint(savepoint)
    try:
        apply_navigation()
    except Exception:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            pass
        frappe.log_error(title="HRMS Addon: workspace links setup failed")
        print("HRMS Addon: workspace links setup FAILED — see Error Log")


def apply_navigation():
    for workspace, cards in rules.CARDS.items():
        _apply_cards(workspace, cards)
    for workspace, entries in rules.SIDEBAR.items():
        _apply_sidebar(workspace, entries)
    frappe.db.commit()


def _apply_cards(workspace, cards):
    if not frappe.db.exists("Workspace", workspace):
        return
    doc = frappe.get_doc("Workspace", workspace)
    links = rules.merge_links([row.as_dict() for row in doc.links], cards)
    content = rules.merge_content(json.loads(doc.content or "[]"), cards)
    if _same(links, [row.as_dict() for row in doc.links]) and json.loads(doc.content or "[]") == content:
        return  # re-saving would only churn `modified` on every migrate
    doc.set("links", [])
    for row in links:
        doc.append("links", row)
    doc.content = json.dumps(content)
    doc.flags.ignore_permissions = True
    doc.save()


def _apply_sidebar(workspace, entries):
    if not frappe.db.exists("Workspace Sidebar", workspace):
        return
    doc = frappe.get_doc("Workspace Sidebar", workspace)
    items = rules.merge_sidebar([row.as_dict() for row in doc.items], entries)
    if _same(items, [row.as_dict() for row in doc.items]):
        return
    doc.set("items", [])
    for row in items:
        doc.append("items", row)
    doc.flags.ignore_permissions = True
    doc.save()


def _same(wanted, current):
    """Whether the rows say the same thing, ignoring what the database adds
    (names, timestamps, the row order Frappe keeps in idx)."""
    keys = ("type", "label", "link_type", "link_to", "child", "link_count")

    def shape(rows):
        return [tuple(row.get(key) for key in keys) for row in rows]

    return shape(wanted) == shape(current)
