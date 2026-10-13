"""Checks the desk home (the dashboard above the module tiles), without a
bench.

    python scripts/verify_home.py

  1  the rules: whose home carries the company's figures, what waits for
     the user, the figures across the top, the pages offered, the one button
  2  the glue: one call, for the logged-in user and nobody else, the
     people read as the user may see them
  3  the page: loaded with the desk, switched by a boot flag, never able to
     stop the desk opening, and Frappe's own tiles left to Frappe while the
     desk is being edited

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
links = R.shortcuts(["leave-overview", "hr-overview", "not-a-page"])
check(links == [{"label": "HR Overview", "route": ["hr-overview"]}, {"label": "Leave Overview", "route": ["leave-overview"]}]
      and R.shortcuts(None) == [], "the pages offered are those the user may open, in the home's own order: %s" % links)
check(R.call_to_action(links) == {"label": "HR Overview", "route": ["hr-overview"]}
      and R.call_to_action([]) == {"label": "My To Do", "route": ["List", "ToDo"], "mine": 1},
      "the one button: the first page they may open, else their own ToDo list")
print("rules: HR's figures and everybody's own work, the pages offered, the one button")

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
      "it is added above Frappe's tiles, which it never rewrites")
check("if (!answer && asked_at && Date.now() - asked_at < FRESH_MS) return true;" in script
      and "there.remove();" in script and 'classList.remove("ha-has-home")' in script,
      "a failed call leaves the desk as Frappe drew it, and is not asked again at once")
check("frappe.utils.escape_html" in script and "function esc(" in script, "what it prints is escaped")
check("frm." not in script and "bench build" in script and "sheet.textContent = CSS;" in script,
      "its styles are written into the page, so a change needs no build")
css = script.split("const CSS = `")[1].split("`;")[0]
tiles = [line for line in css.splitlines() if ".desktop-icon" in line or "> .icons " in line or "> .icons{" in line]
check(tiles and all(".desktop-wrapper.ha-has-home:not([data-mode=\"Edit\"]) .desktop-container > .icons-container > .icons"
                    in line for line in tiles),
      "Frappe's tiles are restyled only on the desk itself and never while it is being edited: a folder's tiles and "
      "the edit layout are Frappe's (%d rules)" % len(tiles))
check('.desktop-wrapper.ha-has-home[data-mode="Edit"] .ha-home { display: none; }' in css,
      "and the home steps aside while the desk is edited")
loose = [line.strip() for line in css.splitlines()
         if line.strip() and not line.startswith(("\t", " ", "}", "@", "/*", "   ")) and "{" in line
         and not line.lstrip().startswith((".ha-home", ".desktop-wrapper.ha-has-home"))]
check(not loose, "every rule is the home's own or under the desk that has one: %s" % loose[:3])
check("box-sizing: border-box" in css.split(".desktop-wrapper.ha-has-home .desktop-container {")[1].split("}")[0],
      "the tiles' container never widens the page")
check("@media (prefers-reduced-motion: reduce)" in css and "@media (max-width: 560px)" in css,
      "it holds on a phone, and stills its motion for those who ask")
print("page: loaded with the desk, switched by a boot flag, added above tiles it leaves to Frappe")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL DESK HOME CHECKS PASSED")
