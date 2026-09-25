"""Verify the CV screening of job applicants, without a bench:

    python scripts/verify_screening.py

  1  words: phrases, whole-word search, Word documents
  2  experience: years from the employment history, overlaps once
  3  answers: yes or no, numbers, phone numbers
  4  the screening: weights, must-haves, pass mark, what HR checks by hand;
     HR's filter for Get Applicants
  5  fairness: gender, age and home district are never read
  6  the glue: hooks, the patch, the shortlist, the careers form, the scripts
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


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def expect(label, got, wanted):
    if got != wanted:
        fail.append("%s: got %r, expected %r" % (label, got, wanted))


R = load("cv_screening_rules")
print("loaded cv_screening_rules.py without Frappe")

# ── 1. Words ──────────────────────────────────────────────────────────
expect("phrases split on lines, commas and semicolons",
       R.phrases("Mechanical Engineering, Class B permit\nPolymer; B.Sc\n\nmechanical engineering"),
       ["mechanical engineering", "class b permit", "polymer", "b sc"])
cv = R.normalise("Diploma in MECHANICAL-Engineering (2019). A smart, team-oriented operator; C++ basics.")
expect("a phrase is found whatever its case and punctuation", R.first_found(["mechanical engineering"], cv),
       "mechanical engineering")
expect("only as whole words", R.first_found(["art", "team"], cv), "team")
expect("C++ keeps its pluses", R.first_found(["c++"], cv), "c++")
expect("nothing found", R.first_found(["welding"], cv), None)
xml = ('<w:document><w:body><w:p><w:r><w:t>Diploma in</w:t></w:r><w:r><w:t xml:space="preserve"> Mechanical'
       '</w:t></w:r><w:r><w:tab/><w:t>Engineering &amp; Plastics</w:t></w:r></w:p><w:p><w:r><w:t>Team work'
       '</w:t></w:r></w:p></w:body></w:document>')
expect("a Word document's text, a line per paragraph", R.docx_text(xml.encode("utf-8")),
       "Diploma in Mechanical Engineering & Plastics\nTeam work\n")
print("words: phrases, whole words, Word documents")

# ── 2. Experience ─────────────────────────────────────────────────────
for value, year in (("2019", 2019), ("Jan 2020", 2020), ("to date", 2026), ("Present", 2026), ("current", 2026),
                    ("", None), ("2031", None), ("recently", None)):
    expect("year_of(%r)" % value, R.year_of(value, 2026), year)
JOBS = [
    {"position": "Machine Operator", "workplace": "Nice House of Plastics", "from_year": "2015", "to_year": "2018"},
    {"position": "Extrusion Operator", "workplace": "Mukwano", "from_year": "2017", "to_year": "2020"},
    {"position": "Store Keeper", "workplace": "Roofings", "from_year": "2022", "to_year": "to date"},
    {"position": "Casual", "workplace": "Market", "from_year": "", "to_year": "2014"},
]
expect("years, overlapping jobs counted once", R.experience_years(JOBS, 2026), 9)
expect("only the jobs that mention what is looked for", R.experience_years(JOBS, 2026, ["operator"]), 5)
expect("a job with no end year is still held",
       R.experience_years([{"position": "Operator", "from_year": "2023", "to_year": ""}], 2026), 3)
expect("a job that ends before it starts counts nothing",
       R.experience_years([{"position": "Operator", "from_year": "2020", "to_year": "2018"}], 2026), 0)
print("experience: years from the employment history, overlaps once, a job still held")

# ── 3. Answers ────────────────────────────────────────────────────────
for answer, value in (("yes", "Yes"), (" Y ", "Yes"), ("No", "No"), ("n", "No"), ("maybe", None), ("", None)):
    expect("yes_or_no(%r)" % answer, R.yes_or_no(answer), value)
for answer, value in (("1,200,000", 1200000.0), ("5 years", 5.0), ("UGX 800000 per month", 800000.0), ("", None),
                      ("none", None)):
    expect("number(%r)" % answer, R.number(answer), value)
expect("a yes-or-no answer is kept as Yes", R.clean_answer("y", R.YES_OR_NO), "Yes")
expect("an answer that is neither is kept as typed", R.clean_answer("sometimes", R.YES_OR_NO), "sometimes")
expect("a number is kept as typed", R.clean_answer(" 1,200,000 ", R.NUMBER), "1,200,000")
expect("the ways one number is written", R.phone_variants("0772 123456"),
       ["+256772123456", "0772 123456", "0772123456", "256772123456"])
expect("too short to be a number", R.phone_variants("12345"), [])
print("answers: yes or no, numbers, phone numbers")

# ── 4. The screening ──────────────────────────────────────────────────
ESSENTIAL, PREFERRED, DESIRABLE = dict(weight=3, must_have=1), dict(weight=2, must_have=0), dict(weight=1, must_have=0)
CHECKS = [
    dict(ESSENTIAL, label="Injection Moulding", kind=R.SKILL, skill="Injection Moulding"),
    dict(DESIRABLE, label="Teamwork", kind=R.SKILL, skill="Teamwork"),
    dict(ESSENTIAL, label="Diploma in Mechanical Engineering", kind="Academic Qualification",
         phrases=["mechanical engineering", "mechanics"]),
    dict(PREFERRED, label="Class B driving permit", kind="Professional Training & Certification",
         phrases=["class b"]),
    dict(PREFERRED, label="3 years operating machines", kind="Work Experience", phrases=["operator"],
         minimum_years=3),
    dict(DESIRABLE, label="First aid training", kind="Professional Training & Certification", phrases=[]),
    dict(ESSENTIAL, label="Can you work night shifts?", kind=R.QUESTION, id="Q1", answer_type=R.YES_OR_NO,
         wanted="Yes"),
    dict(PREFERRED, label="Expected monthly salary (UGX)", kind=R.QUESTION, id="Q2", answer_type=R.NUMBER,
         minimum=0, maximum=1500000),
    dict(DESIRABLE, label="Where do you live?", kind=R.QUESTION, id="Q3", answer_type=R.YES_OR_NO, wanted=""),
]
AMOS = {"skills": ["Injection Moulding"], "bio_data": "Academic Diploma in Mechanical Engineering UTC Kyema",
        "experience": JOBS, "cv": "I enjoy teamwork.", "answers": {"Q1": "Yes", "Q2": "1,200,000", "Q3": "Kawempe"},
        "this_year": 2026}
amos = R.screen(CHECKS, AMOS, 60)
expect("the job is met", amos["result"], R.MEETS)
expect("all but the Class B permit", amos["missing"], ["Class B driving permit"])
expect("with the permit, the full score", R.screen(CHECKS, dict(AMOS, bio_data=AMOS["bio_data"] + " class B"),
                                                   60)["score"], 100)
expect("a line found only in the CV", "Class B driving permit (CV)" in R.screen(
    CHECKS, dict(AMOS, cv="I enjoy teamwork. I hold a Class B permit."), 60)["matched"], True)
expect("where each was met", [note for note in amos["matched"] if "(" in note][:3],
       ["Injection Moulding (bio-data)", "Teamwork (CV)", "Diploma in Mechanical Engineering (bio-data)"])
expect("years that meet the minimum", "3 years operating machines: 5 years" in amos["matched"], True)
expect("a question with no wanted answer is shown, not scored", "Where do you live?: Kawempe" in amos["matched"],
       True)
expect("a line with nothing to look for is left to HR", amos["to_check"], ["First aid training"])
expect("the years worked", amos["experience_years"], 9)
# weights: 3 + 1 + 3 + 2 + 2 + 3 + 2 = 16 scored; Class B (2) missing
expect("the score weighs each check by its priority", amos["score"], int(round(100.0 * 14 / 16)))

no_nights = R.screen(CHECKS, dict(AMOS, answers={"Q1": "No", "Q2": "1,200,000"}), 60)
expect("a must-have not met: does not meet, whatever the score", no_nights["result"], R.DOES_NOT_MEET)
expect("and says which", "Can you work night shifts?: No" in no_nights["missing"], True)
unanswered = R.screen(CHECKS, dict(AMOS, answers={"Q2": "1,200,000"}), 60)
expect("a must-have question not answered", (unanswered["result"], "Can you work night shifts?: not answered" in
                                              unanswered["missing"]), (R.DOES_NOT_MEET, True))
by_text = R.screen(CHECKS, dict(AMOS, answers={"Can you work night shifts?": "yes", "Q2": "900000"}), 60)
expect("an answer found by its question when it has no id", by_text["must_haves_met"], True)
dear = R.screen(CHECKS, dict(AMOS, answers={"Q1": "Yes", "Q2": "2,000,000"}), 60)
expect("a number over the maximum", "Expected monthly salary (UGX): 2,000,000" in dear["missing"], True)
weak = R.screen(CHECKS, {"skills": ["Injection Moulding"], "bio_data": "Certificate in Mechanics",
                         "experience": [], "cv": "", "answers": {"Q1": "Yes"}, "this_year": 2026}, 60)
expect("the must-haves met but little else: below the pass mark", (weak["result"], weak["score"]),
       (R.BELOW_PASS_MARK, int(round(100.0 * 9 / 16))))
expect("with no years, how many were wanted", "3 years operating machines: 0 of 3 years" in weak["missing"], True)
expect("the pass mark is the opening's", R.screen(CHECKS, weak and {"skills": ["Injection Moulding"],
                                                                   "bio_data": "Certificate in Mechanics",
                                                                   "experience": [], "cv": "",
                                                                   "answers": {"Q1": "Yes"}, "this_year": 2026},
                                                  50)["result"], R.MEETS)
cv_years = R.screen([dict(PREFERRED, label="3 years operating machines", kind="Work Experience",
                          phrases=["operator"], minimum_years=3)],
                    {"skills": [], "bio_data": "", "experience": [], "cv": "Machine operator since 2015",
                     "answers": {}, "this_year": 2026}, 60)
expect("years mentioned only in the CV are not counted, but noted",
       cv_years["missing"], ["3 years operating machines: 0 of 3 years (mentioned in the CV)"])
exactly = R.screen([dict(PREFERRED, label="3 years", kind="Work Experience", phrases=[], minimum_years=3)],
                   {"skills": [], "bio_data": "", "cv": "", "answers": {}, "this_year": 2026,
                    "experience": [{"position": "Fitter", "from_year": "2023", "to_year": "2026"}]}, 60)
expect("exactly the years wanted is enough", exactly["result"], R.MEETS)
nothing = R.screen([dict(ESSENTIAL, label="Good character", kind="Other", phrases=[])],
                   {"skills": [], "bio_data": "", "experience": [], "cv": "", "answers": {}, "this_year": 2026}, 60)
expect("nothing that can be checked: no score, no result, all to HR",
       (nothing["score"], nothing["result"], nothing["to_check"]), (None, None, ["Good character"]))
zero = R.screen([dict(label="Teamwork", kind=R.SKILL, skill="Teamwork", weight=0, must_have=0)],
                {"skills": ["Teamwork"], "bio_data": "", "experience": [], "cv": "", "answers": {}, "this_year": 2026}, 60)
expect("a priority weighing nothing counts nothing", zero["score"], None)
rows = [{"screening_result": R.DOES_NOT_MEET, "match_score": 90}, {"screening_result": "", "match_score": None},
        {"screening_result": R.MEETS, "match_score": 70}, {"screening_result": R.BELOW_PASS_MARK, "match_score": 50},
        {"screening_result": R.MEETS, "match_score": 95}]
expect("Meets first, highest first, then the rest", [(row["screening_result"], row["match_score"])
                                                     for row in sorted(rows, key=R.sort_key)],
       [(R.MEETS, 95), (R.MEETS, 70), (R.BELOW_PASS_MARK, 50), (R.DOES_NOT_MEET, 90), ("", None)])
expect("the seeded priorities", R.DEFAULT_PRIORITIES, {"Essential": (3, 1), "Preferred": (2, 0), "Desirable": (1, 0)})
print("the screening: weights, must-haves, the pass mark, years, questions, what HR checks by hand")

# HR's filter for Get Applicants
expect("a filter, cleaned", R.shortlist_filter({"results": ["Meets", "Bogus"], "min_score": "70", "min_years": None,
                                                "look_for": "Mechanical Engineering\nKyambogo", "match_all": 1,
                                                "limit": "2"}),
       {"results": ["Meets"], "min_score": 70.0, "min_years": 0.0, "look_for": ["mechanical engineering", "kyambogo"],
        "match_all": True, "limit": 2})
expect("no filter", R.shortlist_filter(None), {"results": [], "min_score": 0.0, "min_years": 0.0, "look_for": [],
                                               "match_all": False, "limit": 0})
pool = [
    {"applicant_name": "A", "screening_result": R.MEETS, "match_score": 100, "experience_years": 5,
     "search_text": "Diploma in Mechanical Engineering UTC Kyema"},
    {"applicant_name": "B", "screening_result": R.DOES_NOT_MEET, "match_score": 40, "experience_years": 2,
     "search_text": "Certificate in Mechanics"},
    {"applicant_name": "N", "screening_result": "", "match_score": None, "experience_years": 0, "search_text": ""},
    {"applicant_name": "E", "screening_result": R.BELOW_PASS_MARK, "match_score": 60, "experience_years": 0,
     "search_text": "Diploma in Mechanical Engineering"},
    {"applicant_name": "C", "screening_result": R.MEETS, "match_score": 73, "experience_years": 2,
     "search_text": "Mechanical Engineering, Kyambogo"},
]


def kept(values):
    rows, left_out = R.filter_candidates(pool, R.shortlist_filter(values))
    return [row["applicant_name"] for row in rows], left_out


expect("no filter: everyone, the best first", kept({}), (["A", "C", "E", "B", "N"], 0))
expect("by result", kept({"results": ["Meets"]}), (["A", "C"], 3))
expect("the ones nothing could be checked for", kept({"results": ["Not Checked"]}), (["N"], 4))
expect("the lowest match", kept({"min_score": 60}), (["A", "C", "E"], 2))
expect("the fewest years", kept({"min_years": 2}), (["A", "C", "B"], 2))
expect("any word found", kept({"look_for": "Kyambogo, UTC Kyema"}), (["A", "C"], 3))
expect("all of them", kept({"look_for": "mechanical engineering\nkyambogo", "match_all": 1}), (["C"], 4))
expect("whole words only", kept({"look_for": "mechanic"}), ([], 5))
expect("at most, the best first", kept({"limit": 2}), (["A", "C"], 3))
expect("together", kept({"results": ["Meets", "Below Pass Mark"], "look_for": "diploma"}), (["A", "E"], 3))
refused = R.filter_errors(R.shortlist_filter({"look_for": "Female\nCPA\nborn again, Catholic"}))
expect("the filter refuses what the screening never uses, and names it",
       (len(refused), refused[0].split(": ")[-1] if refused else None), (1, "female, born again, catholic."))
expect("and lets a job's own words through", R.filter_errors(R.shortlist_filter({"look_for": "foreman\nsales manager"})),
       [])
print("HR's filter: by result, match, years and words in the bio-data or CV, the best first, never on who they are")

# ── 5. Fairness ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "cv_screening.py")


def body(source, name):
    return source.split("def %s(" % name)[1].split("\ndef ")[0]


protected = ("gender", "date_of_birth", "marital", "religion", "district", "village", "children", "citizenship",
             "tribe", "health")
facts = body(glue, "applicant_facts") + body(glue, "screen")
for word in protected:
    if word in facts.lower().replace("never their gender, age, marital status,\n    religion or home district", ""):
        fail.append("the screening must not read the applicant's %s" % word)
rules_source = read("hrms_addon", "hrms_addon", "cv_screening_rules.py")
for word in protected:
    code = "\n".join(line for line in rules_source.splitlines() if not line.strip().startswith(("#", '"')))
    if re.search(r"\b%s\b" % word, code.split('"""', 2)[-1].lower()):
        fail.append("the screening rules must not take the applicant's %s" % word)
