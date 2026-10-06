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
# what the plan leads to: the holder's exit, the promotion, the requisition
for name in ("Employee Separation", "Employee Position Change", "Job Requisition"):
    known |= set(all_fields(name))
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update", "workflow_state",
                     "db_update", "update_child_table", "ignore_linked_doctypes"):
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
    ("_draft_requisition_for(", "a confirmed gap drafts the requisition that becomes the job opening (case 14)"),
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
    ('grid: ["Nine-box", "get_board"', "the page draws the board from the server"),
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

# ── 9. The bench, the cohort, the plans' progress and the reports ─────
progress = T.plan_progress([{"completed_on": "2027-03-01"}, {"by_when": "2027-01-01"}, {"by_when": "2099-01-01"},
                            {"by_when": "2027-05-31", "completed_on": "2027-06-02"}, {}], "2027-06-01")
if progress != {"actions": 5, "done": 2, "late": 1, "share": 40}:
    fail.append("a plan's progress: done when completed, late when past its date and not done: %s" % progress)
if T.plan_progress([], "2027-06-01") != {"actions": 0, "done": 0, "late": 0, "share": 0}:
    fail.append("a plan with no actions has none done")
for day, bounds in (("2026-02-14", ("2026-02-01", "2026-02-28")), ("2028-02-03", ("2028-02-01", "2028-02-29")),
                    ("2026-12-31 18:00:00", ("2026-12-01", "2026-12-31"))):
    if T.month_bounds(day) != bounds:
        fail.append("the month %s falls in is %s, not %s" % (day, bounds, T.month_bounds(day)))
board = read("hrms_addon", "hrms_addon", "talent_board.py")
for name in ("get_succession", "get_trainees"):
    body = board.split("def %s(" % name)[1].split("\ndef ")[0] if "def %s(" % name in board else ""
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, board):
        fail.append("talent_board.%s reads: a whitelisted method" % name)
    if "_check_access()" not in body:
        fail.append("talent_board.%s is for those who read the boxes (case 10)" % name)
for needle, why in (
    ("COVERAGE_ORDER = {rules.POSITION_GAP: 0", "the roles nobody can fill come first (case 13)"),
    ('position["slate"] = rules.readiness_order(', "each bench readiest first (case 15)"),
    ("_latest_boxes(", "each successor with where they sit on the grid"),
    ("for stage in rules.TRAINEE_STATES]", "the trainees by the workflow's own stages (cases 16 to 20)"),
):
    if needle not in board:
        fail.append("talent_board.py: %s (%r not found)" % (why, needle))
page_js = read("hrms_addon", "hrms_addon", "page", "talent_board", "talent_board.js")
views = dict(re.findall(r'(\w+): \["[^"]+", "(get_\w+)"', page_js.split("const TB_VIEWS = {")[1].split("};")[0]))
if views != {"grid": "get_board", "succession": "get_succession", "trainees": "get_trainees"}:
    fail.append("the page's three views and the methods each reads: %s" % views)
for method in views.values():
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % method, board):
        fail.append("the page calls talent_board.%s, which is not a whitelisted method" % method)
for needle in ("render_succession(", "render_trainees(", "hrms_addon.hrms_addon.talent_board.${TB_VIEWS[view][1]}"):
    if needle not in page_js:
        fail.append("talent_board.js draws each view (%r not found)" % needle)
program_js = read("hrms_addon", "hrms_addon", "doctype", "talent_program", "talent_program.js")
for needle, why in (('frappe.meta.get_docfield("Development Action", "completed_on", frm.doc.name)',
                     "the plan shows when each action was done, on its own form only"),
                    ("ha_plan_progress(frm)", "and how far the plan has got")):
    if needle not in program_js:
        fail.append("talent_program.js: %s (%r not found)" % (why, needle))
trainee_js = read("hrms_addon", "hrms_addon", "doctype", "graduate_trainee_program", "graduate_trainee_program.js")
if "row.due_on >= frm.doc.end_date" not in trainee_js or "ha_trainee_journey(frm)" not in trainee_js:
    fail.append("graduate_trainee_program.js: a typed score reads the final milestone as the server does, and the "
                "journey is drawn")

REPORTS_ON_BOXES = {"Nine-Box Distribution", "Top Talent and Flight Risk", "Calibration Movers",
                    "Monthly Talent Report"}
for name in ("Nine-Box Distribution", "Top Talent and Flight Risk", "Calibration Movers", "Development Plan Tracker",
             "Programme Effectiveness", "Graduate Trainee Progress", "Monthly Talent Report"):
    folder = name.replace(" ", "_").replace("-", "_").lower()
    base = os.path.join(APP, "report", folder)
    if not all(os.path.exists(os.path.join(base, folder + ext)) for ext in (".json", ".py", ".js")):
        fail.append("the %s report ships its JSON, its Python and its filters" % name)
        continue
    spec = json.load(open(os.path.join(base, folder + ".json"), encoding="utf-8"))
    if (spec.get("name"), spec.get("report_type"), spec.get("is_standard")) != (name, "Script Report", "Yes"):
        fail.append("%s is a standard Script Report of that name" % name)
    if not doctype(spec.get("ref_doctype") or ""):
        fail.append("%s reads %s, which is not a DocType of this app" % (name, spec.get("ref_doctype")))
    if {row["role"] for row in spec.get("roles") or []} != level_one:
        fail.append("%s is for HR and the Talent Council, as the board is" % name)
    code = read("hrms_addon", "hrms_addon", "report", folder, folder + ".py")
    if "def execute(filters=None):" not in code:
        fail.append("%s has an execute" % name)
    if (name in REPORTS_ON_BOXES) != ("talent_reports.check_boxes()" in code):
        fail.append("%s %s where people sit on the grid, so it %s HR and the Talent Council (case 10)"
                    % (name, "names" if name in REPORTS_ON_BOXES else "does not name",
                       "asks for" if name in REPORTS_ON_BOXES else "need not ask for"))
    if 'frappe.query_reports["%s"]' % name not in read("hrms_addon", "hrms_addon", "report", folder, folder + ".js"):
        fail.append("%s registers its filters under its own name" % name)
