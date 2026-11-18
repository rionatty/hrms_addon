"""Verify LMS phase 4, capability (17 Nov 2026), without a bench:

    python scripts/verify_competency.py

The blueprint's section 4.8 and the plant's Skills Matrix on Frappe HR's own Skill master: an employee's level in a
skill, 1 to 5, against the level it needs of them (their job title's, else the skill's, else 4); the newest
assessment counts; competent, a gap, a certificate needed or a reassessment due; each skill's cover, from no cover
to enough for every shift; and the HR Excellence scorecard's skills pillar reading it.

  1  the rules: levels, the level needed, the next assessment, where one stands, which counts, cover, coverage
  2  the paper: the assessment, the Skill's and the job title's fields, the settings, the reports
  3  the glue: what an assessment takes and settles, the daily round, what the scorecard reads
  4  wiring
"""
import datetime
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
D = datetime.date


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


def options(name, field):
    return [option for option in (fields(name)[field].get("options") or "").split("\n") if option]


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


R = load("competency_rules")
L = load("learning_rules")
E = load("excellence_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("levels: by name or number, 1 to 5 only", R.level_of("4 Competent Independently") == 4 and R.level_of(2) == 2
      and R.level_of("6") is None and R.level_of(None) is None and R.level_of("Expert") is None)
check("levels: a number's name", R.level_name(5) == "5 Can Train and Supervise" and R.level_name(None) is None)
check("level needed: the job title's, else the skill's, else 4",
      R.required_level({"custom_required_level": "3 Works Under Supervision"}, {"Supervisor": "5 Can Train and Supervise"},
                       "Supervisor") == 5
      and R.required_level({"custom_required_level": "3 Works Under Supervision"}, {}, "Operator") == 3
      and R.required_level({}, {}, "Operator") == 4)
check("reassessed a year on unless set", R.next_due(D(2026, 1, 31), None) == D(2027, 1, 31)
      and R.next_due(D(2026, 1, 31), 6) == D(2026, 7, 31) and R.next_due(D(2026, 8, 31), 6) == D(2027, 2, 28)
      and R.next_due(None, 12) is None)
check("where one stands: a certificate missing first, then a reassessment overdue, then the level", (
    R.status_of(4, 4, D(2027, 1, 1), D(2026, 11, 17), True, False),
    R.status_of(2, 4, D(2026, 11, 16), D(2026, 11, 17)),
    R.status_of(4, 4, D(2026, 11, 17), D(2026, 11, 17)),
    R.status_of(3, 4, D(2027, 1, 1), D(2026, 11, 17)),
    R.status_of(5, 4, None, D(2026, 11, 17), True, True)) == (R.CERTIFICATE, R.REASSESS, R.COMPETENT, R.GAP,
                                                              R.COMPETENT))
ROWS = [{"name": "A1", "employee": "E1", "skill": "S1", "assessed_on": D(2026, 1, 1), "creation": "2026-01-01 09:00"},
        {"name": "A2", "employee": "E1", "skill": "S1", "assessed_on": D(2026, 6, 1), "creation": "2026-06-01 09:00"},
        {"name": "A3", "employee": "E1", "skill": "S1", "assessed_on": D(2026, 6, 1), "creation": "2026-06-02 09:00"},
        {"name": "A4", "employee": "E2", "skill": "S1", "assessed_on": D(2026, 3, 1), "creation": "2026-11-01 09:00"},
        {"name": "A5", "employee": "E1", "skill": "S2", "assessed_on": D(2025, 3, 1), "creation": "2025-03-01 09:00"},
        {"name": "A6", "employee": "E2", "skill": "S1", "assessed_on": D(2026, 1, 1), "creation": "2026-12-01 09:00"}]
NOW = R.current(ROWS)
check("the newest counts: by the day assessed, then the one made last",
      {key: row["name"] for key, row in NOW.items()} == {("E1", "S1"): "A3", ("E2", "S1"): "A4", ("E1", "S2"): "A5"},
      {key: row["name"] for key, row in NOW.items()})
check("cover: none, one, fewer than the people needed per shift times the shifts, enough",
      [R.cover(count) for count in (None, 0, 1, 2, 3, 4, 9)]
      == [R.NOT_ASSESSED, R.NO_COVER, R.SINGLE, R.THIN, R.THIN, R.OK, R.OK]
      and R.cover(2, {"cover_per_shift": 1, "cover_shifts": 2}) == R.OK)
check("coverage: competent over assessed, the superseded left out", R.coverage(
    [{"status": R.COMPETENT}, {"status": R.GAP}, {"status": R.SUPERSEDED}, {"status": R.REASSESS}]) == (1, 3))
check("what an assessment refuses", R.assessment_errors({"level": "7", "assessed_on": D(2026, 11, 18),
                                                         "assessed_by": "E1", "employee": "E1"}, D(2026, 11, 17))
      == ["Pick a level from 1 to 5.", "An assessment cannot be dated ahead.", "Nobody assesses themselves."])
check("settings: the cover's defaults are the LMS settings'", (L.DEFAULTS["cover_per_shift"],
                                                               L.DEFAULTS["cover_shifts"]) == (2, 2)
      and R.DEFAULTS == {"cover_per_shift": 2, "cover_shifts": 2})
