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
  4  the desk come back to, drawn out to the window's edges, and each
     module's own menu opened from the list, with what Frappe does that
     these lean on read from Frappe itself
  5  each user's own desk: HR the company's people, a manager their team,
     an employee their own, and none given what is not theirs

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


def own_colours(css_text, bundle_text):
    """What a page's styles write that is not the theme's: any colour outside a var() fallback, white aside
    (white text on the navy, which the settings' contrast line keeps readable), and every var(--hra-...)
    fallback that is not the stylesheet's own value."""
    roots = dict(re.findall(r"(--hra-[\w-]+):\s*(#[0-9A-Fa-f]{3,6})\s*;", bundle_text))
    drift = sorted({"%s %s (the stylesheet: %s)" % (name, fallback, roots.get(name)) for name, fallback in
                    re.findall(r"var\((--hra-[\w-]+),\s*(#[0-9A-Fa-f]{3,6})\)", css_text)
                    if roots.get(name, "").lower() != fallback.lower()})
    text = re.sub(r"var\(--[\w-]+,\s*(?:#[0-9A-Fa-f]{3,6}|var\([^()]*\))\)", "", css_text)
    fixed = sorted({found for found in re.findall(r"#[0-9A-Fa-f]{3,6}\b|rgba?\([^)]*\)", text)
                    if found.lower() not in ("#fff", "#ffffff") and not found.replace(" ", "").startswith("rgba(255,255,255,")})
    return fixed, drift


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

# ── each user's own desk ──
import datetime  # noqa: E402

D = datetime.date
TODAY = D(2026, 10, 14)
check([R.view_of(True, "E1", ["x"]), R.view_of(False, "E1", ["x"]), R.view_of(False, "E1", []), R.view_of(False, None, [])]
      == [R.HR, R.MANAGER, R.STAFF, R.OWN],
      "HR have HR's desk whoever reports to them, a manager theirs, an employee their own, anybody else what waits for them")
where = R.where_today(["a", "b", "c", "d", "e", "f"], {"a", "d"}, {"b": ("Present", 1), "c": ("Absent", 0), "f": ("On Leave", 0)}, {"d"})
check(where == {"a": "in", "b": "late", "c": "absent", "d": "on_leave", "e": "not_in", "f": "on_leave"},
      "where each is today: on leave before clocked in, absent as marked, late as marked, not in yet otherwise: %s" % where)
board = R.today_board(["a", "b", "c", "d", "e", "f"], {"a", "d"}, {"b": ("Present", 1), "c": ("Absent", 0), "f": ("On Leave", 0)}, {"d"})
check(board["total"] == 6 and [(row["key"], row["value"]) for row in board["rows"]]
      == [("in", 2), ("late", 1), ("on_leave", 2), ("absent", 1), ("not_in", 1)],
      "the day's bars: those in counted with the late among them, and every employee once otherwise: %s" % board)
staffed = R.departments([{"department": "Production - LPL"}] * 3 + [{"department": "Stores - LPL"}] * 2 + [{}]
                        + [{"department": "D%d - LPL" % index} for index in range(6)], shown=4)
check([(row["label"], row["value"]) for row in staffed] == [("Production", 3), ("Stores", 2), ("D0", 1), ("D1", 1), ("Other", 5)]
      and staffed[0]["filters"] == {"status": "Active", "department": "Production - LPL"}
      and R.departments([{}])[0]["filters"] == {"status": "Active", "department": ["is", "not set"]},
      "the departments, the largest first by their own name, those without one last, the rest as Other, each opening "
      "its people: %s" % staffed)
people_rows = [
    {"name": "E1", "employee_name": "Ann", "date_of_birth": "1990-10-14", "date_of_joining": "2026-10-20"},
    {"name": "E2", "employee_name": "Bob", "date_of_birth": "1988-02-29", "date_of_joining": "2016-10-28",
     "custom_probation_end_date": "2026-10-29"},
    {"name": "E3", "employee_name": "Cy", "custom_probation_end_date": "2026-10-13", "date_of_birth": "1999-10-29"}]
