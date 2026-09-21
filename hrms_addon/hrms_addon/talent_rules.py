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
DECISIONS = ("Succession Pipeline", "Promotion", "Replacement", "Retain in Role", "Improve")

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


# ── Reading the two axes ──────────────────────────────────────────────
def performance_band(score):
    """The appraisal's own score, put in a band. Nothing is re-entered."""
    if score is None or score == "":
        return None
    return next(name for floor, name in PERFORMANCE_BANDS if _number(score) >= floor)


def potential_score(assessment):
    """Ability, aspiration and engagement, each out of ten and each worth
    the same, as a score out of a hundred. A dimension left blank is not
    counted, so a half-finished assessment does not read as a low one."""
    given = [_number(assessment.get(name)) for name in POTENTIAL_DIMENSIONS
             if assessment.get(name) not in (None, "")]
    if not given:
        return None
    return round(sum(given) / len(given) * (100.0 / DIMENSION_OUT_OF), 2)


def potential_band(score):
    if score is None or score == "":
        return None
    return next(name for floor, name in POTENTIAL_BANDS if _number(score) >= floor)


def box_for(performance, potential):
    """The one cell the two bands resolve to."""
    found = BOXES.get((performance, potential))
    return dict(found) if found else None


def is_top_talent(box):
    return _number(box) in TOP_TALENT


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


def milestone_outcome(score, final=False):
    """What a milestone score comes to."""
    if score in (None, ""):
        return None
    if _number(score) < PASS_MARK:
        return "Fail"
    return "Final Pass" if final else "Pass"


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


# ── Small helpers ─────────────────────────────────────────────────────
def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value):
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def _and(items):
    items = [str(item).replace("_", " ") for item in items]
    if len(items) == 1:
        return items[0]
    return "%s and %s" % (", ".join(items[:-1]), items[-1])
