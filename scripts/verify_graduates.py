"""Verify the graduate pipeline in depth (graduate_rules.py, graduates.py),
without a bench:

    python scripts/verify_graduates.py

The talent blueprint, section 7: "30 / 60 / 90 day milestones map to
Appraisal records"; "Rotation child schedules plant/function stints with
objectives"; "Mentor / Rotation Supervisor | Edit assigned trainee rotations
and notes | Assigned trainee only"; the trainee tracker "Cohort, stage,
milestone status, mentor". A Graduate Cohort master and its milestone
template, the rotation supervisor's assessment with criteria and a
recommendation, the mentor's sessions that only the mentor writes, the
discipline, the funnel by cohort.
"""
import importlib.util
import json
import os
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


G = load("graduate_rules")
print("loaded graduate_rules.py without Frappe")

# ── 1. The cohort ─────────────────────────────────────────────────────
check("the template: 30, 60 and 90 days, the last deciding confirmation",
      [(name, days, final) for name, days, final in G.TEMPLATE] == [("30-Day Review", 30, 0), ("60-Day Review", 60, 0),
                                                                    ("90-Day Review", 90, 1)])
check("a trainee's milestones dated from their own start",
      G.milestones_from([], "2026-01-01") == [{"milestone": "30-Day Review", "due_on": "2026-01-31"},
                                               {"milestone": "60-Day Review", "due_on": "2026-03-02"},
                                               {"milestone": "90-Day Review", "due_on": "2026-04-01"}]
      and G.milestones_from([{"milestone": "Six Months", "days_after_start": 182}], "2026-01-01")
      == [{"milestone": "Six Months", "due_on": "2026-07-02"}] and G.milestones_from([], None) == [])
check("a template's milestones in order, each after the start, one deciding",
      G.template_errors([{"milestone": "A", "days_after_start": 30}, {"milestone": "B", "days_after_start": 60,
                                                                      "final": 1}]) == []
      and G.template_errors([{"milestone": "A", "days_after_start": 60}, {"milestone": "B", "days_after_start": 30}])
      != [] and G.template_errors([{"milestone": "A", "days_after_start": 0}]) != []
      and "Only one milestone decides confirmation." in G.template_errors(
          [{"milestone": "A", "days_after_start": 30, "final": 1}, {"milestone": "B", "days_after_start": 60, "final": 1}]))
check("a cohort cannot end before it starts", G.cohort_errors({"start_date": "2026-02-01", "end_date": "2026-01-01"})
      == ["A cohort cannot end before it starts."])

# ── 2. The rotation supervisor's assessment ───────────────────────────
good = {"trainee_program": "GT-1", "rotation": "row-1", "supervisor": "E1", "rotation_supervisor": "E1",
        "criteria": [{"criterion": "Quality of work", "score": 4}, {"criterion": "Teamwork", "score": 3}],
        "recommendation": "Continue Rotation"}
check("a complete assessment", G.rotation_assessment_errors(good) == [])
check("the stint is assessed by its own supervisor",
      "The stint is assessed by its own rotation supervisor." in G.rotation_assessment_errors(dict(good, supervisor="E2")))
check("each criterion 1 to 5, a recommendation of the four",
      G.rotation_assessment_errors(dict(good, criteria=[{"criterion": "x", "score": 9}])) != []
      and G.rotation_assessment_errors(dict(good, recommendation="Promote")) != []
      and G.RECOMMENDATIONS == ("Continue Rotation", "Extend Rotation", "Ready for Placement", "Exit Programme"))
check("the score out of a hundred", G.rotation_score(good["criteria"]) == 70.0 and G.rotation_score([]) is None)
check("what the stint's row says of it", G.rotation_outcome("Extend Rotation", "Careful", "Speed")
      == "Extend Rotation. Strengths: Careful. To develop: Speed")

# ── 3. The mentor's sessions ──────────────────────────────────────────
session = {"mentor": "M", "mentee": "T", "trainee_program": "GT-1", "session_date": "2026-11-10",
           "topics": "Shift handover", "today": "2026-11-18"}
check("a complete session", G.mentoring_errors(session) == [])
check("a session belongs to a trainee or a plan, is held before it is recorded, says what was covered",
      G.mentoring_errors(dict(session, trainee_program=None)) != []
      and "A session is recorded once it is held." in G.mentoring_errors(dict(session, session_date="2026-12-01"))
      and G.mentoring_errors(dict(session, topics=" ")) != []
      and "A mentor does not mentor themselves." in G.mentoring_errors(dict(session, mentee="M")))
