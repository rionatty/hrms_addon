"""Verify the salaried structure's lines of 31 Oct 2026, without a bench:

    python scripts/verify_structure_lines.py

patches/v1_0/salaried_structure_lines.py gives Luuka Salaried 2026-27 the
lines Luuka's own payroll has, Union Dues, and takes recoveries, encashments
and settlements in full (salary_structure_rules.taxable_formula):

  1  the rules: Taxable Salary read by the abbreviations the site has, the
     overtime it lacked added, once
  2  the patch, run on a stand-in for Frappe: what it makes, corrects and
     adds, and nothing the second time
  3  the modules make their components taken in full; nobody is exempted
"""
import importlib.util
import math
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label, detail=""):
    if not condition:
        fail.append("%s%s" % (label, ("   <- %s" % (detail,)) if detail != "" else ""))


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 1. Taxable Salary ─────────────────────────────────────────────────
rules = load("salary_structure_rules", os.path.join(APP, "salary_structure_rules.py"))
SITE = {"BS", "MA", "CB", "LE", "BC", "A", "PB", "OT1", "OT_20", "SOT", "SOT1", "OT3", "A.t"}
ON_THE_SITE = "BS + MA + CB + LE + BC + A + PB + (OT_15 or 0) + (OT_20 or 0)"
WANTED = "BS + MA + CB + LE + BC + A + PB + OT1 + (OT_20 or 0) + SOT + OT3"
got = rules.taxable_formula(ON_THE_SITE, SITE, ("SOT", "OT3"))
check(got == WANTED, "Overtime 1.0's old OT_15 read as OT1, Special Overtime and Overtime 3 counted", got)
check(rules.taxable_formula(got, SITE, ("SOT", "OT3")) == got, "and nothing more the second time")
check(rules.taxable_formula("BS + MA + CB + LE + BC + A + PB + OT1 + OT_20", SITE, ("SOT", "OT3"))
      == "BS + MA + CB + LE + BC + A + PB + OT1 + OT_20 + SOT + OT3", "a formula already corrected by hand takes the two")
check(rules.taxable_formula(ON_THE_SITE, SITE | {"OT_15"}, ()) == ON_THE_SITE,
      "OT_15 is left where a component still has it")
check(rules.taxable_formula("BS + OT1", SITE - {"SOT"}, ("SOT", "OT3")) == "BS + OT1 + OT3",
      "an abbreviation the site has not got is never written in: it would stop every slip")
check(rules.taxable_formula("BS + SOT1", SITE, ("SOT",)) == "BS + SOT1 + SOT", "SOT1 is not SOT")
names = set(re.findall(r"(?<![\w.])[A-Za-z_][\w]*(?![\w(])", WANTED)) - {"or", "and", "if", "else", "not", "in"}
check(names <= SITE, "every name the new formula uses is an abbreviation the site has", sorted(names - SITE))

# union dues: 3% of the salary earned (Basic as the slip has it, after the days not worked), half up to the
# shilling, for those ticked Union Member; the line is not cut again, which the structure would refuse
union = "floor(BS * 0.03 + 0.500001) if custom_union_member else 0"
for earned, member, wanted in ((1000000, 1, 30000), (882654, 1, 26480), (823165, 1, 24695), (646420, 1, 19393),
                               (1000000, 0, 0)):
    value = eval(union, {"__builtins__": {}, "floor": math.floor}, {"BS": earned, "custom_union_member": member})
    check(value == wanted, "union dues on %s earned, member %s: %s" % (earned, member, wanted), value)
line = {"idx": 9, "salary_component": "Union Dues", "formula": union, "depends_on_payment_days": 0}
check(rules.row_errors("deductions", line, {"type": "Deduction", "disabled": 0}, ["PAYEE"], ["BS"]) == [],
      "the structure takes the Union Dues line: on the earned Basic, not cut a second time")
check(rules.row_errors("deductions", dict(line, depends_on_payment_days=1), {"type": "Deduction", "disabled": 0}, [],
                       ["BS"]) != [], "and would refuse it cut for the days twice")
print("rules: Taxable Salary by the abbreviations the site has, the overtime counted once; union dues at 3% of the "
      "salary earned")


# ── 2. The patch, on a stand-in for Frappe ────────────────────────────
class Row(types.SimpleNamespace):
    pass