upcoming = R.coming_up(people_rows, [{"name": "SEP-1", "employee_name": "Dee", "custom_relieving_date": "2026-10-15"}], TODAY)
check([(row["title"], row["when"]) for row in upcoming] == [
    ("Birthday: Ann", "today"), ("Last day: Dee", "tomorrow"), ("10 years with the company: Bob", "in 14 days")]
      and upcoming[1]["doctype"] == "Employee Separation" and upcoming[0]["doctype"] == "Employee",
      "what is coming up in the next two weeks, the nearest first, the last of them included; not a probation that "
      "ended yesterday, not a first year still to come, not a birthday past the fortnight: %s"
      % [(row["title"], row["when"]) for row in upcoming])
check(R._next(D(2027, 2, 1), 2, 29) == D(2027, 2, 28) and R._next(D(2028, 2, 1), 2, 29) == D(2028, 2, 29),
      "a birthday on the 29th of February falls on the 28th in a year without one")
team = R.team_today([{"name": "a", "employee_name": "Amy"}, {"name": "b", "employee_name": "Zed"},
                     {"name": "c", "employee_name": "Bo"}, {"name": "d", "employee_name": "Al"}], {"a"}, {}, {"c"})
blind = R.team_today([{"name": "a", "employee_name": "Amy"}, {"name": "c", "employee_name": "Bo"}], {"a"}, {}, {"c"},
                      seen={"clock": False, "attendance": False, "leave": True})
check((blind["in"], blind["on_leave"]) == (None, 1)
      and [(row["title"], row["when"]) for row in blind["rows"]] == [("Bo", "On leave"), ("Amy", "")]
      and R.team_today([{"name": "a"}], set(), {}, set(), seen={"clock": True, "attendance": False, "leave": False})["on_leave"] is None,
      "a manager who may read neither the clock nor Attendance is told nobody's day but their leave; one who may "
      "read neither Attendance nor leave is told nobody is on leave: %s" % blind)
blind_cards = R.view_cards(R.MANAGER, R.waiting([]), team={"size": 2, "in": None, "on_leave": None, "employee": "E9"})
check([(card["value"], card["note"]) for card in blind_cards[1:3]] == [(0, "Not open to you"), (0, "Not open to you")],
      "and their cards say so, rather than a nought that would read as nobody")
check((team["size"], team["in"], team["on_leave"]) == (4, 1, 1)
      and [(row["title"], row["when"]) for row in team["rows"]]
      == [("Al", "Not in yet"), ("Zed", "Not in yet"), ("Bo", "On leave"), ("Amy", "In")],
      "a manager's team today, those not in yet first: %s" % team)
requests = R.my_requests([("Leave Application", "Leave", {"name": "L1", "status": "Open", "docstatus": 0, "modified": "2026-10-10"}),
                          ("Gate Pass", "Gate pass", {"name": "G1", "status": "Rejected", "docstatus": 0, "modified": "2026-10-12"}),
                          ("Employee Loan", "Loan", {"name": "N1", "status": "Approved", "docstatus": 1, "modified": "2026-10-11"})])
check(requests["waiting"] == 1 and [row["docname"] for row in requests["rows"]] == ["G1", "N1", "L1"]
      and requests["rows"][2]["band"] == "today" and requests["rows"][0]["band"] == "none",
      "an employee's requests, the latest first; waiting only those in draft that nobody has turned down: %s" % requests)
check([row["title"] for row in R.holidays([{"holiday_date": "2026-10-09", "description": "Gone"},
                                          {"holiday_date": "2026-12-25", "description": "Christmas Day"},
                                          {"holiday_date": "2026-12-08", "description": "Heroes Day"}], TODAY)]
      == ["Heroes Day", "Christmas Day"], "the holidays still to come, the nearest first")
nobody = R.waiting([])
manager_cards = R.view_cards(R.MANAGER, nobody, team={"size": 4, "in": 3, "on_leave": 1, "employee": "E9"})
staff_cards = R.view_cards(R.STAFF, nobody, mine={"employee": "E1", "leave_left": 16.5, "present": 9, "late": 2, "waiting": 1})
check([card["key"] for card in manager_cards] == ["team", "team_in", "team_leave", "waiting"]
      and manager_cards[0]["filters"] == {"status": "Active", "reports_to": "E9"} and manager_cards[1]["note"] == "75% of your team",
      "a manager's figures are their team's, and open their team")
