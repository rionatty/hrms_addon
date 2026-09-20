"""Verify performance management, without a bench:

    python scripts/verify_performance.py

Luuka's appraisal round (the flowchart and the test script's cases 1 to 10),
on the shape of the Supervisory Skills Evaluation Form (LPL/HR/18), built on
Frappe HR's Appraisal Cycle and Appraisal so the round keeps its appraisee
list and its Appraisal Overview chart.

  1  the rules: the form's sections, the scale, the bands, the quarters and
     their deadlines, the year's average, what a score suggests
  2  the signatures: Employee, Supervisor, HR Manager, Production Manager,
     General Manager
  3  the forms carry the paper, with the rights each role needs
  4  the glue reads and writes fields that exist, here and upstream
  5  the print-outs say what the paper says
  6  wiring: the doc events, the workflow on migrate, the daily jobs, the
     seed, the patch, the way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import datetime
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
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def all_fields(name):
    """Every field the site has on a DocType: its own JSON, here or
    upstream, plus this app's Custom Fields."""
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


def print_format(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "print_format", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
R, A, P = load("appraisal_rules"), load("appraisal_approval"), load("pip_rules")
print("loaded appraisal_rules.py, appraisal_approval.py and pip_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if len(R.FACTORS) != 12:
    fail.append("Section A of LPL/HR/18 has twelve ratable factors, not %d" % len(R.FACTORS))
if R.FACTORS[0] != "Job performance, work output, quality of work":
    fail.append("Section A must open with the form's first factor")
if "changes brought by the supervisor" not in R.FACTORS[2]:
    fail.append("the third factor is the supervisory form's, not the probation form's")
if R.APPRAISAL_MASTERS != {"Appraisal Factor": ("factor_name", R.FACTORS)}:
    fail.append("the Appraisal Factor list is seeded with exactly Section A")
if len(R.QUESTIONS) != 4:
    fail.append("the form's General section asks four questions, not %d" % len(R.QUESTIONS))
if (R.FACTORS_WEIGHT, R.OBJECTIVES_WEIGHT) != (60, 40):
    fail.append("Section C weights the factors 60 and the objectives 40")
if R.MAX_OBJECTIVES != 8:
    fail.append("the form carries at most eight objectives")
if R.BANDS != ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average")):
    fail.append("the bands are the form's: 90, 75, 60, 50")
if R.NOT_APPLICABLE not in R.RATINGS or R.TOP_RATING != 5:
    fail.append("the scale is 1 to 5 with N/A for a factor that does not fit the job")

if R.section_percent(["5", "5", "N/A", None]) != 100.0:
    fail.append("N/A and blanks are left out of a section's percentage")
if R.section_percent(["N/A", None]) is not None:
    fail.append("a section with nothing rated scores nothing at all")
found = R.scores(["5"] * 12, ["4"] * 8)
if (found["factors"], found["objectives"], found["total"]) != (60.0, 32.0, 92.0):
    fail.append("Section C: all fives and all fours must give 60/60, 32/40, 92%%; got %s" % found)
if R.scores(["3"] * 12, [])["total"] != 60.0:
    fail.append("a section with nothing rated leaves the total to the other alone")
for total, name in ((100, "Excellent"), (90, "Excellent"), (89.9, "Very Good"), (75, "Very Good"),
                    (74, "Good"), (60, "Good"), (59, "Average"), (50, "Average"), (49, "Below Average"), (0, "Below Average")):
    if R.band(total) != name:
        fail.append("%s%% is %s, not %r" % (total, name, R.band(total)))
if R.band(None) is not None:
    fail.append("nothing rated has no band")
if R.annual_average([80, 60, None, 70]) != 70.0 or R.annual_average([]) is not None:
    fail.append("the year is the average of the quarters appraised: %s" % R.annual_average([80, 60, None, 70]))
if R.PIP_BELOW != 60:
    fail.append("the recommendation puts anyone below 60 on an improvement plan")
if R.recommended(59.9) != R.PIP or R.recommended(60) != R.CLOSE or R.recommended(None) is not None:
    fail.append("below the pass mark suggests a PIP, at or above it suggests closing")
if R.POSITION_CHANGE_FOR.get(R.PROMOTION) != "Promotion" or R.POSITION_CHANGE_FOR.get(R.INCREASE) != "Salary Increment":
    fail.append("a promotion and an increase are carried out by an Employee Position Change")

if R.quarter_window(2026, "Q1") != (datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)):
    fail.append("Q1 runs January to March: %s" % (R.quarter_window(2026, "Q1"),))
if R.quarter_window(2026, "Q4") != (datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)):
    fail.append("Q4 runs October to December: %s" % (R.quarter_window(2026, "Q4"),))