reports = read("hrms_addon", "hrms_addon", "talent_reports.py")
for doctype_name, fieldname in (("Talent Placement", "finalised_on"), ("Succession Position", "confirmed_on"),
                                ("Talent Program", "reviewed_on"), ("Graduate Trainee Program", "confirmed_on"),
                                ("Talent Calibration Entry", "moved_on"), ("Development Action", "completed_on"),
                                ("Development Action", "by_when")):
    if fieldname not in all_fields(doctype_name):
        fail.append("the month reads %s.%s, which is not a field" % (doctype_name, fieldname))
    if '"%s"' % fieldname not in reports:
        fail.append("the month reads %s.%s for when it happened" % (doctype_name, fieldname))
for needle, why in (("rules.month_bounds(", "the month a day falls in"),
                    ('"completed_on": ["is", "not set"]', "the actions still not done at the month's end"),
                    ("rules.plan_progress(", "each plan's progress as the rules count it")):
    if needle not in reports:
        fail.append("talent_reports.py: %s (%r not found)" % (why, needle))
if "hrms_addon.hrms_addon.talent.monthly" not in ((hooks.get("scheduler_events") or {}).get("monthly") or []):
    fail.append("hooks.py: the month just ended is told to HR and the council (scheduler, monthly)")
monthly = glue.split("def monthly(")[1].split("\ndef ")[0] if "def monthly(" in glue else ""
for needle, why in (("talent_reports.month(add_days(today(), -1))", "the month just ended, on the first"),
                    ('("HR Manager", "Talent Council")', "told to the HR Managers and the council"),
                    ("people.notify(", "as an HR Alert, which is emailed"),
                    ("/app/query-report/Monthly Talent Report?month=", "with the report for that month")):
    if needle not in monthly:
        fail.append("talent.monthly: %s (%r not found)" % (why, needle))
print("the bench and the cohort on the board, each plan's progress, the seven reports and the month told to HR")

# ── 10. What a confirmed plan leads to (6 Oct 2026) ───────────────────
# The rules: when the plan acts on its holder's exit, and on what
for label, facts, today, wanted in (
        ("no exit, nothing", {"exit_due": None}, "2027-11-01", (None, False, False, None)),
        ("past the exit, nothing", {}, "2028-01-02", (-2, False, False, None)),
        ("five months out, nothing yet", {}, "2027-08-03", (150, False, False, None)),
        ("91 days out, nothing yet", {}, "2027-10-01", (91, False, False, None)),
        ("90 days out with somebody ready: their promotion", {"ready": True}, "2027-10-02", (90, True, False, None)),
        ("a promotion drafted already: nothing", {"ready": True, "promotion": True}, "2027-11-01",
         (60, False, False, None)),
        ("nobody ready at 90 days: the requisition, and the first mark", {}, "2027-10-02", (90, False, True, 90)),
        ("a requisition already: only the mark", {"requisition": True}, "2027-10-02", (90, False, False, 90)),
        ("the 90 told, at 45 days: the 60", {"requisition": True, "alerted": 90}, "2027-11-16",
         (45, False, False, 60)),
        ("the 60 told, at 45 days: nothing", {"requisition": True, "alerted": 60}, "2027-11-16",
         (45, False, False, None)),
        ("announced 20 days out: one mark, the 30", {}, "2027-12-11", (20, False, True, 30)),
        ("the 30 told, on the day: nothing", {"requisition": True, "alerted": 30}, "2027-12-31",
         (0, False, False, None)),
        ("a plan not confirmed: told, nothing drafted", {"confirmed": False, "ready": True}, "2027-10-02",
         (90, False, False, 90)),
):
    got = T.exit_step(dict({"exit_due": "2027-12-31", "confirmed": True, "ready": False, "promotion": False,
                            "requisition": False, "alerted": 0}, **facts), today)
    if (got["days"], got["promote"], got["recruit"], got["alert"]) != wanted:
        fail.append("exit_step, %s: got %s, wanted %s" % (label, got, wanted))
if [T.exit_mark(days, alerted) for days, alerted in ((95, 0), (90, 0), (61, 90), (60, 90), (31, 60), (30, 60),
                                                      (10, 30), (-1, 0), (None, 0))] \
        != [None, 90, None, 60, None, 30, None, None, None]:
    fail.append("exit_mark: 90, 60 and 30 days out, each told once, a missed day caught up")
candidates = [{"employee": "E1", "readiness": T.EMERGING}, {"employee": "E2", "readiness": T.READY_NOW},
              {"employee": "E3", "readiness": T.READY_NOW}, {"employee": "E4", "readiness": T.READY_SOON},
              {"employee": "E5", "readiness": T.GAP}]
if (T.ready_successor(candidates) or {}).get("employee") != "E2" \
        or (T.ready_successor(candidates, leaver="E2") or {}).get("employee") != "E3" \
        or (T.ready_successor(candidates, active={"E1", "E3"}) or {}).get("employee") != "E3" \
        or T.ready_successor(candidates, active={"E1"}) is not None:
    fail.append("ready_successor: the first ready now, in the council's order, employed, not the one leaving")
if [row["employee"] for row in T.successors_to_develop(candidates)] != ["E1", "E4"]:
    fail.append("successors_to_develop: those ready in one to two years and those emerging only")