check([card["key"] for card in staff_cards] == ["leave_left", "present", "requests", "waiting"]
      and staff_cards[0]["value"] == 16.5 and staff_cards[0]["filters"] == {"employee": "E1"}
      and staff_cards[1]["note"] == "2 late" and "route" not in staff_cards[2],
      "an employee's figures are their own, and open their own records")
check(R.view_cards(R.HR, nobody, PEOPLE) == R.cards(nobody, PEOPLE)
      and [card["key"] for card in R.view_cards(R.HR, nobody, None)] == ["waiting", "unread"]
      and [card["key"] for card in R.view_cards(R.OWN, nobody)] == ["waiting", "unread"]
      and [card["key"] for card in R.view_cards(R.MANAGER, nobody, team=None)] == ["waiting", "unread"],
      "HR's figures are as before; a desk whose figures could not be read has what waits for the user")
print("desks: HR's, a manager's, an employee's, each from what that user may know")

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
view_part = summary_body = body
check("hr = rules.sees_people(frappe.get_roles(user)) and frappe.has_permission(\"Employee\", \"read\")" in body
      and "me = _or(None, _employee_of, user)" in body and "reports = _or([], _reports, me.name) if me and not hr else []" in body
      and "view = rules.view_of(hr, me, reports)" in body,
      "the desk is chosen from the user's roles and their own employee record: HR's only for somebody who may read employees")
check(body.index("if view == rules.HR:") < body.index("people = _or(None, _people, today)")
      and body.index("elif view == rules.MANAGER:") < body.index("team = _or(None, _team, me.name, reports, today)")
      and "if view in (rules.MANAGER, rules.STAFF):" in body and '"cards": rules.view_cards(view, waits, people, team, mine),' in body,
      "each desk is given its own parts and no other's")
own_record = glue.split("def _employee_of(")[1].split("\ndef ")[0]
check('{"user_id": user, "status": "Active"}' in own_record,
      "the user's own employee record is the active one whose user is theirs")
for part, needle in (("_reports", 'frappe.get_list("Employee", filters={"reports_to": employee, "status": "Active"}'),
                     ("_last_days", 'frappe.get_list("Employee Separation", filters={'),
                     ("_mine", 'frappe.get_list("Attendance", filters={'),
                     ("_mine", 'frappe.get_list(doctype, filters={"employee": me.name, "docstatus": ["<", 2]}')):
    check(needle in glue.split("def %s(" % part)[1].split("\ndef ")[0],
          "%s reads with the user's own permissions" % part)
mine_part = glue.split("def _mine(")[1].split("\ndef ")[0]
check('if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):' in mine_part
      and "for doctype, label in rules.REQUESTS:" in mine_part and 'if frappe.has_permission("Attendance", "read"):' in mine_part
      and 'if not frappe.has_permission("Employee", "read"):\n        return []' in glue.split("def _reports(")[1]
      and 'if not frappe.has_permission("Employee Separation", "read"):\n        return []' in glue.split("def _last_days(")[1]
      and '"employee": me.name' in mine_part.split('frappe.get_list("Attendance"')[1].split(")")[0],
      "an employee's requests and days are their own, of the doctypes the site has; a part the user may not read is "
      "left out before it is asked for, not tried and logged on every desk load")
marks = glue.split("def _marks(")[1].split("\ndef ")[0]
check('"employee": ["in", names]' in marks and marks.count('"employee": ["in", names]') == 3
      and "frappe.get_all" not in marks and marks.count("frappe.get_list(") == 3
      and all('frappe.has_permission("%s", "read")' % doctype in marks
              for doctype in ("Employee Checkin", "Attendance", "Leave Application"))
      and "rules.team_today(reports, clocked, marked, on_leave, seen=seen)" in glue
      and "clocked, marked, on_leave, _seen = _marks(names, today)" in people,
      "today's marks are read for the employees the user may see, with the user's own permissions on each of the "
      "clock, Attendance and leave, and not at all where they may not read it: reports_to is no permission")