if R.deadlines(2026, "Q1") != (datetime.date(2026, 4, 25), datetime.date(2026, 4, 30)):
    fail.append("Q1 is appraised by the 25th of April, at the latest that month's end: %s" % (R.deadlines(2026, "Q1"),))
if R.deadlines(2026, "Q4") != (datetime.date(2027, 1, 25), datetime.date(2027, 1, 31)):
    fail.append("Q4's deadlines fall in the next year: %s" % (R.deadlines(2026, "Q4"),))
if R.SOFT_DEADLINE_DAY != 25:
    fail.append("the recommendation sets the soft deadline on the 25th")
if R.REMINDER_DAYS != (7, 1, 0):
    fail.append("appraisers are reminded a week before, a day before and on the day")

PLAN = {"year": 2026, "company": "Luuka Plastics Limited",
        "quarters": [{"quarter": q, "from_date": str(R.quarter_window(2026, q)[0]),
                      "to_date": str(R.quarter_window(2026, q)[1]),
                      "soft_deadline": str(R.deadlines(2026, q)[0]), "hard_deadline": str(R.deadlines(2026, q)[1])}
                     for q in R.QUARTERS]}
expect("a whole year planned", R.plan_errors(PLAN))
expect("no year", R.plan_errors(dict(PLAN, year=None)), "year the plan covers")
expect("no quarters", R.plan_errors(dict(PLAN, quarters=[])), "List the quarters")
expect("a quarter listed twice", R.plan_errors(dict(PLAN, quarters=PLAN["quarters"] + [PLAN["quarters"][0]])),
       "is listed twice")
expect("a deadline inside the quarter it appraises",
       R.plan_errors(dict(PLAN, quarters=[dict(PLAN["quarters"][0], soft_deadline=None,
                                               hard_deadline="2026-02-01")])),
       "falls inside the quarter it appraises")
expect("a soft deadline after the hard one",
       R.plan_errors(dict(PLAN, quarters=[dict(PLAN["quarters"][0], soft_deadline="2026-04-29",
                                               hard_deadline="2026-04-28")])),
       "after its hard deadline")

RATED = {"step": "self", "roles": "Run the line", "skills": "Planning",
         "factors": [{"item": f, "employee_rating": "4"} for f in R.FACTORS],
         "objectives": [{"item": "Output", "employee_rating": "4"}]}
expect("a self-assessment complete", R.appraisal_errors(RATED))
expect("a factor not rated",
       R.appraisal_errors(dict(RATED, factors=[dict(row, employee_rating=None) for row in RATED["factors"]])),
       "Rate yourself on every factor")
expect("no objectives listed", R.appraisal_errors(dict(RATED, objectives=[])), "List the objectives")
expect("the General questions unanswered", R.appraisal_errors(dict(RATED, roles="", skills=" ")),
       "Answer the General questions")
SUPERVISED = {"step": "supervisor",
              "factors": [{"item": f, "supervisor_rating": "4"} for f in R.FACTORS],
              "objectives": [{"item": "Output", "supervisor_rating": "3"}]}
expect("the supervisor's rating complete", R.appraisal_errors(SUPERVISED))
expect("the supervisor left one unrated",
       R.appraisal_errors(dict(SUPERVISED, objectives=[{"item": "Output"}])), "Give your rating")
expect("too many objectives",
       R.appraisal_errors(dict(SUPERVISED, objectives=[{"item": str(i), "supervisor_rating": "3"} for i in range(9)])),
       "at most 8 objectives")

due = R.due_quarters([{"quarter": "Q1", "to_date": "2026-03-31"},
                      {"quarter": "Q2", "to_date": "2026-06-30"},
                      {"quarter": "Q3", "to_date": "2026-09-30", "appraisal_cycle": "C3"},
                      {"quarter": "Q4", "to_date": "2026-12-31"}], "2026-10-05")
if [row["quarter"] for row in due] != ["Q1", "Q2"]:
    fail.append("a quarter is due once it has closed and has no cycle yet: %s" % [row["quarter"] for row in due])
