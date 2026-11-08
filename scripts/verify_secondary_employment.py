"""Checks PAYE on a second job, without a bench:

    python scripts/verify_secondary_employment.py

Luuka, 8 Nov 2026: "if someone has two jobs there pay is calculated
different", and Luuka's register works it out as 40% of the gross less LST
(its example: 0.4 * (18,000,000 - 25,000) = 7,190,000). The Income Tax
regulations, as URA restated them on 9 September 2026: the main employer
taxes an employee on the bands; every other employer withholds a flat rate
of their pay, 40%, with no tax-free amount. So:

  1. the rate: what Payroll Settings hold, 40 until they are saved with it
  2. the formula: a ticked employee's PAYE is the rate of taxable pay less
     LST, everyone else's the bands exactly as before; written on once, and
     only on a line worked out from taxable pay
  3. the mixins give the rate to the slip, its full-month copy and the
     assignment
  4. the patch: the PAYE component and every structure's PAYE line worked
     out from taxable pay, nothing else; the others named; twice is once
  5. Frappe HR's own code still gives a formula every employee field, where
     the mixins extend it
  6. the wiring: the hooks, the fields, the patch
"""
import ast
import contextlib
import importlib.util
import io
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


R = load("secondary_employment_rules", os.path.join(APP, "secondary_employment_rules.py"))  # no Frappe import
print("loaded secondary_employment_rules.py without Frappe")

# ── 1. The rate ───────────────────────────────────────────────────────
for stored, want, why in ((None, 40, "40 until Payroll Settings are saved with it"), ("", 40, "or saved blank"),
                          (40, 40, "40 saved"), ("30", 30, "another rate saved"), (0, 0, "0 saved"),
                          (-5, 0, "never below nought"), ("forty", 0, "nothing that is not a number")):
    check("the rate: %s" % why, R.rate_of(stored) == want, R.rate_of(stored))
print("the rate: Payroll Settings', URA's 40 until saved")

# ── 2. The formula ────────────────────────────────────────────────────
# Luuka's PAYE line (payroll-setup build.py PAYE_FORMULA): the Income Tax
# (Amendment) Act 2026 bands on taxable pay less Local Service Tax
PAYE = ("floor((0 if (TXP - LST) <= 335000 else ((TXP - LST) - 335000) * 0.2 if (TXP - LST) <= 410000 "
        "else 15000 + ((TXP - LST) - 410000) * 0.25 if (TXP - LST) <= 485000 "
        "else 33750 + ((TXP - LST) - 485000) * 0.3 if (TXP - LST) <= 10000000 "
        "else 2888250 + ((TXP - LST) - 10000000) * 0.4) + 0.500001)")
# the USD structure's line, worked out from the USD pay at the month's rate (usd_net_pay.py)
USD = "round(%s / custom_exchange_rate, 2)" % PAYE.replace("TXP", "(USDP * custom_exchange_rate)").replace("LST", "0")
SCOPE = {"floor": math.floor, "round": round, "__builtins__": {}}


def paye(formula, txp, lst, secondary, rate=40):
    return eval(formula, dict(SCOPE), {"TXP": txp, "LST": lst, R.SECONDARY: secondary, R.RATE_NAME: rate})


WRAPPED = R.secondary_formula(PAYE)
check("the register's example, as Luuka work it out: 40% of (18,000,000 - 25,000) = 7,190,000",
      paye(WRAPPED, 18000000, 25000, 1) == 7190000, paye(WRAPPED, 18000000, 25000, 1))
check("the same pay at a main job, on the bands: 6,078,250",
      paye(WRAPPED, 18000000, 25000, 0) == paye(PAYE, 18000000, 25000, 0) == 6078250, paye(WRAPPED, 18000000, 25000, 0))
check("a second job has no tax-free amount: 300,000 pays 120,000 where the bands give nothing",
      (paye(WRAPPED, 300000, 0, 1), paye(WRAPPED, 300000, 0, 0)) == (120000, 0))
check("the rate is the one Payroll Settings give: 30% of (1,000,000 - 5,000) is 298,500",
      paye(WRAPPED, 1000000, 5000, 1, rate=30) == 298500)
check("rounded to the shilling as the bands are",
      (paye(WRAPPED, 1000001, 0, 1), paye(WRAPPED, 1000004, 0, 1)) == (400000, 400002))
same = [txp for txp in (0, 200000, 335000, 335001, 400000, 410000, 485000, 2500000, 10000000, 10000001, 25000000)
        if paye(WRAPPED, txp, 10000, 0) != paye(PAYE, txp, 10000, 0)]
check("an employee without the tick is taxed exactly as before, at every band", not same, same)
check("written on once", R.secondary_formula(WRAPPED) == WRAPPED)
check("the rate is read from the settings, not written into the formula",
      R.RATE_NAME in WRAPPED and not re.search(r"\b40\b", WRAPPED.replace(PAYE, "")), WRAPPED.replace(PAYE, ""))