check("_or(None, exits._leave_balance, me.name, today)" in mine_part and "_or([], _holidays, me, today)" in body
      and "_or(None, _team, me.name, reports, today)" in body and "_or(None, _mine, me, today)" in body,
      "every part of a desk is read through _or: one that cannot be read is left out, the desk still comes")
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
taken_off = script.split("function unmount(")[1].split("\n\t}\n")[0]
check("appendChild" not in script.replace("document.head.appendChild(sheet);", "") and script.count("insertBefore") == 1
      and script.count(".remove()") == 1 and ".style.order" not in script
      and 'wrapper.querySelectorAll(".ha-home, .ha-rail-toggle, .ha-rail-menu").forEach((node) => node.remove());' in taken_off,
      "nothing of Frappe's is moved or removed: the list and its order are CSS, and the only things taken off the "
      "page are the home's own")
check(script.count("insertAdjacentHTML") == 1 and 'tile.insertAdjacentHTML(\n\t\t\t\t\t\t"beforeend",' in script
      and script.count("setAttribute") == 2 and 'toggle.setAttribute("aria-expanded"' in script
      and 'heading.setAttribute("aria-expanded", shown ? "true" : "false");' in script
      and script.count("classList.add(") == 2 and 'tile.classList.add("ha-has-menu");' in script
      and 'wrapper.classList.add("ha-has-home");' in script,
      "a tile gains an arrow and a menu after what Frappe wrote in it, and a class; nothing else of Frappe's is marked "
      "(the other aria-expanded is on a heading inside the home's own menu)")
check("if (!answer && asked_at && Date.now() - asked_at < FRESH_MS) return true;" in script
      and "else if (there && !answer) unmount(desk());" in script
      and 'tile.classList.remove("ha-has-menu", "ha-open")' in taken_off and 'wrapper.classList.remove("ha-has-home");' in taken_off
      and "MEASURED.forEach((name) => wrapper.style.removeProperty(name));" in taken_off,
      "a failed call leaves the desk as Frappe drew it, the arrows, menus and measures off it too, and is not asked "
      "again at once")
