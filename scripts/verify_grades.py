"""Verify grades, bands and the per-diem scale, without a bench:

    python scripts/verify_grades.py

Two sheets of Luuka's revised testing scripts:

  Organisation & System Setup, case 6   the Gradar structure: nineteen
        grades G2 to G20, each with ten steps and a min-to-max band
  Organisation & System Setup, case 8   a second approval level above a
        configured grade threshold
  Travel & Expense, case 2              a per-diem scale by grade and
        destination, in the destination's own currency for foreign travel

  1  the band and its steps
  2  the scale, and what it says nothing about
  3  the paper: custom fields on Frappe HR's own Employee Grade, and the
     two masters it does not ship
  4  the glue reads and writes fields that exist, and fills the travel
     form's rates rather than leaving them to the traveller
  5  wiring: the grades seeded, the doc events, the way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
G = load("grade_rules")
hooks = hooks_dict()
print("loaded grade_rules.py without Frappe")

# ── 1. The band and its steps ─────────────────────────────────────────
if len(G.GRADE_CODES) != 19 or G.GRADE_CODES[0] != "G2" or G.GRADE_CODES[-1] != "G20":
    fail.append("nineteen grades, G2 to G20: %s" % (G.GRADE_CODES,))
if G.STEPS_A_GRADE != 10:
    fail.append("each with ten steps: %s" % G.STEPS_A_GRADE)

steps = G.steps_between(1000000, 1900000)
if len(steps) != 10:
    fail.append("ten steps across the band: %d" % len(steps))
if steps[0]["amount"] != 1000000 or steps[-1]["amount"] != 1900000:
    fail.append("step one is the bottom and step ten the top: %s" % [steps[0], steps[-1]])
if steps[1]["amount"] != 1100000:
    fail.append("and they are evenly spaced: %s" % steps[1])
if [row["step"] for row in steps] != list(range(1, 11)):
    fail.append("numbered one to ten: %s" % [row["step"] for row in steps])
if G.steps_between(1000000, 1000000):
    fail.append("a band with no width has no steps")
if G.steps_between(1900000, 1000000):
    fail.append("nor does one the wrong way round")
if len(G.steps_between(1000000, 1900000, 5)) != 5:
    fail.append("a grade may have a different number of steps if Luuka say so")

if G.step_of(1200000, steps) != 3:
    fail.append("a salary at step three reads as step three")
if G.step_of(1150000, steps) != 2:
    fail.append("one between two steps reads as the step below")
if G.step_of(900000, steps) is not None:
    fail.append("one below the band is on no step at all")
if G.next_step(3, steps) != 4:
    fail.append("an increment is the next step up")
if G.next_step(10, steps) is not None:
    fail.append("at the top of the band the only way up is the next grade")

if not G.in_band(1500000, 1000000, 1900000):
    fail.append("a salary inside the band is inside it")
if G.in_band(2000000, 1000000, 1900000):
    fail.append("and one above the top is not")
if G.in_band(900000, 1000000, 1900000):
    fail.append("nor one below the bottom")
if not G.in_band(None, 1000000, 1900000):
    fail.append("no salary yet is not out of band")

good = {"grade_code": "G7", "minimum": 1000000, "maximum": 1900000, "steps": steps}
expect("a proper band", G.band_errors(good))
expect("a grade outside the structure", G.band_errors(dict(good, grade_code="G21")),
       "G2 to G20")
expect("a band the wrong way round", G.band_errors(dict(good, minimum=1900000,
                                                        maximum=1000000, steps=[])),
       "above the bottom")
expect("steps that go backwards", G.band_errors(dict(good, steps=[
    {"step": 1, "amount": 1500000}, {"step": 2, "amount": 1200000}])),
    "at least as much as the one below it")
expect("a step outside the band", G.band_errors(dict(good, steps=[
    {"step": 1, "amount": 1000000}, {"step": 2, "amount": 2500000}])),
    "falls outside the band")
expect("the same step twice", G.band_errors(dict(good, steps=[
    {"step": 1, "amount": 1000000}, {"step": 1, "amount": 1100000}])),
    "in the band twice")

# test case 8: the threshold is a flag on the grade
if not G.needs_second_approval({"G15": 1}, "G15"):
    fail.append("a grade flagged for a second approval needs one")
if G.needs_second_approval({"G15": 1}, "G7"):
    fail.append("and one below it does not")
print("the band: nineteen grades, ten steps, and the threshold on the grade itself")

# ── 2. The per-diem scale ─────────────────────────────────────────────
if G.SCALE_LINES != ("Lodging", "Daily Allowance", "Conveyance"):
    fail.append("the scale sets the three rated lines of LPL.HR.31: %s" % (G.SCALE_LINES,))
if G.currency_for({"is_foreign": 1}) != "USD":
    fail.append("foreign travel is not paid in shillings")
if G.currency_for({"is_foreign": 0}) != "UGX":
    fail.append("and local travel is")
if G.currency_for({"is_foreign": 1, "currency": "KES"}) != "KES":
    fail.append("a destination that names its own currency is paid in it")
if G.currency_for(None) != "UGX":
    fail.append("no destination is home")

SCALE = [
    {"grade": "G7", "destination": "Kampala", "effective_from": "2026-01-01",
     "lodging": 80000, "daily_allowance": 40000, "conveyance": 20000},
    {"grade": "G7", "destination": "Kampala", "effective_from": "2026-07-01",
     "lodging": 100000, "daily_allowance": 50000, "conveyance": 25000},
    {"grade": "G7", "destination": "Nairobi", "effective_from": "2026-01-01",
     "lodging": 120, "daily_allowance": 60, "conveyance": 0},
]
row = G.rate_row(SCALE, "G7", "Kampala", "2026-03-01")
if not row or row["lodging"] != 80000:
    fail.append("the rate in force in March is the January one: %s" % row)
row = G.rate_row(SCALE, "G7", "Kampala", "2026-09-01")
if not row or row["lodging"] != 100000:
    fail.append("and in September, the July one that superseded it: %s" % row)
if G.rate_row(SCALE, "G7", "Kampala", "2025-06-01") is not None:
    fail.append("before any rate came into effect there is no rate")
if G.rate_row(SCALE, "G12", "Kampala", "2026-09-01") is not None:
    fail.append("a grade with no scale row has no rate")

rates = G.rates_for(G.rate_row(SCALE, "G7", "Nairobi", "2026-09-01"))
if rates != {"Lodging": 120.0, "Daily Allowance": 60.0}:
    fail.append("a line the scale leaves at nothing is left out, not set to nothing: %s" % rates)

lines = [{"expense_type": "Lodging", "rate": 0}, {"expense_type": "Daily Allowance", "rate": 0},
         {"expense_type": "Conveyance", "rate": 30000}]
filled = G.apply_scale(lines, G.rates_for(G.rate_row(SCALE, "G7", "Kampala", "2026-09-01")))
if filled["filled"] != 2:
    fail.append("the two blank lines are filled from the scale: %s" % filled)
if filled["lines"][0]["rate"] != 100000:
    fail.append("at the rate in force")
if filled["lines"][2]["rate"] != 30000:
    fail.append("and a rate somebody typed is left alone: the scale is a default, not a ceiling")
if not filled["lines"][0].get("from_scale") or filled["lines"][2].get("from_scale"):
    fail.append("and which came from the scale is said")

gaps = G.scale_gap(rates, [{"expense_type": "Lodging"}, {"expense_type": "Conveyance"}])
if gaps != ["Conveyance"]:
    fail.append("a line on the form the scale says nothing about is named: %s" % gaps)

rate = {"grade": "G7", "destination": "Kampala", "effective_from": "2026-01-01",
        "lodging": 80000, "daily_allowance": 40000, "conveyance": 20000}
expect("a proper rate", G.scale_errors(rate))
expect("a rate with no date", G.scale_errors(dict(rate, effective_from=None)),
       "from when the rate applies")
expect("a rate of nothing", G.scale_errors(dict(rate, lodging=0, daily_allowance=0,
                                                conveyance=0)),
       "nothing on every line")
expect("a rate below nothing", G.scale_errors(dict(rate, conveyance=-1)),
       "less than nothing")
expect("a proper destination", G.destination_errors(
    {"destination_name": "Nairobi", "is_foreign": 1, "country": "Kenya", "currency": "KES"}))
expect("a foreign destination with no country", G.destination_errors(
    {"destination_name": "Nairobi", "is_foreign": 1, "currency": "USD"}), "which country")
print("the scale: in force on the day, filling what was left blank, naming what it misses")

# ── 3. The paper ──────────────────────────────────────────────────────
grade = custom_fields("Employee Grade")
for fieldname in ("custom_grade_code", "custom_min_salary", "custom_max_salary", "custom_steps",
                  "custom_step_count", "custom_second_approval", "custom_gradar_points"):
    if fieldname not in grade:
        fail.append("Employee Grade has no %s" % fieldname)
if grade.get("custom_steps", {}).get("options") != "Grade Step":
    fail.append("the steps are a table of Grade Step")
upstream = fields_of(upstream_doctype("Employee Grade"))
if not upstream:
    fail.append("Employee Grade is Frappe HR's own; it was not found upstream")
for fieldname in ("default_salary_structure", "default_base_pay", "currency"):
    if fieldname not in upstream:
        fail.append("Employee Grade has no %s: this is not the doctype we think it is"
                    % fieldname)
if doctype("Employee Grade"):
    fail.append("Employee Grade must not be rebuilt here: the band is custom fields on theirs")

step = fields_of(doctype("Grade Step"))
for fieldname in ("step", "amount"):
    if fieldname not in step:
        fail.append("a Grade Step row has no %s" % fieldname)

destination = fields_of(doctype("Travel Destination"))
for fieldname in ("destination_name", "is_foreign", "country", "currency"):
    if fieldname not in destination:
        fail.append("Travel Destination has no %s" % fieldname)
rate_fields = fields_of(doctype("Per Diem Rate"))
for fieldname in ("grade", "destination", "effective_from", "currency", "lodging",
                  "daily_allowance", "conveyance"):
    if fieldname not in rate_fields:
        fail.append("Per Diem Rate has no %s" % fieldname)
for line, fieldname in G.SCALE_FIELDS.items():
    if fieldname not in rate_fields:
        fail.append("the scale has no field for %s" % line)
if rate_fields.get("grade", {}).get("options") != "Employee Grade":
    fail.append("a rate is for a grade of Frappe HR's own")

travel = custom_fields("Travel Request")
for fieldname in ("custom_destination", "custom_currency", "custom_per_diem_rate",
                  "custom_scale_remarks", "custom_grade"):
    if fieldname not in travel:
        fail.append("the travel request has no %s" % fieldname)
if travel.get("custom_destination", {}).get("options") != "Travel Destination":
    fail.append("the travel request points at a real destination")
for fieldname in ("custom_currency", "custom_per_diem_rate", "custom_scale_remarks"):
    if not travel.get(fieldname, {}).get("read_only"):
        fail.append("%s is read off the scale, not typed" % fieldname)
costing = custom_fields("Travel Request Costing")
if "custom_from_scale" not in costing:
    fail.append("a line does not say whether its rate came from the scale")
print("the paper: the band on their Employee Grade, and the two masters they do not ship")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "grades.py")
known = set(grade) | set(destination) | set(rate_fields) | set(travel)
known |= {"doctype", "name", "docstatus", "employee", "company", "flags", "costings", "base",
          "currency", "grade", "destination", "effective_from", "lodging", "daily_allowance",
          "conveyance", "country", "is_foreign", "destination_name"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "as_dict", "update"):
        continue
    if fieldname not in known:
        fail.append("grades.py reads or writes %s, which is on none of its documents" % fieldname)
for needle, why in (
    ("rules.steps_between(", "the steps are laid out by the rules (case 6)"),
    ("rules.band_errors(", "and the band is checked by them"),
    ("rules.rate_row(", "the scale in force is read by the rules (Travel case 2)"),
    ("rules.apply_scale(", "and the travel form's rates filled from it"),
    ("rules.scale_gap(", "with what the scale misses named"),
    ("rules.currency_for(", "foreign travel paid in its own currency"),
    ("rules.in_band(", "a salary outside its band is noticed"),
    ("custom_second_approval", "the second-approval threshold is on the grade (case 8)"),
    ("GRADE_CODES", "and the nineteen grades are seeded"),
):
    if needle not in glue:
        fail.append("grades.py: %s (%r not found)" % (why, needle))
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef generate_steps\(', glue):
    fail.append("grades.generate_steps replaces what is there: a whitelisted POST method")
if "check_permission(" not in glue:
    fail.append("and it must check the caller may act")
if "frappe.throw" in glue.split("def assignment_validate")[1].split("def ")[0]:
    fail.append("a salary outside its band is said, not refused: payroll is not ours to block")
allowances = read("hrms_addon", "hrms_addon", "allowances.py")
if "grades.apply_scale(" not in allowances:
    fail.append("the travel form must read the scale before it costs its lines")
if allowances.index("grades.apply_scale(") > allowances.index("_cost_lines(doc)"):
    fail.append("and read it before, not after")
for name, prefix in (("travel_destination", "destination"), ("per_diem_rate", "rate")):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    if "    def validate(self):\n        grades.%s_validate(self)" % prefix not in controller:
        fail.append("the %s controller must hand validate to grades.%s_validate"
                    % (name, prefix))
print("glue: the steps laid out, the scale read, the band watched, the form filled")

# ── 5. Wiring ─────────────────────────────────────────────────────────
if "hrms_addon.hrms_addon.grades.setup_on_migrate" not in hooks.get("after_migrate", []):
    fail.append("the nineteen grades must be seeded on every migrate")
events = hooks.get("doc_events", {})
if events.get("Employee Grade", {}).get("validate") \
        != "hrms_addon.hrms_addon.grades.grade_validate":
    fail.append("the band is checked on Frappe HR's own Employee Grade")
if events.get("Salary Structure Assignment", {}).get("validate") \
        != "hrms_addon.hrms_addon.grades.assignment_validate":
    fail.append("a salary set outside its band is said where it is set")
if hooks.get("doctype_js", {}).get("Employee Grade") != "public/js/employee_grade.js":
    fail.append("the grade form needs its script")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Travel Destination", "Per Diem Rate"):
    if name not in nav:
        fail.append("%s has no way in" % name)
if '("Employee Grade", "Employee Grade", DOCTYPE)' in nav:
    fail.append("Employee Grade is already on Frappe HR's HR Setup page: leave it where it is")
print("wiring: seeded on migrate, checked on their own forms, and a way in")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL GRADE AND PER-DIEM CHECKS PASSED")