if R.due_quarters([{"quarter": "Q1", "to_date": "2026-03-31", "notified_on": "2026-04-01"}], "2026-10-05"):
    fail.append("the HR Officer is told of a quarter once, not every day")
if R.reminders_due("2026-04-30", "2026-04-20", None) != []:
    fail.append("nothing is sent before the first threshold")
if R.reminders_due("2026-04-30", "2026-04-25", None, "2026-04-25") != ["soft", "7"]:
    fail.append("the soft deadline and the week-before reminder fall together: %s"
                % R.reminders_due("2026-04-30", "2026-04-25", None, "2026-04-25"))
if R.reminders_due("2026-04-30", "2026-04-29", "7") != ["1"]:
    fail.append("a day before, once the week's has gone")
if R.reminders_due("2026-04-30", "2026-04-30", "7, 1") != ["0"]:
    fail.append("and on the day")
if R.reminders_due("2026-04-30", "2026-05-01", None) != []:
    fail.append("nothing is sent once the deadline has passed")
if R.reminders_due("2026-04-30", "2026-04-29", None) != ["1"]:
    fail.append("a deadline first seen inside several thresholds gets the nearest")
if "7" not in R.record_reminders(None, ["1"]) or "1" not in R.record_reminders(None, ["1"]):
    fail.append("recording the nearest threshold marks the ones already passed")

rows = R.sheet_rows("HR-APR-0001", "HR-EMP-1", "John", [{"item": "Job performance", "employee_rating": "4"}],
                    [{"item": "Output", "employee_rating": "3"}])
if len(rows) != 2 or rows[0][3] != R.SECTION_A or rows[1][3] != R.SECTION_B:
    fail.append("the sheet carries Section A then Section B, one row per item: %s" % rows)
if len(rows[0]) != len(R.SHEET_COLUMNS):
    fail.append("every sheet row must have a cell for each column")
back = R.read_sheet([list(R.SHEET_COLUMNS),
                     ["HR-APR-0001", "HR-EMP-1", "John", R.SECTION_A, 1, "Job performance", "4", "5", "Strong"],
                     ["HR-APR-0001", "HR-EMP-1", "John", R.SECTION_B, 1, "Output", "3", 4.0, ""],
                     ["HR-APR-0001", "HR-EMP-1", "John", R.SECTION_B, 2, "Waste", "3", "rubbish", ""],
                     [None, None, None, None, None, None, None, None, None]])
if back.get("HR-APR-0001", {}).get("A", {}).get("Job performance") != ("5", "Strong"):
    fail.append("the sheet read back must carry the supervisor's rating and comment: %s" % back)
if back.get("HR-APR-0001", {}).get("B", {}).get("Output", (None,))[0] != "4":
    fail.append("a rating that came back as a number is read as the scale's: %s" % back)
if back.get("HR-APR-0001", {}).get("B", {}).get("Waste", (None,))[0] is not None:
    fail.append("a rating that is not on the scale is left out, not guessed at: %s" % back)
if R.read_sheet([]) != {}:
    fail.append("an empty sheet says nothing")
print("rules: the form's sections and scale, the bands, the quarters and deadlines, the year, the sheet")

# ── 2. The signatures ─────────────────────────────────────────────────
if A.DOCTYPE != "Appraisal":
    fail.append("the workflow runs on Frappe HR's Appraisal, so the round keeps its cycle and its chart")
if A.STATUS_FIELD != "custom_appraisal_status":
    fail.append("Frappe HR's Appraisal has no status field; ours must carry the workflow's states")
