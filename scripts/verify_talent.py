"""Verify talent management, without a bench:

    python scripts/verify_talent.py

The Talent Management sheet of Luuka's revised testing scripts, all
twenty-two cases: the programme (1 to 3), the nine-box review (4 to 10),
succession (11 to 15), the graduate trainee scheme (16 to 20) and the
automation (21, 22).

  1  the two axes: the appraisal's own score banded, the potential rated
  2  the grid: nine cells, their names, colours and default actions
  3  the programme, the bench and the trainee: what each must carry
  4  the DocTypes carry them, and the box is at permission level 1
  5  the glue reads and writes fields that exist, and really reaches the
     other modules
  6  the four workflows walked end to end
  7  wiring: the workflows on migrate, the daily job, the report, the way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
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


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def all_fields(name):
    spec = doctype(name) or upstream_doctype(name)
    return dict(fields_of(spec), **custom_fields(name))


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
T = load("talent_rules")
P = load("talent_approval")
M = load("talent_program_approval")
S = load("succession_approval")
G = load("trainee_approval")
hooks = hooks_dict()
print("loaded talent_rules.py and the four approval modules without Frappe")

# ── 1. The two axes ───────────────────────────────────────────────────
# test case 4: the band comes off the appraisal score, and the line
# between Low and Meeting is the line the performance module puts a PIP
# below, so the two modules cannot disagree
appraisal_rules = load("appraisal_rules")
if T.MEETS_FROM != float(appraisal_rules.PIP_BELOW):
    fail.append("Low must start where the performance module starts a PIP: %s vs %s"
                % (T.MEETS_FROM, appraisal_rules.PIP_BELOW))
for score, band in ((0, T.LOW), (59.9, T.LOW), (60, T.MEETING), (79.9, T.MEETING),
                    (80, T.EXCEEDING), (100, T.EXCEEDING)):
    if T.performance_band(score) != band:
        fail.append("%s is %s, not %s" % (score, band, T.performance_band(score)))
if T.performance_band(None) is not None:
    fail.append("no appraisal means no band, not a low one")

# test case 5: ability, aspiration and engagement, each out of ten
if T.POTENTIAL_DIMENSIONS != ("ability", "aspiration", "engagement"):
    fail.append("potential is ability, aspiration and engagement: %s" % (T.POTENTIAL_DIMENSIONS,))
if T.potential_score({"ability": 8, "aspiration": 8, "engagement": 8}) != 80.0:
    fail.append("eight out of ten on each is eighty out of a hundred")
if T.potential_band(T.potential_score({"ability": 8, "aspiration": 8, "engagement": 8})) \
        != T.POTENTIAL_HIGH:
    fail.append("eighty is high potential")
if T.potential_score({"ability": 9, "aspiration": None, "engagement": None}) != 90.0:
    fail.append("a half-finished assessment averages what was given, not what was not")
if T.potential_score({}) is not None:
    fail.append("nothing rated is no score at all")
if T.competency_average([{"level": 6}, {"level": 8}]) != 7.0:
    fail.append("the competency evidence averages out of ten")
if T.competency_average([]) is not None:
    fail.append("no competencies carried over is no average")
print("the axes: the appraisal's own score banded, the three dimensions rated")

# ── 2. The grid ───────────────────────────────────────────────────────
if len(T.BOXES) != 9:
    fail.append("a nine-box grid has nine boxes: %d" % len(T.BOXES))
numbers = sorted(box["box"] for box in T.BOXES.values())
if numbers != list(range(1, 10)):
    fail.append("the boxes are numbered one to nine: %s" % numbers)
if len({box["name"] for box in T.BOXES.values()}) != 9:
    fail.append("each box has its own name")
for key, box in T.BOXES.items():
    for part in ("name", "colour", "action", "decision"):
        if not box.get(part):
            fail.append("box %s has no %s" % (box["box"], part))
    if box["decision"] not in T.DECISIONS:
        fail.append("box %s suggests %s, which is not a decision" % (box["box"], box["decision"]))
# test case 6: the two bands resolve to one cell
if T.box_for(T.EXCEEDING, T.POTENTIAL_HIGH)["box"] != 9:
    fail.append("exceeding with high potential is the star")
if T.box_for(T.LOW, T.POTENTIAL_LOW)["box"] != 1:
    fail.append("low on both is the bottom-left box")
if T.box_for(T.MEETING, T.POTENTIAL_HIGH)["decision"] != "Succession Pipeline":
    fail.append("a high-potential performer is one for the pipeline")
if T.box_for(T.EXCEEDING, T.POTENTIAL_MODERATE)["decision"] != "Promotion":
    fail.append("a high performer with potential to match is one to promote")
if T.box_for(T.LOW, T.POTENTIAL_LOW)["decision"] != "Replacement":
    fail.append("the chart's third decision, replacement, must be reachable")
if T.box_for(None, T.POTENTIAL_HIGH) is not None:
    fail.append("without a performance band there is no cell to resolve to")
if T.TOP_TALENT != (6, 8, 9) or not T.is_top_talent(9) or T.is_top_talent(5):
    fail.append("top talent is the three boxes with performance and potential both up")
print("the grid: nine named cells, and the three decisions the chart asks for")

# ── 3. What each document must carry ──────────────────────────────────
good = {"employee": "HR-EMP-1", "talent_review": "Talent Review 2026", "performance_score": 71.0,
        "ability": 7, "aspiration": 8, "engagement": 6, "rationale": "Steady, and asks for more."}
expect("a complete placement", T.placement_errors(good))
expect("no appraisal to read", T.placement_errors(dict(good, performance_score=None)),
       "no appraisal score")
expect("potential half rated", T.placement_errors(dict(good, aspiration=None)),
       "aspiration out of ten")
expect("rated out of a hundred by mistake", T.placement_errors(dict(good, ability=70)),
       "rated out of ten")
expect("no rationale", T.placement_errors(dict(good, rationale="  ")), "rationale")

# test case 7: a move in calibration is signed for
expect("a proper move", T.calibration_errors({"from_box": 5, "to_box": 6, "reason": "Two plants "
                                              "were scoring the same work differently.",
                                              "moved_by": "hrm@luuka"}))
expect("a silent move", T.calibration_errors({"from_box": 5, "to_box": 6, "reason": "",
                                              "moved_by": "hrm@luuka"}),
       "why the placement moves")
expect("a move to nowhere", T.calibration_errors({"from_box": 5, "to_box": 5, "reason": "x",
                                                  "moved_by": "a"}), "already in that box")
moved = T.movers([{"placement": "TP-1", "box": 5}, {"placement": "TP-2", "box": 9}],
                 [{"placement": "TP-1", "box": 6}, {"placement": "TP-2", "box": 9}])
if [row["placement"] for row in moved] != ["TP-1"] or moved[0]["to_box"] != 6:
    fail.append("the movers are the placements whose box is not the one submitted: %s" % moved)

# test cases 1 to 3: the programme
program = {"employee": "HR-EMP-1", "program_type": "Leadership Development",
           "start_date": "2026-01-05", "end_date": "2026-12-20",
           "actions": [{"action": "Run the Monday production meeting"}]}
expect("a complete programme", T.program_errors(program))
expect("mentoring with no mentor", T.program_errors(dict(
    program, program_type="Mentoring and Coaching")), "needs a mentor named")
expect("a programme with nothing in it", T.program_errors(dict(program, actions=[])),
       "at least one action")
expect("ending before it starts", T.program_errors(dict(program, end_date="2025-12-01")),
       "cannot end before it starts")
if T.PROGRAM_TYPES != ("Leadership Development", "Mentoring and Coaching",
                       "Learning and Development"):
    fail.append("the chart's three programmes: %s" % (T.PROGRAM_TYPES,))
if T.movement(62, 75) != 13.0:
    fail.append("the movement is what the appraisal did across the programme")
if T.effectiveness(62, 75) != "Highly Effective" or T.effectiveness(70, 68) != "No Effect":
    fail.append("effectiveness is read off the movement, not given as an opinion")
expect("closed with no appraisal since", T.review_errors({"outcome_notes": "Did well."}),
       "no appraisal since the programme ended")
expect("a proper review", T.review_errors({"score_after": 75, "outcome_notes": "Did well.",
                                           "decision": "Promotion"}))

# test cases 11 to 13: the bench
position = {"designation": "Extrusion Supervisor", "company": "Luuka Plastics Limited",
            "risk_level": "High", "incumbent": "HR-EMP-9", "single_person_role": 1,
            "candidates": [{"employee": "HR-EMP-1", "readiness": T.READY_SOON}]}
expect("a complete position", T.position_errors(position))
expect("a single-person role with nobody in it",
       T.position_errors(dict(position, incumbent=None)), "Name the incumbent")
expect("the incumbent as their own successor", T.position_errors(dict(
    position, candidates=[{"employee": "HR-EMP-9", "readiness": T.READY_NOW}])),
    "cannot succeed themselves")
expect("the same successor twice", T.position_errors(dict(position, candidates=[
    {"employee": "HR-EMP-1", "readiness": T.READY_NOW},
    {"employee": "HR-EMP-1", "readiness": T.READY_SOON}])), "nominated twice")
if T.coverage([{"readiness": T.READY_NOW}]) != T.COVERED:
    fail.append("somebody ready now covers the role")
if T.coverage([{"readiness": T.READY_SOON}]) != T.AT_RISK:
    fail.append("a successor two years out is a plan, not cover")
if T.coverage([]) != T.POSITION_GAP or not T.is_gap([]):
    fail.append("an empty bench is a gap")
if T.is_gap([{"readiness": T.READY_NOW}]):
    fail.append("a covered role is not a gap")
counts = T.bench_strength([{"readiness": T.READY_NOW}, {"readiness": T.EMERGING},
                           {"readiness": T.EMERGING}])
if counts[T.READY_NOW] != 1 or counts[T.EMERGING] != 2:
    fail.append("the bench is counted by readiness: %s" % counts)
needs = T.development_needs([{"employee": "A", "readiness": T.READY_NOW, "development_needs": "x"},
                             {"employee": "B", "readiness": T.EMERGING,
                              "development_needs": "Costing"}])
if [row["employee"] for row in needs] != ["B"]:
    fail.append("only a successor who is not ready yet has a development need to send: %s" % needs)
order = T.readiness_order([{"employee": "C", "readiness": T.GAP},
                           {"employee": "A", "readiness": T.READY_NOW},
                           {"employee": "B", "readiness": T.EMERGING}])
if [row["employee"] for row in order] != ["A", "B", "C"]:
    fail.append("the coverage report reads readiest first: %s" % order)

# test cases 16 to 20: the trainee
trainee = {"job_applicant": "HR-APP-1", "cohort": "Graduate Intake 2026",
           "start_date": "2026-02-02"}
expect("a complete trainee", T.trainee_errors(trainee))
expect("a trainee in no cohort", T.trainee_errors(dict(trainee, cohort=None)), "cohort")
expect("induction with no mentor", T.induction_errors({"checklist": []}), "Assign a mentor")
expect("induction with the checklist half done", T.induction_errors(
    {"mentor": "HR-EMP-3", "checklist": [{"item": "ID", "done": 1}, {"item": "PPE", "done": 0}]}),
    "Finish the onboarding checklist")
rotations = [{"department": "Extrusion", "from_date": "2026-02-02", "to_date": "2026-04-30",
              "supervisor": "HR-EMP-4", "objectives": "Learn the line."},
             {"department": "Printing", "from_date": "2026-05-01", "to_date": "2026-07-31",
              "supervisor": "HR-EMP-5", "objectives": "Learn the presses."}]
expect("two stints back to back", T.rotation_errors(rotations))
overlap = [dict(rotations[0]), dict(rotations[1], from_date="2026-04-15")]
expect("two places at once", T.rotation_errors(overlap), "overlaps the stint before it")
expect("a stint with nothing to do", T.rotation_errors(
    [dict(rotations[0], objectives="")]), "no objectives")
expect("a stint nobody watches", T.rotation_errors(
    [dict(rotations[0], supervisor=None)]), "no rotation supervisor")
expect("a milestone with a result and no score", T.milestone_errors(
    {"milestone": "Six months", "due_on": "2026-08-02", "result": "Pass"}),
    "Record the score")
if T.milestone_outcome(59) != "Fail" or T.milestone_outcome(60) != "Pass":
    fail.append("sixty is the pass mark, as it is everywhere else in this app")
if T.milestone_outcome(85, final=True) != "Final Pass":
    fail.append("the last milestone passed is a final pass")
if T.next_trainee_state(T.UNDER_ASSESSMENT, "Fail") != T.EXITED:
    fail.append("a failed milestone ends the traineeship")
if T.next_trainee_state(T.UNDER_ASSESSMENT, "Final Pass") != T.CONFIRMED:
    fail.append("a final pass confirms")
if T.next_trainee_state(T.UNDER_ASSESSMENT, "Pass") != T.IN_ROTATION:
    fail.append("a pass sends the trainee back out on rotation")
if T.trainee_placement()["readiness"] != T.EMERGING:
    fail.append("test case 20: a confirmed trainee enters the pool as emerging")
print("the documents: the placement, the programme, the bench and the trainee")

# ── 4. The paper ──────────────────────────────────────────────────────
placement = fields_of(doctype("Talent Placement"))
for fieldname in ("talent_review", "employee", "appraisal", "performance_score",
                  "performance_band", "ability", "aspiration", "engagement", "potential_score",
                  "potential_band", "competencies", "box", "box_name", "box_colour",
                  "default_action", "suggested_decision", "rationale", "flight_risk",
                  "themes", "development_plan", "submitted_box", "calibration_reason"):
    if fieldname not in placement:
        fail.append("the placement has no %s" % fieldname)
# test case 4: the score is read, never typed
for fieldname in ("appraisal", "performance_score", "performance_band", "box", "box_name"):
    if not placement.get(fieldname, {}).get("read_only"):
        fail.append("%s is read from elsewhere: it must be read-only" % fieldname)
# test case 10: the grid is at permission level 1, the themes are not
for fieldname in ("box", "box_name", "box_colour", "default_action", "performance_band",
                  "potential_band", "suggested_decision"):
    if placement.get(fieldname, {}).get("permlevel") != 1:
        fail.append("%s is the council's to see: it belongs at permission level 1" % fieldname)
if placement.get("themes", {}).get("permlevel"):
    fail.append("an employee sees their development themes: those stay at level 0")
if placement.get("rationale", {}).get("permlevel"):
    fail.append("the rationale is written by the line manager, so it stays at level 0")
perms = {(row["role"], row.get("permlevel", 0)) for row in doctype("Talent Placement")["permissions"]}
for role in ("HR Manager", "Talent Council"):
    if (role, 1) not in perms:
        fail.append("%s must be able to see the grid" % role)
if any(permlevel == 1 for role, permlevel in perms
       if role in ("Employee", "Supervisor", "Head of Department")):
    fail.append("a line manager rates potential; the grid itself is not theirs to read")

review = fields_of(doctype("Talent Review"))
for fieldname in ("appraisal_cycle", "opens_on", "calibration", "placements_created"):
    if fieldname not in review:
        fail.append("the review cycle has no %s" % fieldname)
if review.get("calibration", {}).get("options") != "Talent Calibration Entry":
    fail.append("the movers are recorded on the cycle")

program = fields_of(doctype("Talent Program"))
for fieldname in ("program_type", "mentor", "actions", "training_requisition", "score_before",
                  "score_after", "movement", "effectiveness", "decision", "outcome_notes",
                  "placement"):
    if fieldname not in program:
        fail.append("the programme has no %s" % fieldname)
if program.get("actions", {}).get("options") != "Development Action":
    fail.append("the programme's actions are the appraisal's own Development Action rows, so "
                "Part E and the development plan are one shape")

position_fields = fields_of(doctype("Succession Position"))
for fieldname in ("designation", "incumbent", "single_person_role", "risk_level", "candidates",
                  "coverage", "gap", "gap_confirmed", "job_opening", "ready_now"):
    if fieldname not in position_fields:
        fail.append("the succession position has no %s" % fieldname)
# the bench goes on growing after the council has confirmed the role
for fieldname in ("candidates", "ready_now", "coverage", "gap"):
    if not position_fields.get(fieldname, {}).get("allow_on_submit"):
        fail.append("%s must be writable after submit, or nobody can be added to the bench"
                    % fieldname)

trainee_fields = fields_of(doctype("Graduate Trainee Program"))
for fieldname in ("job_applicant", "cohort", "mentor", "checklist", "rotations", "milestones",
                  "employee", "placement", "succession_position", "exit_reason"):
    if fieldname not in trainee_fields:
        fail.append("the trainee programme has no %s" % fieldname)
milestone = fields_of(doctype("Trainee Milestone"))
if "appraisal" not in milestone or milestone["appraisal"].get("options") != "Appraisal":
    fail.append("test case 19: a milestone is assessed on a real Appraisal")
if "competency_check" not in milestone:
    fail.append("test case 19: with a competency check beside it")
candidate = fields_of(doctype("Succession Candidate"))
for fieldname in ("employee", "readiness", "placement", "development_needs",
                  "training_requisition"):
    if fieldname not in candidate:
        fail.append("a successor row has no %s" % fieldname)
if set((candidate["readiness"].get("options") or "").split("\n")) != set(T.READINESS):
    fail.append("the four readiness levels of test case 12: %s" % candidate["readiness"])
print("the paper: the placement, the cycle, the programme, the bench, the trainee")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "talent.py")
known = set()
for name in ("Talent Placement", "Talent Review", "Talent Program", "Succession Position",
             "Graduate Trainee Program", "Trainee Milestone", "Succession Candidate"):
    known |= set(fields_of(doctype(name)))
known |= {"doctype", "name", "docstatus", "employee", "company", "flags", "milestones"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update", "workflow_state",
                     "db_update", "update_child_table"):
        continue
    if fieldname not in known:
        fail.append("talent.py reads or writes %s, which is on none of its documents" % fieldname)
for needle, why in (
    ("rules.performance_band(", "the band comes off the appraisal score (case 4)"),
    ("rules.potential_score(", "and the potential off the three dimensions (case 5)"),
    ("rules.box_for(", "and the cell off the two bands (case 6)"),
    ("rules.calibration_errors(", "a move in calibration is signed for (case 7)"),
    ('"BSC Appraisal Competency"', "the competency evidence is carried over, not typed (case 5)"),
    ("custom_total_score", "the appraisal's own score is read, never re-entered (case 4)"),
    ("rules.coverage(", "coverage is worked out from the bench (case 13)"),
    ("rules.development_needs(", "and what the bench still needs (case 14)"),
    ('"Job Opening"', "a confirmed gap raises a job opening in resourcing (case 14)"),
    ("REQUISITION", "and the development needs really reach L&D (cases 9 and 14)"),
    ('"Appraisal"', "a milestone is assessed on a real appraisal (case 19)"),
    ('"Employee"', "a confirmed trainee gets an employee record (case 20)"),
    ("rules.trainee_placement(", "and enters the grid as emerging (case 20)"),
    ("_draft_placements(", "a cycle that opens drafts its placements (case 21)"),
    ("_flag_flight_risk(", "top talent at risk is told to the council (case 22)"),
):
    if needle not in glue:
        fail.append("talent.py: %s (%r not found)" % (why, needle))
for name in ("draft_placements", "trainee_from_applicant"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("talent.%s changes something: a whitelisted POST method" % name)
if "check_permission(" not in glue:
    fail.append("talent.py: a whitelisted method must check the caller may act")
for name, prefix, methods in (
        ("talent_review", "review", ("validate",)),
        ("talent_placement", "placement", ("validate", "on_submit", "on_cancel")),
        ("talent_program", "program", ("validate", "on_submit", "on_cancel")),
        ("succession_position", "position", ("validate", "on_submit", "on_cancel")),
        ("graduate_trainee_program", "trainee", ("validate", "on_submit", "on_cancel"))):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    for method in methods:
        if "    def %s(self):\n        talent.%s_%s(self)" % (method, prefix, method) \
                not in controller:
            fail.append("the %s controller must hand %s to talent.%s_%s"
                        % (name, method, prefix, method))
print("glue: the score read, the grid derived, the opening raised, L&D really reached")

# ── 6. The four workflows ─────────────────────────────────────────────
def walk(module, first, forward):
    state, seen, walked = first, set(), [first]
    while state not in seen:
        seen.add(state)
        steps = [t for t in module.TRANSITIONS if t["state"] == state and t["action"] in forward]
        if not steps:
            break
        state = steps[0]["next_state"]
        walked.append(state)
    return walked


walked = walk(P, P.DRAFT, (P.SUBMIT, P.TO_COUNCIL, P.FINALISE))
if walked != [P.DRAFT, P.CALIBRATION, P.COUNCIL_REVIEW, P.FINALISED]:
    fail.append("a placement is submitted, calibrated, then finalised: %s" % walked)
if not [t for t in P.TRANSITIONS
        if t["action"] == P.RETURN_TO_CALIBRATION and t["next_state"] == P.CALIBRATION]:
    fail.append("test case 8: the council must be able to send a pool back for rework")
if P.next_states(P.COUNCIL_REVIEW, ("Supervisor",)):
    fail.append("a line manager does not finalise their own placements")
if not P.next_states(P.COUNCIL_REVIEW, ("Talent Council",)):
    fail.append("the council finalises")

walked = walk(M, M.DRAFT, (M.ENROL, M.START, M.REVIEW, M.CLOSE))
if walked != [M.DRAFT, M.ENROLLED, M.RUNNING, M.UNDER_REVIEW, M.CLOSED]:
    fail.append("a programme is enrolled, run, reviewed, closed: %s" % walked)

walked = walk(S, S.DRAFT, (S.OPEN_NOMINATIONS, S.TO_COUNCIL, S.CONFIRM))
if walked != [S.DRAFT, S.NOMINATIONS, S.COUNCIL_REVIEW, S.CONFIRMED]:
    fail.append("a position is opened, nominated for, then confirmed: %s" % walked)
expect("an empty bench sent up with no note",
       S.step_errors(S.NOMINATIONS, S.COUNCIL_REVIEW, {"candidates": []}), "no successors named")

walked = walk(G, G.RECRUITED, (G.INDUCT, G.START_ROTATION, G.ASSESS))
if walked != [G.RECRUITED, G.IN_INDUCTION, G.IN_ROTATION, G.UNDER_ASSESSMENT]:
    fail.append("a trainee is inducted, rotated, then assessed: %s" % walked)
if not [t for t in G.TRANSITIONS
        if t["state"] == G.UNDER_ASSESSMENT and t["next_state"] == G.IN_ROTATION]:
    fail.append("a passed milestone sends the trainee back out for the next stint")
for action, state in ((G.CONFIRM, G.CONFIRMED), (G.FAIL, G.EXITED)):
    if not [t for t in G.TRANSITIONS if t["action"] == action and t["next_state"] == state]:
        fail.append("test case 19: a milestone ends in %s as well" % state)
expect("exited with no reason", G.step_errors(G.UNDER_ASSESSMENT, G.EXITED, {}), "why the trainee")

for module, label in ((P, "placement"), (M, "programme"), (S, "position"), (G, "trainee")):
    if set(module.STAMPS) - set(module.PENDING_STATES) - {module.STATES[0]["state"]}:
        fail.append("the %s stamps a state it does not pass: %s" % (label, sorted(module.STAMPS)))
    if set(module.ROLE_WAITING) != set(module.PENDING_STATES):
        fail.append("every desk the %s waits at is known: %s" % (label, sorted(module.ROLE_WAITING)))
    if any(module.compute_stamps(module.PENDING_STATES[-1], module.STATES[0]["state"], "x",
                                 "2026-06-01", {field: "a" for field in
                                                module.ALL_STAMP_FIELDS}).values()):
        fail.append("a returned %s clears every signature" % label)
    submitting = [row["state"] for row in module.STATES if row.get("doc_status") == "1"]
    if not submitting:
        fail.append("the %s must end in a submitted state" % label)
for role in ("Talent Council", "Mentor"):
    if role not in set(P.NEW_ROLES) | set(M.NEW_ROLES) | set(S.NEW_ROLES) | set(G.NEW_ROLES):
        fail.append("%s is named on a document of ours: a workflow must create it" % role)
print("the four workflows: each walked end to end, each returning and each signed")

# ── 7. Wiring ─────────────────────────────────────────────────────────
migrate = hooks.get("after_migrate", [])
if "hrms_addon.hrms_addon.talent.setup_workflows_on_migrate" not in migrate:
    fail.append("the four workflows must be built on every migrate")
if migrate.index("hrms_addon.hrms_addon.talent.setup_workflows_on_migrate") \
        > migrate.index("hrms_addon.hrms_addon.navigation.setup_on_migrate"):
    fail.append("the workflows are built before the navigation that links to them")
if "hrms_addon.hrms_addon.talent.daily" not in hooks.get("scheduler_events", {}).get("daily", []):
    fail.append("the cycle that opens and the milestone that falls due need the daily job")
setup = read("hrms_addon", "hrms_addon", "talent.py")
for module in ("talent_approval", "talent_program_approval", "succession_approval",
               "trainee_approval"):
    if module not in setup:
        fail.append("setup_workflows_on_migrate must build %s" % module)
if hooks.get("doctype_js", {}).get("Job Applicant") != "public/js/job_applicant_trainee.js":
    fail.append("test case 16: the trainee is made from the applicant's own form")

nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Talent Review", "Talent Placement", "Talent Program", "Succession Position",
             "Graduate Trainee Program", "Succession Coverage"):
    if name not in nav:
        fail.append("%s has no way in" % name)
report = json.load(open(os.path.join(APP, "report", "succession_coverage",
                                     "succession_coverage.json"), encoding="utf-8"))
if report.get("ref_doctype") != "Succession Position" or report.get("is_standard") != "Yes":
    fail.append("test case 15: the coverage report is a standard report on the position")
if "Talent Council" not in [row["role"] for row in report.get("roles", [])]:
    fail.append("the council reads the coverage report")
report_py = read("hrms_addon", "hrms_addon", "report", "succession_coverage",
                 "succession_coverage.py")
for needle in ("rules.readiness_order(", "rules.bench_strength(", "incumbent", "risk_level"):
    if needle not in report_py:
        fail.append("the coverage report shows the incumbent, the risk and the successors by "
                    "readiness (%r not found)" % needle)
if "frappe.get_list(" not in report_py:
    fail.append("the report reads through Frappe's permissions (get_list, not get_all)")
for name in ("talent_placement", "talent_review", "succession_position",
             "graduate_trainee_program"):
    path = os.path.join(APP, "doctype", name, name + ".js")
    if not os.path.exists(path):
        fail.append("%s has no form script" % name)
print("wiring: the workflows on migrate, the daily job, the report, the way in")

# ── 8. Luuka, 5 Oct 2026: one module with the appraisal, and the board ──
# "build a coherent module properly linked with appraisal": the year read
# from the appraisal plan's quarters, the evidence from both forms, the
# improvement plan and management's decision carried across, the trainee's
# milestones on real appraisals, and the review on one grid.
YEAR = [{"name": "A1", "quarter": "Q1", "total": 70, "band": "Good", "year_score": 70, "year_band": "Good",
         "end_date": "2027-03-31"},
        {"name": "A2", "quarter": "Q2", "total": 86, "band": "Very Good", "year_score": 78, "year_band": "Good",
         "end_date": "2027-06-30"}]
year = T.year_performance(list(reversed(YEAR)))
if (year or {}).get("appraisal") != "A2" or year.get("score") != 78.0 or year.get("band") != "Good":
    fail.append("case 4: the year to date of the latest quarter, whatever order the appraisals come in: %s" % year)
if [row["quarter"] for row in (year or {}).get("quarters", [])] != ["Q1", "Q2"]:
    fail.append("case 4: each quarter beside it, in order: %s" % year)
if T.year_performance([{"name": "X", "quarter": "Q3", "total": 0, "band": None, "year_score": 0,
                        "year_band": None}]) is not None:
    fail.append("case 4: a completed appraisal never scored (0, no rating) is no performance to read")
if T.year_performance([]) is not None:
    fail.append("case 4: no appraisal, no performance")
averaged = T.year_performance([dict(YEAR[0], year_band=None), dict(YEAR[1], year_band=None)])
if (averaged or {}).get("score") != 78.0 or averaged.get("band") is not None:
    fail.append("case 4: without a year to date the rated quarters are averaged, under no one quarter's "
                "rating: %s" % averaged)
single = T.year_performance([dict(YEAR[0], year_band=None)])
if (single or {}).get("band") != "Good":
    fail.append("case 4: one rated quarter keeps its own rating: %s" % single)
evidence = T.competency_evidence(
    [{"competency": "Teamwork", "score": 6, "appraisal": "A1"}, {"competency": "Teamwork", "score": 8, "appraisal": "A2"},
     {"competency": "Safety", "score": 0, "appraisal": "A2"}],
    [{"factor": "Attendance", "rating": "4", "appraisal": "S1"}, {"factor": "Initiative", "rating": "N/A",
                                                                  "appraisal": "S1"},
     {"factor": "Quality  of   work", "rating": "5", "appraisal": "S1"}])
if evidence != [{"competency": "Teamwork", "level": 7.0, "times": 2, "appraisal": "A2"},
                {"competency": "Attendance", "level": 8.0, "times": 1, "appraisal": "S1"},
                {"competency": "Quality of work", "level": 10.0, "times": 1, "appraisal": "S1"}]:
    fail.append("case 5: scorecard scores as given, LPL/HR/18 ratings doubled, 0 and N/A left out, averaged "
                "over the quarters: %s" % evidence)
if T.effective_potential("High", None) != "High" or T.effective_potential("High", "Moderate") != "Moderate":
    fail.append("case 7: the box is drawn from the calibrated potential where there is one")
for box, axes in ((1, ("Low", "Low")), (5, ("Meeting", "Moderate")), (9, ("Exceeding", "High"))):
    if T.box_axes(box) != axes or T.box_for(*axes)["box"] != box:
        fail.append("box %d is %s, both ways round" % (box, axes))
calibrating = {"state": P.CALIBRATION, "calibrating": P.CALIBRATION}
expect("a move up the column, with its reason", T.move_errors(dict(calibrating, from_box=4, to_box=5, reason="x")))
expect("a move across the columns",
       T.move_errors(dict(calibrating, from_box=4, to_box=1, reason="x")), "Performance comes from the appraisal")
expect("a silent move", T.move_errors(dict(calibrating, from_box=4, to_box=5, reason=" ")), "why the placement moves")
expect("a move to the same box", T.move_errors(dict(calibrating, from_box=5, to_box=5, reason="x")),
       "already in that box")
expect("a move outside calibration",
       T.move_errors(dict(calibrating, state=P.COUNCIL_REVIEW, from_box=4, to_box=5, reason="x")),
       "only while the placement is in calibration")
expect("a move to no box", T.move_errors(dict(calibrating, from_box=4, to_box=None, reason="x")),
       "which box")
drawn = T.board([{"name": "P1", "box": 9, "performance_score": 80, "employee_name": "B"},
                 {"name": "P2", "box": 9, "performance_score": 90, "employee_name": "A"},
                 {"name": "P3", "box": None}, {"name": "P4", "box": "2"}])
if [cell["box"] for cell in drawn["cells"]] != list(range(1, 10)) \
        or [row["name"] for row in drawn["cells"][8]["people"]] != ["P2", "P1"] \
        or drawn["strips"] != {"top": 2, "core": 0, "attention": 1} or drawn["total"] != 3 \
        or [row["name"] for row in drawn["unplaced"]] != ["P3"]:
    fail.append("the board: nine cells in order, best first, the strips, the unplaced apart: %s" % drawn)
if set(T.TOP_TALENT) | set(T.CORE) | set(T.ATTENTION) != set(range(1, 10)) \
        or set(T.TOP_TALENT) & set(T.CORE) or set(T.CORE) & set(T.ATTENTION):
    fail.append("the board's three strips share the nine boxes out between them")
if (T.share(1, 3), T.share(0, 0)) != (33, 0):
    fail.append("a share is a whole percentage, and of nothing is nothing")
if (T.final_milestone("2029-02-05", False, "2029-02-01"), T.final_milestone("2028-08-05", True, "2029-02-01"),
        T.final_milestone("2028-08-05", True, None)) != (True, False, True):
    fail.append("case 19: the final milestone is the one due as the programme ends, else the last")
expect("confirmed on an employment type", T.confirmation_errors({"employment_type": "Permanent"}))
expect("confirmed on none", T.confirmation_errors({}), "employment type")
expect("confirmed as a trainee still", T.confirmation_errors({"employment_type": T.TRAINEE_EMPLOYMENT}),
       "no longer a graduate trainee")

placement_fields = all_fields("Talent Placement")
for fieldname, fieldtype, options in (("quarter_results", "Table", "Appraisal Quarter Result"),
                                      ("on_pip", "Check", None),
                                      ("improvement_plan", "Link", "Performance Improvement Plan"),
                                      ("management_decision", "Data", None),
                                      ("performance_review", "Link", "Performance Review"),
                                      ("calibrated_potential", "Select", None)):
    field = placement_fields.get(fieldname) or {}
    if field.get("fieldtype") != fieldtype or (options and field.get("options") != options):
        fail.append("Talent Placement.%s: a %s%s" % (fieldname, fieldtype, " of " + options if options else ""))
    elif not field.get("read_only"):
        fail.append("Talent Placement.%s comes from the appraisal or the calibration: read only" % fieldname)
if (placement_fields.get("calibrated_potential") or {}).get("permlevel") != 1:
    fail.append("case 10: the calibrated potential is at permission level 1, as the box is")
if set((placement_fields.get("calibrated_potential") or {}).get("options", "").split("\n")) - {""} \
        != {T.POTENTIAL_LOW, T.POTENTIAL_MODERATE, T.POTENTIAL_HIGH}:
    fail.append("the calibrated potential is one of the three potential bands")
if (all_fields("Talent Review").get("appraisal_plan") or {}).get("options") != "Appraisal Plan":
    fail.append("a review reads the year's Appraisal Plan")
if (all_fields("Talent Competency Level").get("competency") or {}).get("fieldtype") != "Data":
    fail.append("an LPL/HR/18 factor is evidence too, so the competency is text, not a link to the scorecard's")
trainee_fields = all_fields("Graduate Trainee Program")
for fieldname, options in (("confirmed_employment_type", "Employment Type"), ("separation", "Employee Separation")):
    if (trainee_fields.get(fieldname) or {}).get("options") != options:
        fail.append("Graduate Trainee Program.%s links to %s" % (fieldname, options))
if (all_fields("Development Action").get("completed_on") or {}).get("fieldtype") != "Date":
    fail.append("a development action records when it was completed, for the plan's progress")
for name in ("Appraisal Quarter Result", "Appraisal Plan", "Performance Improvement Plan", "Performance Review"):
    if not doctype(name):
        fail.append("%s, which talent reads, is not a DocType of this app" % name)

glue = read("hrms_addon", "hrms_addon", "talent.py")
for needle, why in (
    ('{"custom_plan": row.get("appraisal_plan")}', "a review reads the year's appraisal plan (case 4)"),
    ("rules.year_performance(", "and the year to date, not one quarter"),
    ('"custom_annual_score"', "read off the appraisal, never typed"),
    ('"Appraisal Factor Rating"', "LPL/HR/18 factors are competency evidence too (case 5)"),
    ("rules.competency_evidence(", "averaged as the rules say"),
    ("pips.open_plan(", "the improvement plan comes across"),
    ('"custom_outcome"', "and management's decision on the appraisal"),
    ("rules.effective_potential(", "the box is drawn from the calibrated potential (case 7)"),
    ("doc.calibrated_potential = None", "a placement back with the line manager starts calibration again"),
    ("have.add(row.employee)", "one placement a person, though the year has an appraisal each quarter"),
    ("_agreed_actions(doc)", "the plan carries on from the year's development actions (case 9)"),
    ('row.get("completed_on")', "leaving out those already completed"),
    ("def appraisal_on_submit(", "a completed appraisal reaches talent at once"),
    ("_refresh_open_placements(", "the placements still open read the year again"),
    ("milestone.score = flt(", "a milestone takes its appraisal's score (case 19)"),
    ("milestone.competency_check = _competency_level(", "and its competency check"),
    ("_employ_trainee(doc)", "a trainee is employed from induction (cases 19 and 20)"),
    ("rules.confirmation_errors(", "and confirmed on the employment type HR names (case 20)"),
    ('"custom_exit_type": "Involuntary"', "a trainee who leaves goes through the exit process"),
):
    if needle not in glue:
        fail.append("talent.py: %s (%r not found)" % (why, needle))
if "custom_form_type" in glue.split("def _raise_milestone_appraisal(")[1].split("\ndef ")[0]:
    fail.append("a milestone appraisal is on the form the trainee's Job Title's template gives, not one fixed here")
board = read("hrms_addon", "hrms_addon", "talent_board.py")
for needle, why in (
    ('get_permlevel_access("read", user=user)', "the board is for those who read the boxes (case 10)"),
    ("_check_access()", "and every method asks"),
    ("rules.move_errors(", "a move is judged by the rules (case 7)"),
    ("doc.flags.ignore_permissions = True", "the calibrated potential is written once the access is checked"),
    ("approval.next_states(state, frappe.get_roles())", "the board steps only as the workflow lets the user (case 8)"),
    ("frappe.db.savepoint(savepoint)", "each placement stands alone in a step taken together"),
    ("frappe.db.rollback(save_point=savepoint)", "and one refused takes back only what it wrote"),
    ('return {"allowed": 0}', "the forms ask for the card quietly"),
):
    if needle not in board:
        fail.append("talent_board.py: %s (%r not found)" % (why, needle))
for name in ("get_board", "get_card"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, board):
        fail.append("talent_board.%s reads: a whitelisted method" % name)
for name in ("move", "advance"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, board):
        fail.append("talent_board.%s writes: a whitelisted POST method" % name)
bulk = {action: state for action, state in (("Send to Council", P.CALIBRATION), ("Return", P.CALIBRATION),
                                             ("Finalise", P.COUNCIL_REVIEW),
                                             ("Return to Calibration", P.COUNCIL_REVIEW))}
for action, state in bulk.items():
    if not any(row["state"] == state and row["action"] == action for row in P.TRANSITIONS):
        fail.append("the board's step %s from %s is not one of the workflow's own" % (action, state))
page = json.load(open(os.path.join(APP, "page", "talent_board", "talent_board.json"), encoding="utf-8"))
page_roles = {row["role"] for row in page.get("roles") or []}
level_one = {row["role"] for row in doctype("Talent Placement").get("permissions", [])
             if row.get("permlevel") == 1 and row.get("read")}
if page.get("name") != "talent-board" or page_roles != level_one:
    fail.append("the board page opens for exactly those who read the boxes: %s, not %s"
                % (sorted(level_one), sorted(page_roles)))
page_js = read("hrms_addon", "hrms_addon", "page", "talent_board", "talent_board.js")
for needle, why in (
    ("talent_board.get_board", "the page draws the board from the server"),
    ("talent_board.move", "a drag in calibration is a move"),
    ("TB_COLUMN[box] === TB_COLUMN[this.dragging.box]", "and only up or down its column"),
    ("talent_board.advance", "the steps taken together"),
    ("hrms_addon.talent_card.render(", "the talent card beside the grid"),
):
    if needle not in page_js:
        fail.append("talent_board.js: %s (%r not found)" % (why, needle))
card_js = read("hrms_addon", "public", "js", "talent_card.js")
if "/assets/hrms_addon/js/talent_card.js" not in (hooks.get("app_include_js") or []):
    fail.append("the talent card is loaded on every desk page, for the board and both forms")
for path, needle in ((("hrms_addon", "public", "js", "employee.js"), "talent_card.attach(frm, frm.doc.name)"),
                     (("hrms_addon", "public", "js", "appraisal.js"), "talent_card.attach(frm, frm.doc.employee)")):
    if needle not in read(*path):
        fail.append("%s draws the talent card (%r not found)" % (path[-1], needle))
if '"custom ha-talent"' not in card_js:
    fail.append("the card's form section carries Frappe's custom class, so a refresh clears it")
appraisal_events = (hooks.get("doc_events") or {}).get("Appraisal") or {}
if appraisal_events.get("on_submit") != "hrms_addon.hrms_addon.talent.appraisal_on_submit":
    fail.append("hooks.py: a completed appraisal reaches talent (Appraisal on_submit)")
if "hrms_addon.hrms_addon.talent.seed_masters" not in (hooks.get("after_install") or []):
    fail.append("hooks.py: a fresh install has the graduate trainee employment type")
if "hrms_addon.patches.v1_0.talent_with_appraisal" not in read("hrms_addon", "patches.txt"):
    fail.append("patches.txt: talent_with_appraisal links the reviews to their plans and reads the year again")
print("Oct 2026: the year from the appraisal plan, the evidence from both forms, the plan and the decision across; "
      "milestones on real appraisals; the board, its moves and its steps")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL TALENT MANAGEMENT CHECKS PASSED")