class Structure:
    def __init__(self, docstatus, earnings, deductions):
        self.name = "Luuka Salaried 2026-27"
        self.docstatus = docstatus
        self.earnings = [Row(salary_component=c, formula=f) for c, f in earnings]
        self.deductions = [Row(salary_component=c, formula=f) for c, f in deductions]
        self.flags = types.SimpleNamespace()
        self.saved = 0

    def get(self, table):
        return getattr(self, table)

    def append(self, table, row):
        getattr(self, table).append(Row(formula="", **row))

    def save(self):
        self.saved += 1


class Site:
    def __init__(self, structure):
        abbr = {"Basic": "BS", "Meals Allowance": "MA", "Car Benefit": "CB", "Leave Encashment": "LE",
                "Bonus and Commisions": "BC", "Arrear": "A", "Annual Performance Bonus": "PB", "Overtime 1.0": "OT1",
                "Overtime 2.0": "OT_20", "Special Overtime": "SOT", "Overtime 3": "OT3", "Advance Recovery": "AR",
                "Additional Advance": "ADDA", "Arrears Deductions": "ARRD", "Other Deduction": "OTHD", "Penalties": "PNL",
                "Loan Repayment": "LR", "Taxable Salary": "TS"}
        days = {"Advance Recovery": 1, "Loan Repayment": 1, "Leave Encashment": 1, "Basic": 1}
        self.components = {name: {"salary_component_abbr": a, "depends_on_payment_days": days.get(name, 0)}
                           for name, a in abbr.items()}
        self.lines = [{"name": "SD-1", "parenttype": "Salary Structure", "salary_component": "Leave Encashment",
                       "depends_on_payment_days": 1},
                      {"name": "SD-2", "parenttype": "Salary Slip", "salary_component": "Advance Recovery",
                       "depends_on_payment_days": 1},
                      {"name": "SD-3", "parenttype": "Salary Structure", "salary_component": "Basic",
                       "depends_on_payment_days": 1}]
        self.structure = structure
        self.recovered = 0
        self.inserted = []

    def frappe(self):
        site = self

        class Inserted:
            def __init__(self, values):
                self.values = values
                self.flags = types.SimpleNamespace()

            def insert(self):
                site.components[self.values["salary_component"]] = dict(self.values)
                site.inserted.append(self.values["salary_component"])

        def exists(doctype, name=None):
            if doctype == "DocType":
                return True
            if doctype == "Salary Component":
                return name in site.components
            if doctype == "Salary Structure":
                return site.structure is not None and name == site.structure.name
            raise AssertionError("asked whether %s %s exists" % (doctype, name))

        def get_value(doctype, name, field):
            assert doctype == "Salary Component"
            return (site.components.get(name) or {}).get(field)

        def set_value(doctype, name, field, value, update_modified=True):
            if doctype == "Salary Component":
                site.components[name][field] = value
            else:
                next(line for line in site.lines if line["name"] == name)[field] = value

        def get_all(doctype, filters=None, pluck=None):
            if doctype == "Salary Component":
                return [values["salary_component_abbr"] for values in site.components.values()]
            assert doctype == "Salary Detail"
            out = [line for line in site.lines if line["parenttype"] == filters["parenttype"]
                   and line["salary_component"] in filters["salary_component"][1]
                   and line["depends_on_payment_days"] == filters["depends_on_payment_days"]]
            return [line[pluck] for line in out]

        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                return Inserted(doctype)
            assert doctype == "Salary Structure"
            return site.structure

        module = types.ModuleType("frappe")
        module.db = types.SimpleNamespace(exists=exists, get_value=get_value, set_value=set_value)
        module.get_all = get_all
        module.get_doc = get_doc
        return module


def run(site):
    sys.modules["frappe"] = site.frappe()
    package = types.ModuleType("hrms_addon.hrms_addon")
    package.salary_structure_rules = rules
    leave_advances = types.ModuleType("hrms_addon.hrms_addon.leave_advances")

    def recovery_component(company=None):
        site.recovered += 1
        site.components.setdefault("Leave Advance Recovery", {"salary_component_abbr": "LAR", "depends_on_payment_days": 0})
        return "Leave Advance Recovery"

    leave_advances.recovery_component = recovery_component
    package.leave_advances = leave_advances
    sys.modules.update({"hrms_addon": types.ModuleType("hrms_addon"), "hrms_addon.hrms_addon": package,
                        "hrms_addon.hrms_addon.leave_advances": leave_advances})
    patch = load("salaried_structure_lines", os.path.join(REPO, "hrms_addon", "patches", "v1_0", "salaried_structure_lines.py"))
    patch.execute()
    return patch


