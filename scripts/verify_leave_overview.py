"""Checks the Leave Overview without a bench.

    python scripts/verify_leave_overview.py

Four questions, one row each (leave_overview_rules.py):

  1  who is away, and each department against its limit
  2  what is stuck: leave on a desk, and people not back
  3  what the year end will cost
  4  the year by month, and the sick leave worth a conversation
  5  who sees what: everybody for HR and management, their own people for
     a head of department or a supervisor; the money for management, the
     reasons for HR
  6  the glue only reads, and refuses before it reads; the page asks for
     nothing else, escapes what it draws, and has a way in
"""
import datetime
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


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def same(label, got, want):
    if got != want:
        fail.append("%s: expected %r, got %r" % (label, want, got))


R, L, E = load("leave_overview_rules"), load("leave_rules"), load("encashment_rules")
print("loaded leave_overview_rules.py without Frappe")
D = datetime.date

# ── 5. who sees what ──────────────────────────────────────────────────
same("an employee", R.reach(["Employee"]), None)
same("nobody", R.reach([]), None)
same("the HR Officer: everybody and the reasons, not the money", R.reach(["HR User", "Employee"]),
     {"all": True, "money": False, "why": True, "head": False})
same("the HR Manager: all of it", R.reach(["HR Manager"]), {"all": True, "money": True, "why": True, "head": False})
same("management: everybody and the money, not the reasons", R.reach(["General Manager"]),
     {"all": True, "money": True, "why": False, "head": False})
same("the Executive Director the same", R.reach(["Executive Director"])["why"], False)
same("a supervisor: their own people, no money, no reasons", R.reach(["Supervisor"]),
     {"all": False, "money": False, "why": False, "head": False})
same("a head of department: their own people", R.reach(["Head of Department"]),
     {"all": False, "money": False, "why": False, "head": True})
if set(R.SEES_ALL) - set(R.PAGE_ROLES) or set(R.SEES_MONEY) - set(R.SEES_ALL) or set(R.SEES_WHY) - set(R.SEES_ALL):
    fail.append("who sees everybody may open the page, and the money and the reasons are for some of them")
STAFF = [{"name": "ME", "reports_to": None, "department": "Extrusion", "branch": "Kawempe"},
         {"name": "A", "reports_to": "ME", "department": "Printing", "branch": "Kawempe"},
         {"name": "B", "reports_to": "X", "department": "Extrusion", "branch": "Kawempe"},
         {"name": "C", "reports_to": "X", "department": "Extrusion", "branch": "Jinja"},
         {"name": "D", "reports_to": "X", "department": "Stores", "branch": "Kawempe"}]
same("a supervisor's own: who reports to them", R.own_people(STAFF, "ME"), {"A"})
same("held to a department: its people too", R.own_people(STAFF, "ME", {"Extrusion"}), {"A", "B", "C"})
same("and to a plant: that plant's", R.own_people(STAFF, "ME", {"Extrusion"}, {"Kawempe"}), {"A", "B"})
same("a head held to no department heads their own", R.own_people(STAFF, "ME", head=True), {"A", "B", "C"})
same("a supervisor held to none sees only who reports to them", R.own_people(STAFF, "ME", head=False), {"A"})
same("somebody with no employee record and no department sees nobody", R.own_people(STAFF, None), set())
same("never themselves", "ME" in R.own_people(STAFF, "ME", {"Extrusion"}), False)
print("who sees what: everybody, or their own people; the money and the reasons apart")

