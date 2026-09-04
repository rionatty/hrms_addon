"""Cross-check the HRMS Addon palette contract.

The same field->colour mapping is duplicated in four places by design
(server boot, form preview, doctype schema, stylesheet). This asserts
they still agree, plus a few structural checks on the ported JS.
"""
import os, re, sys, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
DT = BASE + "/hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings"

def read(rel):
    return open(BASE + "/" + rel, encoding="utf-8").read()

css      = read("hrms_addon/public/css/hrms_addon.bundle.css")
theme_js = read("hrms_addon/public/js/hrms_addon_theme.js")
side_js  = read("hrms_addon/public/js/form_sidebar_toggle.js")
py       = read("hrms_addon/hrms_addon/theme.py")
js       = read("hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/hrms_addon_theme_settings.js")
ctrl     = read("hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/hrms_addon_theme_settings.py")
dt       = json.loads(read("hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/hrms_addon_theme_settings.json"))

fail = []

def block(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]

# 1. FIELD_TO_VAR (theme.py) vs HA_THEME_FIELDS (settings js)
py_map = dict(re.findall(r'"(\w+)":\s*"(--hra-[\w-]+)"', block(py, "FIELD_TO_VAR = {", "}")))
js_map = dict(re.findall(r'(\w+):\s*"(--hra-[\w-]+)"', block(js, "const HA_THEME_FIELDS", "};")))
print("FIELD_TO_VAR: %d entries | HA_THEME_FIELDS: %d entries" % (len(py_map), len(js_map)))
if py_map != js_map:
    fail.append("py/js palette maps differ: %s" % (set(py_map.items()) ^ set(js_map.items())))

# 2. DEFAULTS keys == FIELD_TO_VAR keys
defaults = dict(re.findall(r'"(\w+)":\s*"(#[0-9A-Fa-f]{3,6})"', block(py, "DEFAULTS = {", "}")))
print("DEFAULTS: %d entries" % len(defaults))
if set(defaults) != set(py_map):
    fail.append("DEFAULTS keys != FIELD_TO_VAR keys: %s" % (set(defaults) ^ set(py_map)))

# 3. DEFAULTS values match the stylesheet — scan EVERY :root block.
#    There are two: the palette at the top, and the cockpit canvas below.
root_blocks = re.findall(r'^:root \{(.*?)^\}', css, re.M | re.S)
print("CSS :root blocks: %d" % len(root_blocks))
root_vars = dict(re.findall(r'(--hra-[\w-]+):\s*([^;]+);', "".join(root_blocks)))
for field, var in py_map.items():
    want = defaults.get(field, "").lower()
    got = (root_vars.get(var) or "").strip().lower()
    if var not in root_vars:
        fail.append("%s (%s) not in CSS :root" % (var, field))
    elif got != want:
        fail.append("%s: DEFAULTS=%s but CSS :root=%s" % (var, want, got))

# 4. every var() reference is defined somewhere in the stylesheet
used = set(re.findall(r'var\((--hra-[\w-]+)', css))
defined = set(re.findall(r'^\s*(--hra-[\w-]+)\s*:', css, re.M))
print("CSS vars: %d used, %d defined" % (len(used), len(defined)))
if used - defined:
    fail.append("CSS references undefined vars: %s" % sorted(used - defined))

# 5. doctype Color fields == palette fields
colour_fields = {f["fieldname"] for f in dt["fields"] if f["fieldtype"] == "Color"}
print("doctype: %s | %d fields, %d Color" % (dt["name"], len(dt["fields"]), len(colour_fields)))
if colour_fields != set(py_map):
    fail.append("Color fields != palette fields: %s" % (colour_fields ^ set(py_map)))
if dt["module"] != "HRMS Addon":
    fail.append("doctype module is %r" % dt["module"])
if not dt.get("issingle"):
    fail.append("theme settings must be a Single")

# 6. the whitelisted method the form calls actually exists
path = re.search(r'method:\s*"([\w.]+)"', js).group(1)
mod, fn = path.rsplit(".", 1)
print("whitelisted call: %s" % path)
if mod != "hrms_addon.hrms_addon.doctype.hrms_addon_theme_settings.hrms_addon_theme_settings":
    fail.append("frappe.call module path wrong: %s" % mod)
if "def %s(" % fn not in ctrl:
    fail.append("%s() not defined in controller" % fn)
if "@frappe.whitelist()" not in ctrl:
    fail.append("controller has no @frappe.whitelist()")

# 7. boot keys agree across the three files that touch them
for key in ("hrms_addon_theme", "hrms_addon_workspace_cockpit"):
    for name, text in (("theme.py", py), ("hrms_addon_theme.js", theme_js), ("settings.js", js)):
        if key not in text:
            fail.append("boot key %s missing from %s" % (key, name))
