"""Verify LMS phase 3, delivery (17 Nov 2026), without a bench:

    python scripts/verify_learning_delivery.py

The blueprint's sections 4.4 and 4.5 on Frappe HR's training documents: attendance and its form (LPL/TRG/FRM03),
the evaluation form (LPL/TRG/FRM05), a supervisor's review of how each trainee applies the training (Kirkpatrick
level 3), the programme's KPIs measured before and after (level 4, from the Shift Reports where they carry it), and
those who did not pass told. Requests keep their approval: the assessment, then the calendar.

  1  the rules: a review's score, when reviews and impact reviews fall due, the KPIs from the Shift Reports, an
     impact's result, attendance, the form's day columns, who newly failed, the four levels
  2  the paper: the doctypes, the programme's KPIs, the settings, the two prints
  3  the glue: who is asked, what is measured, who may answer
  4  wiring: the hooks, the permissions, the reports
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


R = load("learning_delivery_rules")
L = load("learning_rules")
T = load("training_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("level 3: the three answers averaged", R.review_score(
    {"applied": "Applied in Full", "behaviour": "4 Clear Change", "competency": "Partly Improved"}) == 75.0)
check("level 3: no score until all three are in", R.review_score({"applied": "Applied in Full"}) is None)
check("level 3: not applied needs a reason", R.review_errors({"applied": "Not Applied"}) == ["Say why it was not applied."]
      and R.review_errors({"applied": "Not Applied", "comments": "No machine yet"}) == [])
check("level 3: an answer not on the list is refused", R.review_errors({"behaviour": "6 Transformed"}) != [])
check("reviews: raised the set number of days after the session", R.raise_on("2026-10-01 17:00:00", 30) == D(2026, 10, 31))
check("reviews: due once the day comes, not for sessions long before",
      R.due_now(D(2026, 10, 1), 30, D(2026, 10, 31)) and not R.due_now(D(2026, 10, 1), 30, D(2026, 10, 30))
      and R.due_now(D(2026, 10, 1), 30, D(2026, 11, 30)) and not R.due_now(D(2026, 10, 1), 30, D(2026, 12, 1)))
check("reviews: only those marked present", R.reviewees({"employees": [
    {"employee": "A", "attendance": "Present"}, {"employee": "B", "attendance": "Absent"}, {"employee": "C"}]}) == ["A"])
check("impact: the windows before the session began and after it ended",
      R.impact_windows("2026-10-05 08:00:00", "2026-10-06 17:00:00", 30)
      == (D(2026, 9, 5), D(2026, 10, 4), D(2026, 10, 7), D(2026, 11, 5)))
TOTALS = {"count": 4, "waste": 500000.0, "complaints": 0.0, "hours_lost": 12.0, "incidents": 1.0, "actual": 1000.0,
          "on_shift": 40.0}
AVERAGES = {"ppe": 0.95, "attendance": 0.9, "score": 82.5}
check("impact: the KPIs the Shift Reports give", [R.kpi_from_totals(kpi, TOTALS, AVERAGES) for kpi in (
    "Waste Value", "Complaint Value", "Machine Hours Lost", "Safety Incidents", "PPE Compliance %", "Attendance %",
    "Output per Person-Shift", "Shift Score")] == [500000.0, 0.0, 12.0, 1.0, 95.0, 90.0, 25.0, 82.5])
check("impact: none without shift reports, none for Other", R.kpi_from_totals("Waste Value", {"count": 0}, {}) is None
      and R.kpi_from_totals("Other", TOTALS, AVERAGES) is None)
check("impact: waste down is an improvement, PPE down is not",
      R.impact_result("Lower", 500000, 300000) == (-200000, -40.0, R.IMPROVED)
      and R.impact_result("Higher", 95, 90)[2] == R.WORSE and R.impact_result("Higher", 0, 5) == (5, None, R.IMPROVED))
check("impact: no result without both values and a way", R.impact_result("Lower", None, 3) == (None, None, "")
      and R.impact_result(None, 1, 2) == (None, None, "") and R.impact_result("Lower", 3, 3)[2] == R.NO_CHANGE)
check("impact: what it refuses", len(R.impact_errors({
    "kpi": "Other", "baseline_from": D(2026, 9, 5), "baseline_to": D(2026, 9, 1), "after_from": D(2026, 9, 1),
    "after_to": D(2026, 10, 1)})) == 4)
check("impact: the section most trainees work in", R.main_section(["A", "B", "A", None]) == "A"
      and R.main_section([None]) is None and R.main_section(["B", "A"]) == "A")
check("impact: every KPI the rules measure has its way", all(
    name in R.KPI_BETTER for name in R.KPI_FROM_SHIFTS) and R.OTHER not in R.KPI_BETTER)
check("attendance: invited, present, absent, unmarked, no-shows and hours", R.attendance_of({"employees": [
    {"employee": "A", "attendance": "Present"}, {"employee": "B", "attendance": "Absent"},
    {"employee": "C", "attendance": "Present"}, {"employee": "D"}]}, 4) == {
    "invited": 4, "present": 2, "absent": 1, "unmarked": 1, "no_show": 33.3, "hours": 8.0})
check("attendance: no-show rate only over those marked", R.attendance_of({"employees": [{"employee": "A"}]}, 2)[
    "no_show"] is None)
check("FRM03: a signature column a day, one to five", R.day_columns("2026-10-05 08:00:00", "2026-10-07 17:00:00") == 3
      and R.day_columns("2026-10-05 08:00:00", "2026-10-05 17:00:00") == 1
      and R.day_columns("2026-10-01", "2026-10-20") == 5 and R.day_columns(None, None) == 1)
check("level 2: only those newly not passing are told", R.newly_failed(
    [{"employee": "A", "custom_effective": T.NOT_EFFECTIVE}, {"employee": "B", "custom_effective": T.NOT_EFFECTIVE},
     {"employee": "C", "custom_effective": T.EFFECTIVE}],
    [{"employee": "A", "custom_effective": T.NOT_EFFECTIVE}], T.NOT_EFFECTIVE) == ["B"])
FOUR = R.effectiveness(
    [{"present": 10, "evaluation_score": 80}, {"present": 5, "evaluation_score": 90}, {"present": 2}],
    [{"effective": T.EFFECTIVE}, {"effective": T.EFFECTIVE}, {"effective": T.NOT_EFFECTIVE}, {"effective": ""}],
    [{"status": R.DONE, "score": 75, "applied": "Applied in Full"}, {"status": R.DONE, "score": 25,
                                                                     "applied": "Not Applied"},
     {"status": R.PENDING}],
    [{"result": R.IMPROVED}, {"result": R.WORSE}, {"result": ""}], T.EFFECTIVE)
check("the four levels: reaction, pass rate, application, KPIs improved", (
    FOUR["sessions"], FOUR["trainees"], FOUR["reaction"], FOUR["assessed"], FOUR["pass_rate"], FOUR["reviews"],
    FOUR["reviews_done"], FOUR["application"], FOUR["applied_rate"], FOUR["kpis"], FOUR["kpis_improved"])
      == (3, 17, 85.0, 3, 66.7, 3, 2, 50.0, 50.0, 2, 1), FOUR)
check("settings: the days are the LMS settings' own", (L.DEFAULTS["application_review_days"],
                                                       L.DEFAULTS["impact_review_days"],
                                                       L.DEFAULTS["impact_window_days"]) == (30, 60, 30))

# ── 2. The paper ──────────────────────────────────────────────────────
REVIEW = fields("Training Application Review")
check("paper: the review's answers are the rules'", options("Training Application Review", "applied")
      == [name for name, _v in R.APPLIED] and options("Training Application Review", "behaviour")
      == [name for name, _v in R.BEHAVIOUR] and options("Training Application Review", "competency")
      == [name for name, _v in R.COMPETENCY]
      and options("Training Application Review", "status") == list(R.REVIEW_STATUSES))
check("paper: what the glue sets on a review is on it", {
    "training_event", "training_program", "event_end", "employee", "employee_name", "department", "branch",
    "company", "supervisor", "supervisor_name", "reviewer", "due_on", "status", "score", "reviewed_on",
    "comments", "evidence"} <= set(REVIEW))
check("paper: the review's worked-out fields are read only", all(REVIEW[name].get("read_only") for name in (
    "status", "score", "reviewed_on", "reviewer")))
check("paper: a supervisor may answer, not raise or delete", [
    (row.get("create", 0), row.get("write", 0), row.get("delete", 0)) for row in
    doctype("Training Application Review")["permissions"] if row["role"] == "Supervisor"] == [(0, 1, 0)])
IMPACT = fields("Training Impact Review")
check("paper: the impact's KPIs are the rules'", options("Training Impact Review", "kpi") == list(R.KPI_NAMES)
      and options("Training Program KPI", "kpi") == list(R.KPI_NAMES))
check("paper: what the glue sets on an impact review is on it", {
    "training_event", "training_program", "event_end", "branch", "company", "work_section", "kpi", "kpi_name",
    "better", "measured", "status", "baseline_from", "baseline_to", "baseline", "after_from", "after_to", "after",
    "change", "change_percent", "result", "benefit", "measured_by"} <= set(IMPACT))
check("paper: the programme lists its KPIs", any(row["name"] == "Training Program-custom_kpis"
                                                  and row["options"] == "Training Program KPI"
                                                  for row in json.loads(read("hrms_addon", "fixtures",
                                                                             "custom_field.json"))))
SETTINGS = fields("Learning Settings")
check("paper: the days on the LMS settings, with their defaults", all(
    key in SETTINGS and int(SETTINGS[key]["default"]) == L.DEFAULTS[key]
    for key in ("application_review_days", "impact_review_days", "impact_window_days")))
for name, ref in (("Training Attendance Form", "LPL/TRG/FRM03"), ("Training Evaluation Form", "LPL/TRG/FRM05")):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "print_format", folder, folder + ".json"), encoding="utf-8"))
    check("print: %s on the Training Event, %s" % (name, ref), spec["doc_type"] == "Training Event"
          and ref in spec["html"] and spec["standard"] == "Yes" and "print_control(doc)" in spec["html"])
FRM03 = json.load(open(os.path.join(APP, "print_format", "training_attendance_form", "training_attendance_form.json"),
                       encoding="utf-8"))["html"]
check("FRM03: the trainee's section beside their department, a column a day, eighteen lines at least",
      "custom_work_section" in FRM03 and "Day {{ n + 1 }}" in FRM03 and "[18 - (people | length), 0] | max" in FRM03
      and "5] | min" in FRM03)
FRM05 = json.load(open(os.path.join(APP, "print_format", "training_evaluation_form", "training_evaluation_form.json"),
                       encoding="utf-8"))["html"]
check("FRM05: a page for each trainee, the items from the list HR keep, the five columns, the six questions",
      "lpl-page" in FRM05 and '"Training Evaluation Item"' in FRM05 and all(
          rating in FRM05 for rating in T.RATINGS) and all(question in FRM05 for _key, question in T.QUESTIONS[:4]))

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_delivery.py")


def body(name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@frappe)|\Z)" % re.escape(name), GLUE, re.S)
    return found.group(0) if found else ""


check("glue: reviews and impacts from held sessions only", '"docstatus": 1, "event_status": ["!=", "Cancelled"]'
      in body("daily") and "rules.due_now(event.end_time, s[\"application_review_days\"], day)" in body("daily")
      and "rules.due_now(event.end_time, s[\"impact_review_days\"], day)" in body("daily"))
check("glue: one review a trainee a session, to their supervisor", 'frappe.db.exists(REVIEW, {"training_event": '
      'event.name, "employee": employee})' in body("_raise_review") and "facts.reports_to" in body("_raise_review")
      and "people.assign(REVIEW" in body("_raise_review"))
check("glue: one impact review a KPI a session, to the plant's HR", "(row.kpi, row.kpi_name or \"\") in have"
      in body("_raise_impacts") and "people.hr_officers(event.custom_branch)" in body("_raise_impacts"))
check("glue: measured from the section's shift reports", "excellence.shift_rows(start, end, section=doc.work_section)"
      in body("_measure"))
check("glue: measuring by hand only for someone who may change it", 'doc.check_permission("write")'
      in body("impact_from_shift_reports") and "@frappe.whitelist()\ndef impact_from_shift_reports" in GLUE)
check("glue: a supervisor answers only their own; management reads", 'doc.get("reviewer") == user'
      in body("review_permission") and '"`tab{0}`.`reviewer` = {1}"' in body("review_query"))
check("glue: a failed trainee told with their supervisor and HR", "people.hr_officers(facts.branch, facts.department)"
      in body("result_failed") and "training_rules.NOT_EFFECTIVE" in body("result_failed")
      and 'method == "on_update_after_submit"' in body("result_failed"))

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("wiring: every day", '"hrms_addon.hrms_addon.learning_delivery.daily"' in HOOKS)
check("wiring: on a result submitted and changed", HOOKS.count('"hrms_addon.hrms_addon.learning_delivery.result_failed"')
      == 2)
check("wiring: the review's permissions", '"Training Application Review": "hrms_addon.hrms_addon.learning_delivery.'
      'review_query"' in HOOKS and '"Training Application Review": "hrms_addon.hrms_addon.learning_delivery.'
      'review_permission"' in HOOKS)
check("wiring: the programme's KPI fields ship", '"Training Program-custom_kpis"' in HOOKS
      and '"Training Program-custom_kpis_section"' in HOOKS)
for name, controller in (("Training Application Review", "review_validate"),
                         ("Training Impact Review", "impact_validate")):
    folder = name.lower().replace(" ", "_")
    source = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    check("wiring: %s calls learning_delivery.%s" % (name, controller),
          "learning_delivery.%s(self)" % controller in source and "\ndef %s(" % controller in GLUE)
for folder in ("training_attendance", "training_effectiveness"):
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    check("wiring: %s reads held sessions through the user's permissions" % spec["name"],
          "frappe.get_list(\"Training Event\"" in read("hrms_addon", "hrms_addon", "report", folder, folder + ".py"))

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_delivery: OK")
