"""Checks the desk home (the dashboard above the module tiles), without a
bench.

    python scripts/verify_home.py

  1  the rules: whose home carries the company's figures, what waits for
     the user, the figures across the top, the pages offered, the one button,
     and the modules in the order of an employee's time with the company
  2  the glue: one call, for the logged-in user and nobody else, the
     people read as the user may see them
  3  the page: loaded with the desk, switched by a boot flag, never able to
     stop the desk opening, Frappe's own tiles drawn as the list of modules
     down the left, and the desk exactly Frappe's while it is being edited

The rules are loaded without Frappe.
"""
import ast
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
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


spec = importlib.util.spec_from_file_location("home_rules", os.path.join(APP, "home_rules.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)  # proves it has no Frappe import
print("loaded home_rules.py without Frappe")

# ── 1. The rules ────────────────────────────────────────────────────────
check(R.home_of(None) == R.DASHBOARD and R.home_of("") == R.DASHBOARD and R.home_of("Dashboard") == R.DASHBOARD
      and R.home_of(" Tiles Only ") == R.TILES and R.home_of("anything else") == R.DASHBOARD,
      "the desk opens on the dashboard unless Theme Settings say Tiles Only, a setting nobody touched included")
check(R.sees_people(["Employee", "HR User"]) and R.sees_people(["HR Manager"]) and R.sees_people(["System Manager"])
      and not R.sees_people(["Employee", "Supervisor", "Head of Department"]) and not R.sees_people(None),
      "the company's figures are HR's")

ALERTS = [
    {"kind": "assignment", "key": "T1", "title": "Authorise the overtime", "doctype": "Overtime Request",
     "docname": "OT-1", "urgency": "overdue", "when": "overdue by 2 days"},
    {"kind": "assignment", "key": "T2", "title": "Probation evaluation", "doctype": "Probation Evaluation",
     "docname": "PEV-1", "urgency": "overdue", "when": "overdue by a day"},
    {"kind": "notification", "key": "N1", "title": "Leave approved", "doctype": "Leave Application", "docname": "LA-1",
     "urgency": "none", "when": "", "unread": 1},
    {"kind": "assignment", "key": "T3", "title": "Contract ends", "doctype": "Employee Contract", "docname": "CON-1",
     "urgency": "today", "when": "due today"},
    {"kind": "assignment", "key": "T4", "title": "Review", "doctype": None, "docname": None, "urgency": "soon",
     "when": "in 3 days"},
    {"kind": "notification", "key": "N2", "title": "Already read", "urgency": "none", "unread": 0},
]
waits = R.waiting(ALERTS, shown=3)
check((waits["tasks"], waits["overdue"], waits["today"], waits["unread"]) == (4, 2, 1, 1),
      "what waits: four assigned, two of them late and one due today, one notification unread: %s"
      % ((waits["tasks"], waits["overdue"], waits["today"], waits["unread"]),))
check([row["key"] for row in waits["items"]] == ["T1", "T2", "T3"] and [row["key"] for row in waits["notes"]] == ["N1"],
      "the first rows of each, in the order My Alerts gives them, a read notification left out")
check(waits["items"][0] == {"title": "Authorise the overtime", "doctype": "Overtime Request", "docname": "OT-1",
                            "when": "overdue by 2 days", "band": "overdue", "key": "T1"},
      "each row carries what the page prints and opens")
nothing = R.waiting(None)
check((nothing["tasks"], nothing["unread"], nothing["items"], nothing["notes"]) == (0, 0, [], []), "nobody's work")
for found, want in ((nothing, "Nothing waiting"), (waits, "2 overdue"),
                    (dict(waits, overdue=0), "1 due today"), (dict(waits, overdue=0, today=0), "None overdue")):
    check(R.waiting_note(found) == want, "under the count: %s, not %s" % (want, R.waiting_note(found)))

PEOPLE = {"active": 1284, "joined": 6, "on_site": 1107, "on_leave": 23, "ending": 14, "ending_from": "2026-10-13",
          "ending_to": "2026-11-12"}
hr = R.cards(waits, PEOPLE)
check([card["key"] for card in hr] == ["employees", "on_site", "on_leave", "contracts"],
      "HR's figures: the employees, who is on site, who is on leave, the contracts about to end: %s"
      % [card["key"] for card in hr])
check((hr[0]["value"], hr[0]["note"]) == (1284, "6 joined this month") and (hr[1]["value"], hr[1]["note"]) == (
    1107, "86.2% of employees") and (hr[2]["value"], hr[3]["value"], hr[3]["note"]) == (23, 14, "In the next 30 days"),
    "each with its figure and what is said under it: %s" % [(card["value"], card["note"]) for card in hr])
check(hr[3]["route"] == ["List", "Employee Contract"] and hr[3]["filters"] == {
    "status": ["in", ["Active", "Expiring Soon"]], "end_date": ["between", ["2026-10-13", "2026-11-12"]]}
    and hr[0]["filters"] == {"status": "Active"} and hr[1]["route"] == ["attendance-board"],
    "and each opens the list or the page behind its figure")
quiet = R.cards(waits, dict(PEOPLE, active=0, joined=0, on_site=0, ending=0))
check((quiet[0]["note"], quiet[1]["note"], quiet[3]["tone"]) == ("Active today", "0% of employees", "blue")
      and hr[3]["tone"] == "rose", "nobody yet, and no contract ending, are said plainly")
own = R.cards(waits, None)
check([card["key"] for card in own] == ["waiting", "unread"] and own[0]["value"] == 4 and own[0]["tone"] == "rose"
      and own[0]["mine"] == 1 and own[1]["value"] == 1 and R.cards(nothing, None)[0]["tone"] == "blue",
      "everybody else sees their own work, and nothing of the company's: %s" % [card["key"] for card in own])
check(all(card.get("mine") == 1 for card in own) and own[0]["route"] == ["List", "ToDo"]
      and own[1]["route"] == ["List", "Notification Log"],
      "and each of their cards opens their own list, never everybody's: %s" % [(card["route"], card.get("mine")) for card in own])
links =R.shortcuts(["leave-overview", "hr-overview", "not-a-page"])
check(links == [{"label": "HR Overview", "route": ["hr-overview"]}, {"label": "Leave Overview", "route": ["leave-overview"]}]
      and R.shortcuts(None) == [], "the pages offered are those the user may open, in the home's own order: %s" % links)
check(R.call_to_action(links) == {"label": "HR Overview", "route": ["hr-overview"]}
      and R.call_to_action([]) == {"label": "My To Do", "route": ["List", "ToDo"], "mine": 1},
      "the one button: the first page they may open, else their own ToDo list")


def tile_labels(folder):
    """The labels of the desk tiles an app ships."""
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith(".json"):
            out.append(json.load(io.open(os.path.join(folder, name), encoding="utf-8")).get("label"))
    return out


# Frappe HR's own tile for the whole app, and the home's own page: neither is a module
NOT_MODULES = {"Frappe HR", "HR Overview"}
ours = tile_labels(os.path.join(APP, "desktop_icon"))
theirs = tile_labels(os.path.join(APPS_ROOT, "hrms", "hrms", "desktop_icon"))
check(theirs and "Recruitment" in theirs and "Loans" in ours, "the HR tiles are read from Frappe HR and from this app: %s"
      % (theirs or "none found under %s" % APPS_ROOT))
check(len(set(R.MODULES)) == len(R.MODULES) and set(R.MODULES) == (set(theirs) | set(ours)) - NOT_MODULES,
      "the modules are every HR tile, each once, so a tile added later cannot be left out of the order: %s"
      % sorted(set(R.MODULES) ^ ((set(theirs) | set(ours)) - NOT_MODULES)))
check(R.MODULES[0] == "Recruitment" and R.MODULES[-1] == "Tenure", "from recruitment to Tenure, which holds the exit")
check(R.MODULES == ("Recruitment", "HR Setup", "Shift & Attendance", "Leaves", "Payroll", "Tax & Benefits", "Loans",
                    "Expenses", "Performance", "Tenure"),
      "in the order of an employee's time with the company: %s" % (R.MODULES,))
navigation = read("hrms_addon", "hrms_addon", "navigation_rules.py")
check('("Exit", "log-out", ["Employee Separation"' in navigation.split("GROUPS = {")[1].split('"Tenure": [')[1].split("\n    ],")[0],
      "and Tenure is where the exit is")
print("rules: HR's figures and everybody's own work, the pages offered, the one button, the modules recruitment to exit")

# ── 2. The glue ─────────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "home.py")
tree = ast.parse(glue)
summary = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "summary")
check(not summary.args.args and re.search(r"@frappe\.whitelist\(\)\ndef summary\(\):", glue),
      "summary is one whitelisted call that takes nobody to look at")
check(len(re.findall(r"@frappe\.whitelist", glue)) == 1, "and the only one")
body = glue.split("def summary(")[1].split("\ndef ")[0]
check('return alerts.my_alerts(limit=40)["alerts"]' in glue.split("def _alerts(")[1].split("\ndef ")[0]
      and "rules.waiting(_or([], _alerts))" in body, "what waits is the user's own, as My Alerts lists it")
check("rules.sees_people(frappe.get_roles(user)) and frappe.has_permission(\"Employee\", \"read\")" in body,
      "the people figures are HR's, and only for somebody who may read employees")
people = glue.split("def _people(")[1].split("\ndef ")[0]
check('frappe.get_list("Employee", filters={"status": "Active"}' in people and "frappe.get_all(\"Employee\"" not in glue,
      "the employees are read as the user may see them, so a branch's HR sees that branch")
ending = glue.split("def _contracts_ending(")[1].split("\ndef ")[0]
check('frappe.get_list("Employee Contract"' in ending and '"status": ["in", list(rules.RUNNING)]' in ending
      and '"end_date": ["between", [today, until]]' in ending and "except Exception:\n        return 0" in ending,
      "the contracts ending are those still running, as the user may see them, and nothing on a site without them")
check("frappe.get_cached_doc(\"Page\", page).is_permitted()" in glue.split("def _may_open(")[1],
      "a page is offered only to somebody whose roles may open it")
check("ignore_permissions" not in glue and "frappe.db.sql" not in glue, "nothing is read past the user's permissions")
guard = glue.split("def _or(")[1].split("\ndef ")[0]
check("except Exception:" in guard and "defer_insert=True" in guard and "return fallback" in guard
      and "people = _or(None, _people, today)" in body,
      "a part that cannot be read is left out and logged past the GET's rollback, and the rest still comes")
print("glue: one call, the user's own work, the people as they may see them")

# ── 3. The page ─────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
check('"/assets/hrms_addon/js/hrms_addon_home.js",' in hooks.split("app_include_js = [")[1].split("]")[0],
      "the home's script is loaded with the desk")
theme = read("hrms_addon", "hrms_addon", "theme.py")
enabled = theme.split("def home_enabled(")[1].split("\ndef ")[0]
check("bootinfo.hrms_addon_home = home_enabled()" in theme and "home_rules.home_of(value) == home_rules.DASHBOARD" in enabled
      and enabled.count("return 1") >= 2, "a boot flag switches it, on unless Theme Settings say otherwise or cannot be read")
check("bootinfo.hrms_addon_home_modules = list(home_rules.MODULES)" in theme,
      "the order of the modules comes with the boot, so the tiles are never seen in another order first")
settings = {row["fieldname"]: row for row in json.loads(read(
    "hrms_addon", "hrms_addon", "doctype", "hrms_addon_theme_settings", "hrms_addon_theme_settings.json"))["fields"]}
switch = settings.get("desk_home", {})
check((switch.get("fieldtype"), switch.get("options"), switch.get("default")) == ("Select", "Dashboard\nTiles Only", "Dashboard"),
      "Theme Settings has the switch, a Select so a setting nobody saved reads as the dashboard")
check(tuple(switch.get("options", "").split("\n")) == R.HOMES, "and its options are the rules' own")

script = read("hrms_addon", "public", "js", "hrms_addon_home.js")
check("if (!frappe.boot.hrms_addon_home) return;" in script, "Tiles Only: the script does nothing at all")
check('if (frappe.session && frappe.session.user === "Guest") return;' in script, "nor for a guest")
check('const METHOD = "hrms_addon.hrms_addon.home.summary";' in script
      and script.count('fetch("/api/method/" + METHOD') == 1 and "if (asking || Date.now() - asked_at < FRESH_MS) return;" in script,
      "it asks home.summary, once at a time")
check(not re.search(r"frappe\s*\.\s*x?call\(", script) and "response.ok ? response.json() : null" in script
      and ".catch(() => {})" in script,
      "and never through frappe.call, whose failure opens Frappe's Server Error dialog on the page everybody lands on")
check(script.count("try {") >= 4 and "console.error(error);" in script,
      "nothing it does can stop the desk opening: every entry is caught")
check("wrapper.insertBefore(home, tiles);" in script and ".desktop-container" in script
      and "innerHTML" not in script.split("function mount(")[1].split("\n\tfunction ")[0],
      "it is added before Frappe's tiles, which it never rewrites")
check("appendChild" not in script.replace("document.head.appendChild(sheet);", "") and ".remove()" not in script.replace(
    "there.remove();", "") and "setAttribute" not in script and ".style.order" not in script,
    "nothing of Frappe's is moved, removed or marked: the list and its order are CSS")
check("if (!answer && asked_at && Date.now() - asked_at < FRESH_MS) return true;" in script
      and "there.remove();" in script and 'classList.remove("ha-has-home")' in script,
      "a failed call leaves the desk as Frappe drew it, and is not asked again at once")
check("frappe.utils.escape_html" in script and "function esc(" in script, "what it prints is escaped")
check("frm." not in script and "bench build" in script and "sheet.textContent = CSS + order_rules();" in script,
      "its styles are written into the page, so a change needs no build")
NOT_EDITED = '.desktop-wrapper.ha-has-home:not([data-mode="Edit"])'
RAIL = NOT_EDITED + " > .desktop-container"
TILES = RAIL + " > .icons-container > .icons"
check("const RAIL = '%s';" % RAIL in script and 'const TILES = RAIL + " > .icons-container > .icons";' in script,
      "the tiles it styles are those of the desk itself, by child selectors all the way, and never in edit mode")
css = script.split("const CSS = `")[1].split("`;")[0].replace("${TILES}", TILES).replace("${RAIL}", RAIL)
check("${" not in css, "the styles name nothing else of the script's")
rules = [line.strip() for line in css.splitlines() if "{" in line and not line.strip().startswith(("@", "/*", "from ", "to "))]
frappes = [line for line in rules if ".desktop-" in line or ".icons" in line or ".icon-" in line]
hidden = '.desktop-wrapper.ha-has-home[data-mode="Edit"] .ha-home { display: none; }'
check(frappes and hidden in frappes and all(line.startswith(NOT_EDITED) for line in frappes if line != hidden),
      "every rule on something of Frappe's holds only outside edit mode, where the desk is exactly as Frappe draws it "
      "(%d rules): %s" % (len(frappes), [line[:60] for line in frappes if line != hidden and not line.startswith(NOT_EDITED)][:2]))
check(all(line.startswith((RAIL, NOT_EDITED + " > .desktop-navbar", NOT_EDITED + " > .ha-home", NOT_EDITED + " {"))
          for line in frappes if line != hidden),
      "and reaches only the desk's own tiles: a folder's thumbnails and the folder window keep Frappe's layout")
wide = css.split("@media (min-width: 901px) {")[1].split("\n}\n")[0]
check(NOT_EDITED + " { display: flex; flex-wrap: wrap;" in wide and "display: grid" not in wide
      and NOT_EDITED + " > .desktop-navbar { flex: 0 0 100%; order: 0; }" in wide,
      "on a wide screen the list sits beside the home in a flex row that wraps: a grid would hold Frappe's sticky "
      "navbar to its own row")
check("flex: 1 1 0; min-width: 0; max-width: 1196px;" in wide.split(NOT_EDITED + " > .ha-home {")[1].split("}")[0],
      "the home starts from nothing and grows: a line breaks before it shrinks, and it would drop under the list")
rail = wide.split(RAIL + " {")[1].split("}")[0]
check("order: 1; flex: 0 0 248px; width: 248px; margin: 18px 0 18px 20px; position: sticky;" in rail
      and "top: calc(var(--desktop-navbar-height, 52px) + 18px);" in rail
      and "max-height: calc(100vh - var(--desktop-navbar-height, 52px) - 36px);" in rail and "overflow-y: auto;" in rail,
      "the list stays under the navbar as the page scrolls, as tall as the window allows and no taller, with the same "
      "gap below as above so it is never pushed up under the navbar")
base = css.split(RAIL + " {")[1].split("}")[0]
check("width: auto;" in base and "box-sizing: border-box;" in base,
      "under the home on a narrow screen the list keeps inside the page, whatever width the density gives the container")
check('content: var(--ha-rail-title, "Modules");' in css.split(RAIL + "::after {")[1].split("}")[0]
      and 'wrapper.style.setProperty("--ha-rail-title", JSON.stringify(__("Modules")));' in script,
      "its heading is written by CSS, in the user's language")
order = script.split("function order_rules(")[1].split("\n\t}\n")[0]
check("const escape = window.CSS && window.CSS.escape;" in order and "CSS.escape(" not in order.replace("window.CSS.escape", "")
      and "[data-id=${escape(String(label))}] { order: ${index + 1}; }" in order and "${TILES} > .desktop-icon" in order
      and "sheet.textContent = CSS + order_rules();" in script,
      "the order is one CSS rule a module, by the label Frappe writes on the tile; the browser's CSS.escape is "
      "reached through window, the styles here being a constant named CSS")
check("frappe.boot.hrms_addon_home_modules" in script
      and "order: 1000;" in css.split(TILES + " > .desktop-icon {")[1].split("}")[0],
      "from the order the boot carries, and a tile that is not one of the modules named comes after them")
loose = [line.strip() for line in css.splitlines()
         if line.strip() and not line.startswith(("\t", " ", "}", "@", "/*", "   ")) and "{" in line
         and not line.lstrip().startswith((".ha-home", ".desktop-wrapper.ha-has-home"))]
check(not loose, "every rule is the home's own or under the desk that has one: %s" % loose[:3])
check("@media (prefers-reduced-motion: reduce)" in css and "@media (max-width: 560px)" in css,
      "it holds on a phone, and stills its motion for those who ask")
print("page: loaded with the desk, switched by a boot flag, the modules a list down the left, the edit layout Frappe's")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL DESK HOME CHECKS PASSED")
