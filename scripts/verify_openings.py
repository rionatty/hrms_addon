"""Verify the Job Opening's own rules, without a bench:

    python scripts/verify_openings.py

  1  the rules: what an opening takes from its Job Requisition, the route of
     its careers page, the JD's screening questions as its rows
  2  the glue: before_validate, Create Job Opening, the form's two calls
  3  wiring: hooks, the JD's Screening Questions, the form script

HRMS's own fields are read from FRAPPE_APPS_ROOT (default ../ERPNext).
"""
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def body(source, name):
    return source.split("def %s(" % name)[1].split("\ndef ")[0] if "def %s(" % name in source else ""


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    hits = glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "doctype", folder, folder + ".json"), recursive=True)
    return json.load(open(hits[0], encoding="utf-8")) if hits else None


R = load("opening_rules")
print("loaded opening_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
requisition = {"designation": "Machine Operator", "department": "Production - LPL", "no_of_positions": 3,
               "description": "<p>Operate the injection moulding machines.</p>", "custom_reason_type": "Replacement",
               "custom_reporting_line": "Production Supervisor", "custom_subordinates": "",
               "custom_head_hunt": 1, "custom_external_advert": 0}
got = R.blanks_from({"job_title": "", "vacancies": 0, "description": "<p><br></p>"}, requisition)
if got != {"job_title": "Machine Operator", "designation": "Machine Operator", "department": "Production - LPL",
           "vacancies": 3, "description": "<p>Operate the injection moulding machines.</p>",
           "custom_reason_type": "Replacement", "custom_reporting_line": "Production Supervisor",
           "custom_head_hunt": 1}:
    fail.append("a blank opening takes what its requisition says, the modes it ticks among them: %s" % got)
got = R.blanks_from({"job_title": "Operator, Kawempe", "vacancies": 5, "description": "<p>Our own words.</p>",
                     "custom_internal_advert": 1}, requisition)
if set(got) & {"job_title", "vacancies", "description", "custom_head_hunt", "custom_internal_advert"}:
    fail.append("what the opening says itself is kept, its modes of recruitment together: %s" % got)
if R.blanks_from({}, {}) != {}:
    fail.append("a requisition that says nothing gives nothing")
if R.route_for("Luuka Plastics Limited", "Machine Operator (Kawempe)") != "jobs/luuka_plastics_limited/machine-operator-(kawempe)":
    fail.append("the route is HRMS's: jobs/<company>/<job-title>: %s" % R.route_for("Luuka Plastics Limited",
                                                                                  "Machine Operator (Kawempe)"))
for taken, wanted in (([], "jobs/luuka/machine-operator"), (["jobs/luuka/machine-operator"], "jobs/luuka/machine-operator-2"),
                      (["jobs/luuka/machine-operator", "jobs/luuka/machine-operator-2"], "jobs/luuka/machine-operator-3"),
                      (["jobs/luuka/machine-operator-2"], "jobs/luuka/machine-operator")):
    if R.unique_route("jobs/luuka/machine-operator", taken) != wanted:
        fail.append("route taken by %s: expected %s, got %s" % (taken, wanted, R.unique_route("jobs/luuka/machine-operator",
                                                                                            taken)))
rows = R.question_rows([{"question": "Can you work night shifts?", "answer_type": "Yes or No", "wanted": "Yes",
                         "priority": "Essential", "name": "row-1", "parent": "Machine Operator", "idx": 1},
                        {"question": ""}])
if rows != [{"question": "Can you work night shifts?", "answer_type": "Yes or No", "wanted": "Yes", "minimum": None,
             "maximum": None, "priority": "Essential"}]:
    fail.append("the JD's questions become an opening's rows, their own columns only: %s" % rows)
question = json.load(open(os.path.join(APP, "doctype", "screening_question", "screening_question.json"), encoding="utf-8"))
if tuple(f["fieldname"] for f in question["fields"] if f["fieldtype"] not in ("Column Break", "Section Break")) \
        != R.QUESTION_FIELDS:
    fail.append("QUESTION_FIELDS must be exactly a Screening Question's columns")
print("the rules: the requisition's blanks, HRMS's route made unique, the JD's questions as rows")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "job_openings.py")
custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
custom_of = {}
for row in custom:
    custom_of.setdefault(row["dt"], set()).add(row["fieldname"])
opening_json, requisition_json = upstream_doctype("Job Opening"), upstream_doctype("Job Requisition")
if opening_json and requisition_json:
    opening_fields = {f["fieldname"] for f in opening_json["fields"]} | custom_of.get("Job Opening", set())
    requisition_fields = {f["fieldname"] for f in requisition_json["fields"]} | custom_of.get("Job Requisition", set())
    for target, source in list(R.FROM_REQUISITION.items()) + [(mode, mode) for mode in R.MODES]:
        if target not in opening_fields or source not in requisition_fields:
            fail.append("Job Opening.%s from Job Requisition.%s: a field that does not exist" % (target, source))
    hrms_opening = open(glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "doctype", "job_opening",
                                               "job_opening.py"), recursive=True)[0], encoding="utf-8").read()
    if """self.route = f"jobs/{frappe.scrub(self.company)}/{frappe.scrub(self.job_title).replace('_', '-')}\"""" \
            not in hrms_opening:
        fail.append("HRMS builds an opening's route differently now: recheck opening_rules.route_for")
    hrms_requisition = open(glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "doctype", "job_requisition",
                                                   "job_requisition.py"), recursive=True)[0], encoding="utf-8").read()
    if "def make_job_opening(" not in hrms_requisition:
        fail.append("HRMS has no make_job_opening to build on")
