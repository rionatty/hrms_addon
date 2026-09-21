"""Ship a page of ours as files, the way Frappe HR ships its ten.

Making the records in after_migrate was wrong twice over:

  * `remove_orphan_entities()` runs BEFORE the after_migrate hooks and
    deletes a public Workspace with a module and an app but no file behind
    it, and any standard Workspace Sidebar or Desktop Icon whose app folder
    has no file for it. A record made by a hook is exactly that, so it is
    swept at the start of the next migrate.
  * nothing but the hook created it, so if the hook did not run — or fell
    into the Error Log, which is what it is written to do — the page was
    simply not there, with nothing to look at.

Frappe's own sync_for() imports module-level workspace folders and the
app-level `workspace_sidebar` and `desktop_icon` folders on every migrate.
Files are therefore the durable answer: imported before the sweep, matched
by it, and complete whether or not any hook of ours runs.
"""
import importlib.util
import io
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
STAMP = "2026-09-21 20:00:00.000000"
OWN_APP = "hrms_addon"

spec = importlib.util.spec_from_file_location("navigation_rules", os.path.join(APP, "navigation_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print("wrote", os.path.relpath(path, REPO))


for page in rules.PAGES:
    label = page["label"]
    folder = label.lower().replace(" ", "_")
    cards = rules.CARDS[label]
    entries = rules.SIDEBAR[label]

    # ── the page ──────────────────────────────────────────────────────
    links = rules.merge_links([], cards)
    content = rules.merge_content([], cards)
    write(os.path.join(APP, "workspace", folder, folder + ".json"), {
        "app": OWN_APP, "charts": [], "content": json.dumps(content), "creation": STAMP,
        "custom_blocks": [], "docstatus": 0, "doctype": "Workspace", "for_user": "",
        "hide_custom": 0, "icon": page["icon"], "idx": 0, "is_hidden": 0, "label": label,
        "links": links, "modified": STAMP, "modified_by": "Administrator", "module": rules.MODULE,
        "name": label, "number_cards": [], "owner": "Administrator", "parent_page": "",
        "public": 1, "quick_lists": [], "roles": [], "sequence_id": page["sequence_id"],
        "shortcuts": [], "title": label, "type": "Workspace",
    })

    # ── its left-hand list ────────────────────────────────────────────
    items = rules.merge_sidebar(rules.new_sidebar(label, page.get("sections") or ()), entries)
    write(os.path.join(APP, "workspace_sidebar", folder + ".json"), {
        "app": OWN_APP, "docstatus": 0, "doctype": "Workspace Sidebar", "header_icon": page["icon"],
        "idx": 0, "items": rules.numbered(items), "modified": STAMP, "modified_by": "Administrator",
        "module": rules.MODULE, "name": label, "owner": "Administrator", "standard": 1,
        "title": label,
    })

    # ── the tile on the launcher grid ─────────────────────────────────
    write(os.path.join(APP, "desktop_icon", folder + ".json"), {
        "app": OWN_APP, "bg_color": "blue", "creation": STAMP, "docstatus": 0,
        "doctype": "Desktop Icon", "hidden": 0, "icon": page["icon"], "icon_type": "Link",
        "idx": 0, "label": label, "link_to": label, "link_type": "Workspace Sidebar",
        "modified": STAMP, "modified_by": "Administrator", "name": label, "owner": "Administrator",
        "parent_icon": page["under"], "restrict_removal": 0, "roles": [], "standard": 1,
    })