print("boot keys present in theme.py, hrms_addon_theme.js, settings.js")

# 8. classes the JS toggles must exist in the stylesheet
for cls, where in (("ha-cockpit", theme_js), ("ha-form-sidebar-collapsed", side_js), ("ha-sidebar-toggle", side_js)):
    if cls not in where:
        fail.append("%s not referenced by its JS" % cls)
    if "." + cls not in css and cls not in css:
        fail.append("%s has no styling in the bundle" % cls)
print("toggled classes styled: ha-cockpit, ha-form-sidebar-collapsed, ha-sidebar-toggle")

# 9. no leftover stock_addon identifiers in LIVE CODE.
#    Provenance notes in comments/docstrings are deliberate and stay, so
#    blank comments out (preserving line numbers) before scanning.
def strip_comments(text, ext):
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    if ext == ".py":
        text = re.sub(r'"""(?:[^"\\]|\\.|"(?!""))*"""', blank, text, flags=re.S)
        text = re.sub(r"'''(?:[^'\\]|\\.|'(?!''))*'''", blank, text, flags=re.S)
        text = re.sub(r'#[^\n]*', blank, text)
    elif ext in (".js", ".css"):
        text = re.sub(r'/\*.*?\*/', blank, text, flags=re.S)
        if ext == ".js":
            text = re.sub(r'//[^\n]*', blank, text)
    elif ext in (".txt", ".yml", ".toml"):
        text = re.sub(r'#[^\n]*', blank, text)
    return text

leftovers = []
for dirpath, dirnames, filenames in os.walk(BASE):
    # `scripts` holds these verifiers, whose own pattern lists name the
    # very identifiers being hunted. Checking the checker is noise.
    dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "node_modules", "scripts")]
    for fn2 in filenames:
        if not fn2.endswith((".py", ".js", ".css", ".json", ".txt", ".toml", ".yml", ".md")):
            continue
        full = os.path.join(dirpath, fn2)
        rel = os.path.relpath(full, BASE)
        # README documents the rename table on purpose
        if rel.lower() == "readme.md":
            continue
        raw = open(full, encoding="utf-8", errors="replace").read()
        code = strip_comments(raw, os.path.splitext(fn2)[1])
        for pat in (r"stock_addon", r"Stock Addon", r"--agri-", r"\bagri-btn-main\b",
                    r"\bsa-cockpit\b", r"\bsa-sidebar-toggle\b", r"\bsa-form-sidebar-collapsed\b",
                    r"\bSA_THEME_FIELDS\b", r"\bsa_preview\b", r"StockAddon"):
            for m in re.finditer(pat, code):
                line = code[:m.start()].count("\n") + 1
                src = raw.splitlines()[line - 1].strip()
                leftovers.append("%s:%d  %s  |  %s" % (rel, line, m.group(0), src[:70]))
print("leftover stock_addon identifiers in live code: %d" % len(leftovers))
for l in leftovers[:15]:
    print("   ", l)
if leftovers:
    fail.append("%d leftover stock_addon identifiers" % len(leftovers))

# 10. brace/paren balance per JS file (crude, but catches a botched sed)
for name in ("hrms_addon/public/js/hrms_addon_theme.js",
             "hrms_addon/public/js/form_sidebar_toggle.js",
             "hrms_addon/hrms_addon/doctype/hrms_addon_theme_settings/hrms_addon_theme_settings.js"):
    text = read(name)
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', '', text, flags=re.S)
    for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
        if stripped.count(op) != stripped.count(cl):
            fail.append("%s: unbalanced %s%s (%d vs %d)" % (name, op, cl, stripped.count(op), stripped.count(cl)))
print("JS bracket balance checked on 3 files")

# 11. hooks.py asset paths point at files that exist
hooks_live = "\n".join(l for l in read("hrms_addon/hooks.py").splitlines() if not l.lstrip().startswith("#"))
for m in re.finditer(r'"/assets/hrms_addon/(js|css)/([\w.]+)"', hooks_live):
    rel = "hrms_addon/public/%s/%s" % (m.group(1), m.group(2))
    if not os.path.exists(BASE + "/" + rel):
        fail.append("hooks.py app_include points at missing %s" % rel)
bundle = re.search(r'app_include_css\s*=\s*"([\w.]+)"', hooks_live).group(1)
if not os.path.exists(BASE + "/hrms_addon/public/css/" + bundle):
    fail.append("app_include_css bundle %s not found" % bundle)
print("hooks.py asset paths resolve")


print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
