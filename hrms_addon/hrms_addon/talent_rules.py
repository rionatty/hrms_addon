# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Talent management: the nine-box review, succession, and the graduate
trainee scheme.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_talent.py exercises them without a bench.

THE TWO AXES

Performance is not re-entered. It is the appraisal's own score out of a
hundred, from whichever of Luuka's two forms the employee is on, and it
falls into three bands. The line between Low and Meeting is the same sixty
the performance module puts a PIP below, so a person on a PIP is a person
in the bottom row — the two modules cannot disagree.

Potential is judged by the line manager on three things the literature and
Luuka's own council both use: whether they CAN (ability), whether they WANT
to (aspiration), and whether they are here for it (engagement). Each is
scored out of ten and they weigh the same, because no one at Luuka has
argued one of them matters more. Competency levels come across from the
appraisal as evidence for that judgement, not as a fourth score: a manager
reads them and rates, rather than the grid rating on their behalf.

THE GRID

    potential                                                  performance
                 Low (<60)          Meeting (60-79)    Exceeding (80+)
    High (80+)   3 Potential Gem    6 High Potential   9 Star
    Mod (60-79)  2 Inconsistent     5 Core Player      8 High Performer
    Low (<60)    1 Risk             4 Average          7 Trusted Pro

The three boxes on the right-hand column with potential to match — 6, 8 and
9 — are the succession pool and the people worth losing sleep over, so they
are the ones flight risk is watched on.
"""

import calendar
import datetime
import re

# ── The bands ─────────────────────────────────────────────────────────
LOW, MEETING, EXCEEDING = "Low", "Meeting", "Exceeding"
POTENTIAL_LOW, POTENTIAL_MODERATE, POTENTIAL_HIGH = "Low", "Moderate", "High"

# the same line the performance module puts a PIP below, and the same
# eighty the scorecard calls Very Good
MEETS_FROM = 60.0
EXCEEDS_FROM = 80.0

PERFORMANCE_BANDS = ((EXCEEDS_FROM, EXCEEDING), (MEETS_FROM, MEETING), (0.0, LOW))
POTENTIAL_BANDS = ((EXCEEDS_FROM, POTENTIAL_HIGH), (MEETS_FROM, POTENTIAL_MODERATE),
                   (0.0, POTENTIAL_LOW))

POTENTIAL_DIMENSIONS = ("ability", "aspiration", "engagement")
DIMENSION_OUT_OF = 10.0

# ── The grid ──────────────────────────────────────────────────────────
# (performance band, potential band) -> box
BOXES = {
    (LOW, POTENTIAL_LOW): {
        "box": 1, "name": "Risk", "colour": "Red",
        "action": "Exit, or move to work that fits",
        "decision": "Replacement"},
    (LOW, POTENTIAL_MODERATE): {
        "box": 2, "name": "Inconsistent Player", "colour": "Orange",
        "action": "Find out what is in the way, and coach",
        "decision": "Improve"},
    (LOW, POTENTIAL_HIGH): {
        "box": 3, "name": "Potential Gem", "colour": "Yellow",
        "action": "Develop, or move to a better fit",
        "decision": "Improve"},
    (MEETING, POTENTIAL_LOW): {
        "box": 4, "name": "Average Performer", "colour": "Orange",
        "action": "Lift performance in the role",
        "decision": "Improve"},
    (MEETING, POTENTIAL_MODERATE): {
        "box": 5, "name": "Core Player", "colour": "Yellow",
        "action": "Grow in the role",
        "decision": "Retain in Role"},
    (MEETING, POTENTIAL_HIGH): {
        "box": 6, "name": "High Potential", "colour": "Blue",
        "action": "Give a stretch assignment",
        "decision": "Succession Pipeline"},
    (EXCEEDING, POTENTIAL_LOW): {
        "box": 7, "name": "Trusted Professional", "colour": "Yellow",
        "action": "Keep, reward, and use as a teacher",
        "decision": "Retain in Role"},
    (EXCEEDING, POTENTIAL_MODERATE): {
        "box": 8, "name": "High Performer", "colour": "Blue",
        "action": "Develop for the next role",
        "decision": "Promotion"},
    (EXCEEDING, POTENTIAL_HIGH): {
        "box": 9, "name": "Star", "colour": "Green",
        "action": "Put in the succession pool, and keep",
        "decision": "Succession Pipeline"},
}
BOX_NAMES = tuple(BOXES[key]["name"] for key in sorted(BOXES, key=lambda k: BOXES[k]["box"]))
TOP_TALENT = (6, 8, 9)
# the board's three strips: the boxes worth keeping and growing, the middle
# of the grid, and the ones somebody has to act on
CORE = (3, 5, 7)
ATTENTION = (1, 2, 4)
# box -> (performance band, potential band)
BOX_AXES = {spec["box"]: key for key, spec in BOXES.items()}
DECISIONS = ("Succession Pipeline", "Promotion", "Replacement", "Retain in Role", "Improve")
COLOURS = ("Red", "Orange", "Yellow", "Blue", "Green")
PERFORMANCE_NAMES = (LOW, MEETING, EXCEEDING)
POTENTIAL_NAMES = (POTENTIAL_LOW, POTENTIAL_MODERATE, POTENTIAL_HIGH)


# ── The grid as HR keep it (blueprint section 3: "business rules must be
# configurable") ──────────────────────────────────────────────────────
# Performance Band and Potential Band hold where each band starts, Nine Box
# each cell's name, colour, action, decision and whether it is top talent,
# Talent Settings how ability, aspiration and engagement weigh and the
# trainee pass mark. The grid stays three by three: the band names and the
# box numbers are what everything else (the board, the reports, succession)
# is keyed on, so HR change what each means, not what there is.
def grid_from(performance=None, potential=None, boxes=None, settings=None):
    """The grid as kept, the built-in values for whatever is not.

    performance, potential: [{"name": band, "score_from": floor}], all three
    or none counts; boxes: [{"box", "box_name", "colour", "default_action",
    "suggested_decision", "top_talent"}]; settings: {"weight_ability",
    "weight_aspiration", "weight_engagement", "trainee_pass_mark"}.
    """
    settings = settings or {}
    kept = {int(_number(row.get("box"))): row for row in boxes or () if row.get("box") not in (None, "")}
    table = {}
    for key, spec in BOXES.items():
        row = kept.get(spec["box"])
        cell = dict(spec, top=spec["box"] in TOP_TALENT)
        if row:
            cell.update({"name": _text(row.get("box_name")) or spec["name"],
                         "colour": row.get("colour") if row.get("colour") in COLOURS else spec["colour"],
                         "action": _text(row.get("default_action")) or spec["action"],
                         "decision": row.get("suggested_decision") if row.get("suggested_decision") in DECISIONS
                         else spec["decision"],
                         "top": bool(int(_number(row.get("top_talent"))))})
        table[key] = cell
    weights = {name: (_number(settings.get("weight_" + name))
                      if settings.get("weight_" + name) not in (None, "") else 1.0)
               for name in POTENTIAL_DIMENSIONS}
    if not sum(weights.values()):
        weights = dict.fromkeys(POTENTIAL_DIMENSIONS, 1.0)
    pass_mark = settings.get("trainee_pass_mark")
    return {"performance_bands": _bands(performance, PERFORMANCE_BANDS),
            "potential_bands": _bands(potential, POTENTIAL_BANDS),
            "boxes": table, "top_talent": tuple(sorted(cell["box"] for cell in table.values() if cell["top"])),
            "weights": weights,
            "pass_mark": _number(pass_mark) if pass_mark not in (None, "") and _number(pass_mark) > 0 else PASS_MARK}


def _bands(rows, built_in):
    names = [name for _floor, name in built_in]
    kept = {row.get("name"): _number(row.get("score_from")) for row in rows or ()
            if row.get("name") in names and row.get("score_from") not in (None, "")}
    if set(kept) != set(names) or band_errors([(name, kept[name]) for name in reversed(names)]):
        return built_in
    return tuple(sorted(((kept[name], name) for name in names), key=lambda band: -band[0]))


def band_errors(bands):
    """Why a set of bands cannot stand. bands: [(name, where it starts)],
    lowest first. The lowest starts at nought and each starts above the one
    below it, under a hundred."""
    errors = []
    floors = [_number(floor) for _name, floor in bands]
    if floors and floors[0] != 0:
        errors.append("The lowest band starts at 0.")
    if any(later <= earlier for earlier, later in zip(floors, floors[1:])):
        errors.append("Each band starts above the one below it.")
    if any(floor < 0 or floor >= 100 for floor in floors):
        errors.append("A band starts at 0 or more, and under 100.")
    return errors


def band_ranges(bands):
    """[(name, from, up to)] lowest first, each up to where the next starts
    (the highest up to 100)."""
    ordered = sorted(bands, key=lambda band: _number(band[1]))
    return [(name, _number(floor), _number(ordered[index + 1][1]) if index + 1 < len(ordered) else 100.0)
            for index, (name, floor) in enumerate(ordered)]

# ── The programme ─────────────────────────────────────────────────────
PROGRAM_TYPES = ("Leadership Development", "Mentoring and Coaching",
                 "Learning and Development")
EFFECTIVENESS = ((10.0, "Highly Effective"), (5.0, "Effective"), (0.0, "Some Effect"),
                 (-1000.0, "No Effect"))

# ── Succession ────────────────────────────────────────────────────────
READY_NOW, READY_SOON, EMERGING, GAP = ("Ready Now", "Ready in 1-2 Years", "Emerging", "Gap")
READINESS = (READY_NOW, READY_SOON, EMERGING, GAP)
READINESS_RANK = {READY_NOW: 0, READY_SOON: 1, EMERGING: 2, GAP: 3}
RISK_LEVELS = ("High", "Medium", "Low")
COVERED, AT_RISK, POSITION_GAP = "Covered", "At Risk", "Gap"

# ── The graduate trainee ──────────────────────────────────────────────
RECRUITED, IN_INDUCTION, IN_ROTATION, UNDER_ASSESSMENT = (
    "Recruited", "In Induction", "In Rotation", "Under Assessment")
CONFIRMED, EXITED = "Confirmed", "Exited"
TRAINEE_STATES = (RECRUITED, IN_INDUCTION, IN_ROTATION, UNDER_ASSESSMENT, CONFIRMED, EXITED)
MILESTONE_RESULTS = ("Pass", "Final Pass", "Fail")
PASS_MARK = 60.0
# a trainee is employed from induction, on this employment type, so the
# milestone appraisals have somebody to appraise; confirmation changes it
TRAINEE_EMPLOYMENT = "Graduate Trainee"

# ── Linked with the appraisal (Luuka, 5 Oct 2026) ─────────────────────
# Luuka appraise each quarter (the Appraisal Plan of the year, Q1 to Q4),
# and each appraisal carries the year to date. LPL/HR/18 rates each factor
# 1 to 5; the scorecard scores each competency out of ten.
QUARTER_ORDER = ("Q1", "Q2", "Q3", "Q4")
FACTOR_OUT_OF = 5.0


# ── Reading the two axes ──────────────────────────────────────────────
def performance_band(score, grid=None):
    """The appraisal's own score, put in a band. Nothing is re-entered."""
    if score is None or score == "":
        return None
    bands = (grid or {}).get("performance_bands") or PERFORMANCE_BANDS
    return next(name for floor, name in bands if _number(score) >= floor)


