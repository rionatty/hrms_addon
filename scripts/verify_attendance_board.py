"""Verify the attendance board, without a bench:

    python scripts/verify_attendance_board.py

The board is LPL/HR/07 on screen — the register Luuka already reads,
ruled the 26th to the 25th and filled from the punches — with the state
of the floor above it and the things that need a person below.

  1  the reading: machines, who is inside, how full a day was
  2  the glue: one call, every read, nothing written
  3  it builds on what is already there rather than deciding again
  4  the page: the route, the roles, and what it calls
  5  the letters keep their colours, and the board has a way in
  6  a day the clock saw is on the register before anybody marks it
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


B = load("board_rules")
A = load("attendance_rules")
print("loaded board_rules.py without Frappe")

glue = read("hrms_addon", "hrms_addon", "attendance_board.py")
page_js = read("hrms_addon", "hrms_addon", "page", "attendance_board", "attendance_board.js")
page_json = json.loads(read("hrms_addon", "hrms_addon", "page", "attendance_board",
                            "attendance_board.json"))
bundle = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
# the board's styles travel with the page, not in the bundle: the bundle
# only reaches a browser after `bench build`, and the board shipped once
# looking like a list of words because of exactly that
css = page_js.split("HRA_BOARD_STYLE = ")[1].split(chr(96) + ";")[0] \
    if "HRA_BOARD_STYLE = " in page_js else ""
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")

# ── 1. The reading ────────────────────────────────────────────────────
NOW = "2026-09-22 14:00:00"
for last_seen, expected, why in (
    ("2026-09-22 13:50:00", B.HEALTHY, "a machine that punched ten minutes ago is fine"),
    ("2026-09-22 11:00:00", B.QUIET, "three hours could be the gap between shifts"),
    ("2026-09-21 18:00:00", B.SILENT, "a whole day of nothing is somebody's job to look at"),
    (None, B.NEVER, "and one that has never sent a punch has not been set up"),
):
    if B.machine_health(last_seen, NOW) != expected:
        fail.append("machine_health(%s) should be %s: %s" % (last_seen, expected, why))

# who is inside: the LAST reading decides, whatever day it fell on
readings = [
    {"employee": "A", "time": "2026-09-22 07:00:00", "log_type": "IN"},
    {"employee": "A", "time": "2026-09-22 12:00:00", "log_type": "OUT"},
    {"employee": "B", "time": "2026-09-21 19:00:00", "log_type": "IN"},
]
inside = B.inside_now(readings)
if sorted(inside) != ["B"]:
    fail.append("inside_now must read the last punch of each person, not the first: a night "
                "shift starts on one day and ends on the next, and somebody who clocked out "
                "at noon is not inside")
if not B.inside_now([{"employee": "C", "time": "2026-09-22 06:00:00", "log_type": "in"}]):
    fail.append("and IN is IN whatever case the machine wrote it in")

# Luuka's twelve-hour shift, with two of them overtime
for hours, expected in ((4, B.ON_SHIFT), (10, B.INTO_OVERTIME), (11.9, B.INTO_OVERTIME),
                        (12, B.OVER_A_SHIFT), (19, B.OVER_A_SHIFT)):
    if B.standing_of(hours) != expected:
        fail.append("%sh on the floor is %s: the shift is twelve hours with two of them "
                    "overtime, so the tenth hour is the line" % (hours, expected))
if B.OVERTIME_AFTER_HOURS != A.STANDARD_HOURS or B.FULL_SHIFT_HOURS != A.FULL_SHIFT_HOURS:
    fail.append("the board and the register must agree about how long a shift is")

tally = B.floor_tally([{"night": True, "hours": 19}, {"night": False, "hours": 3},
                       {"night": False, "hours": 10.5}])
if tally != {"inside": 3, "day": 2, "night": 1, "into_overtime": 2, "over_a_shift": 1}:
    fail.append("the band across the top counts inside, day, night, and how many have gone "
                "past their hours: %s" % tally)
if [seat["branch"] for seat in B.by_branch([{"branch": "A"}, {"branch": "B"}, {"branch": "B"}])] \
        != ["B", "A"]:
    fail.append("the plants are listed busiest first")
if B.by_branch([{"branch": None}])[0]["branch"] != "Unplaced":
    fail.append("and somebody whose plant is not set is shown, not dropped")

if B.rate(9, 10) != 0.9 or B.band(0.9) != B.THIN:
    fail.append("how full a day was, and which band it falls in")
if B.rate(5, 0) is not None or B.band(None) is not None:
    fail.append("a day nobody was expected is not an empty day, it is not a working day")
if B.progress(A.cycle_days(2026, 9), "2026-09-12")["day"] != 18:
    fail.append("how far through the cycle today is, counted from the 26th")
if B.progress([], "2026-09-12")["of"] != 0:
    fail.append("and a cycle with no days does not divide by nothing")
if B.worked_and_overtime(["M", "M", "N", "A", "WO"]) != {"worked": 3, "overtime": 6.0}:
    fail.append("three shifts worked carry their two hours of overtime each")
# each day's own shift says what overtime it carries
if B.worked_and_overtime(["M", "M", "N", "A", "WO"], overtime_by_day=[0, 2, 4, 2, 2]) != {"worked": 3, "overtime": 6.0} \
        or B.worked_and_overtime(["M", "A"], overtime_by_day=[0.0, 2.0]) != {"worked": 1, "overtime": 0.0} \
        or B.worked_and_overtime(["M", "M"], overtime_by_day=[None]) != {"worked": 2, "overtime": 0.0}:
    fail.append("only the days worked carry overtime, each what its own shift says")
if B.standing_of(8.5, 8, 9) != B.INTO_OVERTIME or B.standing_of(9, 8, 9) != B.OVER_A_SHIFT \
        or B.standing_of(7.9, 8, 9) != B.ON_SHIFT:
    fail.append("somebody is into overtime past their own shift's standard hours")
judged = B.floor_tally([{"night": False, "hours": 9, "standing": B.OVER_A_SHIFT},
                        {"night": False, "hours": 11, "standing": B.ON_SHIFT}])
if (judged["into_overtime"], judged["over_a_shift"]) != (1, 1):
    fail.append("the band counts each person as their own shift judged them: %s" % judged)
# ── 1b. One line per plant ────────────────────────────────────────────
# Luuka's plants are run by their own people — each has its own HODs,
# supervisors and HR Officer — so attendance is a question with one
# answer per plant, and a plant must never be shown another's problems.
LINES = [
    {"branch": "Kawempe", "codes": ["M", "M", "A"]},
    {"branch": "Kawempe", "codes": ["N", "N", "N"]},
    {"branch": "Luuka", "codes": ["M", "A", "A"]},
]
seats = {seat["branch"]: seat for seat in B.plants(
    LINES,
    inside=[{"branch": "Kawempe", "night": True}],
    machines=[{"branch": "Kawempe", "health": B.HEALTHY},
              {"branch": "Luuka", "health": B.SILENT},
              {"branch": None, "health": B.NEVER}])}
if sorted(seats) != ["Kawempe", "Luuka"]:
    fail.append("a terminal nobody has placed must not invent a plant with no people in "
                "it — it is already its own line under what needs a person: %s" % sorted(seats))
if seats["Kawempe"]["worked"] != 5 or seats["Kawempe"]["night"] != 3:
    fail.append("each plant counts its own shifts and its own nights: %s" % seats["Kawempe"])
if seats["Kawempe"]["inside"] != 1 or seats["Kawempe"]["inside_night"] != 1:
    fail.append("and who is inside it this minute")
if seats["Luuka"]["machines_watch"] != 1 or seats["Kawempe"]["machines_watch"] != 0:
    fail.append("a machine to look at belongs to the plant it stands in, and to no other")
order = [seat["branch"] for seat in B.plants(LINES)]
if order[0] != "Luuka":
    fail.append("the plant in trouble comes first: a board sorted alphabetically hides the "
                "one that needs somebody today (%s)" % order)
if B.plants([{"branch": "Kawempe", "codes": []}])[0]["rate"] is not None:
    fail.append("a plant nobody worked at has no turnout, rather than nought per cent")
print("the reading: machines, who is inside, the shift, and how full a day was")

# ── 2. The glue: every read, nothing written ──────────────────────────
for written, why in (
    (".insert(", "a board that wrote things while somebody looked at it would be a bad board"),
    (".save(", "marking attendance belongs to Frappe HR's auto-attendance"),
    ("db_set(", "and pushing a punch belongs to devices.py"),
    ("delete_doc", "and nothing on a board deletes"),
    ("frappe.db.sql", "the board asks through get_all, so permissions and filters apply"),
):
    if written in glue:
        fail.append("attendance_board.py must not %s: %s" % (written.strip("(."), why))
if "frappe.has_permission" not in glue:
    fail.append("somebody who may not read attendance may not read the board either")
if "@frappe.whitelist()" not in glue:
    fail.append("the page has to be able to call it")

board = glue.split("def board(")[1].split(chr(10) + "# ")[0]
for part in ("floor", "cycle_totals", "per_day", "plants", "register", "exceptions",
             "machines"):
    if '"%s"' % part not in board:
        fail.append("the board answers in one call, and %s is part of it" % part)
if '"shown"' not in board or '"of"' not in board:
    fail.append("the register is capped so a screen stays a screen — and a cap that is not "
                "reported reads as though everybody was shown")
if "lines[:limit]" not in board:
    fail.append("only the SHOWING of the register is capped: a footer that tallied the first "
                "page would quietly disagree with the register it sits under")

# the plant being looked at is the plant being answered about
for called, why in (
    ("_machines(now, branch)", "one plant's HR Officer cannot act on another plant's "
                               "machine, and a red dot they cannot act on is noise"),
    ("_exceptions(start, end, marked, machines, branch, list(people),",
     "nor fix another plant's failed punches"),
):
    if called not in board:
        fail.append("%s: %s" % (called, why))
scoped = glue.split("def _exceptions(")[1].split(chr(10) + "def ")[0]
if "if branch" not in scoped:
    fail.append("every count on the list must narrow with the plant, or somebody is told to "
                "go and fix something that is not theirs")
opening = glue.split("def _open_days(")[1].split(chr(10) + "def ")[0]
if "employees" not in opening:
    fail.append("and an open day belongs to the plant whose people left it open")
if "def board(cycle=None, branch=None, department=None, limit=None, employee=None):" not in glue \
        or "people = _people(start, end, branch, department, employee)" not in board \
        or '    if employee:\n        filters["name"] = employee\n' not in glue:
    fail.append("the board can be narrowed to one employee: 300 of 2018 people cannot be scrolled to")
if "    if employee and not branch and employee in people:\n        branch = people[employee].branch\n" not in board:
    fail.append("one person is looked at in their own plant, not beside every plant's machines")
if '"nights_short": [] if employee else ' not in board:
    fail.append("a plant can be short of a night shift; one person is not to be told so")
for needle, why in (
    ('fieldname: "employee",\n\t\t\toptions: "Employee",', "the page has an Employee filter"),
    ("employee: this.employee ? this.employee.get_value() : null,", "and asks the board for the one picked"),
    ("Filter by plant, department or employee to see the rest.", "and says so where the register is cut"),
    ("this.ask_again = true;", "a filter changed while the board is being read is read next, not lost"),
):
    if needle not in page_js:
        fail.append(why)
print("the glue: one call fills the board, and every one of its reads is a read")

if "    attendance.only_hr()\n    if not frappe.has_permission(ATTENDANCE, \"read\"):" not in glue \
        or glue.count("attendance.only_hr()") != 2:
    fail.append("the board and its filters ask who is asking: every employee can read Attendance, their own")
if "punch_without_shift" not in B.EXCEPTION_KINDS:
    fail.append("somebody clocking with no shift is never marked, and the board must say so")
if not B.silent_since("2026-10-10 08:00:00", "2026-10-12 09:00:00") or B.silent_since("2026-10-11 08:00:00", "2026-10-12 09:00:00") \
        or B.silent_since(None, "2026-10-12 09:00:00"):
    fail.append("a machine silent a day and a half is told about; a rest day's silence, or one never heard from, is not")
for needle, why in (
    ('"punch_without_shift": _clocking_with_no_shift(now_datetime(), everybody),', "the people clocking on no shift are counted"),
    ('"shift": ["is", "not set"]},\n        fields=["employee"])', "from the punches Frappe HR could place in no shift"),
    ('"punch_without_shift": {"doctype": CHECKIN, "filters": {"shift": ["is", "not set"]}},', "and the line leads to them"),
):
    if needle not in glue:
        fail.append("attendance_board.py: %s (%r not found)" % (why, needle))
drivers = read("hrms_addon", "hrms_addon", "devices.py")
for needle, why in (
    ("board_rules.silent_since(seen, now)", "a silent machine is judged by the board's own rule"),
    ("people.hr_officers(machine.branch)", "and told to its own plant's HR"),
    ("        tell_silent_machines()\n", "every day"),
):
    if needle not in drivers:
        fail.append("devices.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("shift_hours = attendance.all_shift_hours()", "the board reads each shift's hours once"),
    ('attendance.shift_hours_of(shift, shift_hours or {})["overtime"]', "a day carries its own shift's overtime"),
    ('rules.standing_of(hours, theirs["standard"], theirs["full"])', "and overtime on the floor is by the person's shift"),
):
    if needle not in read("hrms_addon", "hrms_addon", "attendance_board.py"):
        fail.append("attendance_board.py: %s (%r not found)" % (why, needle))

# ── 3. Built on what is already there ─────────────────────────────────
if "register.register_code(" not in glue:
    fail.append("what a day's cell says is attendance_rules.register_code — deciding it again "
                "here is how two answers to the same question start")
if "attendance._off_duty_between(" not in glue:
    fail.append("attendance.py already reads the approved off-duty days; reading them again "
                "would mean two places to get LPL/HR/25's dates wrong")
if "register.tallies(" not in glue:
    fail.append("the footer of LPL/HR/07 is attendance_rules.tallies")
if "register.cycle_window(" not in glue or "register.cycle_days(" not in glue:
    fail.append("and the 26th-to-25th cycle is theirs too")
for code in A.CODES:
    if re.search(r'["\']%s["\']\s*(?:==|!=)' % code, glue):
        fail.append("the board compares a register letter itself (%s): the letters are "
                    "attendance_rules' business" % code)
print("built on the register that is already there, not beside it")

# ── 4. The page ───────────────────────────────────────────────────────
route = page_json["name"]
if page_json.get("standard") != "Yes" or page_json.get("module") != "HRMS Addon":
    fail.append("the page ships with the app, so it is standard and in this module")
if not page_json.get("roles"):
    fail.append("a page with no roles is a page everybody can open")
if 'frappe.pages["%s"]' % route not in page_js:
    fail.append("the script must register on the page's own name (%s), or the page loads "
                "and nothing draws" % route)
if "hrms_addon.hrms_addon.attendance_board.board" not in page_js:
    fail.append("and call the method that fills it")
if "escape_html" not in page_js:
    fail.append("employee names and plant names are typed by people and printed as HTML")
if "on_page_show" not in page_js:
    fail.append("coming back to the board should show what is true now, not what was true "
                "when it was last opened")
if "clearInterval" not in page_js:
    fail.append("a board that refreshes itself must be able to stop")
print("the page: its own route, its own roles, and it draws what it is given")

# ── 5. The letters, and a way in ──────────────────────────────────────
# the call site, not just the function: a checker satisfied by the
# definition would pass with nothing ever calling it
loading = page_js.split("on_page_load = function")[1].split(chr(10) + "};")[0] \
    if "on_page_load = function" in page_js else ""
if "HRA_BOARD_STYLE" not in page_js or "hra_board_style()" not in loading:
    fail.append("the board must put its own styles on the head as it loads: "
                "hrms_addon.bundle.css needs `bench build` to reach a browser, and a page "
                "whose whole layout waits on a build step ships as a list of words when the "
                "build is skipped or an old bundle is cached")
if ".hra-band" in bundle or ".hra-register" in bundle:
    fail.append("and they must be in ONE place, or the two copies will drift")
for code in A.CODES:
    # the CELL, not just the legend: a letter that is only coloured in the
    # key leaves the grid a wall of letters, which is what the register is
    # read instead of
    if "td.hra-code-%s" % code not in css:
        fail.append("register letter %s has no colour in the grid itself" % code)
    if "i.hra-code-%s" % code not in css:
        fail.append("letter %s has no colour in the key that says what it means" % code)
if "--hra-board-night" not in css:
    fail.append("the night shift is the one thing somebody looks for on the register, and it "
                "has to be visible at a glance")
used = set(re.findall(r"var\((--hra-[a-z0-9-]+)", css))
mine = set(re.findall(r"^\s*(--hra-[a-z0-9-]+)\s*:", css, re.M))
declared = mine | set(re.findall(r"^\s*(--hra-[a-z0-9-]+)\s*:", bundle, re.M))
if used - declared:
    fail.append("a var() that resolves to nothing takes its whole declaration with it, "
                "silently: %s" % sorted(used - declared))
if "--hra-board-" not in css:
    fail.append("the colours the board adds are its own, and are declared beside it")
# the theme's colours live in the bundle, which the board no longer waits
# for; without a fallback a theme that has not loaded costs the whole
# declaration rather than just the colour
borrowed = re.findall(r"var\((--hra-[a-z0-9-]+)(\s*,[^)]*)?\)", css)
bare = sorted({name for name, fallback in borrowed if not fallback and name not in mine})
if bare:
    fail.append("every theme colour the board reads needs a fallback, or a theme that has "
                "not loaded takes the layout with it: %s" % bare)
if 'PAGE = "Page"' not in nav:
    fail.append("a page is a kind of thing a workspace can link to")
if '"attendance-board", PAGE' not in nav:
    fail.append("the board needs a way in from the attendance page, or nobody will find it")
if nav.count('"attendance-board"') < 2:
    fail.append("and one from the sidebar as well, which is where people look")
print("the letters keep their colours, and the board has a way in")

# ── 6. A day the clock saw ────────────────────────────────────────────
# Luuka, 22 Oct 2026: the register was blank for a whole cycle, "present
# is not marked here", because it showed only what Frappe HR had marked.
# A present day comes from the punches for those who clock in and from
# the upload for those who do not, so a day the clock saw is on the
# register at once, lighter until it is marked.
S = load("shift_rules")


def days_of(punches, who="E1"):
    return {str(day): shift for day, shift in (B.clocked_days(punches).get(who) or {}).items()}


night = [{"employee": "E1", "time": "2026-10-01 19:02:00", "shift": None},
         {"employee": "E1", "time": "2026-10-02 07:05:00", "shift": None},
         {"employee": "E1", "time": "2026-10-02 19:01:00", "shift": None},
         {"employee": "E1", "time": "2026-10-03 06:58:00", "shift": None}]
if days_of(night) != {"2026-10-01": None, "2026-10-02": None}:
    fail.append("a night shift's clock-out the next morning is the night before, not a day of its own: %s"
                % days_of(night))
if days_of(list(reversed(night))) != days_of(night):
    fail.append("the punches are read in time order whatever order they come in")
placed = [{"employee": "E1", "time": "2026-10-02 06:40:00", "shift": "Night Shift",
           "shift_start": "2026-10-01 19:00:00"}]
if days_of(placed) != {"2026-10-01": "Night Shift"}:
    fail.append("a punch Frappe HR placed in a shift belongs to the day that shift started, which is the "
                "day Frappe HR marks: %s" % days_of(placed))
late_out = [{"employee": "E1", "time": "2026-10-01 18:55:00", "shift": "Night Shift",
             "shift_start": "2026-10-01 19:00:00"},
            {"employee": "E1", "time": "2026-10-02 11:30:00", "shift": None}]
if days_of(late_out) != {"2026-10-01": "Night Shift"}:
    fail.append("a clock-out after the shift's own window is still that shift's, not a new day: %s"
                % days_of(late_out))
first_unplaced = [{"employee": "E1", "time": "2026-10-05 06:30:00", "shift": None},
                  {"employee": "E1", "time": "2026-10-05 07:01:00", "shift": "Day Shift",
                   "shift_start": "2026-10-05 07:00:00"}]
if days_of(first_unplaced) != {"2026-10-05": "Day Shift"}:
    fail.append("the day's shift is the one any of its punches was placed in: %s" % days_of(first_unplaced))
two = [{"employee": "E1", "time": "2026-10-05 07:00:00"}, {"employee": "E2", "time": "2026-10-05 19:00:00"},
       {"employee": "E2", "time": "2026-10-06 07:00:00"}, {"employee": None, "time": "2026-10-07 07:00:00"},
       {"employee": "E1", "time": None}]
if sorted(B.clocked_days(two)) != ["E1", "E2"] or days_of(two, "E2") != {"2026-10-05": None}:
    fail.append("each person's turns are their own, and a punch with nobody or no time on it is no day")
if not (A.FULL_SHIFT_HOURS + 1 + max(S.CHECK_OUT_AFTER_MINUTES.values()) / 60.0 < B.TURN_HOURS < 24):
    fail.append("a turn is longer than the longest shift with its early clock-in and late clock-out, and "
                "shorter than a day, or the next day's shift would be folded into this one")
rows6 = [{"clock": ["2026-10-20", "2026-10-21", "2026-10-22"]}, {"clock": ["2026-10-01"]}, {}]
if B.unmarked_days(rows6, "2026-10-22") != 2:
    fail.append("a day the clock saw counts as missed once two days have passed, and not before, because "
                "Frappe HR marks a night shift the next morning: %s" % B.unmarked_days(rows6, "2026-10-22"))
kinds = {row["kind"]: row for row in B.EXCEPTIONS}
if kinds.get("clocked_not_marked", {}).get("severity") != B.HIGH:
    fail.append("days the clock saw that nobody has marked are a payroll problem, listed first among what "
                "needs a person")
for needle, why in (
    ("clocked = _clocked(start, end, list(people))", "the board reads what the machines saw"),
    ('"time": ["between", [add_days(start, -1), add_days(end, 1)]]},',
     "a day either side, because a night shift crosses midnight at both ends of the cycle"),
    ("seen = rules.clocked_days(punches)", "which day a punch belongs to is board_rules' to say"),
    ("came = not marked_day and day in seen", "a day somebody has marked is what they marked, whatever the clock saw"),
    ('"status": marked_day.status if marked_day else ("Present" if came else None),',
     "and an unmarked day the clock saw reads as present, through register_code like any other"),
    ("shift = (marked_day.shift if marked_day else seen.get(day)) or person.default_shift",
     "in the shift the punch was placed in, else the person's own"),
    ("clock=[index for index, day in enumerate(days) if getdate(day) in clock])",
     "the page is told which columns only the clock has seen"),
    ("unmarked=rules.unmarked_days(rows, getdate(now))",
     "and the missed days are counted from the register's own rows, so a plant is counted its own"),
    ('"clocked_not_marked": unmarked,', "they are on the list of what needs a person"),
    ('"attendance": ["is", "not set"], "skip_auto_attendance": 0,', "which leads to the punches nothing marked"),
):
    if needle not in glue:
        fail.append("attendance_board.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("td.hra-clock", "a day only the clock has seen is drawn lighter in the grid"),
    ("i.hra-clock", "and in the key"),
):
    if needle not in css:
        fail.append("attendance_board.js: %s (%r not found)" % (why, needle))
for needle, why in (
    ('const clock = new Set(row.clock || []);', "the cells the server says only the clock has seen"),
    ('hra-clock" data-clock="1" title="${unmarked}"', "are marked so, with a title saying what they are"),
    ('<i class="hra-code-M hra-clock">M</i> ${unmarked}</span>', "and the key says what the lighter letter means"),
    ('const unmarked = frappe.utils.escape_html(__("Clocked in, not marked"));', "in plain words"),
    ('frappe.set_route("List", "Employee Checkin", {', "and clicking one opens the punches, as there is nothing marked"),
):
    if needle not in page_js:
        fail.append("attendance_board.js: %s (%r not found)" % (why, needle))
print("a day the clock saw is on the register, lighter, until it is marked")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL ATTENDANCE BOARD CHECKS PASSED")