check("only the mentor writes their sessions (System Manager aside)",
      G.may_edit_session("M", "M", ["Mentor"]) and not G.may_edit_session("X", "M", ["Mentor", "HR Manager"])
      and G.may_edit_session(None, "M", ["System Manager"]) and not G.may_edit_session(None, "M", ["Mentor"]))

# ── 4. The funnel ─────────────────────────────────────────────────────
funnel = G.funnel([{"cohort": "Intake 2025", "stage": "Confirmed", "n": 3},
                   {"cohort": "Intake 2025", "stage": "Exited", "n": 1},
                   {"cohort": "Intake 2026", "stage": "In Rotation", "n": 5},
                   {"cohort": "Intake 2026", "stage": None, "n": 2}])
check("the funnel by cohort, the latest first, each stage counted, a blank stage as Recruited",
      [row["cohort"] for row in funnel] == ["Intake 2026", "Intake 2025"]
      and funnel[0]["stages"]["Recruited"] == 2 and funnel[0]["total"] == 7
      and funnel[1]["confirmed_share"] == 75.0 and funnel[1]["exited_share"] == 25.0)

# ── 5. The doctypes ───────────────────────────────────────────────────
cohort = fields("Graduate Cohort")
check("a cohort: name, intake, dates, coordinator, its milestones, its figures",
      {"cohort_name", "intake_year", "start_date", "end_date", "coordinator", "milestones", "trainees", "confirmed",
       "exited"} <= set(cohort) and cohort["milestones"]["options"] == "Cohort Milestone")
trainee = fields("Graduate Trainee Program")
check("a trainee's cohort is a Graduate Cohort; their discipline kept",
      trainee["cohort"]["fieldtype"] == "Link" and trainee["cohort"]["options"] == "Graduate Cohort"
      and "discipline" in trainee and {"rotation_assessments", "mentoring_sessions"} <= set(trainee))
assessment = spec_of("Rotation Assessment")
assessment_fields = fields("Rotation Assessment")
check("a rotation assessment: submittable, the trainee, the stint, the supervisor, criteria rows, a recommendation",
      assessment.get("is_submittable") == 1 and {"trainee_program", "rotation", "supervisor", "criteria",
                                                 "overall_score", "recommendation"} <= set(assessment_fields)
      and assessment_fields["criteria"]["options"] == "Rotation Assessment Score")
rotation = fields("Trainee Rotation")
check("the stint names its assessment", rotation["assessment"]["options"] == "Rotation Assessment")
mentoring = spec_of("Mentoring Session")
check("a mentoring session: the mentor writes, HR reads",
      [row["role"] for row in mentoring["permissions"] if row.get("write")] == ["System Manager", "Mentor"]
      and any(row["role"] == "HR Manager" and row.get("read") and not row.get("write") for row in mentoring["permissions"]))
check("Talent Settings keep the rotation criteria", fields("Talent Settings")["rotation_criteria"]["options"]
      == "Talent Rotation Criterion")
check("the milestones' appraisal looked up by an index", fields("Trainee Milestone")["appraisal"].get("search_index"))

# ── 6. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "graduates.py")
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
HOOKS = read("hrms_addon", "hooks.py")
check("a trainee in a cohort gets its milestones once", "graduates.trainee_milestones(doc)" in body_of(TALENT, "trainee_validate")
      and "if doc.get(\"milestones\")" in body_of(GLUE, "trainee_milestones"))
check("an applicant hired into a cohort typed on the way: the cohort made", "graduates.cohort_of_text(" in TALENT)
check("the assessment written onto the stint, the trainee's count kept",
      "frappe.db.set_value(ROTATION, doc.rotation" in body_of(GLUE, "rotation_assessment_on_submit")
      and "_count_rotations(" in body_of(GLUE, "rotation_assessment_on_submit"))
check("cancelled, the stint lets go of what it wrote", '"assessment": None' in body_of(GLUE, "rotation_assessment_on_cancel"))
check("only the mentor writes, on the record and on the list",
      "rules.may_edit_session(" in body_of(GLUE, "session_validate")
      and "rules.may_edit_session(" in body_of(GLUE, "session_has_permission")
      and '"Mentoring Session": "hrms_addon.hrms_addon.graduates.session_has_permission"' in HOOKS
      and '"Mentoring Session": "hrms_addon.hrms_addon.graduates.session_query_conditions"' in HOOKS)
check("a rotation supervisor opens their own assessments",
      '"Rotation Assessment": "hrms_addon.hrms_addon.graduates.rotation_has_permission"' in HOOKS)
check("the funnel counted in one GROUP BY", "group by cohort, workflow_state" in body_of(GLUE, "funnel"))
check("the old cohorts become Graduate Cohort records", "Graduate Cohort" in read("hrms_addon", "patches", "v1_0",
                                                                                  "talent_review_plants.py"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_graduates: OK")