def potential_score(assessment, grid=None):
    """Ability, aspiration and engagement, each out of ten, weighed as
    Talent Settings say (the same, by default), as a score out of a hundred.
    A dimension left blank is not counted, so a half-finished assessment
    does not read as a low one."""
    weights = (grid or {}).get("weights") or dict.fromkeys(POTENTIAL_DIMENSIONS, 1.0)
    given = [(_number(assessment.get(name)), _number(weights.get(name, 1.0))) for name in POTENTIAL_DIMENSIONS
             if assessment.get(name) not in (None, "")]
    weight = sum(share for _score, share in given)
    if not given or not weight:
        return None
    return round(sum(score * share for score, share in given) / weight * (100.0 / DIMENSION_OUT_OF), 2)


def potential_band(score, grid=None):
    if score is None or score == "":
        return None
    bands = (grid or {}).get("potential_bands") or POTENTIAL_BANDS
    return next(name for floor, name in bands if _number(score) >= floor)


def box_for(performance, potential, grid=None):
    """The one cell the two bands resolve to, as HR keep it."""
    found = ((grid or {}).get("boxes") or BOXES).get((performance, potential))
    return dict(found) if found else None


def is_top_talent(box, grid=None):
    return _number(box) in ((grid or {}).get("top_talent") or TOP_TALENT)