for args, wanted in (((T.READY_SOON, "2027-09-01"), "2028-09-01"), ((T.EMERGING, "2027-09-01"), "2029-09-01"),
                     ((T.EMERGING, "2028-02-29"), "2030-02-28"),
                     ((T.READY_SOON, "2027-09-01", "2028-03-01"), "2028-03-01"),
                     ((T.READY_SOON, "2027-09-01", "2027-10-01"), "2027-11-30"),
                     ((T.READY_SOON, "2027-09-01", "2030-01-01"), "2028-09-01")):
    if T.successor_plan_end(*args) != wanted:
        fail.append("successor_plan_end%s: got %s, wanted %s" % (args, T.successor_plan_end(*args), wanted))
if T.plan_actions("1. Lab testing\r\n2) ISO 9001 audits; - Shift reports\n• lab testing\n\n * Costing") \
        != ["Lab testing", "ISO 9001 audits", "Shift reports", "Costing"] or T.plan_actions(None) != []:
    fail.append("plan_actions: a line or a semicolon each, numbering and bullets dropped, each once")
if (T.successor_program(True), T.successor_program(False)) != (T.MENTORED, T.TAUGHT) \
        or not set((T.MENTORED, T.TAUGHT)) <= set(T.PROGRAM_TYPES):
    fail.append("a successor is coached by the holder while there is one, taught otherwise")
if (T.requisition_reason("2027-12-31", "E1"), T.requisition_reason(None, None), T.requisition_reason(None, "E1")) \
        != (T.REPLACEMENT, T.REPLACEMENT, T.NEW_ADDITION):
    fail.append("requisition_reason: a replacement for a holder leaving or a role nobody holds, else an addition")
custom_reason = (custom_fields("Job Requisition").get("custom_reason_type") or {}).get("options") or ""
if not {T.REPLACEMENT, T.NEW_ADDITION} <= set(custom_reason.split("\n")):
    fail.append("the requisition's reasons are the ones its form offers: %r" % custom_reason)
if T.handover_note("Quality Lead", "John Okello") != "To John Okello, who takes over as Quality Lead" \
        or "head of department" not in T.handover_note("Quality Lead") or len(T.handover_note("X" * 300, "Y")) > 140:
    fail.append("handover_note: who takes over, else the head of department, within the line's 140 characters")
exit_rules = load("exit_rules")
if T.HANDOVER_ITEM not in dict((code, items) for code, _name, items in exit_rules.SECTIONS).get("A", ()):
    fail.append("the handover is written on LPL/HR/22's own line in box A: %r" % T.HANDOVER_ITEM)
if not set(T.DECISION_STEPS) <= set(T.DECISIONS):
    fail.append("each decision acted on is one the programme offers")

# The documents: what points where, and what may change on a confirmed plan
plan_fields = fields_of(doctype("Succession Position"))
for fieldname in ("incumbent", "incumbent_name", "retirement_or_exit_due", "previous_incumbent",
                  "previous_incumbent_name", "handed_over_on", "exit_alerted", "promotion_drafted_for",
                  "requisition_drafted_for", "ready_now", "ready_soon", "emerging", "bench_depth", "coverage", "gap"):
    if not (plan_fields.get(fieldname) or {}).get("allow_on_submit"):
        fail.append("Succession Position.%s changes on a confirmed plan, so it is allowed on submit" % fieldname)
for fieldname in ("exit_alerted", "promotion_drafted_for", "requisition_drafted_for"):
    if not (plan_fields.get(fieldname) or {}).get("hidden"):
        fail.append("Succession Position.%s is the watch's own record: hidden" % fieldname)
for dt, fieldname, options in (("Succession Candidate", "development_plan", "Talent Program"),
                               ("Talent Program", "succession_position", "Succession Position"),
                               ("Employee Position Change", "succession_position", "Succession Position"),
                               ("Employee Position Change", "talent_program", "Talent Program"),
                               ("Job Requisition", "custom_succession_position", "Succession Position"),
                               ("Job Requisition", "custom_talent_program", "Talent Program"),
                               ("Employee Separation", "custom_succession_position", "Succession Position")):
    spec = all_fields(dt).get(fieldname) or {}
    if (spec.get("fieldtype"), spec.get("options"), spec.get("read_only")) != ("Link", options, 1):
        fail.append("%s.%s is a read-only Link to %s" % (dt, fieldname, options))
order = json.loads(next(row["value"] for row in json.load(open(os.path.join(PACKAGE, "fixtures", "property_setter.json"),
                                                               encoding="utf-8"))
                        if row.get("doc_type") == "Job Requisition" and row.get("property") == "field_order"))
if order[order.index("reason_for_requesting") + 1:order.index("reason_for_requesting") + 3] \
        != ["custom_succession_position", "custom_talent_program"]:
    fail.append("the requisition's form shows where it came from under its reason (field_order)")
for name in ("Job Requisition-custom_succession_position", "Job Requisition-custom_talent_program",
             "Employee Separation-custom_succession_position"):
    if name not in json.dumps(hooks.get("fixtures")):
        fail.append("hooks.py exports the custom field %s with the fixtures" % name)


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


# a confirmed plan is changed only where Frappe allows it after submit
for name, target in (("position_before_update_after_submit", "doc"), ("_count_bench", "doc"),
                     ("_restart_exit_watch", "doc"), ("change_on_submit", "position"),
                     ("change_on_cancel", "position")):
    body = body_of(glue, name)
    if not body:
        fail.append("talent.%s is missing" % name)
        continue
    for fieldname in set(re.findall(r"\b%s\.(\w+)\s*=(?!=)" % target, body)) \
            | set(re.findall(r'\b%s\.set\("(\w+)"' % target, body)):
        if fieldname in ("flags", "ignore_linked_doctypes") or fieldname == "candidates":
            continue
        if not (plan_fields.get(fieldname) or {}).get("allow_on_submit"):
            fail.append("talent.%s sets Succession Position.%s, which a confirmed plan refuses" % (name, fieldname))
    if name in ("change_on_submit", "change_on_cancel") and "set(field, None)" in body:
        for fieldname in ("previous_incumbent", "previous_incumbent_name", "handed_over_on"):
            if not (plan_fields.get(fieldname) or {}).get("allow_on_submit"):
                fail.append("talent.%s clears %s, which a confirmed plan refuses" % (name, fieldname))
