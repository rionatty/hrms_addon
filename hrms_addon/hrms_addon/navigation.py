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
What it does put right is its own: a link of ours found twice, or in a card
that is not its own, goes back once into the right one, and the rows are
numbered afresh whenever they are written (navigation_rules.numbered).

A workspace that is not installed is skipped, so the app still installs on
a site without Frappe HR. The exception is a page this app makes of its
own (navigation_rules.PAGES): Frappe HR has no page for lending, so the
Loans page is created here and then filled the same way as theirs. Such a
page is three records — the Workspace, its Workspace Sidebar, and the
Desktop Icon that puts it on the launcher grid.
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
    for page in rules.PAGES:
        _ensure_page(page)
    for workspace, cards in rules.CARDS.items():
        _apply_cards(workspace, cards)
    for workspace, entries in rules.SIDEBAR.items():
        _apply_sidebar(workspace, entries)
    frappe.db.commit()


def _ensure_page(page):
    """A page of our own, made once. What goes on it is merged in like any
    other page afterwards, so this never rewrites one that is already
    there — a card someone added by hand survives the next migrate."""
    label = page["label"]
    if not frappe.db.exists("Workspace", label):
        doc = frappe.get_doc({
            "doctype": "Workspace", "name": label, "label": label, "title": label,
            "type": "Workspace", "app": rules.HOST_APP, "module": rules.MODULE,
            "icon": page["icon"], "sequence_id": page["sequence_id"],
            "public": 1, "parent_page": "", "content": "[]",
        })
        doc.flags.ignore_permissions = True
        doc.insert()
    if not frappe.db.exists("Workspace Sidebar", label):
        doc = frappe.get_doc({
            "doctype": "Workspace Sidebar", "name": label, "title": label,
            "app": rules.HOST_APP, "module": rules.MODULE, "header_icon": page["icon"],
            # not standard: a standard sidebar is exported into the app its
            # `app` names, which is Frappe HR's and not ours to write in
            "standard": 0,
            "items": rules.new_sidebar(label, page.get("sections") or ()),
        })
        doc.flags.ignore_permissions = True
        doc.insert()
    _ensure_icon(page)


def _ensure_icon(page):
    """The launcher tile. get_desktop_icons() builds the grid from Desktop
    Icon rows alone, so without one the page is on no grid however well
    the Workspace is set up. It sits under the app tile the page names,
    and only where that tile is really there."""
    label = page["label"]
    if not frappe.db.exists("DocType", "Desktop Icon") or frappe.db.exists("Desktop Icon", label):
        return
    under = page.get("under")
    doc = frappe.get_doc({
        "doctype": "Desktop Icon", "name": label, "label": label,
        # the app is ours, so a developer-mode export writes the row into
        # this app rather than Frappe HR's; the grid it lands on is the one
        # `parent_icon` names, not the one `app` does
        "app": "hrms_addon", "standard": 1, "hidden": 0,
        "icon_type": "Link", "link_type": "Workspace Sidebar", "link_to": label,
        "icon": page["icon"], "bg_color": "blue",
        "parent_icon": under if under and frappe.db.exists("Desktop Icon", under) else None,
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    # both are read straight from cache by get_desktop_icons(); without
    # this the row is right and the launcher keeps serving the old grid
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")


def _apply_cards(workspace, cards):
    if not frappe.db.exists("Workspace", workspace):
        return
    doc = frappe.get_doc("Workspace", workspace)
    links = rules.merge_links([row.as_dict() for row in doc.links], cards)
    content = rules.merge_content(json.loads(doc.content or "[]"), cards)
    if _same(links, [row.as_dict() for row in doc.links]) and json.loads(doc.content or "[]") == content:
        return  # re-saving would only churn `modified` on every migrate
    _write(doc, "links", links)
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
    _write(doc, "items", items)
    doc.flags.ignore_permissions = True
    doc.save()


def show():
    """What is on the site's pages right now, and what is missing.

        bench --site <site> execute hrms_addon.hrms_addon.navigation.show

    Run it when a link this app adds is not on the page: it says whether
    the workspace is there at all (the app was never migrated), whether
    the link is on it (the page is cached in the browser) or whether it is
    missing (apply_navigation did not run, or failed into the Error Log).
    """
    lines = []
    for workspace, cards in rules.CARDS.items():
        wanted = [link[1] for _card, links in cards for link in links]
        if not frappe.db.exists("Workspace", workspace):
            lines.append("%-22s NO WORKSPACE      wanted: %s" % (workspace, ", ".join(wanted)))
            continue
        on_it = set(frappe.get_all("Workspace Link", filters={"parent": workspace, "parenttype": "Workspace"},
                                   pluck="link_to"))
        missing = [link for link in wanted if link not in on_it]
        lines.append("%-22s %-17s %s" % (workspace, "page ok" if not missing else "MISSING",
                                         ", ".join(missing) or "all %d there" % len(wanted)))
    for workspace, entries in rules.SIDEBAR.items():
        wanted = [entry[1] for entry in entries]
        if not frappe.db.exists("Workspace Sidebar", workspace):
            lines.append("%-22s NO SIDEBAR        wanted: %s" % (workspace, ", ".join(wanted)))
            continue
        on_it = set(frappe.get_all("Workspace Sidebar Item",
                                   filters={"parent": workspace, "parenttype": "Workspace Sidebar"},
                                   pluck="link_to"))
        missing = [link for link in wanted if link not in on_it]
        lines.append("%-22s %-17s %s" % (workspace + " (sidebar)", "ok" if not missing else "MISSING",
                                         ", ".join(missing) or "all %d there" % len(wanted)))
    report = "\n".join(lines)
    print(report)
    return report


def _write(doc, table, rows):
    """Replace the table's rows, numbered afresh: a row read from the
    database keeps the idx it had, so one put in before it would share its
    number and the two come back in either order (navigation_rules.numbered)."""
    doc.set(table, [])
    for row in rules.numbered(rows):
        doc.append(table, row)


def _same(wanted, current):
    """Whether the rows say the same thing, ignoring what the database adds
    (names, timestamps), and are numbered 1, 2, 3... as they must be to come
    back in this order every time."""
    keys = ("type", "label", "link_type", "link_to", "child", "link_count")

    def shape(rows):
        return [tuple(row.get(key) for key in keys) for row in rows]

    in_order = [row.get("idx") for row in current] == list(range(1, len(current) + 1))
    return in_order and shape(wanted) == shape(current)
