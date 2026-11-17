"""Verify the talent gaps of the six-files plan (batch 5, 17 Nov 2026), without a bench:

    python scripts/verify_talent_setup.py

The talent blueprint (Luuka_Talent_9Box_Flow, 15 Aug 2026) against what talent.py already did:

  1  the grid as HR keep it: Performance Band, Potential Band, Nine Box,
     Readiness Level and Talent Settings read into the rules, the built-in
     grid where nothing is kept
  2  where a development plan aims (its target box), and how people moved
     between reviews (the Talent Movement report)
  3  the Succession Plan: a year's critical roles reviewed by the council
     as one, each role taking its own step with the plan's
  4  who sees which talent records: a line manager their team, a head of
     department their departments, a mentor their mentees, an employee
     their own development plan
  5  a trainee's milestone falling due raises its appraisal by itself
  6  the paper and the wiring
"""
import importlib.util
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
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


def body_of(source, name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@|# ──)|\Z)" % re.escape(name), source, re.S)
    return found.group(0) if found else ""


R = load("talent_rules")
P = load("succession_plan_approval")
A = load("talent_access_rules")

# ── 1. The grid as HR keep it ─────────────────────────────────────────
built = R.grid_from()
check("nothing kept: the built-in grid, every box as it was",
      built["performance_bands"] == R.PERFORMANCE_BANDS and built["potential_bands"] == R.POTENTIAL_BANDS
      and all(built["boxes"][key]["name"] == spec["name"] for key, spec in R.BOXES.items())
      and built["top_talent"] == R.TOP_TALENT and built["pass_mark"] == R.PASS_MARK)
kept = R.grid_from([{"name": "Low", "score_from": 0}, {"name": "Meeting", "score_from": 65},
                    {"name": "Exceeding", "score_from": 85}],
                   [{"name": "Low", "score_from": 0}, {"name": "Moderate", "score_from": 50},
                    {"name": "High", "score_from": 75}],
                   [{"box": 9, "box_name": "Top Talent", "colour": "Green", "default_action": "Keep and grow",
                     "suggested_decision": "Promotion", "top_talent": 1},
                    {"box": 6, "box_name": "Future Leader", "colour": "Purple", "top_talent": 0}],
                   {"weight_ability": 2, "weight_aspiration": 1, "weight_engagement": 1, "trainee_pass_mark": 70})
check("bands where HR start them: 64 is Low, 65 Meeting, 85 Exceeding",
      [R.performance_band(score, kept) for score in (64, 65, 84.9, 85)] == ["Low", "Meeting", "Meeting", "Exceeding"]
      and R.performance_band(64) == "Meeting")
check("potential bands too", [R.potential_band(score, kept) for score in (49, 50, 75)] == ["Low", "Moderate", "High"])
check("ability weighing twice the others: 10, 5, 5 makes 75, not 66.67",
      R.potential_score({"ability": 10, "aspiration": 5, "engagement": 5}, kept) == 75.0
      and R.potential_score({"ability": 10, "aspiration": 5, "engagement": 5}) == 66.67)
check("a dimension left blank is still not counted, weights or no weights",
      R.potential_score({"ability": 8}, kept) == 80.0 and R.potential_score({}, kept) is None)
check("a box named, coloured and decided as HR keep it; a colour the grid does not have is not taken",
      R.box_for("Exceeding", "High", kept)["name"] == "Top Talent"
      and R.box_for("Exceeding", "High", kept)["decision"] == "Promotion"
      and R.box_for("Meeting", "High", kept)["colour"] == R.BOXES[("Meeting", "High")]["colour"])
check("top talent as HR flag it", R.is_top_talent(6, kept) is False and R.is_top_talent(9, kept)
      and R.is_top_talent(6) and kept["top_talent"] == (8, 9))
check("the board's strips follow the flags: a box no longer top counts in the core",
      R.board([{"box": 6}, {"box": 9}, {"box": 1}], kept)["strips"] == {"top": 1, "core": 1, "attention": 1}
      and R.board([{"box": 6}, {"box": 9}, {"box": 1}])["strips"] == {"top": 2, "core": 0, "attention": 1})
check("a box flagged top talent leaves the attention strip, which never counts anyone twice",
      R.board([{"box": 4}, {"box": 1}], R.grid_from(boxes=[{"box": 4, "top_talent": 1}]))["strips"]
      == {"top": 1, "core": 0, "attention": 1})
check("the board's cells named as kept", R.board([], kept)["cells"][8]["name"] == "Top Talent")
check("the trainee pass mark as kept", R.milestone_outcome(65, pass_mark=kept["pass_mark"]) == "Fail"
      and R.milestone_outcome(65) == "Pass" and R.milestone_outcome(70, final=True, pass_mark=70) == "Final Pass")
check("half a set of bands, or one that does not climb, is not taken",
      R.grid_from([{"name": "Low", "score_from": 0}])["performance_bands"] == R.PERFORMANCE_BANDS
      and R.grid_from([{"name": "Low", "score_from": 0}, {"name": "Meeting", "score_from": 90},
                       {"name": "Exceeding", "score_from": 80}])["performance_bands"] == R.PERFORMANCE_BANDS)
check("weights all nought fall back to equal",
      R.grid_from(settings={"weight_ability": 0, "weight_aspiration": 0, "weight_engagement": 0})["weights"]
      == {"ability": 1.0, "aspiration": 1.0, "engagement": 1.0})
check("bands refused: not from nought, not climbing, at or over a hundred",
      R.band_errors([("Low", 0), ("Meeting", 60), ("Exceeding", 80)]) == []
      and R.band_errors([("Low", 5), ("Meeting", 60), ("Exceeding", 80)]) == ["The lowest band starts at 0."]
      and R.band_errors([("Low", 0), ("Meeting", 80), ("Exceeding", 80)]) == ["Each band starts above the one below it."]
      and R.band_errors([("Low", 0), ("Meeting", 60), ("Exceeding", 100)]) == ["A band starts at 0 or more, and under 100."])
check("each band runs up to where the next starts",
      R.band_ranges([("Exceeding", 80), ("Low", 0), ("Meeting", 60)])
      == [("Low", 0.0, 60.0), ("Meeting", 60.0, 80.0), ("Exceeding", 80.0, 100.0)])
check("the readiness a box suggests, nearest first; none where no level draws from it",
      [R.readiness_for(box, [("Ready Now", 0, [9]), ("Ready in 1-2 Years", 1, [6, 8]), ("Emerging", 2, [3, 5])])
       for box in (9, 8, 6, 5, 1, None)] == ["Ready Now", "Ready in 1-2 Years", "Ready in 1-2 Years", "Emerging", None,
                                            None])

check("a box two levels draw from suggests the nearer",
      R.readiness_for(6, [("Ready in 1-2 Years", 1, [6, 8]), ("Ready Now", 0, [9, 6])]) == "Ready Now")

# ── 2. Targets and movement ───────────────────────────────────────────
check("a plan aims one performance band up, the right-hand column keeps its box",
      [R.target_box(box) for box in range(1, 10)] == [4, 5, 6, 7, 8, 9, 7, 8, 9] and R.target_box(None) is None)
check("a target reached is at least it on both axes",
      R.target_reached(8, 5) and R.target_reached(5, 5) and not R.target_reached(4, 5) and not R.target_reached(7, 5)
      and not R.target_reached(None, 5))
check("movement between reviews", [R.box_movement(*pair) for pair in ((5, 8), (8, 5), (3, 7), (5, 5), (None, 5),
                                                                       (5, None), (None, None))]
      == ["Up", "Down", "Across", "Same", "New", "Not Placed", None])

# ── 3. The Succession Plan ────────────────────────────────────────────
check("the plan's states: Draft, Council Review, Finalised (submitted), Cancelled",
      [state["state"] for state in P.STATES][::1] and {state["state"] for state in P.STATES}
      == {"Draft", "Council Review", "Finalised", "Cancelled"}
      and all(state.get("doc_status") == "1" for state in P.STATES if state["state"] == "Finalised"))
check("HR send it, the council or the HR Manager finalise or return it",
      P.next_states("Draft", ["HR User"]) == [("Send to Council", "Council Review")]
      and P.next_states("Council Review", ["Talent Council"]) == [("Finalise", "Finalised"), ("Return", "Draft")]
      and P.next_states("Council Review", ["HR User"]) == [])
check("sent with no roles, or with roles not yet nominating: refused",
      P.step_errors("Draft", "Council Review", {"positions": []})
      == ["There are no critical roles in the plan. Get the positions first."]
      and "SP-1" in P.step_errors("Draft", "Council Review", {"positions": [{"succession_position": "SP-1",
                                                                               "state": "Draft"}]})[0]
      and not P.step_errors("Draft", "Council Review", {"positions": [{"succession_position": "SP-1",
                                                                         "state": "Nominations Open"}]}))
check("returned without a reason: refused", P.step_errors("Council Review", "Draft", {})
      == ["Write in Return Remarks what must be put right."])
ROLES = [{"succession_position": "SP-1", "state": "Nominations Open"}, {"succession_position": "SP-2",
                                                                         "state": "Council Review"},
         {"succession_position": "SP-3", "state": "Confirmed"}]
check("the roles sent with the plan, and those it confirms", P.to_send(ROLES) == ["SP-1"]
      and P.to_confirm(ROLES) == ["SP-2"])
check("the plan's figures from its roles",
      P.summary([{"coverage": "Covered", "ready_now": 2, "single_person_role": 1}, {"coverage": "Gap"},
                 {"coverage": "At Risk", "ready_now": 1}])
      == {"total_positions": 3, "covered": 1, "at_risk": 1, "gaps": 1, "single_person_roles": 1, "ready_now": 3})
check("the stamps: who sent it, who finalised it; returned, cleared",
      P.compute_stamps("Draft", "Council Review", "hr", "2026-11-17", {})["sent_by"] == "hr"
      and P.compute_stamps("Council Review", "Finalised", "gm", "2026-11-18", {"sent_by": "hr"})["finalised_by"] == "gm"
      and P.compute_stamps("Council Review", "Draft", "gm", "2026-11-18", {"sent_by": "hr"})["sent_by"] is None)
check("the plan's role states are the role workflow's own",
      (P.POSITION_DRAFT, P.POSITION_NOMINATING, P.POSITION_REVIEW, P.POSITION_CONFIRMED)
      == tuple(re.search(r'%s = "([^"]+)"' % name, read("hrms_addon", "hrms_addon", "succession_approval.py")).group(1)
               for name in ("DRAFT", "NOMINATIONS", "COUNCIL_REVIEW", "CONFIRMED")))

# ── 4. Who sees which talent records ──────────────────────────────────
check("HR, the council and those who oversee see everything their roles open",
      not A.narrowed(["HR User"]) and not A.narrowed(["Talent Council"]) and not A.narrowed(["Auditor"])
      and A.narrowed(["Supervisor", "Employee"]) and A.narrowed(["Head of Department"]) and A.narrowed(["Employee"]))
check("a team is everyone below, directly or through others",
      A.team_from("M", {"M": ["A", "B"], "A": ["C"], "C": ["D"], "X": ["Y"]}) == {"A", "B", "C", "D"})
SUP = A.scope_of(["Supervisor", "Employee"], "M", {"A", "C"})
HOD = A.scope_of(["Head of Department"], "H", (), {"Extrusion"})
EMP = A.scope_of(["Employee"], "E", {"Z"}, {"Printing"})
check("an employee has no team and no departments, whatever is passed",
      EMP["team"] == set() and EMP["departments"] == set())
check("a supervisor sees their team's placements, not others'",
      A.visible("Talent Placement", {"employee": "C"}, SUP) and not A.visible("Talent Placement", {"employee": "Q"}, SUP))
check("nobody below HR sees their own placement", not A.visible("Talent Placement", {"employee": "M"}, SUP))
check("a head of department sees their departments'",
      A.visible("Talent Placement", {"employee": "Q", "department": "Extrusion"}, HOD)
      and not A.visible("Talent Placement", {"employee": "Q", "department": "Printing"}, HOD))
check("an employee sees their own development plan, and nothing of anyone else's",
      A.visible("Talent Program", {"employee": "E"}, EMP) and not A.visible("Talent Program", {"employee": "Z"}, EMP))
check("a mentor sees the plans and trainees they mentor; a rotation supervisor theirs",
      A.visible("Talent Program", {"employee": "Q", "mentor": "E"}, EMP)
      and A.visible("Graduate Trainee Program", {"employee": "T", "mentor": "E"}, EMP)
      and A.visible("Graduate Trainee Program", {"employee": "T", "rotation_supervisors": ["E"]}, EMP)
      and not A.visible("Graduate Trainee Program", {"employee": "T", "rotation_supervisors": ["F"]}, EMP))
check("a line manager sees the roles their team holds",
      A.visible("Succession Position", {"incumbent": "A"}, SUP) and not A.visible("Succession Position",
                                                                                 {"incumbent": "Q"}, SUP))
quote = lambda value: "'%s'" % value  # noqa: E731
check("as a list condition: the team, the departments and the person's own",
      A.conditions("Talent Program", SUP, quote)
      == "(`tabTalent Program`.`employee` = 'M' or `tabTalent Program`.`employee` in ('A', 'C') "
         "or `tabTalent Program`.`mentor` = 'M')", A.conditions("Talent Program", SUP, quote))
check("a head of department's placements by department",
      A.conditions("Talent Placement", HOD, quote) == "(`tabTalent Placement`.`department` in ('Extrusion'))")
check("a rotation supervisor's trainees through the rotations",
      "`tabTrainee Rotation` ha_rotation" in A.conditions("Graduate Trainee Program", EMP, quote))
check("nothing to see: a condition nothing meets", A.conditions("Talent Placement", EMP, quote) == "1=0")

# ── 5 and 6. The glue, the paper and the wiring ───────────────────────
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
MASTERS = read("hrms_addon", "hrms_addon", "talent_masters.py")
PLANS = read("hrms_addon", "hrms_addon", "succession_plans.py")
ACCESS = read("hrms_addon", "hrms_addon", "talent_access.py")
HOOKS = read("hrms_addon", "hooks.py")
for needle, what in (('rules.performance_band(year["score"], masters.grid())', "performance read on the bands kept"),
                     ('"engagement": doc.get("engagement")}, masters.grid())', "potential weighed as kept"),
                     ("rules.potential_band(doc.potential_score, masters.grid())", "potential on the bands kept"),
                     ('rules.is_top_talent(box["box"], masters.grid())', "top talent as flagged"),
                     ("rules.is_top_talent(box, masters.grid())", "the programme a box asks for, as flagged"),
                     ('doc.get("flight_risk") in masters.watched_risks()', "the flight risks alerted on"),
                     ('pass_mark=masters.grid()["pass_mark"]', "the trainee pass mark kept"),
                     ('"target_box": _nine_box(rules.target_box(doc.get("box")))', "a plan's target box"),
                     ("    _mark_targets(doc)", "earlier plans told whether their target is reached"),
                     ("masters.suggested_readiness(", "a successor's readiness suggested from their box")):
    check("talent.py: " + what, needle in TALENT)
raise_due = body_of(TALENT, "_raise_due_milestones")
check("talent.py: a milestone falling due moves the trainee to Under Assessment, which raises the appraisal",
      "apply_workflow(trainee, approval.ASSESS)" in raise_due and 'cint(s.get("milestone_lead_days"))' in raise_due
      and '"appraisal": ["is", "not set"]' in raise_due and "approval.IN_ROTATION" in raise_due)
check("talent.py: the rotation supervisor, the mentor and HR told", "_rotation_supervisor(trainee)" in TALENT
      and 'trainee.get("mentor")' in body_of(TALENT, "_tell_milestone_due"))
check("talent.py: the daily run raises due milestones", "_raise_due_milestones()" in body_of(TALENT, "daily"))
check("talent_masters: band names stay, each band above the one below",
      "rules.band_errors(" in body_of(MASTERS, "band_validate") and "Their names stay" in MASTERS)
check("talent_masters: the grid read once a request and forgotten when a master changes",
      'getattr(frappe.local, _CACHE, None)' in MASTERS and "forget()" in body_of(MASTERS, "master_on_update"))
check("talent_masters: seeded once from the built-in grid", all(needle in body_of(MASTERS, "setup_on_migrate") for needle in
                                                                ("rules.BOXES", "READINESS_SEED", "SETTINGS_SEED")))
check("succession_plans: each role takes its own step with the plan's, as the user taking it",
      "apply_workflow(frappe.get_doc(POSITION, name), action)" in PLANS
      and '"Send to Council")' in body_of(PLANS, "plan_on_update") and '"Confirm")' in body_of(PLANS, "plan_on_submit"))
check("succession_plans: no role in two plans of a year", "is already in {1}" in PLANS
      and '"plan_year": doc.get("plan_year")' in PLANS)
check("talent_access: has_permission answers a bool", all(
    "return _allowed(" in body_of(ACCESS, name) for name in ("placement_has_permission", "program_has_permission",
                                                              "position_has_permission", "trainee_has_permission"))
      and "return bool(rules.visible(" in ACCESS)
for doctype_name, short in (("Talent Placement", "placement"), ("Talent Program", "program"),
                            ("Succession Position", "position"), ("Graduate Trainee Program", "trainee")):
    check("hooks: %s narrowed for lists and for each record" % doctype_name,
          '"%s": "hrms_addon.hrms_addon.talent_access.%s_query_conditions"' % (doctype_name, short) in HOOKS
          and '"%s": "hrms_addon.hrms_addon.talent_access.%s_has_permission"' % (doctype_name, short) in HOOKS)
check("hooks: the grid seeded on migrate", '"hrms_addon.hrms_addon.talent_masters.setup_on_migrate"' in HOOKS)
check("talent.py: the plan's workflow built with the others",
      '(succession_plan_approval, "succession plan")' in body_of(TALENT, "setup_workflows_on_migrate"))
check("talent.py: a role cancelled leaves its plans alone", 'PLAN = "Succession Plan"' in TALENT
      and re.search(r"POSITION_RECORDS = \([^)]*\bPLAN\)", TALENT))
for name in ("Performance Band", "Potential Band", "Nine Box", "Readiness Level", "Talent Settings", "Succession Plan"):
    check("%s has a doctype" % name, os.path.exists(os.path.join(APP, "doctype", name.lower().replace(" ", "_"))))
check("bands keep their names and say where they start", {"band_name", "score_from", "score_to"}
      <= set(fields("Performance Band")) and fields("Performance Band")["band_name"].get("set_only_once")
      and {"band_name", "score_from", "score_to"} <= set(fields("Potential Band")))
nine = fields("Nine Box")
check("a box: its number set once, its bands read-only, a colour of the grid's, a decision, top talent",
      nine["box"].get("set_only_once") and nine["performance_band"].get("read_only")
      and nine["colour"]["options"].split("\n") == list(R.COLOURS)
      and nine["suggested_decision"]["options"].split("\n") == list(R.DECISIONS) and "top_talent" in nine)
check("readiness: drawn from boxes", fields("Readiness Level")["boxes"]["options"] == "Readiness Level Box")
settings = fields("Talent Settings")
check("Talent Settings: the weights, the flight risks, the pass mark, the milestones",
      {"weight_ability", "weight_aspiration", "weight_engagement", "watch_high", "watch_medium", "trainee_pass_mark",
       "auto_milestones", "milestone_lead_days"} <= set(settings))
plan = fields("Succession Plan")
check("the plan: year, scope, roles, bench, council, stamps",
      {"plan_year", "company", "branch", "department", "plan_owner", "positions", "total_positions", "gaps",
       "council_remarks", "return_remarks", "sent_by", "finalised_by"} <= set(plan)
      and doctype("Succession Plan").get("is_submittable") == 1)
program = doctype("Talent Program")
program_fields = {field["fieldname"]: field for field in program["fields"]}
check("a plan's target box and whether it is reached sit with the box, at level one",
      program_fields.get("target_box", {}).get("permlevel") == 1
      and program_fields.get("target_reached", {}).get("permlevel") == 1
      and program_fields["target_box"].get("options") == "Nine Box")
level_one = {row["role"] for row in program["permissions"] if row.get("permlevel") == 1}
check("HR and the council read a plan's box; no employee or mentor does",
      {"HR Manager", "HR User", "Talent Council"} <= level_one and not level_one & {"Employee", "Mentor"}, level_one)
movement = read("hrms_addon", "hrms_addon", "report", "talent_movement", "talent_movement.py")
check("Talent Movement names where people sit: for HR and the council", "talent_reports.check_boxes()" in movement
      and "rules.box_movement(" in movement)
check("the plan tracker shows the target box only to those who may read boxes",
      "talent_board.can_see_boxes()" in read("hrms_addon", "hrms_addon", "report", "development_plan_tracker",
                                              "development_plan_tracker.py"))
check("the Performance tab lists top talent at flight risk",
      '"top_talent_at_risk"' in read("hrms_addon", "hrms_addon", "dashboards_rules.py"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_talent_setup: OK")
