"""Checks for the careers portal, run without a bench: the Job Opening page
(templates/generators/job_opening.html), the Job Application Form web form
(/apply) and their shared stylesheet.

  * the page template really overrides HRMS's (same path), links the
    stylesheet, sends Apply to the opening's route or /apply, escapes what it
    prints, and shows Job Description parts only through job_posting_details;
  * jd_rules.posting_details lets out only candidate-facing parts
    (behaviour, with LPL/JD/SM/001-style rows);
  * every field of the web form exists on Job Applicant with the same type
    and options, the only mandatory fields are on step 1, and every value a
    candidate picks comes from a list that is seeded (a candidate cannot add
    to a list);
  * the form's script has no Jinja delimiters (Frappe renders it through
    Jinja) and calls the guest-safe summary method, which only describes
    published openings;
  * the stylesheet defines every variable it uses;
  * every file a guest or portal user uploads is stored private (uploads.py,
    in front of Frappe's upload_file), and the form's upload dialog starts
    private with no Private box to untick (checked against Frappe's upload
    code when the upstream apps are checked out).

    python scripts/verify_careers.py
"""
import ast
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
FORM_DIR = os.path.join(APP, "web_form", "job_application_form")
fail = []


def read(path):
    return open(path, encoding="utf-8").read()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jd_rules = load("jd_rules", os.path.join(APP, "jd_rules.py"))
bio_rules = load("bio_data_rules", os.path.join(APP, "bio_data_rules.py"))
print("loaded jd_rules.py and bio_data_rules.py without Frappe")

# ── 1. Job Opening page template ─────────────────────────────────────
template_path = os.path.join(REPO, "hrms_addon", "templates", "generators", "job_opening.html")
template = read(template_path)
upstream_template = os.path.join(APPS_ROOT, "hrms", "hrms", "templates", "generators", "job_opening.html")
if os.path.isdir(APPS_ROOT) and not os.path.exists(upstream_template):
    fail.append("HRMS no longer has templates/generators/job_opening.html: this override no longer replaces anything")
upstream_py = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "job_opening", "job_opening.py")
if os.path.exists(upstream_py) and 'template="templates/generators/job_opening.html"' not in read(upstream_py):
    fail.append("Job Opening no longer renders templates/generators/job_opening.html upstream")
if not template.lstrip().startswith("{#") or '{% extends "templates/web.html" %}' not in template:
    fail.append("the page template must extend templates/web.html like HRMS's")
for block in ("style", "page_content"):
    if not re.search(r"{%%-?\s*block %s\s*-?%%}" % block, template):
        fail.append("the page template must fill the %s block" % block)
if "{{ super() }}" not in template.split("{% block style %}")[-1].split("{% endblock %}")[0]:
    fail.append("the style block must keep Frappe's own styles ({{ super() }})")
css_link = re.search(r'href="(/assets/hrms_addon/css/careers\.css)\?v=\d+"', template)
if not css_link:
    fail.append("the page template must link /assets/hrms_addon/css/careers.css with a ?v= cache buster")
for opened, closed in (("{%", "%}"), ("{{", "}}")):
    if template.count(opened) != template.count(closed):
        fail.append("page template: unbalanced %s %s" % (opened, closed))
for tag in ("if", "for", "macro", "block"):
    if len(re.findall(r"{%-?\s*" + tag + r"\b", template)) != len(re.findall(r"{%-?\s*end" + tag + r"\b", template)):
        fail.append("page template: every {%% %s %%} needs its {%% end%s %%}" % (tag, tag))
if '"/" ~ (job_application_route or "apply") ~ "/new?job_title=" ~ (name | urlencode)' not in template:
    fail.append("Apply must go to the opening's Application Web Form Route, or /apply, with the opening name encoded")
if template.count("{{ apply_url }}") < 3:
    fail.append("the hero, the overview card and the mobile bar must all link to apply_url")
for variable in ("job_title", "company", "location", "department", "employment_type"):
    for printed in re.findall(r"{{\s*" + variable + r"\b([^}]*)}}", template):
        if "| e" not in printed:
            fail.append("page template prints %s without escaping it" % variable)
if 'job_posting_details(doc) if doc.get("custom_show_job_description") else {}' not in template:
    fail.append("the Job Description may only come from job_posting_details, and only when the opening allows it")
for part in re.findall(r"\bjd\.([a-z_]+)", template):
    if part not in jd_rules.POSTING_PARTS:
        fail.append("page template reads jd.%s, which job_posting_details never returns" % part)
