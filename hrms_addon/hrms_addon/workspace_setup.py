# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Workspace reorganisation.

Driven by the declarations at the top of this file, so that changing the
menu is a data edit, not a code change:

  WORKSPACE_ORDER      the top-level list down the desk sidebar
  SIDEBAR_LINKS        the links inside one workspace
  WORKSPACE_ADD_LINKS  this app's own links, added to another app's cards

Verified against frappe v16.33 (frappe/desk/doctype/workspace):

  Workspace.sequence_id   Float  — the sort key for the sidebar
  Workspace.parent_page   Link   — set to nest under another workspace
  Workspace.is_hidden     Check  — keeps the record, drops it from the menu
  Workspace.public        Check  — private workspaces are per-user
  Workspace.links         Table of Workspace Link, ordered by idx

  Workspace Link.type     Select — "Card Break" starts a group,
                                   "Link" is an entry inside it
  Workspace Link.hidden   Check  — hide one entry without deleting it

WHY REORDER RATHER THAN REBUILD: these are ERPNext's and Frappe HR's own
Workspace records. Deleting and recreating them loses whatever the site
has customised and puts us in conflict with every upstream update. So
this adds only its own links, otherwise only nudges sequence_id /
is_hidden / idx on records that already exist, and silently skips
anything that is not installed.

IDEMPOTENT: safe on every migrate. Nothing is written when the stored
value already matches, so a repeat run is a no-op and does not churn
`modified` timestamps.
"""

import frappe

from hrms_addon.hrms_addon import workspace_rules

# ── Top-level sidebar order ──────────────────────────────────────────
# "Workspace name": sequence_id. Lower floats sort first. Names must
# match the Workspace record's `name` exactly (case-sensitive).
#
# Anything not listed keeps whatever sequence_id it already has, which
# in ERPNext is generally >= 1, so listing yours below 1 floats them to
# the top without having to enumerate every workspace on the site.
#
# EMPTY PENDING THE AGREED ORDER — add entries like:
#     "Home": 0.1,
#     "HR": 0.2,
WORKSPACE_ORDER = {}

# Workspaces to drop from the sidebar without deleting the record.
# `bench migrate` will re-apply this, so it survives an ERPNext update
# putting them back.
WORKSPACE_HIDE = []

# ── Links inside a workspace ─────────────────────────────────────────
# "Workspace name": [labels, in the order you want them]
#
# Labels are matched against Workspace Link.label. Card Breaks (the
# group headings) are matched the same way, so listing a heading moves
# the heading; the links under it follow their own listed order.
#
# Any link NOT named here keeps its relative order and is appended after
# the ones that are — so a partial list is fine, and an upstream update
# that adds a new link will not be silently buried.
#
# EMPTY PENDING THE AGREED ORDER — add entries like:
#     "Leaves": ["Leave Application", "Leave Allocation", ...],
SIDEBAR_LINKS = {}

# Links to hide, per workspace: "Workspace name": [labels]
SIDEBAR_HIDE = {}

# ── Links this app adds to another app's workspace ───────────────────
# "Workspace name": {"Card label": [(label, link_type, link_to, after)]}
#
# Each link goes into the card straight after the link labelled `after`
# (None: first in the card), unless the card already has it. Unlike the
# declarations above this is not pending anything: it is how HR finds this
# app's documents on the pages they already use. Re-asserted on every
# migrate, because a Frappe HR update re-imports its workspace and drops
# rows it does not know. The placing is workspace_rules.plan_card_links.
WORKSPACE_ADD_LINKS = {
    "Recruitment": {
        "Interviews": [
            ("Interview Shortlist", "DocType", "Interview Shortlist", None),
            ("Interview Report", "DocType", "Interview Report", "Interview Feedback"),
            ("Interview Criterion", "DocType", "Interview Criterion", "Interview Report"),
        ],
    },
}


def _workspace_exists(name):
    return bool(frappe.db.exists("Workspace", name))


def apply_added_links():
    """Add WORKSPACE_ADD_LINKS to their cards, straight in the Workspace Link
    table: saving another app's Workspace would, in developer mode, write it
    back into that app's files."""
    changed = []
    for workspace, cards in WORKSPACE_ADD_LINKS.items():
        if not _workspace_exists(workspace):
            continue
        for card, wanted in cards.items():
            wanted = [link for link in wanted if link[1] != "DocType" or frappe.db.exists("DocType", link[2])]
            rows = frappe.get_all(
                "Workspace Link",
                filters={"parent": workspace, "parenttype": "Workspace", "parentfield": "links"},
                fields=["name", "type", "label", "link_type", "link_to", "idx", "link_count"],
                order_by="idx asc",
            )
            planned = workspace_rules.plan_card_links(rows, card, wanted)
            if planned is None or not any(row.get("new") for row in planned):
                continue
            for position, row in enumerate(planned, start=1):
                if row.get("new"):
                    frappe.get_doc({
                        "doctype": "Workspace Link",
                        "parent": workspace,
                        "parenttype": "Workspace",
                        "parentfield": "links",
                        "idx": position,
                        "type": "Link",
                        "label": row["label"],
                        "link_type": row["link_type"],
                        "link_to": row["link_to"],
                        "hidden": 0,
                        "onboard": 0,
                        "is_query_report": 0,
                    }).db_insert()
                    changed.append("%s: %s added to %s" % (workspace, row["label"], card))
                elif row.get("idx") != position:
                    frappe.db.set_value("Workspace Link", row["name"], "idx", position, update_modified=False)
            # The workspace editor cuts a card out of the table by its link
            # count when it saves: keep it true, or our links fall out of the card.
            card_row = next(row for row in planned if row.get("type") == "Card Break" and row.get("label") == card)
            count = len(workspace_rules.card_links(planned, card))
            if card_row.get("link_count") != count:
                frappe.db.set_value("Workspace Link", card_row["name"], "link_count", count, update_modified=False)
    return changed