for needle, why in (
        ("    for field, value in requisition_values(doc).items():\n        doc.set(field, value)\n"
         "    _add_jd_questions(doc)\n    _unique_route(doc)", "before_validate: the blanks, the questions, the route"),
        ("rules.blanks_from(doc.as_dict(), frappe.get_doc(\"Job Requisition\", name).as_dict(), _has_content)",
         "the blanks from the requisition, an editor's empty paragraph blank"),
        ('rules.question_rows(frappe.get_doc("Designation", designation).get("custom_jd_screening_questions"))',
         "the JD's screening questions"),
        ('if doc.get("designation") and not doc.get(QUESTIONS):', "only an opening with none takes the JD's"),
        ('rules.route_for(doc.get("company"), doc.get("job_title"))', "HRMS's route when the opening has none"),
        ('filters={"name": ["!=", doc.name or ""]}', "the routes of the other openings"),
        ("doc.route = rules.unique_route(route, taken)", "a route no other opening has")):
    if needle not in glue:
        fail.append("job_openings.py: %s" % why)
making = body(glue, "make_job_opening")
for needle in ("hrms_make_job_opening(source_name, target_doc)", "opening.job_requisition = source_name",
               "requisition_values(opening)", "_add_jd_questions(opening)"):
    if needle not in making:
        fail.append("make_job_opening: %s" % needle)
for name in ("make_job_opening", "get_requisition_values", "get_jd_questions"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("%s must be whitelisted" % name)
for name in ("get_requisition_values", "get_jd_questions"):
    if 'frappe.has_permission("Job Opening", "write", throw=True)' not in body(glue, name):
        fail.append("%s is for whoever may write openings" % name)
print("glue: the blanks, the JD's questions and a route of its own on save; Create Job Opening with its requisition")

# ── 3. Wiring ─────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
if '"before_validate": "hrms_addon.hrms_addon.job_openings.before_validate"' not in hooks.split('"Job Opening": {', 1)[-1][:400]:
    fail.append("hooks.py doc_events must run job_openings.before_validate on Job Opening")
if '"hrms.hr.doctype.job_requisition.job_requisition.make_job_opening": (\n        "hrms_addon.hrms_addon.job_openings.make_job_opening"' \
        not in hooks:
    fail.append("hooks.py must route Create Job Opening through job_openings.make_job_opening")
if '"Job Opening": "public/js/job_opening.js",' not in hooks or not os.path.exists(
        os.path.join(REPO, "hrms_addon", "public", "js", "job_opening.js")):
    fail.append("the Job Opening form script is loaded")
by_name = {row["name"]: row for row in custom}
table = by_name.get("Designation-custom_jd_screening_questions") or {}
if (table.get("fieldtype"), table.get("options"), table.get("allow_bulk_edit"), table.get("insert_after")) \
        != ("Table", "Screening Question", 1, "custom_jd_screening_section"):
    fail.append("the JD carries its screening questions, with Download and Upload: %s" % table)
if (by_name.get("Designation-custom_jd_signoff_section") or {}).get("insert_after") != "custom_jd_screening_questions":
    fail.append("the sign-off stays last on the JD")
for name in ("Designation-custom_jd_screening_section", "Designation-custom_jd_screening_questions"):
    if '"%s",' % name not in hooks:
        fail.append("hooks.py fixtures must list %s" % name)
js = read("hrms_addon", "public", "js", "job_opening.js")
for method in re.findall(r'HA_OPENINGS \+ "(\w+)"', js):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % method, glue):
        fail.append("job_opening.js calls %s, which is not whitelisted" % method)
for needle, why in (
        ("if (!frm.is_new()) {\n\t\t\treturn;", "only a new opening is filled"),
        ("if (frm.doc.job_requisition) {\n\t\t\tha_fill_from_requisition(frm);", "a new opening with a requisition"),
        ('frappe.xcall(HA_OPENINGS + "get_requisition_values", { doc: frm.doc })', "from its requisition"),
        ("if (frm.doc.designation && !(frm.doc.custom_screening_questions || []).length) {",
         "the JD's questions only when it has none"),
        ("if (frm.doc.designation !== designation || (frm.doc.custom_screening_questions || []).length) {",
         "an answer for a job since changed, or questions since added, is ignored")):
    if needle not in js:
        fail.append("job_opening.js: %s" % why)
print("wiring: the hook, Create Job Opening, the JD's questions table, the form script")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL JOB OPENING CHECKS PASSED")