def competency_average(rows):
    """The competency levels that came across from the appraisal, averaged
    out of ten. Evidence for the manager's judgement, not a score in it."""
    given = [_number(row.get("level")) for row in rows or [] if row.get("level") not in (None, "")]
    if not given:
        return None
    return round(sum(given) / len(given), 2)


# ── What a placement must carry ───────────────────────────────────────
def placement_errors(facts):
    errors = []
    if not facts.get("employee"):
        errors.append("Say whose placement this is.")
    if not facts.get("talent_review"):
        errors.append("A placement belongs to a review cycle.")
    if facts.get("performance_score") in (None, ""):
        errors.append("There is no appraisal score for this employee in the cycle, so the "
                      "performance band cannot be read. Complete the appraisal first.")
    missing = [name for name in POTENTIAL_DIMENSIONS if facts.get(name) in (None, "")]
    if missing:
        errors.append("Rate the employee on %s out of ten." % _and(missing))
    for name in POTENTIAL_DIMENSIONS:
        value = facts.get(name)
        if value not in (None, "") and not 0 <= _number(value) <= DIMENSION_OUT_OF:
            errors.append("%s is rated out of ten." % name.title())
    if not _text(facts.get("rationale")):
        errors.append("Write the rationale for the placement. The council reads it, not the grid.")
    return errors


def calibration_errors(facts):
    """A box moved in calibration is a decision about a person, so it is
    signed for: who moved it, and why."""
    errors = []
    if facts.get("to_box") in (None, ""):
        errors.append("Say which box the placement moves to.")
    if facts.get("from_box") == facts.get("to_box"):
        errors.append("The placement is already in that box.")
    if not _text(facts.get("reason")):
        errors.append("Say why the placement moves. Calibration is recorded, not silent.")
    if not facts.get("moved_by"):
        errors.append("A move is made by somebody.")
    return errors


def movers(before, after):
    """Who moved in calibration: the placements whose box is not the box
    the manager submitted."""
    was = {row["placement"]: row.get("box") for row in before or []}
    out = []
    for row in after or []:
        name = row["placement"]
        if name in was and was[name] != row.get("box"):
            out.append({"placement": name, "employee": row.get("employee"),
                        "from_box": was[name], "to_box": row.get("box")})
    return out