def apply_workspace_order():
    """Set sequence_id / is_hidden on the top-level workspaces."""
    changed = []

    for name, sequence in WORKSPACE_ORDER.items():
        if not _workspace_exists(name):
            continue
        current = frappe.db.get_value("Workspace", name, "sequence_id")
        if current is not None and float(current) == float(sequence):
            continue
        frappe.db.set_value("Workspace", name, "sequence_id", float(sequence), update_modified=False)
        changed.append("%s -> %s" % (name, sequence))

    for name in WORKSPACE_HIDE:
        if not _workspace_exists(name):
            continue
        if frappe.db.get_value("Workspace", name, "is_hidden"):
            continue
        frappe.db.set_value("Workspace", name, "is_hidden", 1, update_modified=False)
        changed.append("%s hidden" % name)

    return changed


def apply_sidebar_links():
    """Reorder (and optionally hide) the links inside each workspace.

    Rows are reordered by rewriting `idx` only — no row is added, removed
    or retyped, so an upstream link we know nothing about keeps working.
    """
    changed = []

    for workspace, wanted in SIDEBAR_LINKS.items():
        if not _workspace_exists(workspace):
            continue

        rows = frappe.get_all(
            "Workspace Link",
            filters={"parent": workspace, "parenttype": "Workspace"},
            fields=["name", "label", "idx"],
            order_by="idx asc",
        )
        if not rows:
            continue

        rank = {label: position for position, label in enumerate(wanted)}
        tail = len(wanted)

        # Listed links take the given order; everything else keeps its
        # existing relative order behind them.
        ordered = sorted(
            rows,
            key=lambda row: (rank.get(row.label, tail), row.idx),
        )

        for position, row in enumerate(ordered, start=1):
            if row.idx == position:
                continue
            frappe.db.set_value("Workspace Link", row.name, "idx", position, update_modified=False)
            changed.append("%s: %s -> #%d" % (workspace, row.label, position))

    for workspace, labels in SIDEBAR_HIDE.items():
        if not _workspace_exists(workspace):
            continue
        for label in labels:
            for row in frappe.get_all(
                "Workspace Link",
                filters={"parent": workspace, "parenttype": "Workspace", "label": label, "hidden": 0},
                pluck="name",
            ):
                frappe.db.set_value("Workspace Link", row, "hidden", 1, update_modified=False)
                changed.append("%s: %s hidden" % (workspace, label))

    return changed


def apply_all():
    """Everything, in one call. Returns the combined change list."""
    changed = apply_added_links() + apply_workspace_order() + apply_sidebar_links()
    if changed:
        # The sidebar tree is cached in the boot payload.
        frappe.clear_cache()
    return changed


def apply_on_migrate():
    """after_migrate hook. Never allowed to fail a deploy.

    Adds this app's links (WORKSPACE_ADD_LINKS) every time; the reordering
    is a no-op until WORKSPACE_ORDER / SIDEBAR_LINKS above are filled in.
    """
    try:
        changed = apply_added_links()
        if WORKSPACE_ORDER or WORKSPACE_HIDE or SIDEBAR_LINKS or SIDEBAR_HIDE:
            changed += apply_workspace_order() + apply_sidebar_links()
        if changed:
            # The sidebar tree is cached in the boot payload.
            frappe.clear_cache()
    except Exception:
        frappe.log_error(title="HRMS Addon: workspace reorganisation failed")
