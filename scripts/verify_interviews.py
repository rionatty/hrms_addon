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
    on in HRMS (the Shortlisted status, the Interview Type's panel).

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
if list(rules.CRITERIA) != PAPER:
    fail.append("CRITERIA must be LPL/HR/17's 17 criteria in the form's order: %s" % (rules.CRITERIA,))
groups_in_order = []
for group, _criterion in rules.CRITERIA:
    if group not in groups_in_order:
        groups_in_order.append(group)
if list(rules.CRITERIA_GROUPS) != groups_in_order:
    fail.append("CRITERIA_GROUPS %s must be the criteria's groups in the form's order %s" % (rules.CRITERIA_GROUPS, groups_in_order))
if rules.SCORE_OPTIONS != ("", "1", "2", "3", "4", "5", "N/A") or rules.TOP_SCORE != 5:
    fail.append("the scale is 1 to 5 or N/A, with blank for not scored yet: %s" % (rules.SCORE_OPTIONS,))
if rules.BANDS != ((90, "Excellent"), (75, "Very Good"), (60, "Good"), (50, "Average"), (0, "Below Average")):
    fail.append("BANDS must be the form's: Excellent 90-100, Very Good 75-89, Good 60-74, Average 50-59, Below Average 49 and below")
if rules.RECOMMENDATIONS != ("Offer", "Shortlist", "Reject"):
    fail.append("RECOMMENDATIONS must be the form's Offer / Shortlist / Reject")
print("form: %d criteria in %d groups, scored 1-5 or N/A, five bands, three recommendations"
      % (len(rules.CRITERIA), len(rules.CRITERIA_GROUPS)))

# ── 2. Scoring ───────────────────────────────────────────────────────
def sheet(*scores):
    return [{"criterion": criterion, "score": score} for (_group, criterion), score in zip(rules.CRITERIA, scores)]


full = sheet("5", "4", "4", "3", "N/A", "5", "4", "4", "3", "4", "5", "3", "4", "4", "3", "5", "5")
summary = rules.score_summary(full)
if (summary["total"], summary["maximum"], summary["percent"], summary["band"], summary["scored"], summary["not_applicable"]) \
        != (65, 80, 81.25, "Very Good", 16, 1):
    fail.append("a full sheet with one N/A: expected 65 of 80, 81.25%%, Very Good, got %s" % summary)
if rules.average_rating(summary) != 0.8125:
    fail.append("the sheet as HRMS's 0-1 rating must be 0.8125, got %s" % rules.average_rating(summary))
for total, maximum, band in ((27, 30, "Excellent"), (45, 50, "Excellent"), (26, 30, "Very Good"), (15, 20, "Very Good"),
                             (14, 20, "Good"), (12, 20, "Good"), (11, 20, "Average"), (10, 20, "Average"),
                             (9, 20, "Below Average"), (1, 5, "Below Average"), (5, 5, "Excellent"), (0, 0, "")):
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
expect("a complete sheet submitted", errors(full, "Offer", submitting=True))
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
averages = rules.criterion_averages([
    [{"criterion": "Job knowledge", "score": "5"}, {"criterion": "Health", "score": "N/A"}, {"criterion": "Computer skills", "score": ""}],
    [{"criterion": "Job knowledge", "score": "4"}, {"criterion": "Health", "score": "3"}],
])
if averages != [("Job knowledge", 4.5), ("Health", 3.0)]:
    fail.append("the panel's averages ignore N/A and blanks and keep the form's order: %s" % averages)

group_records, criterion_records = rules.criteria_seed_plan([], [])
if [(g["group_name"], g["sort_order"]) for g in group_records] != [(g, (i + 1) * 10) for i, g in enumerate(rules.CRITERIA_GROUPS)]:
    fail.append("fresh seed must create the five groups ordered 10-50: %s" % group_records)
if [(c["criteria_group"], c["criterion_name"]) for c in criterion_records] != list(rules.CRITERIA) \
        or [c["sort_order"] for c in criterion_records] != [(i + 1) * 10 for i in range(len(rules.CRITERIA))]:
    fail.append("fresh seed must create the 17 criteria in the form's order, 10 apart")
if any(c["doctype"] != "Interview Criterion" for c in criterion_records) or any(g["doctype"] != "Interview Criteria Group" for g in group_records):
    fail.append("seed records must name their DocTypes")
group_records, criterion_records = rules.criteria_seed_plan(["education", "Health"], ["technical qualification skills", "Health"])
if [g["group_name"] for g in group_records] != ["Working Experience", "Personality", "Appearance"]:
    fail.append("seeding must skip groups already there, ignoring case: %s" % group_records)
if len(criterion_records) != 15 or any(c["criterion_name"] in ("Technical Qualification skills", "Health") for c in criterion_records):
    fail.append("seeding must skip criteria already there, ignoring case")
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
if not score_spec.get("istable") or list(score_fields) != ["criteria_group", "criterion", "score", "comments"]:
    fail.append("Interview Feedback Score must be a child table of criteria_group, criterion, score, comments")
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
    ("rules.score_sheet_errors(doc.custom_scores, doc.get(\"custom_recommendation\"), submitting=doc.docstatus == 1)",
     "must check the sheet with the tested rules, strictly only on submit"),
    ("doc.average_rating = rules.average_rating(summary)", "must feed the sheet's percentage to HRMS's average rating"),
    ("doc.result = rules.result_for(doc.custom_recommendation)", "must set HRMS's result from the recommendation"),
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
for needle, why in (
    ('frappe.xcall("hrms_addon.hrms_addon.interviews.get_score_criteria")', "must start a new sheet from the criteria list"),
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
education = rules.qualification_lines(quals, CERTS, certifications=False)
if education.split("\n") != [
        "Post Graduate Diploma in Digital Marketing, Chartered Institute of Marketing (2026)",
        "UACE, East High School Ntinda (2017)",
        "Bachelor's Degree in Business Computing, Makerere University Business School (2008 - 2012)"]:
    fail.append("education must list the academic rows, most recent first, award standing in for a missing program: %r" % education)
certifications = rules.qualification_lines(quals, [c.lower() for c in CERTS], certifications=True)
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
if rules.interview_slots("09:00", 30, 3) != [("09:00:00", "09:30:00"), ("09:30:00", "10:00:00"), ("10:00:00", "10:30:00")] \
        or rules.interview_slots("13:45:00", 45, 1) != [("13:45:00", "14:30:00")] or rules.interview_slots("09:00", 20, 0) != []:
    fail.append("interview slots must run back to back from the first start time")
for args, why in ((("09:00", 0, 2), "a length of 0"), (("22:30", 60, 2), "running past midnight"), (("", 30, 1), "no start time")):
    try:
        rules.interview_slots(*args)
        fail.append("interview_slots must refuse %s" % why)
    except ValueError:
        pass
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
if list(cand_fields) != ["job_applicant", "applicant_name", "phone_number", "email_id", "education", "work_experience",
                         "certifications", "interview"] or not cand.get("istable"):
    fail.append("Interview Shortlist Candidate's fields are not the shortlist's columns: %s" % list(cand_fields))
if not (cand_fields.get("interview") or {}).get("allow_on_submit"):
    fail.append("Interview Shortlist Candidate.interview is set after submit, so it needs allow_on_submit")
if sum(f.get("columns") or 0 for f in cand["fields"] if f.get("in_list_view")) > 10:
    fail.append("the shortlist grid exceeds 10 columns")
controller = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.py")
for event, function in (("validate", "validate_shortlist"), ("on_submit", "mark_shortlisted"), ("on_cancel", "unmark_shortlisted")):
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
    ("slots = rules.interview_slots(from_time, minutes, len(pending))", "must book with the tested slots"),
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
    ("frm.doc.docstatus === 1 && unscheduled.length", "must offer Schedule Interviews only once submitted, while someone is unscheduled"),
    ("filters: { job_title: frm.doc.job_opening", "must pick applicants of this opening only"),
    ("frappe.utils.escape_html(reason)", "must escape the reasons a booking was refused"),
):
    if needle not in sjs:
        fail.append("interview_shortlist.js %s" % why)
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

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL INTERVIEW CHECKS PASSED")
