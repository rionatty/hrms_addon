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
Loans page is one of ours. Such a page is three records — the Workspace,
its Workspace Sidebar, and the Desktop Icon that puts it on the launcher
grid — and all three are SHIPPED AS FILES, which Frappe imports on every
migrate. What is here is only a fallback for a site whose sync did not
bring them in; it makes nothing that is already there.
"""

import json

import frappe

from hrms_addon.hrms_addon import navigation_rules as rules


def setup_on_migrate():
    """after_migrate: the cards and sidebar entries, never failing the deploy.

    One page at a time, each inside its own savepoint. A page that will
    not write costs only itself: doing them together meant one bad one
    undid every good one in the same run.

    Not quiet either. The reason goes to the migrate output, not only to
    the Error Log — the Error Log is on the server and so is the person
    reading the output, but only one of the two is in front of them.
    """
    units = _units()
    failed = []
    for number, (what, run) in enumerate(units):
        savepoint = "ha_nav_%d" % number
        frappe.db.savepoint(savepoint)
        try:
            run()
            frappe.db.commit()
        except Exception as error:
            try:
                frappe.db.rollback(save_point=savepoint)
            except Exception:
                pass
            failed.append(what)
            frappe.log_error(title="HRMS Addon: %s" % what)
            print("HRMS Addon: %s FAILED — %s: %s" % (what, type(error).__name__, error))
    if failed:
        print("HRMS Addon: %d of %d navigation steps failed (%s). The rest were applied."
              % (len(failed), len(units), ", ".join(failed)))


def _units():
    """Every navigation step, named, so one can fail without the others."""
    units = [("the %s page itself" % page["label"], lambda page=page: _ensure_page(page))
             for page in rules.PAGES]
    units += [("links on %s" % workspace, lambda w=workspace, c=cards: _apply_cards(w, c))
              for workspace, cards in rules.CARDS.items()]
    units += [("the %s sidebar" % workspace, lambda w=workspace, e=entries: _apply_sidebar(w, e))
              for workspace, entries in rules.SIDEBAR.items()]
    return units


def apply_navigation():
    """The same work in one go, raising rather than logging. This is what
    `bench execute` is for when something did not land."""
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
            "type": "Workspace", "app": rules.OWN_APP, "module": rules.MODULE,
            "icon": page["icon"], "sequence_id": page["sequence_id"],
            "public": 1, "parent_page": "", "content": "[]",
        })
        doc.flags.ignore_permissions = True
        doc.insert()
    if not frappe.db.exists("Workspace Sidebar", label):
        doc = frappe.get_doc({
            "doctype": "Workspace Sidebar", "name": label, "title": label,
            "app": rules.OWN_APP, "module": rules.MODULE, "header_icon": page["icon"],
            "standard": 1,
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
        # the app is ours, so the orphan sweep looks for the file where we
        # keep it; the grid it lands on is the one `parent_icon` names
        "app": rules.OWN_APP, "standard": 1, "hidden": 0,
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
    current = [row.as_dict() for row in doc.links]
    links = rules.merge_links(_prune(current), cards)
    content = rules.merge_content(json.loads(doc.content or "[]"), cards)
    if _same(links, current) and json.loads(doc.content or "[]") == content:
        return  # re-saving would only churn `modified` on every migrate
    _write(doc, "links", links)
    doc.content = json.dumps(content)
    doc.flags.ignore_permissions = True
    doc.save()


def _apply_sidebar(workspace, entries):
    if not frappe.db.exists("Workspace Sidebar", workspace):
        return
    doc = frappe.get_doc("Workspace Sidebar", workspace)
    current = [row.as_dict() for row in doc.items]
    items = rules.merge_sidebar(_prune(current), entries)
    if _same(items, current):
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
    for page in rules.PAGES:
        label = page["label"]
        for doctype in ("Workspace", "Workspace Sidebar", "Desktop Icon"):
            there = frappe.db.exists(doctype, label)
            lines.append("%-22s %-17s %s" % ("%s (%s)" % (label, doctype.lower()),
                                             "ok" if there else "NOT THERE",
                                             "" if there else "the file was not imported"))
    report = "\n".join(lines)
    print(report)
    return report


# what a row can point at, and the doctype each kind is a name in
LINK_KINDS = ("DocType", "Report", "Page", "Workspace", "Dashboard")


def _prune(rows):
    """The rows whose target is gone.

    Frappe validates every row of a child table when the parent is saved,
    so one link to a deleted DocType makes the whole page unwritable:

        LinkValidationError: Could not find Row #14:
        Link To: BSC Appraisal Template

    That was this app's own doctype until the scorecard moved onto Frappe
    HR's Appraisal Template. Deleting a doctype does not take the rows
    that point at it, and until they go nothing else can be written to the
    page — which is why Leaves and Tenure sat without their links while
    the run that would have added them was rolled back by this one row.
    """
    kept = []
    for row in rows:
        target, kind = row.get("link_to"), row.get("link_type")
        if kind in LINK_KINDS and target and not frappe.db.exists(kind, target):
            continue
        kept.append(row)
    return kept


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
