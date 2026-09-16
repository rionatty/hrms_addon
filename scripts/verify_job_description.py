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
