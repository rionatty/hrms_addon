"""Verify the HR calendar without a bench:

    python scripts/verify_calendar.py

  1  the rules: the month, its days and weeks, what a leave cell shows,
     the counts under the days, what a training session shows as
  2  the glue reads fields that exist, and who sees what
  3  the page: its route, its roles, its own styles, what it calls
  4  a way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import datetime
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def fields_of(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    if not os.path.exists(path):
        hits = glob.glob(os.path.join(APPS_ROOT, "*", "*", "**", "doctype", folder, folder + ".json"), recursive=True)
        path = hits[0] if hits else None
    if not path:
        return None
    return {f["fieldname"] for f in json.load(open(path, encoding="utf-8")).get("fields", [])}


C = load("calendar_rules")
print("loaded calendar_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if C.month_of(None, None, "2026-09-24") != (2026, 9) or C.month_of("2027", "3", "2026-09-24") != (2027, 3):
    fail.append("the month asked for, else the one today is in")
try:
    C.month_of(2027, 13, "2026-09-24")
    fail.append("there is no thirteenth month")
except ValueError:
    pass
if C.month_window(2028, 2) != (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29)):
    fail.append("a leap February has 29 days: %s" % (C.month_window(2028, 2),))
if C.month_title(2027, 3) != "March 2027":
    fail.append("the month is named in full")
days = C.days(2027, 3, {"2027-03-08": "Women's Day"}, "2027-03-02")
if len(days) != 31 or days[0]["weekday"] != "Mon" or days[7]["holiday"] != "Women's Day" or days[0]["holiday"] \
        or not days[1]["today"] or days[0]["today"]:
    fail.append("a day knows its weekday, its holiday and whether it is today: %s" % days[:9])
weeks = C.weeks(days)
if len(weeks) != 5 or weeks[0][0]["day"] != 1 or weeks[4][2]["day"] != 31 or weeks[4][3:] != [None] * 4:
    fail.append("March 2027 starts on a Monday and ends on a Wednesday: five rows, the last padded")
sept = C.weeks(C.days(2026, 9))
if sept[0][0] is not None or sept[0][1]["day"] != 1 or sept[-1][2]["day"] != 30 or sept[-1][3] is not None:
    fail.append("September 2026 starts on a Tuesday: the first row is padded in front")
if C.weeks([]) != []:
    fail.append("no days, no weeks")
if C.common_holidays([{"a": "x", "b": "y"}, {"b": "y", "c": "z"}]) != {"b": "y"} or C.common_holidays([]) != {}:
    fail.append("the header shows the holidays everybody shown shares")
for docstatus, status, kind in ((0, "Open", C.APPLIED), (1, "Approved", C.APPROVED), (1, "Rejected", None),
                                (2, "Cancelled", None), (0, "Cancelled", None), ("1", "Approved", C.APPROVED)):
    if C.leave_kind(docstatus, status) != kind:
        fail.append("a leave with docstatus %r and status %r is %r on the calendar, got %r"
                    % (docstatus, status, kind, C.leave_kind(docstatus, status)))
if C.span_days("2027-02-27", "2027-03-02", "2027-03-01", "2027-03-31") != ["2027-03-01", "2027-03-02"]:
    fail.append("a leave that starts before the month is drawn from its first day")
if C.span_days(None, "2027-03-02", "2027-03-01", "2027-03-31") != []:
    fail.append("no dates, no days")
cells = C.leave_cells(
    [{"employee": "E", "from_date": "2027-03-03", "to_date": "2027-03-05", "kind": C.APPROVED, "label": "Annual",
      "link": ["Leave Application", "LA-1"]},
     {"employee": "E", "from_date": "2027-03-08", "to_date": "2027-03-09", "kind": C.APPLIED, "label": "Sick",
      "link": ["Leave Application", "LA-2"]},
     {"employee": "E", "from_date": "2027-03-10", "to_date": "2027-03-10", "kind": None}],
    [{"employee": "E", "planned_from": "2027-03-01", "planned_to": "2027-03-12", "label": "Planned",
      "link": ["Annual Leave Plan", "P-1"]}],
    {"E": {"2027-03-07": "Sunday", "2027-03-05": "Holiday", "2027-04-01": "Next month"}}, "2027-03-01", "2027-03-31")
mine = cells["E"]
got = {day: mine.get(day, {}).get("kind") for day in ("2027-03-01", "2027-03-03", "2027-03-05", "2027-03-07",
                                                       "2027-03-08", "2027-03-10", "2027-03-12", "2027-03-13",
                                                       "2027-04-01")}
if got != {"2027-03-01": C.PLANNED, "2027-03-03": C.APPROVED, "2027-03-05": C.HOLIDAY, "2027-03-07": C.HOLIDAY,
           "2027-03-08": C.APPLIED, "2027-03-10": C.PLANNED, "2027-03-12": C.PLANNED, "2027-03-13": None,
           "2027-04-01": None}:
    fail.append("a holiday over approved leave, approved over applied for, applied for over planned; nothing "
                "outside the month: %s" % got)
if mine["2027-03-03"]["link"] != ["Leave Application", "LA-1"] or mine["2027-03-01"]["link"] != ["Annual Leave Plan", "P-1"]:
    fail.append("a cell opens what it shows")
overlap = C.leave_cells(
    [{"employee": "E", "from_date": "2027-03-03", "to_date": "2027-03-05", "kind": C.APPROVED, "label": "Annual"},
     {"employee": "E", "from_date": "2027-03-05", "to_date": "2027-03-06", "kind": C.APPLIED, "label": "Sick"}],
    [], {}, "2027-03-01", "2027-03-31")["E"]
if (overlap["2027-03-05"]["kind"], overlap["2027-03-06"]["kind"]) != (C.APPROVED, C.APPLIED):
    fail.append("on a day with leave both approved and applied for, the approved one shows, whichever came last")
counts = C.off_counts(cells, C.days(2027, 3))
if (counts["off"]["2027-03-03"], counts["off"]["2027-03-05"], counts["off"]["2027-03-08"], counts["planned"]["2027-03-01"],
        counts["planned"]["2027-03-03"]) != (1, 0, 1, 1, 0):
    fail.append("off counts approved and applied for; planned counts the rest; a holiday counts nobody: %s" % counts)
if not C.too_many(2, 1) or C.too_many(1, 1) or C.too_many(5, 0) or C.too_many(5, None):
    fail.append("a day is over the plan's Most Off at Once when more than it are off; no limit, never")
for event_status, docstatus, status in (("Scheduled", 0, C.SCHEDULED), ("Scheduled", 1, C.SCHEDULED),
                                        ("Completed", 1, C.COMPLETED), ("Cancelled", 1, None), ("Scheduled", 2, None)):
    if C.session_status(event_status, docstatus) != status:
        fail.append("a %s event with docstatus %s shows as %r" % (event_status, docstatus, status))
for given, shown in (("2027-03-10 07:00:00", "07:00"), ("7:00:00", "07:00"), (datetime.time(14, 30), "14:30"),
                     (datetime.timedelta(hours=9), "09:00"), (None, ""), ("", ""),
                     (datetime.datetime(2027, 3, 10, 7, 5), "07:05"), ("2027-03-10T16:00:00", "16:00")):
    if C.clock(given) != shown:
        fail.append("the hour as the form sends it, as the database keeps it or as Python has it: %r shows %r, "
                    "not %r" % (given, C.clock(given), shown))
print("the rules: the month, its days and weeks, the cells, the counts, the sessions")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "calendar_board.py")
for doctype, wanted in (
    ("Leave Application", ("employee", "from_date", "to_date", "leave_type", "status")),
    ("Training Event", ("event_name", "course", "event_status", "location", "trainer_name", "start_time", "end_time")),
    ("Training Event Employee", ("employee", "employee_name", "department")),
    ("Holiday", ("holiday_date", "description", "weekly_off")),
    ("Company", ("default_holiday_list",)),
    ("Employee", ("employee_name", "department", "designation", "holiday_list", "company", "branch", "status")),
    ("Annual Leave Plan", ("year", "branch", "department", "most_off")),
    ("Annual Leave Plan Employee", ("employee", "planned_from", "planned_to")),
    ("Monthly Training Schedule", ("month", "year")),
    ("Training Schedule Line", ("course", "training_date", "start_time", "end_time", "venue", "trainer",
                                "department", "target_group", "training_event")),
    ("Training Calendar Entry", ("course", "trainer", "target_group", "section", "planned_month", "planned_year",
                                 "scheduled")),
):
    have = fields_of(doctype)
    if have is None:
        fail.append("%s is not to be found" % doctype)
        continue
    missing = [field for field in wanted if field not in have]
    if missing:
        fail.append("the calendar reads %s of %s, which it has not got" % (missing, doctype))
if "own = leave.own_place(frappe.session.user)" not in glue:
    fail.append("who sees what follows the leave plan: HR, heads of department and supervisors everything, "
                "an employee their own plant and department")
if "@frappe.whitelist()\ndef month(" not in glue:
    fail.append("the page has to be able to call it")
if "OPENS_TO & set(frappe.get_roles())" not in glue:
    fail.append("Training Event is HR's to read; the page's own roles gate the call")
people_body = glue.split("def _people(")[1].split(chr(10) + "def ")[0]
if "PEOPLE_LIMIT" not in people_body:
    fail.append("the roster is capped, and the page says so")
if "rules.span_days(event.start_time, event.end_time" not in glue:
    fail.append("a training that runs over days is a chip on each of them")
if 'filters["department"] = department' not in glue.split("def _unbooked(")[1].split(chr(10) + "def ")[0]:
    fail.append("a planned line is narrowed to its department like a booked session is")
if "rules.session_status(" not in glue or "rules.leave_kind(" not in glue or "rules.leave_cells(" not in glue:
    fail.append("what a cell or a chip shows comes from the rules")
print("the glue: fields that exist, one rule for who sees what, the rules deciding what shows")

# ── 3. The page ───────────────────────────────────────────────────────
page_js = read("hrms_addon", "hrms_addon", "page", "hr_calendar", "hr_calendar.js")
page_json = json.loads(read("hrms_addon", "hrms_addon", "page", "hr_calendar", "hr_calendar.json"))
route = page_json["name"]
if route != "hr-calendar" or page_json.get("page_name") != route:
    fail.append("the page is hr-calendar")
if page_json.get("standard") != "Yes" or page_json.get("module") != "HRMS Addon":
    fail.append("the page ships with the app, so it is standard and in this module")
roles = {row["role"] for row in page_json.get("roles", [])}
if roles != {"HR User", "HR Manager", "Head of Department", "Supervisor", "Employee"}:
    fail.append("the calendar opens to HR, heads of department, supervisors and employees: %s" % sorted(roles))
for role in roles:
    if '"%s"' % role not in glue.split("OPENS_TO = ")[1].split(chr(10))[0]:
        fail.append("the call must open to everybody the page opens to (%s)" % role)
if 'frappe.pages["%s"]' % route not in page_js:
    fail.append("the script must register on the page's own name, or the page loads and nothing draws")
if "hrms_addon.hrms_addon.calendar_board.month" not in page_js:
    fail.append("and call the method that fills it")
if "escape_html" not in page_js:
    fail.append("names, courses and venues are typed by people and printed as HTML")
if "on_page_show" not in page_js:
    fail.append("coming back to the calendar should show what is true now")
loading = page_js.split("on_page_load = function")[1].split(chr(10) + "};")[0] \
    if "on_page_load = function" in page_js else ""
if "HRC_STYLE" not in page_js or "hrc_style()" not in loading:
    fail.append("the calendar must put its own styles on the head as it loads (see attendance_board.js)")
css = page_js.split("const HRC_STYLE = `")[1].split("`;")[0] if "const HRC_STYLE = `" in page_js else ""
bundle = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
if ".hrc-" in bundle:
    fail.append("and they must be in ONE place, or the two copies will drift")
for kind in C.KINDS:
    if ".hrc-roster td.hrc-%s" % kind not in css:
        fail.append("a %s cell has no colour in the roster" % kind)
for status in (C.SCHEDULED, C.COMPLETED, C.PLANNED_SESSION):
    if "hrc-chip-%s" % status not in css:
        fail.append("a %s session has no look on the wall" % status)
if "hrc-bad" not in css or "hrc-bad" not in page_js.split("const HRC_STYLE")[0] + page_js.split("`;", 1)[1]:
    fail.append("a day with more off than the plan allows is marked")
used = set(re.findall(r"var\((--hrc-[a-z0-9-]+)", css))
mine = set(re.findall(r"^\s*(--hrc-[a-z0-9-]+)\s*:", css, re.M))
if used - mine:
    fail.append("a var() that resolves to nothing takes its whole declaration with it: %s" % sorted(used - mine))
borrowed = re.findall(r"var\((--hra-[a-z0-9-]+)(\s*,[^)]*)?\)", css)
bare = sorted({name for name, fallback in borrowed if not fallback})
if bare:
    fail.append("every theme colour the calendar borrows needs a fallback: %s" % bare)
for needle, why in (
    ("add_inner_button", "the month is walked with Previous and Next"),
    ('fieldname: "everyone"', "the whole roster is one tick away"),
    ("frappe.ui.Dialog", "a session opens to show its people before the event is opened"),
    ("data-doctype", "a leave cell opens what it shows"),
    ("hrc-planned-strip\" ", ""),
):
    if why and needle not in page_js:
        fail.append(why)
if "HRC_MARKS" not in page_js:
    fail.append("a cell carries a letter as well as a colour, for those who print it")
if "if (!data.people.length) {" not in page_js or "No leave this month" not in page_js:
    fail.append("an empty roster says so instead of drawing an empty table")
print("the page: its own route, its own roles, its own styles, and it draws what it is given")

# ── 4. A way in ───────────────────────────────────────────────────────
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if nav.count('"hr-calendar", PAGE') < 4:
    fail.append("the calendar needs a way in from the leave page and the training card, and from both sidebars")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "hr-calendar" not in carded or "hr-calendar" not in sidebarred:
    fail.append("the calendar is not on a card or not in a sidebar")
print("a way in from the leave page and the training card")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CALENDAR CHECKS PASSED")