route = [A.DRAFT, A.PENDING_SUPERVISOR, A.PENDING_HRM, A.PENDING_PRODUCTION, A.PENDING_GM, A.COMPLETED]
walked, state = [A.DRAFT], A.DRAFT
while True:
    forward = [t for t in A.TRANSITIONS if t["state"] == state and t["action"] in (A.SELF, A.RATE, A.APPROVE)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != route:
    fail.append("the form is signed Employee, Supervisor, HR Manager, Production Manager, General Manager: %s" % walked)
if set(A.STAMPS) != {A.DRAFT, *A.PENDING_STATES} or set(A.REMARK_FIELDS) != {A.DRAFT, *A.PENDING_STATES}:
    fail.append("every comment block on the paper is stamped and signed: %s" % sorted(A.STAMPS))
for state in A.PENDING_STATES:
    if not [t for t in A.TRANSITIONS if t["state"] == state and t["action"] == A.RETURN and t["next_state"] == A.DRAFT]:
        fail.append("%s must be able to return the appraisal to Draft" % state)
if [row for row in A.STATES if row["state"] == A.COMPLETED and row.get("doc_status") != "1"]:
    fail.append("the General Manager's approval submits the appraisal")
if "Production Manager" not in A.NEW_ROLES:
    fail.append("the Production Manager signs the form and appears nowhere else: the role must be created")
for role, ptypes in (("HR User", ("read", "write", "create", "submit")), ("Supervisor", ("read", "write")),
                     ("Production Manager", ("read", "write")), ("General Manager", ("read", "write"))):
    granted = (A.PERMISSIONS.get("Appraisal") or {}).get(role) or ()
    missing = [ptype for ptype in ptypes if ptype not in granted]
    if missing:
        fail.append("Frappe HR gives the Appraisal to the HR Manager alone: %s needs %s on it"
                    % (role, ", ".join(missing)))
    if granted and granted[0] != "read":
        fail.append("PERMISSIONS[Appraisal][%r] must start with read: workflows.py adds the rule with its first right"
                    % role)
granted_roles = {role for grants in A.PERMISSIONS.values() for role in grants}
if not granted_roles - {"HR User", "HR Manager", "Employee"} <= set(A.NEW_ROLES):
    fail.append("NEW_ROLES must name every granted role Frappe HR does not ship: %s"
                % sorted(granted_roles - {"HR User", "HR Manager", "Employee"} - set(A.NEW_ROLES)))

stamped = A.compute_stamps(A.PENDING_SUPERVISOR, A.PENDING_HRM, "sup@luuka", "2026-09-23", {})
if stamped["custom_supervisor_by"] != "sup@luuka" or stamped["custom_supervisor_on"] != "2026-09-23":
    fail.append("the block just passed is signed by whoever passed it: %s" % stamped)
if any(stamped[field] for field in ("custom_hrm_by", "custom_gm_by")):
    fail.append("only the block passed is signed")
if any(A.compute_stamps(A.PENDING_GM, A.DRAFT, "x", "2026-09-23",
                        {"custom_hrm_by": "a", "custom_supervisor_by": "b"}).values()):
    fail.append("a return to Draft clears every signature")
expect("returned without saying why", A.step_errors(A.PENDING_GM, A.DRAFT, {}), "Return Remarks")
expect("returned with a reason", A.step_errors(A.PENDING_GM, A.DRAFT, {"return_remarks": "Re-rate section B"}))
expect("the supervisor passing it on with no comments",
       A.step_errors(A.PENDING_SUPERVISOR, A.PENDING_HRM, {}), "Supervisor's general comments")
if A.next_states(A.PENDING_GM, ["General Manager"]) != [(A.APPROVE, A.COMPLETED), (A.RETURN, A.DRAFT)]:
    fail.append("the General Manager may approve or return: %s" % A.next_states(A.PENDING_GM, ["General Manager"]))
if A.next_states(A.PENDING_GM, ["HR User"]):
    fail.append("nobody but the General Manager acts on an appraisal waiting for them")
print("signatures: Employee to General Manager, returns, stamps, the rights each role needs")

# ── PIP rules ─────────────────────────────────────────────────────────
if P.DEFAULT_MONTHS != 3:
    fail.append("a Performance Improvement Plan runs three months unless HR says otherwise")
if P.end_date("2026-10-01", 3) != datetime.date(2026, 12, 31):
    fail.append("a three-month plan from 1 October runs to 31 December: %s" % P.end_date("2026-10-01", 3))
PIP = {"employee": "HR-EMP-1", "supervisor": "HR-EMP-2", "start_date": "2026-10-01", "end_date": "2026-12-31",
       "objectives": [{"area": "Output", "expected_standard": "95% of target", "measure": "Daily report",
                       "review_date": "2026-11-01"}]}
expect("a plan agreed", P.plan_errors(PIP))
expect("a plan with nothing to improve", P.plan_errors(dict(PIP, objectives=[])), "List what must improve")
expect("a line with no standard",
       P.plan_errors(dict(PIP, objectives=[dict(PIP["objectives"][0], expected_standard="")])), "expected standard")
expect("nobody guiding the employee", P.plan_errors(dict(PIP, supervisor=None)), "supervisor who will guide")
expect("a review date after the plan ends",
       P.plan_errors(dict(PIP, objectives=[dict(PIP["objectives"][0], review_date="2027-02-01")])),
       "falls after the plan ends")
expect("closing with nothing recorded", P.close_errors({}), "at least one review", "how the plan ended",
       "what was agreed")
expect("closing properly", P.close_errors({"reviews": [{"progress": P.MET}], "outcome": P.IMPROVED,
                                           "remarks": "Back to standard."}))
expect("extending with no new date", P.close_errors({"reviews": [{"progress": P.PARTLY}], "outcome": P.EXTENDED,
                                                     "remarks": "More time.", "end_date": "2026-12-31"}),
       "new end date")
if P.suggested_outcome([{"progress": P.MET}, {"progress": P.MET}, {"progress": P.NOT_MET}]) != P.IMPROVED:
    fail.append("two of three met is most of them, and suggests Improved")
if P.suggested_outcome([{"progress": P.NOT_MET}, {"progress": P.MET}]) != P.NOT_IMPROVED:
    fail.append("half met is not most, and does not suggest Improved")
if P.suggested_outcome([{"progress": P.PARTLY}, {"progress": P.PARTLY}]) != P.NOT_IMPROVED:
    fail.append("partly met is not met")
if P.suggested_outcome([]) is not None:
    fail.append("nothing reviewed suggests nothing")
if [row["area"] for row in P.due_reviews([{"area": "A", "review_date": "2026-11-01"},
                                          {"area": "B", "review_date": "2026-12-01"},
                                          {"area": "C", "review_date": "2026-11-01", "reviewed_on": "2026-11-02"}],
                                         "2026-11-15")] != ["A"]:
    fail.append("a review is due once its date has come and nobody has looked at it")
print("improvement plans: the agreement, the reviews, the outcome it suggests")

# ── 3. The forms ──────────────────────────────────────────────────────
PAPER = {
    "Appraisal Plan": ["year", "company", "branch", "quarters", "appraise_all", "employees", "status"],
    "Performance Review": ["appraisal_cycle", "review_date", "employees", "appraised", "average_score",
                           "below_pass", "completion", "shared_with", "shared_on", "management_remarks",
                           "decided_by", "decided_on", "status"],
    "Performance Improvement Plan": ["employee", "supervisor", "appraisal", "appraisal_score", "performance_review",
                                     "start_date", "months", "end_date", "objectives", "reviews", "outcome",
                                     "suggested_outcome", "new_end_date", "outcome_remarks",
                                     "employee_agreed_on", "supervisor_agreed_on", "status"],
}
for name, wanted in PAPER.items():
    spec = doctype(name)
    if not spec:
        fail.append("%s is not there" % name)
        continue
    fields = fields_of(spec)
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the process asks for" % (name, fieldname))
    if not spec.get("is_submittable"):
        fail.append("%s must be submittable: it is approved, and cancelling undoes what it did" % name)
    roles = {row["role"] for row in spec.get("permissions", [])}
    if not {"HR Manager", "HR User"} <= roles:
        fail.append("%s: the HR Manager and the branch HR Officer must be able to work it (%s)" % (name, sorted(roles)))

quarter = fields_of(doctype("Appraisal Plan Quarter"))
for fieldname in ("quarter", "from_date", "to_date", "soft_deadline", "hard_deadline", "appraisal_cycle",
                  "notified_on", "reminders_sent"):
    if fieldname not in quarter:
        fail.append("Appraisal Plan Quarter has no %s" % fieldname)
if (quarter.get("quarter") or {}).get("options", "").split("\n") != list(R.QUARTERS):
    fail.append("Appraisal Plan Quarter.quarter must offer exactly %s" % (R.QUARTERS,))

review_row = fields_of(doctype("Performance Review Employee"))
for fieldname in ("employee", "appraisal", "total_score", "band", "recommended", "decision", "position_change",
                  "improvement_plan"):
    if fieldname not in review_row:
        fail.append("Performance Review Employee has no %s" % fieldname)
if (review_row.get("decision") or {}).get("options", "").split("\n") != list(R.DECISIONS):
    fail.append("the decision must offer exactly what management may decide: %s" % (R.DECISIONS,))

for name, wanted in (("Appraisal Factor Rating", ("item", "employee_rating", "supervisor_rating", "supervisor_comment")),
                     ("Appraisal Objective Rating", ("item", "employee_rating", "supervisor_rating", "supervisor_comment"))):
    fields = fields_of(doctype(name))
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s: the form is rated by the employee and the supervisor" % (name, fieldname))
    for side in ("employee_rating", "supervisor_rating"):
        if fields.get(side, {}).get("options", "").split("\n") != list(R.RATINGS):
            fail.append("%s.%s must offer the form's scale %s" % (name, side, (R.RATINGS,)))

pip_row = fields_of(doctype("PIP Objective"))
for fieldname in ("area", "expected_standard", "support", "measure", "review_date", "progress", "reviewed_on"):
    if fieldname not in pip_row:
        fail.append("PIP Objective has no %s" % fieldname)
if (fields_of(doctype("Performance Improvement Plan")).get("outcome") or {}).get("options", "").split("\n") != list(P.OUTCOMES):
    fail.append("the plan's outcome must offer exactly %s" % (P.OUTCOMES,))

# LPL/HR/18 on Frappe HR's Appraisal
appraisal = all_fields("Appraisal")
if not upstream_doctype("Appraisal"):
    fail.append("Frappe HR no longer ships an Appraisal to build the round on")
for fieldname in ("custom_factors", "custom_objectives", "custom_factors_score", "custom_objectives_score",
                  "custom_total_score", "custom_band", "custom_annual_score", "custom_plan", "custom_quarter",
                  "custom_supervisor", "custom_appraisal_status", "custom_return_remarks", "custom_outcome",
                  "custom_performance_review", *A.ALL_STAMP_FIELDS,
                  *[field for field, _who in A.REMARK_FIELDS.values()],
                  *["custom_%s" % field for field, _question in R.QUESTIONS]):
    if fieldname not in appraisal:
        fail.append("the Appraisal has no %s, which LPL/HR/18 asks for" % fieldname)
ours = custom_fields("Appraisal")
if (ours.get("custom_appraisal_status") or {}).get("options", "").split("\n") != list(R.STATUSES):
    fail.append("Appraisal.custom_appraisal_status must follow the workflow's states")
for fieldname in ("custom_factors_score", "custom_objectives_score", "custom_total_score", "custom_band",
                  "custom_annual_score", *A.ALL_STAMP_FIELDS):
    if not (ours.get(fieldname) or {}).get("read_only"):
        fail.append("Appraisal.%s is worked out, not typed: it must be read-only" % fieldname)
if (ours.get("custom_factors") or {}).get("options") != "Appraisal Factor Rating":
    fail.append("Section A must be the Appraisal Factor Rating table")
if (ours.get("custom_objectives") or {}).get("options") != "Appraisal Objective Rating":
    fail.append("Section B must be the Appraisal Objective Rating table")
cycle = custom_fields("Appraisal Cycle")
for fieldname in ("custom_plan", "custom_quarter", "custom_soft_deadline", "custom_hard_deadline",
                  "custom_reminders_sent"):
    if fieldname not in cycle:
        fail.append("the Appraisal Cycle has no %s: the round needs its plan and its deadlines" % fieldname)
print("forms: the plan, the review, the improvement plan, and LPL/HR/18 on Frappe HR's Appraisal")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "appraisals.py")
pips = read("hrms_addon", "hrms_addon", "pips.py")
own = {name: fields_of(doctype(name)) for name in PAPER}


