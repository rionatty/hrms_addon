"""Checks the module pages (each module's workspace under a header of its
own, in the desk home's look), without a bench.

    python scripts/verify_module_pages.py

  1  the rules: the switch, the document each module offers to make, the
     doctypes a module opens, the user's alerts among them
  2  the glue: one call, for the logged-in user and nobody else, the
     module's doctypes read from its menu and its page, the alerts read as
     My Alerts reads them, a part that cannot be read left out and logged
  3  the switch and the boot: on unless Theme Settings say Standard, the
     cockpit standing aside while it is on, the document offered sent with
     the boot
  4  the page: loaded with the desk, never able to stop a module opening,
     the header added first in the workspace's body and nothing of Frappe's
     moved, removed or rewritten, every rule on Frappe's page under the
     switch and its blocks restyled only while the workspace is not edited,
     what the server says escaped as it is written
  5  what Frappe does that this leans on, read from Frappe itself

The rules are loaded without Frappe.
"""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
APP = os.path.join(PACKAGE, "hrms_addon")
FRAPPE_JS = os.path.join(APPS_ROOT, "frappe", "frappe", "public", "js", "frappe")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(*parts):
    path = os.path.join(APPS_ROOT, *parts)
    return io.open(path, encoding="utf-8").read() if os.path.exists(path) else None


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    hits = glob.glob(os.path.join(APP, "doctype", folder, folder + ".json"))
    return json.load(open(hits[0], encoding="utf-8")) if hits else None


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("module_pages_rules")
HOME = load("home_rules")
print("loaded module_pages_rules.py and home_rules.py without Frappe")

# ── 1. The rules ────────────────────────────────────────────────────────
check(R.page_of(None) == R.EXECUTIVE and R.page_of("") == R.EXECUTIVE and R.page_of("Executive") == R.EXECUTIVE
      and R.page_of(" Standard ") == R.STANDARD and R.page_of("anything else") == R.EXECUTIVE,
      "the modules open in the home's look unless Theme Settings say Standard, a setting nobody touched included")
check(R.PAGES == (R.EXECUTIVE, R.STANDARD), "the two settings, the shipped one first")
check(set(R.ACTIONS) <= set(HOME.MODULES) and "Tax & Benefits" not in R.ACTIONS and len(R.ACTIONS) == 9,
      "a document is offered on the modules down the desk only, every one but Tax & Benefits: %s"
      % sorted(set(R.ACTIONS) - set(HOME.MODULES)))
missing = [doctype for doctype in R.ACTIONS.values() if not upstream_doctype(doctype)]
check(not missing, "each document offered is a doctype this bench has: %s" % missing)
singles = [doctype for doctype in R.ACTIONS.values() if (upstream_doctype(doctype) or {}).get("issingle")]
check(not singles, "and none is a Single, which has no new one to make: %s" % singles)
check(R.doctypes(["Job Opening", "", None, " Job Opening ", "Job Applicant", "Job Opening"]) == ["Job Opening", "Job Applicant"]
      and R.doctypes(None) == [] and R.doctypes(x for x in ("A", "B", "A")) == ["A", "B"],
      "each doctype once, in the order first named, blanks left out, from any iterable")
ALERTS = [{"key": "1", "doctype": "Job Opening"}, {"key": "2", "doctype": "Leave Application"},
          {"key": "3", "doctype": None}, {"key": "4", "doctype": "Job Applicant"}]
check([alert["key"] for alert in R.mine_in(ALERTS, ["Job Applicant", "Job Opening"])] == ["1", "4"]
      and R.mine_in(ALERTS, []) == [] and R.mine_in(None, ["Job Opening"]) == [],
      "the user's alerts about the module's documents, in the order given; none about nothing")
check(R.SHOWN == 5 and HOME.SHOWN >= R.SHOWN, "five rows of what waits: the rest are one click away")
print("rules: the switch, the documents offered, the module's doctypes, the user's alerts among them")

# ── 2. The glue ─────────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "module_pages.py")
tree = ast.parse(glue)
functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
check(len(re.findall(r"@frappe\.whitelist", glue)) == 1 and re.search(r"@frappe\.whitelist\(\)\ndef summary\(workspace: str\):", glue),
      "summary is the one whitelisted call, and takes the workspace as text, which v16 checks")