print("fairness: gender, age, marital status, religion and home district never read")

# ── 6. The glue ───────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
applicant_hooks = hooks.split('"Job Applicant": {', 1)[1].split("},", 1)[0]
if '"hrms_addon.hrms_addon.bio_data.validate"' not in applicant_hooks or \
        '"hrms_addon.hrms_addon.cv_screening.applicant_validate"' not in applicant_hooks:
    fail.append("a Job Applicant's CV is read and its answers lined up as it is saved, after its bio-data")
install = hooks.split("after_install = [", 1)[1].split("\n]", 1)[0]
if install.find("cv_screening.set_priority_weights") < install.find("pick_lists.after_install"):
    fail.append("the priorities' weights are set after they are seeded on a new site")
if "hrms_addon.patches.v1_0.screening_priority_weights" not in read("hrms_addon", "patches.txt"):
    fail.append("the priorities' weights are set on the sites already running")
for name in ("Job Opening-custom_screening_section", "Job Opening-custom_pass_mark",
             "Job Opening-custom_screening_questions", "Job Applicant-custom_cv_text",
             "Job Applicant-custom_cv_read_from", "Job Applicant-custom_screening_section",
             "Job Applicant-custom_screening_answers"):
    if '"%s"' % name not in hooks:
        fail.append("%s is not in hooks.py's fixture list, so it is never synced" % name)
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
for name, fieldtype, options in (("Job Opening-custom_screening_questions", "Table", "Screening Question"),
                                 ("Job Applicant-custom_screening_answers", "Table", "Screening Answer"),
                                 ("Job Opening-custom_pass_mark", "Percent", None)):
    row = custom.get(name) or {}
    if row.get("fieldtype") != fieldtype or row.get("options") != options:
        fail.append("%s must be a %s%s" % (name, fieldtype, " of " + options if options else ""))
