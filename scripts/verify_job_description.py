"""Checks for the Job Description template on Designation, run without a bench.

jd_rules.py imports nothing from Frappe, so it is loaded directly and its
Key Result Area rules are exercised: the real Head Sales & Marketing split
(LPL/JD/SM/001, 25/20/45/10), a perspective split across several KRAs,
floating-point drift, totals that miss 100%, missing and repeated KRAs, a
KRA with no perspective, and bad weightings.

It also checks:
  * the perspective list is identical in all four places it is written
    (rules, KRA.custom_perspective, the JD row, the form script);
  * the JD row picks from the standard KRA master and fetches the
    perspective from a field that exists;
  * the KRA additions keep the KPI Library contract — the exact fieldnames
    and dropdown values of the "KPI Library" sheet in the Part 2 master-data
    template given to Luuka, so their completed sheet imports into KRA;
  * hooks, controller and form script are wired to things that exist.

    python scripts/verify_job_description.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILD_DIR = os.path.join(REPO, "hrms_addon", "hrms_addon", "doctype", "jd_key_result_area")
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

# ── 1. One list of perspectives, written in four places ──────────────
lists = {
    "jd_rules.PERSPECTIVES": list(rules.PERSPECTIVES),
    "KRA.custom_perspective": options(kra_fields.get("custom_perspective", {})),
    "JD Key Result Area.perspective": options(child_fields.get("perspective", {})),
    "designation.js": re.findall(r'"([^"]+)"', re.search(r"HA_BSC_PERSPECTIVES = \[(.*?)\]", js, re.S).group(1)),
}
if len({tuple(v) for v in lists.values()}) != 1:
    fail.append("perspective lists differ: %s" % lists)
print("perspectives agree in all four places: %s" % ", ".join(rules.PERSPECTIVES))

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
for fieldname, expected in KPI_LIBRARY_CONTRACT.items():
    f = kra_fields.get(fieldname)
    if not f:
        fail.append("KRA.%s missing — the KPI Library sheet maps a column to it" % fieldname)
    elif expected is not None and options(f) != expected:
        fail.append("KRA.%s options %s differ from the KPI Library dropdown %s" % (fieldname, options(f), expected))
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
print("behaviour: JD split, split perspective, drift, strings, objects, totals, repeats, gaps and bad values correct")

# ── 4b. The four section tables ──────────────────────────────────────
EXPECTED_TABLE_FIELDS = {
    "JD Reporting Line": ["relationship", "designation", "scope"],
    "JD Stakeholder": ["stakeholder_type", "stakeholder", "interaction"],
    "JD Decision Authority": ["authority_level", "decisions", "constraints"],
    "JD Planning Horizon": ["horizon", "work_cycle"],
}
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

horizon_json = json.loads(read("hrms_addon", "hrms_addon", "doctype", "jd_planning_horizon", "jd_planning_horizon.json"))
if tuple(options(next(f for f in horizon_json["fields"] if f["fieldname"] == "horizon"))) != rules.HORIZONS:
    fail.append("JD Planning Horizon options differ from jd_rules.HORIZONS")
position = next(f for f in json.loads(read("hrms_addon", "hrms_addon", "doctype", "jd_reporting_line", "jd_reporting_line.json"))["fields"]
                if f["fieldname"] == "designation")
if (position.get("fieldtype"), position.get("options"), position.get("reqd")) != ("Link", "Designation", 1):
    fail.append("JD Reporting Line.designation must be a mandatory Link to Designation")
print("section tables: 4 child tables wired, fields, grid width and classes correct")

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
print("wiring: table, doc event, KRA lookup, form script events and totals all resolve")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL JOB DESCRIPTION CHECKS PASSED")
