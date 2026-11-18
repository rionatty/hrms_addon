"""Verify the entry sheets and the evaluation's depth (the LMS rebuild, 18 Nov 2026), without a bench:

    python scripts/verify_learning_sheets.py

  1  the rules: a skills grid's rows, what a sheet refuses, the pre and post tests and the attempt that counts,
     level 2's figures, the parts and the tally a job keeps
  2  the paper: the three sheets and their rows carry what the rules and the glue name; HR's lists of KPIs and of
     the kinds of test; the levels a programme is evaluated at; the trainee's test fields on Frappe HR's result
  3  the glue and the wiring: worked in the background a hundred rows at a time, a failing row undone alone, the
     supervisor's own sheets only, the menus
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
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


R = load("learning_sheets_rules")
DR = load("learning_delivery_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
PEOPLE = [{"name": "E1", "employee_name": "Ann"}, {"name": "E2", "employee_name": "Ben"}]
rows = R.skills_rows(PEOPLE, ["Extruder", "5S"], {("E1", "5S"): "3 Works Under Supervision"}, [("E2", "5S")])
check("a skills sheet's rows: each employee against each skill, the level now, those there already left out",
      [(row["employee"], row["skill"], row["current_level"]) for row in rows]
      == [("E1", "Extruder", None), ("E1", "5S", "3 Works Under Supervision"), ("E2", "Extruder", None)], rows)
check("a skills sheet refuses an employee and skill twice, the assessor assessing themselves, nothing given on submit",
      R.skills_errors([{"employee": "E1", "skill": "5S"}, {"employee": "E1", "skill": "5S"}])
      and R.skills_errors([{"employee": "E1", "skill": "5S", "level": "4"}], assessor="E1") == ["Nobody assesses themselves."]
      and R.skills_errors([{"employee": "E1", "skill": "5S"}], submitting=True) == ["Give a level on at least one row."]
      and not R.skills_errors([{"employee": "E1", "skill": "5S", "level": "4"}], assessor="E9", submitting=True))
GRID = R.grid(rows)
check("the grid: the employees down, the skills across, each cell its row",
      GRID["employees"] == [("E1", "Ann"), ("E2", "Ben")] and GRID["skills"] == ["Extruder", "5S"]
      and GRID["cells"][("E2", "Extruder")] == 2)
check("trainees grouped by the supervisor who reviews them, those with none left out",
      R.review_groups([{"employee": "A", "supervisor": "S"}, {"employee": "B", "supervisor": "S"},
                       {"employee": "C"}]) == {"S": ["A", "B"]})
ANSWERS = ("applied", "behaviour", "competency")
check("a review sheet: every trainee answered, a reason where it was not applied",
      R.review_sheet_errors([{"employee": "A", "applied": "Applied in Full", "behaviour": "4"}], ANSWERS)
      == ["Answer every question for A."]
      and R.review_sheet_errors([{"employee": "A", "applied": "Not Applied", "behaviour": "1", "competency": "x"}],
                                ANSWERS) == ["Say why A has not applied it."]
      and not R.review_sheet_errors([{"employee": "A", "applied": "Applied in Part", "behaviour": "3",
                                      "competency": "Improved"}], ANSWERS))
check("marks as a share of what they are out of", R.percent_of(15, 20) == 75.0 and R.percent_of(None, 20) is None
      and R.percent_of(40, 0) == 40.0)
check("a trainee's row: pre and post as percentages, the gain, passed at the pass mark",
      R.result_row({"pre_test": 8, "post_test": 16}, 20, 70) == {"pre_percent": 40.0, "post_percent": 80.0, "gain": 40.0,
                                                                  "passed": 1}
      and R.result_row({"post_test": 13}, 20, 70)["passed"] == 0 and R.result_row({}, 20, 70)["passed"] is None)
ATTEMPTS = [{"name": "r1", "employee": "A", "attempt": 1}, {"name": "r2", "employee": "A", "attempt": 2},
            {"name": "r3", "employee": "B"}]
check("the attempt that counts: the highest number", {key: row["name"] for key, row in R.latest_attempts(ATTEMPTS).items()}
      == {"A": "r2", "B": "r3"})
check("a results sheet refuses one who did not attend, an attempt twice, marks outside what they are out of",
      R.results_errors([{"employee": "X"}], {"A"}, 20) == ["X did not attend this training."]
      and R.results_errors([{"employee": "A"}, {"employee": "A", "attempt": 1}], {"A"}, 20)
      == ["A's attempt 1 is listed twice."]
      and R.results_errors([{"employee": "A", "post_test": 25}], {"A"}, 20) == ["A's marks must be between 0 and 20."]
      and not R.results_errors([{"employee": "A", "post_test": 20}, {"employee": "A", "attempt": 2}], {"A"}, 20))
check("level 2 over a set of results: the average pre and post, the gain, the pass rate",
      R.learning_figures([{"pre": 40, "post": 80, "passed": True}, {"pre": 60, "post": 70, "passed": False},
                          {"post": 90, "passed": True}])
      == {"pre_test": 50.0, "post_test": 80.0, "gain": 25.0, "pass_rate": 66.7})
check("a job's parts of a hundred and its tally", [len(part) for part in R.parts(range(205))] == [100, 100, 5]
      and R.tally(["Created", "Updated", "Created", "Failed", "Skipped"])
      == {"created": 2, "updated": 1, "skipped": 1, "failed": 1})

# ── 2. The paper ──────────────────────────────────────────────────────
options = lambda spec, field: [value for value in spec[field]["options"].split("\n") if value]  # noqa: E731
for sheet, row, link in (("Skills Assessment Sheet", "Skills Assessment Sheet Row", "assessment"),
                         ("Application Review Sheet", "Application Review Sheet Row", "review"),
                         ("Training Results Sheet", "Training Results Sheet Row", "result_row")):
    spec = doctype(sheet)
    check("%s is submitted, then worked in the background" % sheet, spec.get("is_submittable") == 1)
    check("%s shows how far it is" % sheet, {"status", "rows_done", "created", "updated", "failed", "result_log"}
          <= set(fields(sheet)) and options(fields(sheet), "status") == list(R.SHEET_STATUSES))
    check("%s's rows say what was done with each" % sheet, {"result", "message", link} <= set(fields(row))
          and options(fields(row), "result") == list(R.ROW_RESULTS)
          and all(fields(row)[name].get("allow_on_submit") for name in ("result", "message", link)))
    check("%s's rows table is rows" % sheet, fields(sheet)["rows"]["options"] == row)
skills = fields("Skills Assessment Sheet")
check("a skills sheet: its section, its skills to pick, the grid", {"branch", "work_section", "department", "assessed_on",
                                                                    "assessor", "skills", "grid_html", "purpose"}
      <= set(skills) and skills["skills"]["fieldtype"] == "Table MultiSelect"
      and options(skills, "purpose") == list(R.PURPOSES))
LEVELS = load("competency_rules").LEVEL_NAMES
check("the skills sheet's levels are the competency scale's", options(fields("Skills Assessment Sheet Row"), "level")
      == list(LEVELS))
review = fields("Application Review Sheet Row")
check("the review sheet's answers are the review's own", options(review, "applied") == [n for n, _v in DR.APPLIED]
      and options(review, "behaviour") == [n for n, _v in DR.BEHAVIOUR]
      and options(review, "competency") == [n for n, _v in DR.COMPETENCY])
check("a supervisor answers their sheet; HR raise it", any(row["role"] == "Supervisor" and row.get("submit")
                                                           and not row.get("create")
                                                           for row in doctype("Application Review Sheet")["permissions"]))
results = fields("Training Results Sheet Row")
check("a results row: the attempt, the kind of test, the pre and post test, the gain, passed",
      {"attempt", "assessment_type", "pre_test", "post_test", "gain", "passed"} <= set(results)
      and results["gain"].get("read_only") and results["passed"].get("read_only"))
check("the assessment made by a sheet points back at it", "assessment_sheet" in fields("Competency Assessment"))
kpi = fields("Training KPI")
check("a KPI: its unit, which way is better, its source and measure, its worth a unit and its window",
      {"kpi_name", "unit", "better", "source", "shift_measure", "value_per_unit", "window_days", "is_active"} <= set(kpi)
      and options(kpi, "source") == ["Manual", "Shift Reports"])
check("the kinds of test are HR's list", "assessment_type" in fields("Assessment Type"))
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
HOOKS = read("hrms_addon", "hooks.py")
for dt_name, field in (("Training Result Employee", "custom_pre_test"), ("Training Result Employee", "custom_gain"),
                       ("Training Result Employee", "custom_attempt"),
                       ("Training Result Employee", "custom_assessment_type"),
                       ("Training Program", "custom_level_reaction"), ("Training Program", "custom_level_learning"),
                       ("Training Program", "custom_level_behaviour"), ("Training Program", "custom_level_impact")):
    row = next((item for item in custom if item["dt"] == dt_name and item["fieldname"] == field), None)
    check("%s has %s, shipped" % (dt_name, field), row and '"%s-%s"' % (dt_name, field) in HOOKS)
    if row and dt_name == "Training Result Employee":
        check("%s changes after the result is submitted" % field, row.get("allow_on_submit") == 1)
    if row and dt_name == "Training Program":
        check("%s is on unless turned off" % field, row.get("default") == "1")
check("the levels' fields are the rules'", [field for _level, field in DR.LEVELS]
      == ["custom_level_reaction", "custom_level_learning", "custom_level_behaviour", "custom_level_impact"])

# ── 3. The glue and the wiring ────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_sheets.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("worked in the background on the long queue, once per sheet",
      'queue="long"' in GLUE and 'job_id="%s::%s" % (doc.doctype, doc.name)' in GLUE and "deduplicate=True" in GLUE)
check("a hundred rows at a time, each part committed, the progress kept",
      "rules.parts(doc.get(\"rows\") or [])" in GLUE and "rows_done=len(results)), update_modified=False, commit=True" in GLUE)
check("a failing row undone alone: the part's other rows stand",
      'frappe.db.savepoint("learning_sheet_row")' in GLUE and 'frappe.db.rollback(save_point="learning_sheet_row")' in GLUE)
check("a stopped sheet says why, and may be run again", "rules.FAILED" in GLUE and "def run_again(" in GLUE)
check("an assessment made again is updated, not made twice", '"assessed_on": str(getdate(doc.assessed_on))' in GLUE
      and "rules.UPDATED" in GLUE)
check("the attempt that counts goes on the result; the result submitted once filled",
      "rules.latest_attempts(" in GLUE and "result.submit()" in GLUE)
check("a supervisor lists and answers their own sheets only",
      '"`tab{0}`.`reviewer` = {1}"' in GLUE and 'doc.get("reviewer") == user' in GLUE)
check("reassessments falling due put on one sheet a section", "def reassessment_sheets(due):" in GLUE
      and "rules.REASSESSMENT" in GLUE)
for name in ("skill_rows", "trainees", "run_again"):
    check("%s is whitelisted" % name, re.search(r"@frappe\.whitelist\([^)]*\)\ndef %s\(" % name, GLUE))
for needle in ('"Application Review Sheet": "hrms_addon.hrms_addon.learning_sheets.review_sheet_query"',
               '"Application Review Sheet": "hrms_addon.hrms_addon.learning_sheets.review_sheet_permission"',
               '"hrms_addon.hrms_addon.learning_delivery.programme_validate"',
               '"/assets/hrms_addon/js/hrms_addon_learning.js"', "hrms_addon.patches.v1_0.lms_training_kpis"):
    check("wiring: %s" % needle, needle in HOOKS or needle in read("hrms_addon", "patches.txt"))
DELIVERY = read("hrms_addon", "hrms_addon", "learning_delivery.py")
check("the supervisor's reviews of a session on one sheet", "learning_sheets.review_sheet_for(" in DELIVERY)
check("evaluation forms only where the programme is evaluated by its trainees",
      'levels["reaction"]' in read("hrms_addon", "hrms_addon", "training.py"))
check("the effectiveness report reads the pre and post tests and the weighted KPIs",
      "sheets_rules.learning_figures(" in read("hrms_addon", "hrms_addon", "report", "training_effectiveness",
                                               "training_effectiveness.py"))
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Skills Assessment Sheet", "Application Review Sheet", "Training Results Sheet", "Training KPI",
              "Assessment Type"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)
for name in ("Skills Assessment Sheet", "Training Results Sheet"):
    check("%s takes a Data Import" % name, doctype(name).get("allow_import") == 1)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_sheets: OK")