code = re.sub(r"{#.*?#}", "", template, flags=re.S)  # the header comment may name what stays out
for unsafe in ("group.items", "weighting", "perspective", "reporting", "stakeholder", "custom_jd_"):
    if unsafe in code:
        fail.append("page template must not touch %r (internal JD parts, or a dict method instead of a key)" % unsafe)
if os.path.isdir(APPS_ROOT):
    opening = json.load(open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "job_opening", "job_opening.json"), encoding="utf-8"))
    opening_fields = {f["fieldname"] for f in opening["fields"]}
    custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
    opening_fields |= {f["fieldname"] for f in custom if f["dt"] == "Job Opening"}
    context_only = {"doc", "name", "posted_on", "no_of_applications", "status", "frappe", "_", "none", "loop"}
    stripped = re.sub(r'"[^"]*"|\'[^\']*\'', "", "".join(re.findall(r"{[{%](.*?)[}%]}", code, re.S)))
    local = set(re.findall(r"\bset\s+([a-z_]+)\s*=", stripped)) | set(re.findall(r"\bfor\s+([a-z_]+)\s+in\b", stripped))
    local |= set(re.findall(r"\bblock\s+([a-z_]+)", stripped))
    local |= set(re.findall(r"\bmacro\s+([a-z_]+)", stripped))
    local |= {"icon", "super", "urlencode", "lower", "e", "replace", "join", "format", "tojson"}
    words = set(re.findall(r"(?<![\.\w])([a-z_][a-z0-9_]*)\b", stripped)) - {"if", "else", "elif", "endif", "for", "in",
                "endfor", "not", "and", "or", "is", "set", "block", "endblock", "extends", "macro", "endmacro"}
    unknown = sorted(w for w in words - local - context_only
                     if w not in opening_fields and w not in ("job_posting_details", "job_share_links"))
    if unknown:
        fail.append("page template uses %s, which is neither a Job Opening field nor set in the template" % unknown)
# the Share card and the preview the networks show
meta = template.split("{% block meta_block %}", 1)[-1].split("{% endblock %}", 1)[0] \
    if "{% block meta_block %}" in template else ""
if "{{ super() }}" not in meta or "job_share_links(doc)" not in meta \
        or '<meta property="og:url" content="{{ share.url | e }}">' not in meta \
        or '<meta property="og:image" content="{{ share.image | e }}">' not in meta:
    fail.append("the page keeps Frappe's meta tags and adds the job's address and the logo for the networks' preview")
card = template.split("{%- set share = job_share_links(doc) %}")[-1].split("</section>", 1)[0]
if template.count("job_share_links(doc)") != 2 or "{%- if share %}" not in card \
        or "{%- for link in share.links %}" not in card or 'href="{{ link.url | e }}"' not in card:
    fail.append("the Share card lists job_share_links' own links, and only when it returns any")
if '{%- if not link.url.startswith("mailto:") %} target="_blank" rel="noopener noreferrer"{% endif %}' not in card:
    fail.append("a network's page opens in a new tab; the email link does not")
if 'class="lpl-share__link lpl-share__copy" data-url="{{ share.url | e }}"' not in card:
    fail.append("Copy Link copies the job's own address")
script = template.split("{% block script %}", 1)[-1] if "{% block script %}" in template else ""
if "{{ super() }}" not in script or '{{ _("Link Copied") | tojson }}' not in script \
        or "navigator.clipboard && window.isSecureContext" not in script or 'document.execCommand("copy")' not in script:
    fail.append("Copy Link keeps Frappe's scripts, and works on a site served without https too")
print("Job Opening page: overrides HRMS's template, links the stylesheet, escapes fields, internal JD parts stay out, "
      "a Share card")

# ── 2. What the page may show from a Job Description ─────────────────
details = jd_rules.posting_details(
    purpose="  Lead group sales.\n",
    key_result_areas=[
        {"kra": "Sales Revenue", "perspective": "Financial", "weighting": 25,
         "key_outputs": "• Achieve group sales targets\n• Grow key accounts"},
        {"kra": "Key Accounts", "perspective": "Customer / Stakeholder", "weighting": 20,
         "key_outputs": "grow key  accounts\nZero unresolved complaints"},
    ],
    specifications=[
        {"specification_type": "Work Experience", "requirement": "Minimum 8 years in sales", "priority": "Essential"},
        {"specification_type": "Academic Qualification", "requirement": "Bachelor's Degree in Commerce"},
        {"specification_type": "Driving Permit", "requirement": "Class B"},
        {"specification_type": "Academic Qualification", "requirement": "   "},
    ],
    competencies=[
        {"category": "Behavioural", "competency": "Negotiation and persuasion"},
        {"category": "Technical", "competency": "Key account management"},
    ],
    specification_order=["Academic Qualification", "Professional Training & Certification", "Work Experience"],
    category_order=["Technical", "Behavioural"],
)
if set(details) != set(jd_rules.POSTING_PARTS):
    fail.append("posting_details must return exactly %s, returned %s" % (jd_rules.POSTING_PARTS, sorted(details)))