# ── The programme and whether it worked ───────────────────────────────
def program_errors(facts):
    errors = []
    if not facts.get("employee"):
        errors.append("Say who is on the programme.")
    if facts.get("program_type") not in PROGRAM_TYPES:
        errors.append("Choose the programme: %s." % _and(PROGRAM_TYPES))
    if facts.get("program_type") == "Mentoring and Coaching" and not facts.get("mentor"):
        errors.append("Mentoring and coaching needs a mentor named.")
    if not facts.get("start_date"):
        errors.append("Say when the programme starts.")
    if facts.get("start_date") and facts.get("end_date") \
            and str(facts["end_date"]) < str(facts["start_date"]):
        errors.append("The programme cannot end before it starts.")
    if not (facts.get("actions") or []):
        errors.append("A programme is a list of things to be done. Add at least one action.")
    return errors


def review_errors(facts):
    """Step 2 of the chart: the HR Officer reviews the programme against
    what actually became of the employee."""
    errors = []
    if facts.get("score_after") in (None, ""):
        errors.append("There is no appraisal since the programme ended, so its effect cannot be "
                      "read yet.")
    if not _text(facts.get("outcome_notes")):
        errors.append("Write what came of the programme.")
    if facts.get("decision") and facts["decision"] not in DECISIONS:
        errors.append("The decision is one of: %s." % _and(DECISIONS))
    return errors


def movement(before, after):
    """What the appraisal score did across the programme."""
    if before in (None, "") or after in (None, ""):
        return None
    return round(_number(after) - _number(before), 2)


def effectiveness(before, after):
    """How much good it did, from the movement alone."""
    moved = movement(before, after)
    if moved is None:
        return None
    return next(name for floor, name in EFFECTIVENESS if moved >= floor)


# ── Succession ────────────────────────────────────────────────────────
def position_errors(facts):
    errors = []
    if not facts.get("designation"):
        errors.append("Say which role this is.")
    if not facts.get("company"):
        errors.append("Say which company the role sits in.")
    if facts.get("risk_level") and facts["risk_level"] not in RISK_LEVELS:
        errors.append("Risk is High, Medium or Low.")
    if facts.get("single_person_role") and not facts.get("incumbent"):
        errors.append("A single-person role is one person's. Name the incumbent.")
    seen = set()
    for row in facts.get("candidates") or []:
        if not row.get("employee"):
            errors.append("A successor without a name is not a successor.")
            continue
        if row["employee"] in seen:
            errors.append("%s is nominated twice." % (row.get("employee_name") or row["employee"]))
        seen.add(row["employee"])
        if row.get("employee") == facts.get("incumbent"):
            errors.append("The incumbent cannot succeed themselves.")
        if row.get("readiness") not in READINESS:
            errors.append("Give each successor a readiness: %s." % _and(READINESS))
    return errors


def bench_strength(candidates):
    """How deep the bench is, counted by readiness."""
    counts = dict.fromkeys(READINESS, 0)
    for row in candidates or []:
        if row.get("readiness") in counts:
            counts[row["readiness"]] += 1
    return counts


def coverage(candidates):
    """Whether the role is covered. Nobody ready now is not cover, whatever
    else is on the bench — a successor two years out is a plan, not a
    stand-in — so that reads as at risk, and an empty bench as a gap."""
    counts = bench_strength(candidates)
    if counts[READY_NOW]:
        return COVERED
    if counts[READY_SOON] or counts[EMERGING]:
        return AT_RISK
    return POSITION_GAP


def is_gap(candidates):
    return coverage(candidates) == POSITION_GAP


def development_needs(candidates):
    """What the bench needs before it is a bench: the named gaps of every
    successor who is not ready now."""
    out = []
    for row in candidates or []:
        if row.get("readiness") == READY_NOW:
            continue
        gaps = _text(row.get("development_needs"))
        if gaps:
            out.append({"employee": row.get("employee"),
                        "employee_name": row.get("employee_name"), "needs": gaps})
    return out


def readiness_order(candidates):
    """Successors, readiest first, so the coverage report reads down."""
    return sorted(candidates or [],
                  key=lambda row: (READINESS_RANK.get(row.get("readiness"), 9),
                                   str(row.get("employee_name") or row.get("employee") or "")))


# ── The graduate trainee ──────────────────────────────────────────────
def trainee_errors(facts):
    errors = []
    if not (facts.get("job_applicant") or facts.get("trainee_name")):
        errors.append("A trainee comes from a job applicant, or is at least named.")
    if not facts.get("cohort"):
        errors.append("Say which cohort the trainee is in.")
    if not facts.get("start_date"):
        errors.append("Say when the programme starts.")
    return errors


def induction_errors(facts):
    errors = []
    if not facts.get("mentor"):
        errors.append("Assign a mentor before the induction.")
    checklist = facts.get("checklist") or []
    if checklist and not all(row.get("done") for row in checklist):
        errors.append("Finish the onboarding checklist, or say why an item does not apply.")
    return errors


