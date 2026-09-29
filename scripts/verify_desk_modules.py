"""Verify the Desk Modules setting without a bench:

    python scripts/verify_desk_modules.py

HRMS Addon Branding > Desk Modules lists every tile on the desk (Frappe
v16's Desktop Icon records), each module under its group, and unticking one
takes its tile off everyone's desk. The same rules as the CyveTech UI app's
Desk Modules; where that app is installed too, its table decides.

  1  the rules: nesting, merging the table, what changes, what is hidden
  2  the documents: the Desk Modules tab and its table
  3  the glue: loaded from the tiles, applied on save, on Apply Now and on
     every migrate, shipped with the boot, hidden in the browser too
  4  what Frappe v16 must still do for this to hold
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(*parts):
    path = os.path.join(APPS_ROOT, *parts)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def function(source, name):
    """The text of one top-level def (or method) in a module's source."""
    match = re.search(r"(?m)^( *)def %s\(.*?(?=^\1(?:def |@|class )|^(?:def |@|class )|\Z)" % name, source, re.S)
    return match.group(0) if match else ""


def check(label, ok, got=None):
    if not ok:
        fail.append(label if got is None else "%s: got %r" % (label, got))


R = load("desk_modules_rules")
print("loaded desk_modules_rules.py without Frappe")


# ── 1. The rules ──────────────────────────────────────────────────────
def icon(label, hidden=0, app="erpnext", icon_type="App", parent=None):
    return {"name": label, "label": label, "app": app, "icon_type": icon_type, "hidden": hidden,
            "parent_icon": parent}


def row(module, show):
    return {"module": module, "app": "erpnext", "icon_type": "App", "show_on_desk": show}


# as ERPNext v16 ships them (erpnext/*/desktop_icon/*.json), in idx order
DESKTOP = [
    icon("Accounting", icon_type="Folder"),
    icon("Selling", icon_type="Link", parent="ERPNext"),
    icon("Taxes", icon_type="Link", parent="Accounting"),
    icon("ERPNext", hidden=1),
    icon("Subcontracting", icon_type="Link"),
    icon("Stock", icon_type="Link", parent="ERPNext"),
    icon("Support", hidden=1, icon_type="Link", parent="ERPNext"),
    icon("Banking", icon_type="Link", parent="Accounting"),
]

check("each group is followed by the modules inside it",
      [i["label"] for i in R.ordered(DESKTOP)]
      == ["Accounting", "Taxes", "Banking", "ERPNext", "Selling", "Stock", "Support", "Subcontracting"],
      [i["label"] for i in R.ordered(DESKTOP)])
check("a module whose group is gone stands on its own",
      [i["label"] for i in R.ordered([icon("Selling", icon_type="Link", parent="Gone"),
                                       icon("Stock", icon_type="Link")])] == ["Selling", "Stock"])
nested = [icon("Leaves", icon_type="Link", parent="People"), icon("People", icon_type="Folder", parent="Frappe HR"),
          icon("Frappe HR", app="hrms")]
check("groups inside groups nest", [i["label"] for i in R.ordered(nested)] == ["Frappe HR", "People", "Leaves"],
      [i["label"] for i in R.ordered(nested)])
loop = [icon("A", icon_type="Folder", parent="B"), icon("B", icon_type="Folder", parent="A"), icon("C", icon_type="Link")]
check("two groups naming each other are still listed once each",
      sorted(i["label"] for i in R.ordered(loop)) == ["A", "B", "C"] and len(R.ordered(loop)) == 3)

rows = R.merge_rows([], DESKTOP)
by_module = {r["module"]: r for r in rows}
check("every tile is listed, with the group it sits in",
      len(rows) == len(DESKTOP) and by_module["Selling"]["group"] == "ERPNext"
      and by_module["Taxes"]["group"] == "Accounting" and by_module["Subcontracting"]["group"] == ""
      and by_module["Accounting"]["icon_type"] == "Folder", rows)
check("a hidden group does not untick the modules in it (ERPNext's own tile ships hidden)",
      (by_module["ERPNext"]["show_on_desk"], by_module["Selling"]["show_on_desk"], by_module["Support"]["show_on_desk"])
      == (0, 1, 0))
check("new tiles come in as they are",
      [(r["module"], r["show_on_desk"]) for r in R.merge_rows([], [icon("Selling"), icon("Quality", hidden=1)])]
      == [("Selling", 1), ("Quality", 0)])
check("choices already made are kept",
      [(r["module"], r["show_on_desk"]) for r in R.merge_rows([row("Selling", 0)], [icon("Selling"), icon("Buying")])]
      == [("Selling", 0), ("Buying", 1)])
check("a tile that is gone drops out", [r["module"] for r in R.merge_rows([row("Old", 0)], [icon("Selling")])]
      == ["Selling"])
check("a module whose group is gone is listed with no group",
      [(r["module"], r["group"]) for r in R.merge_rows([], [icon("Selling", icon_type="Link", parent="Gone")])]
      == [("Selling", "")])
