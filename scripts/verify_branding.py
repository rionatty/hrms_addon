"""Cross-check the HRMS Addon branding + density contracts.

Companion to verify_hrms.py (which covers the colour palette). Same
premise: these settings are declared in three or four places each by
necessity — server boot, form script, doctype schema, stylesheet — so
something has to assert they still agree.
"""
import os, re, sys, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")


def read(rel):
    return open(BASE + "/" + rel, encoding="utf-8").read()


def block(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


css        = read("hrms_addon/public/css/hrms_addon.bundle.css")
theme_js   = read("hrms_addon/public/js/hrms_addon_theme.js")
theme_py   = read("hrms_addon/hrms_addon/theme.py")
theme_dt   = json.loads(read("hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/hrms_addon_theme_settings.json"))
brand_py   = read("hrms_addon/hrms_addon/branding.py")
brand_js   = read("hrms_addon/hrms_addon/doctype/hrms_addon_branding/hrms_addon_branding.js")
brand_ctrl = read("hrms_addon/hrms_addon/doctype/hrms_addon_branding/hrms_addon_branding.py")
brand_dt   = json.loads(read("hrms_addon/hrms_addon/doctype/hrms_addon_branding/hrms_addon_branding.json"))
desk_brand = read("hrms_addon/public/js/hrms_addon_branding.js")
ws_py      = read("hrms_addon/hrms_addon/workspace_setup.py")
hooks_live = "\n".join(l for l in read("hrms_addon/hooks.py").splitlines() if not l.lstrip().startswith("#"))

fail = []

# 1. DENSITY is declared in four places — they must agree.
py_dens = re.findall(r'"(\w+)"', re.search(r'DENSITIES = \(([^)]*)\)', theme_py).group(1))
py_default = re.search(r'DEFAULT_DENSITY = "(\w+)"', theme_py).group(1)
js_dens = re.findall(r'"(\w+)"', re.search(r'hrms_addon\.DENSITIES = \[([^\]]*)\]', theme_js).group(1))
js_default = re.search(r'hrms_addon\.DEFAULT_DENSITY = "(\w+)"', theme_js).group(1)
dens_field = [f for f in theme_dt["fields"] if f["fieldname"] == "density"]
dt_opts = dens_field[0]["options"].split("\n") if dens_field else []
dt_default = dens_field[0].get("default") if dens_field else None

print("density options  py=%s  js=%s  doctype=%s" % (py_dens, js_dens, dt_opts))
print("density default  py=%s  js=%s  doctype=%s" % (py_default, js_default, dt_default))
if not (py_dens == js_dens == dt_opts):
    fail.append("density options differ")
if not (py_default == js_default == dt_default):
    fail.append("density default differs")
if py_default not in py_dens:
    fail.append("DEFAULT_DENSITY %r is not one of DENSITIES" % py_default)

# The default lives in :root; each other value needs its own CSS block.
for d in py_dens:
    if d == py_default:
        continue
    if 'data-ha-density="%s"' % d.lower() not in css:
        fail.append("density %r has no CSS block" % d)

# Every density variable the form-density rules read must be set somewhere.
dens_used = set(re.findall(r'var\((--hra-d-[\w-]+)', css))
dens_set = set(re.findall(r'^\s*(--hra-d-[\w-]+)\s*:', css, re.M))
print("density CSS vars: %d used, %d set" % (len(dens_used), len(dens_set)))
if dens_used - dens_set:
    fail.append("density vars used but never set: %s" % sorted(dens_used - dens_set))

# The launcher fix needs all three parts; any one alone is a no-op.
launcher_parts = {
    "container width": "max-width: var(--hra-d-launcher-max)",
    "fixed tracks": "repeat(auto-fill, var(--hra-d-tile-w))",
    "centred leftover": "justify-content: center",
}
for label, needle in launcher_parts.items():
    if needle not in css:
        fail.append("launcher fix incomplete — missing %s (%r)" % (label, needle))
print("launcher fix: all 3 parts present")

# Comfortable must NOT touch the launcher (it means "upstream spacing").
for m in re.finditer(r'html\[data-ha-density="comfortable"\][^{]*\{([^}]*)\}', css, re.S):
    body = m.group(1)
    if "grid-template-columns" in body or "--hra-d-tile-w" in body:
        fail.append("Comfortable overrides the launcher — it should leave it alone")
print("Comfortable leaves the launcher alone")

# 2. BRANDING_TARGETS must name real fields on the Branding doctype.
targets = re.findall(r'^    "(\w+)":', block(brand_py, "BRANDING_TARGETS = {", "\n}"), re.M)
brand_fields = {f["fieldname"] for f in brand_dt["fields"]}
print("BRANDING_TARGETS: %d fields -> %s" % (len(targets), targets))
for t in targets:
    if t not in brand_fields:
        fail.append("BRANDING_TARGETS names non-existent field %r" % t)
for required in ("enabled", "rebrand_app_labels"):
    if required not in brand_fields:
        fail.append("Branding doctype missing %r" % required)
if brand_dt["module"] != "HRMS Addon":
    fail.append("Branding module is %r" % brand_dt["module"])
if not brand_dt.get("issingle"):
    fail.append("Branding must be a Single")

# Every target doctype/field pair should be one Frappe actually has.
KNOWN = {
    ("Website Settings", "app_name"), ("Website Settings", "app_logo"),
    ("Website Settings", "favicon"), ("Website Settings", "splash_image"),
    ("Website Settings", "footer_powered"), ("Navbar Settings", "app_logo"),
}
pairs = set(re.findall(r'\("(Website Settings|Navbar Settings)", "(\w+)"\)', brand_py))
unknown = pairs - KNOWN
if unknown:
    fail.append("branding writes unrecognised upstream fields: %s" % sorted(unknown))
print("branding upstream targets: %d, all recognised" % len(pairs))

# 3. Every frappe.call from the Branding form resolves in its controller.
calls = re.findall(r'method:\s*"([\w.]+)"', brand_js)
for path in calls:
    mod, fn = path.rsplit(".", 1)
    if mod != "hrms_addon.hrms_addon.doctype.hrms_addon_branding.hrms_addon_branding":
        fail.append("branding frappe.call has bad module: %s" % mod)
    if "def %s(" % fn not in brand_ctrl:
        fail.append("branding %s() not defined in controller" % fn)
print("branding whitelisted calls: %d, all resolve" % len(calls))

# 4. hooks.py after_migrate + extend_bootinfo must resolve to real functions.
MODULES = {
    "hrms_addon.hrms_addon.branding": brand_py,
    "hrms_addon.hrms_addon.workspace_setup": ws_py,
    "hrms_addon.hrms_addon.theme": theme_py,
    "hrms_addon.hrms_addon.apps_screen": read("hrms_addon/hrms_addon/apps_screen.py"),
}
hook_paths = re.findall(r'"(hrms_addon\.[\w.]+)"', block(hooks_live, "after_migrate = [", "]"))
hook_paths.append(re.search(r'extend_bootinfo = "([\w.]+)"', hooks_live).group(1))
for path in hook_paths:
    mod, fn = path.rsplit(".", 1)
    src = MODULES.get(mod)
    if src is None:
        fail.append("hook %s points at an unknown module" % path)
    elif "def %s(" % fn not in src:
        fail.append("hook %s: %s() is not defined" % (path, fn))
print("hooks: %d after_migrate/bootinfo targets resolve" % len(hook_paths))

# 5. The placeholder logo every static reference points at must exist.
refs = 0
for name, src in (("hooks.py", hooks_live), ("branding.py", brand_py)):
    for m in re.finditer(r'"(/assets/hrms_addon/images/[\w.-]+)"', src):
        refs += 1
        rel = "hrms_addon/public/" + m.group(1).split("/assets/hrms_addon/", 1)[1]
        if not os.path.exists(BASE + "/" + rel):
            fail.append("%s references missing asset %s" % (name, rel))
if not refs:
    fail.append("nothing references the placeholder logo")
print("placeholder logo: %d references, all resolve" % refs)

# 6. Boot keys wired end to end.
for key, files in (
    ("hrms_addon_branding", (("theme.py", theme_py), ("branding.py", brand_py), ("branding desk js", desk_brand))),
    ("hrms_addon_density", (("theme.py", theme_py), ("theme js", theme_js))),
):
    for name, text in files:
        if key not in text:
            fail.append("boot key %s missing from %s" % (key, name))
print("boot keys hrms_addon_branding + hrms_addon_density wired end to end")

# 7. The safety rule branding.py documents must actually be implemented:
#    a blank field is skipped, never written.
apply_src = block(brand_py, "def apply_branding(", "\ndef apply_branding_on_migrate")
if "if not value:" not in apply_src or "continue" not in apply_src:
    fail.append("apply_branding() no longer skips blank values — the SAFETY RULE is documented but not enforced")
print("branding SAFETY RULE (blank never clears) is enforced in code")

# 8. workspace_setup ships empty (pending the agreed order) but wired.
for decl in ("WORKSPACE_ORDER", "WORKSPACE_HIDE", "SIDEBAR_LINKS", "SIDEBAR_HIDE"):
    if decl not in ws_py:
        fail.append("workspace_setup missing %s" % decl)
if "def apply_on_migrate(" not in ws_py:
    fail.append("workspace_setup has no apply_on_migrate()")
print("workspace_setup declarations present")

# 8a. The launcher tile must land somewhere that exists.
#
#     This is the "Page hr not found" bug: `app_home` was pointing at a
#     route with no Workspace behind it. Two things make it easy to get
#     wrong — v16 rewrites /app/* to /desk/* (so an /app/ route 404s
#     silently under a different name), and frappe/boot.py builds the
#     tile's route from the `app_home` HOOK, not from the "route" key in
#     add_to_apps_screen. So both are checked, against the record that
#     actually ships.
ws_json = json.loads(read("hrms_addon/hrms_addon/workspace/hrms_addon/hrms_addon.json"))


def frappe_slug(name):
    # frappe/desk/utils.py
    return name.lower().replace(" ", "-")


expected_route = "/app/" + frappe_slug(ws_json["name"])
app_home = re.search(r'app_home = "([^"]+)"', hooks_live).group(1)
print("workspace %r -> %s" % (ws_json["name"], expected_route))
if app_home != expected_route:
    fail.append("app_home is %r but the shipped workspace resolves to %r" % (app_home, expected_route))
# The /app prefix is not about navigation (v16 rewrites /app/* to /desk/*).
# desktop_icon.py hides an app's OWN workspaces from the launcher when the
# app icon's link does not start with /app — observed on Frappe HR, whose
# app_home is /desk/people and whose workspaces are absent from the grid.
if not app_home.startswith("/app"):
    fail.append("app_home must start with /app or this app's workspaces are hidden from the launcher")
# The route is copied into a Desktop Icon row at install and never re-read,
# so something has to re-sync it or hooks.py and the tile drift apart.
if "apps_screen.sync_on_migrate" not in hooks_live:
    fail.append("apps_screen.sync_on_migrate is not in after_migrate — the tile will keep its install-time route")
tile_route = re.search(r'"route":\s*([^,\n]+)', hooks_live).group(1).strip()
if tile_route != "app_home":
    fail.append("add_to_apps_screen route should reuse app_home, got %s" % tile_route)
if ws_json["module"] != "HRMS Addon":
    fail.append("workspace module is %r — boot.py finds workspaces by Module Def.app_name" % ws_json["module"])
if not ws_json.get("public"):
    fail.append("workspace must be public or it will not appear")

# Card blocks in `content` reference a Card Break in `links` by name;
# a mismatch renders an empty card with no error.
content_cards = {b["data"]["card_name"] for b in json.loads(ws_json["content"]) if b["type"] == "card"}
card_breaks = {l["label"] for l in ws_json["links"] if l["type"] == "Card Break"}
if not content_cards <= card_breaks:
    fail.append("workspace card_name with no matching Card Break: %s" % sorted(content_cards - card_breaks))

# Every DocType the workspace links to must actually ship in this app.
for l in ws_json["links"]:
    if l["type"] != "Link" or l.get("link_type") != "DocType":
        continue
    folder = l["link_to"].lower().replace(" ", "_")
    if not os.path.exists(BASE + "/hrms_addon/hrms_addon/doctype/%s/%s.json" % (folder, folder)):
        fail.append("workspace links to %r which this app does not ship" % l["link_to"])
print("workspace wiring: route, module, %d cards, %d links all resolve"
      % (len(content_cards), len([l for l in ws_json["links"] if l["type"] == "Link"])))

# 8b. Every package directory needs __init__.py or Frappe cannot import
#     the controller. Easy to forget when adding a doctype by hand.
pkg_roots = [BASE + "/hrms_addon"]
missing_init = []
for root in pkg_roots:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "public", "fixtures")]
        rel = os.path.relpath(dirpath, BASE).replace("\\", "/")
        if rel.startswith("hrms_addon/templates") or "/public" in rel:
            continue
        if any(f.endswith(".py") for f in filenames) or "doctype" in rel:
            if "__init__.py" not in filenames:
                missing_init.append(rel)
if missing_init:
    fail.append("missing __init__.py in: %s" % sorted(missing_init))
print("package __init__.py present in every module dir")

# 9. Bracket balance on the two new JS files.
for name in ("hrms_addon/public/js/hrms_addon_branding.js",
             "hrms_addon/hrms_addon/doctype/hrms_addon_branding/hrms_addon_branding.js"):
    text = read(name)
    stripped = re.sub(
        r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`',
        '', text, flags=re.S)
    for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
        if stripped.count(op) != stripped.count(cl):
            fail.append("%s: unbalanced %s%s (%d vs %d)" % (name, op, cl, stripped.count(op), stripped.count(cl)))
print("JS bracket balance checked on 2 files")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL BRANDING/DENSITY CHECKS PASSED")
