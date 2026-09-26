"""Checks for the sign-in page, run without a bench.

login_rules.py imports nothing from Frappe, so it is loaded directly: the
theme's colours reach the page only as plain hex, the panel's picture only as
a public file of the site's or an https address, percent-encoded so nothing
in it can end the url('') it sits in, and the tagline falls back to the
standard line.

It also checks the page: login.html extends Frappe's own and keeps its card
whole, overrides no style or script block (Frappe would drop login.css, or
login.js), puts the colours and picture on :root and escapes the words it
prints; login.css hides Frappe's footer over login.js's inline style, draws
the picture from --hal-image, defines every variable it uses and styles only
classes Frappe's page still has; login.py builds Frappe's context first and
never fails the page; the Branding fields; and against Frappe (../ERPNext, or
FRAPPE_APPS_ROOT) what the design relies on.

    python scripts/verify_login_page.py
"""
import ast
import colorsys
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def assigned(source, name):
    """A literal assigned at the top of a module, read without importing it."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def block(source, name):
    """A Jinja block's body."""
    start = source.index("{%% block %s %%}" % name) + len("{%% block %s %%}" % name)
    return source[start:source.index("{% endblock %}", start)]


def function(source, name):
    """A function's or method's text, up to the first line not inside it."""
    start = source.index("def %s(" % name)
    depth = start - (source.rfind("\n", 0, start) + 1)
    lines = source[start:].split("\n")
    kept = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= depth:
            break
        kept.append(line)
    return "\n".join(kept)


R = load("login_rules")
print("loaded login_rules.py without Frappe")