def rotation_errors(rotations):
    """Stints across plants and functions: each needs somewhere to be, a
    span, somebody to answer to, and something to achieve."""
    errors = []
    ordered = sorted(rotations or [], key=lambda row: str(row.get("from_date") or ""))
    previous = None
    for row in ordered:
        where = row.get("department") or row.get("plant") or "a stint"
        if not row.get("from_date") or not row.get("to_date"):
            errors.append("%s has no dates." % where)
            continue
        if str(row["to_date"]) < str(row["from_date"]):
            errors.append("%s ends before it starts." % where)
        if not row.get("supervisor"):
            errors.append("%s has no rotation supervisor." % where)
        if not _text(row.get("objectives")):
            errors.append("%s has no objectives. A rotation without them is a visit." % where)
        if previous and str(row["from_date"]) <= str(previous["to_date"]):
            errors.append("%s overlaps the stint before it. A trainee is in one place at a time."
                          % where)
        previous = row
    return errors


def milestone_errors(facts):
    errors = []
    if not facts.get("milestone"):
        errors.append("Say which milestone this is.")
    if not facts.get("due_on"):
        errors.append("Say when the milestone falls.")
    if facts.get("result") and facts["result"] not in MILESTONE_RESULTS:
        errors.append("A milestone is a Pass, a Final Pass or a Fail.")
    if facts.get("result") and facts.get("score") in (None, ""):
        errors.append("Record the score the milestone was judged on.")
    return errors


def confirmation_errors(facts):
    """Test case 20: a confirmed trainee stays an employee, on the
    employment type HR names for them; the graduate trainee one ends."""
    errors = []
    if not facts.get("employment_type"):
        errors.append("Say which employment type the trainee is confirmed on.")
    elif facts["employment_type"] == TRAINEE_EMPLOYMENT:
        errors.append("A confirmed trainee is no longer a graduate trainee. Choose the employment type "
                      "they are confirmed on.")
    return errors


def final_milestone(due_on, is_last, programme_ends=None):
    """Whether a milestone is the one that decides confirmation: the one
    due when the programme ends, or, where no end is set, the last one.
    Its pass is a Final Pass; an earlier milestone's pass sends the trainee
    back out on rotation."""
    if programme_ends and due_on:
        return str(due_on) >= str(programme_ends)
    return bool(is_last)


def milestone_outcome(score, final=False, pass_mark=None):
    """What a milestone score comes to, against the pass mark Talent
    Settings keep (60 by default)."""
    if score in (None, ""):
        return None
    if _number(score) < (_number(pass_mark) if pass_mark not in (None, "") and _number(pass_mark) > 0 else PASS_MARK):
        return "Fail"
    return "Final Pass" if final else "Pass"


# ── Where a development plan aims, and how people moved (batch 5) ─────
# A box's place on each axis: performance across (0 Low to 2 Exceeding),
# potential up (0 Low to 2 High).
def box_place(box):
    box = int(_number(box))
    if box not in BOX_AXES:
        return None
    return (box - 1) // 3, (box - 1) % 3


def target_box(box):
    """Where a development plan aims by default: the box one performance
    band up in the same potential row; the right-hand column keeps its box."""
    place = box_place(box)
    if place is None:
        return None
    return int(_number(box)) + 3 if place[0] < 2 else int(_number(box))


def target_reached(box, target):
    """Whether a box is at least the target on both axes."""
    now, aim = box_place(box), box_place(target)
    if now is None or aim is None:
        return False
    return now[0] >= aim[0] and now[1] >= aim[1]


UP, DOWN, ACROSS, SAME, NEW, OUT = "Up", "Down", "Across", "Same", "New", "Not Placed"


def box_movement(before, after):
    """How someone moved between two reviews: Up where neither axis fell
    and one rose, Down where neither rose and one fell, Across where one
    rose and the other fell; New with no earlier box, Not Placed with no
    later one."""
    was, now = box_place(before) if before not in (None, "") else None, \
        box_place(after) if after not in (None, "") else None
    if was is None and now is None:
        return None
    if was is None:
        return NEW
    if now is None:
        return OUT
    if was == now:
        return SAME
    if now[0] >= was[0] and now[1] >= was[1]:
        return UP
    if now[0] <= was[0] and now[1] <= was[1]:
        return DOWN
    return ACROSS


def readiness_for(box, levels):
    """The readiness a box suggests for a successor, from the Readiness
    Levels' "drawn from" boxes, the nearest first. levels: [(readiness,
    rank, [boxes])]. None where no level draws from that box."""
    box = int(_number(box)) if box not in (None, "") else None
    for readiness, _rank, boxes in sorted(levels or (), key=lambda level: _number(level[1])):
        if box is not None and box in [int(_number(item)) for item in boxes or ()]:
            return readiness
    return None


def next_trainee_state(state, result):
    """Where a milestone leaves the trainee."""
    if result == "Fail":
        return EXITED
    if result == "Final Pass":
        return CONFIRMED
    if result == "Pass":
        return IN_ROTATION
    return state


def trainee_placement(box_name=None):
    """A confirmed trainee enters the grid as emerging talent: potential
    seen, performance not yet earned over a full year."""
    return {"readiness": EMERGING, "potential": POTENTIAL_HIGH, "performance": None,
            "box_name": box_name or BOXES[(LOW, POTENTIAL_HIGH)]["name"]}