def body_of(source, name):
    start = source.index("\ndef %s(" % name)
    rest = source[start + 1:]
    end = rest.index("\ndef ", 1) if "\ndef " in rest[1:] else len(rest)
    return rest[:end]


for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue))
                        | set(re.findall(r'doc\.(custom_\w+)\b', glue))):
    if fieldname not in appraisal:
        fail.append("appraisals.py reads or writes Appraisal.%s, which does not exist" % fieldname)
upstream_appraisal = fields_of(upstream_doctype("Appraisal") or {})
for fieldname in ("final_score", "total_score", "self_score", "appraisal_cycle", "employee", "start_date", "end_date"):
    if upstream_appraisal and fieldname not in upstream_appraisal:
        fail.append("appraisals.py sets Appraisal.%s, which Frappe HR no longer has" % fieldname)
upstream_cycle = fields_of(upstream_doctype("Appraisal Cycle") or {})
for fieldname in ("cycle_name", "company", "start_date", "end_date", "status", "branch", "department",
                  "kra_evaluation_method"):
    if upstream_cycle and fieldname not in upstream_cycle:
        fail.append("the cycle is opened with %s, which Frappe HR no longer has" % fieldname)
for needle, why in (
    ('"doctype": "Appraisal Cycle"', "the quarter opens one of Frappe HR's cycles, so the round keeps its chart"),
    ('"doctype": "Appraisal",', "an Appraisal is raised per employee"),
    ("rules.scores(", "Section C comes from the rules"),
    ("doc.final_score = ", "Frappe HR's own score is written too, or the Appraisal Overview chart stays empty"),
    ("approval.compute_stamps(", "the signatures are stamped by the workflow"),
    ("rules.annual_average(", "the year is the average of the quarters"),
    ("rules.due_quarters(", "the HR Officer is told when a quarter closes"),
    ("rules.reminders_due(", "everyone appraising is reminded before the deadlines"),
    ("rules.sheet_rows(", "the sheet is built by the rules"),
    ("rules.read_sheet(", "and read back by them"),
    ("build_xlsx_response(", "the sheet comes down as a spreadsheet"),
    ("read_xlsx_file_from_attached_file(", "and the filled one is read back"),
    ('frappe.new_doc("Employee Position Change")', "a promotion or an increase is an Employee Position Change"),
    ('frappe.new_doc("Performance Improvement Plan")', "a PIP decision raises the plan"),
    ("people.hr_officers(", "the branch HR Officer is told"),
):
    if needle not in glue:
        fail.append("appraisals.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("rules.plan_errors(", "the plan is judged by the rules"),
    ("rules.close_errors(", "and so is closing it"),
    ("rules.suggested_outcome(", "the reviews suggest an outcome"),
    ("rules.due_reviews(", "a review date that has come is chased"),
    ('doc.db_set({"status": rules.CLOSED', "submitting closes the plan"),
):
    if needle not in pips:
        fail.append("pips.py: %s (%r not found)" % (why, needle))
if 'doc.check_permission("submit")' not in body_of(glue, "open_quarter"):
    fail.append("open_quarter raises documents for everyone in scope: it must check the caller may submit the plan")
if 'doc.check_permission("write")' not in body_of(glue, "upload_sheet"):
    fail.append("upload_sheet writes onto an appraisal: it must check the caller may write it")
if "if doc.docstatus != 0:" not in body_of(glue, "upload_sheet"):
    fail.append("upload_sheet must leave a submitted appraisal alone")
for name in ("fill_year", "get_appraisals", "download_sheet"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("appraisals.%s must be whitelisted for the form" % name)
for source, module, name in ((glue, "appraisals", "open_quarter"), (glue, "appraisals", "upload_sheet"),
                             (glue, "appraisals", "share_with_management"), (pips, "pips", "start")):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, source):
        fail.append("%s.%s changes something: a whitelisted POST method" % (module, name))
print("glue: fields that exist here and upstream, the rules followed, the buttons' methods whitelisted")

# ── 5. The print-outs ─────────────────────────────────────────────────
PRINTS = {
    "Supervisory Skills Evaluation Form": ("Appraisal", [
        "LPL/HR/18", "Section A: Ratable Factors", "Section B", "Section C", "Ratable Factors /60",
        "Objectives/KPIs /40", "Total Score", "General comments by the Employee",
        "Human Resources Manager&rsquo;s remarks".replace("&rsquo;", "'"), "Production Manager's remarks",
        "General Manager's remarks", "Rating Scale:"]),
    "Performance Appraisal Report": ("Performance Review", [
        "Performance Appraisal Report", "Average Score", "Below the pass mark", "Decision", "Management's Remarks"]),
    "Performance Improvement Plan Document": ("Performance Improvement Plan", [
        "Performance Improvement Plan", "Area to improve", "Expected standard", "Support from the company",
        "How it is measured", "Review meetings", "Outcome", "Agreement"]),
}
for name, (doc_type, needles) in PRINTS.items():
    spec = print_format(name)
    if not spec:
        fail.append("the %s print format is not there" % name)
        continue
    if spec.get("doc_type") != doc_type:
        fail.append("%s must print a %s, not a %s" % (name, doc_type, spec.get("doc_type")))
    html = spec.get("html") or ""
    for needle in needles:
        if needle not in html:
            fail.append("%s does not say %r, which the paper does" % (name, needle))
    available = all_fields(doc_type)
    for fieldname in sorted(set(re.findall(r"doc\.(\w+)", html))):
        if fieldname in ("name", "creation", "owner", "modified", "doctype", "docstatus", "get"):
            continue
        if fieldname not in available:
            fail.append("%s prints doc.%s, which the %s does not have" % (name, fieldname, doc_type))
    for bad in re.findall(r"\{\{\s*doc\.(\w+)\s*\}\}", html):
        fail.append("%s prints doc.%s unescaped: use v()" % (name, bad))
print("print-outs: LPL/HR/18, the appraisal report and the improvement plan, from fields that exist")

# ── 6. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
events = hooks.get("doc_events") or {}
for doctype_name, event, function in (("Appraisal", "validate", "appraisals.appraisal_validate"),
                                      ("Appraisal", "on_cancel", "appraisals.appraisal_on_cancel")):
    if (events.get(doctype_name) or {}).get(event) != "hrms_addon.hrms_addon.%s" % function:
        fail.append("doc_events %s %s must be %s" % (doctype_name, event, function))
if "hrms_addon.hrms_addon.appraisals.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must build the appraisal workflow and its roles")
for job in ("hrms_addon.hrms_addon.appraisals.daily", "hrms_addon.hrms_addon.pips.daily"):
    if job not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
        fail.append("the scheduler must run %s" % job)