EARNINGS = [("Basic", "(base * 1)"), ("Arrear", ""), ("Leave Encashment", ""), ("Overtime 1.0", ""),
            ("Overtime 2.0", ""), ("Taxable Salary", ON_THE_SITE)]
DEDUCTIONS = [("Local Service Tax", "lst"), ("PAYEE", "paye"), ("NSSF Employee", "nssf"), ("Penalties", "")]
site = Site(Structure(1, EARNINGS, DEDUCTIONS))
patch = run(site)
union_dues = site.components.get("Union Dues") or {}
check(site.inserted == ["Union Dues"] and union_dues.get("salary_component_abbr") == "UD"
      and union_dues.get("type") == "Deduction" and union_dues.get("depends_on_payment_days") == 0
      and union_dues.get("amount_based_on_formula") == 1 and union_dues.get("formula") == union,
      "Union Dues made: a deduction, 3% of the package for a Union Member, never cut for days", union_dues)
check(site.recovered == 1, "Leave Advance Recovery made the way leave advances make it")
check(all(site.components[name]["depends_on_payment_days"] == 0
          for name in ("Advance Recovery", "Loan Repayment", "Leave Encashment"))
      and site.components["Basic"]["depends_on_payment_days"] == 1,
      "recoveries and the encashment taken in full; Basic still by the days", site.components)
check([line["depends_on_payment_days"] for line in site.lines] == [0, 1, 1],
      "and a structure's line of them too; a slip and Basic are left alone", site.lines)
structure = site.structure
check(structure.saved == 1, "the structure saved once", structure.saved)
check([row.salary_component for row in structure.earnings] == [c for c, _f in EARNINGS] + ["Special Overtime", "Overtime 3"],
      "Special Overtime and Overtime 3 added to the earnings", [row.salary_component for row in structure.earnings])
check([row.salary_component for row in structure.deductions] == [c for c, _f in DEDUCTIONS] + [
    "Advance Recovery", "Additional Advance", "Arrears Deductions", "Leave Advance Recovery", "Other Deduction",
    "Loan Repayment", "Union Dues"], "the deductions Luuka's payroll has added, Penalties not twice",
      [row.salary_component for row in structure.deductions])
check(next(row.formula for row in structure.earnings if row.salary_component == "Taxable Salary") == WANTED,
      "Taxable Salary corrected on the structure")
check([row.formula for row in structure.deductions[:3]] == ["lst", "paye", "nssf"],
      "LST, PAYEE and NSSF left as they are: nobody is exempted")
patch.execute()
check(structure.saved == 1 and site.inserted == ["Union Dues"], "the second run changes nothing", structure.saved)

draft = Site(Structure(2, EARNINGS, DEDUCTIONS))
run(draft)
check(draft.structure.saved == 0 and len(draft.structure.deductions) == len(DEDUCTIONS), "a cancelled structure is left alone")
nothing = Site(None)
run(nothing)
check(nothing.inserted == ["Union Dues"], "a site without the structure still gets the components")
print("patch: Union Dues and Leave Advance Recovery made, recoveries taken in full, the lines added, once")

# ── 3. The modules, and nobody exempted ───────────────────────────────
for module, abbr in (("advances", "AR"), ("loans", "LR"), ("penalties", "PEN"), ("settlements", "TB")):
    source = read("hrms_addon", "hrms_addon", module + ".py")
    check(re.search(r'"salary_component_abbr": "%s", "depends_on_payment_days": 0' % abbr, source),
          "%s makes its component taken in full, never cut for the days not worked" % module)
patches = read("hrms_addon", "patches.txt")
check("hrms_addon.patches.v1_0.salaried_structure_lines" in patches.split("[post_model_sync]")[1],
      "the patch runs after the doctypes are migrated")
everything = "".join(read(os.path.relpath(path, REPO)) for folder in ("hrms_addon",)
                     for path in __import__("glob").glob(os.path.join(REPO, folder, "**", "*.*"), recursive=True)
                     if path.endswith((".py", ".json", ".js")))
check("custom_nssf_exempt" not in everything and "custom_paye_special" not in everything,
      "nobody is exempted from NSSF or put on a PAYE of their own")
print("modules: advances, loans, penalties and settlements take their components in full; nobody exempted")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL STRUCTURE LINE CHECKS PASSED")
