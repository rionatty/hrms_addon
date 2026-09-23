"""Checks for the Pre-Interview Bio-Data Form (LPL/HR/19) on Job Applicant,
run without a bench.

bio_data_rules.py imports nothing from Frappe, so it is loaded directly and
exercised with a filled-in form: the save checks (dates, years, repeated
rows, languages with nothing ticked) and the carry-over onto Employee when
the candidate is hired.

It also checks:
  * the Bio-Data pick lists (District, Relationship, Spoken Language,
    Examination Level) are masters HR can add to, seeded once, and every
    field that picks from them is a Link to them;
  * the seven child tables are wired to Job Applicant, fit the grid and
    have the expected columns;
  * every Employee field the carry-over writes exists on Employee, its
    Education and External Work History tables, or our fixtures; Marital
    Status offers exactly Employee's options; NIN, TIN and NSSF No. keep
    the Employee master-data template's fieldnames on both doctypes;
  * the Employee's Personal Bio-Data tab (the Personal Bio-Data Form,
    LPL/HR/16) shares the parent, next of kin and qualification tables with
    Job Applicant, is filled from the candidate on hire (certifications and
    licences apart from Education), and its print format only prints fields
    that exist, escaped;
  * the two HRMS "Create Employee" methods the overrides wrap still exist;
  * hooks, patches and the print format resolve, and the print format
    only prints fields that exist, escaped.

Reads frappe/erpnext/hrms from ../ERPNext (or FRAPPE_APPS_ROOT) for the
upstream checks; the behaviour checks run without them.

    python scripts/verify_bio_data.py
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
fail = []

# The Employee master-data template ("Luuka Plastics - ERPNext HR Master Data
# Template.xlsx", Employee sheet) maps its statutory columns to these.
TEMPLATE_STATUTORY_FIELDS = ["custom_nin", "custom_tin", "custom_nssf_no"]


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def doctype_json(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def upstream_json(app, *parts):
    path = os.path.join(APPS_ROOT, app, app, *parts)
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


spec = importlib.util.spec_from_file_location("bio_data_rules", os.path.join(APP, "bio_data_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)  # proves it has no Frappe import
print("loaded bio_data_rules.py without Frappe")

custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
ja_fields = {f["fieldname"]: f for f in custom if f["dt"] == "Job Applicant"}
em_fields = {f["fieldname"]: f for f in custom if f["dt"] == "Employee"}

# ── 1. Pick lists ────────────────────────────────────────────────────
for master, (name_field, seeds) in rules.BIO_DATA_MASTERS.items():
    spec_json = doctype_json(master)
    if not spec_json:
        fail.append("master %s has no DocType JSON" % master)
        continue
    folder = master.lower().replace(" ", "_")
    fields = {f["fieldname"]: f for f in spec_json["fields"]}
    if spec_json.get("istable") or spec_json.get("module") != "HRMS Addon" or spec_json.get("name") != master:
        fail.append("%s must be an HRMS Addon master (not a child table)" % master)
    if spec_json.get("autoname") != "field:%s" % name_field or not (fields.get(name_field) or {}).get("reqd"):
        fail.append("%s must be named by its mandatory %s field" % (master, name_field))
    if not spec_json.get("allow_rename") or not spec_json.get("quick_entry"):
        fail.append("%s must allow rename and open in quick entry" % master)
    if not spec_json.get("allow_import"):
        fail.append("%s must allow Data Import: a list is loaded in bulk, not typed one value at a time" % master)
    perms = {p["role"]: p for p in spec_json.get("permissions", [])}
    for role in ("HR Manager", "HR User"):
        if not all((perms.get(role) or {}).get(k) for k in ("read", "write", "create")):
            fail.append("%s: %s must be able to add values" % (master, role))
    long_list = master == "District"
    expected_sort = (name_field, "ASC") if long_list else ("creation", "ASC")
    if (spec_json.get("sort_field"), spec_json.get("sort_order")) != expected_sort:
        fail.append("%s must list values by %s (%s)" % (master, expected_sort,
                    "a long list, alphabetically" if long_list else "the seeded order, then HR's additions"))
    if not re.search(r"^class %s\(Document\):" % master.replace(" ", ""), open(os.path.join(APP, "doctype", folder, folder + ".py"), encoding="utf-8").read(), re.M):
        fail.append("%s controller class must be %s" % (master, master.replace(" ", "")))
    if not os.path.exists(os.path.join(APP, "doctype", folder, "__init__.py")):
        fail.append("%s folder is missing __init__.py" % master)
    if len({s.lower() for s in seeds}) != len(seeds) or not all(s and s == s.strip() for s in seeds):
        fail.append("%s seeds must be distinct, non-blank and trimmed" % master)
    if any(c in s for s in seeds for c in "<>'\""):
        fail.append("%s seeds must not contain < > or quotes (names, and URLs built from them)" % master)

for (doctype, fieldname), master in rules.BIO_DATA_FIELD_MASTERS.items():
    if doctype == "Job Applicant":
        f = ja_fields.get(fieldname) or {}
    else:
        f = next((x for x in (doctype_json(doctype) or {"fields": []})["fields"] if x["fieldname"] == fieldname), {})
    if (f.get("fieldtype"), f.get("options")) != ("Link", master):
        fail.append("%s.%s must be a Link to %s, is %s %r" % (doctype, fieldname, master, f.get("fieldtype"), f.get("options")))
if set(rules.BIO_DATA_FIELD_MASTERS.values()) != set(rules.BIO_DATA_MASTERS):
    fail.append("every Bio-Data pick list must be used by a field, and every field's list must be a Bio-Data master")
print("pick lists: %d masters, %d fields link to them" % (len(rules.BIO_DATA_MASTERS), len(rules.BIO_DATA_FIELD_MASTERS)))

# ── 2. Child tables ──────────────────────────────────────────────────
EXPECTED_TABLE_FIELDS = {
    "Applicant Parent": ["full_name", "relationship", "occupation", "home_village", "home_district", "current_residence",
                         "current_district", "phone"],
    "Applicant Next of Kin": ["full_name", "relationship", "company", "job_title", "phone", "email"],
    "Applicant Qualification": ["qualification_type", "institution", "period", "program", "award"],
    "Applicant School Result": ["examination_level", "subject", "grade"],
    "Applicant Employment History": ["workplace", "position", "from_year", "to_year", "reason_for_leaving"],
    "Applicant Skill": ["skill"],
    "Applicant Language": ["language", "can_read", "can_write", "can_speak"],
}
if list(rules.TABLES.values()) != list(EXPECTED_TABLE_FIELDS):
    fail.append("bio_data_rules.TABLES %s differ from the expected tables" % list(rules.TABLES.values()))
child_fields = {}
for table_field, child in rules.TABLES.items():
    parent = ja_fields.get(table_field) or {}
    if (parent.get("fieldtype"), parent.get("options")) != ("Table", child):
        fail.append("Job Applicant.%s must be a Table of %s" % (table_field, child))
    spec_json = doctype_json(child)
    if not spec_json:
        fail.append("child table %s has no DocType JSON" % child)
        continue
    names = [f["fieldname"] for f in spec_json["fields"]]
    child_fields[child] = {f["fieldname"]: f for f in spec_json["fields"]}
    if names != EXPECTED_TABLE_FIELDS.get(child) or spec_json.get("field_order") != names:
        fail.append("%s fields %s, expected %s" % (child, names, EXPECTED_TABLE_FIELDS.get(child)))
    if not spec_json.get("istable") or spec_json.get("module") != "HRMS Addon" or spec_json.get("name") != child:
        fail.append("%s must be an HRMS Addon child table" % child)
    width = sum(f.get("columns") or 0 for f in spec_json["fields"] if f.get("in_list_view"))
    if not 0 < width <= 10:
        fail.append("%s grid is %d columns wide; Frappe fits 10" % (child, width))
    if not any(f.get("reqd") for f in spec_json["fields"]):
        fail.append("%s needs a mandatory column, or blank rows are saved" % child)
    for f in spec_json["fields"]:
        if f["fieldtype"] == "Select":
            fail.append("%s.%s is a Select: make it a Link to a pick list" % (child, f["fieldname"]))
    folder = child.lower().replace(" ", "_")
    if not re.search(r"^class %s\(Document\):" % child.replace(" ", ""), open(os.path.join(APP, "doctype", folder, folder + ".py"), encoding="utf-8").read(), re.M):
        fail.append("%s controller class must be %s" % (child, child.replace(" ", "")))
    if not os.path.exists(os.path.join(APP, "doctype", folder, "__init__.py")):
        fail.append("%s folder is missing __init__.py" % child)
skill = (child_fields.get("Applicant Skill") or {}).get("skill") or {}
if (skill.get("fieldtype"), skill.get("options"), skill.get("reqd")) != ("Link", "Skill", 1):
    fail.append("Applicant Skill.skill must be a mandatory Link to Skill, the list Job Descriptions use")
for child, fieldname, fieldtype in (("Applicant Employment History", "from_year", "Data"), ("Applicant Employment History", "to_year", "Data")):
    if ((child_fields.get(child) or {}).get(fieldname) or {}).get("fieldtype") != fieldtype:
        fail.append("%s.%s must be Data: an Int year prints as 2,015" % (child, fieldname))
for fieldname, (fieldtype, options) in {"custom_gender": ("Link", "Gender"), "custom_citizenship": ("Link", "Country"),
                                        "custom_previous_salary": ("Currency", "currency"), "custom_signed_bio_data": ("Attach", None)}.items():
    f = ja_fields.get(fieldname) or {}
    if (f.get("fieldtype"), f.get("options")) != (fieldtype, options):
        fail.append("Job Applicant.%s must be %s %s" % (fieldname, fieldtype, options or ""))
if any(f.get("reqd") for f in ja_fields.values()):
    fail.append("no Bio-Data field may be mandatory: applicants from the portal have none of it")
print("child tables: %d wired to Job Applicant, columns, grid width and classes correct" % len(rules.TABLES))

# ── 3. Carrying the bio-data onto Employee ───────────────────────────
if list(rules.MARITAL_STATUSES) != [o for o in (ja_fields.get("custom_marital_status", {}).get("options") or "").split("\n") if o]:
    fail.append("Job Applicant.custom_marital_status options must be exactly bio_data_rules.MARITAL_STATUSES")
if [f for f in TEMPLATE_STATUTORY_FIELDS if f not in ja_fields or f not in em_fields]:
    fail.append("NIN, TIN and NSSF No. must be %s on both Job Applicant and Employee (the master-data template's names)"
                % TEMPLATE_STATUTORY_FIELDS)
for fieldname in TEMPLATE_STATUTORY_FIELDS:
    if rules.EMPLOYEE_FIELDS.get(fieldname) != fieldname:
        fail.append("%s must carry over to the Employee field of the same name" % fieldname)

glue_source_for_types = read("hrms_addon", "hrms_addon", "bio_data.py")
employee = upstream_json("erpnext", "setup", "doctype", "employee", "employee.json")
job_applicant = upstream_json("hrms", "hr", "doctype", "job_applicant", "job_applicant.json")
education = upstream_json("erpnext", "setup", "doctype", "employee_education", "employee_education.json")
work_history = upstream_json("erpnext", "setup", "doctype", "employee_external_work_history", "employee_external_work_history.json")
if employee and job_applicant and education and work_history:
    em_all = {f["fieldname"]: f for f in employee["fields"]} | em_fields
    ja_all = {f["fieldname"]: f for f in job_applicant["fields"]} | ja_fields
    if [o for o in (em_all["marital_status"].get("options") or "").split("\n") if o] != list(rules.MARITAL_STATUSES):
        fail.append("Employee.marital_status options changed upstream: %s" % em_all["marital_status"].get("options"))
    for source, target in rules.EMPLOYEE_FIELDS.items():
        if source not in ja_all:
            fail.append("carry-over reads Job Applicant.%s, which does not exist" % source)
        if target not in em_all:
            fail.append("carry-over writes Employee.%s, which does not exist" % target)
    for fieldname in ("custom_nin", "custom_tin", "custom_nssf_no"):
        if fieldname in ja_all and ja_all[fieldname]["fieldtype"] != (em_all.get(fieldname) or {}).get("fieldtype"):
            fail.append("%s must have the same type on Job Applicant and Employee" % fieldname)
    if "upper_range" not in ja_all or job_applicant["field_order"][-1] != "upper_range":
        fail.append("HRMS's Job Applicant no longer ends with upper_range: re-anchor Previous Salary and the Bio-Data tab")
    UPSTREAM_OK = True
else:
    UPSTREAM_OK = False
    print("SKIPPED upstream field checks: frappe/erpnext/hrms not found at %s (set FRAPPE_APPS_ROOT)" % APPS_ROOT)

# A filled-in form, from the fields of LPL/HR/19
FORM = {
    "applicant_name": "Okello John", "phone_number": "+256 772 123456",
    "custom_date_of_birth": "1994-05-14", "custom_gender": "Male", "custom_marital_status": "Married",
    "custom_no_of_children": 2, "custom_citizenship": "Uganda",
    "custom_home_village": "Kasangati", "custom_home_district": "Wakiso",
    "custom_current_residence": "Kawempe", "custom_current_district": "Kampala",
    "custom_nin": "CM94012345678P", "custom_nssf_no": "NS123456789", "custom_tin": "1001234567",
    "custom_health_issues": "", "custom_previous_salary": 850000, "custom_bio_data_date": "2026-09-10",
    "custom_parents": [
        {"full_name": "Okello Peter", "relationship": "Father", "home_village": "Kasangati", "home_district": "Wakiso",
         "current_residence": "Gayaza", "current_district": "Wakiso", "phone": "0701234567"},
        {"full_name": "Akello Mary", "relationship": "Mother"},
    ],
    "custom_next_of_kin": [
        {"full_name": "", "relationship": "Spouse"},
        {"full_name": "Namusoke Sarah", "relationship": "Spouse", "company": "Crane Bank", "job_title": "Teller",
         "phone": "0772000111", "email": "sarah@example.com"},
    ],
    "custom_qualifications": [
        {"institution": "Makerere University", "period": "2014 - 2017", "program": "Bachelor of Commerce", "award": "Second Class Upper"},
        {"institution": "UMI", "period": "Aug 2018 to Jul 2019", "program": "", "award": "Postgraduate Diploma"},
        {"institution": "Kyambogo", "period": "ongoing", "program": "Diploma in Marketing", "award": ""},
    ],
    "custom_school_results": [
        {"examination_level": "O-Level (UCE)", "subject": "Mathematics", "grade": "D1"},
        {"examination_level": "O-Level (UCE)", "subject": "English", "grade": "C3"},
        {"examination_level": "A-Level (UACE)", "subject": "Mathematics", "grade": "B"},
    ],
    "custom_employment_history": [
        {"workplace": "Nice House of Plastics", "position": "Sales Executive", "from_year": "2017", "to_year": "2021",
         "reason_for_leaving": "Career growth"},
        {"workplace": "x" * 150, "position": "", "from_year": "2021", "to_year": ""},
    ],
    "custom_skills": [{"skill": "Negotiation"}, {"skill": "Driving"}],
    "custom_languages": [{"language": "English", "can_read": 1, "can_write": 1, "can_speak": 1},
                         {"language": "Luganda", "can_read": 0, "can_write": 0, "can_speak": 1}],
}
TODAY = "2026-09-17"


class Row:  # Frappe child rows are objects, not dicts
    def __init__(self, **values):
        self.__dict__.update(values)


check = rules.bio_data_errors
expect("filled-in form", check(FORM, TODAY))
expect("an applicant from the portal with no bio-data", check({"applicant_name": "Jane"}, TODAY))
expect("object rows", check(dict(FORM, custom_languages=[Row(language="English", can_read=0, can_write=0, can_speak=1)]), TODAY))
expect("date of birth in the future", check(dict(FORM, custom_date_of_birth="2027-01-01"), TODAY), "Date of Birth cannot be in the future.")
expect("signed in the future", check(dict(FORM, custom_bio_data_date="2026-09-18"), TODAY), "Date Signed cannot be in the future.")
expect("negative children", check(dict(FORM, custom_no_of_children=-1), TODAY), "No. of Children cannot be negative.")
expect("two-digit year", check(dict(FORM, custom_employment_history=[{"workplace": "A", "from_year": "15"}]), TODAY),
       "Employment History row 1: From (Year) must be a year from 1950 to 2026")
expect("future year", check(dict(FORM, custom_employment_history=[{"workplace": "A", "to_year": "2030"}]), TODAY),
       "Employment History row 1: To (Year) must be a year from 1950 to 2026")
expect("years back to front", check(dict(FORM, custom_employment_history=[{"workplace": "A", "from_year": "2020", "to_year": "2018"}]), TODAY),
       "Employment History row 1: To (Year) 2018 is before From (Year) 2020.")
expect("same skill twice", check(dict(FORM, custom_skills=[{"skill": "Driving"}, {"skill": "driving"}]), TODAY),
       "Skills Possessed row 2: driving is already listed in row 1.")
expect("same language twice", check(dict(FORM, custom_languages=[{"language": "English", "can_speak": 1}, {"language": "English", "can_read": 1}]), TODAY),
       "Language Proficiency row 2: English is already listed in row 1.")
expect("language with nothing ticked", check(dict(FORM, custom_languages=[{"language": "Swahili", "can_read": 0}]), TODAY),
       "Language Proficiency row 1: tick Read, Write or Speak for Swahili.")
expect("subject twice at one level", check(dict(FORM, custom_school_results=[
    {"examination_level": "O-Level (UCE)", "subject": "Mathematics"}, {"examination_level": "O-Level (UCE)", "subject": " mathematics "}]), TODAY),
    "A'Level and O'Level Results row 2: mathematics is already listed for O-Level (UCE) in row 1.")
print("save checks: filled-in form passes; future dates, bad years, repeats and unticked languages refused")

values = rules.employee_values(FORM)
EXPECTED_SIMPLE = {
    "date_of_birth": "1994-05-14", "gender": "Male", "marital_status": "Married", "cell_number": "+256 772 123456",
    "custom_nin": "CM94012345678P", "custom_tin": "1001234567", "custom_nssf_no": "NS123456789",
    "current_address": "Kawempe, Kampala", "permanent_address": "Kasangati, Wakiso",
    "person_to_be_contacted": "Namusoke Sarah", "relation": "Spouse", "emergency_phone_number": "0772000111",
    # the Employee's Personal Bio-Data tab asks the same
    "custom_home_village": "Kasangati", "custom_home_district": "Wakiso",
    "custom_current_residence": "Kawempe", "custom_current_district": "Kampala",
}
for field, value in EXPECTED_SIMPLE.items():
    if values.get(field) != value:
        fail.append("carry-over %s is %r, expected %r" % (field, values.get(field), value))
if "health_details" in values:
    fail.append("an empty value must not be carried over (it would blank nothing, but hides intent): health_details")
if values.get("family_background") != ("Father: Okello Peter | home: Kasangati, Wakiso | lives: Gayaza, Wakiso | tel: 0701234567\n"
                                       "Mother: Akello Mary\nChildren: 2"):
    fail.append("family background wrong: %r" % values.get("family_background"))
if values.get("education") != [
    {"school_univ": "Makerere University", "qualification": "Bachelor of Commerce", "class_per": "Second Class Upper", "year_of_passing": 2017},
    {"school_univ": "UMI", "qualification": "Postgraduate Diploma", "year_of_passing": 2019},
    {"school_univ": "Kyambogo", "qualification": "Diploma in Marketing"},
    {"qualification": "O-Level (UCE)", "maj_opt_subj": "Mathematics: D1\nEnglish: C3"},
    {"qualification": "A-Level (UACE)", "maj_opt_subj": "Mathematics: B"},
]:
    fail.append("education rows wrong: %s" % values.get("education"))
if values.get("external_work_history") != [
    {"company_name": "Nice House of Plastics", "designation": "Sales Executive", "total_experience": "2017 - 2021"},
    {"company_name": "x" * 140, "total_experience": "from 2021"},
]:
    fail.append("work history rows wrong (Data fields cut to 140): %s" % values.get("external_work_history"))
if rules.employee_values({}) != {}:
    fail.append("an applicant with no bio-data must carry nothing over: %s" % rules.employee_values({}))
for period, year in (("2014 - 2017", 2017), ("2019/2020", 2020), ("1999", 1999), ("20015", None), ("ongoing", None), (None, None)):
    if rules.last_year(period) != year:
        fail.append("last_year(%r) is %r, expected %r" % (period, rules.last_year(period), year))

current = {"date_of_birth": "1990-01-01", "gender": "", "marital_status": None, "education": [{"qualification": "PLE"}],
           "external_work_history": []}
missing = rules.missing_values(current, values)
if "date_of_birth" in missing or "education" in missing:
    fail.append("missing_values must never overwrite what the Employee already has: %s" % sorted(missing))
if missing.get("gender") != "Male" or missing.get("marital_status") != "Married" or not missing.get("external_work_history"):
    fail.append("missing_values must fill blank fields and empty tables: %s" % sorted(missing))

if UPSTREAM_OK:
    for field in values:
        if field not in em_all:
            fail.append("carry-over writes Employee.%s, which does not exist" % field)
    for table, spec_json in (("education", education), ("external_work_history", work_history)):
        columns = {f["fieldname"]: f for f in spec_json["fields"]}
        for row in values.get(table, []):
            for key, value in row.items():
                if key not in columns:
                    fail.append("carry-over writes %s.%s, which does not exist" % (spec_json["name"], key))
                elif columns[key]["fieldtype"] == "Data" and len(str(value)) > rules.DATA_MAX:
                    fail.append("carry-over writes %d characters into Data field %s.%s" % (len(str(value)), spec_json["name"], key))
                elif columns[key]["fieldtype"] == "Int" and not isinstance(value, int):
                    fail.append("carry-over writes %r into Int field %s.%s" % (value, spec_json["name"], key))
print("carry-over: %d Employee fields filled from the form, blanks only, every target exists" % len(values))

# ── 3b. The Employee's Personal Bio-Data tab (LPL/HR/16) ─────────────
for child, columns in rules.TABLE_COLUMNS.items():
    names = [f["fieldname"] for f in (doctype_json(child) or {}).get("fields", [])]
    if list(columns) != names:
        fail.append("bio_data_rules.TABLE_COLUMNS[%r] %s must be all of %s's columns %s" % (child, list(columns), child, names))
for source, target in rules.EMPLOYEE_TABLES.items():
    f = em_fields.get(target) or {}
    if (f.get("fieldtype"), f.get("options")) != ("Table", rules.TABLES.get(source)):
        fail.append("Employee.%s must be a Table of %s, like Job Applicant.%s" % (target, rules.TABLES.get(source), source))
f = em_fields.get(rules.PROFESSIONAL_TABLE) or {}
if (f.get("fieldtype"), f.get("options")) != ("Table", "Applicant Qualification"):
    fail.append("Employee.%s must be a Table of Applicant Qualification" % rules.PROFESSIONAL_TABLE)
f = em_fields.get("custom_children") or {}
if (f.get("fieldtype"), f.get("options")) != ("Table", "Employee Child"):
    fail.append("Employee.custom_children must be a Table of Employee Child")
child_spec = doctype_json("Employee Child") or {}
kid_fields = [(f["fieldname"], f["fieldtype"], bool(f.get("reqd"))) for f in child_spec.get("fields", [])]
if kid_fields != [("full_name", "Data", True), ("date_of_birth", "Date", False)]:
    fail.append("Employee Child must have a mandatory Name and a Date of Birth, has %s" % kid_fields)
if not child_spec.get("istable") or child_spec.get("module") != "HRMS Addon" \
        or not 0 < sum(f.get("columns") or 0 for f in child_spec.get("fields", []) if f.get("in_list_view")) <= 10:
    fail.append("Employee Child must be an HRMS Addon child table that fits the grid")
kid_py = os.path.join(APP, "doctype", "employee_child", "employee_child.py")
if not os.path.exists(kid_py) or not re.search(r"^class EmployeeChild\(Document\):", open(kid_py, encoding="utf-8").read(), re.M) \
        or not os.path.exists(os.path.join(APP, "doctype", "employee_child", "__init__.py")):
    fail.append("Employee Child needs its controller class EmployeeChild and __init__.py")
if (em_fields.get("custom_bio_data_signed_on") or {}).get("fieldtype") != "Date":
    fail.append("Employee.custom_bio_data_signed_on (the date the form was signed) must be a Date: the onboarding checks it")

# parents and next of kin carry over row by row; a next of kin with no name does not
if values.get("custom_parents") != [
    {"full_name": "Okello Peter", "relationship": "Father", "home_village": "Kasangati", "home_district": "Wakiso",
     "current_residence": "Gayaza", "current_district": "Wakiso", "phone": "0701234567"},
    {"full_name": "Akello Mary", "relationship": "Mother"},
]:
    fail.append("parent rows wrong: %s" % values.get("custom_parents"))
if values.get("custom_next_of_kin") != [
    {"full_name": "Namusoke Sarah", "relationship": "Spouse", "company": "Crane Bank", "job_title": "Teller",
     "phone": "0772000111", "email": "sarah@example.com"},
]:
    fail.append("next of kin rows wrong (the row with no name must be left out): %s" % values.get("custom_next_of_kin"))
if rules.PROFESSIONAL_TABLE in values:
    fail.append("qualifications with no type stay in Education: %s" % values.get(rules.PROFESSIONAL_TABLE))

# certifications and licences apart from the formal education, by the site's own types
QUALIFICATIONS = [
    {"qualification_type": "Academic", "institution": "Makerere University", "period": "2014 - 2017",
     "program": "Bachelor of Commerce"},
    {"qualification_type": "Professional Certification", "institution": "ICPAU", "period": "2020", "award": "CPA"},
    {"qualification_type": "Membership", "institution": "IPPU", "award": "Member"},
]
routed = rules.employee_values(dict(FORM, custom_qualifications=QUALIFICATIONS, custom_school_results=[]))
if routed.get(rules.PROFESSIONAL_TABLE) != [QUALIFICATIONS[1]]:
    fail.append("a Professional Certification must go to the professional table: %s" % routed.get(rules.PROFESSIONAL_TABLE))
if [row.get("school_univ") for row in routed.get("education", [])] != ["Makerere University", "IPPU"]:
    fail.append("Education must keep the other qualifications only: %s" % routed.get("education"))
routed = rules.employee_values(dict(FORM, custom_qualifications=QUALIFICATIONS, custom_school_results=[]), ("Membership",))
if [row.get("institution") for row in routed.get(rules.PROFESSIONAL_TABLE, [])] != ["IPPU"] \
        or [row.get("school_univ") for row in routed.get("education", [])] != ["Makerere University", "ICPAU"]:
    fail.append("the site's own certification types (ticked on Qualification Type) must decide: %s / %s"
                % (routed.get(rules.PROFESSIONAL_TABLE), routed.get("education")))
if "is_certification" not in glue_source_for_types:
    fail.append("bio_data.add_bio_data must pass the site's certification types (Qualification Type is_certification)")
for target in list(rules.EMPLOYEE_TABLES.values()) + [rules.PROFESSIONAL_TABLE]:
    child = (em_fields.get(target) or {}).get("options")
    columns = {f["fieldname"] for f in (doctype_json(child) or {}).get("fields", [])}
    for row in values.get(target, []) + dict(routed).get(target, []):
        for key in row:
            if key not in columns:
                fail.append("carry-over writes %s.%s, which does not exist" % (child, key))
print("Personal Bio-Data tab: shared tables wired, parents and next of kin carried, certifications apart, "
      "Employee Child ready")

# ── 4. Wiring ────────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "bio_data.py")
hooks_src = read("hrms_addon", "hooks.py")
hooks = {}
for node in ast.parse(hooks_src).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass

applicant_validate = (hooks.get("doc_events") or {}).get("Job Applicant", {}).get("validate")
if isinstance(applicant_validate, str):
    applicant_validate = [applicant_validate]
if list(applicant_validate or [])[:1] != ["hrms_addon.hrms_addon.bio_data.validate"]:
    fail.append("doc_events Job Applicant validate must run hrms_addon.hrms_addon.bio_data.validate first")
if "bio_data_rules.bio_data_errors(doc.as_dict(), today())" not in glue:
    fail.append("bio_data.validate must apply the tested rules to the whole document, tables included")
OVERRIDES = {
    "hrms.hr.doctype.job_offer.job_offer.make_employee": ("make_employee_from_job_offer", "Job Offer",
                                                         ("hr", "doctype", "job_offer", "job_offer.py")),
    "hrms.hr.doctype.employee_onboarding.employee_onboarding.make_employee": ("make_employee_from_onboarding", "Employee Onboarding",
                                                                             ("hr", "doctype", "employee_onboarding", "employee_onboarding.py")),
}
for original, (function, source_doctype, path) in OVERRIDES.items():
    if (hooks.get("override_whitelisted_methods") or {}).get(original) != "hrms_addon.hrms_addon.bio_data.%s" % function:
        fail.append("override_whitelisted_methods must send %s to bio_data.%s" % (original, function))
    body = re.search(r"@frappe\.whitelist\(\)\ndef %s\(source_name, target_doc=None\):\n(.*?)(?=\n\n\n|\Z)" % function, glue, re.S)
    module = original.rsplit(".", 1)[0]
    if not body or "from %s import make_employee" % module not in body.group(1) \
            or 'add_bio_data(make_employee(source_name, target_doc), "%s", source_name)' % source_doctype not in body.group(1):
        fail.append("bio_data.%s must be whitelisted, call %s.make_employee and add the bio-data from the %s"
                    % (function, module, source_doctype))
    upstream = os.path.join(APPS_ROOT, "hrms", "hrms", *path)
    if os.path.exists(upstream) and not re.search(r"@frappe\.whitelist\(\)\ndef make_employee\(source_name", open(upstream, encoding="utf-8").read()):
        fail.append("HRMS no longer has a whitelisted make_employee(source_name, ...) in %s" % "/".join(path))
for needle, why in (
    ("bio_data_rules.missing_values(employee.as_dict(), values)", "must fill blanks only"),
    ("meta.has_field(field)", "must skip Employee fields this site does not have yet"),
    ('frappe.get_doc("Job Applicant", job_applicant)', "must read the applicant's bio-data"),
):
    if needle not in glue:
        fail.append("bio_data.add_bio_data %s" % why)
if not re.search(r'for ptype in \("read", "write", "create"\):', glue) or '"delete"' in glue:
    fail.append("allow_hr_user_to_add_skills must grant HR User read, write and create on Skill, not delete")
if "setup_custom_perms(\"Skill\")" not in glue:
    fail.append("allow_hr_user_to_add_skills must copy Skill's standard rules first (setup_custom_perms)")
after_install = hooks.get("after_install")
after_install = [after_install] if isinstance(after_install, str) else (after_install or [])
if "hrms_addon.hrms_addon.bio_data.after_install" not in after_install or "hrms_addon.hrms_addon.pick_lists.after_install" not in after_install:
    fail.append("after_install must run pick_lists.after_install and bio_data.after_install")
if not re.search(r"def after_install\(\):\n    allow_hr_user_to_add_skills\(\)", glue):
    fail.append("bio_data.after_install must grant the Skill permission")
if "bio_data" in json.dumps(hooks.get("after_migrate") or []):
    fail.append("the Skill permission must be granted once, not on every migrate")

pick_lists = read("hrms_addon", "hrms_addon", "pick_lists.py")
if "def seed_bio_data_masters():\n    seed_masters(bio_data_rules.BIO_DATA_MASTERS)" not in pick_lists \
        or "MASTERS = {**jd_rules.MASTERS, **bio_data_rules.BIO_DATA_MASTERS, **org_rules.ORG_MASTERS}" not in pick_lists:
    fail.append("pick_lists.py must seed the Bio-Data lists (seed_bio_data_masters) and include them in after_install")
for name in os.listdir(os.path.join(REPO, "hrms_addon", "fixtures")):
    if name.endswith(".json") and any(r.get("doctype") in rules.BIO_DATA_MASTERS for r in json.loads(read("hrms_addon", "fixtures", name))):
        fail.append("fixtures/%s holds Bio-Data list values: migrate would re-import them over HR's changes" % name)

post = read("hrms_addon", "patches.txt").split("[post_model_sync]")
listed = [line.strip() for line in post[1].splitlines() if line.strip() and not line.startswith("#")] if len(post) == 2 else []
for patch, function, module in (("seed_bio_data_masters", "seed_bio_data_masters", "pick_lists"),
                                ("allow_hr_user_to_add_skills", "allow_hr_user_to_add_skills", "bio_data")):
    if "hrms_addon.patches.v1_0.%s" % patch not in listed:
        fail.append("%s must be a post_model_sync patch" % patch)
    src = read("hrms_addon", "patches", "v1_0", patch + ".py")
    if "from hrms_addon.hrms_addon.%s import %s" % (module, function) not in src or not re.search(r"def execute\(\):\n    %s\(\)" % function, src):
        fail.append("patch %s must call %s.%s" % (patch, module, function))
print("wiring: save check, both Create Employee overrides, Skill permission and seeding resolve")

# ── 5. Print format ──────────────────────────────────────────────────
pf_path = os.path.join(APP, "print_format", "pre_interview_bio_data_form", "pre_interview_bio_data_form.json")
pf = json.load(open(pf_path, encoding="utf-8"))
if (pf.get("doctype"), pf.get("name"), pf.get("doc_type"), pf.get("module"), pf.get("standard"), pf.get("print_format_type"),
        pf.get("custom_format"), pf.get("disabled")) != ("Print Format", "Pre-Interview Bio-Data Form", "Job Applicant", "HRMS Addon",
                                                        "Yes", "Jinja", 1, 0):
    fail.append("print format must be a standard, enabled Jinja format of Job Applicant in HRMS Addon")
html = pf.get("html") or ""
for block in ("for", "if", "macro"):
    opened = len(re.findall(r"{%-?\s*" + block + r"\b", html))
    closed = len(re.findall(r"{%-?\s*end" + block + r"\b", html))
    if opened != closed:
        fail.append("print format: %d {%% %s %%} but %d {%% end%s %%}" % (opened, block, closed, block))
if html.count("{{") != html.count("}}") or html.count("{%") != html.count("%}"):
    fail.append("print format: unbalanced {{ }} or {% %}")
if "LPL/HR/19" not in html:
    fail.append("print format must carry the form's document reference LPL/HR/19")
if UPSTREAM_OK:
    for fieldname in set(re.findall(r"\bdoc\.([a-z_]+)", html)) | set(re.findall(r'get_formatted\("([a-z_]+)"\)', html)):
        if fieldname not in ja_all and fieldname != "get_formatted":
            fail.append("print format uses Job Applicant.%s, which does not exist" % fieldname)
# padded lists and the tables they come from
PADDED = dict(re.findall(r"set (\w+) = doc\.(custom_\w+) \+ \[\{\}\]", html))
for variable, table_field in PADDED.items():
    if table_field not in rules.TABLES:
        fail.append("print format pads %s from %s, which is not a Bio-Data table" % (variable, table_field))
for variable, body in re.findall(r"for row in (\S+?)(?: if [^%]*)? %}(.*?){%-? endfor", html, re.S):
    table_field = PADDED.get(variable) or variable.replace("doc.", "")
    child = rules.TABLES.get(table_field)
    if not child:
        fail.append("print format loops over %s, which is not a Bio-Data table" % variable)
        continue
    for attribute in set(re.findall(r"\brow\.([a-z_]+)", body)):
        if attribute not in (child_fields.get(child) or {}):
            fail.append("print format prints %s.%s, which does not exist" % (child, attribute))
raw = re.findall(r"{{-?\s*(?:doc|row)\.(?!get_formatted)[a-z_]+", html)
if raw:
    fail.append("print format must print text through v() so it is escaped: %s" % raw[:3])
if len(PADDED) != 6:
    fail.append("print format should pad the six repeating sections to the paper form's rows, pads %s" % sorted(PADDED))
print("print format: LPL/HR/19, balanced blocks, every printed field exists, text escaped")

# ── 5b. Personal Bio-Data Form print (LPL/HR/16) on Employee ─────────
pf_path = os.path.join(APP, "print_format", "personal_bio_data_form", "personal_bio_data_form.json")
pf = json.load(open(pf_path, encoding="utf-8")) if os.path.exists(pf_path) else {}
if (pf.get("doctype"), pf.get("name"), pf.get("doc_type"), pf.get("module"), pf.get("standard"), pf.get("print_format_type"),
        pf.get("custom_format"), pf.get("disabled")) != ("Print Format", "Personal Bio-Data Form", "Employee", "HRMS Addon",
                                                        "Yes", "Jinja", 1, 0):
    fail.append("Personal Bio-Data Form must be a standard, enabled Jinja print format of Employee in HRMS Addon")
html = pf.get("html") or ""
for block in ("for", "if", "macro"):
    opened = len(re.findall(r"{%-?\s*" + block + r"\b", html))
    closed = len(re.findall(r"{%-?\s*end" + block + r"\b", html))
    if opened != closed:
        fail.append("Personal Bio-Data Form: %d {%% %s %%} but %d {%% end%s %%}" % (opened, block, closed, block))
if html.count("{{") != html.count("}}") or html.count("{%") != html.count("%}"):
    fail.append("Personal Bio-Data Form: unbalanced {{ }} or {% %}")
for needle in ("LPL/HR/16", "PERSONAL BIO-DATA FORM", "passport size photographs", "Number of Children",
               "Previous Work Experience", "true and correct to the best of my knowledge"):
    if needle not in html:
        fail.append("Personal Bio-Data Form must print %r, as the paper form does" % needle)
if UPSTREAM_OK:
    for fieldname in set(re.findall(r"\bdoc\.([a-z_]+)", html)):
        if fieldname not in em_all:
            fail.append("Personal Bio-Data Form uses Employee.%s, which does not exist" % fieldname)
    # each loop prints only the columns of the table it walks
    padded = dict(re.findall(r"set (\w+) = \(doc\.(\w+) or \[\]\) \+ \[\{\}\]", html))
    padded.update({name: "custom_parents" for name in ("others", "father", "mother", "parents")})
    tables = {"education": education, "external_work_history": work_history}
    for variable, body in re.findall(r"for (?:\w+, )?row in (\w+|\[.*?\]) %}(.*?){%-? endfor", html, re.S):
        table_field = padded.get(variable) or ("custom_parents" if "father" in variable else None)
        options = (em_all.get(table_field) or {}).get("options")
        spec_json = tables.get(table_field) or doctype_json(options or "")
        if not spec_json:
            fail.append("Personal Bio-Data Form loops over %s, which is no Employee table" % variable[:30])
            continue
        columns = {f["fieldname"] for f in spec_json["fields"]}
        for attribute in set(re.findall(r"\brow\.([a-z_]+)", body)):
            if attribute not in columns:
                fail.append("Personal Bio-Data Form prints %s.%s, which does not exist" % (spec_json["name"], attribute))
    if len({v for v in padded.values()}) != 6:
        fail.append("Personal Bio-Data Form must pad the paper form's lists (next of kin, children, education, "
                    "certificates, work) and print the parents: %s" % sorted(padded))
raw = re.findall(r"{{-?\s*(?:doc|row)\.[a-z_]+", html)
if raw:
    fail.append("Personal Bio-Data Form must print text through v() so it is escaped: %s" % raw[:3])
print("Personal Bio-Data Form: LPL/HR/16, balanced blocks, every printed field exists, text escaped")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL BIO-DATA CHECKS PASSED")