S = E.settings_from({})
CARD = E.pillars({"totals": E.totals([], S), "coverage": (8, 10), "competency": (6, 10), "critical": (2, 4)}, S)
SKILLS = next(pillar for pillar in CARD["pillars"] if pillar["key"] == "skills")
check("HR Excellence: skills is training done, competency and critical competency against 80%",
      SKILLS["score"] == round((100 + 75 + 62.5) / 3, 1), SKILLS["score"])
KPIS = {label: value for label, value, _target, _status in CARD["kpis"]["skills"]}
check("HR Excellence: the competency figures on the skills pillar", (KPIS["Skills at the Level Needed"],
                                                                      KPIS["Critical Skills at the Level Needed"])
      == (0.6, 0.5), KPIS)

# ── 2. The paper ──────────────────────────────────────────────────────
A = fields("Competency Assessment")
check("paper: the assessment's levels and statuses are the rules'", options("Competency Assessment", "level")
      == list(R.LEVEL_NAMES) and options("Competency Assessment", "status") == list(R.STATUSES))
check("paper: what the glue sets is on the assessment", {
    "employee", "employee_name", "designation", "branch", "department", "company", "work_section", "skill",
    "critical", "level", "required_level", "gap", "assessed_by", "assessed_by_name", "assessed_on", "next_due",
    "status", "induction_done", "training_event", "evidence"} <= set(A))
check("paper: worked out, not typed", all(A[name].get("read_only") for name in (
    "employee_name", "designation", "branch", "work_section", "company", "critical", "required_level", "gap",
    "next_due", "status")))
check("paper: a supervisor assesses", any(row["role"] == "Supervisor" and row.get("create") and row.get("write")
                                          for row in doctype("Competency Assessment")["permissions"]))
CUSTOM = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
check("paper: the Skill's fields", all("Skill-custom_" + name in CUSTOM for name in (
    "competency_section", "skill_type", "branch", "work_section", "critical", "competency_cb", "required_level",
    "reassess_months", "certification")) and CUSTOM["Skill-custom_skill_type"]["options"].split("\n")[1:]
      == list(R.SKILL_TYPES) and CUSTOM["Skill-custom_certification"]["options"] == "Certification")
check("paper: a job title's own level", CUSTOM["Designation Skill-custom_required_level"]["options"].split("\n")[1:]
      == list(R.LEVEL_NAMES))
SETTINGS = fields("Learning Settings")
check("paper: the cover on the LMS settings", int(SETTINGS["cover_per_shift"]["default"]) == 2
      and int(SETTINGS["cover_shifts"]["default"]) == 2)
for name in ("Skills Matrix", "Skills Cover", "Competency Gaps"):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    readers = {row["role"] for row in doctype("Competency Assessment")["permissions"] if row.get("report")}
    check("paper: %s is for those who may report on assessments" % name,
          spec["ref_doctype"] == "Competency Assessment" and {row["role"] for row in spec["roles"]} <= readers,
          {row["role"] for row in spec["roles"]} - readers)

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "competency.py")


def body(name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@frappe)|\Z)" % re.escape(name), GLUE, re.S)
    return found.group(0) if found else ""


check("glue: the assessment takes the employee's place, the level their job title needs, the next date",
      '"custom_work_section"' in body("assessment_validate") and "_role_levels(doc.skill)" in body(
          "assessment_validate") and 'skill.get("custom_reassess_months")' in body("assessment_validate"))
check("glue: a superseded one stays so when edited", "doc.get(\"status\") != rules.SUPERSEDED or doc.is_new()"
      in body("assessment_validate"))
check("glue: the newest counts on save and when one goes", "_settle(doc.employee, doc.skill)" in body(
    "assessment_on_update") and "leaving=doc.name" in body("assessment_on_trash"))
check("glue: a certificate counts while Valid or Due Soon", "[learning_rules.VALID, learning_rules.DUE_SOON]"
      in body("_has_certificate"))
check("glue: the reassessments newly due go on one sheet a section, every certificate read once a run",
      "if status == rules.REASSESS:" in body("daily") and "_valid_pairs(" in body("daily")
      and "learning_sheets.reassessment_sheets(due)" in body("daily"))
check("glue: the reports read the counting assessments through the user's permissions",
      "frappe.get_list(ASSESSMENT" in body("counting_rows") and "rules.SUPERSEDED" in body("counting_rows"))
check("glue: the scorecard reads competency and critical competency", "competency.coverage_for(ids)"
      in read("hrms_addon", "hrms_addon", "excellence.py"))

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("wiring: every day", '"hrms_addon.hrms_addon.competency.daily"' in HOOKS)
check("wiring: the Skill's and the job title's fields ship", all(
    '"%s"' % name in HOOKS for name in CUSTOM if name.startswith(("Skill-custom_", "Designation Skill-custom_"))))
CONTROLLER = read("hrms_addon", "hrms_addon", "doctype", "competency_assessment", "competency_assessment.py")
for method, call in (("validate", "assessment_validate"), ("on_update", "assessment_on_update"),
                     ("on_trash", "assessment_on_trash")):
    check("wiring: %s calls competency.%s" % (method, call), "def %s(self)" % method in CONTROLLER
          and "competency.%s(self)" % call in CONTROLLER and "\ndef %s(" % call in GLUE)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_competency: OK")