theme_py = read("hrms_addon", "hrms_addon", "theme.py")
FIELD_TO_VAR = assigned(theme_py, "FIELD_TO_VAR")
DEFAULTS = assigned(theme_py, "DEFAULTS")
html = read("hrms_addon", "www", "login.html")
css = read("hrms_addon", "www", "login.css")
page_py = read("hrms_addon", "www", "login.py")
branding_dt = json.loads(read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_branding", "hrms_addon_branding.json"))
branding_ctrl = read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_branding", "hrms_addon_branding.py")
css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

# ── 1. The theme's colours ────────────────────────────────────────────
for field, variable in R.COLOURS:
    if field not in FIELD_TO_VAR or field not in DEFAULTS:
        fail.append("%s is not a colour of HRMS Addon Theme Settings: the page could not follow the desk" % field)
    if not variable.startswith("--hal-"):
        fail.append("%s is not one of the page's --hal- variables" % variable)
defaults_block = re.search(r"^html \{(.*?)\}", css_code, re.M | re.S)
page_defaults = dict(re.findall(r"(--hal-[\w-]+):\s*([^;]+);", defaults_block.group(1))) if defaults_block else {}
if not page_defaults:
    fail.append("login.css has no html { } block of --hal- defaults")
for field, variable in R.COLOURS:
    if page_defaults.get(variable, "").lower() != DEFAULTS.get(field, "").lower():
        fail.append("login.css's %s is %r, the shipped theme's %s is %r: with Theme Settings off the page and the "
                    "desk would differ" % (variable, page_defaults.get(variable), field, DEFAULTS.get(field)))

for value, expected in {"#abc": "#abc", "#ABCD": "#ABCD", "#14395E": "#14395E", "#14395e80": "#14395e80",
                        "  #0A6ED1 \n": "#0A6ED1"}.items():
    if R.safe_colour(value, "#000000") != expected:
        fail.append("safe_colour(%r) should be %r, is %r" % (value, expected, R.safe_colour(value, "#000000")))
for value in (None, "", "red", "#12345", "#1234567", "#ggg", "14395E", "#14395E;}body{display:none}", "#14395E\n}",
              "#14395E !important", "rgb(1, 2, 3)", "var(--x)", "#14395E}", "url(x)", "#14395E\n#fff"):
    if R.safe_colour(value, "#000000") != "#000000":
        fail.append("safe_colour takes %r: only a plain hex colour may reach the stylesheet" % (value,))

# ── 2. The panel's picture ────────────────────────────────────────────
DANGER = set("'\"()\\;<>{}` \t\r\n\f\v")
for value, expected in {
    "/files/plant.jpg": "/files/plant.jpg",
    "  /files/plant.jpg  ": "/files/plant.jpg",
    "/files/Luuka plant.jpg": "/files/Luuka%20plant.jpg",
    "/files/a%20b.jpg": "/files/a%20b.jpg",
    "/files/100%.jpg": "/files/100%25.jpg",
    "/files/it's.jpg": "/files/it%27s.jpg",
    "/files/plant (1).jpg": "/files/plant%20%281%29.jpg",
    "/files/Kampala-été.jpg": "/files/Kampala-%C3%A9t%C3%A9.jpg",
    "https://cdn.example.com/p/plant.jpg?w=1600&q=80": "https://cdn.example.com/p/plant.jpg?w=1600&q=80",
}.items():
    if R.safe_image(value) != expected:
        fail.append("safe_image(%r) should be %r, is %r" % (value, expected, R.safe_image(value)))
for value in (None, "", "   ", "/private/files/plant.jpg", " /private/files/a b.jpg", "http://example.com/plant.jpg",
              "javascript:alert(1)", "data:image/png;base64,AAAA", "//example.com/plant.jpg", "files/plant.jpg",
              "/files/", "https://", "/assets/hrms_addon/images/plant.jpg", "HTTPS://example.com/a.jpg"):
    if R.safe_image(value) != "":
        fail.append("safe_image takes %r: the picture is a public file of the site's or an https address" % (value,))
# nothing typed into the address can end the url('') or the style element around it
for code in list(range(128)) + [0xa0, 0xe9, 0x2028, 0x2029, 0xfeff]:
    for value in ("/files/a%sb.jpg" % chr(code), "https://example.com/a%sb.jpg" % chr(code)):
        out = R.safe_image(value)
        if not out or DANGER & set(out) or any(not 33 <= ord(ch) <= 126 for ch in out):
            fail.append("safe_image(%r) gives %r: every character that could end url('') must be encoded"
                        % (value, out))
for value in ("/files/x');}body{display:none}/*", "/files/x</style><script>alert(1)</script>",
              "/files/x\\');background:url(//example.com/x)", "/files/x\n}", "/files/x&#39;);"):
    out = R.safe_image(value)
    if DANGER & set(out) or "</" in out:
        fail.append("safe_image(%r) gives %r" % (value, out))

# ── 3. What the page gets ─────────────────────────────────────────────
plain = R.look({}, DEFAULTS)
if plain["colours"] != [(variable, DEFAULTS[field]) for field, variable in R.COLOURS]:
    fail.append("with Theme Settings off the page takes the shipped theme's colours")
if plain["tagline"] != R.DEFAULT_TAGLINE or plain["image"] != "":
    fail.append("with no branding set the page shows the standard line and no picture")
mine = R.look({"primary_navy": "#000000", "accent_colour": "red;}"}, DEFAULTS, "  Our people, one place.  ",
              "/files/a b.jpg")
colours = dict(mine["colours"])
if colours.get("--hal-primary") != "#000000":
    fail.append("the theme's own navy does not reach the page")
if colours.get("--hal-accent") != DEFAULTS["accent_colour"]:
    fail.append("a colour that is not plain hex must fall back to the shipped theme's")
if mine["tagline"] != "Our people, one place." or mine["image"] != "/files/a%20b.jpg":
    fail.append("the branding's tagline and picture reach the page, trimmed and encoded")
if R.look(None, None)["colours"] != [(variable, "#14395E") for _field, variable in R.COLOURS] \
        or R.look({}, DEFAULTS, "   ")["tagline"] != R.DEFAULT_TAGLINE \
        or R.look({}, DEFAULTS, None, "/private/files/a.jpg")["image"] != "":
    fail.append("look() must stand with nothing usable given: the page never fails to draw")

# ── 4. login.html ─────────────────────────────────────────────────────
first = next(line for line in html.splitlines() if line.strip())
if first.strip() != '{% extends "frappe/www/login.html" %}':
    fail.append("login.html must extend Frappe's own sign-in page, not copy it")
blocks = re.findall(r"\{%-?\s*block\s+(\w+)", html)
if sorted(blocks) != ["head_include", "page_content"]:
    fail.append("login.html overrides %s: only head_include and page_content (Frappe drops login.css when the text "
                "names a style block, comments included, and a script block would drop login.js)" % blocks)
page = block(html, "page_content")
head = block(html, "head_include")
if page.count("{{ super() }}") != 1 or not re.search(r'class="hal-card">\s*\{\{ super\(\) \}\}\s*</div>', page):
    fail.append("Frappe's card goes in whole, once, inside .hal-card: login.js drives it by its own classes and ids")
if "{{ super() }}" not in head:
    fail.append("head_include must keep Frappe's login.bundle.css")
if not re.search(r"\{%-? for variable, colour in hal\.colours %\}\s*\{\{ variable \}\}: \{\{ colour \}\};", head):
    fail.append("the theme's colours go on :root as login_rules gives them")
if not re.search(r"\{%- if hal\.image %\}\s*--hal-image: url\('\{\{ hal\.image \}\}'\);\s*\{%- endif %\}", head):
    fail.append("the picture goes on :root as --hal-image, only when there is one")
if re.search(r"\sstyle\s*=", html):
    fail.append("login.html puts a style attribute on the page: the colours and picture go on :root")
if "{{ ' hal-has-image' if hal.image else '' }}" not in page:
    fail.append("the page is marked hal-has-image only when there is a picture")
RAW_OK = {"{{ super() }}", "{{ variable }}", "{{ colour }}", "{{ hal.image }}", "{{ logo }}", "{{ footer_powered }}",
          "{{ ' hal-has-image' if hal.image else '' }}"}
for expression in re.findall(r"\{\{.*?\}\}", html):
    if expression not in RAW_OK and not re.search(r"\|\s*e\s*\}\}$", expression):
        fail.append("login.html prints %s unescaped" % expression)
if not re.search(r'\{% if show_footer_on_login %\}\s*<div class="hal-powered">', page):
    fail.append("the Powered by line shows only when Website Settings shows the footer on the sign-in page")
page_classes = set(re.findall(r"hal-[\w-]+", " ".join(re.findall(r'class="([^"]*)"', page))))
css_classes = set(re.findall(r"\.(hal-[\w-]+)", css_code))
if page_classes - css_classes:
    fail.append("login.html draws %s, which login.css never styles" % sorted(page_classes - css_classes))
if css_classes - page_classes:
    fail.append("login.css styles %s, which login.html never draws" % sorted(css_classes - page_classes))

# ── 5. login.css ──────────────────────────────────────────────────────
if not re.search(r"\.web-footer\s*\{\s*display:\s*none\s*!important;\s*\}", css_code):
    fail.append("login.js shows Frappe's footer with an inline style; only !important hides it")
if not re.search(r"\.hal-has-image \.hal-brand\s*\{\s*background-image:\s*var\(--hal-image\);", css_code):
    fail.append("the picture is drawn from --hal-image on .hal-has-image .hal-brand")
used = set(re.findall(r"var\((--hal-[\w-]+)", css_code))
defined = set(page_defaults) | {"--hal-image"}
if used - defined:
    fail.append("login.css uses %s, defined nowhere" % sorted(used - defined))
if css_code.count("{") != css_code.count("}"):
    fail.append("login.css's braces do not balance")
if "</" in css:
    fail.append("login.css goes inside a style element on the page: it cannot hold </")
for hexcode in sorted(set(re.findall(r"#[0-9a-fA-F]{6}\b", css_code))):
    red, green, blue = (int(hexcode[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if 0.44 <= hue <= 0.53 and saturation > 0.3 and 0.15 < lightness < 0.85:
        fail.append("%s is teal: CyveTech's colours are navy and gold" % hexcode)
frappe_classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", css_code)) - css_classes

# ── 6. login.py ───────────────────────────────────────────────────────
if "from frappe.www.login import get_context as frappe_login_context" not in page_py:
    fail.append("login.py builds the context with Frappe's own get_context")
get_context = function(page_py, "get_context")
if not 0 <= get_context.find("frappe_login_context(context)") < get_context.find("context.hal = look()"):
    fail.append("Frappe's context first (it sends a signed-in user on), then the look")
if not re.search(r"^no_cache = True$", page_py, re.M):
    fail.append("the sign-in page must never be cached, as Frappe's own is not")
look_fn = function(page_py, "look")
if "except Exception:" not in look_fn or "return login_rules.look({}, theme.DEFAULTS)" not in look_fn:
    fail.append("look() falls back to the shipped look on any trouble: the sign-in page never fails")
for fieldname in ("login_tagline", "login_image"):
    if 'settings.get("%s")' % fieldname not in look_fn:
        fail.append("login.py does not read %s from HRMS Addon Branding" % fieldname)
if "theme.get_palette()" not in look_fn or "theme.FIELD_TO_VAR" not in look_fn:
    fail.append("the colours come from Theme Settings as the desk takes them (theme.get_palette)")

# ── 7. HRMS Addon Branding ────────────────────────────────────────────
fields = {f["fieldname"]: f for f in branding_dt["fields"]}
order = branding_dt["field_order"]
tagline, picture = fields.get("login_tagline"), fields.get("login_image")
if not tagline or tagline.get("fieldtype") != "Small Text":
    fail.append("HRMS Addon Branding has no Tagline (login_tagline, Small Text)")
if not picture or picture.get("fieldtype") != "Attach Image" or picture.get("make_attachment_public") != 1:
    fail.append("the Panel Picture is an Attach Image that uploads public files (a guest cannot load a private one)")
if sorted(order) != sorted(fields):
    fail.append("field_order and fields differ on HRMS Addon Branding")
if "login_tagline" in order:
    sections = [f for f in order[:order.index("login_tagline")] if fields[f]["fieldtype"] == "Section Break"]
    if not sections or sections[-1] != "section_login" or fields["section_login"].get("label") != "Sign-In Page":
        fail.append("the sign-in settings sit in their own Sign-In Page section")
if "login_rules.safe_image(self.login_image)" not in function(branding_ctrl, "validate"):
    fail.append("saving a picture the sign-in page cannot show (a private file) must say so")
if "custom_section" in json.dumps(branding_dt):
    fail.append("no field may be named custom_section")

# ── 8. What Frappe must still do ──────────────────────────────────────
if UPSTREAM_OK:
    renderer = upstream("frappe", "website", "page_renderers", "template_page.py")
    if "for app in reversed(frappe.get_installed_apps()):" not in function(renderer, "set_template_path"):
        fail.append("Frappe no longer looks in the last installed app's www first: recheck that login.html is served")
    if 'if os.path.exists(css_path) and "{% block style %}" not in self.source:' not in renderer \
            or 'css_path = self.basename + ".css"' not in renderer:
        fail.append("Frappe changed how it puts a page's own .css on it: recheck login.css")
    if 'self.pymodule_name = self.app + "."' not in renderer:
        fail.append("Frappe no longer takes the controller from the page's own app: recheck login.py")
    jinja = upstream("frappe", "utils", "jinja.py")
    if "apps = list(reversed(frappe.get_installed_apps(" not in jinja \
            or 'PrefixLoader({app: PackageLoader(app, ".") for app in apps})' not in jinja:
        fail.append("Frappe's template loader changed: recheck {% extends \"frappe/www/login.html\" %}")
    if "autoescape" in jinja:
        fail.append("Frappe's templates may now escape on their own: recheck | e, footer_powered and --hal-image")
    base = upstream("frappe", "templates", "base.html")
    head_at, style_at = base.find("block head_include"), base.find("block style")
    if not 0 <= head_at < style_at or "colocated_css" not in base[style_at:style_at + 200]:
        fail.append("base.html no longer puts the page's own .css after head_include: login.css may lose to "
                    "login.bundle.css")
    frappe_page = upstream("frappe", "www", "login.html")
    if not frappe_page.startswith('{% extends "templates/web.html" %}') \
            or "{{ include_style('login.bundle.css') }}" not in block(frappe_page, "head_include") \
            or "{% block page_content %}" not in frappe_page or "{% block script %}" not in frappe_page:
        fail.append("Frappe's login.html changed its blocks: recheck login.html")
    if re.search(r"\{%-?\s*block\s+style\b", frappe_page):
        fail.append("Frappe's login.html now has a style block: base.html's, which carries login.css, would not show")
    frappe_login = upstream("frappe", "www", "login.py")
    frappe_get_context = function(frappe_login, "get_context")
    for key in ('context["show_footer_on_login"]', 'context["logo"]', 'context["app_name"]', "return context"):
        if key not in frappe_get_context:
            fail.append("Frappe's login get_context no longer has %s: recheck login.html and login.py" % key)
    if not 0 <= frappe_get_context.find("raise frappe.Redirect") < frappe_get_context.find("context.no_header"):
        fail.append("Frappe's login get_context no longer sends a signed-in user on first")
    for prop in re.findall(r"^(\w+) = ", frappe_login, re.M):
        if prop in assigned(renderer, "WEBPAGE_PY_MODULE_PROPERTIES") and not re.search(r"^%s = " % prop, page_py, re.M):
            fail.append("Frappe's login.py sets %s; login.py replaces it as the page's controller, so must too" % prop)
    settings_py = upstream("frappe", "website", "doctype", "website_settings", "website_settings.py")
    if '"copyright",' not in settings_py or '"footer_powered",' not in settings_py:
        fail.append("Website Settings no longer puts copyright and footer_powered on the page")
    if not os.path.exists(os.path.join(APPS_ROOT, "frappe", "frappe", "templates", "includes", "footer",
                                       "footer_powered.html")):
        fail.append("Frappe has no footer_powered.html: login.html includes it when Powered By is empty")
    login_js = upstream("frappe", "templates", "includes", "login", "login.js")
    if not re.search(r'if \(window\.show_footer_on_login\) \{\s*\$\("body \.web-footer"\)\.show\(\);', login_js):
        fail.append("login.js no longer shows the footer itself: recheck the .web-footer rule and hal-powered")
    if "options.make_attachments_public = this.df.make_attachment_public" not in \
            upstream("frappe", "public", "js", "frappe", "form", "controls", "attach.js") \
            or "private: !props.make_attachments_public" not in \
            upstream("frappe", "public", "js", "frappe", "file_uploader", "FileUploader.vue"):
        fail.append("Frappe changed how an Attach field makes a file public: recheck the Panel Picture")
    frappe_markup = frappe_page + upstream("frappe", "templates", "web.html") + login_js \
        + upstream("frappe", "templates", "includes", "footer", "footer.html")
    for name in sorted(frappe_classes):
        if not re.search(r"""[\s"'.]%s[\s"'.]""" % re.escape(name), frappe_markup):
            fail.append("login.css styles .%s, which Frappe's sign-in page no longer has" % name)
    upstream_note = "checked against Frappe (%d of Frappe's classes styled)" % len(frappe_classes)
else:
    upstream_note = "Frappe not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL SIGN-IN PAGE CHECKS PASSED")
