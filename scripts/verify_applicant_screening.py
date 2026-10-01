"""Checks for the screening kept on each applicant, the Applicant Screening
report, Remove by Result and the blind first screening, run without a bench.

cv_screening_rules.py imports nothing from Frappe, so it is loaded directly:
the fields kept on the applicant are the shortlist's own columns; Remove by
Result takes the results ticked, and the matches below the one given, never
an applicant nothing could be checked for by their match alone; the
signatures tell a changed job description, pass mark or questions from an
unchanged one. It also checks the glue (kept on every save, screened again in
the background when what they are screened on changes, Set Status for HR and
only for applicants not yet shortlisted or hired), the fields, the report,
the shortlist's form script, and against Frappe (../ERPNext, or
FRAPPE_APPS_ROOT) what the report's buttons and the hidden names rest on.

    python scripts/verify_applicant_screening.py
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


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def function(source, name):
    """A function's or method's text, up to the first line not inside it."""
    start = source.index("def %s(" % name)
    depth = start - (source.rfind(chr(10), 0, start) + 1)
    lines = source[start:].split(chr(10))
    kept = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= depth:
            break
        kept.append(line)
    return chr(10).join(kept)


R = load("cv_screening_rules")
print("loaded cv_screening_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
screened = {"match_score": 73, "screening_result": "Meets", "experience_years": 4, "matched": "a", "missing": "b",
            "to_check": "c", "flags": "d", "education": "not kept"}
if R.stored_values(screened) != {"custom_match_score": 73, "custom_screening_result": "Meets",
                                 "custom_experience_years": 4, "custom_screening_matched": "a",
                                 "custom_screening_missing": "b", "custom_screening_to_check": "c",
                                 "custom_screening_flags": "d"}:
    fail.append("the applicant keeps the shortlist's own screening columns: %s" % R.stored_values(screened))
if R.stored_values({"screening_result": ""})["custom_screening_result"] is not None \
        or set(R.stored_values(None)) != set(R.STORED):
    fail.append("a result nothing could decide is kept blank, and every field is always written")
rows = [
    {"job_applicant": "A", "screening_result": "Meets", "match_score": 90},
    {"job_applicant": "B", "screening_result": "Below Pass Mark", "match_score": 55},
    {"job_applicant": "C", "screening_result": "Does Not Meet", "match_score": 70},
    {"job_applicant": "D", "screening_result": "", "match_score": None},
    {"job_applicant": "E", "screening_result": "Meets", "match_score": 61},
    {"job_applicant": None, "screening_result": "Does Not Meet", "match_score": 10},
]
for results, below, wanted in (
        (["Does Not Meet"], None, ["C"]),
        (["Below Pass Mark", "Does Not Meet"], None, ["B", "C"]),
        ([], 60, ["B"]),
        ([], "65%", ["B", "E"]),
        (["Not Checked"], None, ["D"]),
        (["Does Not Meet"], 60, ["B", "C"]),
        (["Made Up"], None, []),
        ([], None, []),
        ([], 0, [])):
    got = R.removals(rows, results, below)
    if got != wanted:
        fail.append("removals(%r, %r) should take %r, took %r" % (results, below, wanted, got))
jd = ([{"competency": "Welding", "priority": "Essential"}],
      [{"specification_type": "Work Experience", "requirement": "3 years", "keywords": "welder", "minimum_years": 3,
        "priority": "Preferred"}])
if R.jd_signature(*jd) != R.jd_signature([dict(jd[0][0])], [dict(jd[1][0], idx=4, name="x")]):
    fail.append("the JD's signature is what it screens on, not the rows' names or order numbers")
for changed in ([{"competency": "Welding", "priority": "Desirable"}], jd[0] + [{"competency": "Safety"}]):
    if R.jd_signature(changed, jd[1]) == R.jd_signature(*jd):
        fail.append("a competency or its priority changed changes the JD's signature")
if R.jd_signature(jd[0], [dict(jd[1][0], keywords="welder, fabricator")]) == R.jd_signature(*jd) \
        or R.jd_signature(jd[0], [dict(jd[1][0], minimum_years=4)]) == R.jd_signature(*jd):
    fail.append("the words looked for, or the years, changed change the JD's signature")
questions = [{"question": "Night shifts?", "answer_type": "Yes or No", "wanted": "Yes", "priority": "Essential"}]
if R.opening_signature(60, questions) == R.opening_signature(70, questions) \
        or R.opening_signature(60, questions) == R.opening_signature(60, [dict(questions[0], wanted="No")]) \
        or R.opening_signature(60, questions) != R.opening_signature("60", [dict(questions[0], idx=2)]):
    fail.append("an opening's signature is its pass mark and its questions' content")
print("the rules: what is kept, what Remove by Result takes, what counts as a change")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "cv_screening.py")
if "_store(doc)" not in function(glue, "applicant_validate") \
        or "doc.update(rules.stored_values(screen(doc, context_for(doc.job_title))))" not in function(glue, "_store") \
        or "doc.custom_screened_on = now_datetime()" not in function(glue, "_store") \
        or "doc.update(dict.fromkeys(rules.STORED))" not in function(glue, "_store"):
    fail.append("every save keeps the applicant's screening against their opening, or clears it without one")
again = function(glue, "rescreen_opening")
if 'frappe.db.set_value("Job Applicant", name, values, update_modified=False)' not in again \
        or 'filters={"job_title": job_opening}' not in again:
    fail.append("screening again writes straight to the database, for that opening's applicants")
queued = function(glue, "queue_rescreen")
if 'job_id="rescreen-applicants-%s" % job_opening, deduplicate=True, enqueue_after_commit=True' not in queued \
        or 'queue="long"' not in queued:
    fail.append("screening again runs in the background, once per opening however often asked")
for name, needle in (
        ("opening_on_update", "rules.opening_signature(before.get(\"custom_pass_mark\"), before.get(QUESTIONS))"),
        ("designation_on_update", 'filters={"designation": doc.name, "status": "Open"}'),
        ("priority_on_update", '(flt(before.get("weight")), int(before.get("must_have") or 0))')):
    if needle not in function(glue, name) or "queue_rescreen(" not in function(glue, name):
        fail.append("%s: screened again only when what they are screened on changed" % name)
status = function(glue, "set_applicant_status")
for needle, why in (
        ("if status not in SETTABLE_STATUSES:", "only the statuses Set Status gives"),
        ('if not doc.has_permission("write"):', "only applicants HR may change"),
        ("if doc.status in MOVED_ON:", "a shortlisted or hired applicant is left"),
        ("doc.save()", "saved as the form saves it, so the regret email follows HR Settings"),
        ("except frappe.ValidationError as error:", "one refused does not stop the rest"),
        ("frappe.clear_last_message()", "and its message does not pop up after")):
    if needle not in status:
        fail.append("set_applicant_status: %s" % why)
if tuple(re.findall(r'"(\w+)"', glue.split("SETTABLE_STATUSES = ", 1)[1].split(chr(10), 1)[0])) \
        != ("Open", "Replied", "Hold", "Rejected") \
        or tuple(re.findall(r'"(\w+)"', glue.split("MOVED_ON = ", 1)[1].split(chr(10), 1)[0])) != ("Shortlisted", "Accepted"):
    fail.append("Set Status gives Open, Replied, Hold or Rejected, and leaves Shortlisted and Accepted")
for name in ("rescreen", "set_applicant_status"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("%s is whitelisted, POST only" % name)
if 'frappe.has_permission("Job Applicant", "write", throw=True)' not in function(glue, "rescreen"):
    fail.append("Screen Again is for whoever may change applicants")
interviews = read("hrms_addon", "hrms_addon", "interviews.py")
if not re.search(r"@frappe\.whitelist\(\)\ndef pick_removals\(", interviews) \
        or 'frappe.has_permission("Interview Shortlist", "write", throw=True)' not in function(interviews, "pick_removals") \
        or "cv_screening_rules.removals(" not in function(interviews, "pick_removals"):
    fail.append("pick_removals is whitelisted for whoever writes shortlists, and runs the tested rule")
if 'frappe.db.get_single_value("HR Settings", "custom_blind_screening")' not in function(interviews, "hide_names"):
    fail.append("hide_names reads HR Settings")
controller = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.py")
if 'self.set_onload("hide_names", interviews.hide_names())' not in function(controller, "onload"):
    fail.append("the shortlist tells its form whether names are hidden")
hooks = read("hrms_addon", "hooks.py")
for doctype, handler in (("Job Opening", "cv_screening.opening_on_update"),
                         ("Designation", "cv_screening.designation_on_update")):
    block = hooks.split('"%s": {' % doctype, 1)[-1].split("},", 1)[0]
    if '"on_update": "hrms_addon.hrms_addon.%s"' % handler not in block:
        fail.append("hooks.py: %s on_update runs %s" % (doctype, handler))
# a pick list master is never named in hooks.py (verify_job_description.py): its own controller does it
priority = read("hrms_addon", "hrms_addon", "doctype", "jd_requirement_priority", "jd_requirement_priority.py")
if "def on_update(self):\n        cv_screening.priority_on_update(self)" not in priority:
    fail.append("JD Requirement Priority's own on_update screens the open openings again")
patches = read("hrms_addon", "patches.txt")
patch = read("hrms_addon", "patches", "v1_0", "screen_existing_applicants.py")
if "hrms_addon.patches.v1_0.screen_existing_applicants" not in patches.split("[post_model_sync]", 1)[-1]:
    fail.append("the existing applicants' patch runs after the model sync")
body = function(patch, "execute")
if not (0 <= body.find('sync_fixtures("hrms_addon")') < body.find("cv_screening.rescreen_opening(opening)")) \
        or 'filters={"status": "Open"}' not in body or 'if not doc.get("custom_employee"):' not in body \
        or "rules.employee_match(cv_screening.employees_like(doc, limit=5))" not in body:
    fail.append("the patch syncs the fields first, screens the open openings' applicants, links staff HR has not")
print("glue: kept on save, screened again when it changes, Set Status, Remove by Result, hidden names, "
      "the existing applicants")

# ── 3. The fields ─────────────────────────────────────────────────────
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
kinds = {"custom_match_score": "Percent", "custom_screening_result": "Select", "custom_experience_years": "Float",
         "custom_screened_on": "Datetime", "custom_screening_matched": "Small Text",
         "custom_screening_missing": "Small Text", "custom_screening_to_check": "Small Text",
         "custom_screening_flags": "Small Text"}
if set(R.STORED) | {"custom_screened_on"} != set(kinds):
    fail.append("STORED and the Job Applicant's fields differ")
for fieldname, kind in kinds.items():
    row = custom.get("Job Applicant-" + fieldname) or {}
    if row.get("fieldtype") != kind or not (row.get("read_only") and row.get("no_copy")):
        fail.append("Job Applicant.%s is a read-only %s, never copied" % (fieldname, kind))
    if '"Job Applicant-%s",' % fieldname not in hooks:
        fail.append("hooks.py fixtures must list Job Applicant-%s" % fieldname)
result = custom.get("Job Applicant-custom_screening_result") or {}
if (result.get("options") or "").split(chr(10)) != [""] + list(R.RESULTS) or not result.get("in_standard_filter"):
    fail.append("the Result is one of the screening's results, and the applicant list filters by it")
if not (custom.get("Job Applicant-custom_match_score") or {}).get("in_list_view"):
    fail.append("the Match shows on the applicant list")
blind = custom.get("HR Settings-custom_blind_screening") or {}
if blind.get("fieldtype") != "Check" or blind.get("insert_after") != "custom_applicant_screening_section" \
        or (custom.get("HR Settings-custom_letters_section") or {}).get("insert_after") != "custom_blind_screening":
    fail.append("HR Settings has Hide Names While HR Screens, in its own section before the letters")
print("fields: the screening on the applicant, read-only and filterable; the setting")

# ── 4. The report ─────────────────────────────────────────────────────
base = os.path.join("hrms_addon", "hrms_addon", "report", "applicant_screening")
spec = json.loads(read(base, "applicant_screening.json"))
if (spec.get("name"), spec.get("report_type"), spec.get("ref_doctype"), spec.get("is_standard"), spec.get("module")) \
        != ("Applicant Screening", "Script Report", "Job Applicant", "Yes", "HRMS Addon") \
        or {row["role"] for row in spec.get("roles", [])} != {"HR User", "HR Manager", "System Manager"}:
    fail.append("Applicant Screening is HR's standard Script Report on Job Applicant")
if not os.path.exists(os.path.join(REPO, base, "__init__.py")):
    fail.append("Applicant Screening needs its __init__.py")
py = read(base, "applicant_screening.py")
js = read(base, "applicant_screening.js")
for needle, why in (
        ("data.sort(key=rules.sort_key)", "the best first, as the shortlist sorts"),
        ('"match_score": None if result == rules.NOT_CHECKED else row.get("custom_match_score")',
         "no match for an applicant nothing could be checked for (the database keeps a nought)"),
        ('opened = frappe.get_all("Job Opening", filters={"status": "Open"}, pluck="name")',
         "without an opening, the open ones"),
        ("return columns(), data, None, None, summary", "the count of each result on top")):
    if needle not in py:
        fail.append("Applicant Screening: %s" % why)
fields_read = re.findall(r'"(custom_\w+)"', py.split("FIELDS = ", 1)[1].split(chr(10) * 2, 1)[0])
for fieldname in fields_read:
    if "Job Applicant-" + fieldname not in custom:
        fail.append("Applicant Screening reads Job Applicant.%s, which does not exist" % fieldname)
declared = set(re.findall(r'fieldname: "(\w+)"', js))
for used in set(re.findall(r'filters\.get\("(\w+)"\)', py)):
    if used not in declared:
        fail.append("Applicant Screening reads the filter %s, which its script does not offer" % used)
columns = re.findall(r'\{"fieldname": "(\w+)"', function(py, "columns"))
given = set(re.findall(r'^\s+"(\w+)": ', function(py, "screening_line"), re.M))
if not set(columns) <= given or len(columns) != len(set(columns)):
    fail.append("Applicant Screening shows each column once, from its lines: %s" % sorted(set(columns) - given))
for needle, why in (
        ('frappe.query_reports["Applicant Screening"] = {', "registered by its name"),
        ("return Object.assign(options, { checkboxColumn: true });", "rows can be ticked"),
        ("frappe.query_report\n\t\t.get_checked_items()", "Set Status works on the ticked rows"),
        ('HA_SCREENING + "set_applicant_status", { applicants: ticked, status: values.status }', "Set Status"),
        ('options: ["Open", "Replied", "Hold", "Rejected"],', "the statuses the server gives"),
        ('HA_SCREENING + "rescreen", { job_opening: opening }', "Screen Again, for the opening chosen"),
        ('if (!opening) {', "Screen Again needs the opening")):
    if needle not in js:
        fail.append("applicant_screening.js: %s" % why)
print("report: the kept screening, the best first, ticked rows set in one go, an opening screened again")

# ── 5. The shortlist's form ───────────────────────────────────────────
form = read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist", "interview_shortlist.js")
for needle, why in (
        ('frm.add_custom_button(__("Remove by Result"), () => ha_remove_by_result(frm));', "Remove by Result"),
        ('const args = { rows: rows, results: values.results || [] };', "the server is sent the list and the results"),
        ('.xcall(HA_SHORTLIST_METHODS + "pick_removals", args)', "the server picks who goes"),
        ("frappe.confirm(__(\"Remove {0} applicants from the list?\", [names.length]), () => {", "HR confirms"),
        (".forEach((row) => frappe.model.clear_doc(row.doctype, row.name));", "rows removed as Frappe removes them"),
        ("frm.dirty();", "the change waits for Save"),
        ('const HA_NAME_FIELDS = ["applicant_name", "phone_number", "email_id"];', "the names and contacts"),
        ("ha_hide_names(frm, !!(frm.doc.__onload && frm.doc.__onload.hide_names) && with_hr && frm.doc.docstatus === 0);",
         "hidden only while HR screens"),
        ('frappe.meta.get_docfield("Interview Shortlist Candidate", field, frm.doc.name);', "this form's own columns"),
        ("grid.reset_grid();", "the grid drawn again")):
    if needle not in form:
        fail.append("interview_shortlist.js: %s" % why)
candidate = {f["fieldname"] for f in json.loads(read("hrms_addon", "hrms_addon", "doctype", "interview_shortlist_candidate",
                                                        "interview_shortlist_candidate.json"))["fields"]}
for fieldname in ("applicant_name", "phone_number", "email_id", "job_applicant", "screening_result", "match_score"):
    if fieldname not in candidate:
        fail.append("Interview Shortlist Candidate has no %s" % fieldname)
print("shortlist: Remove by Result, names hidden while HR screens")

# ── 6. What Frappe must still do ──────────────────────────────────────
if UPSTREAM_OK:
    grid = upstream("frappe", "public", "js", "frappe", "form", "grid.js")
    if "reset_grid() {\n\t\tthis.visible_columns = [];" not in grid \
            or "this.docfields = frappe.meta.get_docfields(this.doctype, this.frm.docname);" not in grid \
            or "!df.hidden &&" not in grid:
        fail.append("Frappe's grid draws its columns differently now: recheck the hidden names")
    report = upstream("frappe", "public", "js", "frappe", "views", "reports", "query_report.js")
    if "get_checked_items(only_docnames) {" not in report:
        fail.append("Frappe's query report has no get_checked_items: recheck Set Status")
    jobs = upstream("frappe", "utils", "background_jobs.py")
    if "deduplicate=False," not in jobs:
        fail.append("frappe.enqueue no longer de-duplicates: recheck queue_rescreen")
    applicant = json.loads(upstream("hrms", "hr", "doctype", "job_applicant", "job_applicant.json"))
    options = next((f.get("options") or "" for f in applicant["fields"] if f["fieldname"] == "status"), "")
    wanted = set(("Open", "Replied", "Hold", "Rejected", "Shortlisted", "Accepted"))
    if not wanted <= set(options.split(chr(10))):
        fail.append("Frappe HR's applicant statuses changed: recheck Set Status")
    if applicant.get("show_title_field_in_link"):
        fail.append("Frappe HR now shows the applicant's name in links: hiding names must hide the link too")
    upstream_note = "checked against Frappe and Frappe HR"
else:
    upstream_note = "Frappe not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL APPLICANT SCREENING CHECKS PASSED")