check(not any(arg.arg in ("user", "for_user", "allocated_to", "owner") for node in functions.values() for arg in node.args.args),
      "nothing takes a user to look at: what waits is the logged-in user's own")
body = glue.split("def summary(")[1].split("\ndef ")[0]
check("names = _or([], _doctypes, workspace)" in body
      and "mine = rules.mine_in(_or([], _alerts, names) if names else [], names)" in body
      and '"waiting": home_rules.waiting(mine, rules.SHOWN)' in body
      and '"doctypes": rules.doctypes(alert.get("doctype") for alert in mine)' in body,
      "the module's doctypes, the user's alerts among them, counted as the desk home counts them; and nothing read "
      "at all for a module that opens no documents")
own = glue.split("def _doctypes(")[1].split("\ndef ")[0]
check('frappe.db.exists("DocType", "Workspace Sidebar") and frappe.db.exists("Workspace Sidebar", workspace)' in own
      and 'if row.link_type == "DocType"]' in own
      and 'row.type == "Link" and row.link_type == "DocType"' in own and 'page.shortcuts if row.type == "DocType"' in own
      and own.index('"Workspace Sidebar"') < own.index('frappe.db.exists("Workspace", workspace)')
      and "return rules.doctypes(names)" in own,
      "the doctypes the module opens: its menu first, then its page's cards and shortcuts, each once; on a Frappe "
      "without menus of their own, its page alone")
for doctype, fields in (("Workspace Sidebar", ("items",)), ("Workspace Sidebar Item", ("type", "link_type", "link_to")),
                        ("Workspace", ("links", "shortcuts")), ("Workspace Link", ("type", "link_type", "link_to")),
                        ("Workspace Shortcut", ("type", "link_to"))):
    spec_json = upstream_doctype(doctype)
    have = {f["fieldname"] for f in (spec_json or {}).get("fields", [])}
    check(spec_json and set(fields) <= have, "%s has %s upstream: %s" % (doctype, ", ".join(fields), sorted(set(fields) - have)))
read_alerts = glue.split("def _alerts(")[1].split("\ndef ")[0]
check("alerts_rules.order(alerts._assignments(day, names) + alerts._notifications(day, names), day)" in read_alerts,
      "the user's alerts read as My Alerts reads them, kept to the module's doctypes, ordered by the rail's own rule")
guard = glue.split("def _or(")[1].split("\ndef ")[0]
check("except Exception:" in guard and "defer_insert=True" in guard and "return fallback" in guard
      and '"Module page: %s"' in guard,
      "a part that cannot be read is left out and logged past the GET's rollback, and the rest still comes")
check("ignore_permissions" not in glue and "frappe.db.sql" not in glue and "frappe.session.user" not in glue,
      "nothing here reads past the user or names one: the alerts' own queries are filtered on the logged-in user")
alerts_glue = read("hrms_addon", "hrms_addon", "alerts.py")
check("def _assignments(day, doctypes=None):" in alerts_glue and "def _notifications(day, doctypes=None):" in alerts_glue
      and '_about({"allocated_to": frappe.session.user, "status": "Open"}, "reference_type", doctypes)' in alerts_glue
      and '_about({"for_user": frappe.session.user, "read": 0}, "document_type", doctypes)' in alerts_glue,
      "the alerts' queries take the module's doctypes beside the user's own filter")
print("glue: one call, the module's doctypes from its menu and page, the user's own alerts among them")

# ── 3. The switch and the boot ──────────────────────────────────────────
theme = read("hrms_addon", "hrms_addon", "theme.py")
enabled = theme.split("def module_pages_enabled(")[1].split("\ndef ")[0]
check("module_pages_rules.page_of(value) == module_pages_rules.EXECUTIVE" in enabled and enabled.count("return 1") >= 2
      and '.get("module_pages")' in enabled,
      "on unless Theme Settings say Standard, and where they cannot be read")
