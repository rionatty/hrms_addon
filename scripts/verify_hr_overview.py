"""Checks for the HR Overview dashboard and the round desk tiles, run
without a bench.

hr_overview_rules.py imports nothing from Frappe, so it is loaded directly
and exercised: the greeting, the months the headcount is drawn over, who was
employed on a day, the year's turnover, the attendance stacked by day, the
appraisal gauge and the task rings.

It also cross-checks the glue (the employees read with the user's own
permissions, every figure counted for those people, the fields read existing
upstream), the page (its roles, its one call, its text escaped, its styles
kept to itself), the HR home tile and sidebar (shipped as files, no
Workspace to take the page's address, our tiles added to saved desktops)
and the round tiles (a picture for every Frappe HR tile, round and navy, and
the theme script preferring ours).

    python scripts/verify_hr_overview.py
"""
import ast
import datetime
import glob
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
D = datetime.date


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def upstream_fields(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return {f["fieldname"] for f in json.load(open(hits[0], encoding="utf-8"))["fields"]}
    return None


rules = load("hr_overview_rules")

# ── 1. The figures ────────────────────────────────────────────────────
if [rules.greeting(h) for h in (0, 9, 11, 12, 16, 17, 23)] != ["Good morning"] * 3 + ["Good afternoon"] * 2 + \
        ["Good evening"] * 2:
    fail.append("greeting: morning before noon, afternoon to five, evening after")
if rules.percent(1, 3) != 33.3 or rules.percent(5, 0) != 0.0 or rules.percent(0, 7) != 0.0:
    fail.append("percent: one place, and nothing of nothing is 0")
if rules.month_ends(D(2026, 10, 2), 3) != [D(2026, 8, 31), D(2026, 9, 30), D(2026, 10, 2)]:
    fail.append("month_ends: each month's last day, the current month ending today")
if rules.month_ends(D(2026, 1, 15), 3) != [D(2025, 11, 30), D(2025, 12, 31), D(2026, 1, 15)]:
    fail.append("month_ends must cross the year")
if len(rules.month_ends(D(2026, 10, 2))) != 12:
    fail.append("month_ends draws twelve months unless told otherwise")
people = [(D(2025, 1, 1), None), (D(2026, 3, 1), D(2026, 6, 15)), (D(2026, 9, 20), None), (None, None)]
if [rules.headcount_on(people, day) for day in (D(2026, 2, 28), D(2026, 6, 15), D(2026, 6, 16), D(2026, 9, 30))] \
        != [1, 2, 1, 2]:
    fail.append("headcount_on: joined by the day, the relieving day still counted, no joining date never")
if rules.headcount_series(people, [D(2026, 6, 15), D(2026, 9, 30)]) != [2, 2]:
    fail.append("headcount_series: the headcount at each date")
year = rules.turnover(people, D(2026, 10, 2))
if year != {"leavers": 1, "rate": rules.percent(1, (1 + 2) / 2.0)}:
    fail.append("turnover: the year's leavers over the average of the start's and today's headcount: %s" % year)
if rules.turnover(people, D(2027, 7, 1))["leavers"] != 0:
    fail.append("turnover counts only the last twelve months")
if rules.joined_between(people, D(2026, 9, 1), D(2026, 9, 30)) != 1 or \
        rules.joined_between(people, D(2026, 9, 21), D(2026, 9, 30)) != 0:
    fail.append("joined_between: both days in, nothing else")
if rules.months_back(D(2026, 3, 31), 1) != D(2026, 2, 28) or rules.months_back(D(2026, 1, 31), 12) != D(2025, 1, 31):
    fail.append("months_back keeps within the month it lands in")
days = rules.recent_days([D(2026, 9, 28), D(2026, 9, 29), D(2026, 9, 29), D(2026, 10, 5), D(2026, 9, 30), None],
                         D(2026, 10, 2), count=2)
if days != [D(2026, 9, 29), D(2026, 9, 30)]:
    fail.append("recent_days: the last days marked up to today, each once, oldest first: %s" % days)
rows = [(D(2026, 9, 29), "Present", 0), (D(2026, 9, 29), "Present", 1), (D(2026, 9, 29), "Half Day", 0),
        (D(2026, 9, 29), "Work From Home", 1), (D(2026, 9, 29), "Absent", 0), (D(2026, 9, 29), "On Leave", 0),
        (D(2026, 9, 29), "Weird", 0), (D(2026, 9, 1), "Absent", 0)]
stack = rules.attendance_days(rows, [D(2026, 9, 29), D(2026, 9, 30)])
if stack != [{"On Time": 2, "Late": 2, "Absent": 1, "On Leave": 1, "date": D(2026, 9, 29)},
             {"On Time": 0, "Late": 0, "Absent": 0, "On Leave": 0, "date": D(2026, 9, 30)}]:
    fail.append("attendance_days: present (late or not), absent, on leave, other days left out: %s" % stack)
if rules.tally(["Casual", "Permanent", None, "Casual", "Intern", "Contract", "Contract"], order=("Permanent",)) \
        != [("Permanent", 1), ("Casual", 2), ("Contract", 2), ("Intern", 1), ("Not Set", 1)]:
    fail.append("tally: those in the order first, then the most, a blank as Not Set")
summary = rules.appraisal_summary([(1, 80, "Very Good"), (1, 92.5, "Excellent"), (0, 40, "Below Average"),
                                   (1, None, "Good"), (1, 65, "Odd")])
if summary != {"total": 5, "submitted": 4, "percent": 80.0, "average": round((80 + 92.5 + 65) / 3, 1),
               "bands": [("Excellent", 1), ("Very Good", 1), ("Good", 1)]}:
    fail.append("appraisal_summary: the submitted ones only, their average, the bands in order: %s" % summary)
if rules.appraisal_summary([]) != {"total": 0, "submitted": 0, "percent": 0.0, "average": 0.0, "bands": []}:
    fail.append("appraisal_summary of nothing is nothing")
if [rules.task_ring(band) for band in ("overdue", "today", "soon", "later", "none", None, "x")] != \
        [100, 85, 60, 30, 10, 10, 10]:
    fail.append("task_ring: the nearer, the fuller")
print("figures: greeting, months, headcount, turnover, attendance, appraisals, rings")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "hr_overview.py")
body = glue.split("def overview(")[-1].split("\ndef ")[0]
for needle, why in (
        ('@frappe.whitelist()\ndef overview(branch: str | None = None) -> dict:', "must be whitelisted, the branch optional"),
        ('frappe.has_permission("Employee", "read", throw=True)', "must be for those who may read employees"),
        ('frappe.get_list("Employee"', "must read the employees with the user's own permissions"),
        ('frappe.get_list("Branch"', "must offer only the branches the user may see")):
    if needle not in (glue if needle.startswith("@") else body):
        fail.append("hr_overview.overview %s" % why)
