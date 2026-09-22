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
css = read("hrms_addon", "public", "css", "hrms_addon.bundle.css")
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
for part in ("floor", "cycle_totals", "per_day", "register", "exceptions", "machines"):
    if '"%s"' % part not in board:
        fail.append("the board answers in one call, and %s is part of it" % part)
if '"shown"' not in board or '"of"' not in board:
    fail.append("the register is capped so a screen stays a screen — and a cap that is not "
                "reported reads as though everybody was shown")
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
for code in A.CODES:
    if ".hra-code-%s" % code not in css:
        fail.append("register letter %s has no colour, so the grid reads as a wall of "
                    "letters" % code)
if "--hra-board-night" not in css:
    fail.append("the night shift is the one thing somebody looks for on the register, and it "
                "has to be visible at a glance")
used = set(re.findall(r"var\((--hra-[a-z0-9-]+)", css))
declared = set(re.findall(r"^\s*(--hra-[a-z0-9-]+)\s*:", css, re.M))
if used - declared:
    fail.append("a var() that resolves to nothing takes its whole declaration with it, "
                "silently: %s" % sorted(used - declared))
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