# ── The year, as the appraisal module holds it ────────────────────────
def year_performance(appraisals):
    """The employee's performance for the review, read off the appraisals
    and never typed: {"appraisal", "score", "band", "quarters"}, or None
    when there is no appraisal to read.

    appraisals: the year's completed appraisals, each with "name",
    "quarter", "total" (the quarter's score), "band" (its rating),
    "year_score" and "year_band" (the year to date it carries) and
    "end_date". The latest quarter carries the year to date over every
    quarter appraised, which is the figure the review is about. A blank
    figure is kept as 0, so a figure counts only where its rating says it
    was worked out: the year to date where it has its rating, else the
    quarters rated, averaged (one rated quarter keeps its own rating), and
    nothing rated at all is no performance to read."""
    rows = [row for row in appraisals or [] if row.get("name")]
    if not rows:
        return None

    def when(row):
        quarter = row.get("quarter")
        return (QUARTER_ORDER.index(quarter) if quarter in QUARTER_ORDER else -1, str(row.get("end_date") or ""))

    rows = sorted(rows, key=when)
    latest = rows[-1]
    quarters = [{"quarter": row.get("quarter"), "appraisal": row["name"], "total": row.get("total"),
                 "band": row.get("band")} for row in rows if row.get("quarter") in QUARTER_ORDER]
    if latest.get("year_band"):
        score, band = _number(latest.get("year_score")), latest["year_band"]
    else:
        rated = [row for row in rows if row.get("band")]
        if not rated:
            return None
        score = sum(_number(row.get("total")) for row in rated) / len(rated)
        band = rated[0]["band"] if len(rated) == 1 else None
    return {"appraisal": latest["name"], "score": round(score, 2), "band": band, "quarters": quarters}


def competency_evidence(scorecard_rows, factor_rows):
    """The year's competency levels out of ten, as the appraiser gave them:
    a scorecard competency as scored, an LPL/HR/18 factor as rated (1 to 5,
    doubled), averaged over the quarters it was given in. Evidence beside
    the potential rating, never a score in it.

    scorecard_rows: [{"competency", "score", "appraisal"}]
    factor_rows: [{"factor", "rating", "appraisal"}], the rating "1" to "5"
    or "N/A". A blank is kept as 0, so a 0 is a figure never given, and
    N/A is no figure at all."""
    found = {}
    for name, value, appraisal in [(row.get("competency"), _number(row.get("score")), row.get("appraisal"))
                                   for row in scorecard_rows or []] + \
            [(row.get("factor"), _rating(row.get("rating")), row.get("appraisal")) for row in factor_rows or []]:
        name = " ".join(_text(name).split())[:140]
        if not name or value is None or value <= 0:
            continue
        entry = found.setdefault(name, {"competency": name, "levels": [], "appraisal": appraisal})
        entry["levels"].append(value)
        entry["appraisal"] = appraisal
    return [{"competency": entry["competency"], "level": round(sum(entry["levels"]) / len(entry["levels"]), 2),
             "times": len(entry["levels"]), "appraisal": entry["appraisal"]} for entry in found.values()]


def _rating(value):
    """An LPL/HR/18 rating (1 to 5) out of ten; N/A and blank are none."""
    text = _text(value)
    if not text or not text.replace(".", "", 1).isdigit():
        return None
    return round(_number(text) * DIMENSION_OUT_OF / FACTOR_OUT_OF, 2)


def effective_potential(rated, calibrated=None):
    """The potential band the box is drawn from: the one calibration gave,
    else the line manager's."""
    return calibrated or rated


def box_axes(box):
    """(performance band, potential band) of a box, or None."""
    return BOX_AXES.get(int(_number(box))) if box not in (None, "") else None


def move_errors(facts):
    """A box moved on the board during calibration (test case 7). The peer
    group moves a person up or down their column: potential is theirs to
    weigh across the plants, performance is the appraisal's, and changing
    it is done on the appraisal, not here.

    facts: "state" (the placement's), "calibrating" (the state that means
    calibration), "from_box", "to_box", "reason"."""
    errors = []
    if facts.get("state") != facts.get("calibrating"):
        errors.append("A box is moved only while the placement is in calibration.")
    to_axes = box_axes(facts.get("to_box"))
    if not to_axes:
        errors.append("Say which box the placement moves to.")
        return errors
    from_axes = box_axes(facts.get("from_box"))
    if from_axes and from_axes == to_axes:
        errors.append("The placement is already in that box.")
    elif from_axes and from_axes[0] != to_axes[0]:
        errors.append("Performance comes from the appraisal, so a placement moves up or down its "
                      "column only. Correct the appraisal to change it.")
    if not _text(facts.get("reason")):
        errors.append("Say why the placement moves. Calibration is recorded, not silent.")
    return errors