check("a line not worked out from taxable pay less LST is left on its bands: the USD structure's",
      R.secondary_formula(USD) == USD and not R.worked_from_taxable_pay(USD) and R.worked_from_taxable_pay(PAYE))
check("an empty formula is left alone", R.secondary_formula("") == "" and R.secondary_formula(None) is None)
check("spaces round a formula are dropped", R.secondary_formula("  %s\n" % PAYE) == WRAPPED)
print("the formula: the rate of taxable pay less LST for a second job, the bands for the rest")

# ── 3. The mixins ─────────────────────────────────────────────────────
saved = {}
frappe = types.ModuleType("frappe")
frappe.db = types.SimpleNamespace(get_singles_dict=lambda doctype: dict(saved) if doctype == "Payroll Settings" else {})
package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
app.secondary_employment_rules = R
sys.modules.update({"frappe": frappe, "hrms_addon": package, "hrms_addon.hrms_addon": app,
                    "hrms_addon.hrms_addon.secondary_employment_rules": R})
G = load("secondary_employment", os.path.join(APP, "secondary_employment.py"))


class FrappeHRSlip:
    """Frappe HR's Salary Slip as the mixin sees it: the components worked out so far and every employee field."""

    def get_data_for_eval(self):
        data = {"TXP": 18000000, "LST": 25000, R.SECONDARY: self.secondary, "end_date": "2026-10-25"}
        return dict(data), dict(data)


class Slip(G.SalarySlipSecondaryEmployment, FrappeHRSlip):
    def __init__(self, secondary=0):
        self.secondary = secondary


class FrappeHRAssignment:
    def _get_component_eval_context(self):
        return {"TXP": 1000000, "LST": 0, R.SECONDARY: 1}


class Assignment(G.SalaryStructureAssignmentSecondaryEmployment, FrappeHRAssignment):
    pass


data, default_data = Slip(1).get_data_for_eval()
check("the slip's formulas are given the rate, 40 never saved", data[R.RATE_NAME] == 40, data)
check("and its full-month copy too", default_data[R.RATE_NAME] == 40, default_data)
check("Frappe HR's own values kept", data["TXP"] == 18000000 and data[R.SECONDARY] == 1)
saved = {G.FIELD: "30"}
check("the rate HR saved is the one given", Slip(1).get_data_for_eval()[0][R.RATE_NAME] == 30)
saved = {}
check("the assignment's formulas are given it too", Assignment()._get_component_eval_context()[R.RATE_NAME] == 40)
check("that pay on a slip, worked out from what the slip is given: 7,190,000, and 6,078,250 without the tick",
      (eval(WRAPPED, dict(SCOPE), Slip(1).get_data_for_eval()[0]),
       eval(WRAPPED, dict(SCOPE), Slip(0).get_data_for_eval()[0])) == (7190000, 6078250))
print("the mixins: the rate on the slip, its full-month copy and the assignment")


# ── 4. The patch ──────────────────────────────────────────────────────
class Row(dict):
    __getattr__ = dict.get


SITE = {"components": {}, "lines": []}


def fresh_site():
    SITE["components"] = {"PAYE": PAYE, "NSSF Employee": "GCP * 0.05", "Local Service Tax": "0"}
    SITE["lines"] = [Row(name="SD-1", parent="Luuka Salaried 2026-27", parenttype="Salary Structure",
                         salary_component="PAYE", formula=PAYE),
                     Row(name="SD-2", parent="Luuka Output Pay 2026-27", parenttype="Salary Structure",
                         salary_component="PAYE", formula=PAYE),
                     Row(name="SD-3", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure",
                         salary_component="PAYE", formula=USD),
                     Row(name="SD-4", parent="Luuka Salaried 2026-27", parenttype="Salary Structure",
                         salary_component="NSSF Employee", formula="GCP * 0.05"),
                     Row(name="SD-5", parent="Sal Slip/0001", parenttype="Salary Slip",
                         salary_component="PAYE", formula=PAYE)]


def get_all(doctype, filters=None, fields=None, **kwargs):
    assert doctype == "Salary Detail", doctype
    wanted = filters or {}
    return [Row(line) for line in SITE["lines"]
            if line.parenttype == wanted.get("parenttype") and line.salary_component in wanted["salary_component"][1]]


def set_value(doctype, name, field, value, update_modified=True):
    if doctype == "Salary Component":
        SITE["components"][name] = value
    else:
        next(line for line in SITE["lines"] if line.name == name)[field] = value


frappe.db = types.SimpleNamespace(
    exists=lambda doctype, name=None: doctype == "DocType" or (doctype == "Salary Component" and name in SITE["components"]),
    get_value=lambda doctype, name, field: SITE["components"][name], set_value=set_value)
