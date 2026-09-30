# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Which modules show on the desk (HRMS Addon Branding > Desk Modules).

The desktop's tiles are Desktop Icon records (Frappe v16), each with a
`hidden` flag that Frappe itself honours: on the desktop, and in the list of
modules under the sidebar's app name. The Desk Modules table lists every
tile, each module under its group (an app or a folder;
desk_modules_rules.py explains the nesting); saving sets their flags.

A group taken off the desk (Frappe HR's tile, say) leaves each of its
modules a tile of its own on the desk, as Frappe's desktop does whenever a
group is hidden.

One catch: a user who has rearranged their own desktop keeps a saved copy
of every tile (Desktop Layout), and Frappe shows that copy instead of the
shared list. The flags go into those copies too (_sync_layouts), only the
flags: what else each user arranged stays. public/js/hrms_addon_desk_modules.js
also hides the modules listed in frappe.boot.hrms_addon_hidden_modules by
name, never a group, whose tile would take its modules along.

Where the CyveTech UI app is installed too, its own Desk Modules decide, and
this does nothing: two tables setting the same flags would undo each other
on every save and migrate. Frappe v15 has no Desktop Icon, so there this
does nothing either.
"""

import json

import frappe
from frappe import _

from hrms_addon.hrms_addon import desk_modules_rules as rules

SETTINGS = "HRMS Addon Branding"
CHILD = "HRMS Addon Desk Module"
TABLE = "desk_modules"
DESKTOP_ICON = "Desktop Icon"
LAYOUT = "Desktop Layout"
# the app whose Desk Modules decide when it is installed alongside this one
OTHER_APP = "cyvetech_ui"


def managed_elsewhere():
    try:
        return OTHER_APP in frappe.get_installed_apps()
    except Exception:
        return False


def available():
    try:
        return bool(frappe.db.exists("DocType", DESKTOP_ICON)) and not managed_elsewhere()
    except Exception:
        return False


def status():
    """For the settings form: whether the table can be used here, and why
    not."""
    if managed_elsewhere():
        return {"available": 0, "message": _("CyveTech UI is installed. Set the desk modules in CyveTech UI Settings.")}
    if not available():
        return {"available": 0, "message": _("This version of Frappe has no desk tiles.")}
    return {"available": 1, "message": ""}


def desk_icons():
    """Every tile the desktop can show, groups and the modules in them alike:
    those shipped by an app or made by the Administrator (not users' own
    shortcuts)."""
    return frappe.get_all(
        DESKTOP_ICON,
        or_filters={"standard": 1, "owner": "Administrator"},
        fields=["name", "label", "app", "icon_type", "hidden", "parent_icon"],
        order_by="idx asc, label asc",
    )


def saved_rows():
    return frappe.get_all(
        CHILD,
        filters={"parenttype": SETTINGS, "parent": SETTINGS, "parentfield": TABLE},
        fields=["module", "app", "icon_type", "show_on_desk"],
        order_by="idx asc",
    )


def refresh_rows(settings_doc):
    """Fill the settings table from the current tiles, keeping choices made."""
    if not available():
        frappe.throw(status()["message"], title=_("Desk Modules"))
    current = [row.as_dict() for row in settings_doc.get(TABLE) or []]
    settings_doc.set(TABLE, rules.merge_rows(current, desk_icons()))


def apply():
    """Set each tile's hidden flag from the saved table. True if any changed."""
    if not available():
        return False
    rows = saved_rows()
    if not rows:
        return False  # the table was never filled in: the desk stays as it is
    updates = rules.changes(rows, desk_icons())
    for name, hidden in updates:
        frappe.db.set_value(DESKTOP_ICON, name, "hidden", hidden, update_modified=False)
    layouts = _sync_layouts(rows)
    if updates or layouts:
        # both are read straight from cache by get_desktop_icons(), and
        # set_value does not run Desktop Icon's own on_update that clears them
        frappe.cache.delete_key("desktop_icons")
        frappe.cache.delete_key("bootinfo")
    return bool(updates or layouts)


def _sync_layouts(rows):
    """Each saved desktop takes the table's choices as well. How many changed."""
    if not frappe.db.exists("DocType", LAYOUT):
        return 0
    changed = 0
    for saved in frappe.get_all(LAYOUT, fields=["name", "layout"]):
        try:
            layout = json.loads(saved.layout or "null")
        except ValueError:
            continue  # not ours to mend: Frappe falls back to the shared tiles
        wanted = rules.layout_with(layout, rows)
        if wanted is not None:
            frappe.db.set_value(LAYOUT, saved.name, "layout", json.dumps(wanted), update_modified=False)
            changed += 1
    return changed


def app_tile(app):
    """The label of an app's own tile (Frappe HR's for "hrms"), if it has one."""
    return next((icon.label for icon in desk_icons() if icon.icon_type == "App" and icon.app == app), None)


def hidden_labels():
    """For the desk boot. Never raises."""
    try:
        if not available():
            return []
        return rules.hidden_labels(saved_rows())
    except Exception:
        return []


def apply_on_migrate():
    """after_migrate: an app update can bring a hidden tile back; hide it again."""
    try:
        apply()
    except Exception:
        frappe.log_error(title="HRMS Addon: desk modules could not be applied")