written = set(re.findall(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", script.split("const CSS = `")[0]))
served = sorted(expr for expr in written if re.search(r"\b(row|card|link|action|data|waits)\.", expr) or expr == "name")
bare = [expr for expr in served if not (expr.startswith(("esc(", "count(", "icon(")) or ".map(esc)" in expr)]
check("return frappe.utils.escape_html(text == null ? \"\" : String(text));" in script.split("function esc(")[1].split("}")[0]
      and len(served) >= 12 and not bare,
      "every value from the server is escaped as it is written into the page, a number as a number and a picture by "
      "its name (%d looked at): %s" % (len(served), bare[:3]))
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
EDITED = '.desktop-wrapper.ha-has-home[data-mode="Edit"]'
hidden = (EDITED + " .ha-home { display: none; }",)


def selectors(line):
    """Each selector of a rule: a rule may name several."""
    return [part.strip() for part in line.split("{")[0].split(",")]


outside = [line for line in frappes if line not in hidden]
check(frappes and all(line in frappes for line in hidden)
      and all(part.startswith(NOT_EDITED) for line in outside for part in selectors(line)),
      "every rule on something of Frappe's holds only outside edit mode, where the desk is exactly as Frappe draws it "
      "and only the home is hidden (%d rules): %s"
      % (len(frappes), [line[:60] for line in outside if not all(part.startswith(NOT_EDITED) for part in selectors(line))][:2]))


def desks_own(part):
    """The desk itself, its navbar, the home, or the desk's own tiles."""
    return part == NOT_EDITED or part.startswith((RAIL, NOT_EDITED + " > .desktop-navbar", NOT_EDITED + " > .ha-home"))


check(all(desks_own(part) for line in outside for part in selectors(line)),
      "and reaches only the desk's own tiles, every selector of every rule: a folder's thumbnails and the folder "
      "window keep Frappe's layout: %s" % [part[:70] for line in outside for part in selectors(line) if not desks_own(part)][:2])
wide = css.split("@media (min-width: 901px) {")[1].split("\n}\n")[0]
check(NOT_EDITED + " { display: flex; flex-wrap: wrap;" in wide and "display: grid" not in wide
      and NOT_EDITED + " > .desktop-navbar { flex: 0 0 100%; order: 0; }" in wide,
      "on a wide screen the list sits beside the home in a flex row that wraps: a grid would hold Frappe's sticky "
      "navbar to its own row")
across = wide.split(NOT_EDITED + " { display: flex;")[1].split("}")[0]
check("justify-content: flex-start;" in across and "center" not in across and "align-content: flex-start;" in across,
      "the row starts at the left edge, and its lines at the top: centred, a wide screen had room left over at both "
      "sides, and a desk taller than what is on it would open a gap under the navbar")
check("flex: 1 1 0; min-width: 0; max-width: none;" in wide.split(NOT_EDITED + " > .ha-home {")[1].split("}")[0],
      "the home starts from nothing and grows to fill the row: a line breaks before it shrinks, and it would drop "
      "under the list; nothing caps its width")
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
         and not line.lstrip().startswith((".ha-home", ".ha-rail-", ".desktop-wrapper.ha-has-home"))]
check(not loose, "every rule is the home's own or under the desk that has one: %s" % loose[:3])
bundle = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
fixed, drift = own_colours(css, bundle)
check(not fixed, "the home writes no colour of its own, only the theme's, so a colour picked in Theme Settings "
      "reaches it (white on the navy aside): %s" % fixed[:4])
check(not drift, "and every fallback is the stylesheet's own value: %s" % drift[:3])
check("--ha-h-gold: var(--hra-shell-marker, #F0AB00);" in css and "--ha-h-on-gold: var(--hra-primary-dark, #0A2540);" in css
      and all(".ha-home .ha-tone-%s { --ha-tone: var(--hra-%s, " % (tone, name) in css for tone, name in (
          ("green", "success"), ("amber", "amber-text"), ("rose", "danger"), ("blue", "accent")))
      and "background: var(--ha-band, var(--ha-h-navy));" in css,
      "its gold is the Gold Highlight with Dark Navy on it, its figures' tones and bars the status colours")
check("@media (prefers-reduced-motion: reduce)" in css and "@media (max-width: 560px)" in css,
      "it holds on a phone, and stills its motion for those who ask")
print("page: loaded with the desk, switched by a boot flag, the modules a list down the left, the edit layout Frappe's")

# ── 4. Come back to, edge to edge, a module's own menu ───────────────────
FRAPPE = os.path.join(APPS_ROOT, "frappe", "frappe")


def frappes_own(*parts):
    path = os.path.join(FRAPPE, *parts)
    return io.open(path, encoding="utf-8").read() if os.path.exists(path) else ""


# Frappe draws its desk afresh every time the page is shown, after "page-change", and says when it has
container = frappes_own("public", "js", "frappe", "views", "container.js")
desktop = frappes_own("desk", "page", "desktop", "desktop.js")
shown = desktop.split('frappe.pages["desktop"].on_page_show')[1].split("};")[0] if "on_page_show" in desktop else ""
made = desktop.split("\n\tmake() {")[1].split("\n\t}\n")[0] if "\n\tmake() {" in desktop else ""
check(container and 0 < container.find('$(document).trigger("page-change");') < container.find('$(this.page).trigger("show");')
      and "desktop_page.update();" in shown and "$(this.page.body).empty();" in made and "this.setup();" in made
      and '$(document).trigger("desktop_screen", { desktop: this });' in desktop.split("\n\tsetup() {")[1].split("\n\t}\n")[0],
      "Frappe says the page changed, then empties its desk and draws it afresh, then says the desk is drawn: read "
      "from %s" % FRAPPE)
again = script.split("function drawn_again(")[1].split("\n\t}\n")[0]
check('$(document).on("desktop_screen", drawn_again);' in script and '$(document).on("page-change", arrive);' in script
      and "if (!on_desk()) return;" in again and "if (!present()) show();" in again,
      "so the home goes back on when Frappe says the desk is drawn, where it is missing")
scrolled = frappes_own("public", "js", "frappe", "utils", "utils.js")
check('element_to_be_scrolled = element_to_be_scrolled || $("html, body");' in scrolled
      and "frappe.utils.scroll_to(0)" in container
      and 'const pane = wrapper && wrapper.closest(".main-section");' in again and "if (pane) pane.scrollTop = 0;" in again,
      "and opens at its top: Frappe scrolls the window when it shows a page, and the desk scrolls in a pane of its own")
check("setTimeout(measure, 0);" in again and '$(".sticky-top > .navbar").hide();' in desktop,
      "measured again once Frappe has done what it does after saying so, its own navbar hidden among it")
looking = script.split("function arrive(")[1].split("\n\t}\n")[0]
check("const there = present() || show();" in looking
      and "if (tries < 12 && (!there || tries < 5)) setTimeout(look, 150 * tries);" in looking,
      "and is looked for a few times more after the page changes, having been on the desk Frappe was about to empty")
found = script.split("function desk(")[1].split("\n\t}\n")[0]
there = script.split("function present(")[1].split("\n\t}\n")[0]
check("wrapper.offsetParent !== null" in found and "const wrapper = desk();" in script.split("function mount(")[1]
      and 'home.childElementCount && wrapper.classList.contains("ha-has-home")' in there,
      "on the desk that is on the screen, which has the home when the home is in it with something drawn")

# edge to edge
measure = script.split("function bleed(")[1].split("\n\t}\n")[0]
check("const MOST_INSET = 64;" in script
      and measure.index("MEASURED.forEach((name) => wrapper.style.removeProperty(name));") < measure.index("getBoundingClientRect()")
      and 'wrapper.closest(".main-section")' in measure and "try {" in measure and "console.error(error);" in measure,
      "how far in the page holds the desk is measured afresh, from where Frappe puts it, against the pane that "
      "scrolls, and never stops the desk opening")
check('cut.overflowX !== "visible" || cut.overflowY !== "visible"' in measure
      and "inset[side] > 0.5 && inset[side] <= MOST_INSET" in measure
      and 'wrapper.style.setProperty("--ha-bleed-" + side, (drawn_out ? Math.round(inset[side]) : 0) + "px");' in measure
      and "desk-height" not in script and "b: holder.getBoundingClientRect().bottom - box.bottom," in measure,
      "it is drawn out no further than something that would cut it off, and not at all on a side something wide holds "
      "it in from; at the foot too, so the padding under it does not push the list up under the navbar at the end of "
      "the page; and it is never made taller than what is on it, which scrolled the page by whatever Frappe puts under it")
check('const page = wrapper.closest(".page-container");' in measure
      and "t: box.top - Math.max(top, page ? page.getBoundingClientRect().top : top)," in measure,
      "its top is measured from its own page, so Frappe's navbar above the page, there until the desk hides it, is "
      "not taken for padding")
check('const MEASURED = ["--ha-bleed-l", "--ha-bleed-r", "--ha-bleed-t", "--ha-bleed-b"];' in script
      and "bleed(wrapper);" in script.split("function mount(")[1].split("\n\t}\n")[0]
      and '$(window).on("resize", resized);' in script
      and "measuring = setTimeout(measure, 150);" in script.split("function resized(")[1].split("\n\t}\n")[0]
      and 'if (wrapper && wrapper.classList.contains("ha-has-home")) bleed(wrapper);' in script.split("function measure(")[1].split("\n\t}\n")[0]
      and "if (there) measure();" in looking and "setTimeout(measure, 0);" in again,
      "measured each time the home goes on, each time it is looked for (the page may not have been laid out when it "
      "went on) and when the window changes size")
drawn_out = css.split("\n" + NOT_EDITED + " {")[1].split("}")[0]
check("margin: calc(-1 * var(--ha-bleed-t, 0px)) calc(-1 * var(--ha-bleed-r, 0px)) calc(-1 * var(--ha-bleed-b, 0px)) "
      "calc(-1 * var(--ha-bleed-l, 0px));" in drawn_out and "width: auto; max-width: none;" in drawn_out and "min-height" not in drawn_out
      and "background-color: inherit;" in drawn_out,
      "CSS draws the desk out by what was measured, and by nothing where nothing was; its colour is the page's own, "
      "whatever the theme")

# a module's own menu
sidebar = frappes_own("public", "js", "frappe", "ui", "sidebar", "sidebar.js")
router = frappes_own("public", "js", "frappe", "router.js")
check("frappe.boot.workspace_sidebar_item[desktop_icon.label.toLowerCase()]" in desktop
      and "sidebar: desktop_icon.label," in desktop
      and "(frappe.boot.workspace_sidebar_item || {})[String(label).toLowerCase()]" in script.split("function entries(")[1],
      "a module's menu is its sidebar's, found by the tile's name as Frappe finds it")
listed = script.split("function entries(")[1].split("\n\t}\n")[0]
check('item.type === "Section Break"' in listed and 'item.type === "Link"' in listed and "path_of(item)" in listed
      and "!row.heading || (all[index + 1] && !all[index + 1].heading)" in listed,
      "its headings and the entries under them, an entry that goes nowhere and a heading with nothing under it left out")
ways = script.split("function path_of(")[1].split("\n\t}\n")[0]
item_js = frappes_own("public", "js", "frappe", "ui", "sidebar", "sidebar_item.js")
check(all(needle in item_js for needle in ('this.item.link_type === "Report"', 'this.item.link_type == "Workspace"',
                                           'this.item.link_type === "URL"', "tab: this.item.tab,", 'args.doc_view = "List";'))
      and all(needle in ways for needle in ('item.link_type === "URL"', 'item.link_type === "Workspace"',
                                            'item.link_type === "Report"', "if (!item.report) return null;",
                                            'item.link_type === "Page" && item.route_options', "args.tab = item.tab;",
                                            'args.doc_view = "List";', "frappe.utils.generate_route(args)")),
      "each entry's address is worked out as Frappe's sidebar works it out: a report, a workspace, an address of its "
      "own, a page, a tab, a list on the entry's filters")
opened = script.split("function follow(")[1].split("\n\t}\n")[0]
check("frappe.app.sidebar.setup(frappe.route_options.sidebar);\n\t\t\t\tfrappe.route_options = null;" in sidebar
      and "frappe.route_hash = target_element.hash;" in router and "frappe.router.is_app_route(target_element.pathname)" in router,
      "Frappe's sidebar clears every route option once it has read its own, and its router takes a link's tab from "
      "its address: read from Frappe")
check("frappe.route_options = Object.keys(options).length ? options : { sidebar: module };" in opened
      and "if (url.hash) frappe.route_hash = url.hash;" in opened and "frappe.set_route(url.pathname);" in opened
      and 'window.open(url.href, "_blank", "noopener");' in opened
      and "outside || url.origin !== window.location.origin || !frappe.router.is_app_route(url.pathname)" in opened,
      "so an entry opens on its module's sidebar unless it carries filters of its own, which would be lost; a tab "
      "goes as the router sends it; an address outside the desk opens in a tab of its own")
drawn = script.split("function menus(")[1].split("\n\t}\n")[0]
check('":scope > .desktop-container > .icons-container > .icons > .desktop-icon[data-id]"' in drawn
      and 'if (tile.querySelector(".ha-rail-menu")) return;' in drawn and "if (!list.length) return;" in drawn
      and "event.preventDefault();" in drawn and "event.stopPropagation();" in drawn
      and 'event.key === "Enter" || event.key === " "' in drawn and "try {" in drawn,
      "the arrow and the menu go on the desk's own tiles once, only where there is a menu; a click on them is "
      "theirs and never opens the module; they work from the keyboard")
written = script.split("function menu_html(")[1].split("\n\t}\n")[0]
check('role="button" tabindex="0" aria-expanded="false"' in drawn and 'role="link" tabindex="0"' in written
      and "${esc(__(row.heading))}" in written and "${esc(__(row.label))}" in written
      and "${menu_html(list, module)}" in drawn and "open_module = open_module === module ? null : module;" in drawn,
      "one menu open at a time, each name written as text")
check('const shown = shown_groups.has(module + "|" + row.heading);' in written and 'data-group="${index}"' in written
      and '<span class="ha-rail-heading" role="button" tabindex="0"' in written
      and 'const heading = event.target.closest(".ha-rail-heading");' in drawn
      and 'group.classList.toggle("ha-shown", shown);' in drawn and "return;" in drawn.split("if (heading) {")[1].split("}")[0]
      and "shown_groups.add(key);" in drawn and "shown_groups.delete(key);" in drawn,
      "each heading of a menu opens and shuts the entries under it, and nothing else; it stays as it was left while the "
      "desk is drawn again")
check(TILES + " > .desktop-icon > .ha-rail-menu .ha-rail-items { display: none;" in css
      and TILES + " > .desktop-icon > .ha-rail-menu .ha-rail-group.ha-shown > .ha-rail-items { display: block; }" in css
      and "color: var(--hra-primary-mid, #2A5A8C);" in css.split(TILES + " > .desktop-icon > .ha-rail-menu .ha-rail-heading {")[1].split("}")[0]
      and "color: var(--text-color, #1E2A3A);" in css.split(TILES + " > .desktop-icon > .ha-rail-menu .ha-rail-link {")[1].split("}")[0],
      "a heading's entries are shut until it is opened, and a heading is in the theme's blue, apart from its entries")
shows = [line for line in rules if ".ha-rail-" in line and "display:" in line.split("{", 1)[1].split("}")[0].replace("display: none", "")]
check("\n.ha-rail-toggle, .ha-rail-menu { display: none; }\n" in css
      and shows and all(part.startswith(TILES + " > .desktop-icon") for line in shows for part in selectors(line))
      and "display: grid;" in css.split(TILES + " > .desktop-icon > .ha-rail-toggle {")[1].split("}")[0]
      and "display:" not in css.split(TILES + " > .desktop-icon > .ha-rail-menu {")[1].split("}")[0]
      and TILES + " > .desktop-icon.ha-open > .ha-rail-menu { display: block; }" in css,
      "the arrow and the menu are hidden wherever their tile is (the desk being edited, a folder's window) and "
      "shown only in the list, the menu only once its arrow opens it: %s" % [line[:70] for line in shows][:4])
check(TILES + " > .desktop-icon.ha-open > .ha-rail-menu { display: block; }" in css
      and "box-sizing: border-box;" in css.split(TILES + " > .desktop-icon > .ha-rail-menu {")[1].split("}")[0]
      and TILES + " > .desktop-icon.ha-has-menu > .icon-caption { flex: 1 1 0; width: auto !important; }" in css
      and TILES + " > .desktop-icon.ha-has-menu::after { display: none; }" in css,
      "a menu is shut until its arrow opens it and keeps inside the list; the name shares the row with the picture "
      "and the arrow, which stands for the plain mark")
print("fixes: the home back on a desk drawn afresh, the desk out to the window's edges, each module's menu from the list")

# ── 5. each user's own desk, drawn ──
drawn_more = script.split("function sections(")[1].split("\n\t}\n")[0]
check("home.innerHTML = hero(data) + cards(data) + panels(data) + sections(data);" in script
      and all(needle in drawn_more for needle in ("parts.today && parts.today.rows", "parts.departments && parts.departments.length",
                                                  "if (parts.coming)", "if (parts.team)", "if (parts.requests)", "if (parts.holidays)"))
      and 'if (!blocks.length) return "";' in drawn_more,
      "under what waits, each desk draws only the parts the server sent it")
clicked = script.split("function draw(")[1].split("\n\t}\n")[0]
check('const row = ((data.sections || {})[element.getAttribute("data-section")] || [])[index];' in clicked
      and 'if (row && row.doctype && row.docname) frappe.set_route("Form", row.doctype, row.docname);'
      in clicked.split('what === "item"')[1]
      and 'go({ route: ["List", "Employee"], filters: row.filters });' in clicked
      and 'else if (what === "board") go({ route: ["attendance-board"] });' in clicked,
      "a row opens its record, a department its people, the day's figures the Attendance Board")
check('class="ha-home-panel ha-home-waiting"' in script and '<span class="ha-home-bar-label">${esc(__(row.label))}</span>' in script
      and "<b>${count(row.value)}</b>" in script,
      "the bars write their names as text and their figures as numbers")
check(".ha-home-panels.ha-home-three { grid-template-columns: repeat(3, minmax(0, 1fr)); }" in css
      and ".ha-home-panels, .ha-home-panels.ha-home-two, .ha-home-panels.ha-home-three { grid-template-columns: minmax(0, 1fr); }"
      in css.split("@media (max-width: 1100px) {")[1],
      "the parts sit side by side on a wide screen and one under another on a narrow one")
print("desks drawn: HR's company, a manager's team, an employee's own")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL DESK HOME CHECKS PASSED")