if (custom.get("Job Opening-custom_pass_mark") or {}).get("default") != "60":
    fail.append("a new opening's pass mark is 60 until HR sets it")
for name in ("Job Applicant-custom_cv_text", "Job Applicant-custom_cv_read_from"):
    if not (custom.get(name) or {}).get("hidden"):
        fail.append("%s is read from the CV and kept out of sight" % name)

reading = body(glue, "cv_text")
for needle, why in (('content[:5] == b"%PDF-"', "a PDF is read"), ('archive.read("word/document.xml")', "a Word file is read"),
                    ("MAX_CV_BYTES", "a file too big is not read"), ("except Exception", "a damaged upload is not a crash")):
    if needle not in reading:
        fail.append("cv_text: %s" % why)
if "reader.pages[:MAX_CV_PAGES]" not in glue:
    fail.append("only a CV's first pages are read")
lining = body(glue, "_line_up_answers")
if "frappe.flags.in_web_form" not in lining or "doc.is_new()" not in lining:
    fail.append("answers are lined up with the opening's questions; on the website every one is answered")

interviews = read("hrms_addon", "hrms_addon", "interviews.py")
if "**cv_screening.screen(doc, context)" not in body(interviews, "candidate_details"):
    fail.append("each candidate on the shortlist is screened")