if "_fill_bench(" in body_of(glue, "position_before_update_after_submit"):
    fail.append("after submit the bench is counted only: gap_confirmed is not allowed on submit")
if not (fields_of(doctype("Succession Position")).get("candidates") or {}).get("allow_on_submit"):
    fail.append("successors are added to and taken off a confirmed plan: its table is allowed on submit")

# The glue: the plan acts, and each module reached does its own signing
for function, needles in (
        ("position_on_submit", ("_draft_requisition_for(", "_send_needs_to_ld(", "_plan_successor_development(",
                                "_act_on_exit(")),
        ("position_on_update_after_submit", ("_plan_successor_development(", "_act_on_exit(")),
        ("_act_on_exit", ("rules.exit_step(", "_draft_promotion(", "_draft_requisition_for(", "exit_alerted",
                          "promotion_drafted_for", "requisition_drafted_for", "_tell_council(")),
        ("_draft_requisition", ("flags.drafted_by_talent = True", "ignore_permissions", "custom_reason_type",
                                "CLOSED_REQUISITION")),
        ("_draft_promotion", ('"change_type": "Promotion"', "succession_position", "reports_to",
                              "ignore_permissions")),
        ("separation_on_update", ("custom_relieving_date", "retirement_or_exit_due", "_act_on_exit(")),
        ("separation_on_cancel", ("retirement_or_exit_due", "None")),
        ("change_on_submit", ("previous_incumbent", "handed_over_on", '"mentor"')),
        ("program_on_submit", ("rules.DECISION_STEPS", "_promote_from_program(", "_replace_from_program(")),
        ("daily", ("_watch_exits()", "_link_openings()")),
        ("position_on_cancel", ("POSITION_RECORDS",)),
        ("program_on_cancel", ("PROGRAM_RECORDS",))):
    body = body_of(glue, function)
    for needle in needles:
        if needle not in body:
            fail.append("talent.%s: %r not found" % (function, needle))
if "_raise_job_opening" in glue:
    fail.append("a gap no longer raises its job opening round Luuka's approvals")
requisition_glue = read("hrms_addon", "hrms_addon", "job_requisition.py")
validate = body_of(requisition_glue, "validate")
if 'if doc.flags.get("drafted_by_talent"):\n        # one a succession plan' not in validate \
        or validate.count("drafted_by_talent") != 1:
    fail.append("job_requisition.validate leaves the mode to HR only on a requisition talent drafts")
exits_glue = read("hrms_addon", "hrms_addon", "exits.py")
if "talent.handover_for(exit_doc.employee)" not in body_of(exits_glue, "draw_up_clearance") \
        or "talent_rules.HANDOVER_ITEM" not in body_of(exits_glue, "draw_up_clearance"):
    fail.append("exits.draw_up_clearance writes who takes over on the handover line")
events = hooks.get("doc_events") or {}


def handlers(dt, event):
    value = (events.get(dt) or {}).get(event) or []
    return [value] if isinstance(value, str) else list(value)


for dt, event, handler in (("Employee Separation", "on_update", "talent.separation_on_update"),
                           ("Employee Separation", "on_cancel", "talent.separation_on_cancel"),
                           ("Employee Separation", "on_cancel", "exits.separation_on_cancel"),
                           ("Employee Separation", "on_trash", "talent.separation_on_cancel"),
                           ("Employee Position Change", "on_submit", "talent.change_on_submit"),
                           ("Employee Position Change", "on_cancel", "talent.change_on_cancel")):
    if "hrms_addon.hrms_addon.%s" % handler not in handlers(dt, event):
        fail.append("hooks.py: %s %s runs %s" % (dt, event, handler))
controller = read("hrms_addon", "hrms_addon", "doctype", "succession_position", "succession_position.py")
for method in ("before_update_after_submit", "on_update_after_submit"):
    if "    def %s(self):\n        talent.position_%s(self)" % (method, method) not in controller:
        fail.append("the Succession Position controller hands %s to talent.position_%s" % (method, method))
if "hrms_addon.patches.v1_0.succession_follow_through" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]", 1)[-1]:
    fail.append("a site with plans already gets the follow-through by patch")
if 'sync_fixtures("hrms_addon")' not in read("hrms_addon", "patches", "v1_0", "succession_follow_through.py"):
    fail.append("the patch syncs the fixtures first: its links are custom fields")


# What points at a plan or a programme from a submittable document is left
# alone when it is cancelled, on the server and in Cancel All
def pointing_at(target):
    found = set()
    for path in glob.glob(os.path.join(APP, "doctype", "*", "*.json")):
        spec = json.load(open(path, encoding="utf-8"))
        if spec.get("doctype") != "DocType":
            continue
        owner = spec["name"]
        if spec.get("istable"):
            parents = [other["name"] for other_path in glob.glob(os.path.join(APP, "doctype", "*", "*.json"))
                       for other in [json.load(open(other_path, encoding="utf-8"))]
                       if other.get("doctype") == "DocType"
                       and any(f.get("options") == owner and f["fieldtype"] == "Table" for f in other.get("fields", []))]
        else:
            parents = [owner]
        if any(f["fieldtype"] == "Link" and f.get("options") == target for f in spec.get("fields", [])):
            found |= {name for name in parents if doctype(name).get("is_submittable")}
    for row in CUSTOM:
        if row.get("fieldtype") == "Link" and row.get("options") == target:
            upstream = upstream_doctype(row["dt"]) or {}
            if upstream.get("is_submittable"):
                found.add(row["dt"])
    return found - {target}