def board(placements, grid=None):
    """The grid as the board draws it, its cells named as HR keep them.

    placements: [{"name", "employee", "employee_name", "box", ...}]. Returns
    {"cells": [{"box", "name", "colour", "action", "people"}] in box order,
    "unplaced": the placements with no box yet (no appraisal, or not
    rated), "strips": the top, core and attention counts, "total"}."""
    table = (grid or {}).get("boxes") or BOXES
    cells = {spec["box"]: {"box": spec["box"], "name": spec["name"], "colour": spec["colour"],
                           "action": spec["action"], "people": []} for spec in table.values()}
    unplaced = []
    for row in placements or []:
        box = int(_number(row.get("box"))) if row.get("box") not in (None, "") else None
        (cells[box]["people"] if box in cells else unplaced).append(row)
    for cell in cells.values():
        cell["people"].sort(key=lambda row: (-_number(row.get("performance_score")),
                                             str(row.get("employee_name") or "")))
    placed = sum(len(cell["people"]) for cell in cells.values())
    top = tuple((grid or {}).get("top_talent") or TOP_TALENT)
    attention = tuple(box for box in ATTENTION if box not in top)
    core = tuple(box for box in sorted(cells) if box not in top and box not in attention)
    strips = {name: sum(len(cells[box]["people"]) for box in boxes)
              for name, boxes in (("top", top), ("core", core), ("attention", attention))}
    return {"cells": [cells[box] for box in sorted(cells)], "unplaced": unplaced, "strips": strips,
            "total": placed}


def share(part, whole):
    """A part of the whole, as a whole percentage."""
    return int(round(100.0 * part / whole)) if whole else 0


def review_title(year, branch=None, department=None, plan=None, taken=()):
    """The title of a review started from an appraisal plan, which is also
    its name: the year, then the plant and department the plan covers; the
    plan's own name added where that title is taken."""
    title = " ".join(str(part) for part in ("Talent Review", year, branch, department) if part)
    if title in set(taken or ()) and plan:
        title = "%s (%s)" % (title, plan)
    return title


def plan_progress(actions, today):
    """How far a development plan has got: its actions, those done (each
    records the day it was completed), those past their date and not done,
    and the share done."""
    rows = actions or []
    done = len([row for row in rows if row.get("completed_on")])
    late = len([row for row in rows if not row.get("completed_on") and row.get("by_when")
                and str(row["by_when"])[:10] < str(today)[:10]])
    return {"actions": len(rows), "done": done, "late": late, "share": share(done, len(rows))}


def month_bounds(day):
    """The first and the last day of the month a day falls in, as
    YYYY-MM-DD: what the Monthly Talent Report reads."""
    text = str(day)[:10]
    year, month = int(text[:4]), int(text[5:7])
    return ("%04d-%02d-01" % (year, month),
            "%04d-%02d-%02d" % (year, month, calendar.monthrange(year, month)[1]))


# ── What a confirmed plan leads to (Luuka, 6 Oct 2026) ────────────────
# A plan acts once its holder's last day is EXIT_WINDOW days away: about
# what a requisition needs to clear Luuka's approvals and an opening to be
# filled. While nobody is ready to take over, HR and the council are told
# again at each mark.
EXIT_WINDOW = 90
EXIT_MARKS = (90, 60, 30)
REPLACEMENT, NEW_ADDITION = "Replacement", "New Addition"
MENTORED, TAUGHT = "Mentoring and Coaching", "Learning and Development"
# the successors a plan aimed at the role is drawn up for
TO_DEVELOP = (READY_SOON, EMERGING)
# the line of the clearance (LPL/HR/22, box A) the handover is written on
HANDOVER_ITEM = "Handover report"
# what a programme's closing decision leads to (test case 3)
DECISION_STEPS = {"Succession Pipeline": "pool", "Promotion": "promote", "Replacement": "replace"}


def days_until(day, today):
    """Whole days from today to a day, negative once it has passed; None
    without a day."""
    end, start = _day(day), _day(today)
    if not end or not start:
        return None
    return (end - start).days


def ready_successor(candidates, leaver=None, active=None):
    """Who takes the role over: the first successor the council put down as
    ready now, in the order they listed them, still employed and not the
    one leaving. None when nobody is.

    active: the employees still employed, or None to take everyone named."""
    for row in candidates or []:
        employee = row.get("employee")
        if row.get("readiness") != READY_NOW or not employee or employee == leaver:
            continue
        if active is not None and employee not in active:
            continue
        return row
    return None


def successors_to_develop(candidates):
    """The successors a plan aimed at the role is drawn up for: those ready
    in one to two years and those emerging. One ready now needs the role,
    not a plan."""
    return [row for row in candidates or [] if row.get("employee") and row.get("readiness") in TO_DEVELOP]


def successor_program(has_mentor):
    """A successor is coached by the holder of the role while there is one,
    and taught otherwise."""
    return MENTORED if has_mentor else TAUGHT


def successor_plan_end(readiness, start, exit_due=None):
    """When a successor's plan ends: a year for one ready in one to two
    years, two for one emerging. A holder leaving sooner brings it forward
    to their last day, but never to under a quarter, so an appraisal comes
    after it to read what it did."""
    begin = _day(start)
    if not begin:
        return None
    end = _years_on(begin, 1 if readiness == READY_SOON else 2)
    leaving = _day(exit_due)
    if leaving and leaving < end:
        end = max(leaving, begin + datetime.timedelta(days=90))
    return end.isoformat()


