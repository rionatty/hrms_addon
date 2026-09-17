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
  * the stylesheet defines every variable it uses.

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
    local |= {"icon", "super", "urlencode", "lower", "e", "replace", "join", "format"}
    words = set(re.findall(r"(?<![\.\w])([a-z_][a-z0-9_]*)\b", stripped)) - {"if", "else", "elif", "endif", "for", "in",
                "endfor", "not", "and", "or", "is", "set", "block", "endblock", "extends", "macro", "endmacro"}
    unknown = sorted(w for w in words - local - context_only if w not in opening_fields and w != "job_posting_details")
    if unknown:
        fail.append("page template uses %s, which is neither a Job Opening field nor set in the template" % unknown)
print("Job Opening page: overrides HRMS's template, links the stylesheet, escapes fields, internal JD parts stay out")

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
if len(pages) != 5 or [p for p in pages if not p]:
    fail.append("the form must have 5 non-empty steps (application, personal, family, education, skills), has %d" % len(pages))
mandatory = sorted(row["fieldname"] for p in pages for row in p if row.get("reqd"))
first_page_mandatory = sorted(row["fieldname"] for row in pages[0] if row.get("reqd"))
if mandatory != ["applicant_name", "email_id"] or first_page_mandatory != mandatory:
    fail.append("only Full Name and Email Address may be mandatory, both on step 1: %s" % mandatory)
bio_fields = {fn for fn, f in applicant.items()
              if fn.startswith("custom_") and f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")
              and fn not in ("custom_bio_data_date", "custom_signed_bio_data")}
on_form = {row.get("fieldname") for row in rows}
missing = sorted(bio_fields - on_form)
if missing:
    fail.append("Bio-Data fields missing from the online form: %s" % missing)
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
if 'MASTERS = ("District", "Spoken Language")' not in patch or "seed_masters({master: bio_data_rules.BIO_DATA_MASTERS[master] for master in MASTERS})" not in patch:
    fail.append("seed_districts_and_languages must seed only District and Spoken Language, through seed_masters")

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
print("Job Application Form: %d steps, fields match Job Applicant, only step 1 mandatory, every pick list filled" % len(pages))

# ── 4. Stylesheet ────────────────────────────────────────────────────
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
for cls in set(re.findall(r'class="([^"{]+)"', template)):
    for name in cls.split():
        if name.startswith("lpl-") and "." + name not in css:
            fail.append("the page uses .%s, which careers.css does not style" % name)
print("stylesheet: %d variables, all defined; every page class styled" % len(used))

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CAREERS CHECKS PASSED")