for target, constant, script in (("Succession Position", "POSITION_RECORDS", "succession_position"),
                                 ("Talent Program", "PROGRAM_RECORDS", "talent_program")):
    wanted = pointing_at(target)
    spelled = re.search(r"%s = \(([^)]*)\)" % constant, glue)
    names = {
        {"PROGRAM": "Talent Program", "CHANGE": "Employee Position Change", "SEPARATION": "Employee Separation",
         "TRAINEE": "Graduate Trainee Program", "POSITION": "Succession Position",
         "PLACEMENT": "Talent Placement", "REQUISITION": "Training Requisition"}.get(name.strip(), name.strip())
        for name in (spelled.group(1).split(",") if spelled else []) if name.strip()}
    if not wanted <= names:
        fail.append("talent.%s must leave alone %s, which point at a %s" % (constant, sorted(wanted - names), target))
    form = read("hrms_addon", "hrms_addon", "doctype", script, script + ".js")
    # the names in the list itself: the same names appear elsewhere in the
    # form (links, routes), which says nothing about Cancel All
    listed = re.search(r"ignore_doctypes_on_cancel_all = \[(.*?)\];", form, flags=re.S)
    if not listed or not all('"%s"' % name in listed.group(1) for name in names):
        fail.append("%s.js keeps %s out of Cancel All" % (script, sorted(names)))

# The way it shows: the form, the board, the report, the connections
plan_js = read("hrms_addon", "hrms_addon", "doctype", "succession_position", "succession_position.js")
if "hrms_addon.hrms_addon.talent.get_follow_through" not in plan_js or '"custom ha-follow"' not in plan_js:
    fail.append("succession_position.js shows the follow-through as its own dashboard section")
if not re.search(r"@frappe\.whitelist\(\)\ndef get_follow_through\(", glue) \
        or 'doc.check_permission("read")' not in body_of(glue, "get_follow_through"):
    fail.append("talent.get_follow_through: whitelisted, for those who may read the plan")
board_glue = read("hrms_addon", "hrms_addon", "talent_board.py")
for needle in ('position["promotion"]', 'position["requisition"]', 'position["opening"]', 'position["exit_days"]'):
    if needle not in body_of(board_glue, "get_succession"):
        fail.append("talent_board.get_succession carries %s" % needle)
board_js = read("hrms_addon", "hrms_addon", "page", "talent_board", "talent_board.js")
for needle in ("Taking over:", "Replacement:", "Recruiting:", "leaving(role)"):
    if needle not in board_js:
        fail.append("the board's succession view shows %r" % needle)
coverage = read("hrms_addon", "hrms_addon", "report", "succession_coverage", "succession_coverage.py")
for needle in ('"fieldname": "taking_over"', '"fieldname": "promotion"', '"fieldname": "requisition"',
               "talent.drafted_for_many("):
    if needle not in coverage:
        fail.append("Succession Coverage: %r not found" % needle)