check("only tiles whose flag differs change",
      R.changes([row("Selling", 0), row("Buying", 1), row("Stock", 1)],
                [icon("Selling"), icon("Buying", hidden=1), icon("Stock")]) == [("Selling", 1), ("Buying", 0)])
check("a row for a tile that is gone is ignored", R.changes([row("Gone", 0)], [icon("Selling")]) == [])
check("nothing to do when everything matches", R.changes([row("Selling", 1)], [icon("Selling")]) == [])
check("the unticked, by name, sorted",
      R.hidden_labels([row("Stock", 0), row("Selling", 1), row("Assets", 0)]) == ["Assets", "Stock"])
check("an app's tile and a folder are the groups", tuple(R.GROUP_TYPES) == ("App", "Folder"))
print("rules: nesting, the table, the changes, the hidden")

# ── 2. The documents ──────────────────────────────────────────────────
branding = json.loads(read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_branding", "hrms_addon_branding.json"))
fields = {f["fieldname"]: f for f in branding["fields"]}
order = branding["field_order"]
check("field_order and fields agree on HRMS Addon Branding", sorted(order) == sorted(fields))
check("the Branding tab comes first",
      order and order[0] == "tab_branding" and fields["tab_branding"]["fieldtype"] == "Tab Break"
      and fields["tab_branding"].get("label") == "Branding")
tab = fields.get("tab_desk_modules") or {}
table = fields.get("desk_modules") or {}
help_field = fields.get("desk_modules_help") or {}
check("a Desk Modules tab", tab.get("fieldtype") == "Tab Break" and tab.get("label") == "Desk Modules")
check("the tab holds the help and the table, in that order",
      "tab_desk_modules" in order and order[order.index("tab_desk_modules"):]
      == ["tab_desk_modules", "desk_modules_help", "desk_modules"], order)
check("the help is an HTML field", help_field.get("fieldtype") == "HTML")
check("the table lists HRMS Addon Desk Module rows",
      (table.get("fieldtype"), table.get("options"), table.get("label"))
      == ("Table", "HRMS Addon Desk Module", "Modules on the Desk"), table)
check("its hint says it is not about access", table.get("description") == "Hiding a module does not change who can open it.")
check("only the System Manager keeps these settings",
      [p.get("role") for p in branding.get("permissions", [])] == ["System Manager"])
check("no field is named custom_section", "custom_section" not in json.dumps(branding))

child = json.loads(read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_desk_module", "hrms_addon_desk_module.json"))
cfields = {f["fieldname"]: f for f in child["fields"]}
check("HRMS Addon Desk Module is a child table of this app",
      child.get("istable") == 1 and child.get("module") == "HRMS Addon" and child.get("name") == "HRMS Addon Desk Module")
check("its columns: Module, Group, Type, Show on Desk",
      [f["fieldname"] for f in child["fields"] if f.get("in_list_view")] == ["module", "group", "icon_type", "show_on_desk"])
check("the tile's own facts are read-only",
      all(cfields[name].get("read_only") == 1 for name in ("module", "group", "icon_type", "app")))
check("Show on Desk is a tick, on by default",
      (cfields["show_on_desk"]["fieldtype"], cfields["show_on_desk"].get("default"), cfields["show_on_desk"].get("read_only"))
      == ("Check", "1", None))
check("the child table has its controller (bench migrate needs it)",
      "class HRMSAddonDeskModule(Document)" in read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_desk_module",
                                                     "hrms_addon_desk_module.py"))
print("documents: the tab and its table")

# ── 3. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "desk_modules.py")
for needle, why in (
    ('SETTINGS = "HRMS Addon Branding"', "the table lives on HRMS Addon Branding"),
    ('CHILD = "HRMS Addon Desk Module"', "its rows are HRMS Addon Desk Module"),
    ('OTHER_APP = "cyvetech_ui"', "the CyveTech UI app's own table decides where it is installed"),
    ("return OTHER_APP in frappe.get_installed_apps()", "the other app is looked for among the installed"),
    ('bool(frappe.db.exists("DocType", DESKTOP_ICON)) and not managed_elsewhere()',
     "nothing is done on a Frappe with no tiles, or where the other app decides"),
    ('or_filters={"standard": 1, "owner": "Administrator"}', "the tiles apps ship and the Administrator made, not users' own"),
    ('filters={"parenttype": SETTINGS, "parent": SETTINGS, "parentfield": TABLE}', "the rows of the settings' own table"),
    ("settings_doc.set(TABLE, rules.merge_rows(current, desk_icons()))", "loading keeps the choices made"),
    ("return False  # the table was never filled in", "a table never filled in leaves the desk as it is"),
    ('frappe.db.set_value(DESKTOP_ICON, name, "hidden", hidden, update_modified=False)', "each tile's own hidden flag is set"),
    ('frappe.cache.delete_key("desktop_icons")', "the tiles' cache is cleared (get_desktop_icons reads it)"),
    ('frappe.cache.delete_key("bootinfo")', "and the boot's"),
    ('frappe.log_error(title="HRMS Addon: desk modules could not be applied")', "a failure on migrate is logged, not fatal"),
):
    check("desk_modules.py: %s" % why, needle in glue)
check("desk_modules.py: the boot's list never raises",
      "try:" in function(glue, "hidden_labels") and "except Exception:" in function(glue, "hidden_labels"))
check("desk_modules.py: loading refuses where the table cannot be used",
      "if not available():" in function(glue, "refresh_rows") and "frappe.throw(" in function(glue, "refresh_rows"))
check("desk_modules.py: the reason where it cannot be used names CyveTech UI Settings",
      "CyveTech UI Settings" in function(glue, "status"))

controller = read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_branding", "hrms_addon_branding.py")
check("saving the settings sets the tiles", "if desk_modules.apply():" in function(controller, "on_update"))
refresh = function(controller, "refresh_desk_modules")
check("Load Desk Modules is a method of the form, for the System Manager",
      refresh and "@frappe.whitelist()\n    def refresh_desk_modules(self):" in controller
      and 'frappe.only_for(("System Manager", "Administrator"))' in refresh and "desk_modules.refresh_rows(self)" in refresh)
check("Apply Now sets the tiles too", "if desk_modules.apply():" in function(controller, "apply_now"))
check("the form asks whether the tab can be used here",
      'frappe.only_for(("System Manager", "Administrator"))' in function(controller, "get_desk_modules_status")
      and "return desk_modules.status()" in function(controller, "get_desk_modules_status"))

form = read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_branding", "hrms_addon_branding.js")
for needle, why in (
    ('frm.call("refresh_desk_modules")', "Load Desk Modules fills the table"),
    ("get_desk_modules_status", "the help says why the table cannot be used, where it cannot"),
    ('frappe.ui.form.on("HRMS Addon Desk Module", {', "unticking a group is handled"),
    ('["App", "Folder"].includes(group.icon_type)', "only for a group"),
    ('frm.set_df_property("desk_modules", "cannot_add_rows", 1)', "no row is typed in"),
    ('frm.set_df_property("desk_modules", "cannot_delete_rows", 1)', "nor deleted"),
):
    check("the form: %s" % why, needle in form)

hooks = read("hrms_addon", "hooks.py")
live = "\n".join(line for line in hooks.splitlines() if not line.lstrip().startswith("#"))
check("every migrate hides again what an update brought back",
      '"hrms_addon.hrms_addon.desk_modules.apply_on_migrate",' in live.split("after_migrate = [", 1)[-1].split("]", 1)[0])
check("the desk script loads on every page",
      '"/assets/hrms_addon/js/hrms_addon_desk_modules.js",' in live.split("app_include_js = [", 1)[-1].split("]", 1)[0])
theme = read("hrms_addon", "hrms_addon", "theme.py")
check("the boot carries the tiles taken off the desk",
      "bootinfo.hrms_addon_hidden_modules = desk_modules.hidden_labels()" in function(theme, "boot_session"))
desk_js = read("hrms_addon", "public", "js", "hrms_addon_desk_modules.js")
check("the browser hides each such tile by name, for users with a layout of their own",
      '.desktop-icon[data-id="${css_string(label)}"]' in desk_js
      and "hrms_addon.hide_desk_modules(frappe.boot.hrms_addon_hidden_modules)" in desk_js
      and "display: none !important;" in desk_js)
print("glue: loaded, applied on save, Apply Now and migrate, in the boot, hidden in the browser")

# ── 4. What Frappe v16 must still do ──────────────────────────────────
icon_json = upstream("frappe", "frappe", "desk", "doctype", "desktop_icon", "desktop_icon.json")
if icon_json is None:
    print("upstream: Frappe not found at %s, skipped" % APPS_ROOT)
else:
    spec = {f["fieldname"]: f for f in json.loads(icon_json)["fields"]}
    for name in ("label", "app", "icon_type", "hidden", "parent_icon", "standard"):
        check("Frappe's Desktop Icon still has %s" % name, name in spec)
    check("its types are still App, Link and Folder",
          {"App", "Link", "Folder"} <= set((spec.get("icon_type", {}).get("options") or "").split("\n")))
    icons_py = upstream("frappe", "frappe", "desk", "doctype", "desktop_icon", "desktop_icon.py") or ""
    check("get_desktop_icons still caches the tiles under desktop_icons",
          'frappe.cache.hget("desktop_icons", user)' in icons_py)
    tile = upstream("frappe", "frappe", "public", "js", "frappe", "ui", "desktop_icon.html") or ""
    check("a tile still carries its label as data-id", 'class="desktop-icon" data-id="{{ icon.label}}"' in tile)
    header = upstream("frappe", "frappe", "public", "js", "frappe", "ui", "sidebar", "sidebar_header.js") or ""
    check("the sidebar's list of modules still leaves hidden tiles out", "!icon.hidden" in header)
    print("upstream: Desktop Icon, its cache, the tile markup and the sidebar list as this relies on")

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL DESK MODULE CHECKS PASSED")
