"""Verify potential rated by criterion and by rater (potential_rules.py,
potential.py), without a bench:

    python scripts/verify_talent_potential.py

The talent blueprint, sections 2 and 3: "Potential Assessment: Ability,
aspiration, engagement scores, evidence | Nine Box Placement"; "Read
competency levels and learning agility" from L&D. The rules (criteria and
their levels, one rater's weighted mean, the raters together and their
disagreement, the evidence and the score it suggests, the old three numbers
moved across), the doctypes, and the glue reaching L&D's Competency
Assessment and the placement.
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
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def fields(name):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))
    return {row["fieldname"]: row for row in spec["fields"]}, spec


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


R = load("potential_rules")
print("loaded potential_rules.py without Frappe")

# ── 1. The criteria ───────────────────────────────────────────────────
check("four criteria to start with, learning agility among them, each with five levels",
      [spec["criterion"] for spec in R.SEED] == ["Ability", "Aspiration", "Engagement", "Learning Agility"]
      and all(len(spec["levels"]) == 5 for spec in R.SEED))
check("ability reads competency levels, learning agility how fast they rise",
      {spec["criterion"]: spec["evidence_from"] for spec in R.SEED}["Ability"] == R.LEVELS
      and {spec["criterion"]: spec["evidence_from"] for spec in R.SEED}["Learning Agility"] == R.GROWTH)
check("a criterion's levels 1 to 5, each once; a weight not below nought",
      R.criterion_errors({"weight": 1, "levels": [{"level": n} for n in range(1, 6)]}) == []
      and "Level 3 is described twice." in R.criterion_errors({"weight": 1, "levels": [{"level": 3}, {"level": 3}]})
      and "Levels run from 1 to 5." in R.criterion_errors({"levels": [{"level": 6}]})
      and "A weight is 0 or more." in R.criterion_errors({"weight": -1}))
check("weights of the active criteria above nought",
      R.weights_of([{"name": "A", "weight": 2}, {"name": "B", "weight": 0}, {"name": "C", "weight": 1, "active": 0}])
      == {"A": 2.0})

# ── 2. One rater ──────────────────────────────────────────────────────
WEIGHTS = {"Ability": 2.0, "Aspiration": 1.0, "Engagement": 1.0}
full = {"placement": "TP-1", "rater": "hod@x", "rater_role": "Head of Department",
        "ratings": [{"criterion": "Ability", "score": 4}, {"criterion": "Aspiration", "score": 3},
                    {"criterion": "Engagement", "score": 5}]}
check("a complete assessment", R.assessment_errors(full, WEIGHTS) == [])
check("a criterion missed, rated twice, out of range: refused", (
    "Rate Engagement as well." in R.assessment_errors(dict(full, ratings=full["ratings"][:2]), WEIGHTS)
    and "Ability is rated twice." in R.assessment_errors(dict(full, ratings=full["ratings"] + [
        {"criterion": "Ability", "score": 2}]), WEIGHTS)
    and "Aspiration is rated 1 to 5." in R.assessment_errors(dict(full, ratings=[
        {"criterion": "Ability", "score": 4}, {"criterion": "Aspiration", "score": 7},
        {"criterion": "Engagement", "score": 5}]), WEIGHTS)))
check("a rater is somebody, in a known role",
      "An assessment is somebody's: say who rates." in R.assessment_errors(dict(full, rater=None), WEIGHTS)
      and R.assessment_errors(dict(full, rater_role="Friend"), WEIGHTS) != [])
check("the weighted mean: ability counting twice, 4,3,5 makes 4.0",
      R.weighted_mean(full["ratings"], WEIGHTS) == 4.0 and R.weighted_mean(full["ratings"], {}) == 4.0)
check("a criterion no longer kept still counts once", R.weighted_mean([{"criterion": "Old", "score": 2},
                                                                      {"criterion": "Ability", "score": 5}],
                                                                     {"Ability": 1.0}) == 3.5)
check("nothing rated is no mean", R.weighted_mean([], WEIGHTS) is None)

# ── 3. The raters together ────────────────────────────────────────────
two = [{"rater": "a", "ratings": [{"criterion": "Ability", "score": 5}, {"criterion": "Aspiration", "score": 5},
                                  {"criterion": "Engagement", "score": 5}]},
       {"rater": "b", "ratings": [{"criterion": "Ability", "score": 3}, {"criterion": "Aspiration", "score": 3},
                                  {"criterion": "Engagement", "score": 3}]}]
found = R.placement_potential(two, WEIGHTS)
check("the raters averaged: 5 and 3 make 4, eighty out of a hundred", found["mean"] == 4.0 and found["score"] == 80.0
      and found["raters"] == 2, found)
check("two points apart is a disagreement at the default spread", found["spread"] == 2.0 and found["disagree"] == 1)
check("a wider spread allowed is no disagreement", R.placement_potential(two, WEIGHTS, 2.5)["disagree"] == 0)
check("one rater never disagrees", R.placement_potential(two[:1], WEIGHTS)["disagree"] == 0)
check("each criterion's average, lowest and highest across the raters",
      [(row["criterion"], row["average"], row["lowest"], row["highest"], row["raters"]) for row in found["criteria"]]
      == [("Ability", 4.0, 3.0, 5.0, 2), ("Aspiration", 4.0, 3.0, 5.0, 2), ("Engagement", 4.0, 3.0, 5.0, 2)])
check("nobody rated: no score, no raters", R.placement_potential([], WEIGHTS)["score"] is None
      and R.placement_potential([], WEIGHTS)["raters"] == 0)
check("a 3 is sixty and a 4 eighty, the lines of the potential bands", R.TO_HUNDRED == 20.0)

# ── 4. The evidence ───────────────────────────────────────────────────
check("competency levels averaged as the suggestion", R.from_levels([4, 3, 5]) == 4.0 and R.from_levels([]) is None)
check("the appraisal's competencies out of ten halved, within 1 to 5",
      R.from_appraisal([8, 6]) == 3.5 and R.from_appraisal([1]) == 1.0 and R.from_appraisal([]) is None)
history = [{"skill": "Extruder", "level": 2, "assessed_on": "2026-01-10"},
           {"skill": "Extruder", "level": 4, "assessed_on": "2026-09-10"},
           {"skill": "Safety", "level": 3, "assessed_on": "2026-03-01"},
           {"skill": "Safety", "level": 3, "assessed_on": "2026-10-01"},
           {"skill": "Printing", "level": 1, "assessed_on": "2024-01-01"},
           {"skill": "Printing", "level": 5, "assessed_on": "2026-05-01"}]
check("levels gained in a year: only skills assessed twice within it",
      R.levels_gained(history, "2026-11-18") == 2 and R.levels_gained(history[:1], "2026-11-18") is None)
check("levels gained as learning agility", [R.from_growth(n) for n in (None, 0, 1, 2, 4)] == [None, 2.0, 3.0, 4.0, 5.0])
score, source, evidence = R.suggestion(R.LEVELS, levels=[{"skill": "Extruder", "level": 4},
                                                         {"skill": "Safety", "level": 3}])
check("ability from L&D's levels, sourced as the Competency Assessment",
      (score, source) == (3.5, R.COMPETENCY) and "Extruder 4" in evidence)
score, source, _evidence = R.suggestion(R.LEVELS, levels=[], appraisal=[{"competency": "Teamwork", "level": 8}])
check("nobody assessed in L&D: the appraisal's competencies instead", (score, source) == (4.0, R.APPRAISAL))
check("no evidence at all: the rater's own", R.suggestion(None) == (None, R.MANUAL, None)
      and R.suggestion(R.GROWTH, history=[], today="2026-11-18") == (None, R.MANUAL, None))
check("a score changed from the suggestion is the rater's own",
      R.source_after_edit(4, 3.5, R.COMPETENCY) == R.MANUAL and R.source_after_edit(3.5, 3.5, R.COMPETENCY)
      == R.COMPETENCY and R.source_after_edit(3, None, None) == R.MANUAL)

# ── 5. The old three numbers ──────────────────────────────────────────
moved = R.from_old({"ability": 8, "aspiration": 6, "engagement": 7})
check("ability, aspiration and engagement out of ten become 1 to 5 ratings",
      [(row["criterion"], row["score"]) for row in moved] == [("Ability", 4.0), ("Aspiration", 3.0),
                                                               ("Engagement", 3.5)])
old_score = (8 + 6 + 7) / 3.0 * 10
new_score = R.placement_potential([{"rater": "lm", "ratings": moved}], {})["score"]
check("the potential they make is the same as before", round(old_score, 2) == new_score, (old_score, new_score))

# ── 6. The doctypes ───────────────────────────────────────────────────
assessment, spec = fields("Potential Assessment")
check("an assessment: the placement, the rater and the role they rate as, the ratings, submitted",
      {"placement", "employee", "talent_review", "rater", "rater_role", "assessed_on", "ratings", "weighted_score",
       "potential_score"} <= set(assessment) and spec.get("is_submittable") == 1
      and assessment["ratings"]["options"] == "Potential Rating" and assessment["rater"].get("read_only"))
rating, _spec = fields("Potential Rating")
check("a rating: the criterion as a link, the score, the evidence, where it came from",
      rating["criterion"]["options"] == "Potential Criterion" and {"score", "evidence", "source", "suggested_score",
                                                                   "descriptor"} <= set(rating)
      and rating["source"]["options"].split("\n") == list(R.SOURCES))
criterion, spec = fields("Potential Criterion")
check("a criterion: its weight, whether active, where its evidence comes from, its five levels",
      {"criterion_name", "weight", "active", "evidence_from", "levels"} <= set(criterion)
      and criterion["levels"]["options"] == "Potential Criterion Level"
      and set(criterion["evidence_from"]["options"].split("\n")) - {""} == set(R.EVIDENCE_FROM))
placement, _spec = fields("Talent Placement")
check("the placement keeps no typed potential: the raters, their mean and spread, and each criterion",
      not {"ability", "aspiration", "engagement"} & set(placement)
      and {"raters", "potential_mean", "rater_spread", "raters_disagree", "potential_summary"} <= set(placement)
      and all(placement[name].get("read_only") for name in ("raters", "potential_mean", "rater_spread",
                                                             "raters_disagree", "potential_summary")))

# ── 7. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "potential.py")
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
check("one assessment a rater a placement", "has already assessed this placement" in body_of(GLUE, "assessment_validate"))
check("the rater is whoever records it", 'doc.rater = frappe.session.user' in body_of(GLUE, "assessment_validate"))
check("submitted or cancelled, the placement reads its potential again",
      "refresh_placement(doc.placement)" in body_of(GLUE, "assessment_on_submit")
      and "refresh_placement(doc.placement)" in body_of(GLUE, "assessment_on_cancel"))
check("the placement's potential from the submitted assessments only",
      '"docstatus": 1' in body_of(GLUE, "submitted") and "rules.placement_potential(" in body_of(GLUE, "fill_placement"))
check("L&D's Competency Assessments read as evidence, the latest of each skill counting",
      'COMPETENCY = "Competency Assessment"' in GLUE and 'row.status != "Superseded"' in body_of(GLUE, "_competency"))
check("the placement takes its potential from here", "potential.fill_placement(doc)" in body_of(TALENT, "_fill_potential"))
check("new_assessment and read_evidence are whitelisted and check the placement may be read",
      re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef new_assessment\(', GLUE) is not None
      and re.search(r"@frappe\.whitelist\(\)\ndef read_evidence\(", GLUE) is not None
      and GLUE.count('check_permission("read")') >= 2)
check("a line manager sees the assessments of their team and those they made (talent_access)",
      '"Potential Assessment": {"employee": "employee", "department": "department", "own": False, "rater": "rater"}'
      in read("hrms_addon", "hrms_addon", "talent_access_rules.py"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_talent_potential: OK")
