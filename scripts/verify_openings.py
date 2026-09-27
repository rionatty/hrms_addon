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
# advertising: a published, open job needs its job title's job description
if R.advert_errors(1, "Open", "Machine Operator", False) != [
        "Machine Operator has no job description yet. Add it before publishing the job on the website."]:
    fail.append("a job published without a job description is refused, naming the job title")
for publish, status, has_jd in ((1, "Open", True), (0, "Open", False), (1, "Closed", False), ("0", "Open", False)):
    if R.advert_errors(publish, status, "Machine Operator", has_jd):
        fail.append("only an open job published on the website needs the job description (%r, %r, %r)"
                    % (publish, status, has_jd))
# sharing: each network's own share page, the address and the line encoded
url = "https://careers.example.com/jobs/luuka/machine-operator?x=1&y=2"
links = R.share_links(url, "Machine Operator", "Luuka Plastics Limited")
by_network = {link["network"]: link["url"] for link in links}
if [link["network"] for link in links] != list(R.SHARE_NETWORKS):
    fail.append("every network is offered, in order: %s" % [link["network"] for link in links])
encoded = "https%3A%2F%2Fcareers.example.com%2Fjobs%2Fluuka%2Fmachine-operator%3Fx%3D1%26y%3D2"
if by_network.get("LinkedIn") != "https://www.linkedin.com/sharing/share-offsite/?url=" + encoded \
        or by_network.get("Facebook") != "https://www.facebook.com/sharer/sharer.php?u=" + encoded:
    fail.append("LinkedIn and Facebook are given the job's address, encoded whole: %s" % by_network)
if by_network.get("WhatsApp") != ("https://wa.me/?text=Job%20opening%3A%20Machine%20Operator%20at%20Luuka%20Plastics"
                                  "%20Limited%20" + encoded):
    fail.append("WhatsApp is given the job's line and address: %s" % by_network.get("WhatsApp"))
if by_network.get("X") != ("https://twitter.com/intent/tweet?text=Job%20opening%3A%20Machine%20Operator%20at%20Luuka"
                           "%20Plastics%20Limited&url=" + encoded) \
        or by_network.get("Email") != ("mailto:?subject=Job%20opening%3A%20Machine%20Operator%20at%20Luuka%20Plastics"
                                       "%20Limited&body=" + encoded):
    fail.append("X and email carry the line and the address as their own parameters: %s" % by_network)
if R.share_links("", "Machine Operator") or R.share_text("Driver") != "Job opening: Driver" \
        or "&" in R.share_links("https://x.example/j", "R&D Lead", "A & B")[0]["url"].split("?", 1)[1]:
    fail.append("nothing to share without an address, and a title with & in it cannot break a link")
print("the rules: the requisition's blanks, HRMS's route made unique, the JD's questions as rows, the job "
      "description before the advert, the share links")

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
if 'rules.advert_errors(doc.get("publish"), doc.get("status"), doc.get("designation"),\n' \
        '                                 careers.has_job_description(doc.get("designation")))' not in body(glue, "validate"):
    fail.append("validate: the job description is looked for on the opening's own job title")
if not re.search(r"@frappe\.whitelist\(\)\ndef get_share_links\(", glue) \
        or 'frappe.has_permission("Job Opening", "read", job_opening, throw=True)' not in body(glue, "get_share_links"):
    fail.append("get_share_links is whitelisted, for whoever may read the opening")
careers_py = read("hrms_addon", "hrms_addon", "careers.py")
if 'if not job_opening or not job_opening.get("publish") or job_opening.get("status") != "Open":' \
        not in body(careers_py, "job_share_links") \
        or 'if not route or not job_opening.get("publish"):' not in body(careers_py, "share_card") \
        or 'get_url("/" + route.lstrip("/"))' not in body(careers_py, "share_card"):
    fail.append("a job is shared only while published (and on the page, while open), at its own full address")
if "return bool(posting_details_of(frappe.get_doc(\"Designation\", designation)))" \
        not in body(careers_py, "has_job_description"):
    fail.append("a job description is what the careers page could show of it: posting_details_of")
print("glue: the blanks, the JD's questions and a route of its own on save; Create Job Opening with its requisition; "
      "the advert checked; the share links")

# ── 3. Wiring ─────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
if '"before_validate": "hrms_addon.hrms_addon.job_openings.before_validate"' not in hooks.split('"Job Opening": {', 1)[-1][:400]:
    fail.append("hooks.py doc_events must run job_openings.before_validate on Job Opening")
if '"validate": "hrms_addon.hrms_addon.job_openings.validate"' not in hooks.split('"Job Opening": {', 1)[-1][:600]:
    fail.append("hooks.py doc_events must run job_openings.validate on Job Opening")
if '"hrms_addon.hrms_addon.careers.job_share_links",' not in hooks.split("jinja = {", 1)[-1][:600]:
    fail.append("hooks.py jinja methods must offer careers.job_share_links to the job page")
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
if (by_name.get("Designation-custom_jd_medical_section") or {}).get("insert_after") != "custom_jd_screening_questions" \
        or (by_name.get("Designation-custom_jd_signoff_section") or {}).get("insert_after") != "custom_fitness_requirements":
    fail.append("the screening questions, then the medical check before joining, and the sign-off stays last on the JD")
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
         "an answer for a job since changed, or questions since added, is ignored"),
        ('if (!frm.is_new() && frm.doc.publish && frm.doc.status === "Open" && frm.doc.route) {\n\t\t\tha_share_buttons(frm);',
         "Share only on a published, open job"),
        ('window.open(link.url, "_blank", "noopener"), __("Share")', "each network's page from the Share group"),
        ("frappe.utils.copy_to_clipboard(share.url)", "Copy Link copies the job's address")):
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