if details.get("purpose") != "Lead group sales.":
    fail.append("posting_details purpose must be trimmed: %r" % details.get("purpose"))
if details.get("responsibilities") != ["Achieve group sales targets", "Grow key accounts", "Zero unresolved complaints"]:
    fail.append("responsibilities must be every key output line once, bullets off: %s" % details.get("responsibilities"))
if [(g["title"], [i["text"] for i in g["items"]]) for g in details.get("requirements", [])] != [
        ("Academic Qualification", ["Bachelor's Degree in Commerce"]), ("Work Experience", ["Minimum 8 years in sales"]),
        ("Driving Permit", ["Class B"])]:
    fail.append("requirements must follow the masters' order, then unlisted types, blank rows out: %s" % details.get("requirements"))
if [(g["title"], g["items"]) for g in details.get("competencies", [])] != [
        ("Technical", ["Key account management"]), ("Behavioural", ["Negotiation and persuasion"])]:
    fail.append("competencies must be grouped in the categories' order: %s" % details.get("competencies"))
if "Essential" not in json.dumps(details["requirements"]):
    fail.append("a requirement's priority must be kept for the page's Essential / Desirable pill")
if any(key in json.dumps(details) for key in ("Financial", "25", "Sales Revenue")):
    fail.append("KRA names, perspectives and weightings must not reach the careers page")
if jd_rules.posting_details() != {} or jd_rules.posting_details(purpose="  ", key_result_areas=[{"key_outputs": ""}]) != {}:
    fail.append("a Job Title with nothing to show must give {} so the page shows its fallback")

careers = read(os.path.join(APP, "careers.py"))
if not re.search(r"^def job_posting_details\(job_opening\):", careers, re.M) or "jd_rules.posting_details(" not in careers:
    fail.append("careers.job_posting_details must use jd_rules.posting_details")
if not re.search(r"@frappe\.whitelist\(allow_guest=True\)\ndef get_opening_summary\(job_opening\):", careers):
    fail.append("careers.get_opening_summary must be whitelisted for guests: candidates are not logged in")
if '{"name": job_opening, "publish": 1}' not in careers:
    fail.append("get_opening_summary must only describe published openings")
hooks_src = read(os.path.join(REPO, "hrms_addon", "hooks.py"))
hooks = {n.targets[0].id: n.value for n in ast.parse(hooks_src).body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
jinja = ast.literal_eval(hooks["jinja"]) if "jinja" in hooks else {}
if "hrms_addon.hrms_addon.careers.job_posting_details" not in (jinja.get("methods") or []):
    fail.append("hooks.jinja methods must include hrms_addon.hrms_addon.careers.job_posting_details")
custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
show = next((f for f in custom if f["name"] == "Job Opening-custom_show_job_description"), {})
if (show.get("fieldtype"), show.get("default"), show.get("depends_on")) != ("Check", "1", "publish"):
    fail.append("Job Opening.custom_show_job_description must be a Check, ticked by default, shown for published openings")
print("posting details: candidate-facing parts only, ordered like the masters, wired as a Jinja method")

# ── 3. Job Application Form (/apply) ─────────────────────────────────
form = json.load(open(os.path.join(FORM_DIR, "job_application_form.json"), encoding="utf-8"))
if (form.get("name"), form.get("route"), form.get("doc_type"), form.get("module"), form.get("is_standard"), form.get("published"),
        form.get("login_required")) != ("job-application-form", "apply", "Job Applicant", "HRMS Addon", 1, 1, 0):
    fail.append("the web form must be the standard, published, guest Job Applicant form job-application-form at /apply")
if form.get("allow_edit") or form.get("show_list") or form.get("allow_multiple") or form.get("allow_comments"):
    fail.append("candidates must not list, edit or comment on applications")
if os.path.isdir(APPS_ROOT):
    hrms_form = json.load(open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "web_form", "job_application", "job_application.json"), encoding="utf-8"))
    if form["route"] == hrms_form["route"] or form["name"] == hrms_form["name"]:
        fail.append("the form must not take HRMS's job_application name or route")
    if os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "www", form["route"])):
        fail.append("route /%s is already a page in HRMS" % form["route"])

applicant = {}
if os.path.isdir(APPS_ROOT):
    ja = json.load(open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "job_applicant", "job_applicant.json"), encoding="utf-8"))
    applicant = {f["fieldname"]: f for f in ja["fields"]}