# ── 1. who is away, and the cover ─────────────────────────────────────
LEAVES = [
    {"employee": "A", "employee_name": "Ann", "department": "Extrusion", "from_date": "2026-10-05", "to_date": "2026-10-16"},
    {"employee": "B", "employee_name": "Ben", "department": "Extrusion", "from_date": "2026-10-12", "to_date": "2026-10-12"},
    {"employee": "C", "employee_name": "Cat", "department": "Extrusion", "from_date": "2026-10-14", "to_date": "2026-10-20"},
    {"employee": "D", "employee_name": "Dan", "department": "Stores", "from_date": "2026-10-19", "to_date": "2026-10-19"},
    {"employee": "E", "employee_name": "Eve", "department": "Stores", "from_date": "2026-10-20", "to_date": "2026-10-30"},
]
found = R.away(LEAVES, "2026-10-12")
same("on leave today", [row["employee"] for row in found["today"]], ["B", "A"])
same("starting within the week, the soonest first", [row["employee"] for row in found["soon"]], ["C", "D"])
same("the day back is the day after the last", found["today"][0]["back_on"], "2026-10-13")
same("a leave starting today is not also starting soon", [row["employee"] for row in found["soon"] if row["employee"] == "B"], [])
rows = R.cover({"Extrusion": 40, "Stores": 12, "Printing": 9}, LEAVES, "2026-10-12", most_off=2)
by_name = {row["department"]: row for row in rows}
same("off today", (by_name["Extrusion"]["off_today"], by_name["Stores"]["off_today"]), (2, 0))
same("the most off on one day ahead, and the first day it happens",
     (by_name["Extrusion"]["peak"], by_name["Extrusion"]["peak_on"]), (2, "2026-10-12"))
same("two off is the limit, not over it", by_name["Extrusion"]["over"], False)
same("a department nobody is off in is still listed", by_name["Printing"]["peak"], 0)
over = {row["department"]: row for row in R.cover({"Extrusion": 40}, LEAVES, "2026-10-12", most_off=1)}
same("over the limit", (over["Extrusion"]["over"], R.cover({"Extrusion": 40, "Stores": 3}, LEAVES, "2026-10-12", 1)[0]["department"]),
     (True, "Extrusion"))
same("no limit, nothing is over", any(row["over"] for row in R.cover({"Extrusion": 40}, LEAVES, "2026-10-12", 0)), False)
same("beyond the days looked ahead is not counted", by_name["Stores"]["peak"], 1)
print("away and cover: today, this week, and each department's most off against its limit")

# ── 2. what is stuck ──────────────────────────────────────────────────
stuck = R.waiting([{"name": "L1", "employee_name": "Zed", "since": "2026-10-10"},
                   {"name": "L2", "employee_name": "Amy", "since": "2026-10-06"},
                   {"name": "L3", "employee_name": "Bob", "since": None}], "2026-10-12")
same("the longest wait first", [(row["name"], row["days"]) for row in stuck], [("L2", 6), ("L1", 2), ("L3", 0)])
same("the longest", (R.longest(stuck), R.longest([])), (6, 0))
print("stuck: how long each leave has been on its desk, the longest first")

# ── 3. the year end ───────────────────────────────────────────────────
if R.WORKING_DAYS_A_MONTH != E.WORKING_DAYS_A_MONTH:
    fail.append("a day of leave is worth what encashment pays for one: the gross over %d" % E.WORKING_DAYS_A_MONTH)
same("ten days at a gross of 520,000", R.worth(10, 520000), 200000.0)
same("no days, nothing", R.worth(-3, 520000), 0.0)
same("a type that does not carry forward loses what is left", R.at_risk(7.5), 7.5)
same("one that carries five loses the rest", R.at_risk(7.5, True, 5), 2.5)
same("under the five, nothing", R.at_risk(3, True, 5), 0.0)
same("one that carries without limit loses nothing", R.at_risk(30, True, 0), 0.0)
same("the row's figures", R.year_end([
    {"earned": 10, "balance": 12, "gross": 520000, "carries_forward": 1, "most_carried": 5},
    {"earned": 4, "balance": 2, "gross": 0, "carries_forward": 1, "most_carried": 5},
    {"earned": -1, "balance": 0, "gross": 260000}]),
    {"people": 3, "earned": 14.0, "value": 200000.0, "at_risk": 7.0, "unpriced": 1})
