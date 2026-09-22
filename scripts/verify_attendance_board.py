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
    ("_exceptions(start, end, marked, machines, branch)",
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
print("the glue: one call fills the board, and every one of its reads is a read")

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

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL ATTENDANCE BOARD CHECKS PASSED")