applicant.update({f["fieldname"]: f for f in custom if f["dt"] == "Job Applicant"})
rows = form["web_form_fields"]
pages, page = [[]], 0
for row in rows:
    if row["fieldtype"] == "Page Break":
        pages.append([])
        page += 1
        continue
    if row["fieldtype"] in ("Section Break", "Column Break"):
        continue
    pages[page].append(row)
    meta = applicant.get(row.get("fieldname"))
    if not meta:
        fail.append("web form field %s is not a Job Applicant field" % row.get("fieldname"))
        continue
    if row["fieldname"] == "job_title":
        if not row.get("read_only"):
            fail.append("job_title must be read-only: it comes from the page the candidate applied from")
        continue
    if (row["fieldtype"], row.get("options") or None) != (meta["fieldtype"], meta.get("options") or None):
        fail.append("web form field %s is %s %r, Job Applicant has %s %r"
                    % (row["fieldname"], row["fieldtype"], row.get("options"), meta["fieldtype"], meta.get("options")))
# Oct 2026, Luuka: the phone, the CV and the cover letter are required; the
# personal information is not asked (it is taken at onboarding)
if len(pages) != 3 or [p for p in pages if not p]:
    fail.append("the form must have 3 non-empty steps (application, education, skills), has %d" % len(pages))
REQUIRED = ["applicant_name", "cover_letter", "email_id", "phone_number", "resume_attachment"]
mandatory = sorted(row["fieldname"] for p in pages for row in p if row.get("reqd"))
first_page_mandatory = sorted(row["fieldname"] for row in pages[0] if row.get("reqd"))
if mandatory != REQUIRED or first_page_mandatory != mandatory:
    fail.append("the name, email, phone, CV and cover letter are required, all on step 1: %s" % mandatory)
if "resume_link" in {row.get("fieldname") for row in rows}:
    fail.append("the CV is the file itself: the form no longer asks for a link to one")
# Family details (parents, next of kin) are collected at onboarding, on the
# applicant's Bio-Data tab, not asked of every candidate on the portal
ONBOARDING_ONLY = {"custom_parents", "custom_next_of_kin"}
# The Branch is the Job Opening's (fetched, read-only): never asked
FROM_THE_OPENING = {"custom_branch"}
# Read from the uploaded CV: never asked
FROM_THE_CV = {"custom_cv_text", "custom_cv_read_from"}
# No longer asked of candidates (A'Level and O'Level results), and since
# Oct 2026 none of the personal information: it is taken at onboarding
NOT_ASKED = {"custom_school_results", "custom_date_of_birth", "custom_gender", "custom_marital_status",
             "custom_no_of_children", "custom_citizenship", "custom_nin", "custom_nssf_no", "custom_tin",
             "custom_home_village", "custom_home_district", "custom_current_residence", "custom_current_district",
             "custom_health_issues"}
# Written by the system (when the regret email went, the screening kept on
# the applicant, the employee record of a member of staff applying): never
# asked
BY_THE_SYSTEM = {"custom_regret_sent_on", "custom_match_score", "custom_screening_result", "custom_experience_years",
                 "custom_screened_on", "custom_screening_matched", "custom_screening_missing",
                 "custom_screening_to_check", "custom_screening_flags", "custom_employee"}
if BY_THE_SYSTEM & {row.get("fieldname") for row in rows}:
    fail.append("the portal must not ask %s" % sorted(BY_THE_SYSTEM))
if NOT_ASKED & {row.get("fieldname") for row in rows}:
    fail.append("the form no longer asks for %s" % sorted(NOT_ASKED))
bio_fields = {fn for fn, f in applicant.items()
              if fn.startswith("custom_") and f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")
              and fn not in ("custom_bio_data_date", "custom_signed_bio_data")}
on_form = {row.get("fieldname") for row in rows}
missing = sorted(bio_fields - on_form - ONBOARDING_ONLY - FROM_THE_OPENING - FROM_THE_CV - NOT_ASKED - BY_THE_SYSTEM)
if missing:
    fail.append("Bio-Data fields missing from the online form: %s" % missing)
if FROM_THE_OPENING & on_form:
    fail.append("the Branch comes from the Job Opening applied for; the portal must not ask it: %s"
                % sorted(FROM_THE_OPENING & on_form))
if (applicant.get("custom_branch") or {}).get("fetch_from") != "job_title.location" \
        or not (applicant.get("custom_branch") or {}).get("read_only"):
    fail.append("Job Applicant.custom_branch must be read-only, fetched from the Job Opening's Branch (job_title.location)")