if 'frappe.get_all("Employee"' in glue:
    fail.append("hr_overview must never read employees past the user's permissions")
for helper in ("_on_site", "_on_leave", "_attendance", "_appraisals"):
    part = glue.split("def %s(" % helper)[-1].split("\ndef ")[0]
    if '"employee": ["in", names]' not in part:
        fail.append("hr_overview.%s must count only the people the user may see" % helper)
if "alerts.my_alerts(" not in glue or "alerts.rules.ASSIGNMENT" not in glue:
    fail.append("hr_overview's tasks must be the user's own assignments, as My Alerts has them")
for doctype, fields in (("Employee", ("status", "date_of_joining", "relieving_date", "branch")),
                        ("Attendance", ("employee", "attendance_date", "status", "late_entry", "docstatus")),
                        ("Leave Application", ("employee", "status", "from_date", "to_date")),
                        ("Employee Checkin", ("employee", "time")),
                        ("Appraisal Cycle", ("cycle_name", "start_date")),
                        ("Appraisal", ("appraisal_cycle", "employee"))):
    known = upstream_fields(doctype)
    if known is None:
        continue  # Frappe HR not checked out next to the app
    for field in fields:
        if field not in known | {"docstatus"}:
            fail.append("hr_overview reads %s.%s, which Frappe HR does not have" % (doctype, field))