same("the plan kept to", R.plan_kept({"Taken": 6, "Applied": 2, "Not Applied": 2, "Planned": 40}), 0.8)
same("nothing yet due", R.plan_kept({"Planned": 12}), None)
if not {"Taken", "Applied", "Not Applied"} <= set(L.ROW_STATUSES):
    fail.append("the plan's statuses are leave_rules' own: %s" % (L.ROW_STATUSES,))
print("the year end: days earned and not taken, what they are worth, what would be lost, the plan kept to")

# ── 4. the pattern ────────────────────────────────────────────────────
YEAR = [{"leave_type": "Annual Leave", "from_date": "2026-03-30", "to_date": "2026-04-02", "days": 4},
        {"leave_type": "Sick Leave", "from_date": "2026-04-06", "to_date": "2026-04-06", "days": 1},
        {"leave_type": "Annual Leave", "from_date": "2025-12-29", "to_date": "2026-01-02", "days": 5}]
months = R.by_month(YEAR, 2026)
same("twelve months", [row["month"] for row in months], list(range(1, 13)))
same("a leave across two months is shared by its days", (months[2]["days"], months[3]["days"]),
     ({"Annual Leave": 2.0}, {"Annual Leave": 2.0, "Sick Leave": 1.0}))
same("only the days inside the year", months[0]["total"], 2.0)
same("the days of the year before are not put into its December", months[11]["total"], 0.0)
same("somebody not told why sees one kind", R.by_month(YEAR, 2026, by_type=False)[3]["days"], {R.ALL_LEAVE: 3.0})
SPELLS = [{"employee": "A", "employee_name": "Ann", "from_date": day, "to_date": day, "days": 1}
          for day in ("2026-02-02", "2026-03-06", "2026-05-13")]  # a Monday, a Friday, a Wednesday
SPELLS += [{"employee": "B", "employee_name": "Ben", "from_date": "2026-06-10", "to_date": "2026-06-23", "days": 10}]
SPELLS += [{"employee": "C", "employee_name": "Cat", "from_date": day, "to_date": day, "days": 1}
           for day in ("2026-07-06", "2026-08-01")]  # a Monday, a Saturday
listed = R.sick_patterns(SPELLS)
same("several spells, or more than one beside the rest day", [row["employee"] for row in listed], ["A", "C"])
same("how often, how long, how many beside the rest day",
     (listed[0]["spells"], listed[0]["days"], listed[0]["beside_rest"]), (3, 3.0, 2))
same("one long illness is not a pattern", [row for row in listed if row["employee"] == "B"], [])
same("the list is a short one", len(R.sick_patterns(
    [dict(spell, employee="E%d" % n) for n in range(30) for spell in SPELLS[:3]])), R.SICK_SHOWN)
if "leave_type" in listed[0] or "reason" in listed[0]:
    fail.append("the list says how often, never why")
print("the pattern: leave by month, and the sick leave worth a conversation")

# ── 6. the glue, the page and the way in ──────────────────────────────
glue = read("hrms_addon", "hrms_addon", "leave_overview.py")
for writes in (".db_set(", "frappe.db.set_value(", ".insert(", ".save(", ".submit(", ".cancel(", "frappe.db.commit(",
               "frappe.delete_doc(", "frappe.db.sql("):
    if writes in glue:
        fail.append("leave_overview.py only reads, and through Frappe's own filters: it has %s" % writes)
for name in ("overview", "year_end"):
    body = glue.split("\ndef %s(" % name)[1].split("\ndef ")[0] if "\ndef %s(" % name in glue else ""
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("leave_overview.%s is whitelisted, and reads" % name)
    if "seen = _reach()" not in body or body.index("seen = _reach()") > min(
            [body.index(needle) for needle in ("frappe.get_all(", "_people(", "frappe.db.get_value(") if needle in body]
            or [len(body)]):
        fail.append("leave_overview.%s asks who is asking before it reads anything" % name)