if ONBOARDING_ONLY & on_form:
    fail.append("family details are collected at onboarding, not on the portal: %s" % sorted(ONBOARDING_ONLY & on_form))
if not ONBOARDING_ONLY <= set(applicant):
    fail.append("the family tables HR fills at onboarding must stay on Job Applicant: %s" % sorted(ONBOARDING_ONLY - set(applicant)))
if "custom_signed_bio_data" in on_form or "custom_bio_data_date" in on_form:
    fail.append("the signature date and signed scan belong to the paper form, not the online one")

# every value a candidate picks must come from a list that has values
seeded = {master: seeds for master, (_, seeds) in bio_rules.BIO_DATA_MASTERS.items()}
framework_lists = {"Country", "Gender", "Currency"}  # Frappe ships these filled
hr_lists = {"Job Applicant Source", "Skill"}  # HR fills these before going live
linked = []
for row in rows:
    if row["fieldtype"] == "Link":
        linked.append(row["options"])
    elif row["fieldtype"] == "Table":
        child = os.path.join(APP, "doctype", row["options"].lower().replace(" ", "_"), row["options"].lower().replace(" ", "_") + ".json")
        linked += [f["options"] for f in json.load(open(child, encoding="utf-8"))["fields"] if f["fieldtype"] == "Link"]
for doctype in sorted(set(linked)):
    if doctype in seeded:
        if not seeded[doctype]:
            fail.append("candidates pick %s, whose list is not seeded: they could not pick anything" % doctype)
    elif doctype not in framework_lists | hr_lists:
        fail.append("candidates pick %s: check its list has values, then add it to verify_careers.py" % doctype)
if len(bio_rules.UGANDA_DISTRICTS) != 136 or len({d.lower() for d in bio_rules.UGANDA_DISTRICTS}) != 136:
    fail.append("UGANDA_DISTRICTS must be the 136 districts (Kampala included), each once: %d" % len(bio_rules.UGANDA_DISTRICTS))
for district in ("Kampala", "Wakiso", "Mukono", "Luuka", "Jinja", "Terego"):
    if district not in bio_rules.UGANDA_DISTRICTS:
        fail.append("UGANDA_DISTRICTS is missing %s" % district)

post = read(os.path.join(REPO, "hrms_addon", "patches.txt")).split("[post_model_sync]")
if len(post) != 2 or "hrms_addon.patches.v1_0.seed_districts_and_languages" not in post[1]:
    fail.append("seed_districts_and_languages must be a post_model_sync patch")
patch = read(os.path.join(REPO, "hrms_addon", "patches", "v1_0", "seed_districts_and_languages.py"))
if 'MASTERS = ("District", "Spoken Language")' not in patch \
        or "seed_masters({master: bio_data_rules.BIO_DATA_MASTERS[master] for master in MASTERS\n" \
           "                  if master in bio_data_rules.BIO_DATA_MASTERS})" not in patch:
    fail.append("seed_districts_and_languages seeds District and Spoken Language through seed_masters, "
                "only a list still defined (languages are typed now)")

script = read(os.path.join(FORM_DIR, "job_application_form.js"))
if re.search(r"{{|{%|{#", script):
    fail.append("job_application_form.js is rendered through Jinja by Frappe: it must not contain {{, {% or {#")
if "window.hrms_addon_apply" not in script or 'method: "hrms_addon.hrms_addon.careers.get_opening_summary"' not in script:
    fail.append("job_application_form.js must define hrms_addon_apply and read the job through get_opening_summary")
if ".html(" in script:
    fail.append("job_application_form.js must set text, not HTML, from the opening's values")
if "hrms_addon_apply.init()" not in (form.get("client_script") or ""):
    fail.append("the web form's client_script must call hrms_addon_apply.init() after the form loads")
style = read(os.path.join(FORM_DIR, "job_application_form.css"))
if not style.split("*/", 1)[-1].lstrip().startswith('@import url("/assets/hrms_addon/css/careers.css?v='):
    fail.append("job_application_form.css must start by importing the careers stylesheet (an @import must come first)")
if not re.search(r"^def get_context\(context\):", read(os.path.join(FORM_DIR, "job_application_form.py")), re.M):
    fail.append("job_application_form.py needs get_context: Frappe calls it for a standard web form")
for init in (os.path.join(APP, "web_form", "__init__.py"), os.path.join(FORM_DIR, "__init__.py")):
    if not os.path.exists(init):
        fail.append("%s is missing: Frappe imports the web form's module" % os.path.relpath(init, REPO))
print("Job Application Form: %d steps, fields match Job Applicant, name, email, phone, CV and cover letter required on step 1, every pick list filled, saved for later on the device" % len(pages))