cockpit = theme.split("def workspace_cockpit_enabled(")[1].split("\ndef ")[0]
check("return 1 if (on and not module_pages_enabled()) else 0" in cockpit,
      "the navy cockpit stands aside while the module pages are on: both repaint the workspace")
check("bootinfo.hrms_addon_module_pages = module_pages_enabled()" in theme
      and "bootinfo.hrms_addon_module_actions = dict(module_pages_rules.ACTIONS)" in theme
      and "bootinfo.hrms_addon_home_modules = list(home_rules.MODULES)" in theme,
      "the switch, the documents offered and the order of the modules come with the boot, so a module's header is "
      "drawn without asking")
settings = {row["fieldname"]: row for row in json.loads(read(
    "hrms_addon", "hrms_addon", "doctype", "hrms_addon_theme_settings", "hrms_addon_theme_settings.json"))["fields"]}
switch = settings.get("module_pages", {})
check((switch.get("fieldtype"), switch.get("default")) == ("Select", R.EXECUTIVE)
      and tuple(switch.get("options", "").split("\n")) == R.PAGES,
      "Theme Settings has the switch, a Select whose options are the rules' own and whose default is the pages' look")
check(settings.get("workspace_cockpit", {}).get("depends_on") == 'eval:doc.enabled && doc.module_pages == "Standard"',
      "the cockpit is offered only where it can show, with Module Pages set to Standard")
form = read("hrms_addon", "hrms_addon", "doctype", "hrms_addon_theme_settings", "hrms_addon_theme_settings.js")
check('return !!(doc.enabled && doc.workspace_cockpit && doc.module_pages === "Standard");' in form
      and form.count("ha_cockpit_on(frm.doc)") == 2 and "module_pages(frm) {" in form,
      "the form's preview and its copy of the boot keep the cockpit to Standard too")
print("switch: on by default, the cockpit standing aside, the boot carrying what the header needs")

# ── 4. The page ─────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
listed = re.findall(r'"/assets/hrms_addon/js/([\w.-]+\.js)"', hooks.split("app_include_js = [")[1].split("]")[0])
check("hrms_addon_module_pages.js" in listed and listed.index("hrms_addon_module_pages.js") > listed.index("hrms_addon_theme.js"),
      "the script is loaded with the desk, after the theme's, whose round pictures it shows")
script = read("hrms_addon", "public", "js", "hrms_addon_module_pages.js")
check("if (!frappe.boot.hrms_addon_module_pages) return;" in script
      and 'if (frappe.session && frappe.session.user === "Guest") return;' in script,
      "Standard, or a guest: the script does nothing at all")
check('const METHOD = "hrms_addon.hrms_addon.module_pages.summary";' in script
      and script.count('fetch("/api/method/" + METHOD + "?workspace=" + encodeURIComponent(name)') == 1
      and "if (asking[name] || (answer && Date.now() - answer.at < FRESH_MS)) return;" in script,
      "it asks module_pages.summary for the module shown, once at a time, and not again for a minute")
check(not re.search(r"frappe\s*\.\s*x?call\(", script) and "response.ok ? response.json() : null" in script
      and ".catch(() => null)" in script,
      "and never through frappe.call, whose failure opens Frappe's Server Error dialog over the module")
check(script.count("try {") >= 6 and script.count("console.error(error);") >= 3,
      "nothing it does can stop a module opening: every entry is caught")
mount = script.split("function mount(")[1].split("\n\t}\n")[0]
check('const body = element.querySelector(".layout-main-section");' in mount
      and "body.insertBefore(holder, body.firstChild);" in mount and 'holder.className = "ha-mod";' in mount,
      "the header is added first in the workspace's body")
check(".remove()" not in script and "removeChild" not in script and "appendChild" not in script.replace(
    "document.head.appendChild(sheet);", "") and script.count("insertBefore") == 1
      and script.count(".innerHTML =") == 1 and "holder.innerHTML = hero(page) + panel(page);" in script
      and "setAttribute" not in script.replace('holder.setAttribute("data-mark", mark);', ""),
      "nothing of Frappe's is moved, removed, rewritten or marked: the header is the only thing written, and only "
      "into itself")
