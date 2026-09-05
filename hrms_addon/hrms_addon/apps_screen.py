# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Keep the launcher tile in step with hooks.py.

THE PROBLEM THIS EXISTS TO SOLVE

Frappe turns `add_to_apps_screen` into a **Desktop Icon database row**,
once, at install time. frappe/utils/install.py runs
auto_generate_icons_and_sidebar as after_app_install, which reaches
create_desktop_icons_from_installed_apps:

    for a in apps:
        if get_app_desktop_icon(a):
            continue                      # <- already has an icon: skip
        ...
        icon.link     = app_details[0]["route"]
        icon.logo_url = app_details[0]["logo"]

So the route and logo are COPIED INTO DATA on the first install and never
looked at again. Editing hooks.py afterwards changes nothing: `bench
migrate` does not touch the row, `bench restart` does not touch it, and
the generator skips the app because an icon already exists. The tile goes
on pointing wherever it pointed on day one.

That is exactly how the tile kept opening /desk/hr long after hooks.py
said otherwise. This function closes the gap: on every migrate it copies
the current hook values onto the existing row.

Deliberately NOT using frappe.utils.install.delete_desktop_icon_and_sidebar
to force a regenerate — that helper looks the icon up by the `app_name`
hook ("hrms_addon") while the row is named after the `app_title` hook
("HRMS Addon"), so it would not find ours. Updating in place is both
narrower and correct.

WHY THE ROUTE MUST START WITH /app

Not for navigation — v16 rewrites /app/(.*) to /desk/\\1, so both spellings
load the same page. It matters because of this, in
create_desktop_icons_from_workspace:

    if app_icon_link and not app_icon_link.startswith("/app"):
        icon.hidden = 1
        icon.parent_icon = None

An app whose icon link does not start with /app has all of ITS OWN
workspaces hidden from the launcher. That is observable on this site:
Frappe HR sets app_home = "/desk/people", and its Leaves, Recruitment,
Expenses and Payroll workspaces are absent from the launcher grid, while
ERPNext — which ships no app icon at all — has every workspace showing.

Right now this app has a single workspace sharing the app's title, so it
would be skipped on the label collision regardless. It will matter as
soon as a second workspace is added, which is the plan.
"""

import frappe

APP = "hrms_addon"


def _hook_entry():
    entries = frappe.get_hooks("add_to_apps_screen", app_name=APP)
    return entries[0] if entries else None


def _find_icon():
    """The Desktop Icon row for this app, by whichever column identifies it.

    create_desktop_icons_from_installed_apps() sets `app`, but the row is
    named after the app title, so both are worth trying before giving up.
    """
    entry = _hook_entry() or {}
    for filters in ({"app": APP}, {"label": entry.get("title")}):
        if not all(filters.values()):
            continue
        name = frappe.db.get_value("Desktop Icon", filters, "name")
        if name:
            return name
    return None


def sync_desktop_icon():
    """Copy the current hook route/logo onto the existing Desktop Icon.

    Idempotent — writes only what differs, so a repeat migrate is a no-op.
    Returns the list of fields actually changed.
    """
    if not frappe.db.exists("DocType", "Desktop Icon"):
        return []

    entry = _hook_entry()
    if not entry:
        return []

    name = _find_icon()
    if not name:
        # Nothing to correct. The install-time generator will create it,
        # and it reads the same hook, so it will be right from the start.
        return []

    changed = []
    for field, value in (("link", entry.get("route")), ("logo_url", entry.get("logo"))):
        if not value:
            continue
        if (frappe.db.get_value("Desktop Icon", name, field) or "") == value:
            continue
        frappe.db.set_value("Desktop Icon", name, field, value, update_modified=False)
        changed.append(field)

    if changed:
        # Both are read straight from cache by get_desktop_icons(); without
        # this the row is right but the launcher keeps serving the old one.
        frappe.cache.delete_key("desktop_icons")
        frappe.cache.delete_key("bootinfo")

    return changed


def sync_on_migrate():
    """after_migrate hook. Never allowed to fail a deploy."""
    try:
        sync_desktop_icon()
    except Exception:
        frappe.log_error(title="HRMS Addon: could not sync the launcher tile")