# ── 4. Job Openings list (/jobs) ─────────────────────────────────────
JOBS_DIR = os.path.join(REPO, "hrms_addon", "www", "jobs")
jobs_page = read(os.path.join(JOBS_DIR, "index.html"))
jobs_py = read(os.path.join(JOBS_DIR, "index.py"))
hrms_jobs = os.path.join(APPS_ROOT, "hrms", "hrms", "www", "jobs")
for init in (os.path.join(REPO, "hrms_addon", "www", "__init__.py"), os.path.join(JOBS_DIR, "__init__.py")):
    if not os.path.exists(init):
        fail.append("%s is missing: Frappe imports the page's index.py as a module" % os.path.relpath(init, REPO))
for own in ("index.js", "index.css"):
    if os.path.exists(os.path.join(JOBS_DIR, own)):
        fail.append("www/jobs/%s would replace HRMS's; the page must keep running HRMS's own" % own)
if "from hrms.www.jobs.index import get_context as hrms_get_context" not in jobs_py or "hrms_get_context(context)" not in jobs_py:
    fail.append("www/jobs/index.py must build the page with HRMS's get_context")
for kind in ("js", "css"):
    if 'context.colocated_%s = frappe.read_file(frappe.get_app_path("hrms", "www", "jobs", "index.%s"))' % (kind, kind) not in jobs_py:
        fail.append("www/jobs/index.py must load HRMS's index.%s as the page's colocated %s" % (kind, kind))
if 'context.body_class = "jobs-page lpl-jobs-page"' not in jobs_py:
    fail.append("the page body must keep HRMS's jobs-page class (its styles use it) and add lpl-jobs-page")
if "{{ super() }}" not in jobs_page.split("{% block style %}")[-1].split("{% endblock %}")[0]:
    fail.append("the list page's style block must keep {{ super() }}: that is where HRMS's index.css is printed")
if not re.search(r'href="/assets/hrms_addon/css/careers\.css\?v=\d+"', jobs_page):
    fail.append("the list page must link the careers stylesheet")
for tag in ("if", "for", "macro", "block"):
    if len(re.findall(r"{%-?\s*" + tag + r"\b", jobs_page)) != len(re.findall(r"{%-?\s*end" + tag + r"\b", jobs_page)):
        fail.append("list page: every {%% %s %%} needs its {%% end%s %%}" % (tag, tag))
for opened, closed in (("{%", "%}"), ("{{", "}}")):
    if jobs_page.count(opened) != jobs_page.count(closed):
        fail.append("list page: unbalanced %s %s" % (opened, closed))
for field in ("job_title", "company", "location", "department", "employment_type"):
    for printed in re.findall(r"{{\s*jo\." + field + r"\b([^}]*)}}", jobs_page):
        if "| e" not in printed:
            fail.append("list page prints jo.%s without escaping it" % field)

hrms_script_path = os.path.join(hrms_jobs, "index.js")
if os.path.exists(hrms_script_path):
    hrms_script = read(hrms_script_path)
    selectors = set()
    for found in re.findall(r'\$\(\s*"([^"]+)"', hrms_script):
        selectors.update(part.strip() for part in found.split(","))
    for selector in sorted(selectors):
        if selector in ("html", "body"):
            continue
        if selector in ("#desktop-", "#mobile-"):
            prefix = selector[1:-1]
            if "{{ prefix ~ '-' ~ value }}" not in jobs_page or 'filter_groups("%s")' % prefix not in jobs_page:
                fail.append("HRMS's script ticks filters by id %s<value>: the page must render them" % selector)
        elif selector.startswith("#"):
            if 'id="%s"' % selector[1:] not in jobs_page:
                fail.append("HRMS's script needs #%s, which the list page no longer has" % selector[1:])
        elif selector.startswith("."):
            name = selector[1:]
            prefix = name.split("-")[0]
            if not re.search(r'class="[^"]*\b%s\b' % re.escape(name), jobs_page) and not (
                name.endswith("-filters") and 'filter_groups("%s")' % prefix in jobs_page and "{{ prefix }}-filters" in jobs_page
            ):
                fail.append("HRMS's script needs .%s, which the list page no longer has" % name)
        elif selector.startswith("[name="):
            name = selector[len("[name="):].rstrip("]")
            if 'name="%s"' % name not in jobs_page:
                fail.append("HRMS's script needs [name=%s], which the list page no longer has" % name)
        else:
            fail.append("HRMS's script uses a selector this check does not understand: %r" % selector)
    for data in re.findall(r'\.data\("([a-z-]+)"\)', hrms_script):
        if 'data-%s="' % data not in jobs_page:
            fail.append("HRMS's script reads data-%s from #data, which the list page no longer sets" % data)
    search_box = re.search(r"<input[^>]*id=\"search-box\"[^>]*>", jobs_page, re.S)
    if not search_box or not re.search(r'class="[^"]*\bdesktop-filters\b[^"]*\bmobile-filters\b', search_box.group(0)):
        fail.append("the search box must carry both desktop-filters and mobile-filters: HRMS sends the query with either set")
    if 'id="{{ jo.route }}" name="card"' not in jobs_page:
        fail.append("each job card must carry its route as its id: HRMS's script navigates to this.id")
    print("Job Openings list: %d selectors HRMS's script uses, all present; HRMS's context, script and styles kept"
          % len(selectors - {"html", "body"}))