getting = body(interviews, "get_shortlist_candidates")
for needle, why in (("cv_screening_rules.filter_errors(wanted)", "the filter's refusals stop Get Applicants"),
                    ("cv_screening_rules.filter_candidates(found, wanted)", "Get Applicants keeps what HR's filter keeps"),
                    ('row.pop("search_text", None)', "the text looked through stays on the server"),
                    ('return {"candidates": kept, "left_out": left_out}', "HR is told how many were left out")):
    if needle not in getting:
        fail.append("Get Applicants: %s" % why)
if "sorted(rows, key=sort_key)" not in body(rules_source, "filter_candidates"):
    fail.append("Get Applicants lists the best matches first")
if 'details["search_text"]' not in body(interviews, "candidate_details"):
    fail.append("the filter looks through the bio-data and the CV")
if "_screen_rows(doc)" not in body(interviews, "validate_shortlist") or \
        "(None, screening.DRAFT, screening.RETURNED)" not in body(interviews, "validate_shortlist"):
    fail.append("the candidates are screened again while HR has the list, not once the HOD does")

careers = body(read("hrms_addon", "hrms_addon", "careers.py"), "get_opening_summary")
if '"Screening Question"' not in careers or 'fields=["name", "question", "answer_type"]' not in careers:
    fail.append("the application form gets the opening's questions")
