"""Verify calibration by session and the insert-only calibration log
(calibration_rules.py, calibration.py), without a bench:

    python scripts/verify_talent_calibration.py

The talent blueprint, section 5.1, stage 4: "Calibrate | Manager peer group |
Adjust for consistency across plants; HR records movers", and the cycle's
"mid-year calibration". A session per plant or department of a review, its
lines (proposed box, agreed box, axis, reason, agreed), the spread against
the distribution guide, the moves applied in the background when it is
submitted; the board's drag written into the session or straight on; every
move kept in the log, never written over; the 9 x 9 movement between
reviews.
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


def check(label, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else "   -> %r" % (detail,)))
    if not ok:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def spec_of(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {row["fieldname"]: row for row in spec_of(name)["fields"]}


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


C = load("calibration_rules")
T = load("talent_rules")
print("loaded calibration_rules.py without Frappe")

# ── 1. A move ─────────────────────────────────────────────────────────
check("the axis a move changes", [C.axis_of(*pair) for pair in ((5, 6), (5, 8), (5, 9), (5, 5), (None, 5))]
      == ["Potential", "Performance", "Both", None, None])
check("the box's place: performance across, potential up", C.place(1) == (0, 0) and C.place(9) == (2, 2)
      and C.place(6) == (1, 2) and C.place(10) is None)
check("talent_rules places the boxes the same way", all(C.place(box) == T.box_place(box) for box in range(1, 10)))
check("a move across the columns is allowed now, with its reason (performance is calibrated too)",
      T.move_errors({"state": "In Calibration", "calibrating": "In Calibration", "from_box": 4, "to_box": 7,
                     "reason": "Plants scored differently"}) == [])
check("the bands a move to a box calibrates; back to its own ratings takes them off",
      T.calibrated_bands("Meeting", "Moderate", 9) == ("Exceeding", "High")
      and T.calibrated_bands("Meeting", "Moderate", 6) == (None, "High")
      and T.calibrated_bands("Meeting", "Moderate", 5) == (None, None))
check("the box is drawn from both calibrated bands",
      T.effective_performance("Meeting", "Exceeding") == "Exceeding" and T.effective_performance("Meeting") == "Meeting")

# ── 2. A session ──────────────────────────────────────────────────────
LINES = [{"placement": "TP-1", "employee_name": "Ann", "proposed_box": 5, "calibrated_box": 6, "reason": "Leads well",
          "agreed": 1},
         {"placement": "TP-2", "employee_name": "Ben", "proposed_box": 5, "calibrated_box": 8, "reason": "x",
          "agreed": 0},
         {"placement": "TP-3", "employee_name": "Cy", "proposed_box": 9, "calibrated_box": None},
         {"placement": "TP-4", "employee_name": "Di", "proposed_box": 2, "calibrated_box": 2}]
session = {"talent_review": "TR-2026", "checkpoint": "Year End", "lines": LINES, "participants": [{"user": "hr@x"}]}
check("a good session", C.session_errors(session) == [] and C.submit_errors(session) == [])
check("a move with no reason, a box out of the grid, a placement twice: refused",
      "Ann moves from box 5 to 6. Say why." in C.session_errors(dict(session, lines=[dict(LINES[0], reason=" ")]))
      and "Ann: a box is 1 to 9." in C.session_errors(dict(session, lines=[dict(LINES[0], calibrated_box=12)]))
      and "Ann is in the session twice." in C.session_errors(dict(session, lines=[LINES[0], LINES[0]])))
check("a session names its checkpoint and review", C.session_errors({"lines": []}) == [
    "A session belongs to a talent review.", "Say whether this is the mid-year or the year-end calibration."])
check("submitted with nobody in it, or nobody who took part: refused",
      "There is nobody in the session. Get the placements first." in C.submit_errors(dict(session, lines=[]))
      and "Say who took part in the session." in C.submit_errors(dict(session, participants=[])))
check("only the agreed moves are applied", C.to_apply(LINES) == [("TP-1", 6)])
check("where each line has the person", [C.line_box(row) for row in LINES] == [6, 8, 9, 2])
check("the moves a draft session shows on the board", C.pending(LINES) == {"TP-1": 6, "TP-2": 8})
check("a session's plant and department", C.in_scope({"branch": "Kawempe"}, {"branch": "Kawempe", "department": "X"})
      and not C.in_scope({"branch": "Kawempe", "department": "Y"}, {"branch": "Kawempe", "department": "X"})
      and C.in_scope({}, {"branch": "Namanve"}))

# ── 3. Against the guide ──────────────────────────────────────────────
guide = C.guide_of(T.GUIDE)
check("the guide's shares add up to a hundred, whatever HR typed",
      abs(sum(guide.values()) - 100) < 0.5 and C.guide_of({1: 1, 2: 1})[1] == 50.0 and C.guide_of({}) is None)
spread = C.distribution({5: 3, 9: 1}, {5: 2, 6: 1, 9: 1}, T.GUIDE, before={5: 1})
five = next(row for row in spread if row["box"] == 5)
check("each box: proposed and agreed, their shares, the guide and the gap to it, the review before",
      (five["proposed"], five["proposed_share"], five["calibrated"], five["calibrated_share"], five["guide"],
       five["variance"], five["last_share"]) == (3, 75.0, 2, 50.0, 35.0, 15.0, 100.0), five)
check("the boxes off the guide, the widest first", C.off_guide(spread, 5)[0] == (5, 15.0)
      and all(abs(variance) > 5 for _box, variance in C.off_guide(spread, 5)))
check("no guide: no variance", C.distribution({1: 1}, {1: 1})[0]["variance"] is None)

# ── 4. The log ────────────────────────────────────────────────────────
ENTRIES = [{"name": "L1", "placement": "TP-1", "event": "Moved", "moved_on": "2026-06-01 10:00", "to_box": 6},
           {"name": "L2", "placement": "TP-1", "event": "Applied", "moved_on": "2026-06-02 10:00", "to_box": 9},
           {"name": "L3", "placement": "TP-2", "event": "Moved", "moved_on": "2026-06-01 11:00", "to_box": 4},
           {"name": "L4", "placement": "TP-2", "event": "Reverted", "moved_on": "2026-06-03 09:00"},
           {"name": "L5", "placement": "TP-3", "event": "Proposed", "moved_on": "2026-06-04 09:00", "to_box": 2}]
latest = C.latest_moves(ENTRIES)
check("the latest move of each placement, newest first; one taken off drops out; a proposal is not a move",
      [(row["placement"], row["to_box"]) for row in latest] == [("TP-1", 9)], latest)
check("the log's events", set(C.EVENTS) == {"Proposed", "Applied", "Moved", "Reverted", "Not Agreed"})
check("the mid-year checkpoint comes due on its day, until a session is applied",
      C.checkpoint_due("2026-06-30", "2026-07-01", False) and not C.checkpoint_due("2026-06-30", "2026-07-01", True)
      and not C.checkpoint_due("2026-06-30", "2026-06-29", False) and not C.checkpoint_due(None, "2026-07-01", False))

# ── 5. Box to box ─────────────────────────────────────────────────────
grid = C.matrix([(5, 6), (5, 6), (9, 9), (None, 3), (4, None), (8, 2)])
check("a 9 x 9 grid with a row for the new and a column for those gone",
      grid[5][6] == 2 and grid[9][9] == 1 and grid[0][3] == 1 and grid[4][0] == 1 and grid[8][2] == 1
      and len(grid) == 10 and all(len(row) == 10 for row in grid.values()))
check("its summary: stayed, up, down, across, new, gone", C.matrix_summary(grid)
      == {"same": 1, "up": 2, "down": 1, "across": 0, "new": 1, "gone": 1})

# ── 6. The doctypes ───────────────────────────────────────────────────
session_spec = spec_of("Calibration Session")
session_fields = fields("Calibration Session")
check("a session: submittable, its review, checkpoint, plant and department, participants, lines, spread",
      session_spec.get("is_submittable") == 1
      and {"talent_review", "checkpoint", "branch", "department", "participants", "lines", "distribution", "moves",
           "agreed_moves", "off_guide", "job_log"} <= set(session_fields)
      and session_fields["lines"]["options"] == "Calibration Line"
      and session_fields["participants"]["options"] == "Calibration Participant"
      and session_fields["checkpoint"]["options"].split("\n") == ["Year End", "Mid-Year"])
line = fields("Calibration Line")
check("a line: the placement, the box proposed and agreed, the axis, the reason, agreed",
      {"placement", "proposed_box", "calibrated_box", "axis", "reason", "agreed"} <= set(line)
      and line["proposed_box"].get("read_only") and line["axis"].get("read_only"))
log_spec = spec_of("Talent Calibration Log")
log_fields = fields("Talent Calibration Log")
check("the log: its own doctype, never a child table rewritten on the review",
      not log_spec.get("istable") and {"talent_review", "calibration_session", "placement", "event", "source",
                                       "from_box", "to_box", "axis", "reason", "moved_by", "moved_on"}
      <= set(log_fields) and all(row.get("read_only") for name, row in log_fields.items()
                                 if row["fieldtype"] not in ("Section Break", "Column Break")
                                 and name != "naming_series"))
check("the log is written once: no role may write it, only System Manager deletes",
      not any(row.get("write") for row in log_spec["permissions"])
      and [row["role"] for row in log_spec["permissions"] if row.get("delete")] == ["System Manager"])
review = fields("Talent Review")
check("a review: several plants, the mid-year checkpoint, which calibrations are done; no movers table",
      review["plants"]["fieldtype"] == "Table MultiSelect" and review["plants"]["options"] == "Talent Review Plant"
      and {"mid_year_on", "mid_year_done", "year_end_done"} <= set(review) and "calibration" not in review)
placement = fields("Talent Placement")
check("the placement's performance can be calibrated too, at level 1, and names its session",
      placement["calibrated_performance"].get("permlevel") == 1
      and placement["calibration_session"]["options"] == "Calibration Session")

# ── 7. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "calibration.py")
BOARD = read("hrms_addon", "hrms_addon", "talent_board.py")
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
check("a log entry refuses to change once written", "if not doc.is_new():" in body_of(GLUE, "log_validate"))
check("submitted, the moves are applied in the background, each logged as applied",
      'talent_jobs.start("calibration"' in body_of(GLUE, "session_on_submit")
      and "context.each(" in body_of(GLUE, "apply_job") and "event=rules.APPLIED" in body_of(GLUE, "apply_job"))
check("a move not agreed is logged and left", "rules.NOT_AGREED" in body_of(GLUE, "apply_job"))
check("the review's checkpoint marked when a session is applied",
      '"mid_year_done" if doc.checkpoint == rules.MID_YEAR else "year_end_done"' in body_of(GLUE, "apply_job"))
check("a session refuses moves for placements no longer in calibration",
      "no longer in calibration" in body_of(GLUE, "session_before_submit"))
check("the board's drag goes into the draft session covering the placement, else straight on",
      "_session_for(placement)" in body_of(GLUE, "board_move") and "apply_move(placement, to_box, reason)"
      in body_of(GLUE, "board_move") and "rules.PROPOSED" in body_of(GLUE, "board_move"))
check("the board reads the movers from the log and the moves waiting in sessions",
      "calibration.movers(review" in BOARD and "calibration.pending(review)" in BOARD)
check("the review no longer rewrites a table on each move", "cycle.append(\"calibration\"" not in TALENT
      and "_record_calibration" not in TALENT)
check("a placement back with its line manager is taken off, and the log says so",
      "calibration.revert(doc)" in TALENT and "rules.REVERTED" in body_of(GLUE, "revert"))
check("the mid-year checkpoint told to HR on the day and a week on", "calibration.daily()" in body_of(TALENT, "daily")
      and "add_days(getdate(due), 7)" in body_of(GLUE, "daily"))
check("get_placements is whitelisted and checks the session may be written",
      re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef get_placements\(', GLUE) is not None
      and 'doc.check_permission("write")' in body_of(GLUE, "get_placements"))
check("the old movers moved into the log by a patch", "talent_calibration_to_log" in read("hrms_addon", "patches.txt"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_talent_calibration: OK")
