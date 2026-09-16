"""Checks for the Job Description template on Designation, run without a bench.

jd_rules.py imports nothing from Frappe, so it is loaded directly and its
Balanced Scorecard validation is exercised: the real split from
LPL/JD/SM/001 (Head Sales & Marketing, 25/20/45/10), rounding, totals that
miss 100%, duplicate and missing perspectives, and bad weightings.

It also checks the three places the perspective list is written down agree
(rules, child table Select options, form script), that the child table is a
well-formed child DocType of this app, and that hooks, form script and
controller all point at fields and functions that exist.

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


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


spec = importlib.util.spec_from_file_location("jd_rules", os.path.join(REPO, "hrms_addon", "hrms_addon", "jd_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)  # proves it has no Frappe import
print("loaded jd_rules.py without Frappe")

# ── 1. One list of perspectives, written in three places ─────────────
child = json.loads(read("hrms_addon", "hrms_addon", "doctype", "jd_key_result_area", "jd_key_result_area.json"))
select = next(f for f in child["fields"] if f["fieldname"] == "perspective")
child_options = tuple(o for o in select["options"].split("\n") if o)
js = read("hrms_addon", "public", "js", "designation.js")
js_list = tuple(re.findall(r'"([^"]+)"', re.search(r"HA_BSC_PERSPECTIVES = \[(.*?)\]", js, re.S).group(1)))
if not (rules.PERSPECTIVES == child_options == js_list):
    fail.append("perspective lists differ: rules %s | child table %s | form script %s"
                % (rules.PERSPECTIVES, child_options, js_list))
print("perspectives agree in rules, child table and form script: %s" % ", ".join(rules.PERSPECTIVES))

# ── 2. The child DocType ─────────────────────────────────────────────
if not child.get("istable"):
    fail.append("JD Key Result Area must be a child table (istable)")
if child.get("module") != "HRMS Addon":
    fail.append("JD Key Result Area module is %r" % child.get("module"))
if child.get("name") != "JD Key Result Area":
    fail.append("child doctype name is %r" % child.get("name"))
fieldnames = [f["fieldname"] for f in child["fields"]]
if child.get("field_order") != fieldnames:
    fail.append("child field_order %s does not match its fields %s" % (child.get("field_order"), fieldnames))
for needed in ("perspective", "weighting", "key_outputs"):
    if needed not in fieldnames:
        fail.append("child table missing %s" % needed)
grid = [f for f in child["fields"] if f.get("in_list_view")]
if sum(f.get("columns") or 0 for f in grid) > 10:
    fail.append("grid columns exceed Frappe's 10-column row")
if not re.search(r"^class JDKeyResultArea\(Document\):", read("hrms_addon", "hrms_addon", "doctype", "jd_key_result_area", "jd_key_result_area.py"), re.M):
    # frappe.model.base_document.get_controller: doctype.replace(" ", "").replace("-", "")
    fail.append("controller class must be JDKeyResultArea")
if not os.path.exists(os.path.join(CHILD_DIR, "__init__.py")):
    fail.append("child doctype folder is missing __init__.py")
print("child doctype: istable, module, fields, grid width and controller class correct")

# ── 3. Behaviour ─────────────────────────────────────────────────────
F, C, I, L = rules.PERSPECTIVES


def rows(*pairs):
    return [{"perspective": p, "weighting": w} for p, w in pairs]


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


expect("empty table is allowed", rules.key_result_area_errors([]))
expect("LPL/JD/SM/001 split 25/20/45/10", rules.key_result_area_errors(rows((F, 25), (C, 20), (I, 45), (L, 10))))
expect("rounding 33.33/33.33/33.34", rules.key_result_area_errors(rows((F, 33.33), (C, 33.33), (I, 33.34))))
# 15.7 + 22.1 + 51.4 + 10.8 sums to 99.99999999999999 in floating point — a
# correct split that an exact comparison would wrongly reject. (33.33 +
# 33.33 + 33.34 happens to land on exactly 100.0, so it cannot prove this.)
expect("float drift 15.7/22.1/51.4/10.8", rules.key_result_area_errors(rows((F, 15.7), (C, 22.1), (I, 51.4), (L, 10.8))))
expect("weightings as strings", rules.key_result_area_errors(rows((F, "40"), (I, "60"))))


class Row:  # Frappe child rows are objects, not dicts
    def __init__(self, perspective, weighting):
        self.perspective, self.weighting = perspective, weighting


expect("object rows", rules.key_result_area_errors([Row(F, 50), Row(L, 50)]))
expect("total short of 100", rules.key_result_area_errors(rows((F, 25), (C, 20), (I, 45))), "must total 100%", "currently 90%")
expect("total over 100", rules.key_result_area_errors(rows((F, 60), (L, 60))), "currently 120%")
expect("duplicate perspective", rules.key_result_area_errors(rows((F, 50), (F, 50))), "Financial appears more than once")
expect("blank perspective", rules.key_result_area_errors(rows(("", 100))), "choose a Balanced Scorecard perspective")
expect("unknown perspective", rules.key_result_area_errors(rows(("Operations", 100))), "choose a Balanced Scorecard perspective")
expect("weighting out of range", rules.key_result_area_errors(rows((F, 150), (C, -50))), "between 0 and 100%")
expect("non-numeric weighting", rules.key_result_area_errors(rows((F, "abc"), (C, 100))), "must be a number")
print("behaviour: JD split, rounding, strings, object rows, totals, duplicates, blanks and bad values correct")

# ── 4. Wiring ────────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
fixtures = {f["name"]: f for f in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}

table = fixtures.get("Designation-%s" % TABLE_FIELD)
if not table or table.get("fieldtype") != "Table" or table.get("options") != "JD Key Result Area":
    fail.append("Designation.%s must be a Table of JD Key Result Area" % TABLE_FIELD)
if '"Designation": {\n        # Job Description' not in hooks or '"hrms_addon.hrms_addon.designation.validate"' not in hooks:
    fail.append("hooks.py doc_events does not wire Designation validate")
if "def validate(doc, method=None)" not in read("hrms_addon", "hrms_addon", "designation.py"):
    fail.append("designation.py has no validate(doc, method=None)")
if TABLE_FIELD not in read("hrms_addon", "hrms_addon", "designation.py"):
    fail.append("designation.py does not validate %s" % TABLE_FIELD)
m = re.search(r'"Designation": "([^"]+)"', hooks)
if not m or not os.path.exists(os.path.join(REPO, "hrms_addon", m.group(1))):
    fail.append("doctype_js for Designation does not point at an existing file")
if hooks.count("\ndoc_events = ") != 1 or hooks.count("\ndoctype_js = ") != 1:
    fail.append("doc_events and doctype_js must each be assigned exactly once in hooks.py")
if TABLE_FIELD not in js:
    fail.append("designation.js does not use %s" % TABLE_FIELD)
stripped = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`', "", js, flags=re.S)
for op, cl in (("{", "}"), ("(", ")"), ("[", "]")):
    if stripped.count(op) != stripped.count(cl):
        fail.append("designation.js: unbalanced %s%s" % (op, cl))
print("wiring: table field, doc event, controller, form script all resolve")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL JOB DESCRIPTION CHECKS PASSED")
