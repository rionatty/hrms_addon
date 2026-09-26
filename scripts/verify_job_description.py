"""Checks for the Job Description template on Designation, run without a bench.

jd_rules.py imports nothing from Frappe, so it is loaded directly and its
Key Result Area rules are exercised: the real Head Sales & Marketing split
(LPL/JD/SM/001, 25/20/45/10), a perspective split across several KRAs,
floating-point drift, totals that miss 100%, missing and repeated KRAs, a
KRA with no perspective, bad weightings, a perspective HR added, and the
seeding of the pick lists (fresh, partly there, case clashes, values
already stored). The other JD tables' rules and the moves of old text
sections into them run against the lines of the same JD.

It also checks:
  * every dropdown of the KRA form and of the JD tables is a Link to its
    own master DocType that HR can add to and rename, seeded with every
    value the old dropdowns and text sections held, and no code keeps its
    own copy of the perspective list;
  * the JD row picks from the standard KRA master and fetches the
    perspective from a field that exists;
  * the KRA additions keep the KPI Library contract — the exact fieldnames
    of the "KPI Library" sheet in the Part 2 master-data template given to
    Luuka, with its dropdown values as the masters' seeds, so their
    completed sheet imports into KRA;
  * the seeding runs once on existing sites (patch) and on new installs
    (after_install), never on every migrate;
  * hooks, controller and form script are wired to things that exist;
  * every JD table can be filled from a CSV: each has Download / Upload, the
    save hook first repairs what Excel writes into such a file ("25%",
    Windows-1252 quotes and dashes), and the form's Download writes the rows
    Frappe's Upload reads (checked against frappe's grid.js when the
    upstream apps are checked out, see FRAPPE_APPS_ROOT);
  * a Job Requisition's Job Description tab, filled from the Job Title's
    JD: the Responsibilities say only what the careers page may (HRMS
    copies them onto the public Job Opening), escaped, and the subordinates
    come from the Reporting Relationships.

    python scripts/verify_job_description.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
CHILD_DIR =os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype", "jd_key_result_area")
TABLE_FIELD = "custom_jd_key_result_areas"
fail = []

# The "KPI Library" sheet of "Luuka Plastics - ERPNext HR Process Masters
# Template (Part 2).xlsx": its field-mapping row and its dropdown lists.
KPI_LIBRARY_CONTRACT = {
    "custom_applies_to": ["Machine Operator", "Shift Supervisor", "Production Officer", "Production Manager",
                          "Department Staff", "Supervisory", "Management", "All Staff"],
    "custom_unit": ["%", "Metres", "Pieces", "Hours", "Count", "UGX"],
    "custom_target": None,  # free text
    "custom_source": ["Luuka Prod", "Biometric", "Manual", "ERPNext", "Excel"],
    "custom_frequency": ["Monthly", "Quarterly", "Semi-Annual", "Annual", "On Demand", "Once"],
}


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def options(field):
    return [o for o in (field.get("options") or "").split("\n") if o]


spec = importlib.util.spec_from_file_location("jd_rules", os.path.join(REPO, "hrms_addon", "hrms_addon", "jd_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)  # proves it has no Frappe import
print("loaded jd_rules.py without Frappe")

custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
kra_fields = {f["fieldname"]: f for f in custom if f["dt"] == "KRA"}
child = json.loads(read("hrms_addon", "hrms_addon", "doctype", "jd_key_result_area", "jd_key_result_area.json"))
child_fields = {f["fieldname"]: f for f in child["fields"]}
js = read("hrms_addon", "public", "js", "designation.js")
glue = read("hrms_addon", "hrms_addon", "designation.py")

def doctype_json(name):
    folder = name.lower().replace(" ", "_")
    return json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))


# ── 1. The pick lists are masters HR maintains ───────────────────────
# Every dropdown on KRA and in the JD tables links to its own master
# DocType; nothing that reads the lists may hold a copy of them.
for fieldname, master in rules.KRA_FIELD_MASTERS.items():
    f = kra_fields.get(fieldname) or {}
    if (f.get("fieldtype"), f.get("options")) != ("Link", master):
        fail.append("KRA.%s must be a Link to %s, is %s %r" % (fieldname, master, f.get("fieldtype"), f.get("options")))
if set(rules.KRA_FIELD_MASTERS.values()) != set(rules.KRA_MASTERS):
    fail.append("KRA_FIELD_MASTERS and KRA_MASTERS name different masters")
for (table, fieldname), master in rules.JD_FIELD_MASTERS.items():
    try:
        f = next((x for x in doctype_json(table)["fields"] if x["fieldname"] == fieldname), {})
    except OSError:
        fail.append("%s has no DocType JSON" % table)
        continue
    if (f.get("fieldtype"), f.get("options")) != ("Link", master):
        fail.append("%s.%s must be a Link to %s, is %s %r" % (table, fieldname, master, f.get("fieldtype"), f.get("options")))
if set(rules.JD_FIELD_MASTERS.values()) != set(rules.JD_MASTERS):
    fail.append("JD_FIELD_MASTERS and JD_MASTERS name different masters")
if rules.MASTERS != {**rules.KRA_MASTERS, **rules.JD_MASTERS} or set(rules.FIELD_MASTERS.values()) != set(rules.MASTERS):
    fail.append("MASTERS / FIELD_MASTERS must cover exactly the KRA and JD pick lists")
# Every Select left in a JD child table would be a dropdown HR cannot extend
for folder in sorted(os.listdir(os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype"))):
    if folder.startswith("jd_"):
        spec_json = json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))
        for f in spec_json["fields"]:
            if f["fieldtype"] == "Select":
                fail.append("%s.%s is still a Select: make it a Link to a pick list" % (spec_json["name"], f["fieldname"]))

for master, (name_field, seeds) in rules.MASTERS.items():
    folder = master.lower().replace(" ", "_")
    try:
        spec_json = json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))
    except OSError:
        fail.append("master %s has no DocType JSON" % master)
        continue
    fields = {f["fieldname"]: f for f in spec_json["fields"]}
    if spec_json.get("istable") or spec_json.get("module") != "HRMS Addon" or spec_json.get("name") != master:
        fail.append("%s must be an HRMS Addon master (not a child table)" % master)
    if spec_json.get("autoname") != "field:%s" % name_field or not (fields.get(name_field) or {}).get("reqd"):
        fail.append("%s must be named by its mandatory %s field" % (master, name_field))
    if not spec_json.get("allow_rename"):
        fail.append("%s must allow rename, so fixing a value updates every document using it" % master)
    if not spec_json.get("quick_entry"):
        fail.append("%s should open in quick entry when created from the form that picks it" % master)
    # Data Import lists only DocTypes with allow_import (frappe/utils/user.py
    # can_import), so without it HR can only type a list in one value at a time
    if not spec_json.get("allow_import"):
        fail.append("%s must allow Data Import: HR loads these lists in bulk" % master)
    if len(set(s.lower() for s in seeds)) != len(seeds) or not all(s and s == s.strip() for s in seeds):
        fail.append("%s seeds must be distinct, non-blank and trimmed: %s" % (master, list(seeds)))
    perms = {p["role"]: p for p in spec_json.get("permissions", [])}
    for role in ("HR Manager", "HR User"):
        if not all((perms.get(role) or {}).get(k) for k in ("read", "write", "create")):
            fail.append("%s: %s must be able to add values" % (master, role))
    classname = master.replace(" ", "").replace("-", "")
    if not re.search(r"^class %s\(Document\):" % classname, read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py"), re.M):
        fail.append("%s controller class must be %s" % (master, classname))
    if not os.path.exists(os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype", folder, "__init__.py")):
        fail.append("%s folder is missing __init__.py" % master)
    # The picker lists values in the DocType's sort order: the template's
    # order (seeded in it), then HR's additions — not newest first.
    if master != "KRA Perspective" and (spec_json.get("sort_field"), spec_json.get("sort_order")) != ("creation", "ASC"):
        fail.append("%s must list values in the order they were added (creation ASC)" % master)
perspective_json = json.loads(read("hrms_addon", "hrms_addon", "doctype", "kra_perspective", "kra_perspective.json"))
display_order = next((f for f in perspective_json["fields"] if f["fieldname"] == "sort_order"), {})
if display_order.get("fieldtype") != "Int" or (perspective_json.get("sort_field"), perspective_json.get("sort_order")) != ("sort_order", "ASC"):
    fail.append("KRA Perspective needs an Int Display Order (sort_order) and to list by it ascending")
if display_order.get("default") or not display_order.get("allow_in_quick_entry"):
    fail.append("KRA Perspective Display Order must be offered in quick entry and start blank")
perspective_controller = read("hrms_addon", "hrms_addon", "doctype", "kra_perspective", "kra_perspective.py")
if not re.search(r"def before_insert\(self\):\s*\n(?:\s*#[^\n]*\n)*\s*if not self\.sort_order:\s*\n\s*self\.sort_order = jd_rules\.next_display_order\(",
                 perspective_controller):
    fail.append("KRA Perspective must give a perspective added without a Display Order the next one (before_insert)")
for name in rules.PERSPECTIVES:
    if '"%s"' % name in js:
        fail.append("designation.js hard-codes the perspective %r — perspectives come from the master" % name)
if "get_perspective_order" not in js or not re.search(r"@frappe\.whitelist\(\)\s*\ndef get_perspective_order\(", glue):
    fail.append("designation.js must get the perspective order from the whitelisted get_perspective_order")

# The seeds hold every value the old JD dropdowns and text sections could
# produce, so nothing moved across needs a value its list lacks.
def seeds_of(master):
    return set(rules.JD_MASTERS.get(master, (None, ()))[1])


for kind, master in (("reporting", "JD Relationship Type"), ("stakeholder", "JD Stakeholder Type"),
                     ("authority", "JD Authority Level"), ("horizon", "JD Horizon")):
    written = {label for k, label in rules.OLD_TEXT_FIELDS.values() if k == kind}
    if not written <= seeds_of(master):
        fail.append("%s seeds must include every value the old text migration writes: %s" % (master, sorted(written - seeds_of(master))))
for mapping, master in ((rules.ISO_TEXT_FIELDS, "JD ISO Standard"), (rules.SPECIFICATION_TEXT_FIELDS, "JD Specification Type"),
                        (rules.COMPETENCY_TEXT_FIELDS, "JD Competency Category")):
    if not set(mapping.values()) <= seeds_of(master):
        fail.append("%s seeds must include every value the profile migration writes: %s" % (master, sorted(set(mapping.values()) - seeds_of(master))))
print("pick lists: %d fields link to %d HR-maintained masters; no dropdown left fixed, no copy of the perspective list"
      % (len(rules.FIELD_MASTERS), len(rules.MASTERS)))

# ── 2. The JD row picks from the KRA master ──────────────────────────
kra = child_fields.get("kra") or {}
if (kra.get("fieldtype"), kra.get("options"), kra.get("reqd"), kra.get("in_list_view")) != ("Link", "KRA", 1, 1):
    fail.append("JD Key Result Area.kra must be a mandatory Link to KRA shown in the grid")
perspective = child_fields.get("perspective") or {}
if perspective.get("fetch_from") != "kra.custom_perspective":
    fail.append("JD Key Result Area.perspective must fetch from kra.custom_perspective")
if not perspective.get("read_only"):
    fail.append("JD Key Result Area.perspective must be read-only: the KRA decides it")
if "custom_perspective" not in kra_fields:
    fail.append("the fetch target KRA.custom_perspective is not in the fixtures")
if (perspective.get("fieldtype"), perspective.get("options")) != ("Link", "KRA Perspective"):
    fail.append("JD Key Result Area.perspective must link to KRA Perspective, like the KRA field it fetches")
if child.get("field_order") != list(child_fields):
    fail.append("child field_order %s does not match its fields" % child.get("field_order"))
if sum(f.get("columns") or 0 for f in child["fields"] if f.get("in_list_view")) > 10:
    fail.append("grid columns exceed Frappe's 10-column row")
if not child.get("istable") or child.get("module") != "HRMS Addon" or child.get("name") != "JD Key Result Area":
    fail.append("JD Key Result Area must be an HRMS Addon child table")
if not re.search(r"^class JDKeyResultArea\(Document\):", read("hrms_addon", "hrms_addon", "doctype", "jd_key_result_area", "jd_key_result_area.py"), re.M):
    fail.append("controller class must be JDKeyResultArea")
if not os.path.exists(os.path.join(CHILD_DIR, "__init__.py")):
    fail.append("child doctype folder is missing __init__.py")
print("JD row: KRA picked from the master, perspective fetched read-only, grid fits")

# ── 3. KRA additions keep the KPI Library contract ───────────────────
# The sheet's column mapping names the KRA fields; its dropdown values are
# what each master is seeded with, so the completed sheet imports cleanly.
for fieldname, expected in KPI_LIBRARY_CONTRACT.items():
    f = kra_fields.get(fieldname)
    if not f:
        fail.append("KRA.%s missing — the KPI Library sheet maps a column to it" % fieldname)
    elif expected is not None:
        master = rules.KRA_FIELD_MASTERS.get(fieldname)
        seeded = list(rules.KRA_MASTERS.get(master, (None, ()))[1])
        if seeded != expected:
            fail.append("%s is seeded with %s, the KPI Library dropdown is %s" % (master, seeded, expected))
p = kra_fields.get("custom_perspective", {})
if p.get("reqd"):
    fail.append("KRA.custom_perspective must not be mandatory: the KPI Library sheet has no perspective column")
if not p.get("allow_in_quick_entry"):
    fail.append("KRA.custom_perspective should appear when a KRA is created from the JD picker")
setters = {s["name"]: s for s in json.loads(read("hrms_addon", "fixtures", "property_setter.json"))}
search = setters.get("KRA-main-search_fields", {}).get("value", "")
if "custom_perspective" not in search.split(","):
    fail.append("KRA search_fields should include custom_perspective so the picker shows it")
print("KRA: perspective plus the 5 KPI Library fields with the template's exact names and dropdowns")

# ── 4. Behaviour ─────────────────────────────────────────────────────
F, C, I, L = rules.PERSPECTIVES


def rows(*items):
    return [{"kra": k, "perspective": p, "weighting": w} for k, p, w in items]


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


class Row:  # Frappe child rows are objects, not dicts
    def __init__(self, kra, perspective, weighting):
        self.kra, self.perspective, self.weighting = kra, perspective, weighting


check = rules.key_result_area_errors
expect("empty table is allowed", check([]))
expect("LPL/JD/SM/001 split 25/20/45/10",
       check(rows(("Sales Revenue", F, 25), ("Key Accounts", C, 20), ("Sales Strategy", I, 45), ("Team Capability", L, 10))))
expect("one perspective split across KRAs",
       check(rows(("Sales Revenue", F, 10), ("Debt Recovery", F, 10), ("Budget", F, 5),
                  ("Key Accounts", C, 20), ("Sales Strategy", I, 45), ("Team Capability", L, 10))))
expect("float drift 15.7/22.1/51.4/10.8",
       check(rows(("A", F, 15.7), ("B", C, 22.1), ("C", I, 51.4), ("D", L, 10.8))))
expect("weightings as strings", check(rows(("A", F, "40"), ("B", I, "60"))))
expect("object rows", check([Row("A", F, 50), Row("B", L, 50)]))
expect("total short of 100", check(rows(("A", F, 25), ("B", C, 20), ("C", I, 45))),
       "must total 100%", "currently 90%", "Learning & Growth 0%")
expect("total over 100", check(rows(("A", F, 60), ("B", L, 60))), "currently 120%")
expect("same KRA twice", check(rows(("Sales Revenue", F, 50), ("Sales Revenue", F, 50))),
       "KRA Sales Revenue is listed more than once")
expect("row without a KRA", check(rows(("", None, 100))), "choose a KRA")
expect("KRA with no perspective", check(rows(("Legacy KRA", None, 100))),
       "KRA Legacy KRA has no Balanced Scorecard perspective")
expect("weighting out of range", check(rows(("A", F, 150), ("B", C, -50))), "between 0 and 100%")
expect("non-numeric weighting", check(rows(("A", F, "abc"), ("B", C, 100))), "must be a number")
totals = rules.perspective_totals(rows(("A", F, 10), ("B", F, 15), ("C", I, 75)))
if totals != {F: 25.0, C: 0.0, I: 75.0, L: 0.0}:
    fail.append("perspective_totals wrong: %s" % totals)

# HR can add perspectives: a new one is valid, and totals follow the master's
# order with anything unlisted after it.
expect("perspective HR added", check(rows(("A", F, 50), ("B", "Sustainability", 50))))
ordered = rules.perspective_totals(rows(("A", "Sustainability", 30), ("B", L, 70)), perspectives=[L, F])
if list(ordered.items()) != [(L, 70.0), (F, 0.0), ("Sustainability", 30.0)]:
    fail.append("perspective_totals must follow the given order, then extras: %s" % ordered)
message = check(rows(("A", F, 20)), [L, F])
if not message or "Learning & Growth 0%, Financial 20%" not in message[-1]:
    fail.append("the totals message must follow the master's order: %s" % message)

# Seeding the pick lists
plan = rules.seed_plan({})
for master, (name_field, seeds) in rules.KRA_MASTERS.items():
    if [r[name_field] for r in plan[master]] != list(seeds):
        fail.append("fresh seed of %s wrong: %s" % (master, plan[master]))
if [r["sort_order"] for r in plan["KRA Perspective"]] != [10, 20, 30, 40]:
    fail.append("seeded perspectives must be ordered 10/20/30/40: %s" % plan["KRA Perspective"])
plan = rules.seed_plan({"KRA Unit": ["%", "metres"], "KRA Review Frequency": ["Monthly"]})
if [r["unit_name"] for r in plan["KRA Unit"]] != ["Pieces", "Hours", "Count", "UGX"]:
    fail.append("seed must skip values already there, ignoring case (metres = Metres): %s" % plan["KRA Unit"])
if "Monthly" in [r["frequency_name"] for r in plan["KRA Review Frequency"]]:
    fail.append("seed must not recreate an existing value")
plan = rules.seed_plan({}, {"KRA Perspective": ["Financial", "Sustainability", "", None], "KRA Data Source": ["SAP", "sap"]})
extra = [r for r in plan["KRA Perspective"] if r["perspective_name"] == "Sustainability"]
if len(plan["KRA Perspective"]) != 5 or not extra or extra[0]["sort_order"] < 100:
    fail.append("a perspective in use must be seeded once, after the defaults: %s" % plan["KRA Perspective"])
if [r["source_name"] for r in plan["KRA Data Source"]].count("SAP") != 1 or len(plan["KRA Data Source"]) != 6:
    fail.append("values in use must be seeded once, ignoring case: %s" % plan["KRA Data Source"])
for orders, expected in (([], 10), ([10, 20, 30, 40], 50), ([10, None, 105, 0], 110), ([0, 0], 10), ([40, 45], 50)):
    if rules.next_display_order(orders) != expected:
        fail.append("next_display_order(%s) is %s, expected %s" % (orders, rules.next_display_order(orders), expected))
plan = rules.seed_plan({})
if set(plan) != set(rules.MASTERS):
    fail.append("seed_plan with no lists named must plan every pick list: %s" % sorted(plan))
for master, (name_field, seeds) in rules.JD_MASTERS.items():
    if [r[name_field] for r in plan[master]] != list(seeds) or any(r["doctype"] != master for r in plan[master]):
        fail.append("fresh seed of %s wrong: %s" % (master, plan[master]))
plan = rules.seed_plan({"JD Horizon": ["short-term"]}, {"JD Relationship Type": ["Direct", "Dotted Line"],
                                                        "KRA Unit": ["Tonnes"]}, rules.JD_MASTERS)
if set(plan) != set(rules.JD_MASTERS):
    fail.append("seed_plan must plan only the lists it is given: %s" % sorted(plan))
if [r["horizon"] for r in plan["JD Horizon"]] != ["Medium-Term", "Long-Term"]:
    fail.append("JD Horizon seed must skip Short-Term, already there as short-term: %s" % plan["JD Horizon"])
if [r["relationship_type"] for r in plan["JD Relationship Type"]] != ["Direct", "Indirect", "Dotted Line"]:
    fail.append("a relationship type in use must be seeded once, after the defaults: %s" % plan["JD Relationship Type"])
print("behaviour: JD split, split perspective, drift, totals, repeats, gaps, bad values, new perspectives and seeding correct")

# ── 4b. The other section tables ─────────────────────────────────────
EXPECTED_TABLE_FIELDS = {
    "JD Reporting Line": ["relationship", "designation", "scope"],
    "JD Stakeholder": ["stakeholder_type", "stakeholder", "interaction"],
    "JD Decision Authority": ["authority_level", "decisions", "constraints"],
    "JD Planning Horizon": ["horizon", "work_cycle"],
    "JD ISO Responsibility": ["standard", "accountabilities"],
    "JD Job Specification": ["specification_type", "requirement", "keywords", "minimum_years", "priority"],
    "JD Competency": ["category", "competency", "priority"],
}
if set(rules.TABLES.values()) != set(EXPECTED_TABLE_FIELDS):
    fail.append("jd_rules.TABLES %s differ from the expected tables" % sorted(rules.TABLES.values()))
by_name = {f["name"]: f for f in custom}
for table_field, child_doctype in rules.TABLES.items():
    parent_field = by_name.get("Designation-%s" % table_field)
    if not parent_field or parent_field.get("fieldtype") != "Table" or parent_field.get("options") != child_doctype:
        fail.append("Designation.%s must be a Table of %s" % (table_field, child_doctype))
    folder = child_doctype.lower().replace(" ", "_")
    path = os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype", folder)
    try:
        spec_json = json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))
    except OSError:
        fail.append("child doctype %s has no JSON" % child_doctype)
        continue
    names = [f["fieldname"] for f in spec_json["fields"]]
    if names != EXPECTED_TABLE_FIELDS[child_doctype] or spec_json.get("field_order") != names:
        fail.append("%s fields %s, expected %s" % (child_doctype, names, EXPECTED_TABLE_FIELDS[child_doctype]))
    if not spec_json.get("istable") or spec_json.get("module") != "HRMS Addon" or spec_json.get("name") != child_doctype:
        fail.append("%s must be an HRMS Addon child table" % child_doctype)
    if sum(f.get("columns") or 0 for f in spec_json["fields"] if f.get("in_list_view")) > 10:
        fail.append("%s grid exceeds 10 columns" % child_doctype)
    classname = child_doctype.replace(" ", "").replace("-", "")
    if not re.search(r"^class %s\(Document\):" % classname, read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py"), re.M):
        fail.append("%s controller class must be %s" % (child_doctype, classname))
    if not os.path.exists(os.path.join(path, "__init__.py")):
        fail.append("%s folder is missing __init__.py" % child_doctype)

if rules.JD_MASTERS["JD Horizon"][1] != rules.HORIZONS:
    fail.append("JD Horizon must be seeded with jd_rules.HORIZONS")


def table_field(table, fieldname):
    return next((f for f in doctype_json(table)["fields"] if f["fieldname"] == fieldname), {})


for table, fieldname, fieldtype, options_ in (
    ("JD Reporting Line", "designation", "Link", "Designation"),
    ("JD Competency", "competency", "Link", "Skill"),
    ("JD ISO Responsibility", "accountabilities", "Small Text", None),
    ("JD Job Specification", "requirement", "Small Text", None),
):
    f = table_field(table, fieldname)
    if (f.get("fieldtype"), f.get("options"), f.get("reqd"), f.get("in_list_view")) != (fieldtype, options_, 1, 1):
        fail.append("%s.%s must be a mandatory %s shown in the grid" % (table, fieldname, "Link to %s" % options_ if options_ else fieldtype))
if table_field("JD Job Specification", "priority").get("reqd"):
    fail.append("JD Job Specification.priority must stay optional: the JD's wording does not always say")
for fieldname in ("custom_jd_iso_responsibilities", "custom_jd_specifications", "custom_jd_competencies"):
    f = by_name.get("Designation-%s" % fieldname) or {}
    if f.get("reqd"):
        fail.append("Designation.%s must not be mandatory: not every Job Title has a written JD yet" % fieldname)
print("section tables: %d child tables wired, fields, grid width and classes correct" % len(rules.TABLES))

# Rules across the tables
t = rules.jd_table_errors
expect("clean tables", t("Head Sales & Marketing", "Executive Director",
                         [{"relationship": "Direct", "designation": "Sales Manager", "scope": "PE/Kawempe"},
                          {"relationship": "Direct", "designation": "Sales Manager", "scope": "PP/Namanve"}],
                         [{"stakeholder_type": "Internal", "stakeholder": "CFO"}, {"stakeholder_type": "External", "stakeholder": "CFO"}],
                         [{"authority_level": "Strategic", "decisions": "Pricing"}], [{"horizon": "Short-Term"}, {"horizon": "Long-Term"}]))
expect("reports to itself", t("Sales Manager", None, [{"relationship": "Direct", "designation": "Sales Manager"}], [], [], []),
       "cannot report to itself")
expect("reports-to listed as a report", t("Head Sales & Marketing", "Executive Director",
                                          [{"relationship": "Indirect", "designation": "Executive Director"}], [], [], []),
       "is this role's Reports To")
expect("same position and scope twice", t("X", None, [{"relationship": "Direct", "designation": "Sales Manager", "scope": "PE"},
                                                      {"relationship": "Indirect", "designation": "Sales Manager", "scope": "pe"}], [], [], []),
       "Sales Manager (pe) is already listed in row 1")
expect("stakeholder twice", t("X", None, [], [{"stakeholder_type": "Internal", "stakeholder": "CFO"},
                                             {"stakeholder_type": "Internal", "stakeholder": "cfo"}], [], []),
       "is already listed in row 1")
expect("decision repeated", t("X", None, [], [], [{"authority_level": "Strategic", "decisions": "Pricing  frameworks"},
                                                 {"authority_level": "Strategic", "decisions": "pricing frameworks"}], []),
       "repeats row 1")
expect("horizon twice", t("X", None, [], [], [], [{"horizon": "Short-Term"}, {"horizon": "Short-Term"}]),
       "Use one row per horizon")
ISO_9001, IMS = rules.ISO_STANDARDS[0], rules.ISO_STANDARDS[-1]
ACADEMIC, TRAINING, EXPERIENCE = rules.SPECIFICATION_TYPES
TECHNICAL, BEHAVIOURAL = rules.COMPETENCY_CATEGORIES
expect("clean ISO, specification and competency tables", t(
    "Head Sales & Marketing", None, [], [], [], [],
    iso_responsibilities=[{"standard": ISO_9001, "accountabilities": "Champion zero customer complaints."},
                          {"standard": IMS, "accountabilities": "Participate in IMS management reviews."}],
    specifications=[{"specification_type": ACADEMIC, "requirement": "Bachelor's Degree in Commerce", "priority": "Essential"},
                    {"specification_type": TRAINING, "requirement": "Bachelor's Degree in Commerce"},
                    {"specification_type": EXPERIENCE, "requirement": "Minimum 8 years in sales"}],
    competencies=[{"category": TECHNICAL, "competency": "Key account management"},
                  {"category": BEHAVIOURAL, "competency": "Negotiation and persuasion"}]))
expect("standard twice", t("X", None, [], [], [], [], iso_responsibilities=[
    {"standard": ISO_9001, "accountabilities": "Complaints"}, {"standard": ISO_9001, "accountabilities": "NCRs"}]),
    "ISO Responsibilities row 2: %s is already in row 1. Put all its accountabilities in one row." % ISO_9001)
expect("specification repeated", t("X", None, [], [], [], [], specifications=[
    {"specification_type": ACADEMIC, "requirement": "Bachelor's  Degree in Commerce"},
    {"specification_type": ACADEMIC, "requirement": "bachelor's degree in commerce"}]),
    "Ideal Job Specifications row 2 repeats row 1.")
expect("competency under both categories", t("X", None, [], [], [], [], competencies=[
    {"category": TECHNICAL, "competency": "Negotiation"}, {"category": BEHAVIOURAL, "competency": "negotiation"}]),
    "Competency Framework row 2: negotiation is already listed in row 1.")
expect("competency repeated in another case", t("X", None, [], [], [], [], competencies=[
    {"category": TECHNICAL, "competency": "key account management"}, {"category": TECHNICAL, "competency": "Key Account Management"}]),
    "Competency Framework row 2: Key Account Management is already listed in row 1.")
expect("blank rows are left to the mandatory check", t("X", None, [], [], [], [], iso_responsibilities=[{}, {}],
                                                       specifications=[{}, {}], competencies=[{}, {}]))

# Moving the old text into the tables, using the lines of LPL/JD/SM/001
lookup = rules.designation_lookup(["Sales Manager", "Senior Sales/CCE", "Executive Director", "Receptionist"])
if rules.parse_reporting_line("Sales Manager – PE/Kawempe", lookup) != ("Sales Manager", "PE/Kawempe"):
    fail.append("en-dash reporting line not parsed")
if rules.parse_reporting_line("Senior Sales/CCE (all plants)", lookup) != ("Senior Sales/CCE", "all plants"):
    fail.append("parenthetical reporting line not parsed")
if rules.parse_reporting_line("executive director", lookup) != ("Executive Director", ""):
    fail.append("reporting line should match a Job Title case-insensitively and return its exact name")
if rules.parse_reporting_line("Graphics Designers (all plants)", lookup) is not None:
    fail.append("a Job Title that does not exist must not be guessed")
if rules.split_parenthetical("Procurement (raw materials for custom orders)") != ("Procurement", "raw materials for custom orders"):
    fail.append("stakeholder interaction not split")
if rules.split_lines("• Executive Director\n\n▪ CFO (credit, collections)\r\n - HR Manager ") != ["Executive Director", "CFO (credit, collections)", "HR Manager"]:
    fail.append("split_lines does not strip bullets and blanks")

jd_text = {
    "custom_jd_direct_reports": "Sales Manager – PE/Kawempe\nSales Manager – PP/Namanve\nSales Manager – PIB/Matugga",
    "custom_jd_indirect_reports": "Senior Sales/CCE (all plants)\nGraphics Designers (all plants)\nReceptionist (all plants)",
    "custom_jd_internal_stakeholders": "Executive Director\nCFO (credit, collections)",
    "custom_jd_external_stakeholders": "Distributors and wholesalers\n" + "x" * 150,
    "custom_jd_strategic_authority": "Group sales strategy, pricing frameworks, brand direction.",
    "custom_jd_short_term": "Monthly sales cycles",
    "custom_jd_long_term": "Annual and 3-year sales strategy",
}
tables, unconverted = rules.text_sections_to_rows(jd_text, lookup)
reporting = tables["custom_jd_reporting_lines"]
if [(r["relationship"], r["designation"], r["scope"]) for r in reporting] != [
    ("Direct", "Sales Manager", "PE/Kawempe"), ("Direct", "Sales Manager", "PP/Namanve"),
    ("Direct", "Sales Manager", "PIB/Matugga"), ("Indirect", "Senior Sales/CCE", "all plants"),
    ("Indirect", "Receptionist", "all plants")]:
    fail.append("reporting rows from the JD text wrong: %s" % reporting)
if [(r["stakeholder_type"], r["stakeholder"], r["interaction"]) for r in tables["custom_jd_stakeholders"]] != [
    ("Internal", "Executive Director", ""), ("Internal", "CFO", "credit, collections"), ("External", "Distributors and wholesalers", "")]:
    fail.append("stakeholder rows from the JD text wrong: %s" % tables["custom_jd_stakeholders"])
if tables["custom_jd_decision_authorities"] != [{"authority_level": "Strategic", "decisions": "Group sales strategy, pricing frameworks, brand direction."}]:
    fail.append("authority rows from the JD text wrong")
if [(r["horizon"], r["work_cycle"]) for r in tables["custom_jd_planning_horizons"]] != [
    ("Short-Term", "Monthly sales cycles"), ("Long-Term", "Annual and 3-year sales strategy")]:
    fail.append("horizon rows from the JD text wrong")
if not any("Graphics Designers" in line for line in unconverted):
    fail.append("a report naming a missing Job Title must be kept for the comment, not dropped")
if not any("x" * 141 in line for line in unconverted):
    fail.append("a value longer than a Data field must be kept for the comment, not inserted")
if len(unconverted) != 2:
    fail.append("expected exactly 2 unconverted lines, got %s" % unconverted)
converted = sum(len(rows) for rows in tables.values())
print("section rules and text migration: %d rows moved from the JD text, %d lines kept for the comment" % (converted, len(unconverted)))

# The migration patch
patch_src = read("hrms_addon", "patches", "v1_0", "jd_text_sections_to_tables.py")
if "hrms_addon.patches.v1_0.jd_text_sections_to_tables" not in read("hrms_addon", "patches.txt"):
    fail.append("jd_text_sections_to_tables is not listed in patches.txt")
for needle, why in (
    ("jd_rules.text_sections_to_rows", "must use the tested conversion"),
    ("frappe.db.exists(child", "must not add rows to a table that already has some"),
    ('"parentfield": field', "must set parentfield: the Table fields do not exist yet when it runs"),
    ("except Exception", "must not let one Job Title stop the whole migrate"),
    ('"doctype": "Comment"', "must record unconverted lines instead of dropping them"),
    ("escape_html", "must escape user text written into the comment"),
):
    if needle not in patch_src:
        fail.append("patch %s" % why)
removed = set(re.findall(r'"(Designation-custom_jd_[a-z0-9_]+)"', patch_src))
for field in rules.OLD_TEXT_FIELDS:
    if "Designation-%s" % field not in removed:
        fail.append("patch reads %s but never deletes the field" % field)
if any(name in by_name for name in removed):
    fail.append("patch deletes fields that are still in the fixtures: %s" % sorted(removed & set(by_name)))
if "jd_rules.jd_table_errors" not in glue:
    fail.append("designation.py does not apply jd_table_errors on save")
print("migration patch: listed, uses the tested conversion, idempotent, defensive, deletes exactly the old fields")

# Moving ISO Responsibilities, Ideal Job Specifications and Competency
# Framework into their tables, using the lines of LPL/JD/SM/001
OLD_PROFILE_FIELDS = {
    "iso": ["custom_jd_iso_9001", "custom_jd_iso_22000", "custom_jd_iso_45001", "custom_jd_iso_14001", "custom_jd_ims_leadership"],
    "specification": ["custom_jd_academic", "custom_jd_professional", "custom_jd_experience"],
    "competency": ["custom_jd_technical_competencies", "custom_jd_behavioural_competencies"],
}
for kind, mapping in (("iso", rules.ISO_TEXT_FIELDS), ("specification", rules.SPECIFICATION_TEXT_FIELDS),
                      ("competency", rules.COMPETENCY_TEXT_FIELDS)):
    if sorted(mapping) != sorted(OLD_PROFILE_FIELDS[kind]):
        fail.append("the %s migration must read exactly the old fields %s, reads %s" % (kind, OLD_PROFILE_FIELDS[kind], sorted(mapping)))
if rules.PROFILE_TEXT_FIELDS != {**rules.ISO_TEXT_FIELDS, **rules.SPECIFICATION_TEXT_FIELDS, **rules.COMPETENCY_TEXT_FIELDS}:
    fail.append("PROFILE_TEXT_FIELDS must be the ISO, specification and competency fields together")
if (rules.ISO_TEXT_FIELDS.get("custom_jd_iso_45001"), rules.ISO_TEXT_FIELDS.get("custom_jd_ims_leadership"),
        rules.SPECIFICATION_TEXT_FIELDS.get("custom_jd_professional"), rules.COMPETENCY_TEXT_FIELDS.get("custom_jd_behavioural_competencies")) != (
        "ISO 45001 (Occupational Health & Safety)", "IMS Leadership", "Professional Training & Certification", "Behavioural"):
    fail.append("an old field maps to the wrong list value: %s" % rules.PROFILE_TEXT_FIELDS)

profile_text = {
    "custom_jd_iso_9001": "Champion zero customer complaints across all plants;\nensure NCRs are closed.  ",
    "custom_jd_iso_22000": "   ",
    "custom_jd_ims_leadership": "Participate in IMS management reviews representing the Sales & Marketing function.",
    "custom_jd_academic": "• Bachelor’s Degree in Business Administration, Commerce, Marketing, or a related field.\n\n"
                          "• Post Graduate Diploma or Master’s Degree is strongly preferred.",
    "custom_jd_professional": "Chartered Institute of Marketing (CIM) — professional certification desirable.\n"
                              "Key Account Management and Strategic Selling programmes.\n"
                              "key account management and  strategic selling programmes.",
    "custom_jd_experience": "- Minimum 8 years’ experience in sales and marketing.",
    "custom_jd_technical_competencies": "• Sales strategy development and execution\n• Key account management\n"
                                        "• Negotiation and persuasion\n• " + "y" * 150,
    "custom_jd_behavioural_competencies": "• Negotiation and persuasion\n• Customer-centric focus\n"
                                          "• Results <b>orientation</b>\n• Customer-centric   focus",
}
existing_skills = rules.name_lookup(["Key Account Management", "Customer-Centric Focus"])
before = dict(existing_skills)
tables, new_skills, unconverted = rules.profile_sections_to_rows(profile_text, existing_skills)
if existing_skills != before:
    fail.append("profile_sections_to_rows must not change the Skill lookup it is given (the patch merges it only after a success)")
if tables["custom_jd_iso_responsibilities"] != [
        {"standard": ISO_9001, "accountabilities": "Champion zero customer complaints across all plants;\nensure NCRs are closed."},
        {"standard": IMS, "accountabilities": "Participate in IMS management reviews representing the Sales & Marketing function."}]:
    fail.append("ISO rows from the JD text wrong (one whole row per filled standard, in order): %s" % tables["custom_jd_iso_responsibilities"])
if [(r["specification_type"], r["requirement"]) for r in tables["custom_jd_specifications"]] != [
        (ACADEMIC, "Bachelor’s Degree in Business Administration, Commerce, Marketing, or a related field."),
        (ACADEMIC, "Post Graduate Diploma or Master’s Degree is strongly preferred."),
        (TRAINING, "Chartered Institute of Marketing (CIM) — professional certification desirable."),
        (TRAINING, "Key Account Management and Strategic Selling programmes."),
        (EXPERIENCE, "Minimum 8 years’ experience in sales and marketing.")]:
    fail.append("specification rows from the JD text wrong (one per line, bullets off, repeats once): %s" % tables["custom_jd_specifications"])
if [(r["category"], r["competency"]) for r in tables["custom_jd_competencies"]] != [
        (TECHNICAL, "Sales strategy development and execution"), (TECHNICAL, "Key Account Management"),
        (TECHNICAL, "Negotiation and persuasion"), (BEHAVIOURAL, "Customer-Centric Focus")]:
    fail.append("competency rows from the JD text wrong (existing Skills matched ignoring case): %s" % tables["custom_jd_competencies"])
if new_skills != ["Sales strategy development and execution", "Negotiation and persuasion"]:
    fail.append("only competencies the Skill list lacks become new Skills, once each: %s" % new_skills)
if not any("y" * 141 in line and "longer than" in line for line in unconverted):
    fail.append("a competency too long to be a Skill name must not become a Skill; keep it for the comment")
if not any("<b>" in line for line in unconverted) or any("<" in name for name in new_skills):
    fail.append("a competency with < or > cannot be a Skill name; keep it for the comment")
if not any("Negotiation and persuasion (already listed as Technical)" in line for line in unconverted):
    fail.append("a competency listed under both categories must keep the second listing for the comment")
if len(unconverted) != 3:
    fail.append("expected exactly 3 unconverted competency lines, got %s" % unconverted)
if rules.skill_name_problem("Skill") is None or rules.skill_name_problem("x" * 140) is not None:
    fail.append("skill_name_problem: 'Skill' is refused by Frappe, 140 characters is allowed")
empty = rules.profile_sections_to_rows({}, {})
if empty != ({"custom_jd_iso_responsibilities": [], "custom_jd_specifications": [], "custom_jd_competencies": []}, [], []):
    fail.append("a Job Title with none of the old text must produce nothing: %s" % (empty,))
print("profile text migration: %d rows, %d new Skills, %d lines kept for the comment"
      % (sum(len(r) for r in tables.values()), len(new_skills), len(unconverted)))

profile_patch = read("hrms_addon", "patches", "v1_0", "jd_profile_sections_to_tables.py")
for needle, why in (
    ("jd_rules.profile_sections_to_rows(values, skills)", "must use the tested conversion"),
    ("frappe.db.exists(", "must not add rows to a table that already has some"),
    ('"parentfield": field', "must set parentfield: the Table fields do not exist yet when it runs"),
    ("frappe.db.savepoint(SAVEPOINT)", "must handle each Job Title inside a savepoint"),
    ("frappe.db.rollback(save_point=SAVEPOINT)", "must roll back a failed Job Title, its new Skills included"),
    ("except Exception", "must not let one Job Title stop the whole migrate"),
    ("skills.update(_move(values, skills))", "must share the Skills a Job Title created only after it succeeded"),
    ('frappe.get_doc({"doctype": "Skill", "skill_name": name}).insert(ignore_permissions=True)',
     "must create the missing Skills before the rows that link to them"),
    ('"doctype": "Comment"', "must record unconverted lines instead of dropping them"),
    ("escape_html", "must escape user text written into the comment"),
    ('frappe.get_all("Skill", pluck="name")', "must match competencies against the existing Skills"),
):
    if needle not in profile_patch:
        fail.append("profile patch %s" % why)
if profile_patch.find("Skill\", \"skill_name\"") > profile_patch.find(".db_insert()"):
    fail.append("profile patch must insert the Skills before the competency rows")
removed = set(re.findall(r'"(Designation-custom_jd_[a-z0-9_]+)"', profile_patch))
expected_removed = {"Designation-%s" % f for f in rules.PROFILE_TEXT_FIELDS} | {
    "Designation-custom_jd_iso_cb", "Designation-custom_jd_specs_cb1", "Designation-custom_jd_specs_cb2", "Designation-custom_jd_competency_cb"}
if removed != expected_removed:
    fail.append("profile patch must delete exactly the old fields and their column breaks: missing %s, extra %s"
                % (sorted(expected_removed - removed), sorted(removed - expected_removed)))
if removed & set(by_name):
    fail.append("profile patch deletes fields that are still in the fixtures: %s" % sorted(removed & set(by_name)))
for keyword in ("iso_responsibilities=doc.get(\"custom_jd_iso_responsibilities\")", "specifications=doc.get(\"custom_jd_specifications\")",
                "competencies=doc.get(\"custom_jd_competencies\")", "screening_questions=doc.get(jd_rules.SCREENING_TABLE)"):
    if keyword not in glue:
        fail.append("designation.py must pass %s to jd_table_errors" % keyword.split("=")[0])
expect("a screening question asked twice",
       t("Machine Operator", None, [], [], [], [], screening_questions=[
           {"question": "Can you work night shifts?"}, {"question": "can you  work night shifts?"},
           {"question": "Expected monthly salary (UGX)"}]),
       "Screening Questions row 2 repeats row 1.")
expect("different questions", t("Machine Operator", None, [], [], [], [], screening_questions=[
    {"question": "Can you work night shifts?"}, {"question": "Expected monthly salary (UGX)"}]))
print("profile patch: uses the tested conversion, savepoint per Job Title, Skills first, deletes exactly the old fields")

# ── 5. Wiring ────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
glue = read("hrms_addon", "hrms_addon", "designation.py")
fixtures = {f["name"]: f for f in custom}

table = fixtures.get("Designation-%s" % TABLE_FIELD)
if not table or table.get("fieldtype") != "Table" or table.get("options") != "JD Key Result Area":
    fail.append("Designation.%s must be a Table of JD Key Result Area" % TABLE_FIELD)
if '"hrms_addon.hrms_addon.designation.validate"' not in hooks or "def validate(doc, method=None)" not in glue:
    fail.append("Designation validate is not wired to designation.validate")
if 'frappe.get_all(\n        "KRA"' not in glue and 'frappe.get_all("KRA"' not in glue:
    fail.append("designation.py must read each perspective from the KRA master, not trust the row")
if "custom_perspective" not in glue:
    fail.append("designation.py does not look up KRA.custom_perspective")
block = re.search(r"^doctype_js = \{(.*?)^\}", hooks, re.S | re.M)
m = re.search(r'"Designation": "([^"]+)"', block.group(1)) if block else None
if not m or not os.path.exists(os.path.join(REPO, "hrms_addon", m.group(1))):
    fail.append("doctype_js for Designation does not point at an existing file")
if hooks.count("\ndoc_events = ") != 1 or hooks.count("\ndoctype_js = ") != 1:
    fail.append("doc_events and doctype_js must each be assigned exactly once in hooks.py")
if "add_child" in js:
    fail.append("designation.js must not pre-fill rows: every row now needs a KRA picked")
for event in ("custom_jd_key_result_areas_add", "custom_jd_key_result_areas_remove", "kra(frm)", "perspective(frm)", "weighting(frm)"):
    if event not in js:
        fail.append("designation.js does not refresh the totals on %s" % event)
if ".toggle(" not in js:
    fail.append("designation.js must set the totals box visibility itself (grid.set_grid_description never re-shows it)")
stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", js, flags=re.S)
for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
    if stripped.count(op) != stripped.count(cl):
        fail.append("designation.js: unbalanced %s%s" % (op, cl))
m = re.search(r'frappe\s*\.xcall\(\s*"([^"]+)"', js)
if not m or m.group(1) != "hrms_addon.hrms_addon.designation.get_perspective_order":
    fail.append("designation.js must call hrms_addon.hrms_addon.designation.get_perspective_order")
if glue.count('frappe.get_all("KRA Perspective", order_by="sort_order asc, name asc"') != 2:
    fail.append("designation.py must order perspectives by Display Order, the same way on save and in the form")
print("wiring: table, doc event, KRA lookup, form script events and totals all resolve")

# Seeding the pick lists: once per site, never on every migrate (HR owns
# the lists after that, so a value they delete must stay deleted).
masters_src = read("hrms_addon", "hrms_addon", "pick_lists.py")
for needle, why in (
    ("jd_rules.seed_plan(", "must use the tested seed plan"),
    ("seed_plan(existing, _values_in_use(masters), masters)", "must seed the values already stored, for exactly the lists asked for"),
    ("get_table_columns(doctype)", "must check a field's column exists (a fresh install has no KRA custom fields yet)"),
    ("FIELD_MASTERS = {**jd_rules.FIELD_MASTERS, **bio_data_rules.BIO_DATA_FIELD_MASTERS}",
     "must know every field that picks from a list"),
    ("for (doctype, fieldname), master in FIELD_MASTERS.items():",
     "must look for stored values in every field that picks from a list"),
    ("MASTERS = {**jd_rules.MASTERS, **bio_data_rules.BIO_DATA_MASTERS, **org_rules.ORG_MASTERS}", "must know every pick list"),
    ("insert(ignore_permissions=True)", "must insert regardless of the migrating user's permissions"),
    ("def seed_kra_masters():\n    seed_masters(jd_rules.KRA_MASTERS)", "seed_kra_masters must seed the KRA lists"),
    ("def seed_jd_masters():\n    seed_masters(jd_rules.JD_MASTERS)", "seed_jd_masters must seed the JD lists"),
    ("def after_install():\n    seed_masters(MASTERS)",
     "after_install must seed every pick list: on a fresh install patches are marked done without running"),
):
    if needle not in masters_src:
        fail.append("pick_lists.py %s" % why)
if os.path.exists(os.path.join(REPO, "hrms_addon", "hrms_addon", "kra_masters.py")):
    fail.append("kra_masters.py is now pick_lists.py: remove the old module")
m = re.search(r"^after_install = (\[.*?^\]|\"[^\"]*\")", hooks, re.S | re.M)
if not m or '"hrms_addon.hrms_addon.pick_lists.after_install"' not in m.group(1):
    fail.append("hooks.after_install must include hrms_addon.hrms_addon.pick_lists.after_install")
after_migrate = re.search(r"^after_migrate = \[(.*?)^\]", hooks, re.S | re.M)
if after_migrate and ("pick_lists" in after_migrate.group(1) or "kra_masters" in after_migrate.group(1)):
    fail.append("the pick lists must not be seeded on every migrate: it would recreate values HR deleted")
# migrate imports every JSON in fixtures/, whatever hooks.fixtures says
for name in sorted(os.listdir(os.path.join(REPO, "hrms_addon", "fixtures"))):
    if name.endswith(".json") and any(
        record.get("doctype") in rules.MASTERS for record in json.loads(read("hrms_addon", "fixtures", name))
    ):
        fail.append("fixtures/%s holds pick list values: migrate would re-import them over HR's changes" % name)
if any('"%s"' % master in hooks for master in rules.MASTERS):
    fail.append("hooks.py names a pick list master (fixtures?): the lists are HR data, seeded once")

# Patch order: text moved into the first four tables, then the JD lists
# seeded (values in use included), then the profile text moved using them.
post = read("hrms_addon", "patches.txt").split("[post_model_sync]")
listed = [line.strip() for line in post[1].splitlines() if line.strip() and not line.startswith("#")] if len(post) == 2 else []
order = ["hrms_addon.patches.v1_0.jd_text_sections_to_tables", "hrms_addon.patches.v1_0.seed_jd_masters",
         "hrms_addon.patches.v1_0.jd_profile_sections_to_tables"]
if "hrms_addon.patches.v1_0.seed_kra_masters" not in listed:
    fail.append("seed_kra_masters must be a post_model_sync patch (the master tables exist only after the model sync)")
if not all(p in listed for p in order) or [listed.index(p) for p in order] != sorted(listed.index(p) for p in order):
    fail.append("post_model_sync must run %s in that order: seed_jd_masters must run after jd_text_sections_to_tables "
                "and jd_profile_sections_to_tables must run after seed_jd_masters" % " -> ".join(p.rsplit(".", 1)[1] for p in order))
for patch, function in (("seed_kra_masters", "seed_kra_masters"), ("seed_jd_masters", "seed_jd_masters")):
    seed_patch = read("hrms_addon", "patches", "v1_0", patch + ".py")
    if (not re.search(r"def execute\(\):\s*\n\s+%s\(\)" % function, seed_patch)
            or "from hrms_addon.hrms_addon.pick_lists import %s" % function not in seed_patch):
        fail.append("patch %s must call pick_lists.%s" % (patch, function))
print("seeding: once by patch on existing sites, by after_install on new ones, never on migrate or as fixtures")

# ── 6. Filling the tables from a CSV ─────────────────────────────────
# Every table on the Job Description tab, and HRMS's Required Skills table
# on the same form, has Download and Upload buttons: Frappe shows them for
# a Table field with allow_bulk_edit. Upload copies each cell into the rows
# as the file has it, so the save hook first repairs what Excel writes, and
# the form's own Download must keep writing the rows Upload reads.
jd_tables = sorted(f["fieldname"] for f in custom
                   if f["dt"] == "Designation" and f["fieldtype"] == "Table" and f["fieldname"].startswith("custom_jd_"))
if sorted(rules.JD_TABLE_FIELDS) != jd_tables:
    fail.append("jd_rules.JD_TABLE_FIELDS %s must be exactly the Job Description tables %s" % (sorted(rules.JD_TABLE_FIELDS), jd_tables))
if (rules.KRA_TABLE != TABLE_FIELD or rules.JD_TABLE_FIELDS[0] != TABLE_FIELD
        or sorted(rules.JD_TABLE_FIELDS[1:]) != sorted(list(rules.TABLES) + [rules.SCREENING_TABLE])):
    fail.append("JD_TABLE_FIELDS must be the Key Result Areas table, jd_rules.TABLES and the screening questions")
for fieldname in jd_tables:
    if by_name["Designation-%s" % fieldname].get("allow_bulk_edit") != 1:
        fail.append("Designation.%s needs allow_bulk_edit: without it the table has no Download / Upload buttons" % fieldname)

# HRMS's Required Skills table is theirs, so its flag is a property setter
skills_setter = setters.get("Designation-%s-allow_bulk_edit" % rules.SKILLS_TABLE) or {}
if (skills_setter.get("doctype_or_field"), skills_setter.get("property_type"), skills_setter.get("value")) != ("DocField", "Check", "1"):
    fail.append("Designation.%s needs an allow_bulk_edit property setter (the field belongs to HRMS): %s"
                % (rules.SKILLS_TABLE, skills_setter))
flagged = sorted(jd_tables + [s.get("field_name") for s in setters.values()
                              if s.get("doc_type") == "Designation" and s.get("property") == "allow_bulk_edit" and s.get("value") == "1"])
if sorted(rules.UPLOADABLE_TABLES) != flagged:
    fail.append("jd_rules.UPLOADABLE_TABLES %s must be every Designation table with Download / Upload %s"
                % (sorted(rules.UPLOADABLE_TABLES), flagged))

# Every uploaded column is either Frappe's to check (Link) or cleaned
CLEANED = ("Link", "Percent", "Float", "Select") + tuple(rules.TEXT_FIELDTYPES)
UPSTREAM_TABLES = {rules.SKILLS_TABLE: "Designation Skill"}  # not ours: checked against hrms/setup.py below
columns = 0
for fieldname in rules.UPLOADABLE_TABLES:
    child_doctype = (by_name.get("Designation-%s" % fieldname) or {}).get("options") or UPSTREAM_TABLES.get(fieldname)
    if not child_doctype:
        fail.append("no child DocType known for the uploadable table Designation.%s" % fieldname)
        continue
    if fieldname in UPSTREAM_TABLES:
        continue  # upstream's own columns, checked against hrms/setup.py below
    for column in doctype_json(child_doctype)["fields"]:
        columns += 1
        if column["fieldtype"] not in CLEANED:
            fail.append("%s.%s is a %s, which uploaded_value does not handle: decide how an uploaded cell of it is read"
                        % (child_doctype, column["fieldname"], column["fieldtype"]))
if (child_fields.get("weighting") or {}).get("fieldtype") != "Percent":
    fail.append("JD Key Result Area.weighting must be a Percent: uploaded_value strips the % only from Percent cells")

u = rules.uploaded_value
for fieldtype, value, expected in (
    ("Percent", "25%", 25.0),
    ("Percent", " 12.5 % ", 12.5),
    ("Percent", "40", 40.0),
    ("Percent", "", 0.0),
    ("Percent", 30.0, 30.0),
    ("Percent", None, None),
    ("Percent", "abc", "abc"),        # left for key_result_area_errors to report
    ("Percent", "12,5", "12,5"),      # a decimal comma is not 125
    ("Percent", "#VALUE!", "#VALUE!"),
    ("Percent", "nan", "nan"),
    ("Float", "5", 5.0),
    ("Float", " 3 years ", 3.0),
    ("Float", "1 yr", 1.0),
    ("Float", "", 0.0),
    ("Float", "several", "several"),
    ("Small Text", "Bachelor\x92s degree \x96 \x93IMS\x94 \x95 5\x80", "Bachelor’s degree – “IMS” • 5€"),
    ("Data", "PE\x81/Kawempe", "PE/Kawempe"),  # unused in Windows-1252: dropped
    ("Data", "Café – Ōsaka’s", "Café – Ōsaka’s"),  # already right: untouched
    ("Small Text", None, None),
    ("Link", "Customer\x92s Focus", "Customer\x92s Focus"),  # Frappe checks Links before the hook runs
):
    got = u(fieldtype, value)
    if got != expected or type(got) is not type(expected):
        fail.append("uploaded_value(%r, %r) is %r, expected %r" % (fieldtype, value, got, expected))
for value, options, expected in (
    (" yes ", "\nYes\nNo", "Yes"),                      # one of its options, however written
    ("number", "Yes or No\nNumber", "Number"),
    ("Maybe", "\nYes\nNo", "Maybe"),                   # left for Frappe to report
    ("Yes\x92", "\nYes\nNo", "Yes’"),                  # Excel's characters repaired first
    (None, "\nYes\nNo", None),
):
    got = u("Select", value, options)
    if got != expected:
        fail.append("uploaded_value('Select', %r) is %r, expected %r" % (value, got, expected))
for code in range(0x80, 0xA0):
    try:
        expected = bytes([code]).decode("cp1252")
    except UnicodeDecodeError:
        expected = ""
    if u("Data", chr(code)) != expected:
        fail.append("uploaded_value must read U+%04X as Windows-1252 byte 0x%02X (%r), got %r" % (code, code, expected, u("Data", chr(code))))
        break
expect("weighting nan", check(rows(("A", F, "nan"), ("B", C, 100))), "Row 1: the weighting must be a number")
expect("weighting inf", check(rows(("A", F, "inf"), ("B", C, 100))), "Row 1: the weighting must be a number")
uploaded = rows(("A", F, "25%"), ("B", C, "20%"), ("C", I, " 45 % "), ("D", L, "10"))
expect("an uploaded 25%/20%/45 %/10 split, as sent", check(uploaded), "must be a number")
for row in uploaded:
    row["weighting"] = u("Percent", row["weighting"])
expect("the same split once cleaned", check(uploaded))

validate_body = re.search(r"^def validate\(doc, method=None\):\n(.*?)(?=^\S)", glue, re.S | re.M)
if not validate_body or not validate_body.group(1).lstrip().startswith("_clean_uploaded_cells(doc)\n"):
    fail.append("designation.validate must call _clean_uploaded_cells(doc) first, before any rule reads the rows")
cleaner = re.search(r"^def _clean_uploaded_cells\(doc\):\n(.*?)(?=^\S)", glue, re.S | re.M)
for needle, why in (
    ("for fieldname in jd_rules.UPLOADABLE_TABLES:", "must clean every table that can be filled from a CSV"),
    ("for df in row.meta.fields:", "must look at every column of a row"),
    ("jd_rules.uploaded_value(df.fieldtype, value, df.options)",
     "must use the tested uploaded_value, with a Select column's options"),
    ("row.set(df.fieldname, cleaned)", "must write the cleaned value back"),
):
    if not cleaner or needle not in cleaner.group(1):
        fail.append("designation._clean_uploaded_cells %s" % why)

if not re.search(r'setup\(frm\) \{(?:\s*//[^\n]*)*\s*\$\(frm\.wrapper\)\.on\(\s*"dirty",\s*frappe\.utils\.debounce\(\(\) => ha_show_kra_totals\(frm\), \d+\)', js):
    fail.append("designation.js must recount the KRA totals when the form turns dirty (setup): Upload fires no row event")
if not re.search(r"refresh\(frm\) \{[^}]*ha_setup_jd_downloads\(frm\);", js):
    fail.append("designation.js must set up the Job Description downloads on refresh")
for needle, why in (
    ('df.fieldtype === "Table" && df.allow_bulk_edit', "must replace Download on exactly the tables that have the buttons"),
    ('.find(".grid-download")\n\t\t\t\t.off("click")\n\t\t\t\t.on("click"', "must replace Frappe's Download click, not add to it"),
    ('frappe.model.is_value_type(column.fieldtype)', "must write the same columns as Frappe's Download"),
    ('new Blob(["\\ufeff" + csv]', "must start the file with a UTF-8 byte order mark, or Excel reads it as Windows-1252"),
    ('`"${value.replace(/"/g, \'""\')}"`', "must quote text cells, doubling quotes inside them"),
):
    if needle not in js:
        fail.append("designation.js Download %s" % why)
header = re.search(r"const data = \[\n(.*?)\n\t\];", js, re.S)
our_rows = [line.strip().rstrip(",") for line in header.group(1).splitlines()] if header else []

if os.path.isdir(APPS_ROOT):
    def upstream(*parts):
        return read_upstream("frappe", "frappe", *parts)

    def read_upstream(*parts):
        return open(os.path.join(APPS_ROOT, *parts), encoding="utf-8").read()

    grid = upstream("public", "js", "frappe", "form", "grid.js")
    download = re.search(r"\n\tsetup_download\(\) \{\n(.*?)\n\t\}\n", grid, re.S)
    frappe_rows = re.findall(r"data\.push\((\[.*?\])\);", download.group(1))[:7] if download else []
    if not frappe_rows or our_rows != frappe_rows:
        fail.append("designation.js Download header rows %s differ from Frappe's %s: Upload would misread the file"
                    % (our_rows, frappe_rows))
    for needle, why in (
        ("this.frm.get_docfield(this.df.fieldname)?.allow_bulk_edit", "reads allow_bulk_edit from the Table field"),
        ("var fieldnames = data[2];", "reads the fieldnames from the third row"),
        ("if (i > 6) {", "reads rows from the eighth row on"),
        ("me.frm.add_child(me.df.fieldname)", "adds each row with frm.add_child"),
        ("frappe.utils.get_decoded_string(file.dataurl)", "decodes the file with get_decoded_string"),
        ('.find(".grid-download")', "binds its Download to .grid-download"),
    ):
        if needle not in grid:
            fail.append("frappe grid.js no longer %s: recheck the Job Description tables' Download / Upload" % why)
    hrms_setup = re.search(r'"Designation": \[(.*?)\n\t\t\],\n', read_upstream("hrms", "hrms", "setup.py"), re.S)
    if not hrms_setup or '"fieldname": "skills",' not in hrms_setup.group(1) or '"options": "Designation Skill",' not in hrms_setup.group(1):
        fail.append("HRMS no longer adds the skills table to Designation: the allow_bulk_edit property setter would do nothing")
    add_child = re.search(r"\n\tadd_child: function \(parent_doc, doctype, parentfield, idx\) \{\n(.*?)\n\t\},\n", upstream("public", "js", "frappe", "model", "create_new.js"), re.S)
    if not add_child or "cur_frm.dirty()" not in add_child.group(1):
        fail.append("frappe.model.add_child no longer marks the form dirty: the KRA totals would not follow an Upload")
    # uploaded_value's Windows-1252 repair assumes this exact decoding: UTF-8
    # when the file is valid UTF-8, otherwise atob's bytes as Latin-1
    decoded = re.search(r"\n\tget_decoded_string\(dataURI\) \{\n(.*?)\n\t\},\n", upstream("public", "js", "frappe", "utils", "utils.js"), re.S)
    decoded_code = " ".join(re.sub(r"//[^\n]*", "", decoded.group(1)).split()) if decoded else ""
    if decoded_code != ('let parts = dataURI.split(","); const encoded_data = parts[1]; let decoded = atob(encoded_data); '
                        "try { const escaped = escape(decoded); decoded = decodeURIComponent(escaped); } catch (e) { } return decoded;"):
        fail.append("frappe's get_decoded_string changed: recheck uploaded_value's Windows-1252 repair against it (%s)" % decoded_code)
    upstream_note = "checked against frappe's grid.js"
else:
    if len(our_rows) != 7 or our_rows[6] != '["------"]':
        fail.append("designation.js Download must write Frappe's 7 header rows")
    upstream_note = "upstream apps not found at %s: grid.js contract not checked" % APPS_ROOT
print("table import: %d tables with Download / Upload (%d on the JD tab), %d columns cleaned or linked, %s"
      % (len(rules.UPLOADABLE_TABLES), len(jd_tables), columns, upstream_note))

# ── 7. A Job Requisition's Job Description tab ───────────────────────
# Picking the Job Title fills it from the JD. HRMS copies the Responsibilities
# onto the public Job Opening, so they are posting_details and nothing more.
if tuple(part for part, heading in rules.REQUISITION_HEADINGS) != tuple(rules.POSTING_PARTS):
    fail.append("the requisition's Responsibilities must set out exactly posting_details' parts %s, in its order" % (rules.POSTING_PARTS,))
sample = {
    "purpose": "Lead sales & marketing.\n\n  <Grow> revenue  ",
    "responsibilities": ["Hit the <monthly> targets", "Build the team"],
    "requirements": [{"title": "Academic Qualification", "items": [{"text": "Degree in Marketing", "priority": "Essential"}]},
                     {"title": "", "items": [{"text": "Driving permit", "priority": ""}]}],
    "competencies": [{"title": "Technical", "items": ["Pricing", "CRM & ERP"]}, {"title": "", "items": ["Leadership"]}],
}
expected_html = (
    "<h4>Job Purpose</h4><p>Lead sales &amp; marketing.</p><p>&lt;Grow&gt; revenue</p>"
    "<h4>Key Responsibilities</h4><ul><li>Hit the &lt;monthly&gt; targets</li><li>Build the team</li></ul>"
    "<h4>Requirements</h4><p><strong>Academic Qualification</strong></p><ul><li>Degree in Marketing (Essential)</li></ul>"
    "<ul><li>Driving permit</li></ul>"
    "<h4>Competencies</h4><p><strong>Technical:</strong> Pricing, CRM &amp; ERP</p><p>Leadership</p>"
)
got_html = rules.requisition_description(sample)
if got_html != expected_html:
    fail.append("requisition_description: headings, paragraphs and lists the editor keeps, every value escaped\n    got      %s\n    expected %s"
                % (got_html, expected_html))
if rules.requisition_description({}) != "" or rules.requisition_description(None) != "":
    fail.append("a Job Title with nothing a candidate may see gives empty Responsibilities")
if rules.requisition_description({"competencies": [{"title": "Behavioural", "items": ["Integrity"]}]}) \
        != "<h4>Competencies</h4><p><strong>Behavioural:</strong> Integrity</p>":
    fail.append("requisition_description must write only the parts the JD has")
subordinates = rules.requisition_subordinates([
    {"relationship": "Indirect", "designation": "Sales Representative", "scope": "All depots"},
    {"relationship": "Direct", "designation": "Sales Manager", "scope": ""},
    {"relationship": "Direct", "designation": " Marketing  Officer ", "scope": " Kampala "},
    {"relationship": "", "designation": "Driver"},
    {"relationship": "Direct", "designation": "", "scope": "a row with no position"},
], ["Direct", "Indirect"])
if subordinates != "Direct: Sales Manager, Marketing Officer (Kampala)\nIndirect: Sales Representative (All depots)\nDriver":
    fail.append("requisition_subordinates: one line per relationship in HR's order, positions with their scope: %r" % subordinates)
if rules.requisition_subordinates(None) != "" or rules.requisition_subordinates([{"relationship": "Direct"}], ["Direct"]) != "":
    fail.append("no reporting relationships give no subordinates")
print("requisition: the JD fills the Job Description tab with the careers page's parts only, escaped; subordinates by relationship")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL JOB DESCRIPTION CHECKS PASSED")