else:
    print("SKIPPED HRMS script check: %s not found" % hrms_script_path)

# ── 5. Stylesheet ────────────────────────────────────────────────────
css = read(os.path.join(REPO, "hrms_addon", "public", "css", "careers.css"))
defined = set(re.findall(r"(--lpl-[a-z0-9-]+)\s*:", css))
used = set(re.findall(r"var\((--lpl-[a-z0-9-]+)\)", css))
if used - defined:
    fail.append("careers.css uses undefined variables %s (the browser drops those rules silently)" % sorted(used - defined))
body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
if body.count("{") != body.count("}"):
    fail.append("careers.css: unbalanced braces")
if "!important" in body:
    fail.append("careers.css must win on specificity, not !important")
for page_name, page_source in (("job page", template), ("list page", jobs_page)):
    for cls in set(re.findall(r'class="([^"{]+)"', page_source)):
        for name in cls.split():
            if name.startswith("lpl-") and not re.search(r"\.%s(?![\w-])" % re.escape(name), css):
                fail.append("the %s uses .%s, which careers.css does not style" % (page_name, name))
print("stylesheet: %d variables, all defined; every page class styled" % len(used))

# ── 6. Uploads from the website are private ──────────────────────────
# A CV is personal data. Everything a guest or portal user uploads is stored
# private on the server, and the form's upload dialog offers no choice.
overrides = ast.literal_eval(hooks["override_whitelisted_methods"]) if "override_whitelisted_methods" in hooks else {}
for name in ("upload_file", "frappe.handler.upload_file"):
    if overrides.get(name) != "hrms_addon.hrms_addon.uploads.upload_file":
        fail.append("override_whitelisted_methods must send Frappe's %s to uploads.upload_file, or a CV can be stored public" % name)
uploads = read(os.path.join(APP, "uploads.py"))
for needle, why in (
    ('@frappe.whitelist(allow_guest=True, methods=["POST"])\ndef upload_file():', "must stay open to guests, by POST, as Frappe's is"),
    ('    if "file" in frappe.request.files and from_the_website(frappe.session.user):\n        frappe.form_dict.is_private = 1\n'
     '        if frappe.session.user == "Guest" and for_no_document(frappe.form_dict):\n            return candidate_cv()\n'
     "    return frappe_upload_file()",
     "must store a file sent from the website private, take a guest's CV for an application not yet made, "
     "and hand everything else to Frappe's upload"),
    ("from frappe.handler import upload_file as frappe_upload_file", "must call Frappe's own upload, not a copy of it"),
    ('return user == "Guest" or not frappe.get_doc("User", user).has_desk_access()',
     "must treat guests and portal users, and only them, as the website"),
    # Oct 2026: Frappe v16 refused every CV when System Settings listed any
    # doctype for guest uploads, the form's upload naming none
    ('return not any(form.get(key) for key in ("doctype", "docname", "library_file_name", "file_url", "method"))',
     "takes as a CV only an upload naming no document, file or method"),
    ("@rate_limit(limit=CVS_AN_HOUR, seconds=60 * 60)\ndef candidate_cv():", "limits how many CVs one address sends"),
    ('if not frappe.get_system_settings("allow_guests_to_upload_files"):', "still asks that guests may upload at all"),
    ("if allowed and APPLICANT not in allowed:", "reads System Settings' list as for a Job Applicant"),
    ("if mimetypes.guess_type(upload.filename or \"\")[0] not in CV_TYPES:", "takes a CV's file types only"),
    ('"is_private": 1, "folder": "Home"})', "keeps the CV private"),
    ('"owner": ["in", ["Guest", doc.owner]],\n                                        "attached_to_name": ["is", "not set"]}',
     "attaches to the applicant only an unattached file the applicant sent"),
):
    if needle not in uploads:
        fail.append("uploads.py %s" % why)