spec = importlib.util.spec_from_file_location(
    "succession_position_dashboard",
    os.path.join(APP, "doctype", "succession_position", "succession_position_dashboard.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data = module.get_data()
listed = {item for group in data["transactions"] for item in group["items"]}
for dt in ("Talent Program", "Graduate Trainee Program", "Employee Separation", "Employee Position Change",
           "Job Requisition", "Job Opening"):
    if dt not in listed:
        fail.append("the plan's connections list %s" % dt)
for dt, fieldname in data.get("non_standard_fieldnames", {}).items():
    if fieldname not in all_fields(dt):
        fail.append("the plan's connections read %s.%s, which is not a field" % (dt, fieldname))
for dt in listed - set(data.get("non_standard_fieldnames", {})) - set(data.get("internal_links", {})):
    if data["fieldname"] not in all_fields(dt):
        fail.append("the plan's connections read %s.%s, which is not a field" % (dt, data["fieldname"]))
print("Oct 6: the plan acts on its holder's exit; successors grown, a promotion or a replacement drafted, the "
      "role handed over, each in its own module")

# ── 11. The print-outs (6 Oct 2026) ───────────────────────────────────
# Talent Card, Individual Development Plan, Succession Slate and Graduate
# Trainee Progress: the testing sheet's "Reports and print outs". A custom
# print format is handed every field, whatever the reader's permission
# level, so each prints the box and the potential only behind its own
# check; and each compiles, read by scripts/jinja_subset.py as Frappe's
# Jinja would read it.
_spec = importlib.util.spec_from_file_location("jinja_subset", os.path.join(REPO, "scripts", "jinja_subset.py"))
jinja_subset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jinja_subset)


def print_format(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "print_format", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


TALENT_PRINTS = {
    "Talent Card": ("Talent Placement", ("Appraisal Quarter Result", "Talent Competency Level", "Development Theme"), [
        "Talent Card", "Nine-Box Placement", "Performance, Year to Date", "Potential", "Retention", "Development",
        "Line Manager", "Talent Council"]),
    "Individual Development Plan": ("Talent Program", ("Development Action", "Development Training"), [
        "Individual Development Plan", "Objectives", "Development Actions", "Estimated Cost", "Review",
        "Agreement", "Mentor or Coach", "<h4>Training</h4>", "Attendance"]),
    "Succession Slate": ("Succession Position", ("Succession Candidate",), [
        "Succession Slate", "Successors, Readiest First", "Ready Now", "Bench Depth", "Filling the Role",
        "Confirmed by the Talent Council"]),
    "Graduate Trainee Progress": ("Graduate Trainee Program",
                                  ("Trainee Induction Item", "Trainee Rotation", "Trainee Milestone"), [
        "Graduate Trainee Progress", "Induction", "Rotations", "Milestones", "Outcome", "Mentor"]),
}
GUARDS = ("sees_boxes", "has_permlevel_access_to")
MACROS = ("v(", "day(", "who(", "num(", "person(", "money(")
# numbers, ticks and tables (counted) need no escaping
NUMERIC = {"Int", "Float", "Percent", "Currency", "Check", "Table"}
jinja_methods = (hooks.get("jinja") or {}).get("methods") or []
for name, (doc_type, tables, needles) in TALENT_PRINTS.items():
    spec = print_format(name)
    if not spec:
        fail.append("the %s print format is not there" % name)
        continue
    if (spec.get("doc_type"), spec.get("print_format_type"), spec.get("standard"), spec.get("custom_format"),
            spec.get("module")) != (doc_type, "Jinja", "Yes", 1, "HRMS Addon"):
        fail.append("%s is a standard Jinja print format of this app for %s" % (name, doc_type))
    if doctype(doc_type).get("default_print_format") != name:
        fail.append("%s prints as %s unless another is chosen (default_print_format)" % (doc_type, name))
    html = spec.get("html") or ""
    try:
        jinja_subset.compile_template(html)
    except Exception as error:  # noqa: BLE001
        fail.append("%s does not compile: %s" % (name, error))
    for needle in needles:
        if needle not in html:
            fail.append("%s does not say %r" % (name, needle))
    own = fields_of(doctype(doc_type))
    rows = {}
    for table in tables:
        rows.update(fields_of(doctype(table)))
    standard = {"name", "docstatus", "doctype", "idx", "parent", "workflow_state"}
    for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html))):
        if fieldname in standard | {"has_permlevel_access_to", "candidates"} and fieldname not in own:
            continue
        if fieldname not in own:
            fail.append("%s prints doc.%s, which the %s does not have" % (name, fieldname, doc_type))
    for fieldname in sorted(set(re.findall(r"\brow\.(\w+)", html))):
        if fieldname not in rows and fieldname not in standard | {"has_permlevel_access_to"}:
            fail.append("%s prints row.%s, which none of its tables has" % (name, fieldname))
    # a text field goes out escaped: through one of the macros, or | e
    for expression in re.findall(r"\{\{-?(.*?)-?\}\}", html, flags=re.S):
        text = expression.strip()
        if text.startswith(MACROS) or "| e" in text:
            continue
        for owner, fieldname in re.findall(r"\b(doc|row)\.(\w+)", text):
            field = (own if owner == "doc" else rows).get(fieldname) or {}
            if field and field.get("fieldtype") not in NUMERIC:
                fail.append("%s prints %s.%s unescaped: use v()" % (name, owner, fieldname))
    # the box and the potential bands only behind a check of the reader's level
    secret = {fieldname for fieldname, field in own.items() if field.get("permlevel")}
    secret_rows = {fieldname for fieldname, field in rows.items() if field.get("permlevel")}
    conditions = []
    for part in jinja_subset._scan(html):
        if part[0] == "block":
            word = part[1].split(None, 1)[0]
            if word in ("if", "for"):
                conditions.append(part[1])
            elif word in ("endif", "endfor"):
                conditions.pop()
            elif word == "elif":
                conditions[-1] = part[1]
            elif word == "set" and any(guard in part[1] for guard in GUARDS):
                continue
        if part[0] == "text":
            continue
        used = {fieldname for owner, fieldname in re.findall(r"\b(doc|row)\.(\w+)", part[1])
                if fieldname in (secret if owner == "doc" else secret_rows)}
        if used and not any(guard in condition for condition in conditions + [part[1]] for guard in GUARDS):
            fail.append("%s prints %s to anyone who may print it: put it behind the reader's level (case 10)"
                        % (name, ", ".join(sorted(used))))
    for method in set(re.findall(r"\b(talent_\w+)\(", html)):
        if "hrms_addon.hrms_addon.talent.%s" % method not in jinja_methods:
            fail.append("%s calls %s, which hooks.py does not give Jinja" % (name, method))
        if not re.search(r"\ndef %s\(" % method, glue):
            fail.append("%s calls talent.%s, which is not there" % (name, method))
for method in ("talent_follow_through", "talent_plan_progress"):
    if "frappe.has_permission(" not in body_of(glue, method):
        fail.append("talent.%s answers only a reader who may open the document" % method)
if "def talent_grid(" in glue:
    names = re.findall(r'rules\.BOXES\[\(performance, potential\)\]\["(\w+)"\]', body_of(glue, "talent_grid"))
    if set(names) != {"box", "name"}:
        fail.append("talent.talent_grid prints each cell's number and name from talent_rules.BOXES")
# the box stays where only HR and the council read it (case 10): nothing of
# it is copied into the themes the line manager reads, or into the plan the
# employee and the mentor read
if '"themes"' in body_of(glue, "_fill_box"):
    fail.append("talent._fill_box writes into the development themes, which the line manager reads")
for needle in ('doc.get("default_action")', 'doc.get("suggested_decision")', 'box["action"]'):
    if needle in body_of(glue, "_draw_up_development_plan"):
        fail.append("the development plan the employee reads is written from the box (%s)" % needle)
if "hrms_addon.patches.v1_0.talent_box_out_of_plans" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]", 1)[-1]:
    fail.append("a site whose box already wrote into themes and plans has it taken out by patch")
print("print-outs: the Talent Card, the development plan, the succession slate and the trainee's progress; the box "
      "only for those who may read it")