custom = {(f["dt"], f["fieldname"]) for f in json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"),
                                                             encoding="utf-8"))}
for field in ("custom_total_score", "custom_band"):
    if ("Appraisal", field) not in custom:
        fail.append("hr_overview reads Appraisal.%s, which no custom field makes" % field)
print("glue: one call, the user's own people, the fields there")

# ── 3. The page ───────────────────────────────────────────────────────
page = json.loads(read("hrms_addon", "hrms_addon", "page", "hr_overview", "hr_overview.json"))
if page.get("name") != "hr-overview" or page.get("standard") != "Yes" or page.get("module") != "HRMS Addon":
    fail.append("the page is hr-overview, standard, in HRMS Addon")
if sorted(row["role"] for row in page.get("roles") or []) != ["HR Manager", "HR User", "System Manager"]:
    fail.append("the page is for HR and the System Manager, and nobody else")
js = read("hrms_addon", "hrms_addon", "page", "hr_overview", "hr_overview.js")
for needle, why in (
        ('frappe.pages["hr-overview"].on_page_load = function (wrapper) {', "must set the page up"),
        ('frappe.xcall("hrms_addon.hrms_addon.hr_overview.overview", args)', "must fill itself in one call"),
        ("if (branch) args.branch = branch;", "must leave an empty branch out of the call"),
        ("${esc(task.title", "must escape a task's title"),
        ("${esc(__(kind))}", "must escape the employment types"),
        ("${esc(appraisals.cycle", "must escape the cycle's name"),
        ("${esc(data.first_name", "must escape the user's name")):
    if needle not in js:
        fail.append("hr_overview.js %s" % why)
style = js.split("const HRO_STYLE = `")[-1].split("`;")[0]
selectors = 0
for line in style.splitlines():
    line = re.sub(r"\$\{[^}]*\}", "", line)  # a colour put in from HRO_COLOURS
    if "{" not in line:
        continue
    selector = line.split("{")[0].strip()
    if not selector or selector.startswith("@media"):
        continue
    selectors += 1
    for part in selector.split(","):
        part = part.strip()
        if not (part.startswith(".hro") or part.startswith('html[data-theme="dark"] .hro')
                or part.startswith('.page-container[data-page-route="hr-overview"]')):
            fail.append("hr_overview.js styles %r, which is not the page's own" % part)
if selectors < 30:
    fail.append("only %d style rules read in hr_overview.js: the check is looking in the wrong place" % selectors)
if re.search(r"(?<![\w-])(eval|new Function)\(", js):
    fail.append("hr_overview.js must not evaluate text")
print("page: HR's, one call, escaped, its styles its own")

# ── 4. The HR home: tile, sidebar, saved desktops ─────────────────────
icon = json.loads(read("hrms_addon", "hrms_addon", "desktop_icon", "hr_overview.json"))
want = {"label": "HR Overview", "name": "HR Overview", "app": "hrms_addon", "icon_type": "Link",
        "link_type": "Workspace Sidebar", "link_to": "HR Overview", "parent_icon": "Frappe HR", "standard": 1, "hidden": 0}
if any(icon.get(key) != value for key, value in want.items()) or icon.get("idx") != -1:
    fail.append("desktop_icon/hr_overview.json: a link tile under Frappe HR, first (idx -1), opening its sidebar")
