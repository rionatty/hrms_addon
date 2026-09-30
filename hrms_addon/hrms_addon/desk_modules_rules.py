# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Which desktop tiles show: the Desk Modules table on HRMS Addon Branding
against the Desktop Icon records. No Frappe import
(scripts/verify_desk_modules.py). The same rules as the CyveTech UI app's
Desk Modules.

icons: [{"name", "label", "app", "icon_type", "hidden", "parent_icon"}], the
       Desktop Icon rows.
rows:  [{"module", "group", "app", "icon_type", "show_on_desk"}], the
       settings table, keyed by the icon's label, which is also its name.

HOW THE DESKTOP NESTS ITS TILES (Frappe v16, desk/page/desktop/desktop.js)

An app's tile ("App") and a folder ("Folder") are groups: the tiles whose
parent_icon names one show inside it. Hiding a group does not hide what is
in it: the desktop shows those tiles on their own instead. ERPNext ships its
app tile hidden, which is why Selling, Stock and the rest each have a tile
of their own. So the table lists every tile, each module under its group,
and unticking Frappe HR puts Leaves, Payroll and the rest on the desk.

A user who has rearranged their desktop keeps a copy of every tile of their
own (Desktop Layout), which the desktop shows instead of the shared list, so
the table's choices go into those copies too (layout_with).
"""

GROUP_TYPES = ("App", "Folder")


def ordered(icons):
    """The icons as the desktop nests them: each tile of its own, and straight
    after a group the tiles inside it, each run in the order given."""
    labels = {icon["label"] for icon in icons}
    children = {}
    top = []
    for icon in icons:
        parent = icon.get("parent_icon")
        if parent and parent in labels and parent != icon["label"]:
            children.setdefault(parent, []).append(icon)
        else:
            top.append(icon)  # no group, or one that is gone: it shows on its own

    out = []
    seen = set()

    def walk(icon):
        if icon["label"] in seen:
            return
        seen.add(icon["label"])
        out.append(icon)
        for child in children.get(icon["label"], []):
            walk(child)

    for icon in top:
        walk(icon)
    # groups that name each other (a loop) are never reached from the top: list them last
    out.extend(icon for icon in icons if icon["label"] not in seen)
    return out


def merge_rows(rows, icons):
    """The table for the icons there are now.

    Each icon keeps the choice already made for it; an icon new to the table
    comes in as it currently is (shown unless already hidden); an icon that
    no longer exists drops out.
    """
    choice = {row["module"]: 1 if row.get("show_on_desk") else 0 for row in rows}
    labels = {icon["label"] for icon in icons}
    return [
        {
            "module": icon["label"],
            "group": icon.get("parent_icon") if icon.get("parent_icon") in labels else "",
            "app": icon.get("app") or "",
            "icon_type": icon.get("icon_type") or "",
            "show_on_desk": choice.get(icon["label"], 0 if icon.get("hidden") else 1),
        }
        for icon in ordered(icons)
    ]


def changes(rows, icons):
    """[(icon name, hidden)] for each icon whose hidden flag must change."""
    by_label = {icon["label"]: icon for icon in icons}
    out = []
    for row in rows:
        icon = by_label.get(row["module"])
        if not icon:
            continue
        hidden = 0 if row.get("show_on_desk") else 1
        if (1 if icon.get("hidden") else 0) != hidden:
            out.append((icon["name"], hidden))
    return out


def hidden_labels(rows):
    """The labels of the modules taken off the desk, for the browser to hide
    by name as well. Never a group: hidden that way, its tile would take the
    modules in it along, where the desk shows them on their own."""
    return sorted(row["module"] for row in rows
                  if not row.get("show_on_desk") and row.get("icon_type") not in GROUP_TYPES)


def layout_with(layout, rows):
    """A user's saved desktop (their own copy of every tile) with each tile
    in the table shown or hidden as the table says, or None when nothing
    changes. What else they arranged (the order, folders of their own)
    stays as they left it.

    layout: the list of tiles Frappe saved for them."""
    if not isinstance(layout, list):
        return None
    wanted = {row["module"]: 0 if row.get("show_on_desk") else 1 for row in rows}
    changed = False
    out = []
    for icon in layout:
        label = icon.get("label") if isinstance(icon, dict) else None
        if label in wanted and (1 if icon.get("hidden") else 0) != wanted[label]:
            icon = dict(icon, hidden=wanted[label])
            changed = True
        out.append(icon)
    return out if changed else None