if "hrms_addon.hrms_addon.pick_lists.seed_appraisal_masters" not in (hooks.get("after_install") or []):
    fail.append("a fresh install seeds Section A as the Appraisal Factor list")
for doctype_name, path in (("Appraisal", "public/js/appraisal.js"), ("Appraisal Cycle", "public/js/appraisal_cycle.js")):
    if (hooks.get("doctype_js") or {}).get(doctype_name) != path or not os.path.exists(os.path.join(PACKAGE, path)):
        fail.append("doctype_js %s must load %s" % (doctype_name, path))
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.seed_performance" not in patches:
    fail.append("a site that has the app already must get the factors and the roles by patch")
seed = read("hrms_addon", "patches", "v1_0", "seed_performance.py")
if "seed_appraisal_masters()" not in seed or "appraisal_approval.NEW_ROLES" not in seed:
    fail.append("the patch must seed the factor list and exactly the roles the workflow declares")
if "seed_masters(appraisal_rules.APPRAISAL_MASTERS)" not in read("hrms_addon", "hrms_addon", "pick_lists.py"):
    fail.append("pick_lists.seed_appraisal_masters seeds appraisal_rules.APPRAISAL_MASTERS")
for name, module, prefix, methods in (
        ("appraisal_plan", "appraisals", "plan", ("validate", "on_submit", "on_cancel")),
        ("performance_review", "appraisals", "review", ("validate", "on_submit", "on_cancel")),
        ("performance_improvement_plan", "pips", "plan", ("validate", "on_submit", "on_cancel"))):
    controller = open(os.path.join(APP, "doctype", name, name + ".py"), encoding="utf-8").read()
    for method in methods:
        if "    def %s(self):\n        %s.%s_%s(self)" % (method, module, prefix, method) not in controller:
            fail.append("the %s controller must hand %s to %s.%s_%s" % (name, method, module, prefix, method))
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
for name in list(PAPER) + ["Appraisal Factor"]:
    if name not in carded:
        fail.append("%s is on no workspace card: it could only be found by searching for its DocType" % name)
    if name not in sidebarred:
        fail.append("%s is in no sidebar" % name)
if "Performance" not in navigation.CARDS:
    fail.append("Frappe HR ships the Performance page bare: our cards are what fills it")
conn = read("hrms_addon", "hrms_addon", "connections.py")
for name in ("Appraisal", "Performance Improvement Plan"):
    if name not in conn:
        fail.append("%s must show on the Employee's Connections" % name)
for name in PAPER:
    folder = name.lower().replace(" ", "_")
    if not os.path.exists(os.path.join(APP, "doctype", folder, folder + "_dashboard.py")):
        fail.append("%s has no Connections of its own (%s_dashboard.py)" % (name, folder))
print("wiring: the doc events, the workflow on migrate, the daily jobs, the seed, the patch, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL PERFORMANCE CHECKS PASSED")