for secret in ("wanted", "minimum", "maximum", "priority"):
    if secret in careers.split('"Screening Question"', 1)[-1]:
        fail.append("the application form must never be told the answers the job needs (%s)" % secret)

form = json.loads(read("hrms_addon", "hrms_addon", "web_form", "job_application_form", "job_application_form.json"))
answers = next((f for f in form["web_form_fields"] if f.get("fieldname") == "custom_screening_answers"), None)
if not answers or answers.get("fieldtype") != "Table" or not answers.get("hidden"):
    fail.append("the application form carries the answers, out of sight until the opening has questions")
form_js = read("hrms_addon", "hrms_addon", "web_form", "job_application_form", "job_application_form.js")
for needle in ("field.df.cannot_add_rows = true", "field.df.cannot_delete_rows = true",
               'set_df_property("custom_screening_answers", "hidden", 0)', "question_id: question.name"):
    if needle not in form_js:
        fail.append("application form: %s" % needle)

shortlist_js = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.js")
for needle in ('fieldtype: "MultiCheck"', 'fieldname: "look_for"', 'fieldname: "min_score"', 'fieldname: "min_years"',
               'fieldname: "limit"', "filters: filters", "found.left_out"):
    if needle not in shortlist_js:
        fail.append("Get Applicants asks for HR's filter: %s" % needle)
if 'frm.add_custom_button(__("Sort by Match"), () => ha_sort_by_match(frm))' not in shortlist_js or \
        '"screening_result", "matched", "missing", "to_check", "flags"' not in shortlist_js:
    fail.append("the shortlist shows the screening and sorts by it")
spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", "screening_question", "screening_question.json"))
if {f["fieldname"] for f in spec["fields"]} != {"question", "answer_type", "wanted", "minimum", "maximum", "priority"}:
    fail.append("a Screening Question: the question, its answer type, the answer wanted and its priority")
if next(f for f in spec["fields"] if f["fieldname"] == "priority").get("default") != "Essential":
    fail.append("a screening question is a must-have unless HR says otherwise")
priority = json.loads(read("hrms_addon", "hrms_addon", "doctype", "jd_requirement_priority",
                           "jd_requirement_priority.json"))
if not {"weight", "must_have"} <= {f["fieldname"] for f in priority["fields"]}:
    fail.append("each priority says what it weighs and whether it is a must-have")
print("glue: hooks, patch, fixtures, the CV reader, the shortlist, the careers form and the scripts")

if fail:
    print("\nFAILED:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("\nALL SCREENING CHECKS PASSED")
