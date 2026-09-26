"""Checks for the interview process, run without a bench.

The Candidate Interview Evaluation / Score Form (LPL/HR/17) is each panel
member's Interview Feedback. interview_rules.py imports nothing from Frappe,
so it is loaded directly and its scoring is exercised: a full sheet, N/A,
blank rows, every boundary of the form's scale (27 of 30 is exactly 90%),
the recommendation and the result it sets, the panel's averages per
criterion, and the one-off seeding of the form's groups and criteria.

It also checks:
  * the Interview Criteria Group and Interview Criterion masters and the
    score rows, and that the score options are exactly the form's scale;
  * the Interview Feedback custom fields and the property setters that put
    HRMS's star-rated skill assessment aside, and the salary history on Job
    Applicant that every sheet prints;
  * hooks, patch and form scripts resolve, "Submit Feedback" is taken over
    the supported way (frappe.ui.form.off), and the form's live totals use
    the same scale as the server;
  * the print format prints only fields that exist, escaped, and carries
    the form's reference LPL/HR/17;
  * against HRMS (../ERPNext, or FRAPPE_APPS_ROOT): the button still fires
    "submit_feedback", the feedback's average rating still feeds the
    Interview, and the Feedback tab still reads skill / rating;
  * the Interview Shortlist: each applicant's education, work experience
    and certifications written out from their Bio-Data the way Luuka's
    shortlist sheet reads (most recent first, certifications and licences
    apart by Qualification Type), the checks, back-to-back interview slots,
    the DocTypes, controller, buttons and print format, and what it relies
    on in HRMS (the Shortlisted status, the Interview Type's panel);
  * the shortlist's screening walked end to end (HR shares it with the HOD,
    who approves it or returns it with a reason; HR revises; the HR Manager
    cancels through the workflow), the sign-offs, the HOD named and assigned,
    each screener's remarks, and what it relies on in Frappe;
  * the Interview Report: its approval walked end to end (HR prepares, the
    HR Manager forwards, the Executive Director approves; either may
    reject, HR revises; the HR Manager cancels through the workflow), the
    sign-offs each step records, the panel's averaged score and counted
    recommendations, the checks once it leaves Draft, the DocTypes, Get
    Interview Results, the print format, and what it relies on in HRMS and
    in Frappe's Workflow;
  * closing the loop: approval closes each interview with the panel's
    decision and moves each undecided applicant on (never one already
    Accepted or Rejected), and Create Job Offers makes one draft offer per
    Offer decision, linking an offer the candidate already has.

    python scripts/verify_interviews.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def doctype_json(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def fields_of(spec):
    return {f["fieldname"]: f for f in spec["fields"]}


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


spec = importlib.util.spec_from_file_location("interview_rules", os.path.join(APP, "interview_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)  # proves it has no Frappe import
print("loaded interview_rules.py without Frappe")

custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
setters = {s["name"]: s for s in json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "property_setter.json"), encoding="utf-8"))}
by_name = {f["name"]: f for f in custom}
hooks = read("hrms_addon", "hooks.py")
glue = read("hrms_addon", "hrms_addon", "interviews.py")

# ── 1. The form: LPL/HR/17's criteria and scale ──────────────────────
PAPER = [
    ("Education", "Technical Qualification skills"),
    ("Working Experience", "Job knowledge"), ("Working Experience", "Job experience"),
    ("Working Experience", "Leadership/supervisory skills"), ("Working Experience", "Customer care skills"),
    ("Working Experience", "Computer skills"), ("Working Experience", "Team work skills"),
    ("Working Experience", "Communication skills"), ("Working Experience", "Training/learning ability"),
    ("Personality", "Candidate's attitude"), ("Personality", "Energy, Drive, Enthusiasm"),
    ("Personality", "Problem Solving Skills"), ("Personality", "Self Confidence"),
    ("Personality", "Ability to work under pressure"), ("Personality", "Interests & Hobbies"),
    ("Appearance", "Appearance"), ("Health", "Health"),
]
# the form's Appearance and Health are not scored at interview (Employment Act 2006, s.6)
SEEDED = [row for row in PAPER if row[1] not in ("Appearance", "Health")]
if list(rules.CRITERIA) != SEEDED:
    fail.append("CRITERIA must be LPL/HR/17's criteria in the form's order, less Appearance and Health: %s" % (rules.CRITERIA,))
if tuple(rules.RETIRED_CRITERIA) != ("Appearance", "Health"):
    fail.append("Appearance and Health are the retired criteria: %s" % (rules.RETIRED_CRITERIA,))
groups_in_order = []
for group, _criterion in rules.CRITERIA:
    if group not in groups_in_order:
        groups_in_order.append(group)
if list(rules.CRITERIA_GROUPS) != groups_in_order:
    fail.append("CRITERIA_GROUPS %s must be the criteria's groups in the form's order %s" % (rules.CRITERIA_GROUPS, groups_in_order))
if rules.SCORE_OPTIONS != ("", "1", "2", "3", "4", "5", "N/A") or rules.TOP_SCORE != 5:
    fail.append("the scale is 1 to 5 or N/A, with blank for not scored yet: %s" % (rules.SCORE_OPTIONS,))
if rules.BANDS != ((90, "Excellent"), (70, "Very Good"), (50, "Good"), (30, "Average"), (0, "Below Average")):
    fail.append("BANDS must name the average score, rounded: 4.5 (90%) Excellent, 3.5 (70%) Very Good, 2.5 (50%) Good, "
                "1.5 (30%) Average")
# the scale's names agree with the form's per-score labels: everything scored 2 is Average
for score, name in (("5", "Excellent"), ("4", "Very Good"), ("3", "Good"), ("2", "Average"), ("1", "Below Average")):
    got = rules.score_summary([{"score": score}] * 15)["band"]
    if got != name:
        fail.append("a candidate scored %s on everything must be %s, as the form calls a %s, got %s" % (score, name, score, got))
for mean_scores, name in ((("5", "4"), "Excellent"), (("4", "3"), "Very Good"), (("3", "2"), "Good"), (("2", "1"), "Average")):
    got = rules.score_summary([{"score": s} for s in mean_scores])["band"]
    if got != name:
        fail.append("an average score of %s.5 rounds up to %s, got %s" % (mean_scores[1], name, got))
if rules.RECOMMENDATIONS != ("Offer", "Shortlist", "Reject"):
    fail.append("RECOMMENDATIONS must be the form's Offer / Shortlist / Reject")
print("form: %d criteria in %d groups, scored 1-5 or N/A, five bands naming the average score, three recommendations"
      % (len(rules.CRITERIA), len(rules.CRITERIA_GROUPS)))

# ── 2. Scoring ───────────────────────────────────────────────────────
def sheet(*scores):
    return [{"criterion": criterion, "score": score} for (_group, criterion), score in zip(PAPER, scores)]


full = sheet("5", "4", "4", "3", "N/A", "5", "4", "4", "3", "4", "5", "3", "4", "4", "3", "5", "5")
summary = rules.score_summary(full)
if (summary["total"], summary["maximum"], summary["percent"], summary["band"], summary["scored"], summary["not_applicable"]) \
        != (65, 80, 81.25, "Very Good", 16, 1):
    fail.append("a full sheet with one N/A: expected 65 of 80, 81.25%%, Very Good, got %s" % summary)
if rules.average_rating(summary) != 0.8125:
    fail.append("the sheet as HRMS's 0-1 rating must be 0.8125, got %s" % rules.average_rating(summary))
for total, maximum, band in ((27, 30, "Excellent"), (45, 50, "Excellent"), (26, 30, "Very Good"), (15, 20, "Very Good"),
                             (14, 20, "Very Good"), (13, 20, "Good"), (12, 20, "Good"), (10, 20, "Good"),
                             (9, 20, "Average"), (6, 20, "Average"), (5, 20, "Below Average"), (1, 5, "Below Average"),
                             (5, 5, "Excellent"), (0, 0, "")):
    if rules.band_for(total, maximum) != band:
        fail.append("%d of %d must be %r, got %r" % (total, maximum, band, rules.band_for(total, maximum)))
blank_and_na = rules.score_summary([{"score": "N/A"}, {"score": ""}, {"score": None}])
if (blank_and_na["maximum"], blank_and_na["percent"], blank_and_na["band"], blank_and_na["blank"]) != (0, 0.0, "", 2):
    fail.append("a sheet with nothing scored has no maximum, no percentage and no band: %s" % blank_and_na)
if rules.score_summary([{"score": 4}, {"score": "3 "}])["total"] != 7:
    fail.append("scores sent as numbers or with spaces must still count")
for recommendation, result in (("Offer", "Cleared"), ("Shortlist", "Cleared"), ("Reject", "Rejected"), ("", ""), (None, "")):
    if rules.result_for(recommendation) != result:
        fail.append("recommendation %r must give HRMS's result %r, got %r" % (recommendation, result, rules.result_for(recommendation)))

errors = rules.score_sheet_errors
expect("a draft with blanks", errors(sheet("5", "", ""), "", submitting=False))
expect("an N/A with no reason, submitted", errors(full, "Offer", submitting=True),
       "Row 5 (Customer care skills): say in its comments why it does not apply.")
full[4]["comments"] = "The job has no customers."
expect("a complete sheet submitted", errors(full, "Offer", submitting=True))
expect("N/A on a round's own list", errors(sheet("5", "N/A"), "", submitting=False, round_criteria=True),
       "Row 2 (Job knowledge): this round scores every criterion on its list, from 1 to 5.")
expect("a blank on a round's own list, submitted", errors(sheet("5", ""), "Offer", submitting=True, round_criteria=True),
       "Row 2 (Job knowledge): score it from 1 to 5.")
if any("or N/A" in e for e in errors(sheet("5", ""), "Offer", submitting=True, round_criteria=True)):
    fail.append("a round's own list offers no N/A, so its blank rows are not told about N/A")
expect("blanks on submit", errors(sheet("5", ""), "Offer", submitting=True), "Row 2 (Job knowledge): score it from 1 to 5")
expect("a score off the scale", errors([{"criterion": "Job knowledge", "score": "7"}], "", submitting=False),
       "the score must be 1 to 5 or N/A, not 7")
expect("a criterion twice", errors([{"criterion": "Job knowledge", "score": "4"}, {"criterion": "job knowledge", "score": "3"}],
                                   "Offer", submitting=True), "is already scored in row 1")
expect("every row N/A", errors(sheet("N/A", "N/A"), "Offer", submitting=True), "every row is N/A")
expect("no recommendation", errors(full, "", submitting=True), "Choose a recommendation")
expect("a recommendation not on the form", errors(full, "Maybe", submitting=False), "must be Offer, Shortlist or Reject")
expect("nothing to score", errors([], "Offer", submitting=True), "add the criteria under Interview Criterion")
if errors(sheet("N/A", ""), "Offer", submitting=True) and any("every row is N/A" in e for e in errors(sheet("N/A", ""), "Offer", submitting=True)):
    fail.append("a sheet with blanks must not be told every row is N/A")

rows = rules.sheet_rows([
    {"name": "Health", "criteria_group": "Health", "group_order": 50, "sort_order": 170},
    {"name": "Job knowledge", "criteria_group": "Working Experience", "group_order": 20, "sort_order": 20},
    {"name": "Old criterion", "criteria_group": "Education", "group_order": 10, "sort_order": 5, "disabled": 1},
    {"name": "Technical Qualification skills", "criteria_group": "Education", "group_order": 10, "sort_order": 10},
    {"name": "Added later", "criteria_group": "Education", "group_order": 10, "sort_order": None},
])
if [r["criterion"] for r in rows] != ["Added later", "Technical Qualification skills", "Job knowledge", "Health"]:
    fail.append("a new sheet lists criteria by group order, then their own, and leaves disabled ones out: %s" % rows)
if any(r["weight"] != 1 for r in rows):
    fail.append("on the general list each criterion counts once")
averages = rules.criterion_averages([
    [{"criterion": "Job knowledge", "score": "5"}, {"criterion": "Health", "score": "N/A"}, {"criterion": "Computer skills", "score": ""}],
    [{"criterion": "Job knowledge", "score": "4"}, {"criterion": "Health", "score": "3"}],
])
if averages != [("Job knowledge", 4.5), ("Health", 3.0)]:
    fail.append("the panel's averages ignore N/A and blanks and keep the form's order: %s" % averages)

group_records, criterion_records = rules.criteria_seed_plan([], [])
if [(g["group_name"], g["sort_order"]) for g in group_records] != [(g, (i + 1) * 10) for i, g in enumerate(rules.CRITERIA_GROUPS)]:
    fail.append("fresh seed must create the three groups ordered 10-30: %s" % group_records)
if [(c["criteria_group"], c["criterion_name"]) for c in criterion_records] != list(rules.CRITERIA) \
        or [c["sort_order"] for c in criterion_records] != [(i + 1) * 10 for i in range(len(rules.CRITERIA))]:
    fail.append("fresh seed must create the 15 criteria in the form's order, 10 apart")
if any(c["doctype"] != "Interview Criterion" for c in criterion_records) or any(g["doctype"] != "Interview Criteria Group" for g in group_records):
    fail.append("seed records must name their DocTypes")
group_records, criterion_records = rules.criteria_seed_plan(["education", "Health"], ["technical qualification skills", "Health"])
if [g["group_name"] for g in group_records] != ["Working Experience", "Personality"]:
    fail.append("seeding must skip groups already there, ignoring case: %s" % group_records)
if len(criterion_records) != 14 or any(c["criterion_name"] in ("Technical Qualification skills", "Health") for c in criterion_records):
    fail.append("seeding must skip criteria already there, ignoring case")
if any(c["criterion_name"] in rules.RETIRED_CRITERIA for c in rules.criteria_seed_plan([], [])[1]):
    fail.append("Appearance and Health are never seeded")

# a round's own list: weights, what a submitted sheet needs, the pass mark
weighed = rules.score_summary([{"score": "5", "weight": 3}, {"score": "1", "weight": 1}, {"score": "N/A", "weight": 2}])
if (weighed["total"], weighed["maximum"], weighed["percent"], weighed["band"]) != (16, 20, 80.0, "Very Good"):
    fail.append("a criterion counts as much as its weight, N/A not at all: %s" % weighed)
for weight, counted in ((0, 1), (None, 1), ("", 1), ("x", 1), (2, 2), (5, 5), (9, 5)):
    if rules.score_summary([{"score": "4", "weight": weight}])["maximum"] != 5 * counted:
        fail.append("a weight of %r counts %d times" % (weight, counted))
if (rules.WEIGHTS, rules.OFFER_FLOOR, rules.JD_GROUP) != ((1, 2, 3, 4, 5), 50, "Job Competencies"):
    fail.append("weights are 1 to 5, an Offer needs a Good sheet (50%%) where the round sets no pass mark, "
                "competencies go under Job Competencies")
se_ = rules.submission_errors
good = rules.score_summary([{"score": "3"}, {"score": "4"}])
answered = [{"question": "Which machines?", "score": "4"}, {"question": "A jam?", "score": "3"}]
expect("a sheet ready to submit", se_(good, "Offer", "Knows the machines.", 1, answered, None))
expect("no conflict tick", se_(good, "Offer", "Fine.", 0, answered, None), "Tick that you have no personal or family relationship")
expect("a question not scored", se_(good, "Reject", "Fine.", 1, [{"question": "Which machines?", "score": ""}], None),
       "Question 1: score the answer from 1 to 5.")
expect("no comments", se_(good, "Shortlist", " ", 1, answered, None), "Write your comments on the candidate's suitability")
poor = rules.score_summary([{"score": "2"}, {"score": "2"}])
expect("an Offer under the default pass mark", se_(poor, "Offer", "Keen.", 1, answered, None),
       "The sheet scores 40% (Average), under the 50% an Offer needs")
expect("an Offer under the round's pass mark", se_(rules.score_summary([{"score": "3"}] * 2), "Offer", "Keen.", 1, answered, 70),
       "under the 70% an Offer needs")
expect("an Offer on the pass mark", se_(rules.score_summary([{"score": "3"}] * 2), "Offer", "Keen.", 1, answered, 60))
expect("a low sheet recommending Reject", se_(poor, "Reject", "Not ready.", 1, answered, 60))
expect("the Offer check waits for the scores", se_({}, "Offer", "Keen.", 1, answered, 60))
for rating, percent in ((0.6, 60.0), (0.75, 75.0), (0, None), (None, None), ("x", None)):
    if rules.pass_percent(rating) != percent:
        fail.append("a pass mark of %r stars' fraction is %r%%, got %r" % (rating, percent, rules.pass_percent(rating)))
qs = rules.question_summary([{"score": "5"}, {"score": "4"}, {"score": ""}, {"score": "N/A"}])
if qs != {"scored": 2, "total": 9, "maximum": 10, "percent": 90.0} or rules.question_summary(None)["percent"] != 0.0:
    fail.append("the questions' score counts the questions scored: %s" % qs)
ce = rules.criterion_errors
for name, disabled, refused in (("Health", 0, True), ("Health", 1, False), ("HIV-status", 0, True), ("Appearance ", 0, True),
                                ("Marital Status", 0, True), ("Health and safety awareness", 0, False),
                                ("Job knowledge", 0, False), ("", 0, False)):
    if bool(ce(name, disabled)) != refused:
        fail.append("criterion %r%s must %sbe refused" % (name, " (disabled)" if disabled else "", "" if refused else "not "))
plan_rows, plan_new = rules.round_criteria_plan(
    [{"competency": "Injection Moulding", "priority": "Essential"}, {"competency": "Teamwork", "priority": "Desirable"},
     {"competency": "teamwork", "priority": "Essential"}, {"competency": "Health", "priority": "Essential"},
     {"competency": "Quality Control", "priority": ""}, {"competency": "", "priority": "Essential"}],
    {"Essential": 3, "Preferred": 2, "Desirable": 1},
    [{"criterion": "Job knowledge"}, {"criterion": "TEAMWORK"}, {"criterion": "Appearance"}],
    ["injection moulding", "Job knowledge"])
if plan_rows != [{"criterion": "injection moulding", "weight": 3}, {"criterion": "Teamwork", "weight": 1},
                 {"criterion": "Quality Control", "weight": 1}, {"criterion": "Job knowledge", "weight": 1}] \
        or plan_new != ["Teamwork", "Quality Control"]:
    fail.append("a round's criteria: the JD's competencies weighed by priority, under their existing spelling, then the "
                "general list, nothing twice or never scored: %s %s" % (plan_rows, plan_new))
rce = rules.round_criteria_errors
expect("a sound round list", rce([{"criterion": "Job knowledge", "weight": 3}, {"criterion": "Teamwork", "weight": 1}], []))
expect("a criterion twice", rce([{"criterion": "Job knowledge", "weight": 1}, {"criterion": "job knowledge", "weight": 2}], []),
       "Score Sheet row 2: job knowledge is already in row 1.")
expect("a weight off the scale", rce([{"criterion": "Job knowledge", "weight": 0}, {"criterion": "Teamwork", "weight": 6}], []),
       "row 1 (Job knowledge): the weight must be 1 to 5, not 0", "row 2 (Teamwork): the weight must be 1 to 5, not 6")
expect("a criterion switched off", rce([{"criterion": "Old One", "weight": 1}], ["old one"]), "Old One is switched off")
expect("a criterion never scored", rce([{"criterion": "Health", "weight": 1}], []), "Health is not scored at interview")
print("scoring: totals, N/A, blanks, every boundary of the scale, results, errors, order, panel averages and seeding correct")

# ── 3. The masters and the score rows ────────────────────────────────
for master, name_field in (("Interview Criteria Group", "group_name"), ("Interview Criterion", "criterion_name")):
    spec_json = doctype_json(master)
    fields = fields_of(spec_json)
    if spec_json.get("istable") or spec_json.get("module") != "HRMS Addon" or spec_json.get("name") != master:
        fail.append("%s must be an HRMS Addon master" % master)
    if spec_json.get("autoname") != "field:%s" % name_field or not (fields.get(name_field) or {}).get("reqd"):
        fail.append("%s must be named by its mandatory %s" % (master, name_field))
    for flag in ("allow_rename", "allow_import", "quick_entry"):
        if not spec_json.get(flag):
            fail.append("%s must set %s" % (master, flag))
    if (spec_json.get("sort_field"), spec_json.get("sort_order")) != ("sort_order", "ASC"):
        fail.append("%s must list by Display Order" % master)
    if (fields.get("sort_order") or {}).get("fieldtype") != "Int":
        fail.append("%s needs an Int Display Order (sort_order)" % master)
    perms = {p["role"]: p for p in spec_json.get("permissions", [])}
    for role in ("HR Manager", "HR User"):
        if not all((perms.get(role) or {}).get(k) for k in ("read", "write", "create")):
            fail.append("%s: %s must be able to add and change values" % (master, role))
    if not (perms.get("Interviewer") or {}).get("read"):
        fail.append("%s: the Interviewer role must be able to read it (panel members score against it)" % master)
    folder = master.lower().replace(" ", "_")
    controller = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    if not re.search(r"^class %s\(Document\):" % master.replace(" ", ""), controller, re.M) \
            or "jd_rules.next_display_order(" not in controller:
        fail.append("%s controller must give a value added without a Display Order the next one" % master)
criterion = fields_of(doctype_json("Interview Criterion"))
if (criterion.get("criteria_group") or {}).get("options") != "Interview Criteria Group" or not criterion["criteria_group"].get("reqd"):
    fail.append("Interview Criterion.criteria_group must be a mandatory Link to Interview Criteria Group")
if (criterion.get("disabled") or {}).get("fieldtype") != "Check":
    fail.append("Interview Criterion needs a Disabled check, so HR can retire a criterion without losing old sheets")

score_spec = doctype_json("Interview Feedback Score")
score_fields = fields_of(score_spec)
if not score_spec.get("istable") or list(score_fields) != ["criteria_group", "criterion", "weight", "score", "comments"]:
    fail.append("Interview Feedback Score must be a child table of criteria_group, criterion, weight, score, comments")
if (score_fields.get("weight") or {}).get("fieldtype") != "Int" or not score_fields["weight"].get("read_only"):
    fail.append("a score row's weight is the round's: a read-only Int")
round_spec = doctype_json("Interview Round Criterion")
round_fields = fields_of(round_spec)
if not round_spec.get("istable") or list(round_fields) != ["criterion", "criteria_group", "weight"] \
        or (round_fields["criterion"].get("options"), round_fields["criterion"].get("reqd")) != ("Interview Criterion", 1) \
        or round_fields["criteria_group"].get("fetch_from") != "criterion.criteria_group" \
        or (round_fields["weight"].get("fieldtype"), round_fields["weight"].get("default"), round_fields["weight"].get("reqd")) \
        != ("Int", "1", 1):
    fail.append("Interview Round Criterion is a child table of a mandatory criterion, its group fetched, and a weight of 1 by default")
if "class InterviewRoundCriterion(Document):" not in read("hrms_addon", "hrms_addon", "doctype", "interview_round_criterion",
                                                            "interview_round_criterion.py"):
    fail.append("Interview Round Criterion needs its controller, or migrate stops at it")
if sum(f.get("columns") or 0 for f in round_spec["fields"] if f.get("in_list_view")) > 10:
    fail.append("the round's criteria grid exceeds Frappe's 10 columns")
if (score_fields.get("score") or {}).get("options", "").split("\n") != list(rules.SCORE_OPTIONS):
    fail.append("the score options must be exactly the form's scale %s" % (rules.SCORE_OPTIONS,))
for fieldname, target in (("criterion", "Interview Criterion"), ("criteria_group", "Interview Criteria Group")):
    f = score_fields.get(fieldname) or {}
    if (f.get("fieldtype"), f.get("options"), f.get("read_only")) != ("Link", target, 1):
        fail.append("Interview Feedback Score.%s must be a read-only Link to %s: the rows come from the list" % (fieldname, target))
if sum(f.get("columns") or 0 for f in score_spec["fields"] if f.get("in_list_view")) > 10:
    fail.append("the score grid exceeds Frappe's 10 columns")
print("masters: groups and criteria renameable, importable, ordered; score rows read-only apart from score and comments")

# ── 4. Interview Feedback, Interview Type and Job Applicant fields ────
IF = "Interview Feedback"
for fieldname, fieldtype, options in (
    ("custom_scores", "Table", "Interview Feedback Score"),
    ("custom_total_score", "Int", None), ("custom_max_score", "Int", None),
    ("custom_score_percent", "Percent", None), ("custom_score_band", "Data", None),
    ("custom_interviewer_designation", "Data", None),
):
    f = by_name.get("%s-%s" % (IF, fieldname)) or {}
    if (f.get("fieldtype"), f.get("options")) != (fieldtype, options):
        fail.append("%s.%s must be a %s%s" % (IF, fieldname, fieldtype, " of %s" % options if options else ""))
    if fieldname != "custom_scores" and not f.get("read_only"):
        fail.append("%s.%s is worked out on save, so it must be read-only" % (IF, fieldname))
recommendation = by_name.get("%s-custom_recommendation" % IF) or {}
if recommendation.get("fieldtype") != "Select" or [o for o in recommendation.get("options", "").split("\n") if o] != list(rules.RECOMMENDATIONS):
    fail.append("%s.custom_recommendation must offer exactly %s" % (IF, rules.RECOMMENDATIONS))
if recommendation.get("reqd"):
    fail.append("%s.custom_recommendation must not be mandatory on a draft; submitting requires it" % IF)
for fieldname in ("custom_current_benefits", "custom_expected_benefits", "custom_notice_period"):
    if "Job Applicant-%s" % fieldname not in by_name:
        fail.append("Job Applicant.%s is missing: the score sheet prints the candidate's salary history" % fieldname)
for name, value in (
    ("Interview Feedback-skill_assessment-reqd", "0"), ("Interview Feedback-skill_assessment-hidden", "1"),
    ("Interview Feedback-section_break_4-hidden", "1"), ("Interview Feedback-result-reqd", "0"),
    ("Interview Feedback-result-read_only", "1"), ("Interview Type-expected_skill_set-reqd", "0"),
    ("Interview Type-expected_skill_set-hidden", "1"),
):
    if (setters.get(name) or {}).get("value") != value:
        fail.append("property setter %s must be %s" % (name, value))
PRINT_NAME = "Candidate Interview Evaluation Score Form"
if (setters.get("Interview Feedback-main-default_print_format") or {}).get("value") != PRINT_NAME:
    fail.append("Interview Feedback must print %s by default" % PRINT_NAME)
for name, fieldtype, options, flags in (
        ("Interview Feedback-custom_round_criteria", "Check", None, ("read_only", "hidden")),
        ("Interview Feedback-custom_question_percent", "Percent", None, ("read_only",)),
        ("Interview Feedback-custom_no_conflict", "Check", None, ()),
        ("Interview Type-custom_criteria", "Table", "Interview Round Criterion", ("allow_bulk_edit",)),
        ("Interview-custom_criteria", "Table", "Interview Round Criterion", ("read_only",))):
    f = by_name.get(name) or {}
    if (f.get("fieldtype"), f.get("options")) != (fieldtype, options) or not all(f.get(flag) for flag in flags):
        fail.append("%s must be a %s%s, %s" % (name, fieldtype, " of %s" % options if options else "", ", ".join(flags) or "editable"))
if (by_name.get("Interview Feedback-custom_no_conflict") or {}).get("reqd"):
    fail.append("the conflict tick is asked for on submit, not on every draft")
if "The rating is the average score, rounded." not in (by_name.get("Interview Feedback-custom_evaluation_section") or {}).get(
        "description", "") or "%" in (by_name.get("Interview Feedback-custom_evaluation_section") or {}).get("description", ""):
    fail.append("the sheet's scale says the rating is the average score, rounded, and quotes no percentages")
if (setters.get("Interview Type-expected_average_rating-label") or {}).get("value") != "Pass Mark":
    fail.append("the round's Expected Average Rating is its Pass Mark")
print("fields: the score sheet on Interview Feedback, HRMS's skill ratings set aside, salary history on Job Applicant")

# ── 5. Wiring ────────────────────────────────────────────────────────
def hook_block(name):
    m = re.search(r"^%s = \{(.*?)^\}" % name, hooks, re.S | re.M) or re.search(r"^%s = \[(.*?)^\]" % name, hooks, re.S | re.M)
    return m.group(1) if m else ""


if not re.search(r'"Interview Feedback": \{[^}]*"validate": "hrms_addon\.hrms_addon\.interviews\.feedback_validate"', hook_block("doc_events")):
    fail.append("doc_events must run interviews.feedback_validate on Interview Feedback validate")
for doctype, path in (("Interview", "public/js/interview.js"), ("Interview Feedback", "public/js/interview_feedback.js")):
    if '"%s": "%s"' % (doctype, path) not in hook_block("doctype_js") or not os.path.exists(os.path.join(REPO, "hrms_addon", path)):
        fail.append("doctype_js must load %s for %s" % (path, doctype))
if not re.search(r'"hrms\.hr\.doctype\.interview\.interview\.get_skill_wise_average_rating": \(\s*"hrms_addon\.hrms_addon\.interviews\.get_skill_wise_average_rating"',
                 hook_block("override_whitelisted_methods")):
    fail.append("override_whitelisted_methods must send the Feedback tab's averages to interviews.get_skill_wise_average_rating")
if '"hrms_addon.hrms_addon.interviews.after_install"' not in hook_block("after_install"):
    fail.append("after_install must seed the criteria (patches do not run on a fresh install)")
if "hrms_addon.patches.v1_0.seed_interview_criteria" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1]:
    fail.append("seed_interview_criteria must be a post_model_sync patch")
patch_src = read("hrms_addon", "patches", "v1_0", "seed_interview_criteria.py")
if "from hrms_addon.hrms_addon.interviews import seed_interview_criteria" not in patch_src \
        or not re.search(r"def execute\(\):\n    seed_interview_criteria\(\)", patch_src):
    fail.append("the patch must call interviews.seed_interview_criteria")
for method in ("get_score_criteria", "get_skill_wise_average_rating"):
    if not re.search(r"@frappe\.whitelist\(\)\s*\ndef %s\(" % method, glue):
        fail.append("interviews.%s must be whitelisted" % method)
for needle, why in (
    ("rules.score_sheet_errors(doc.custom_scores, recommendation, submitting=submitting,\n"
     "                                      round_criteria=bool(doc.get(\"custom_round_criteria\")))",
     "must check the sheet with the tested rules, strictly only on submit, N/A by the round"),
    ("submitting = doc.docstatus == 1", "must be strict only on submit"),
    ("errors += rules.submission_errors({} if errors else summary, recommendation, doc.get(\"feedback\"),\n"
     "                                          doc.get(\"custom_no_conflict\"), doc.get(\"custom_answers\"), pass_mark)",
     "must ask on submit for the conflict tick, the comments, every question scored and an Offer at the pass mark"),
    ("rules.pass_percent(frappe.db.get_value(\"Interview\", doc.interview, \"expected_average_rating\"))",
     "must take the pass mark the interview was booked with"),
    ("doc.custom_question_percent = rules.question_summary(doc.get(\"custom_answers\"))[\"percent\"]",
     "must work the questions' score out"),
    ("row.weight = weights.get(row.criterion, 1) if doc.custom_round_criteria else 1",
     "must take the weights from the round, whatever was posted"),
    ("doc.custom_round_criteria = 1 if weights and {row.criterion for row in doc.custom_scores} == set(weights) else 0",
     "must know a round's own list by its criteria"),
    ("doc.average_rating = rules.average_rating(summary)", "must feed the sheet's percentage to HRMS's average rating"),
    ("doc.result = rules.result_for(recommendation)", "must set HRMS's result from the recommendation"),
    ('frappe.has_permission("Interview", "read", interview, throw=True)', "must check the reader may see the Interview"),
    ("return hrms_averages(interview)", "must fall back to HRMS's skill averages for an interview scored on skills"),
    ("rules.criteria_seed_plan(", "must seed with the tested plan"),
    ("insert(ignore_permissions=True)", "must seed regardless of the migrating user's permissions"),
):
    if needle not in glue:
        fail.append("interviews.py %s" % why)
if "def after_install():\n    seed_interview_criteria()" not in glue:
    fail.append("interviews.after_install must seed the criteria")

ijs = read("hrms_addon", "public", "js", "interview.js")
off = ijs.find('frappe.ui.form.off("Interview", "submit_feedback");')
on = ijs.find('frappe.ui.form.on("Interview", {')
if off < 0 or on < off:
    fail.append("interview.js must drop HRMS's submit_feedback handler (frappe.ui.form.off) before adding its own")
if not re.search(r'submit_feedback\(frm\) \{.*?frappe\.new_doc\("Interview Feedback", \{(.*?)\}\);', ijs, re.S):
    fail.append("interview.js Submit Feedback must open a new Interview Feedback")
else:
    passed = re.search(r'frappe\.new_doc\("Interview Feedback", \{(.*?)\}\);', ijs, re.S).group(1)
    for key in ("interview:", "interviewer: frappe.session.user", "interview_type:", "job_applicant:"):
        if key not in passed:
            fail.append("interview.js must pass %s to the new sheet (a new document's values are not fetched)" % key.rstrip(":"))
fjs = read("hrms_addon", "public", "js", "interview_feedback.js")
js_bands = [(int(floor), name) for floor, name in re.findall(r'\[(\d+), "([^"]+)"\]', fjs.split("const HA_SCORE_BANDS = [")[-1].split("];")[0])]
if tuple(js_bands) != rules.BANDS:
    fail.append("interview_feedback.js HA_SCORE_BANDS %s must match interview_rules.BANDS" % js_bands)
js_results = dict(re.findall(r"(\w+): \"(\w+)\"", fjs.split("const HA_RESULTS = {")[-1].split("};")[0]))
if js_results != rules.RESULTS:
    fail.append("interview_feedback.js HA_RESULTS %s must match interview_rules.RESULTS" % js_results)
round_scale = re.search(r"const HA_ROUND_SCALE = \[([^\]]*)\];", fjs)
if not round_scale or re.findall(r'"([^"]*)"', round_scale.group(1)) != [o for o in rules.SCORE_OPTIONS if o != rules.NOT_APPLICABLE]:
    fail.append("interview_feedback.js HA_ROUND_SCALE must be the scale without N/A")
for needle, why in (
    ('.xcall("hrms_addon.hrms_addon.interviews.get_score_criteria", { interview: frm.doc.interview || null })',
     "must start a new sheet from the round's criteria or the general list"),
    ('grid.update_docfield_property("score", "options", HA_ROUND_SCALE.join(', "must offer no N/A on a round's own list"),
    ("total += score * weight;", "must weigh the live total like the server"),
    ('frm.set_df_property(HA_SCORE_TABLE, "cannot_add_rows", true)', "must stop rows being added by hand"),
    ('frm.set_df_property(HA_SCORE_TABLE, "cannot_delete_rows", true)', "must stop rows being removed by hand"),
    ("total * 100 >= floor * maximum", "must compare in whole numbers, like interview_rules.band_for"),
):
    if needle not in fjs:
        fail.append("interview_feedback.js %s" % why)
for name, js in (("interview.js", ijs), ("interview_feedback.js", fjs)):
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", js, flags=re.S)
    for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
        if stripped.count(op) != stripped.count(cl):
            fail.append("%s: unbalanced %s%s" % (name, op, cl))
print("wiring: save check, form scripts, Submit Feedback, Feedback tab averages, seeding by patch and after_install")

# ── 6. Print format ──────────────────────────────────────────────────
pf = json.load(open(os.path.join(APP, "print_format", "candidate_interview_evaluation_score_form",
                                 "candidate_interview_evaluation_score_form.json"), encoding="utf-8"))
if (pf.get("doctype"), pf.get("name"), pf.get("doc_type"), pf.get("module"), pf.get("standard"), pf.get("print_format_type"),
        pf.get("custom_format"), pf.get("disabled")) != ("Print Format", PRINT_NAME, IF, "HRMS Addon", "Yes", "Jinja", 1, 0):
    fail.append("the score form must be a standard, enabled Jinja print format of Interview Feedback in HRMS Addon")
html = pf.get("html") or ""
for block in ("for", "if", "macro"):
    opened = len(re.findall(r"{%-?\s*" + block + r"\b", html))
    closed = len(re.findall(r"{%-?\s*end" + block + r"\b", html))
    if opened != closed:
        fail.append("print format: %d {%% %s %%} but %d {%% end%s %%}" % (opened, block, closed, block))
if html.count("{{") != html.count("}}") or html.count("{%") != html.count("%}"):
    fail.append("print format: unbalanced {{ }} or {% %}")
printed = re.sub(r"{#.*?#}", "", html, flags=re.S)  # what prints, not the template's own notes
if "<td>LPL/HR/17</td>" not in printed or "CANDIDATE INTERVIEW EVALUATION /SCORE FORM" not in printed:
    fail.append("print format must carry the form's title and reference LPL/HR/17")
raw = re.findall(r"{{-?\s*(?:doc|row|applicant)\.(?!custom_total_score|custom_max_score)[a-z_]+", html)
if raw:
    fail.append("print format must print text through v() so it is escaped: %s" % raw[:3])
if UPSTREAM_OK:
    feedback_fields = set(fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview_feedback", "interview_feedback.json"))))
    feedback_fields |= {f["fieldname"] for f in custom if f["dt"] == IF} | {"name", "docstatus", "modified"}
    for fieldname in set(re.findall(r"\bdoc\.([a-z_]+)", html)):
        if fieldname not in feedback_fields:
            fail.append("print format uses Interview Feedback.%s, which does not exist" % fieldname)
    applicant_fields = set(fields_of(json.loads(upstream("hrms", "hr", "doctype", "job_applicant", "job_applicant.json"))))
    applicant_fields |= {f["fieldname"] for f in custom if f["dt"] == "Job Applicant"}
    listed = re.search(r'get_value\("Job Applicant", doc\.job_applicant,\s*\[(.*?)\]', html, re.S)
    for fieldname in re.findall(r'"([a-z_]+)"', listed.group(1) if listed else ""):
        if fieldname not in applicant_fields:
            fail.append("print format reads Job Applicant.%s, which does not exist" % fieldname)
    for attribute in set(re.findall(r"\bapplicant\.([a-z_]+)", html)):
        if attribute not in re.findall(r'"([a-z_]+)"', listed.group(1) if listed else ""):
            fail.append("print format prints applicant.%s without reading it" % attribute)
for attribute in set(re.findall(r"\brow\.([a-z_]+)", html)):
    if attribute not in score_fields:
        fail.append("print format prints Interview Feedback Score.%s, which does not exist" % attribute)
print("print format: LPL/HR/17, balanced blocks, every printed field exists, text escaped")

# ── 7. What the design relies on in HRMS ──────────────────────────────
if UPSTREAM_OK:
    hrms_ijs = upstream("hrms", "hr", "doctype", "interview", "interview.js")
    # the button interviewers press is the primary action; the other trigger is a disabled look-alike
    if not re.search(r'set_primary_action\(__\("Submit Feedback"\),\s*\(\)\s*=>\s*\{\s*frm\.trigger\("submit_feedback"\);', hrms_ijs):
        fail.append("HRMS's Submit Feedback no longer triggers submit_feedback: recheck interview.js")
    hrms_ipy = upstream("hrms", "hr", "doctype", "interview", "interview.py")
    if not re.search(r"@frappe\.whitelist\(\)\s*\ndef get_skill_wise_average_rating\(interview", hrms_ipy):
        fail.append("HRMS moved get_skill_wise_average_rating: the override in hooks.py would no longer apply")
    hrms_fpy = upstream("hrms", "hr", "doctype", "interview_feedback", "interview_feedback.py")
    if "Avg(interview_feedback.average_rating)" not in hrms_fpy or "self.calculate_average_rating()" not in hrms_fpy:
        fail.append("HRMS's Interview Feedback no longer averages average_rating into the Interview: recheck feedback_validate")
    template = upstream("hrms", "public", "js", "templates", "interview_feedback.html")
    if "d.skill" not in template or "d.rating * 5" not in template:
        fail.append("HRMS's Feedback tab no longer reads skill / rating: recheck get_skill_wise_average_rating")
    hrms_feedback = fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview_feedback", "interview_feedback.json")))
    for fieldname in ("skill_assessment", "section_break_4", "result", "feedback", "section_break_7", "average_rating", "interviewer"):
        if fieldname not in hrms_feedback:
            fail.append("HRMS's Interview Feedback has no %s any more: recheck the fixtures" % fieldname)
    if (hrms_feedback.get("interview_type") or {}).get("fetch_from") != "interview.interview_type":
        fail.append("HRMS's Interview Feedback no longer fetches its Interview Type")
    upstream_note = "checked against HRMS"
else:
    upstream_note = "HRMS not found at %s, upstream contract not checked" % APPS_ROOT
print("HRMS contract: %s" % upstream_note)

# ── 8. The interview shortlist ───────────────────────────────────────
spec = importlib.util.spec_from_file_location("bio_data_rules", os.path.join(APP, "bio_data_rules.py"))
bio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bio)
CERTS = bio.CERTIFICATION_TYPES
quals = [
    {"qualification_type": "Academic", "program": "Bachelor's Degree in Business Computing",
     "institution": "Makerere University Business School", "period": "2008 - 2012"},
    {"qualification_type": "academic", "program": "Post Graduate Diploma in Digital Marketing",
     "institution": "Chartered Institute of Marketing", "period": "2026"},
    {"qualification_type": "Professional Certification", "program": "Certificate in Customer Experience Design",
     "institution": "Alison Courses", "period": "2024"},
    {"qualification_type": "", "award": "UACE", "institution": "East High School Ntinda", "period": "2017"},
    {"qualification_type": "Licence", "program": "Class B Driving Permit", "institution": "", "period": ""},
]
# a site whose Licence type is still carried by someone, so kept (and ticked)
# by remove_licence_qualification_type
SITE_CERTS = list(CERTS) + ["Licence"]
education = rules.qualification_lines(quals, SITE_CERTS, certifications=False)
if education.split("\n") != [
        "Post Graduate Diploma in Digital Marketing, Chartered Institute of Marketing (2026)",
        "UACE, East High School Ntinda (2017)",
        "Bachelor's Degree in Business Computing, Makerere University Business School (2008 - 2012)"]:
    fail.append("education must list the academic rows, most recent first, award standing in for a missing program: %r" % education)
certifications = rules.qualification_lines(quals, [c.lower() for c in SITE_CERTS], certifications=True)
if certifications.split("\n") != ["Certificate in Customer Experience Design, Alison Courses (2024)", "Class B Driving Permit"]:
    fail.append("certifications must list the certification and licence rows, whatever the case: %r" % certifications)
history = [
    {"position": "Retail Manager", "workplace": "Africell Uganda Limited", "from_year": "Sept 2016", "to_year": "Apr 2020"},
    {"position": "Operations Coordinator", "workplace": "Leanstar Trading Limited", "from_year": "Nov 2023", "to_year": ""},
    {"position": "Key Account Manager", "workplace": "Echotel Uganda Limited", "from_year": "May 2022", "to_year": "Sept 2023"},
    {"position": "Volunteer", "workplace": "Red Cross", "from_year": "", "to_year": ""},
]
experience = rules.experience_lines(history)
if experience.split("\n") != [
        "Operations Coordinator, Leanstar Trading Limited (Nov 2023 - Present)",
        "Key Account Manager, Echotel Uganda Limited (May 2022 - Sept 2023)",
        "Retail Manager, Africell Uganda Limited (Sept 2016 - Apr 2020)",
        "Volunteer, Red Cross"]:
    fail.append("work experience must put the current job first and undated ones last: %r" % experience)
if rules.contact_line("Rinah Eupal", "0703900711", "rinaeupallorika@gmail.com") != "Rinah Eupal, 0703900711, rinaeupallorika@gmail.com" \
        or rules.contact_line("Mark Henry", None, " ") != "Mark Henry":
    fail.append("the name column is name, phone and email, leaving out what is blank")
if rules.qualification_lines([], CERTS, False) or rules.experience_lines(None):
    fail.append("an applicant with no Bio-Data rows gets empty columns")
se = rules.shortlist_errors
expect("an empty draft", se("JO-1", [], {}, submitting=False))
expect("an empty shortlist submitted", se("JO-1", [], {}, submitting=True), "Add the applicants invited to interview")
expect("a clean shortlist", se("JO-1", [{"job_applicant": "A"}, {"job_applicant": "B"}], {"A": "JO-1", "B": "JO-1"}, submitting=True))
expect("an applicant twice", se("JO-1", [{"job_applicant": "A"}, {"job_applicant": "A"}], {"A": "JO-1"}, submitting=False),
       "Row 2: A is already listed in row 1.")
expect("an applicant for another opening", se("JO-1", [{"job_applicant": "B"}], {"B": "JO-2"}, submitting=False),
       "Row 1: B applied for JO-2, not this opening.")
# the slots of a round: a gap for scoring, the lunch break, the day's end, the next working day
ps = rules.plan_slots
if ps("2026-10-08", "09:00", 30, 3) != [("2026-10-08", "09:00:00", "09:30:00"), ("2026-10-08", "09:30:00", "10:00:00"),
                                       ("2026-10-08", "10:00:00", "10:30:00")] or ps("2026-10-08", "09:00", 20, 0) != []:
    fail.append("with no gap, lunch or day's end, slots run back to back from the first start time")
WEEKEND = ("2026-10-10", "2026-10-11")
day = ps("2026-10-09", "09:00", 60, 9, gap=10, lunch=("13:00", "14:00"), day_end="17:00",
         is_working_day=lambda d: d not in WEEKEND)
if day != [("2026-10-09", "09:00:00", "10:00:00"), ("2026-10-09", "10:10:00", "11:10:00"), ("2026-10-09", "11:20:00", "12:20:00"),
           ("2026-10-09", "14:00:00", "15:00:00"), ("2026-10-09", "15:10:00", "16:10:00"), ("2026-10-12", "09:00:00", "10:00:00"),
           ("2026-10-12", "10:10:00", "11:10:00"), ("2026-10-12", "11:20:00", "12:20:00"), ("2026-10-12", "14:00:00", "15:00:00")]:
    fail.append("slots keep the gap, skip the lunch break, stop at the day's end and carry on the next working day: %s" % day)
import datetime as _dt  # noqa: E402

if ps("2026-10-08", _dt.timedelta(hours=12, minutes=30), 45, 2, lunch=(_dt.timedelta(hours=13), "14:00:00")) \
        != [("2026-10-08", "14:00:00", "14:45:00"), ("2026-10-08", "14:45:00", "15:30:00")]:
    fail.append("a slot that would run into lunch starts after it; times may come as the database's timedelta")
for args, kwargs, why in ((("2026-10-08", "09:00", 0, 2), {}, "a length of 0"), (("2026-10-08", "", 30, 1), {}, "no start time"),
                          (("2026-10-08", "16:30", 45, 1), {"day_end": "17:00"}, "an interview that fits no day"),
                          (("2026-10-10", "09:00", 30, 1), {"is_working_day": lambda d: d not in WEEKEND}, "a weekend"),
                          (("2026-10-08", "09:00", 30, 1), {"lunch": ("14:00", "13:00")}, "a lunch ending before it starts"),
                          (("2026-10-08", "09:00", 30, 3), {"is_working_day": lambda d: d == "2026-10-08", "day_end": "09:30"},
                           "no working day ahead")):
    try:
        ps(*args, **kwargs)
        fail.append("plan_slots must refuse %s" % why)
    except ValueError:
        pass
bp = rules.booking_plan({"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}, [], ["B"],
                        {"A": "Shortlisted", "B": "Shortlisted", "C": "Rejected", "D": "Shortlisted", "E": "Hold", "F": ""},
                        True, ["A", "E", "C"])
if bp != {"book": ["A", "E"], "already": ["B"], "out": [("C", "Rejected")], "not_cleared": ["D"]}:
    fail.append("a round books those still in the running who cleared the round before, never twice: %s" % bp)
if rules.booking_plan(["A", "B"], ["B"], [], {"A": "Open", "B": "Accepted"}, False, []) \
        != {"book": [], "already": [], "out": [("B", "Accepted")], "not_cleared": []}:
    fail.append("a ticked applicant already hired is not booked; the unticked are not considered")
if rules.booking_plan(["A"], [], [], {"A": "Open"}, False, [])["book"] != ["A"]:
    fail.append("a first round needs no round before it")
if rules.earlier_round([("R1a", 1), ("R2a", 2), ("R2b", "2"), ("R3", 3), ("None", 0)], 3) != ["R2a", "R2b"] \
        or rules.earlier_round([("R1", 1)], 1) != [] or rules.earlier_round([], 2) != []:
    fail.append("the round before is every type of the highest round number below this one")
clash = rules.clashes([("2026-10-08", "09:00:00", "10:00:00"), ("2026-10-09", "09:00:00", "10:00:00")], ["hod@lpl", ""],
                      [("hod@lpl", "2026-10-08", "09:30:00", "10:30:00", "HR-INT-1"),
                       ("hod@lpl", "2026-10-08", "10:00:00", "11:00:00", "HR-INT-2"),
                       ("sup@lpl", "2026-10-08", "09:00:00", "10:00:00", "HR-INT-3")],
                      [("hod@lpl", "2026-10-09", "2026-10-12"), ("sup@lpl", "2026-10-08", "2026-10-08")])
if clash != ["hod@lpl sits on another interview (HR-INT-1) on 2026-10-08 from 09:30 to 10:30.",
             "hod@lpl is on leave on 2026-10-09."]:
    fail.append("the panel clashes with an overlapping interview or leave, not one that only touches: %s" % clash)
for args, over in ((("2026-10-08", "10:00:00", "2026-10-08 10:00:00"), True), (("2026-10-08", "10:00:00", "2026-10-08 09:59:59"), False),
                   (("2026-10-07", "23:00:00", "2026-10-08 00:01:00"), True), (("2026-10-09", "08:00:00", "2026-10-08 12:00:00"), False),
                   ((None, "10:00", "2026-10-08 12:00"), False)):
    if rules.slot_over(*args) is not over:
        fail.append("slot_over%s must be %s" % (args, over))
for attendance, status, after in (("No-Show", "Pending", "Cancelled"), ("Withdrew", "Under Review", "Cancelled"),
                                  ("No-Show", "Cancelled", None), ("Attended", "Pending", "Under Review"),
                                  ("Attended", "Cancelled", "Under Review"), ("Attended", "Cleared", None), ("", "Pending", None)):
    if rules.status_for_attendance(attendance, status) != after:
        fail.append("attendance %r on a %s interview must make it %r" % (attendance, status, after))
if (rules.ATTENDANCE, rules.ABSENT, rules.MODES) != (("Attended", "No-Show", "Withdrew"), ("No-Show", "Withdrew"),
                                                     ("In Person", "Video Call", "Phone Call")):
    fail.append("attendance is Attended, No-Show or Withdrew; an interview is in person, by video or by phone")
sms = rules.invitation_sms("Luuka Plastics", "Machine Operator", "Monday 5 October 2026", "09:00", "In Person", "Kawempe plant")
if sms != "Luuka Plastics: interview for Machine Operator on Monday 5 October 2026 at 09:00 at Kawempe plant. Details by email." \
        or "by video call" not in rules.invitation_sms("L", "M", "d", "t", "Video Call", "Kawempe") \
        or len(sms) > 160:
    fail.append("the invitation by SMS says what for, when and where, in one text: %r" % sms)
for args, due in ((("Rejected", None, None, "a@x.com"), True), (("Rejected", "2026-10-01", None, "a@x.com"), False),
                  (("Rejected", None, "HR-OFF-1", "a@x.com"), False), (("Rejected", None, None, ""), False),
                  (("Shortlisted", None, None, "a@x.com"), False)):
    if rules.regret_due(*args) is not due:
        fail.append("regret_due%s must be %s" % (args, due))
for body, keys in ((rules.INVITATION_SUBJECT + rules.INVITATION_BODY, rules.INVITATION_KEYS),
                   (rules.REGRET_SUBJECT + rules.REGRET_BODY, rules.REGRET_KEYS)):
    named = set(re.findall(r"\{\{\s*\(?\s*([a-z_]+)", body)) | set(re.findall(r"\{%\s*(?:el)?if\s+([a-z_]+)", body))
    if not named <= set(keys):
        fail.append("a letter names %s, which it is not always given (Frappe prints them as they are)" % sorted(named - set(keys)))
    for block in ("if",):
        if len(re.findall(r"\{%\s*" + block + r"\b", body)) != len(re.findall(r"\{%\s*end" + block + r"\b", body)):
            fail.append("a letter has unbalanced {%% %s %%} blocks" % block)
    for name in ("applicant_name", "what_to_bring", "venue", "meeting_link"):
        if re.search(r"\{\{\s*\(?%s(?![^}]*\|\s*e\b)" % name, body):
            fail.append("a letter prints %s without escaping it" % name)
if set(rules.SHORTLISTABLE_STATUSES) != {"Open", "Replied", "Hold", "Shortlisted"}:
    fail.append("only applicants not yet turned down or hired can be shortlisted: %s" % (rules.SHORTLISTABLE_STATUSES,))

qt = doctype_json("Qualification Type")
qt_fields = fields_of(qt)
if (qt_fields.get("is_certification") or {}).get("fieldtype") != "Check":
    fail.append("Qualification Type needs its Certification or Licence check")
if bio.BIO_DATA_MASTERS.get("Qualification Type", (None,))[0] != "type_name" \
        or not set(CERTS) <= set(bio.BIO_DATA_MASTERS.get("Qualification Type", (None, ()))[1]):
    fail.append("Qualification Type must be a Bio-Data pick list seeded with the certification types %s" % (CERTS,))
aq = fields_of(doctype_json("Applicant Qualification"))
if (aq.get("qualification_type") or {}).get("options") != "Qualification Type":
    fail.append("Applicant Qualification needs a Type linking to Qualification Type")
web_form = json.load(open(os.path.join(APP, "web_form", "job_application_form", "job_application_form.json"), encoding="utf-8"))
quals_field = next((f for f in web_form["web_form_fields"] if f.get("fieldname") == "custom_qualifications"), {})
if not quals_field.get("allow_read_on_all_link_options"):
    fail.append("the application form must let candidates pick a Qualification Type (allow_read_on_all_link_options)")
picks = read("hrms_addon", "hrms_addon", "pick_lists.py")
for needle, why in (
    ("def after_install():\n    seed_masters(MASTERS)\n    flag_certification_types()", "after_install must flag the certification types it seeds"),
    ('seed_masters({"Qualification Type": bio_data_rules.BIO_DATA_MASTERS["Qualification Type"]})\n    flag_certification_types()',
     "seed_qualification_types must seed the list, then flag the certification types"),
    ('frappe.db.set_value("Qualification Type", name, "is_certification", 1)', "must tick Certification or Licence on the seeded types"),
):
    if needle not in picks:
        fail.append("pick_lists.py %s" % why)
patch_src = read("hrms_addon", "patches", "v1_0", "seed_qualification_types.py")
if "hrms_addon.patches.v1_0.seed_qualification_types" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1] \
        or not re.search(r"def execute\(\):\n    seed_qualification_types\(\)", patch_src):
    fail.append("seed_qualification_types must be a post_model_sync patch calling pick_lists.seed_qualification_types")

shl = doctype_json("Interview Shortlist")
shl_fields = fields_of(shl)
if not shl.get("is_submittable") or shl.get("autoname") != "HR-SHL-.YYYY.-.####" or shl.get("default_print_format") != "Interview Shortlist":
    fail.append("Interview Shortlist must be submittable, named HR-SHL-YYYY-####, and print the shortlist by default")
if (shl_fields.get("job_opening") or {}).get("options") != "Job Opening" or not shl_fields["job_opening"].get("reqd"):
    fail.append("Interview Shortlist.job_opening must be a mandatory Link to Job Opening")
if (shl_fields.get("designation") or {}).get("fetch_from") != "job_opening.designation":
    fail.append("the shortlist's position must be fetched from the Job Opening")
if (shl_fields.get("candidates") or {}).get("options") != "Interview Shortlist Candidate":
    fail.append("Interview Shortlist.candidates must be a Table of Interview Shortlist Candidate")
if (shl_fields.get("amended_from") or {}).get("options") != "Interview Shortlist":
    fail.append("a submittable Interview Shortlist needs amended_from")
perms = {p["role"]: p for p in shl.get("permissions", [])}
if not all((perms.get("HR User") or {}).get(k) for k in ("read", "write", "create", "submit")):
    fail.append("HR User must be able to prepare and submit a shortlist")
if not (perms.get("Interviewer") or {}).get("read") or (perms.get("Interviewer") or {}).get("write"):
    fail.append("the panel (Interviewer) may read the shortlist but not change it")
cand = doctype_json("Interview Shortlist Candidate")
cand_fields = fields_of(cand)
if list(cand_fields) != ["job_applicant", "applicant_name", "match_score", "screening_result", "phone_number",
                         "email_id", "education", "work_experience", "certifications", "screening_section",
                         "experience_years", "flags", "screening_cb", "matched", "missing", "to_check",
                         "remarks_section", "hr_remarks", "hod_remarks", "interview"] or not cand.get("istable"):
    fail.append("Interview Shortlist Candidate's fields are not the shortlist's columns: %s" % list(cand_fields))
if not (cand_fields.get("interview") or {}).get("allow_on_submit"):
    fail.append("Interview Shortlist Candidate.interview is set after submit, so it needs allow_on_submit")
if sum(f.get("columns") or 0 for f in cand["fields"] if f.get("in_list_view")) > 10:
    fail.append("the shortlist grid exceeds 10 columns")
controller = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.py")
for event, function in (("validate", "validate_shortlist"), ("on_update", "shortlist_on_update"), ("on_submit", "mark_shortlisted"),
                        ("on_cancel", "unmark_shortlisted")):
    if not re.search(r"def %s\(self\):\n        interviews\.%s\(self\)" % (event, function), controller) \
            or "def %s(doc):" % function not in glue:
        fail.append("Interview Shortlist %s must call interviews.%s" % (event, function))
for needle, why in (
    ("rules.shortlist_errors(doc.job_opening, doc.candidates, opening_of, submitting=doc.docstatus == 1)",
     "must check the shortlist with the tested rules"),
    ('in ("Open", "Replied", "Hold"):\n            frappe.db.set_value("Job Applicant", row.job_applicant, "status", "Shortlisted")',
     "must mark only applicants still open as Shortlisted"),
    ('"docstatus": 1},\n        )\n        if not elsewhere:', "must keep an applicant Shortlisted while another submitted shortlist lists them"),
    ('filters={"job_title": job_opening, "status": ["in", list(rules.SHORTLISTABLE_STATUSES)]}',
     "must offer only this opening's applicants who can still be shortlisted"),
    ("rules.qualification_lines(qualifications, certification_types, certifications=False)", "must write education out with the tested rules"),
    ("rules.qualification_lines(qualifications, certification_types, certifications=True)", "must write certifications out with the tested rules"),
    ("rules.experience_lines(", "must write work experience out with the tested rules"),
    ('frappe.get_all("Qualification Type", filters={"is_certification": 1}, pluck="name")', "must read which types are certifications"),
    ("slots = rules.plan_slots(first_day, from_time, minutes, len(pending),", "must book with the tested slots"),
    ("gap=settings.gap if gap in (None, \"\") else gap, lunch=settings.lunch,", "with HR Settings' gap and lunch"),
    ("day_end=settings.day_end, is_working_day=lambda day: day not in holidays)", "within the day, on working days"),
    ("if getdate(scheduled_on) < getdate(today()):", "never in the past"),
    ("problems = rules.clashes(slots, panel, _panel_busy(panel, days), _panel_leave(panel, days))",
     "only while the panel is free"),
    ('"status": ["in", ["Open", "Approved"]], "from_date": ["<=", days[-1]],', "leave applied for or approved"),
    ('filters={"scheduled_on": ["in", days or [""]], "docstatus": ["!=", 2], "status": ["!=", "Cancelled"]}',
     "the panel's other interviews those days"),
    ('frappe.enqueue("hrms_addon.hrms_addon.interviews.send_booking_letters", interviews=booked,',
     "must invite the candidates and send the panel its schedule in the background"),
    ("enqueue_after_commit=True", "only once the booking is saved"),
    ("invite=cint(send_invitations), enqueue_after_commit=True)", "inviting only when HR asks"),
    ('"custom_venue": venue if mode == "In Person" else None,', "a venue only for an interview in person"),
    ('"custom_meeting_link": meeting_link if mode == "Video Call" else None,', "a link only for a video call"),
    ('if doc.docstatus != 1:\n        frappe.throw(_("Submit the shortlist before scheduling its interviews."))', "must schedule only a submitted shortlist"),
    ('frappe.has_permission("Interview", "create", throw=True)', "must check the user may create Interviews"),
    ('frappe.get_all("Interviewer", filters={"parent": interview_type, "parenttype": "Interview Type"}, pluck="user")',
     "must take the panel from the Interview Type"),
    ('frappe.db.rollback(save_point="hrms_addon_schedule_interview")', "must undo a refused booking and carry on with the rest"),
    ('row.db_set("interview", interview.name)', "must link each candidate to their Interview"),
):
    if needle not in glue:
        fail.append("interviews.py %s" % why)
for method, decorator in (("get_shortlist_candidates", r"@frappe\.whitelist\(\)"), ("get_candidate_details", r"@frappe\.whitelist\(\)"),
                          ("schedule_interviews", r'@frappe\.whitelist\(methods=\["POST"\]\)')):
    if not re.search(decorator + r"\s*\ndef %s\(" % method, glue):
        fail.append("interviews.%s must be whitelisted (%s)" % (method, decorator.replace("\\", "")))
    body = glue.split("def %s(" % method)[-1].split("\ndef ")[0]
    if method != "schedule_interviews" and 'frappe.has_permission("Interview Shortlist", "write", throw=True)' not in body:
        fail.append("interviews.%s must check the user may write shortlists" % method)

sjs = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.js")
for method in set(re.findall(r'HA_SHORTLIST_METHODS \+ "(\w+)"', sjs)):
    if not re.search(r"@frappe\.whitelist\([^)]*\)\s*\ndef %s\(" % method, glue):
        fail.append("interview_shortlist.js calls interviews.%s, which is not a whitelisted function" % method)
if 'const HA_SHORTLIST_METHODS = "hrms_addon.hrms_addon.interviews.";' not in sjs:
    fail.append("interview_shortlist.js must call the methods in hrms_addon.hrms_addon.interviews")
filled = re.search(r"\[([^\[\]]*)\]\s*\.forEach\(\(field\) => \(row\[field\] = details\[field\] \|\| \"\"\)\)", sjs)
for field_name in re.findall(r'"(\w+)"', filled.group(1) if filled else ""):
    if field_name not in cand_fields:
        fail.append("interview_shortlist.js fills %s, which is not a shortlist column" % field_name)
if not filled:
    fail.append("interview_shortlist.js must fill the rows from the server's details")
for needle, why in (
    ("frm.doc.docstatus === 0 && frm.doc.job_opening", "must offer Get Applicants only on a draft with an opening"),
    ('frm.doc.docstatus === 1 && (frm.doc.candidates || []).length && frappe.model.can_create("Interview")',
     "must offer Schedule Interviews once submitted, a round at a time, to whoever may book"),
    ("filters: { job_title: frm.doc.job_opening", "must pick applicants of this opening only"),
    ("const esc = (text) => frappe.utils.escape_html(text);", "must escape the names and reasons it lists"),
    ('add(__("No longer in the running:"), result.out);', "must say who is no longer in the running"),
    ('add(__("Have not cleared the round before:"), result.not_cleared);', "and who has not cleared the round before"),
    ('add(__("Not scheduled:"), result.refused);', "and why a booking was refused"),
    ("send_invitations: values.send_invitations ? 1 : 0,", "must let HR choose to send the invitations"),
    ("frm.fields_dict.candidates.grid.get_selected_children().map((row) => row.job_applicant)",
     "must book the candidates ticked, a batch"),
    ("applicants: ticked.length ? ticked : null,", "must send the batch, or everyone when none is ticked"),
    ("get_query: () => ({ filters: { designation: frm.doc.designation } }),",
     "must offer only this job's interview types, its rounds"),
    ('add(__("Already have this round:"), result.already);', "must say who already has the round"),
):
    if needle not in sjs:
        fail.append("interview_shortlist.js %s" % why)
fjs = read("hrms_addon", "public", "js", "interview_feedback.js")
for needle, why in (
    ('.xcall("hrms_addon.hrms_addon.interviews.get_interview_questions", { interview: frm.doc.interview })',
     "a new score sheet starts with the interview's questions"),
    ("if (frm.is_new() && frm.doc.interview && !(frm.doc[HA_ANSWER_TABLE] || []).length) {",
     "only a new sheet with none"),
    ('frm.set_df_property(HA_ANSWER_TABLE, "cannot_add_rows", true);', "the questions are the interview's"),
):
    if needle not in fjs:
        fail.append("interview_feedback.js %s" % why)

# the rounds of a job and their questions (Interview Type, one per round per JD)
if rules.to_book(["A", "B", "C"], [], ["B"]) != ["A", "C"] or rules.to_book(["A", "B", "C"], ["C", "B"], []) != ["B", "C"] \
        or rules.to_book(["A", "B"], ["A"], ["A"]) != [] or rules.to_book([], ["A"], []) != []:
    fail.append("to_book: the ticked (or everyone), in the list's order, less those who have the round")
for needle, why in (
    ('    if doc.get("interview_type") and (changed or not doc.get("custom_questions")):\n'
     '        doc.set("custom_questions", type_questions(doc.interview_type))',
     "an interview carries its type's questions, again when the type changes"),
    ('frappe.db.get_value("Interview Type", doc.interview_type, "custom_round")', "and its round"),
    ('filters={"parent": interview_type, "parenttype": "Interview Type",\n                                   "parentfield": "custom_questions"}',
     "the type's own questions"),
    ('    if not doc.get("custom_answers") and doc.get("interview"):\n'
     '        for row in _questions_asked(doc.interview):\n'
     '            doc.append("custom_answers", row)',
     "a score sheet starts with the interview's questions"),
    ('fields=["question", "guidance"], order_by="idx asc")', "each with what to look for"),
    ('    if doc.get("interview_type") and (changed or not doc.get("custom_criteria")):\n'
     '        doc.set("custom_criteria", type_criteria(doc.interview_type))',
     "an interview carries its type's criteria and weights, again when the type changes"),
    ('filters={"parent": name, "parenttype": doctype, "parentfield": "custom_criteria"}', "a round's own list"),
    ("    if not own and interview:\n", "an interview booked before rounds had lists scores its round's"),
    ("errors = rules.round_criteria_errors(doc.get(\"custom_criteria\"), disabled)", "a round's list checked with the tested rules"),
    ("rules.round_criteria_plan(competencies, weights, _sheet_rows(),", "a round's list from its JD with the tested plan"),
    ('filters={"parent": designation, "parenttype": "Designation",\n'
     '                                           "parentfield": "custom_jd_competencies"}', "the JD's competencies"),
    ('frappe.has_permission("Interview Type", "write", throw=True)', "only for whoever may change rounds"),
    ('frappe.has_permission("Interview Criterion", "create", throw=True)', "and add criteria"),
    ('"criteria_group": rules.JD_GROUP}).insert()', "a new competency goes under Job Competencies"),
    ('frappe.has_permission("Interview", "read", interview, throw=True)', "the questions for whoever may read the interview"),
    ('"interview_type": interview_type, "docstatus": ["!=", 2]}', "who already has this round, cancelled ones aside"),
    ("plan = rules.booking_plan(listed, chosen, already, statuses, bool(earlier), cleared)",
     "the batch, less those who have the round, are out of the running or have not cleared the one before"),
    ('"interview_type": ["in", earlier],\n                                                       "docstatus": 1, "status": "Cleared"}',
     "cleared means the round before closed Cleared"),
    ('"already": [names[applicant] for applicant in plan["already"]],', "says who already had it"),
    ('"not_cleared": [names[applicant] for applicant in plan["not_cleared"]],', "and who has not cleared the round before"),
    ("rules.earlier_round([(row.name, row.custom_round) for row in types], this.custom_round)", "the round before, by JD"),
    ('status = rules.status_for_attendance(doc.get("custom_attendance"), doc.get("status"))\n    if status and doc.docstatus == 0:',
     "who came sets the interview's status"),
    ("if row.custom_attendance not in rules.ABSENT and rules.slot_over(row.scheduled_on, row.to_time, now):",
     "an interview over, not a no-show, goes Under Review"),
    ('frappe.db.set_value("Interview", row.name, "status", "Under Review", update_modified=False)',
     "so Frappe HR's reminder chases the missing sheets"),
    ("if not rules.regret_due(values.status, values.custom_regret_sent_on, offered, values.email_id):",
     "a regret once, never to one offered the job"),
    ('frappe.db.set_value("Job Applicant", applicant, "custom_regret_sent_on", now_datetime(), update_modified=False)',
     "records when the regret went"),
    ('if doc.get("status") == "Rejected" and doc.has_value_changed("status"):', "a regret when an applicant is turned down"),
    ('if frappe.db.get_single_value("HR Settings", "custom_send_regret_emails"):', "only where HR Settings says so"),
    ('            if status == "Rejected":\n                queue_regret(row.job_applicant)',
     "the report's rejections get their regrets too"),
    ('frappe.db.set_value("Interview", name, "custom_invited_on", now_datetime(), update_modified=False)',
     "records when the invitation went"),
    ('frappe.has_permission("Interview", "write", interview, throw=True)\n    sent = _invite(interview)',
     "Send Invitation is for whoever may change the interview"),
    ("from frappe.core.doctype.sms_settings.sms_settings import _send_sms", "the SMS through Frappe's gateway"),
    ('and frappe.db.get_single_value("SMS Settings", "sms_gateway_url"):', "only where a gateway is set up"),
    ("frappe.log_error(title=_(\"Interview letter not sent\"))", "a letter that cannot go is logged, the rest still go"),
    ('"doctype": "Email Template", "name": name, "subject": subject, "use_html": 1,', "the letters seeded as Email Templates"),
    ("if not frappe.db.get_single_value(\"HR Settings\", field):", "HR Settings' values set only where empty"),
):
    if needle not in glue:
        fail.append("interviews.py: %s" % why)
if not re.search(r"@frappe\.whitelist\(\)\ndef get_interview_questions\(", glue):
    fail.append("get_interview_questions must be whitelisted")
if '"validate": "hrms_addon.hrms_addon.interviews.interview_validate",' not in read("hrms_addon", "hooks.py"):
    fail.append("hooks.py runs interview_validate on the Interview")
custom_rows = {row["name"]: row for row in json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"),
                                                          encoding="utf-8"))}
for name, fieldtype, options in (("Interview Type-custom_round", "Int", None),
                                 ("Interview Type-custom_questions", "Table", "Interview Question"),
                                 ("Interview-custom_round", "Int", None),
                                 ("Interview-custom_questions", "Table", "Interview Question"),
                                 ("Interview Feedback-custom_answers", "Table", "Interview Answer")):
    row = custom_rows.get(name) or {}
    if (row.get("fieldtype"), row.get("options")) != (fieldtype, options):
        fail.append("%s must be a %s %s" % (name, fieldtype, options or ""))
if not (custom_rows.get("Interview-custom_questions") or {}).get("read_only") \
        or (custom_rows.get("Interview-custom_round") or {}).get("fetch_from") != "interview_type.custom_round":
    fail.append("an interview's round and questions are its type's, not typed in")
setter_rows = {row["name"]: row for row in json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "property_setter.json"),
                                                          encoding="utf-8"))}
if (setter_rows.get("Interview Type-designation-reqd") or {}).get("value") != "1":
    fail.append("every Interview Type belongs to a JD (its Designation is mandatory)")
for child, columns in (("Interview Question", ["question", "guidance"]),
                       ("Interview Answer", ["question", "guidance", "answer", "score"])):
    spec_json = doctype_json(child)
    if not spec_json or not spec_json.get("istable") or [f["fieldname"] for f in spec_json["fields"]] != columns:
        fail.append("%s must be a child table of %s" % (child, columns))
    elif sum(f.get("columns") or 0 for f in spec_json["fields"] if f.get("in_list_view")) > 10:
        fail.append("the %s grid exceeds Frappe's 10 columns" % child)
answer_fields = fields_of(doctype_json("Interview Answer"))
if (answer_fields.get("score") or {}).get("options", "").split("\n") != [o for o in rules.SCORE_OPTIONS if o != rules.NOT_APPLICABLE] \
        or not (answer_fields.get("guidance") or {}).get("read_only"):
    fail.append("each question is scored 1 to 5, beside what to look for, which is the round's")
if not re.search(r'"Interview Type": \{[^}]*"validate": "hrms_addon\.hrms_addon\.interviews\.interview_type_validate"',
                 hook_block("doc_events")):
    fail.append("doc_events must check a round's own list (interviews.interview_type_validate)")
if '"Interview Type": "public/js/interview_type.js"' not in hook_block("doctype_js"):
    fail.append("doctype_js must load interview_type.js for Get Criteria from JD")
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef get_round_criteria\(designation: str\)', glue):
    fail.append("interviews.get_round_criteria adds criteria, so it is whitelisted for POST")
tjs = read("hrms_addon", "public", "js", "interview_type.js")
for needle, why in (('.xcall("hrms_addon.hrms_addon.interviews.get_round_criteria", { designation: frm.doc.designation })',
                     "must fill the round's list from its JD"),
                    ('frappe.confirm(__("Replace the criteria listed?"), fill);', "must ask before replacing a list"),
                    ('frm.clear_table("custom_criteria");', "must replace, not add to, the list")):
    if needle not in tjs:
        fail.append("interview_type.js %s" % why)
criterion_controller = read("hrms_addon", "hrms_addon", "doctype", "interview_criterion", "interview_criterion.py")
if "interview_rules.criterion_errors(self.criterion_name or self.name, self.disabled)" not in criterion_controller:
    fail.append("Interview Criterion must refuse to switch on a criterion that is never scored")
retire = read("hrms_addon", "patches", "v1_0", "retire_health_appearance_criteria.py")
if "hrms_addon.patches.v1_0.retire_health_appearance_criteria" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1] \
        or 'frappe.db.set_value("Interview Criterion", name, "disabled", 1, update_modified=False)' not in retire \
        or "interview_rules.RETIRED_CRITERIA" not in retire:
    fail.append("a post_model_sync patch must switch the retired criteria off where they were seeded")
stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", sjs, flags=re.S)
for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
    if stripped.count(op) != stripped.count(cl):
        fail.append("interview_shortlist.js: unbalanced %s%s" % (op, cl))

spf = json.load(open(os.path.join(APP, "print_format", "interview_shortlist", "interview_shortlist.json"), encoding="utf-8"))
if (spf.get("name"), spf.get("doc_type"), spf.get("standard"), spf.get("print_format_type"), spf.get("disabled")) \
        != ("Interview Shortlist", "Interview Shortlist", "Yes", "Jinja", 0):
    fail.append("the shortlist print format must be a standard Jinja format of Interview Shortlist")
shtml = spf.get("html") or ""
if html_count := [b for b in ("for", "if", "macro") if len(re.findall(r"{%-?\s*" + b + r"\b", shtml)) != len(re.findall(r"{%-?\s*end" + b + r"\b", shtml))]:
    fail.append("shortlist print format: unbalanced %s blocks" % html_count)
for heading in ("SHORTLIST</h3>", "<th class=\"no\">NO.</th>", ">NAME</th>", ">EDUCATION QUALIFICATION</th>", ">WORK EXPERIENCE</th>",
                ">CERTIFICATIONS AND LICENSES</th>"):
    if heading not in shtml:
        fail.append("shortlist print format must carry the sheet's heading %s" % heading)
for attribute in set(re.findall(r"\brow\.([a-z_]+)", shtml)):
    if attribute not in cand_fields:
        fail.append("shortlist print format prints Interview Shortlist Candidate.%s, which does not exist" % attribute)
for fieldname in set(re.findall(r"\bdoc\.([a-z_]+)", shtml)):
    if fieldname not in shl_fields and fieldname not in ("name",):
        fail.append("shortlist print format uses Interview Shortlist.%s, which does not exist" % fieldname)
if re.findall(r"{{-?\s*(?:doc|row)\.[a-z_]+", shtml):
    fail.append("shortlist print format must print text through v() or lines() so it is escaped")

if UPSTREAM_OK:
    applicant_json = json.loads(upstream("hrms", "hr", "doctype", "job_applicant", "job_applicant.json"))
    status = fields_of(applicant_json).get("status") or {}
    if "Shortlisted" not in (status.get("options") or "").split("\n"):
        fail.append("HRMS's Job Applicant has no Shortlisted status any more: recheck mark_shortlisted")
    for fieldname in ("applicant_name", "phone_number", "email_id", "job_title"):
        if fieldname not in fields_of(applicant_json):
            fail.append("HRMS's Job Applicant has no %s: recheck the shortlist's fetches" % fieldname)
    itype = fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview_type", "interview_type.json")))
    if (itype.get("interviewers") or {}).get("options") != "Interviewer" \
            or "user" not in fields_of(json.loads(upstream("hrms", "hr", "doctype", "interviewer", "interviewer.json"))):
        fail.append("HRMS's Interview Type no longer lists its panel as Interviewer rows with a user")
    interview_fields = fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview", "interview.json")))
    if (interview_fields.get("interview_details") or {}).get("options") != "Interview Detail" \
            or "interviewer" not in fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview_detail", "interview_detail.json"))):
        fail.append("HRMS's Interview no longer lists its interviewers as Interview Detail rows")
    for fieldname in ("interview_type", "job_applicant", "scheduled_on", "from_time", "to_time"):
        if fieldname not in interview_fields:
            fail.append("HRMS's Interview has no %s: recheck schedule_interviews" % fieldname)
print("shortlist: columns written out from the Bio-Data, checks, slots, doctypes, controller, buttons and print format resolve")

# ── 8a. Booking a round, and the letters ─────────────────────────────
for name, fieldtype, options, flags in (
        ("Interview-custom_mode", "Select", "In Person\nVideo Call\nPhone Call", ()),
        ("Interview-custom_venue", "Data", None, ()), ("Interview-custom_meeting_link", "Data", "URL", ()),
        ("Interview-custom_attendance", "Select", "\nAttended\nNo-Show\nWithdrew", ()),
        ("Interview-custom_invited_on", "Datetime", None, ("read_only", "no_copy")),
        ("Interview Type-custom_venue", "Data", None, ()), ("Interview Type-custom_what_to_bring", "Small Text", None, ()),
        ("HR Settings-custom_interview_gap", "Int", None, ()), ("HR Settings-custom_interview_day_end", "Time", None, ()),
        ("HR Settings-custom_lunch_from", "Time", None, ()), ("HR Settings-custom_lunch_to", "Time", None, ()),
        ("HR Settings-custom_invitation_template", "Link", "Email Template", ()),
        ("HR Settings-custom_send_invitation_sms", "Check", None, ()),
        ("HR Settings-custom_regret_template", "Link", "Email Template", ()),
        ("HR Settings-custom_send_regret_emails", "Check", None, ()),
        ("Job Applicant-custom_regret_sent_on", "Datetime", None, ("read_only", "no_copy"))):
    f = by_name.get(name) or {}
    if (f.get("fieldtype"), f.get("options")) != (fieldtype, options) or not all(f.get(flag) for flag in flags):
        fail.append("%s must be a %s%s%s" % (name, fieldtype, " of %s" % options if options else "",
                                             ", " + ", ".join(flags) if flags else ""))
if [o for o in (by_name.get("Interview-custom_mode") or {}).get("options", "").split("\n")] != list(rules.MODES) \
        or [o for o in (by_name.get("Interview-custom_attendance") or {}).get("options", "").split("\n") if o] != list(rules.ATTENDANCE):
    fail.append("the Interview's Mode and Attendance offer exactly the rules' modes and attendance")
if (by_name.get("HR Settings-custom_send_regret_emails") or {}).get("default") \
        or (by_name.get("HR Settings-custom_send_invitation_sms") or {}).get("default"):
    fail.append("regret emails and SMS invitations go out once HR switches them on, never by default")
if '"on_update": "hrms_addon.hrms_addon.interviews.regret_on_update"' not in re.search(
        r'"Job Applicant": \{(.*?)\n    \},', hook_block("doc_events"), re.S).group(1):
    fail.append("doc_events must send the regret when a Job Applicant is turned down (interviews.regret_on_update)")
if '"hrms_addon.hrms_addon.interviews.mark_interviews_held"' not in hooks.split('"hourly": [')[-1].split("]")[0]:
    fail.append("the hourly scheduler must mark interviews held (interviews.mark_interviews_held)")
letters_patch = read("hrms_addon", "patches", "v1_0", "seed_interview_letters.py")
if "hrms_addon.patches.v1_0.seed_interview_letters" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1] \
        or letters_patch.find('sync_fixtures("hrms_addon")') < 0 \
        or letters_patch.find('sync_fixtures("hrms_addon")') > letters_patch.find("seed_interview_letters()"):
    fail.append("the letters patch syncs the fixtures (HR Settings' new fields) before it seeds")
if "def after_install():\n    seed_interview_criteria()\n    seed_interview_letters()" not in glue:
    fail.append("after_install must seed the letters too")
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef send_invitation\(interview: str\)', glue):
    fail.append("interviews.send_invitation must be whitelisted for POST")
context_body = glue.split("def _invitation_context(")[-1].split("\ndef ")[0]
if set(re.findall(r'^\s+"(\w+)": ', context_body.split("return {")[-1], re.M)) != set(rules.INVITATION_KEYS):
    fail.append("the invitation's context must give exactly the keys a template may name (INVITATION_KEYS)")
regret_body = glue.split("def send_regret(")[-1].split("\ndef ")[0]
if set(re.findall(r'"(\w+)": ', regret_body.split("_render(template, {")[-1].split("})")[0])) != set(rules.REGRET_KEYS):
    fail.append("the regret's context must give exactly the keys a template may name (REGRET_KEYS)")
ijs_now = read("hrms_addon", "public", "js", "interview.js")
for needle, why in (('frappe.xcall(HA_INTERVIEW_METHODS + "send_invitation", { interview: frm.doc.name })',
                     "must send the invitation through interviews.send_invitation"),
                    ("!frappe.user.has_role(HA_HR_ROLES)", "must offer Send Invitation to HR alone"),
                    ('frm.doc.custom_invited_on ? __("Invite Again") : __("Send Invitation")', "must say when it was sent")):
    if needle not in ijs_now:
        fail.append("interview.js %s" % why)
if UPSTREAM_OK:
    if '"status": "Under Review",' not in upstream("hrms", "hr", "doctype", "interview", "interview.py"):
        fail.append("Frappe HR's feedback reminder no longer looks for Under Review: recheck mark_interviews_held")
    if "def _send_sms(" not in upstream("frappe", "core", "doctype", "sms_settings", "sms_settings.py"):
        fail.append("Frappe no longer has _send_sms: recheck the SMS invitation")
    template_fields = {f["fieldname"] for f in json.loads(upstream("frappe", "email", "doctype", "email_template",
                                                                   "email_template.json"))["fields"]}
    if not {"subject", "response", "response_html", "use_html"} <= template_fields:
        fail.append("Frappe's Email Template changed its fields: recheck _render and seed_interview_letters")
    hr_settings = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "hr_settings", "hr_settings.json"))["fields"]}
    if "hiring_sender_email" not in hr_settings:
        fail.append("Frappe HR's HR Settings has no hiring_sender_email: recheck the letters' sender and field placing")
    if "def has_value_changed(self, fieldname" not in upstream("frappe", "model", "base_document.py") \
            and "def has_value_changed(self, fieldname" not in upstream("frappe", "model", "document.py"):
        fail.append("Frappe's Document has no has_value_changed: recheck regret_on_update")
    leave_status = next(f for f in json.loads(upstream("hrms", "hr", "doctype", "leave_application", "leave_application.json"))
                        ["fields"] if f["fieldname"] == "status")
    if not {"Open", "Approved"} <= set(leave_status["options"].split("\n")):
        fail.append("Frappe HR's Leave Application has no Open or Approved status: recheck the panel's leave")
print("booking: slots with gaps, lunch and the day's end over working days, rounds gated, the panel free; invitations, "
      "the panel's schedule, regrets and the hourly Under Review")

# ── 8b. The shortlist's screening: HR, then the HOD (steps 10 and 11) ─
spec = importlib.util.spec_from_file_location("interview_shortlist_approval", os.path.join(APP, "interview_shortlist_approval.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)  # no Frappe import either
spec = importlib.util.spec_from_file_location("requisition_approval", os.path.join(APP, "requisition_approval.py"))
requisition_rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requisition_rules)

if (S.DOCTYPE, S.STATE_FIELD) != ("Interview Shortlist", "workflow_state") or S.STATES[0]["state"] != S.DRAFT:
    fail.append("the screening runs on Interview Shortlist's workflow_state and starts in Draft (Frappe's default state)")
doc_status_of = {row["state"]: row.get("doc_status", "0") for row in S.STATES}
if doc_status_of != {S.DRAFT: "0", S.PENDING_HOD: "0", S.RETURNED: "0", S.SCREENED: "1", S.CANCELLED: "2"} \
        or len({(row["state"], row.get("doc_status", "0")) for row in S.STATES}) != len(doc_status_of):
    fail.append("the HOD's approval submits the shortlist (Screened), Cancel cancels it, the rest are drafts: %s" % doc_status_of)
for t in S.TRANSITIONS:
    if t["state"] not in doc_status_of or t["next_state"] not in doc_status_of or t["action"] not in S.ACTIONS:
        fail.append("screening transition %s --%s--> %s is not in the workflow's states and actions" % (t["state"], t["action"], t["next_state"]))
        continue
    moves = (doc_status_of[t["state"]], doc_status_of[t["next_state"]])
    if moves[0] == "2" or moves == ("1", "0") or moves == ("0", "2"):
        fail.append("Frappe's Workflow refuses %s --%s--> %s (doc_status %s to %s)" % (t["state"], t["action"], t["next_state"], *moves))
if any(row["send_email"] for row in S.STATES):
    fail.append("the screening must send no workflow email, which reaches everyone with the role: the assignment tells the one HOD")
for state, roles in ((S.DRAFT, set(S.PREPARERS)), (S.RETURNED, set(S.PREPARERS)), (S.PENDING_HOD, {S.SCREENER})):
    if {row["allow_edit"] for row in S.STATES if row["state"] == state} != roles:
        fail.append("%s must be editable by %s alone" % (state, sorted(roles)))
if S.PREPARERS != ("HR User", "HR Manager"):
    fail.append("HR screens first: HR User (the HR Officer) and HR Manager")
if S.SCREENER != "Head of Department" or S.SCREENER not in requisition_rules.NEW_ROLES or S.SCREENER not in S.NEW_ROLES:
    fail.append("the second screening is by the requisition's Head of Department role, which the workflow ensures")
if set(S.PERMISSIONS.get("Interview Shortlist", {}).get(S.SCREENER, ())) != {"read", "write", "submit"}:
    fail.append("the HOD needs read, write and submit on Interview Shortlist: they edit it, and their approval submits it")
if not (perms.get(S.CANCELLER) or {}).get("cancel"):
    fail.append("the %s cancels screened shortlists, so needs cancel on Interview Shortlist" % S.CANCELLER)


def swalk(state, roles):
    return dict(S.next_states(state, roles))


for role in S.PREPARERS:
    if swalk(S.DRAFT, [role]) != {S.SHARE: S.PENDING_HOD}:
        fail.append("%s shares a draft shortlist with the HOD, and only that" % role)
    if swalk(S.RETURNED, [role]) != {S.REVISE: S.DRAFT}:
        fail.append("%s revises a shortlist the HOD returned" % role)
    if swalk(S.PENDING_HOD, [role]):
        fail.append("only the HOD acts on a shortlist shared with them, not %s" % role)
if swalk(S.DRAFT, [S.SCREENER]) or swalk(S.RETURNED, [S.SCREENER]):
    fail.append("the HOD cannot share or revise HR's draft")
if swalk(S.PENDING_HOD, [S.SCREENER]) != {S.APPROVE: S.SCREENED, S.RETURN: S.RETURNED}:
    fail.append("the HOD approves the shortlist or returns it to HR")
if swalk(S.SCREENED, ["HR Manager"]) != {S.CANCEL: S.CANCELLED} or swalk(S.SCREENED, ["HR User", S.SCREENER, "Interviewer"]):
    fail.append("only the HR Manager cancels a screened shortlist, through the workflow")
if swalk(S.CANCELLED, ["HR Manager", "HR User", S.SCREENER, "System Manager"]):
    fail.append("a cancelled shortlist is final (amend it for a new one)")

scs = S.compute_stamps
sblank = dict.fromkeys(S.STAMP_FIELDS)
if scs(None, S.DRAFT, "hr@lpl", "2026-09-19", {"hod_screened_by": "forged@lpl"}) != sblank:
    fail.append("a new shortlist starts with no screening sign-offs, whatever was posted")
shared = scs(S.DRAFT, S.PENDING_HOD, "hr@lpl", "2026-09-19", {})
if shared != dict(sblank, hr_screened_by="hr@lpl", hr_screened_on="2026-09-19"):
    fail.append("sharing records HR's screener and the date: %s" % shared)
screened = scs(S.PENDING_HOD, S.SCREENED, "hod@lpl", "2026-09-20", shared)
if screened != dict(shared, hod_screened_by="hod@lpl", hod_screened_on="2026-09-20"):
    fail.append("the HOD's approval records the HOD and the date, keeping HR's: %s" % screened)
if scs(S.PENDING_HOD, S.RETURNED, "hod@lpl", "2026-09-20", shared) != shared:
    fail.append("returning the shortlist records no approval")
if scs(S.RETURNED, S.DRAFT, "hr@lpl", "2026-09-21", shared) != sblank:
    fail.append("a revised shortlist is screened again from the start")
if scs(S.PENDING_HOD, S.PENDING_HOD, "hod@lpl", "2026-09-21", shared) != shared:
    fail.append("a save that moves nothing keeps the stored screening sign-offs (a typed date reverts)")

ser = S.screening_errors
expect("sharing with the HOD named", ser(S.DRAFT, S.PENDING_HOD, "hod@lpl", ""))
expect("sharing with no HOD named", ser(S.DRAFT, S.PENDING_HOD, None, ""), "Name the Head of Department")
expect("returning with a reason", ser(S.PENDING_HOD, S.RETURNED, "hod@lpl", "Add the two applicants with a diploma."))
expect("returning with no reason", ser(S.PENDING_HOD, S.RETURNED, "hod@lpl", "  "), "HOD's Comments")
expect("a draft saved before the HOD is known", ser(S.DRAFT, S.DRAFT, None, None))
expect("a new shortlist", ser(None, S.DRAFT, None, None))
expect("the HOD's approval", ser(S.PENDING_HOD, S.SCREENED, "hod@lpl", None))

sa = S.assignee
if sa(S.DRAFT, S.PENDING_HOD, "hod@lpl", "hr@lpl") != "hod@lpl" or sa(S.PENDING_HOD, S.RETURNED, "hod@lpl", "hr@lpl") != "hr@lpl":
    fail.append("sharing assigns the shortlist to the HOD, and a return assigns it back to whoever prepared it")
for moves in ((S.PENDING_HOD, S.SCREENED), (S.RETURNED, S.DRAFT), (S.PENDING_HOD, S.PENDING_HOD), (None, S.DRAFT)):
    if sa(*moves, "hod@lpl", "hr@lpl") is not None:
        fail.append("nobody new is assigned on %s -> %s" % moves)

swf = shl_fields.get(S.STATE_FIELD) or {}
if (swf.get("fieldtype"), swf.get("options"), swf.get("hidden"), swf.get("allow_on_submit")) != ("Link", "Workflow State", 1, 1):
    fail.append("Interview Shortlist needs its own hidden workflow_state Link, settable after submit")
sstatus = shl_fields.get("status") or {}
if set(o for o in sstatus.get("options", "").split("\n") if o) != {row["status"] for row in S.STATES} \
        or not sstatus.get("read_only") or not sstatus.get("allow_on_submit"):
    fail.append("Interview Shortlist.status must be read-only, settable after submit, with exactly the workflow's statuses")
for fieldname in S.STAMP_FIELDS:
    f = shl_fields.get(fieldname) or {}
    if not (f.get("read_only") and f.get("allow_on_submit") and f.get("no_copy")):
        fail.append("Interview Shortlist.%s is filled by the screening: read-only, settable after submit, not copied" % fieldname)
hod_field = shl_fields.get("head_of_department") or {}
if hod_field.get("options") != "User" or hod_field.get("read_only"):
    fail.append("the shortlist names its HOD as a User that HR can change")
if (by_name.get("Job Requisition-custom_hod") or {}).get("options") != "User":
    fail.append("the shortlist's HOD defaults from Job Requisition.custom_hod, which must be a User")
if "hod_comments" not in shl_fields or not {"hr_remarks", "hod_remarks"} <= set(cand_fields):
    fail.append("each screener needs remarks per candidate, and the HOD a place to say why it is returned")
for needle, why in (
    ('frappe.db.get_value("Job Requisition", requisition, "custom_hod")', "must default the HOD to the one who signed the requisition"),
    ('screening.screening_errors(old_state, new_state, doc.get("head_of_department"), doc.get("hod_comments"))',
     "must check each screening step with the tested rules"),
    ("screening.compute_stamps(old_state, new_state, frappe.session.user, today(), current)", "must fill the screening sign-offs with the tested rules"),
    ("close_all_assignments(doc.doctype, doc.name, ignore_permissions=True)", "must close the last screener's assignment when it moves on"),
    ('screening.assignee(old_state, new_state, doc.get("head_of_department"), doc.owner)', "must assign the shortlist with the tested rules"),
    ('workflows.setup_on_migrate(screening, "Interview Shortlist screening")', "must build the screening workflow from interview_shortlist_approval"),
):
    if needle not in glue:
        fail.append("interviews.py %s" % why)
on_update_body = glue.split("def shortlist_on_update(")[-1].split("\ndef ")[0]
unmoved = on_update_body.find("if old_state == new_state:\n        return\n")
if unmoved == -1 or unmoved > on_update_body.find("close_all_assignments(doc.doctype"):
    fail.append("interviews.shortlist_on_update must leave assignments alone on a save that moves nothing")
if '"hrms_addon.hrms_addon.interviews.setup_shortlist_workflow_on_migrate"' not in hook_block("after_migrate"):
    fail.append("after_migrate must build the Interview Shortlist screening workflow")
status_patch = read("hrms_addon", "patches", "v1_0", "shortlist_status_from_docstatus.py")
if "hrms_addon.patches.v1_0.shortlist_status_from_docstatus" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[-1] \
        or "for docstatus, status in ((1, screening.SCREENED), (2, screening.CANCELLED)):" not in status_patch:
    fail.append("shortlists submitted or cancelled before the screening need the matching Status: post_model_sync patch "
                "shortlist_status_from_docstatus")
hr_states = re.search(r"const HA_HR_STATES = \[([^\[\]]*)\];", sjs)
if not hr_states or re.findall(r'"([^"]+)"', hr_states.group(1)) != [S.DRAFT, S.RETURNED] \
        or 'const HA_HOD_STATE = "%s";' % S.PENDING_HOD not in sjs:
    fail.append("interview_shortlist.js must know HR's states %s and the HOD's %s" % ([S.DRAFT, S.RETURNED], S.PENDING_HOD))
for needle, why in (
    ("const with_hr = !frm.doc.workflow_state || HA_HR_STATES.includes(frm.doc.workflow_state);", "must treat a new shortlist as HR's"),
    ("frm.doc.docstatus === 0 && frm.doc.job_opening && with_hr", "must offer Get Applicants only to HR"),
    ('frm.toggle_enable("hod_comments", with_hod);', "must open the HOD's comments only to the HOD"),
    ('grid.toggle_enable("hr_remarks", with_hr);', "must open HR's remarks only to HR"),
    ('grid.toggle_enable("hod_remarks", with_hod);', "must open the HOD's remarks only to the HOD"),
    ('frappe.model.can_create("Interview")', "must offer Schedule Interviews only to someone who can create Interviews"),
):
    if needle not in sjs:
        fail.append("interview_shortlist.js %s" % why)
for who, when in (("hr_screened_by", "hr_screened_on"), ("hod_screened_by", "hod_screened_on")):
    if 'frappe.db.get_value("User", doc.%s, "full_name")' % who not in shtml or "frappe.utils.format_date(doc.%s)" % when not in shtml:
        fail.append("the shortlist print format must carry the screening sign-off %s and its date" % who)

if UPSTREAM_OK:
    assign_py = upstream("frappe", "desk", "form", "assign_to.py")
    if "def _add(args=None, *, ignore_permissions=False):" not in assign_py \
            or "def close_all_assignments(doctype, name, ignore_permissions=False):" not in assign_py:
        fail.append("Frappe's assign_to changed: recheck shortlist_on_update")
    workflow_model = upstream("frappe", "model", "workflow.py")
    if "elif doc.docstatus.is_submitted() and new_docstatus.is_cancelled():\n\t\tdoc.cancel()" not in workflow_model:
        fail.append("Frappe's apply_workflow no longer cancels on a doc_status 2 state: recheck the shortlist's Cancel step")
    document_py = upstream("frappe", "model", "document.py")
    if 'if self._action != "cancel":\n\t\t\tself._validate()' not in document_py:
        fail.append("Frappe now validates on a plain cancel: recheck whether the shortlist still needs its Cancel step")
    if 'elif self._action == "submit":\n\t\t\tself.run_method("on_update")\n\t\t\tself.run_method("on_submit")' not in document_py:
        fail.append("Frappe no longer runs on_update on submit: the HOD's approval would leave their assignment open")
    opening = fields_of(json.loads(upstream("hrms", "hr", "doctype", "job_opening", "job_opening.json")))
    if (opening.get("job_requisition") or {}).get("options") != "Job Requisition":
        fail.append("HRMS's Job Opening no longer links its Job Requisition: recheck the shortlist's default HOD")
print("screening: HR shares, the HOD approves or returns with a reason, HR revises, the HR Manager cancels; sign-offs, assignment and remarks resolve")

# ── 9. The interview report and its approval ─────────────────────────
spec = importlib.util.spec_from_file_location("interview_report_approval", os.path.join(APP, "interview_report_approval.py"))
approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approval)  # no Frappe import either
spec = importlib.util.spec_from_file_location("requisition_approval", os.path.join(APP, "requisition_approval.py"))
requisition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requisition)

A = approval
states = {row["state"] for row in A.STATES}
for t in A.TRANSITIONS:
    if t["state"] not in states or t["next_state"] not in states:
        fail.append("transition %s --%s--> %s uses a state the workflow does not have" % (t["state"], t["action"], t["next_state"]))
    if t["action"] not in A.ACTIONS:
        fail.append("transition action %s is not in ACTIONS" % t["action"])
if tuple(A.ACTIONS) != tuple(requisition.ACTIONS) + (A.CANCEL,) or A.CANCEL != S.CANCEL:
    fail.append("the report's actions must be the requisition's %s and the shortlist's Cancel, so the workflows share them"
                % (requisition.ACTIONS,))
report_status_of = {row["state"]: row.get("doc_status", "0") for row in A.STATES}
for row in A.STATES:
    submits = row.get("doc_status", "0") == "1"
    if submits != (row["state"] == A.APPROVED):
        fail.append("only Approved may submit the report (doc_status 1), not %s" % row["state"])
    if (row.get("doc_status") == "2") != (row["state"] == A.CANCELLED):
        fail.append("only Cancelled cancels the report (doc_status 2), not %s" % row["state"])
    emails = row["state"] in (A.PENDING_HRM, A.PENDING_ED)
    if bool(row["send_email"]) != emails:
        fail.append("%s must %ssend email: only a step waiting on an approver emails them" % (row["state"], "" if emails else "not "))
for t in A.TRANSITIONS:
    moves = (report_status_of.get(t["state"]), report_status_of.get(t["next_state"]))
    if moves[0] == "2" or moves == ("1", "0") or moves == ("0", "2"):
        fail.append("Frappe's Workflow refuses %s --%s--> %s (doc_status %s to %s)" % (t["state"], t["action"], t["next_state"], *moves))
for state in (A.DRAFT, A.REJECTED):
    if {row["allow_edit"] for row in A.STATES if row["state"] == state} != set(A.PREPARERS):
        fail.append("%s must be editable by every preparer %s (the 'not editable due to a Workflow' lock-out)" % (state, A.PREPARERS))
if A.PREPARERS != ("HR User", "HR Manager"):
    fail.append("the report is prepared by HR: HR User and HR Manager")


def walk(state, roles):
    return dict(A.next_states(state, roles))


if walk(A.DRAFT, ["HR User"]) != {A.SUBMIT: A.PENDING_HRM} or walk(A.DRAFT, ["HR Manager"]) != {A.SUBMIT: A.PENDING_HRM}:
    fail.append("HR must be able to send a draft to the HR Manager, and only that")
if walk(A.PENDING_HRM, ["HR User"]) or walk(A.PENDING_HRM, ["Executive Director"]):
    fail.append("only the HR Manager may act on a report pending the HR Manager")
if walk(A.PENDING_HRM, ["HR Manager"]) != {A.APPROVE: A.PENDING_ED, A.REJECT: A.REJECTED}:
    fail.append("the HR Manager forwards the report to the Executive Director or rejects it")
if walk(A.PENDING_ED, ["HR Manager"]) or walk(A.PENDING_ED, ["HR User"]):
    fail.append("only the Executive Director may act on a report forwarded to them")
if walk(A.PENDING_ED, ["Executive Director"]) != {A.APPROVE: A.APPROVED, A.REJECT: A.REJECTED}:
    fail.append("the Executive Director approves or rejects the report")
if walk(A.APPROVED, ["HR User", "Executive Director", "System Manager"]) or walk(A.APPROVED, ["HR Manager"]) != {A.CANCEL: A.CANCELLED}:
    fail.append("an approved report is final: only the HR Manager may cancel it, through the workflow")
if walk(A.CANCELLED, ["HR Manager", "HR User", "Executive Director", "System Manager"]):
    fail.append("a cancelled report is final (amend it for a new one)")
if walk(A.REJECTED, ["HR User"]) != {A.REVISE: A.DRAFT} or walk(A.REJECTED, ["HR Manager"]) != {A.REVISE: A.DRAFT}:
    fail.append("a rejected report goes back to HR to revise")

cs = A.compute_stamps
blank = dict.fromkeys(A.STAMP_FIELDS)
if cs(None, A.DRAFT, "hr@lpl", "2026-07-16", {"hrm_approver": "forged@lpl"}) != blank:
    fail.append("a new report starts with no sign-offs, whatever was posted")
fwd = cs(A.PENDING_HRM, A.PENDING_ED, "hrm@lpl", "2026-07-17", {})
if fwd != dict(blank, hrm_approver="hrm@lpl", hrm_approved_on="2026-07-17"):
    fail.append("forwarding to the Executive Director records the HR Manager and the date: %s" % fwd)
done = cs(A.PENDING_ED, A.APPROVED, "ed@lpl", "2026-07-18", fwd)
if done != dict(fwd, ed_approver="ed@lpl", ed_approved_on="2026-07-18"):
    fail.append("approving records the Executive Director and the date, keeping the HR Manager's: %s" % done)
if cs(A.PENDING_ED, A.REJECTED, "ed@lpl", "2026-07-18", fwd) != fwd:
    fail.append("a rejection records no approval")
if cs(A.REJECTED, A.DRAFT, "hr@lpl", "2026-07-19", done) != blank:
    fail.append("a revised report must be approved again from the start")
if cs(A.PENDING_ED, A.PENDING_ED, "hr@lpl", "2026-07-19", fwd) != fwd:
    fail.append("a save that moves nothing keeps the stored sign-offs (a typed date reverts)")
if A.leaves_draft(A.DRAFT) or A.leaves_draft(None) or not A.leaves_draft(A.PENDING_HRM) or not A.leaves_draft(A.APPROVED):
    fail.append("the report must be complete once it leaves Draft, and only then")
if "Executive Director" not in A.NEW_ROLES or set(A.PERMISSIONS.get("Interview Report", {}).get("Executive Director", ())) \
        != {"read", "write", "submit"}:
    fail.append("the Executive Director needs read, write and submit on Interview Report to approve it")

ps = rules.panel_summary
s = ps([{"percent": 81.25, "maximum": 80, "recommendation": "Offer"}, {"percent": 90, "maximum": 85, "recommendation": "Offer"},
        {"percent": 70, "maximum": 85, "recommendation": "Shortlist"}, {"percent": 0, "maximum": 0, "recommendation": ""}])
if (s["count"], s["average"], s["band"], s["tally"], s["decision"]) != (4, 80.42, "Very Good", "Offer 2, Shortlist 1", "Offer"):
    fail.append("panel summary: the scored sheets averaged, recommendations counted, the majority's decision: %s" % s)
s = ps([{"percent": 60, "maximum": 5, "recommendation": "Offer"}, {"percent": 40, "maximum": 5, "recommendation": "Reject"}])
if s["decision"] != "" or s["tally"] != "Offer 1, Reject 1":
    fail.append("a split panel leaves the decision to HR: %s" % s)
if ps([])["average"] is not None or ps([])["band"] != "":
    fail.append("a candidate with no sheets has no score")
for percent, band in ((90, "Excellent"), (89.99, "Very Good"), (70, "Very Good"), (69.99, "Good"), (50, "Good"),
                      (49.99, "Average"), (30, "Average"), (29.99, "Below Average"), (None, "")):
    if rules.band_for_percent(percent) != band:
        fail.append("%s%% must be %r, got %r" % (percent, band, rules.band_for_percent(percent)))
for args, text in ((("UGX", 2600000, 2700000), "Expects UGX 2,600,000 to 2,700,000 a month."),
                   (("UGX", 1000000, 0), "Expects UGX 1,000,000 a month."), (("UGX", 900000, 900000), "Expects UGX 900,000 a month."),
                   ((None, 0, None), "")):
    if rules.salary_remark(*args) != text:
        fail.append("salary_remark%s must be %r, got %r" % (args, text, rules.salary_remark(*args)))
re_ = rules.report_errors
expect("a draft report with gaps", re_([{"job_applicant": "A"}], "", complete=False))
expect("a complete report", re_([{"job_applicant": "A", "decision": "Offer"}], "The panel recommends A.", complete=True))
expect("sent on without decisions", re_([{"job_applicant": "A", "applicant_name": "Rinah Eupal"}], "x", complete=True),
       "Row 1 (Rinah Eupal): choose the panel's decision.")
expect("sent on without recommendations", re_([{"job_applicant": "A", "decision": "Offer"}], " ", complete=True),
       "Write the panel's recommendations")
expect("sent on empty", re_([], "x", complete=True), "List the candidates interviewed")
expect("a candidate twice", re_([{"job_applicant": "A"}, {"job_applicant": "A"}], "", complete=False), "Row 2: A is already listed in row 1.")
expect("a decision off the form", re_([{"job_applicant": "A", "decision": "Hire"}], "", complete=False), "must be Offer, Shortlist or Reject")

rep = doctype_json("Interview Report")
rep_fields = fields_of(rep)
if not rep.get("is_submittable") or rep.get("autoname") != "HR-INR-.YYYY.-.####" or rep.get("default_print_format") != "Interview Report":
    fail.append("Interview Report must be submittable, named HR-INR-YYYY-####, and print the report by default")
wf = rep_fields.get(A.STATE_FIELD) or {}
if (wf.get("fieldtype"), wf.get("options"), wf.get("hidden"), wf.get("allow_on_submit")) != ("Link", "Workflow State", 1, 1):
    fail.append("Interview Report needs its own hidden workflow_state Link, settable after submit")
status_options = [o for o in (rep_fields.get("status") or {}).get("options", "").split("\n") if o]
if set(status_options) != {row["status"] for row in A.STATES} or not (rep_fields.get("status") or {}).get("allow_on_submit"):
    fail.append("Interview Report.status must offer exactly the workflow's statuses %s" % sorted({row["status"] for row in A.STATES}))
for field in A.STAMP_FIELDS:
    f = rep_fields.get(field) or {}
    if not f.get("read_only") or not f.get("allow_on_submit"):
        fail.append("Interview Report.%s is filled by the approval, so it must be read-only and settable on submit" % field)
for fieldname in ("job_opening", "interview_date"):
    if not (rep_fields.get(fieldname) or {}).get("reqd"):
        fail.append("Interview Report.%s must be mandatory" % fieldname)
for fieldname, target in (("panel", "Interview Report Panel Member"), ("candidates", "Interview Report Candidate"),
                          ("amended_from", "Interview Report"), ("head_of_department", "User")):
    if (rep_fields.get(fieldname) or {}).get("options") != target:
        fail.append("Interview Report.%s must point at %s" % (fieldname, target))
rep_perms = {p["role"]: p for p in rep.get("permissions", [])}
for role in A.PREPARERS:
    if not all((rep_perms.get(role) or {}).get(k) for k in ("read", "write", "create")):
        fail.append("%s prepares reports, so needs read, write and create on Interview Report" % role)
if not (rep_perms.get(A.CANCELLER) or {}).get("cancel"):
    fail.append("the %s cancels approved reports, so needs cancel on Interview Report" % A.CANCELLER)
rc = doctype_json("Interview Report Candidate")
rc_fields = fields_of(rc)
if [o for o in (rc_fields.get("decision") or {}).get("options", "").split("\n") if o] != list(rules.RECOMMENDATIONS):
    fail.append("the candidate's decision must be the form's Offer / Shortlist / Reject")
if sum(f.get("columns") or 0 for f in rc["fields"] if f.get("in_list_view")) > 10:
    fail.append("the report's candidate grid exceeds 10 columns")
rp_fields = fields_of(doctype_json("Interview Report Panel Member"))
if (rp_fields.get("interviewer") or {}).get("options") != "User" or (rp_fields.get("interviewer_name") or {}).get("fetch_from") != "interviewer.full_name":
    fail.append("a panel member is a User, their name fetched from it")
if not re.search(r"def validate\(self\):\n        interviews\.validate_report\(self\)",
                 read("hrms_addon", "hrms_addon", "doctype", "interview_report", "interview_report.py")):
    fail.append("Interview Report validate must call interviews.validate_report")

report_body = glue.split("def get_interview_results(")[-1].split("\ndef ")[0]
returned = set(re.findall(r'^\s+"(\w+)": ', report_body, re.M))
panel_keys = {"interviewer", "interviewer_name", "designation"}
if not panel_keys <= set(rp_fields) or not (returned - panel_keys) <= set(rc_fields):
    fail.append("get_interview_results returns fields the report's tables do not have: %s"
                % sorted((returned - panel_keys) - set(rc_fields)))
for needle, why in (
    ("approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current)", "must fill the sign-offs with the tested rules"),
    ("rules.report_errors(doc.candidates, doc.recommendations, complete=approval.leaves_draft(new_state))",
     "must check the report with the tested rules, strictly once it leaves Draft"),
    ('frappe.has_permission("Interview Report", "write", throw=True)', "must check the user may write reports"),
    ('filters={"job_opening": job_opening, "scheduled_on": interview_date, "docstatus": ["!=", 2]}',
     "must take the opening's interviews on that day, leaving cancelled ones out"),
    ("summary = rules.panel_summary(sheets)", "must sum up the panel with the tested rules"),
    ('filters={"interview": interview.name, "docstatus": 1}', "must count only submitted score sheets"),
    ("rules.salary_remark(", "must write the salary expectation with the tested rules"),
    ('workflows.setup_on_migrate(approval, "Interview Report approval")', "must build the approval workflow from interview_report_approval"),
):
    if needle not in glue:
        fail.append("interviews.py %s" % why)
if not re.search(r"@frappe\.whitelist\(\)\s*\ndef get_interview_results\(", glue):
    fail.append("interviews.get_interview_results must be whitelisted")
for fieldname in re.findall(r'"custom_(\w+) as', report_body):
    if "Interview Feedback-custom_%s" % fieldname not in by_name:
        fail.append("get_interview_results reads Interview Feedback.custom_%s, which does not exist" % fieldname)
if '"hrms_addon.hrms_addon.interviews.setup_report_workflow_on_migrate"' not in hook_block("after_migrate"):
    fail.append("after_migrate must build the Interview Report approval workflow")
builder = read("hrms_addon", "hrms_addon", "workflows.py")
if '"doc_status": row.get("doc_status", "0")' not in builder:
    fail.append("workflows.py must take each state's doc_status from the rules, or the report is never submitted")

rjs = read("hrms_addon", "hrms_addon", "doctype", "interview_report", "interview_report.js")
if '.xcall("hrms_addon.hrms_addon.interviews.get_interview_results"' not in rjs:
    fail.append("interview_report.js must fill the report with interviews.get_interview_results")
if '.xcall("hrms_addon.hrms_addon.job_requisition.get_session_employee")' not in rjs \
        or not re.search(r"@frappe\.whitelist\(\)\s*\ndef get_session_employee\(", read("hrms_addon", "hrms_addon", "job_requisition.py")):
    fail.append("interview_report.js must default Prepared By through the whitelisted get_session_employee")
if "frappe.confirm(" not in rjs:
    fail.append("interview_report.js must ask before replacing remarks already typed")
stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", rjs, flags=re.S)
for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
    if stripped.count(op) != stripped.count(cl):
        fail.append("interview_report.js: unbalanced %s%s" % (op, cl))

rpf = json.load(open(os.path.join(APP, "print_format", "interview_report", "interview_report.json"), encoding="utf-8"))
if (rpf.get("name"), rpf.get("doc_type"), rpf.get("standard"), rpf.get("print_format_type"), rpf.get("disabled")) \
        != ("Interview Report", "Interview Report", "Yes", "Jinja", 0):
    fail.append("the report print format must be a standard Jinja format of Interview Report")
rhtml = rpf.get("html") or ""
for block in ("for", "if", "macro"):
    if len(re.findall(r"{%-?\s*" + block + r"\b", rhtml)) != len(re.findall(r"{%-?\s*end" + block + r"\b", rhtml)):
        fail.append("report print format: unbalanced %s blocks" % block)
for text in ("INTERVIEW REPORT FOR", "<b>Position:</b>", "<b>Forwarded to:</b>", "<b>Thru:</b>", "<b>Prepared by:</b>",
             "by a panel consisting of", ">No.</th>", ">Name</th>", ">Qualification</th>", ">Experience</th>", ">Remarks</th>",
             "<b>Recommendations</b>", '"Human Resource Manager"', '"Executive Director"'):
    if text not in rhtml:
        fail.append("report print format must carry the report's %s" % text)
for fieldname in set(re.findall(r"\bdoc\.([a-z_]+)", rhtml)):
    if fieldname not in rep_fields:
        fail.append("report print format uses Interview Report.%s, which does not exist" % fieldname)
for attribute in set(re.findall(r"\brow\.([a-z_]+)", rhtml)):
    if attribute not in rc_fields:
        fail.append("report print format prints Interview Report Candidate.%s, which does not exist" % attribute)
for attribute in set(re.findall(r"\bmember\.([a-z_]+)", rhtml)):
    if attribute not in rp_fields:
        fail.append("report print format prints Interview Report Panel Member.%s, which does not exist" % attribute)
if re.findall(r"{{-?\s*(?:doc|row|member)\.[a-z_]+", rhtml):
    fail.append("report print format must print text through v() or lines() so it is escaped")

if UPSTREAM_OK:
    interview_fields = fields_of(json.loads(upstream("hrms", "hr", "doctype", "interview", "interview.json")))
    if (interview_fields.get("job_opening") or {}).get("fetch_from") != "job_applicant.job_title":
        fail.append("HRMS's Interview no longer carries its Job Opening: recheck get_interview_results")
    state_row = fields_of(json.loads(upstream("frappe", "workflow", "doctype", "workflow_document_state", "workflow_document_state.json")))
    if "1" not in (state_row.get("doc_status") or {}).get("options", "").split("\n"):
        fail.append("Frappe's Workflow no longer lets a state submit the document: recheck the report's Approved state")
    workflow_py = upstream("frappe", "workflow", "doctype", "workflow", "workflow.py")
    if "def create_custom_field_for_workflow_state" not in workflow_py or "if not meta.get_field(self.workflow_state_field)" not in workflow_py:
        fail.append("Frappe's Workflow changed how it adds the state field: recheck Interview Report.workflow_state")
print("report: approval walked end to end, sign-offs, panel summary, checks, doctypes, results, form script and print format resolve")

# ── 9b. Closing the loop: the approved report's interviews, applicants and offers
asa = rules.applicant_status_after
if set(rules.APPLICANT_STATUSES) != set(rules.RECOMMENDATIONS):
    fail.append("every decision on the report must say what becomes of the applicant: %s" % (rules.APPLICANT_STATUSES,))
for decision, current, after, why in (
        ("Offer", "Shortlisted", "Accepted", "an offer marks the applicant Accepted, as HRMS does for a cleared interview"),
        ("Reject", "Shortlisted", "Rejected", "a rejection marks the applicant Rejected"),
        ("Shortlist", "Hold", "Shortlisted", "Shortlist means another interview, so the applicant is Shortlisted"),
        ("Shortlist", "Shortlisted", None, "an applicant already Shortlisted is left alone"),
        ("Offer", "Open", "Accepted", "an applicant added by hand, never shortlisted, still moves on"),
        ("Reject", "Accepted", None, "an applicant already Accepted (by a Job Offer, say) keeps it"),
        ("Offer", "Rejected", None, "an applicant already Rejected keeps it"),
        ("", "Shortlisted", None, "no decision moves nobody"),
        (None, "Open", None, "no decision moves nobody")):
    if asa(decision, current) != after:
        fail.append("%s: applicant_status_after(%r, %r) is %r" % (why, decision, current, asa(decision, current)))
plan = rules.offer_plan([
    {"job_applicant": "A", "decision": "Offer"}, {"job_applicant": "B", "decision": "Offer", "job_offer": "JO-B"},
    {"job_applicant": "C", "decision": "Offer", "job_offer": "JO-OLD"}, {"job_applicant": "D", "decision": "Reject"},
    {"job_applicant": "E", "decision": "Shortlist"}, {"job_applicant": "F", "decision": "Offer"}, {"job_applicant": "", "decision": "Offer"},
], {"B": "JO-B", "D": "JO-D", "F": "JO-F"})
if plan != (["A", "C"], [("F", "JO-F")]):
    fail.append("offers: a draft for each Offer with no live offer (a cancelled one does not count), a link to the offer a candidate "
                "already has, nothing for a row already linked or not offered the job: %s" % (plan,))
if rules.offer_plan([], {}) != ([], []) or rules.offer_plan(None, None) != ([], []):
    fail.append("a report with no candidates makes no offers")

jo = rc_fields.get("job_offer") or {}
if (jo.get("fieldtype"), jo.get("options")) != ("Link", "Job Offer") or not (jo.get("read_only") and jo.get("allow_on_submit") and jo.get("no_copy")):
    fail.append("Interview Report Candidate.job_offer is set after approval: a read-only Link to Job Offer, settable after submit, not copied")
if not re.search(r"def on_submit\(self\):\n        interviews\.close_report\(self\)",
                 read("hrms_addon", "hrms_addon", "doctype", "interview_report", "interview_report.py")) or "def close_report(doc):" not in glue:
    fail.append("Interview Report on_submit (the approval) must call interviews.close_report")
close_body = glue.split("def close_report(")[-1].split("\ndef ")[0]
close_one = glue.split("def _close_interview(")[-1].split("\ndef ")[0]
offers_body = glue.split("def create_job_offers(")[-1].split("\ndef ")[0]
for body, needle, why in (
    (close_body, "result = rules.result_for(row.decision)", "must close each interview with the tested result for its decision"),
    (close_body, "rules.applicant_status_after(row.decision, current)", "must move applicants on with the tested rules"),
    (close_body, 'frappe.db.set_value("Job Applicant", row.job_applicant, "status", status)', "must set the applicant's new status"),
    (close_body, "doc.add_comment(", "must leave HR a note of the interviews it could not close"),
    (close_body, "escape_html(reason)", "must escape the reasons an interview could not be closed"),
    (close_one, 'if interview.docstatus != 0 or interview.status == "Cancelled":\n        return None',
     "must leave an interview closed or cancelled by hand alone"),
    (close_one, "interview.flags.ignore_permissions = True", "must close interviews for the approver, who need not have rights on them"),
    (close_one, 'frappe.db.rollback(save_point="hrms_addon_close_interview")', "must undo a refused interview and carry on"),
    (close_one, "frappe.flags.mute_messages = True", "must keep HRMS's per-interview prompt from the approver"),
    (close_one, "finally:\n        frappe.flags.mute_messages = muted", "must restore messages however the submit ends"),
    (offers_body, 'doc.check_permission("read")', "must check the user may read the report"),
    (offers_body, 'frappe.has_permission("Job Offer", "create", throw=True)', "must check the user may create Job Offers"),
    (offers_body, "if doc.docstatus != 1:", "must make offers only from an approved report"),
    (offers_body, '"docstatus": ["!=", 2]', "must count the offers HRMS counts: any not cancelled"),
    (offers_body, "rules.offer_plan(doc.candidates, existing)", "must plan the offers with the tested rules"),
    (offers_body, 'frappe.db.rollback(save_point="hrms_addon_job_offer")', "must undo a refused offer and carry on with the rest"),
    (offers_body, 'row.db_set("job_offer", offer.name)', "must link each candidate to the offer made"),
    (offers_body, 'rows[applicant].db_set("job_offer", offer)', "must link a candidate to the offer they already have"),
):
    if needle not in body:
        fail.append("interviews.py %s" % why)
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\s*\ndef create_job_offers\(', glue):
    fail.append("interviews.create_job_offers must be whitelisted for POST")
offer_given = set(re.findall(r'"(\w+)": ', offers_body.split('"doctype": "Job Offer",')[-1].split("})")[0]))
for needle, why in (
    ('.xcall("hrms_addon.hrms_addon.interviews.create_job_offers", { report: frm.doc.name })', "must make the offers through interviews.create_job_offers"),
    ('row.decision === "Offer" && !row.job_offer', "must count the Offers still without a Job Offer"),
    ('frm.doc.docstatus === 1 && unoffered.length && frappe.model.can_create("Job Offer")',
     "must offer Create Job Offers only on an approved report, to someone who can create them"),
    ("frappe.utils.escape_html(reason)", "must escape the reasons an offer was refused"),
):
    if needle not in rjs:
        fail.append("interview_report.js %s" % why)

if UPSTREAM_OK:
    interview_py = upstream("hrms", "hr", "doctype", "interview", "interview.py")
    if 'if self.status not in ["Cleared", "Rejected"]:' not in interview_py:
        fail.append("HRMS's Interview no longer submits only Cleared or Rejected: recheck close_report")
    if 'status_map = {"Cleared": "Accepted", "Rejected": "Rejected"}' not in interview_py:
        fail.append("HRMS no longer marks a cleared interview's applicant Accepted: recheck APPLICANT_STATUSES")
    applicant_statuses = set((fields_of(json.loads(upstream("hrms", "hr", "doctype", "job_applicant", "job_applicant.json"))).get("status") or {})
                             .get("options", "").split("\n"))
    if not set(rules.APPLICANT_STATUSES.values()) <= applicant_statuses:
        fail.append("HRMS's Job Applicant has no status %s any more" % sorted(set(rules.APPLICANT_STATUSES.values()) - applicant_statuses))
    if '{"job_applicant": self.job_applicant, "docstatus": ["!=", 2]}' not in upstream("hrms", "hr", "doctype", "job_offer", "job_offer.py"):
        fail.append("HRMS changed which Job Offers count against an applicant: recheck create_job_offers")
    offer_fields = fields_of(json.loads(upstream("hrms", "hr", "doctype", "job_offer", "job_offer.json")))
    for fieldname, f in offer_fields.items():
        if f.get("reqd") and not f.get("fetch_from") and fieldname not in offer_given:
            fail.append("HRMS's Job Offer requires %s, which create_job_offers does not set" % fieldname)
    for fieldname in offer_given - set(offer_fields):
        fail.append("create_job_offers sets Job Offer.%s, which HRMS does not have" % fieldname)

# The shortlist and the report record the Interviews and Job Offers made from
# them; they must not stop HR cancelling one to correct it
for doctype in ("Interview", "Job Offer"):
    if not re.search(r'"%s": \{[^}]*"on_cancel": "hrms_addon\.hrms_addon\.interviews\.unblock_cancel"' % doctype, hook_block("doc_events")):
        fail.append("doc_events must run interviews.unblock_cancel on %s on_cancel, or the shortlist and report block its correction" % doctype)
exempted = re.search(r"^auto_cancel_exempted_doctypes = \[([^\]]*)\]", hooks, re.M)
if not exempted or set(re.findall(r'"([^"]+)"', exempted.group(1))) != {"Interview Shortlist", "Interview Report"}:
    fail.append("auto_cancel_exempted_doctypes must keep the shortlist and the report out of Frappe's Cancel All")
if 'RECORDS = ("Interview Shortlist", "Interview Report")' not in glue \
        or 'doc.ignore_linked_doctypes = tuple(doc.get("ignore_linked_doctypes") or ()) + RECORDS' not in glue:
    fail.append("interviews.unblock_cancel must add the shortlist and the report to ignore_linked_doctypes, keeping any it has")
if UPSTREAM_OK:
    if 'if method == "Cancel" and (doc_ignore_flags := doc.get("ignore_linked_doctypes")):' not in upstream("frappe", "model", "delete_doc.py"):
        fail.append("Frappe's cancel link check no longer reads ignore_linked_doctypes: recheck unblock_cancel")
    if 'frappe.get_hooks("auto_cancel_exempted_doctypes")' not in upstream("frappe", "desk", "form", "linked_with.py"):
        fail.append("Frappe's Cancel All no longer reads auto_cancel_exempted_doctypes")
    if 'elif self._action == "cancel":\n\t\t\tself.run_method("on_cancel")\n\t\t\tself.check_no_back_links_exist()' \
            not in upstream("frappe", "model", "document.py"):
        fail.append("Frappe no longer runs on_cancel before its link check: recheck unblock_cancel")
print("closing the loop: interviews closed and applicants moved on at approval, one draft Job Offer per Offer, rights and HRMS contract checked")

# ── 9c. Each branch sees its own ──────────────────────────────────────
# The shortlist and the report take the Job Opening's branch and department,
# so Branch and Department User Permissions show each branch's HODs and HR
# Officer their own (org_rules.py)
for label, fields in (("Interview Shortlist", shl_fields), ("Interview Report", rep_fields)):
    for fieldname, options, source in (("branch", "Branch", "job_opening.location"), ("department", "Department", "job_opening.department")):
        f = fields.get(fieldname) or {}
        if (f.get("fieldtype"), f.get("options"), f.get("fetch_from"), f.get("read_only")) != ("Link", options, source, 1):
            fail.append("%s.%s must be the Job Opening's %s, read-only, so each branch sees its own" % (label, fieldname, source.split(".")[1]))
print("branches: the shortlist and the report carry the Job Opening's branch and department")

# ── 10. Where HR finds it: the Recruitment workspace ─────────────────
import ast

spec = importlib.util.spec_from_file_location("workspace_rules", os.path.join(APP, "workspace_rules.py"))
wsr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wsr)  # no Frappe import
ws_src = read("hrms_addon", "hrms_addon", "workspace_setup.py")
declared = next((ast.literal_eval(node.value) for node in ast.parse(ws_src).body
                 if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "WORKSPACE_ADD_LINKS"), {})
interview_links = (declared.get("Recruitment") or {}).get("Interviews") or []
if [link[2] for link in interview_links] != ["Interview Shortlist", "Interview Report", "Interview Criterion"]:
    fail.append("WORKSPACE_ADD_LINKS must put Interview Shortlist, Interview Report and Interview Criterion on Recruitment's Interviews card")
for label, link_type, link_to, _after in interview_links:
    folder = link_to.lower().replace(" ", "_")
    if link_type != "DocType" or not os.path.exists(os.path.join(APP, "doctype", folder, folder + ".json")):
        fail.append("the Recruitment link %s must open one of this app's DocTypes" % label)

sample = [
    {"type": "Card Break", "label": "Jobs"}, {"type": "Link", "label": "Job Opening", "link_type": "DocType", "link_to": "Job Opening"},
    {"type": "Card Break", "label": "Interviews"},
    {"type": "Link", "label": "Interview Type", "link_type": "DocType", "link_to": "Interview Type"},
    {"type": "Link", "label": "Interview", "link_type": "DocType", "link_to": "Interview"},
    {"type": "Link", "label": "Interview Feedback", "link_type": "DocType", "link_to": "Interview Feedback"},
    {"type": "Card Break", "label": "Appointment"},
    {"type": "Link", "label": "Appointment Letter", "link_type": "DocType", "link_to": "Appointment Letter"},
]
planned = wsr.plan_card_links(sample, "Interviews", interview_links)
if wsr.card_links(planned, "Interviews") != ["Interview Shortlist", "Interview Type", "Interview", "Interview Feedback",
                                             "Interview Report", "Interview Criterion"]:
    fail.append("the Interviews card must read Shortlist, Type, Interview, Feedback, Report, Criterion: %s"
                % wsr.card_links(planned, "Interviews"))
if wsr.card_links(planned, "Jobs") != ["Job Opening"] or wsr.card_links(planned, "Appointment") != ["Appointment Letter"]:
    fail.append("adding to the Interviews card must leave the other cards alone")
if any(row.get("new") for row in wsr.plan_card_links([{k: v for k, v in r.items() if k != "new"} for r in planned],
                                                      "Interviews", interview_links)):
    fail.append("adding the links again must change nothing (idempotent on every migrate)")
if wsr.plan_card_links(sample, "No Such Card", interview_links) is not None:
    fail.append("a workspace without the card must be left alone")
moved = wsr.plan_card_links(sample, "Interviews", [("Extra", "DocType", "Extra", "Not There")])
if wsr.card_links(moved, "Interviews")[-1] != "Extra":
    fail.append("a link whose anchor is missing goes last in its card, not into the next card")
on_migrate = re.sub(r'^\s*""".*?"""', "", ws_src.split("def apply_on_migrate():")[-1], count=1, flags=re.S)
first_add = on_migrate.find("apply_added_links()")
if first_add < 0 or re.search(r"\breturn\b", on_migrate[:first_add]):
    fail.append("workspace_setup.py apply_on_migrate must add the links on every migrate, not only once the menu order is agreed")
for needle, why in (
    ("workspace_rules.plan_card_links(rows, card, wanted)", "must place the links with the tested rules"),
    ('frappe.db.set_value("Workspace Link", card_row["name"], "link_count", count, update_modified=False)',
     "must keep the card's link count true, or the workspace editor cuts the links out of the card"),
    ('"doctype": "Workspace Link",', "must write Workspace Link rows, never save another app's Workspace"),
):
    if needle not in ws_src:
        fail.append("workspace_setup.py %s" % why)
if ".save(" in ws_src:
    fail.append("workspace_setup.py must not save a Workspace: in developer mode that writes it into Frappe HR's files")

if UPSTREAM_OK:
    recruitment = json.loads(upstream("hrms", "hr", "workspace", "recruitment", "recruitment.json"))
    real = wsr.plan_card_links(recruitment["links"], "Interviews", interview_links)
    if real is None or wsr.card_links(real, "Interviews") != ["Interview Shortlist", "Interview Type", "Interview",
                                                              "Interview Feedback", "Interview Report", "Interview Criterion"]:
        fail.append("HRMS's Recruitment workspace no longer has the Interviews card with Interview Feedback: recheck WORKSPACE_ADD_LINKS")
print("workspace: the three documents on Recruitment's Interviews card, placed idempotently, link count kept true")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL INTERVIEW CHECKS PASSED")