def plan_actions(needs):
    """A successor's development needs as the plan's actions: one per line
    or per semicolon, bullets and numbering dropped, each once."""
    out, seen = [], set()
    for part in re.split(r"[\r\n;]+", _text(needs)):
        text = " ".join(re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", part).split())
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def exit_step(facts, today):
    """What a succession plan does about its holder leaving, on a day.

    facts: "exit_due" (the holder's last day), "confirmed" (the council has
    confirmed the plan), "ready" (somebody is to take over: a successor
    ready now, or a promotion already drafted), "promotion" and
    "requisition" (what is drafted already), "alerted" (the last mark HR
    and the council were told at).

    Returns {"days", "promote", "recruit", "alert"}. Nothing happens until
    the exit is EXIT_WINDOW days away, nor once it has passed. Then a
    confirmed plan with somebody ready drafts their promotion and needs
    nobody told; a confirmed plan without drafts the requisition for a
    replacement; and while nobody is ready, or the plan is not confirmed,
    HR and the council are told at each mark it reaches."""
    out = {"days": days_until(facts.get("exit_due"), today), "promote": False, "recruit": False,
           "alert": None}
    days = out["days"]
    if days is None or days < 0 or days > EXIT_WINDOW:
        return out
    if facts.get("confirmed") and facts.get("ready"):
        out["promote"] = not facts.get("promotion")
        return out
    if facts.get("confirmed") and not facts.get("requisition"):
        out["recruit"] = True
    out["alert"] = exit_mark(days, facts.get("alerted"))
    return out


def exit_mark(days, alerted=None):
    """The mark (90, 60 or 30 days out) a plan has reached and not been told
    at yet, or None. A day the scheduler missed is caught up the next, and
    an exit announced late is told once, at the mark it falls in."""
    if days is None or days < 0:
        return None
    reached = [mark for mark in EXIT_MARKS if days <= mark]
    if not reached:
        return None
    mark = min(reached)
    if alerted and int(_number(alerted)) <= mark:
        return None
    return mark


def requisition_reason(exit_due=None, incumbent=None):
    """Why the requisition is raised: to replace a holder who is leaving, or
    to fill a role nobody holds; otherwise the holder stays and the empty
    bench is grown by an addition."""
    return REPLACEMENT if exit_due or not incumbent else NEW_ADDITION


def handover_note(designation, successor=None):
    """The clearance's handover line for the holder of a critical role: who
    the work goes to. Under 140 characters, the width of the line."""
    if successor:
        text = "To %s, who takes over as %s" % (successor, designation)
    else:
        text = "No successor is ready for %s. Hand over to the head of department" % designation
    return text[:140]


# ── Training, back from L&D (Luuka, 6 Oct 2026) ───────────────────────
# A plan's training goes to L&D as a Training Requisition whose topics are
# the plan's own actions, cut to the 140 characters a topic holds. What L&D
# makes of it (the session, who attended, the marks) comes back to the plan.
TOPIC_LENGTH = 140
ATTENDED = "Present"
EFFECTIVE = "Effective"


def topic_rows(texts, method):
    """The topics a requisition asks for, one row each: the text cut to the
    length a topic holds, its whole wording as the skills it gives, each
    once, the blank ones left out."""
    out, seen = [], set()
    for text in texts or []:
        topic = _text(text)[:TOPIC_LENGTH].strip()
        if topic and _topic_key(topic) not in seen:
            seen.add(_topic_key(topic))
            out.append({"topic": topic, "required_skills": _text(text), "method": method})
    return out


def same_topic(text, topic):
    """Whether a plan's action is the topic its training was requested as:
    the same words, as far as a topic holds them."""
    return bool(_topic_key(text)) and _topic_key(text) == _topic_key(topic)


def actions_for_topic(actions, topic):
    """The plan's actions a training on this topic covers."""
    return [row for row in actions or [] if same_topic(row.get("action"), topic)]


def training_counts(rows):
    """A plan's trainings: booked, attended, and found effective."""
    rows = rows or []
    return {"trainings": len(rows),
            "attended": len([row for row in rows if row.get("attendance") == ATTENDED]),
            "effective": len([row for row in rows if row.get("effectiveness") == EFFECTIVE])}


def _topic_key(value):
    return " ".join(_text(value)[:TOPIC_LENGTH].split()).lower()


# ── Small helpers ─────────────────────────────────────────────────────
def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def _years_on(day, years):
    """The same day `years` on; the 29th of February falls back to the 28th."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = _text(value)[:10]
    try:
        return datetime.date(*(int(part) for part in text.split("-"))) if text else None
    except (TypeError, ValueError):
        return None


def _and(items):
    items = [str(item).replace("_", " ") for item in items]
    if len(items) == 1:
        return items[0]
    return "%s and %s" % (", ".join(items[:-1]), items[-1])
