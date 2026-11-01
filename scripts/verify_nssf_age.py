"""Checks the age NSSF stops at, without a bench:

    python scripts/verify_nssf_age.py

Luuka, 1 Nov 2026: "add a place holder no hardcoding it", then "also add
voluntarily pay this should be per employee whos is above the 55 and still
wants to pay". The NSSF Act s.6(1) covers employees below fifty-five. So:

  1. the age: whole years at the end of the pay period, from the date of
     birth; the limit what Payroll Settings hold, 55 until they are saved
     with it, 0 for none
  2. the formula: an NSSF line gives nothing from the limit on, unless the
     employee's NSSF Voluntary is ticked; written on once
  3. the mixins give both to the slip, its full-month copy and the
     assignment
  4. the patch: both NSSF components and every structure's NSSF lines, and
     nothing else; twice is the same as once
  5. Frappe HR's own code still builds every formula's context where the
     mixins extend it, with the employee's fields and the period's end
  6. the wiring: the hooks, the fields, the patch
"""
import ast
import datetime
import importlib.util
import json
import math
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(label, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("nssf_age_rules", os.path.join(APP, "nssf_age_rules.py"))  # proves it has no Frappe import
S = load("salary_structure_rules", os.path.join(APP, "salary_structure_rules.py"))
print("loaded nssf_age_rules.py and salary_structure_rules.py without Frappe")

# ── 1. The age and the limit ──────────────────────────────────────────
for birth, on, want, why in (
        ("1971-11-25", "2026-11-25", 55, "55 on the birthday itself"),
        ("1971-11-26", "2026-11-25", 54, "54 the day before"),
        ("1972-02-29", "2027-02-28", 54, "born on 29 February: 54 on the 28th"),
        ("1972-02-29", "2027-03-01", 55, "and 55 on 1 March"),
        (datetime.date(1960, 5, 1), datetime.date(2026, 10, 25), 66, "from dates"),
        (datetime.datetime(1960, 5, 1, 8, 30), "2026-10-25", 66, "from a date and time"),
        (None, "2026-10-25", 0, "0 with no date of birth"),
        ("", "2026-10-25", 0, "or a blank one"),
        ("not a date", "2026-10-25", 0, "or one that is no date"),
        ("1971-11-25", None, 0, "0 with no period end"),
        ("2030-01-01", "2026-10-25", 0, "0 for a birth after the day"),
        ("1905-03-02", "2026-10-25", 121, "a date of birth typed as 1905 gives 121: fix it on the employee")):
    check("the age: %s" % why, R.age_on(birth, on) == want, R.age_on(birth, on))
check("the Act's age is 55", R.AGE_LIMIT == 55, R.AGE_LIMIT)
for stored, want, why in ((None, 55, "never saved, the Act's 55, not no limit"), ("", 55, "blank, the same"),
                          (0, 0, "0, no limit"), ("0", 0, "as text too"), (58, 58, "58 as HR set it"),
                          ("58", 58, "as text too"), (57.0, 57, "a whole number"), (-3, 0, "never below nought"),
                          ("x", 0, "nonsense, no limit")):
    check("the limit: %s" % why, R.limit_of(stored) == want, R.limit_of(stored))

# ── 2. The formula ────────────────────────────────────────────────────
# NSSF on the cash pay, as the site's lines read since the pay bases were corrected (salary_structure_rules.PAY_BASES)
NSSF = "floor(%s * 0.05 + 0.500001)" % S.CASH_PAY
NSSFER = "floor(%s * 0.1 + 0.500001)" % S.CASH_PAY
SCOPE = {"__builtins__": {}, "floor": math.floor}


def nssf(formula, limit, age, voluntary=0, gross=1000000):
    data = {"gross_pay": gross, "rmb": 0, "SW": 0, R.LIMIT: limit, R.AGE: age, R.VOLUNTARY: voluntary}
    return eval(formula, dict(SCOPE), data)


for formula, full, line in ((NSSF, 50000, "NSSF Employee"), (NSSFER, 100000, "NSSF Employer 10%")):
    wrapped = R.exempt_formula(formula)
    check("%s: as before below the limit" % line, nssf(wrapped, 55, 54) == full == nssf(formula, 55, 54),
          nssf(wrapped, 55, 54))
    check("%s: nothing from the limit on" % line, nssf(wrapped, 55, 55) == 0 and nssf(wrapped, 55, 74) == 0)
    check("%s: as before past it with NSSF Voluntary ticked" % line, nssf(wrapped, 55, 74, voluntary=1) == full)
    check("%s: as before for everybody with no limit" % line, nssf(wrapped, 0, 74) == full)
    check("%s: the limit HR set, not 55: at 58, charged at 57 and not at 58" % line,
          nssf(wrapped, 58, 57) == full and nssf(wrapped, 58, 58) == 0)
    check("%s: charged where no date of birth is known" % line, nssf(wrapped, 55, 0) == full)
    check("%s: written on once" % line, R.exempt_formula(wrapped) == wrapped)
    check("%s: its own formula inside, whole" % line, wrapped.endswith("else (%s)" % formula), wrapped)
    tree = ast.parse(wrapped, mode="eval")
    check("%s: one expression, nothing Frappe HR refuses in a formula" % line,
          "__" not in wrapped and not any(isinstance(node, (ast.Lambda, ast.NamedExpr)) for node in ast.walk(tree)))
check("no age written into the formula: it is read from the settings",
      not re.search(r"\b5[0-9]\b", R.exempt_formula(NSSF).replace(NSSF, "")), R.exempt_formula(NSSF))
check("an empty formula is left alone", R.exempt_formula("") == "" and R.exempt_formula(None) is None)
check("spaces round a formula are dropped", R.exempt_formula("  %s\n" % NSSF) == R.exempt_formula(NSSF))

# ── 3. The mixins ─────────────────────────────────────────────────────
saved = {}
frappe = types.ModuleType("frappe")
frappe.db = types.SimpleNamespace(get_singles_dict=lambda doctype: dict(saved) if doctype == "Payroll Settings" else {})
package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
app.nssf_age_rules = R
sys.modules.update({"frappe": frappe, "hrms_addon": package, "hrms_addon.hrms_addon": app,
                    "hrms_addon.hrms_addon.nssf_age_rules": R})
G = load("nssf_age", os.path.join(APP, "nssf_age.py"))


class FrappeHRSlip:
    """Frappe HR's Salary Slip as the mixin sees it: the employee's fields and the slip's period end."""

    def get_data_for_eval(self):
        data = {"date_of_birth": self.birth, "end_date": "2026-11-25", R.VOLUNTARY: self.voluntary,
                "gross_pay": 1000000, "rmb": 0, "SW": 0}
        return dict(data), dict(data)


class Slip(G.SalarySlipNssfAge, FrappeHRSlip):
    def __init__(self, birth, voluntary=0):
        self.birth, self.voluntary = birth, voluntary


class FrappeHRAssignment:
    def _get_component_eval_context(self):
        return {"date_of_birth": "1971-11-26", "end_date": "2026-11-25"}


class Assignment(G.SalaryStructureAssignmentNssfAge, FrappeHRAssignment):
    pass


data, default_data = Slip("1971-11-25").get_data_for_eval()
check("the slip's formulas are given the limit, 55 never saved, and the age at the period's end",
      (data[R.LIMIT], data[R.AGE]) == (55, 55), data)
check("and its full-month copy too", (default_data[R.LIMIT], default_data[R.AGE]) == (55, 55), default_data)
check("Frappe HR's own values kept", data["gross_pay"] == 1000000 and data["end_date"] == "2026-11-25")
saved = {G.FIELD: "58"}
check("the limit HR saved is the one given", Slip("1971-11-25").get_data_for_eval()[0][R.LIMIT] == 58)
saved = {G.FIELD: 0}
check("0 saved is no limit", Slip("1971-11-25").get_data_for_eval()[0][R.LIMIT] == 0)
saved = {}
data = Assignment()._get_component_eval_context()
check("the assignment's formulas are given both too, the age at its period's end",
      (data[R.LIMIT], data[R.AGE]) == (55, 54), data)
old, ticked = Slip("1960-01-01"), Slip("1960-01-01", voluntary=1)
check("a slip at 66 takes no NSSF; with NSSF Voluntary ticked, the full 5%",
      eval(R.exempt_formula(NSSF), dict(SCOPE), old.get_data_for_eval()[0]) == 0
      and eval(R.exempt_formula(NSSF), dict(SCOPE), ticked.get_data_for_eval()[0]) == 50000)


# ── 4. The patch ──────────────────────────────────────────────────────
class Site:
    """A stand-in for Frappe with the components and lines the patch reads."""

    def __init__(self):
        self.components = {"NSSF Employee": {"formula": NSSF}, "NSSF Employer 10%": {"formula": NSSFER},
                           "Local Service Tax": {"formula": "floor(BS * 0.01)"}}
        self.lines = [
            {"name": "L1", "parenttype": "Salary Structure", "salary_component": "NSSF Employee", "formula": NSSF},
            {"name": "L2", "parenttype": "Salary Structure", "salary_component": "NSSF Employer 10%", "formula": NSSFER},
            {"name": "L3", "parenttype": "Salary Slip", "salary_component": "NSSF Employee", "formula": NSSF},
            {"name": "L4", "parenttype": "Salary Structure", "salary_component": "Local Service Tax",
             "formula": "floor(BS * 0.01)"},
            {"name": "L5", "parenttype": "Salary Structure", "salary_component": "NSSF Employee", "formula": ""},
            {"name": "L6", "parenttype": "Salary Structure", "salary_component": "NSSF Employee",
             "formula": "0 if nssf_age_limit and employee_age >= nssf_age_limit else (floor(BS * 0.05))"}]
        self.writes = 0

    def frappe(self):
        site = self

        def matches(line, filters):
            for field, wanted in filters.items():
                if isinstance(wanted, list) and wanted[0] == "in":
                    if line.get(field) not in wanted[1]:
                        return False
                elif line.get(field) != wanted:
                    return False
            return True

        def get_all(doctype, filters=None, fields=None):
            return [types.SimpleNamespace(**{field: line.get(field) for field in fields})
                    for line in site.lines if doctype == "Salary Detail" and matches(line, filters or {})]

        def set_value(doctype, name, field, value=None, update_modified=True):
            site.writes += 1
            record = site.components[name] if doctype == "Salary Component" else next(
                line for line in site.lines if line["name"] == name)
            record[field] = value

        module = types.ModuleType("frappe")
        module.db = types.SimpleNamespace(
            exists=lambda doctype, name=None: doctype == "DocType" or name in site.components,
            get_value=lambda doctype, name, field: site.components[name].get(field), set_value=set_value)
        module.get_all = get_all
        return module


site = Site()
sys.modules["frappe"] = site.frappe()
P = load("nssf_age_limit", os.path.join(REPO, "hrms_addon", "patches", "v1_0", "nssf_age_limit.py"))
P.execute()
lines = {line["name"]: line["formula"] for line in site.lines}
check("both NSSF components read the limit",
      [site.components[name]["formula"] for name in R.NSSF_LINES] == [R.exempt_formula(NSSF), R.exempt_formula(NSSFER)],
      site.components)
check("and every structure's NSSF lines", (lines["L1"], lines["L2"]) == (R.exempt_formula(NSSF),
                                                                        R.exempt_formula(NSSFER)), lines)
check("a slip's row, another component, a line without a formula and one already reading the limit are left alone",
      lines["L3"] == NSSF and lines["L4"] == "floor(BS * 0.01)" and lines["L5"] == ""
      and lines["L6"].count(R.LIMIT) == 2 and site.components["Local Service Tax"]["formula"] == "floor(BS * 0.01)",
      lines)
writes = site.writes
P.execute()
check("the second run writes nothing", site.writes == writes, site.writes - writes)

# ── 5. Frappe HR's own code ───────────────────────────────────────────
payroll = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll")
slip_src = os.path.join(payroll, "doctype", "salary_slip", "salary_slip.py")
assignment_src = os.path.join(payroll, "doctype", "salary_structure_assignment", "salary_structure_assignment.py")
utils_src = os.path.join(payroll, "utils.py")
if all(os.path.exists(path) for path in (slip_src, assignment_src, utils_src)):
    slip = open(slip_src, encoding="utf-8").read()
    assignment = open(assignment_src, encoding="utf-8").read()
    utils = open(utils_src, encoding="utf-8").read()
    check("Frappe HR's Salary Slip builds a formula's data in get_data_for_eval, giving back the data and its "
          "full-month copy", "\tdef get_data_for_eval(self):" in slip and "\t\treturn data, default_data" in slip)
    check("from the shared context, then the slip's own fields over it, its end_date among them",
          "data = get_component_eval_context(self.employee, self._salary_structure_assignment)" in slip
          and "data.update(slip_data)" in slip)
    check("Frappe HR's assignment builds its own in _get_component_eval_context, ending its period there",
          "\tdef _get_component_eval_context(self) -> frappe._dict:" in assignment
          and "data.end_date = dates.end_date" in assignment and "data = self._get_component_eval_context()" in assignment)
    check("the shared context carries every employee field: the date of birth, and NSSF Voluntary",
          'data.update(frappe.get_cached_doc("Employee", employee).as_dict())' in utils)
    builders, evaluators = set(), set()
    for folder, _dirs, files in os.walk(os.path.join(APPS_ROOT, "hrms", "hrms")):
        for name in files:
            if not name.endswith(".py") or name.startswith("test_") or os.sep + "tests" in folder:
                continue
            for text in open(os.path.join(folder, name), encoding="utf-8").read().splitlines():
                if text.strip().startswith("def "):
                    continue
                if re.search(r"(?<![\w.])get_component_eval_context\(", text):
                    builders.add(name)
                if re.search(r"(?<![\w.])_safe_eval\(", text):
                    evaluators.add(name)
    check("the shared context is built only by the slip and the assignment, where the mixins reach",
          builders == {"salary_slip.py", "salary_structure_assignment.py"}, builders)
    check("and salary formulas are worked out only there", evaluators == {"salary_slip.py",
                                                                            "salary_structure_assignment.py"},
          evaluators)
    framework = os.path.join(APPS_ROOT, "frappe", "frappe", "model", "base_document.py")
    if os.path.exists(framework):
        check("Frappe still mixes in extend_doctype_class",
              'frappe.get_hooks("extend_doctype_class"' in open(framework, encoding="utf-8").read())
else:
    print("Frappe HR's own code: NOT CHECKED, it was not found under %s" % APPS_ROOT)

# ── 6. The wiring ─────────────────────────────────────────────────────
hooks_src = read("hrms_addon", "hooks.py")
hooks = {}
for node in ast.parse(hooks_src).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
extended = hooks.get("extend_doctype_class") or {}
check("the Salary Slip's formulas are given the age, beside Luuka's month",
      "hrms_addon.hrms_addon.nssf_age.SalarySlipNssfAge" in (extended.get("Salary Slip") or [])
      and "hrms_addon.hrms_addon.pay_days.SalarySlipDays" in (extended.get("Salary Slip") or []),
      extended.get("Salary Slip"))
check("and the assignment's", extended.get("Salary Structure Assignment")
      == ["hrms_addon.hrms_addon.nssf_age.SalaryStructureAssignmentNssfAge"], extended.get("Salary Structure Assignment"))
glue = read("hrms_addon", "hrms_addon", "nssf_age.py")
check("the mixins build on Frappe HR's own context", "data, default_data = super().get_data_for_eval()" in glue
      and "default_data.update(extra)" in glue and "data = super()._get_component_eval_context()" in glue)
check("the setting's field name is the one the code reads", 'FIELD = "custom_nssf_age_limit"' in glue
      and 'SETTINGS = "Payroll Settings"' in glue)
fields = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
by_name = {row["name"]: row for row in fields}
limit = by_name.get("Payroll Settings-custom_nssf_age_limit") or {}
check("Payroll Settings' NSSF Age Limit: a whole number, the Act's 55, never below nought, under the Hours in a Pay Day",
      (limit.get("fieldname"), limit.get("fieldtype"), limit.get("default"), limit.get("non_negative"),
       limit.get("insert_after")) == ("custom_nssf_age_limit", "Int", str(R.AGE_LIMIT), 1, "custom_hours_in_day"), limit)
voluntary = by_name.get("Employee-custom_nssf_voluntary") or {}
check("the Employee's NSSF Voluntary: a tick under the NSSF No., by the name the formula reads",
      (voluntary.get("fieldname"), voluntary.get("fieldtype"), voluntary.get("insert_after"))
      == (R.VOLUNTARY, "Check", "custom_nssf_no"), voluntary)
check("nothing else sits under either", [(row["dt"], row.get("insert_after")) for row in fields].count(
    ("Payroll Settings", "custom_hours_in_day")) == 1 and [(row["dt"], row.get("insert_after")) for row in fields].count(
    ("Employee", "custom_nssf_no")) == 1)
check("both are in the fixtures the app ships", all('"%s",' % name in hooks_src for name in
                                                    ("Payroll Settings-custom_nssf_age_limit",
                                                     "Employee-custom_nssf_voluntary")))
patches = read("hrms_addon", "patches.txt")
check("the patch runs after the doctypes are migrated, and after the pay bases were corrected",
      "hrms_addon.patches.v1_0.nssf_age_limit" in patches.split("[post_model_sync]")[1]
      and patches.index("nssf_age_limit") > patches.index("overtime_and_pay_bases"))

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL NSSF AGE CHECKS PASSED")