if (ast.literal_eval(hooks["doc_events"]) if "doc_events" in hooks else {}).get("Job Applicant", {}).get(
        "after_insert") != "hrms_addon.hrms_addon.uploads.attach_cv":
    fail.append("a Job Applicant made from the website must have its CV attached (uploads.attach_cv after_insert)")
for needle, why in (
        ('$(\'<button type="button" class="lpl-save-later btn btn-default btn-sm ml-2"></button>\')',
         "a Save for later button beside Submit"),
        ("window.localStorage.setItem(this.draft_key(), JSON.stringify({ saved_on: Date.now(), values }));",
         "the application kept on the candidate's own device"),
        ("frappe.web_form.after_save = () => this.clear_draft();", "and cleared once they apply"),
        ('$(".discard-btn").on("click", () => this.clear_draft());', "or discard"),
        ('const HA_APPLY_SKIP = ["job_title", "custom_screening_answers"];',
         "the opening applied for and its questions always come from the page, never the saved copy")):
    if needle not in script:
        fail.append("job_application_form.js: %s (%r not found)" % (why, needle))
if ".lpl-apply-draft" not in style:
    fail.append("job_application_form.css must style the saved application notice")
init = re.search(r"\n\tinit\(\) \{\n\t\t([^\n]*)\n", script)
if not init or init.group(1) != "this.private_uploads();":
    fail.append("job_application_form.js must make uploads private first thing in init, before anything can return early")
private_uploads = script.split("\tprivate_uploads() {")[-1].split("\n\t},")[0] if "\tprivate_uploads() {" in script else ""
for needle in ('["Attach", "Attach Image"].includes(field.df.fieldtype)', "Object.assign({}, field.df.options, {",
               "make_attachments_public: 0,", "allow_toggle_private: false,"):
    if needle not in private_uploads:
        fail.append("job_application_form.js private_uploads must give each attachment field private-only options (%s)" % needle)
hidden = re.search(r"([^{}]*)\{\s*display: none;\s*\}", style)
selectors = {part.strip() for part in hidden.group(1).split("*/")[-1].split(",")} if hidden else set()
if selectors != {"#uploader-private-checkbox", ".file-preview-area .alert-warning"}:
    fail.append("job_application_form.css must hide the dialog's Private box and its 'this file is public' note: %s" % sorted(selectors))

if os.path.isdir(APPS_ROOT):
    def frappe_source(*parts):
        return read(os.path.join(APPS_ROOT, "frappe", "frappe", *parts))

    UPLOADER = ("public", "js", "frappe", "file_uploader")
    for parts, needle, why in (
        (("handler.py",), '@frappe.whitelist(allow_guest=True, methods=["POST"])\ndef upload_file():', "upload_file is whitelisted differently"),
        (("handler.py",), "is_private = frappe.form_dict.is_private", "upload_file no longer reads is_private from the request"),
        (("handler.py",), "cmd = frappe.override_whitelisted_method(cmd)", "calls no longer go through override_whitelisted_methods"),
        (UPLOADER + ("FileUploader.vue",), 'xhr.open("POST", "/api/method/upload_file", true);', "the upload dialog no longer posts to upload_file"),
        (UPLOADER + ("FileUploader.vue",), "private: !props.make_attachments_public || !frappe.utils.can_upload_public_files(),",
         "the dialog decides a file's privacy differently"),
        (UPLOADER + ("FileUploader.vue",), 'class="file-preview-area"', "the dialog's preview area is named differently"),
        (UPLOADER + ("file_uploader.bundle.js",), "allow_toggle_private && frappe.utils.can_upload_public_files()",
         "the dialog decides whether privacy may be toggled differently"),
        (UPLOADER + ("FilePreview.vue",), 'id="uploader-private-checkbox"', "the Private box is named differently"),
        (UPLOADER + ("FilePreview.vue",), 'class="alert alert-warning mb-0"', "the 'this file is public' note is marked up differently"),
        (("public", "js", "frappe", "form", "controls", "attach.js"), "Object.assign(options, this.df.options);",
         "an attachment field's options no longer reach the dialog"),
        (("public", "js", "frappe", "web_form", "web_form.js"), 'method: "frappe.handler.upload_file",',
         "the web form attaches its file differently"),
        (("core", "doctype", "file", "file.py"), 'self.is_private = cint(self.file_url.startswith("/private"))',
         "a file linked by URL no longer takes its privacy from the URL"),
    ):
        if needle not in frappe_source(*parts):
            fail.append("Frappe changed: %s (%s). Recheck the private uploads" % (why, "/".join(parts)))
print("uploads: every file sent from the website is stored private; the form's upload dialog starts private and offers no choice")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CAREERS CHECKS PASSED")