sidebar = json.loads(read("hrms_addon", "hrms_addon", "workspace_sidebar", "hr_overview.json"))
items = [(row.get("link_type"), row.get("link_to")) for row in sidebar.get("items") or []]
if sidebar.get("name") != "HR Overview" or not items or items[0] != ("Page", "hr-overview"):
    fail.append("workspace_sidebar/hr_overview.json: the HR Overview page first, so the tile opens it")
for kind, target in items:
    if kind == "Page" and not os.path.exists(os.path.join(APP, "page", target.replace("-", "_"))):
        fail.append("the HR Overview sidebar links the page %s, which this app does not have" % target)
if glob.glob(os.path.join(APP, "workspace", "hr_overview*")):
    fail.append("no Workspace may be called HR Overview: it would take the page's address")
nav = load("navigation_rules")
if nav.HOME != "HR Overview" or nav.OWN_TILES[0] != ("HR Overview", "first") \
        or [label for label, where in nav.OWN_TILES[1:]] != list(nav.PAGE_LABELS):
    fail.append("navigation_rules.OWN_TILES: HR Overview first, then our pages' tiles")
tile = {"label": "HR Overview"}
loans = {"label": "Loans"}
if nav.with_tiles([{"label": "Leaves"}], [(tile, "first"), (loans, "last")]) != [tile, {"label": "Leaves"}, loans]:
    fail.append("with_tiles adds the missing tiles, first or last")
if nav.with_tiles([tile, loans], [(tile, "first"), (loans, "last")]) is not None:
    fail.append("with_tiles changes nothing on a desktop that has them")
if nav.with_tiles(None, [(tile, "first")]) is not None or nav.with_tiles([], [(None, "first")]) is not None:
    fail.append("with_tiles leaves alone what is not a saved desktop, and adds no tile that is not there")
navigation = read("hrms_addon", "hrms_addon", "navigation.py")
if '("our tiles on saved desktops", _tiles_on_saved_desktops)' not in navigation \
        or "rules.with_tiles(layout, tiles)" not in navigation:
    fail.append("navigation must add our tiles to the saved desktops on migrate")
print("home: tile and sidebar shipped, the page keeps its address, saved desktops get the tiles")

# ── 5. Round tiles ────────────────────────────────────────────────────
ours = os.path.join(REPO, "hrms_addon", "public", "icons", "desktop_icons")
names = {"hr_overview", "loans"}
upstream = os.path.join(APPS_ROOT, "hrms", "hrms", "public", "icons", "desktop_icons", "solid")
if os.path.isdir(upstream):
    names |= {name[:-4] for name in os.listdir(upstream) if name.endswith(".svg")}
for name in sorted(names):
    for style in ("solid", "subtle"):
        path = os.path.join(ours, style, name + ".svg")
        if not os.path.exists(path):
            fail.append("no round %s tile for %s" % (style, name))
            continue
        svg = open(path, encoding="utf-8").read()
        if '<circle cx="27" cy="27" r="27"' not in svg or "#06B58B" in svg.upper() or "1F876C" in svg.upper():
            fail.append("the %s tile for %s must be a navy disc, not Frappe HR's teal" % (style, name))
theme = read("hrms_addon", "public", "js", "hrms_addon_theme.js")
for needle, why in (
        ("assets/hrms_addon/icons/desktop_icons/${style}/${frappe.scrub(icon_name", "must look for our picture first"),
        ("return shipped.includes(ours) ? `/${ours}` : app_picture.call(this, icon_name, variant);",
         "must show ours where it ships one, else the app's own picture"),
        (".desktop-icon .icon-container { border-radius: 50% !important;", "must cut every tile to a circle")):
    if needle not in theme:
        fail.append("hrms_addon_theme.js %s" % why)
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if not any("hrms_addon_theme.js" in path for path in hooks.get("app_include_js") or []):
    fail.append("app_include_js must load the theme script, or the tiles stay square")
print("tiles: a round navy picture for every Frappe HR tile and ours, the theme preferring them")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL HR OVERVIEW CHECKS PASSED")