for needle, why in (
    ("seen = rules.reach(frappe.get_roles())", "what somebody sees is the rules' answer"),
    ("    if not seen:\n        frappe.throw(", "and nobody else opens it"),
    ("rows = [row for row in rows if row.name in own]", "their own people only, where that is their reach"),
    ('if not seen["why"]:\n            line.pop("leave_type", None)', "the leave type is HR's"),
    ('by_type=seen["why"])', "and so is the split by type"),
    ('if seen["why"] else None', "and the sick-leave list"),
    ('    if not seen["money"]:\n        frappe.throw(', "what leave is worth is management's"),
    ("for row in rows[:LIST_SHOWN]:", "a list is capped"),
    ('"today_count": len(found["today"])', "and its count is whole"),
    ("limit = leave_follow.most_off(", "the limit is the one applications are read against"),
    ('"custom_reported_back": ["!=", 1]', "not back is not marked back"),
    ("leave_accrual.earned_for(names, annual, on)", "the days earned are the accrual's own"),
    ("pay.monthly_gross(name, on)", "priced from the salary structure, as pay is"),
):
    if needle not in glue:
        fail.append("leave_overview.py: %s (%r not found)" % (why, needle))

page = json.loads(read("hrms_addon", "hrms_addon", "page", "leave_overview", "leave_overview.json"))
if (page.get("name"), page.get("standard"), page.get("module")) != ("leave-overview", "Yes", "HRMS Addon"):
    fail.append("the page is this app's own standard page, at /app/leave-overview")
if sorted(row["role"] for row in page.get("roles") or []) != sorted(R.PAGE_ROLES):
    fail.append("the page opens for the roles the rules name: %s" % (R.PAGE_ROLES,))
if not os.path.exists(os.path.join(APP, "page", "leave_overview", "__init__.py")):
    fail.append("the page has no __init__.py, so it is not packaged")
script = read("hrms_addon", "hrms_addon", "page", "leave_overview", "leave_overview.js")
calls = sorted(set(re.findall(r'xcall\(\s*"([\w.]+)"', script)))
same("the page asks the server two things", calls, ["hrms_addon.hrms_addon.leave_overview.overview",
                                                     "hrms_addon.hrms_addon.leave_overview.year_end"])
for needle, why in (
    ("if (found.sees.money) {", "the cost is asked for only by those who may see it"),
    ('if (found.sees.money) this.cost_band = this.band(', "and its row drawn only for them"),
    ("found.sick === null || found.sick === undefined", "no sick-leave list is drawn where none is given"),
    ('frappe.set_route("List", "Leave Application", filters);', "a figure opens the list behind it"),
    ('frappe.set_route("query-report", "Leave Accrual")', "the cost opens the accrual report"),
    ("HRA_LEAVE_STYLE", "its styles come with the page, not from a bundle"),
):
    if needle not in script:
        fail.append("leave_overview.js: %s (%r not found)" % (why, needle))
# every value the server sends as text goes through escape_html before it is drawn
for field in ("employee_name", "department", "reliever", "desk", "leave_type", "state"):
    for use in re.findall(r"\$\{([^}]*\brow\.%s\b[^}]*)\}" % field, script):
        if "esc(" not in use and "escape_html(" not in use:
            fail.append("leave_overview.js draws row.%s unescaped: ${%s}" % (field, use))
for var in re.findall(r"var\((--[\w-]+)\)", script):
    fail.append("leave_overview.js uses %s with nothing to fall back to" % var)
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for needle, why in (
    ('("Leave Overview", "leave-overview", PAGE),', "a card on the Leaves page"),
    ('("Leave Overview", "leave-overview", PAGE, None, "Home"),', "at the top of its sidebar"),
    ('"leave-overview": "chart-column"', "with an icon"),
):
    if needle not in nav:
        fail.append("navigation_rules.py: %s (%r not found)" % (why, needle))
print("glue, page and way in: reads only, refuses first, two calls, escaped, on the Leaves page")

print()
if fail:
    print("FAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("ALL LEAVE OVERVIEW CHECKS PASSED")