frappe.get_all = get_all
P = load("secondary_employment_paye", os.path.join(REPO, "hrms_addon", "patches", "v1_0", "secondary_employment_paye.py"))
fresh_site()
said = io.StringIO()
with contextlib.redirect_stdout(said):
    P.execute()
lines = {line.name: line.formula for line in SITE["lines"]}
check("the PAYE component is given the rate for a second job", SITE["components"]["PAYE"] == WRAPPED)
check("and both shilling structures' PAYE lines", lines["SD-1"] == WRAPPED and lines["SD-2"] == WRAPPED)
check("the USD structure's is left on its bands, and named in the migrate's output",
      lines["SD-3"] == USD and "Luuka USD Net Pay 2026-27" in said.getvalue(), said.getvalue())
check("nothing else is touched: NSSF, LST, a slip's own lines",
      SITE["components"]["NSSF Employee"] == "GCP * 0.05" and SITE["components"]["Local Service Tax"] == "0"
      and lines["SD-4"] == "GCP * 0.05" and lines["SD-5"] == PAYE)
before = (dict(SITE["components"]), [dict(line) for line in SITE["lines"]])
with contextlib.redirect_stdout(io.StringIO()):
    P.execute()
check("run twice, it is the same as once", (SITE["components"], [dict(line) for line in SITE["lines"]]) == before)
print("the patch: the PAYE component and each structure's line worked out from taxable pay, the rest named")

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
    check("and the assignment in _get_component_eval_context",
          "\tdef _get_component_eval_context(self) -> frappe._dict:" in assignment)
    check("both from the shared context, which carries every employee field: Secondary Employment among them",
          "data = get_component_eval_context(self.employee, self._salary_structure_assignment)" in slip
          and 'data.update(frappe.get_cached_doc("Employee", employee).as_dict())' in utils)
    print("Frappe HR's own code: every formula is given the employee's fields where the mixins extend it")
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
check("the Salary Slip's formulas are given the rate, beside the NSSF age",
      "hrms_addon.hrms_addon.secondary_employment.SalarySlipSecondaryEmployment" in (extended.get("Salary Slip") or [])
      and "hrms_addon.hrms_addon.nssf_age.SalarySlipNssfAge" in (extended.get("Salary Slip") or []),
      extended.get("Salary Slip"))
check("and the assignment's", "hrms_addon.hrms_addon.secondary_employment.SalaryStructureAssignmentSecondaryEmployment"
      in (extended.get("Salary Structure Assignment") or []), extended.get("Salary Structure Assignment"))
glue = read("hrms_addon", "hrms_addon", "secondary_employment.py")
check("the mixins build on Frappe HR's own context", "data, default_data = super().get_data_for_eval()" in glue
      and "default_data.update(given)" in glue and "data = super()._get_component_eval_context()" in glue)
check("the setting's field name is the one the code reads", 'FIELD = "custom_secondary_employment_rate"' in glue
      and 'SETTINGS = "Payroll Settings"' in glue)
fields = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
by_name = {row["name"]: row for row in fields}
rate_field = by_name.get("Payroll Settings-custom_secondary_employment_rate") or {}
check("Payroll Settings' Secondary Employment PAYE Rate: a percent, URA's 40, never below nought",
      (rate_field.get("fieldname"), rate_field.get("fieldtype"), rate_field.get("default"), rate_field.get("non_negative"),
       rate_field.get("insert_after")) == (G.FIELD, "Percent", str(R.RATE), 1, "custom_branches_verify_attendance"),
      rate_field)
tick = by_name.get("Employee-custom_secondary_employment") or {}
check("the Employee's Secondary Employment: a tick under NSSF Voluntary, by the name the formula reads",
      (tick.get("fieldname"), tick.get("fieldtype"), tick.get("insert_after"))
      == (R.SECONDARY, "Check", "custom_nssf_voluntary"), tick)
anchors = [(row["dt"], row.get("insert_after")) for row in fields]
check("nothing else sits under either", anchors.count(("Payroll Settings", "custom_branches_verify_attendance")) == 1
      and anchors.count(("Employee", "custom_nssf_voluntary")) == 1)
check("both are in the fixtures the app ships", all('"%s",' % name in hooks_src for name in
                                                    ("Payroll Settings-custom_secondary_employment_rate",
                                                     "Employee-custom_secondary_employment")))
patches = read("hrms_addon", "patches.txt")
check("the patch runs after the doctypes are migrated, and after the NSSF age was written on",
      "hrms_addon.patches.v1_0.secondary_employment_paye" in patches.split("[post_model_sync]")[1]
      and patches.index("secondary_employment_paye") > patches.index("nssf_age_limit"))
print("the wiring: the hooks, the two fields, the patch")

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL SECONDARY EMPLOYMENT CHECKS PASSED")