check("classList.add(ON)" in script and script.count("classList.add(") == 1 and "classList.toggle" not in script
      and 'const ON = "ha-mod-on";' in script,
      "the one class it sets is its own, on <html>, under which every style below holds")
written = set(re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", script.split("const CSS = `")[0]))
served = sorted(expr for expr in written if re.search(r"\b(item|waits|page|answer|module|doctype|label|stage)\b", expr)
                or expr in ("name", "title", "address"))
bare = [expr for expr in served if not (expr.startswith(("esc(", "count(", "icon(", "row(", "track(", "near(", "picture("))
                                        or ".map(esc)" in expr or "=> row(" in expr or expr in ("label", "list", "key", "index")
                                        or re.fullmatch(r'[\w. &|]+ \? icon\("\w+"\) : ""', expr))]
check("return frappe.utils.escape_html(text == null ? \"\" : String(text));" in script.split("function esc(")[1].split("}")[0]
      and len(served) >= 12 and not bare,
      "every value from the server or the boot is escaped as it is written, a number as a number (%d looked at): %s"
      % (len(served), bare[:4]))
check("const label = esc(__(module));" in script and 'data-list="${list}"' in script and 'data-tab="${key}"' in script,
      "and what is written bare is the script's own: an escaped label, a list or tab of its own naming")
check("frappe.model.can_create(doctype)" in script.split("function action_of(")[1].split("\n\t}\n")[0]
      and "if (doctype) frappe.new_doc(doctype);" in script,
      "a document is offered only to somebody who may make it")
check("if (!name || !may_open(name)) return;" in script.split("function open_module(")[1].split("\n\t}\n")[0]
      and "frappe.route_options = { sidebar: name };" in script and "frappe.set_route(frappe.router.slug(name));" in script,
      "another module is opened only where the user may, as Frappe opens a workspace, with its own menu")
everything = script.split("function all(")[1].split("\n\t}\n")[0]
check("{ allocated_to: user, status: \"Open\" }" in everything and "{ for_user: user, read: 0 }" in everything
      and 'reference_type: ["in", doctypes]' in everything and 'document_type: ["in", doctypes]' in everything,
      "See all opens the user's own To Do or notifications, kept to the module's documents")
check("frappe.utils.get_desktop_icon(page.name, \"solid\")" in script and "frappe.utils.icon(page.icon, \"lg\")" in script,
      "the module's picture is the one its tile shows, the app's own round one where it ships one")
check('return (frappe.get_route() || [])[0] === "Workspaces";' in script and '$(document).on("page-change", arrive);' in script
      and "if (tries < 10 && (!there || tries < 4)) setTimeout(look, 120 * tries);" in script,
      "it looks for the workspace only on a workspace's route, a few times after each change of page")
arriving = script.split("function arrive(")[1].split("\n\t}\n")[0]
check("setTimeout(look, 0);" in arriving and "\t\tlook();" not in arriving,
      "the first look waits for Frappe to name the workspace it shows, which it does straight after page-change: "
      "looked at in the page-change handler, a switch showed the last module's header for a moment")
check("frm." not in script and "bench build" in script and "sheet.textContent = CSS;" in script,
      "its styles are written into the page, so a change needs no build")

PAGE = 'html.ha-mod-on .page-container[data-page-route="Workspaces"]'
READ = PAGE + " .layout-main-section:not(.edit-mode)"
check("const PAGE = '%s';" % PAGE in script and 'const READ = PAGE + " .layout-main-section:not(.edit-mode)";' in script,
      "the page it styles is Frappe's workspace page, its blocks only while the workspace is not edited")
css = script.split("const CSS = `")[1].split("`;")[0].replace("${PAGE}", PAGE).replace("${READ}", READ)
css = re.sub(r"\$\{glyph\(\"\w+\"\)\}", "GLYPH", css)
check("${" not in css, "the styles name nothing else of the script's")


def selectors(line):
    return [part.strip() for part in line.split("{")[0].split(",")]


rules = []
lines = css.splitlines()
for index, line in enumerate(lines):
    text = line.strip()
    if not text or text.startswith(("/*", "@", "from ", "to ")) or text.endswith("*/"):
        continue
    if "{" in text or (text.endswith(",") and not line.startswith(("\t", " "))):
        rules.extend(part for part in selectors(text) if part)
FRAPPES = (".widget", ".ce-", ".page-head", ".page-container", ".layout-main", ".link-item", ".quick-list", ".see-all",
           ".number", ".indicator-pill", ".chart-", ".list-")
on_frappe = [part for part in rules if any(name in part for name in FRAPPES)]
outside = [part for part in on_frappe if not (part.startswith(PAGE) or part.startswith(
    'html.ha-mod-on:not([data-theme="dark"]) .page-container[data-page-route="Workspaces"]')
    or part.startswith('html.ha-mod-on[data-theme="dark"] .page-container[data-page-route="Workspaces"]'))]
check(len(on_frappe) >= 40 and not outside,
      "every rule on something of Frappe's holds on the workspace page alone, under the switch (%d looked at): %s"
      % (len(on_frappe), outside[:2]))
blocks = [part for part in on_frappe if any(name in part for name in (".widget", ".ce-block", ".link-item"))]
unread = [part for part in blocks if not part.startswith(READ)]
check(blocks and not unread,
      "and every rule on its blocks only while the workspace is not being edited, which is then exactly as it was "
      "(%d looked at): %s" % (len(blocks), unread[:2]))
check(PAGE + " .layout-main-section.edit-mode > .ha-mod { display: none; }" in css
      and PAGE + " .layout-main-section > .ha-mod { order: -1;" in css
      and PAGE + " .layout-main-section:not(.edit-mode) { display: flex; flex-direction: column; }" in css,
      "the header stays above Frappe's loading skeleton, and is gone while the workspace is edited")
KINDS = r"(?:links|shortcut|number|dashboard|quick-list)-widget-box|spacer"
bare_widget = [part for part in blocks if re.search(r"\.widget(?![\w-])(?!\.(?:%s))" % KINDS, part)]
check(not bare_widget, "never a bare .widget: each heading and spacer of the page is one too, so Frappe's card kinds are "
      "named: %s" % bare_widget[:2])
cut = [selector.strip()[:70] for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
       if READ in selector and "overflow" in body]
check(not cut and "overflow: hidden;" in css.split(".ha-mod-hero {")[1].split("}")[0],
      "no card of Frappe's is cut to its edges, where a chart's or a figure's menu opens past them; the header's own "
      "rings are: %s" % cut[:2])
check("inset 0 3px 0 var(--ha-m-navy)" in css.split(READ + " .widget.number-widget-box {")[1].split("}")[0],
      "a figure's band is drawn inside its card, not by cutting the card")
check(READ + " .widget.spacer { background: transparent !important; }" in css,
      "Frappe's spacer, a pixel tall in the card's colour, is no stray line across the canvas")
own_rules = [part for part in rules if part not in on_frappe]
loose = [part for part in own_rules if not (part.startswith(".ha-mod") or part.startswith(PAGE) or ".ha-mod" in part)]
check(not loose, "every other rule is the header's own: %s" % loose[:3])
palette = set(re.findall(r"var\((--hra-[\w-]+)", css))
bundle = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
check(palette and all(re.search(re.escape(name) + r"\s*:", bundle) for name in palette),
      "the theme's colours it reads are the palette's own: %s" % sorted(n for n in palette if n + ":" not in bundle.replace(" ", "")))
check("#14395E" in css and "#EAA51A" in css and "teal" not in css.lower() and "#0d9488" not in css.lower(),
      "CyveTech navy and the home's gold, never teal")
print("page: added first in the workspace, nothing of Frappe's touched, its blocks restyled only while not edited")

# ── 5. What Frappe does that this leans on ──────────────────────────────
workspace = upstream("frappe", "frappe", "public", "js", "frappe", "views", "workspace", "workspace.js")
if workspace is None:
    fail.append("Frappe's workspace.js was not found under %s: what the page leans on is unchecked" % APPS_ROOT)
else:
    shown_at = workspace.split("async show_page(page) {")[1]
    check('this.body = this.wrapper.find(".layout-main-section");' in workspace
          and 'this.body.prepend(frappe.render_template("workspace_loading_skeleton"));' in workspace
          and 'this.body.addClass("edit-mode");' in workspace and 'this.body.removeClass("edit-mode");' in workspace
          and "this.body.empty()" not in workspace and "this.body.html(" not in workspace,
          "Frappe's workspace body: its skeleton put first in it, edit-mode marked on it, and never emptied")
    check("this._page = current_page;" in shown_at
          and shown_at.index("this._page = current_page;") < shown_at.index("await frappe.after_ajax"),
          "the workspace shown is named as Frappe starts drawing it, before it waits on the server")
container = upstream("frappe", "frappe", "public", "js", "frappe", "views", "container.js")
if container is not None:
    change = container.split("change_to(label) {")[1].split("\n\t}\n")[0]
    check(change.index('$(document).trigger("page-change");') < change.index('$(this.page).trigger("show");'),
          "Frappe says page-change before it shows the page: the workspace is named a moment after")
router = upstream("frappe", "frappe", "public", "js", "frappe", "router.js")
if router is not None:
    check('route = ["Workspaces", frappe.workspaces[route[0]].name];' in router,
          "a module's address is the Workspaces route, by the workspace's name")
boot = upstream("frappe", "frappe", "boot.py")
if boot is not None:
    check('"type": item.type,' in boot and '"label": _(item.label),' in boot
          and "sidebar_items[sidebar_title.lower()] = {" in boot,
          "the boot carries each module's menu by its name in small letters, each entry with its type and label")
widgets = {name: upstream("frappe", "frappe", "public", "js", "frappe", "widgets", name + ".js")
           for name in ("base_widget", "links_widget", "quick_list_widget", "number_card_widget", "chart_widget",
                        "shortcut_widget")}
if all(widgets.values()):
    check('<div class="widget" data-widget-name=' in widgets["base_widget"] and '<div class="widget-title"></div>' in widgets["base_widget"]
          and 'this.widget.addClass("links-widget-box");' in widgets["links_widget"]
          and 'this.widget.addClass("quick-list-widget-box");' in widgets["quick_list_widget"]
          and 'this.widget.addClass("number-widget-box");' in widgets["number_card_widget"]
          and 'this.widget.addClass("dashboard-widget-box");' in widgets["chart_widget"]
          and 'this.widget.addClass("shortcut-widget-box");' in widgets["shortcut_widget"],
          "Frappe's cards carry the classes the styles name")
    check('class="link-item ellipsis' in widgets["links_widget"] and '<span class="link-content ellipsis">' in widgets["links_widget"]
          and 'frappe.utils.icon("es-line-arrow-up-right", "xs", "", "", "ml-2")' in widgets["links_widget"],
          "a link is a .link-item holding its .link-content and Frappe's arrow, which the rows replace")
    check('class="list-no-data-state text-muted"' in widgets["quick_list_widget"] and '<div class="see-all btn btn-xs">' in widgets["quick_list_widget"],
          "an empty list and its way to the whole list are where the styles look for them")
else:
    fail.append("Frappe's widgets were not found under %s" % APPS_ROOT)
spacer = upstream("frappe", "frappe", "public", "js", "frappe", "views", "workspace", "blocks", "spacer.js")
if spacer is not None:
    check('classList.add("widget", "spacer")' in spacer, "a spacer is a widget too, which is why the cards are named")
listing = upstream("frappe", "frappe", "public", "js", "frappe", "list", "list_view.js")
if listing is not None:
    check("} else if (Array.isArray(value)) {\n\t\t\t\t\tfilters.push([doctype, field, value[0], value[1]]);" in listing,
          "a list takes [\"in\", [...]] from the route as one filter")
model = upstream("frappe", "frappe", "public", "js", "frappe", "model", "model.js")
if model is not None:
    check("return frappe.boot.user.can_create.indexOf(doctype) !== -1;" in model,
          "who may make a document is known in the browser, from the boot")
print("upstream: the workspace body, the order Frappe shows a page in, its cards' classes, as this relies on")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL MODULE PAGE CHECKS PASSED")