# ── 12. Training, back from L&D (6 Oct 2026) ──────────────────────────
# A plan's training goes to L&D as a requisition linked to the plan, the
# branch HR Officer told to submit it; what L&D makes of it comes back: the
# plan's Training rows, the actions of a session's topic done for an
# attendee, the marks and whether it worked.
rows = T.topic_rows(["Lab testing", "  lab   testing ", "", "ISO 9001 audits " + "x" * 200], "Internal")
if [row["topic"] for row in rows] != ["Lab testing", ("ISO 9001 audits " + "x" * 200)[:140].strip()] \
        or rows[1]["required_skills"] != "ISO 9001 audits " + "x" * 200 or rows[0]["method"] != "Internal":
    fail.append("topic_rows: each text once, cut to a topic's 140 characters, its whole wording as the skills")
if not T.same_topic("Lead  the night shift", "lead the night shift") or T.same_topic("", "") \
        or T.same_topic("Lab testing", "Lab test") \
        or not T.same_topic("a  b " + "y" * 300, ("a  b " + "y" * 300)[:140].strip()):
    fail.append("same_topic: the same words as far as a topic holds them, spacing and case aside, never blank")
if [row["action"] for row in T.actions_for_topic([{"action": "Lab testing"}, {"action": "Shift reports"},
                                                  {"action": "lab testing"}], "Lab Testing")] \
        != ["Lab testing", "lab testing"]:
    fail.append("actions_for_topic: every action of the session's topic")
if T.training_counts([{"attendance": "Present", "effectiveness": "Effective"}, {"attendance": "Absent"},
                      {"attendance": None}]) != {"trainings": 3, "attended": 1, "effective": 1}:
    fail.append("training_counts: booked, attended, effective")
training_rows = fields_of(doctype("Development Training"))
for fieldname in ("topic", "training_event", "training_date", "attendance", "marks", "effectiveness"):
    spec = training_rows.get(fieldname) or {}
    if not spec.get("read_only") or not spec.get("in_list_view"):
        fail.append("Development Training.%s is shown and only ever filled from L&D" % fieldname)
if (training_rows.get("training_event") or {}).get("options") != "Training Event":
    fail.append("a plan's training row opens its session")
if not os.path.exists(os.path.join(APP, "doctype", "development_training", "development_training.py")):
    fail.append("Development Training needs its controller, child table or not, or migrate stops at it")
plan_spec = fields_of(doctype("Talent Program"))
trainings = plan_spec.get("trainings") or {}
if (trainings.get("fieldtype"), trainings.get("options"), trainings.get("read_only"), trainings.get("allow_on_submit")) \
        != ("Table", "Development Training", 1, 1):
    fail.append("Talent Program.trainings: a read-only Development Training table, kept after the plan closes")
action_spec = fields_of(doctype("Development Action")).get("training_event") or {}
if (action_spec.get("fieldtype"), action_spec.get("hidden")) != ("Data", 1):
    fail.append("Development Action.training_event: the session that marked it, hidden, and no link a cancel "
                "could trip on")
requisition_link = fields_of(doctype("Training Requisition")).get("talent_program") or {}
if (requisition_link.get("fieldtype"), requisition_link.get("options"), requisition_link.get("read_only")) \
        != ("Link", "Talent Program", 1):
    fail.append("Training Requisition.talent_program: a read-only Link to the plan it came from")
for function, needles in (
        ("_push_to_ld", ('"talent_program": program.name', "rules.topic_rows(", "_ask_hr_to_submit(")),
        ("_send_needs_to_ld", ("rules.topic_rows(rules.plan_actions(", "_ask_hr_to_submit(")),
        ("_plan_successor_development", ('frappe.db.set_value(REQUISITION, row.training_requisition, "talent_program"',)),
        ("_ask_hr_to_submit", ("people.hr_officers(", "people.notify(", "people.assign(")),
        ("sync_training", ("_training_behind(", "_plans_for(", "event.docstatus == 2", "rules.ATTENDED",
                           "_mark_actions(", "_unmark_actions(", "_training_results(")),
        ("_mark_actions", ('if not row.get("completed_on"):', "rules.actions_for_topic(")),
        ("_unmark_actions", ('"training_event": training_event}',)),
        ("_add_training_row", (".db_insert()",)),
        ("forget_training", ("_drop_training_row(", "_unmark_actions(")),
        ("_draw_up_development_plan", ("if themes:\n        _push_to_ld(program, themes)",))):
    body = body_of(glue, function)
    for needle in needles:
        if needle not in body:
            fail.append("talent.%s: %r not found" % (function, needle))
training_glue = read("hrms_addon", "hrms_addon", "training.py")
for function, needle in (("_book_event", "_to_talent(event.name)"), ("event_on_submit", "_to_talent(doc.name)"),
                         ("event_on_cancel", "_to_talent(doc.name)"),
                         ("result_on_submit", "_to_talent(doc.training_event)"),
                         ("result_on_cancel", "_to_talent(doc.training_event)"),
                         ("_release", "talent.forget_training(training_event)"),
                         ("_to_talent", "talent.sync_training(training_event)")):
    if needle not in body_of(training_glue, function):
        fail.append("training.%s reports to the plans: %r not found" % (function, needle))
cancel = body_of(training_glue, "event_on_cancel")
if "_to_talent(" not in cancel or cancel.index("_to_talent(") > cancel.index('"training_event": None'):
    fail.append("training.event_on_cancel lets the plans go before its requisitions forget the session")
if '("Talent Program",)' not in cancel:
    fail.append("training.event_on_cancel: a closed plan's Training row does not stop the session's cancel")
event_js = read("hrms_addon", "public", "js", "training_event.js")
listed = re.search(r"ignore_doctypes_on_cancel_all = \[(.*?)\];", event_js, flags=re.S)
if not listed or '"Talent Program"' not in listed.group(1):
    fail.append("training_event.js keeps the plans out of Cancel All")
tracker = read("hrms_addon", "hrms_addon", "report", "development_plan_tracker", "development_plan_tracker.py")
for needle in ("talent_reports.training_progress(", '"fieldname": "trainings"', '"fieldname": "attended"',
               '"fieldname": "effective"'):
    if needle not in tracker:
        fail.append("Development Plan Tracker: %r not found" % needle)
if "rules.training_counts(" not in body_of(read("hrms_addon", "hrms_addon", "talent_reports.py"), "training_progress"):
    fail.append("talent_reports.training_progress counts as the rules count")
training_report = read("hrms_addon", "hrms_addon", "report", "training_report", "training_report.py")
if '"parenttype": "Talent Program"' not in body_of(training_report, "_talent_only") \
        or 'fieldname: "talent_only"' not in read("hrms_addon", "hrms_addon", "report", "training_report",
                                                  "training_report.js"):
    fail.append("Training Report: Talent Programmes Only reads the plans' Training rows")
if "hrms_addon.patches.v1_0.talent_training_from_ld" not in read("hrms_addon", "patches.txt").split(
        "[post_model_sync]", 1)[-1]:
    fail.append("a site with talent training already booked gets it back on the plans by patch")
plan_js = read("hrms_addon", "hrms_addon", "doctype", "talent_program", "talent_program.js")
if "trainings attended" not in plan_js:
    fail.append("the plan's headline counts the trainings attended")
print("Oct 6: training back from L&D; the requisition names its plan and HR is told, sessions booked, attended "
      "and marked on the plan, its actions done")

# ── 14. The appraisal picked on the board (7 Oct 2026) ────────────────
# Luuka: "make appraisal selectable". The nine-box view is chosen by the
# appraisal plan; the review picker shows that plan's reviews; a plan no
# review reads yet can have one started from the board.
for args, wanted in (((2026,), "Talent Review 2026"), ((2026, "Kawempe"), "Talent Review 2026 Kawempe"),
                     ((2026, "Kawempe", "Extrusion - LPL"), "Talent Review 2026 Kawempe Extrusion - LPL"),
                     ((2026, None, None, "HR-APL-2026-00009", ["Talent Review 2026"]),
                      "Talent Review 2026 (HR-APL-2026-00009)"),
                     ((2026, None, None, None, ["Talent Review 2026"]), "Talent Review 2026")):
    if T.review_title(*args) != wanted:
        fail.append("review_title%r: want %r, got %r" % (args, wanted, T.review_title(*args)))
board_glue = read("hrms_addon", "hrms_addon", "talent_board.py")
for needle, why in (
        ("def get_board(review=None, branch=None, department=None, grade=None, plan=None):",
         "the board takes the plan picked"),
        ('filters={"appraisal_plan": plan} if plan else {}', "and lists only that plan's reviews"),
        ('if review and plan and frappe.db.get_value(REVIEW, review, "appraisal_plan") != plan:',
         "a review of another plan gives way to the plan picked"),
        ('"can_start": 1 if plan and frappe.has_permission(REVIEW, "create") else 0',
         "a plan with no review offers to start one to whoever may"),
        ('frappe.has_permission(REVIEW, "create", throw=True)', "starting a review needs the right to make one"),
        ('{"appraisal_plan": appraisal_plan, "status": ["!=", "Cancelled"]}', "one review a plan: the one there given back"),
        ("if plan.docstatus != 1:", "only a submitted plan has quarters to read"),
        ('"appraisal_cycle": ["is", "set"]}', "read from a quarter the plan has opened"),
        ('order_by="to_date desc", limit=1)', "the latest of them"),
        ("rules.review_title(plan.year, plan.get(\"branch\"), plan.get(\"department\"), plan.name,",
         "titled by the tested rule")):
    if needle not in board_glue:
        fail.append("talent_board.py: %s (%r not found)" % (why, needle))
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef start_review\(', board_glue) \
        or "_check_access()" not in body_of(board_glue, "start_review"):
    fail.append("talent_board.start_review: a whitelisted POST, for HR and the Talent Council only")
board_js = read("hrms_addon", "hrms_addon", "page", "talent_board", "talent_board.js")
for needle, why in (
        ('grid: ["Nine-box", "get_board", ["plan", "review", "branch", "department", "grade"]]',
         "the nine-box view reads the plan picked"),
        ('plan: field("plan", "Appraisal Plan", "Appraisal Plan", {', "the plan is the first picker"),
        ("if (!this.quiet) this.pick_plan();", "picking a plan lets the review picked before go"),
        ('this.fields.review.set_value("").then(() => {', "and shows the plan's latest review"),
        ("return plan ? { filters: { appraisal_plan: plan } } : {};", "the review picker offers the plan's reviews"),
        ('const shown = { review: data.review.name, plan: data.review.appraisal_plan || "" };',
         "the pickers say which review and plan are on the board"),
        ('frappe.xcall("hrms_addon.hrms_addon.talent_board.start_review", { appraisal_plan: plan.name })',
         "Start Talent Review starts the plan's review"),
        ("data.can_start ?", "for whoever may")):
    if needle not in board_js:
        fail.append("talent_board.js: %s (%r not found)" % (why, needle))
if board_js.index("plan: field(") > board_js.index("review: field("):
    fail.append("the Appraisal Plan picker comes before the Talent Review picker")
if 'employee.status not in ("Active", "Suspended")' not in body_of(glue, "_draft_placements"):
    fail.append("drafting places a suspended employee too: they are still on the staff")
print("Oct 7: the appraisal plan picked on the board, its review shown or started from it; the suspended placed")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL TALENT MANAGEMENT CHECKS PASSED")
