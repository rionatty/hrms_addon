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

# ── 4. Overtime in full, Leave Advance, the pay NSSF, LST and PAYE are on ──
LST_11_OCT = ("(0 if (gross_pay - (rmb or 0) - (CB or 0)) <= 100000 else 1250 if (gross_pay - (rmb or 0) - (CB or 0)) <= 200000 "
              "else 2500 if (gross_pay - (rmb or 0) - (CB or 0)) <= 300000 else 5000 if (gross_pay - (rmb or 0) - (CB or 0)) "
              "<= 400000 else 7500 if (gross_pay - (rmb or 0) - (CB or 0)) <= 500000 else 10000 if (gross_pay - (rmb or 0) - "
              "(CB or 0)) <= 600000 else 15000 if (gross_pay - (rmb or 0) - (CB or 0)) <= 700000 else 17500 if (gross_pay - "
              "(rmb or 0) - (CB or 0)) <= 800000 else 20000 if (gross_pay - (rmb or 0) - (CB or 0)) <= 900000 else 22500 if "
              "(gross_pay - (rmb or 0) - (CB or 0)) <= 1000000 else 25000) if getdate(end_date).month in (7, 8, 9, 10) else 0")
PAYE_11_OCT = ("floor((0 if (gross_pay - (rmb or 0) - (LST or 0)) <= 335000 else ((gross_pay - (rmb or 0) - (LST or 0)) - "
               "335000) * 0.2 if (gross_pay - (rmb or 0) - (LST or 0)) <= 410000 else 15000 + ((gross_pay - (rmb or 0) - "
               "(LST or 0)) - 410000) * 0.25 if (gross_pay - (rmb or 0) - (LST or 0)) <= 485000 else 33750 + ((gross_pay - "
               "(rmb or 0) - (LST or 0)) - 485000) * 0.3 if (gross_pay - (rmb or 0) - (LST or 0)) <= 10000000 else 2888250 + "
               "((gross_pay - (rmb or 0) - (LST or 0)) - 10000000) * 0.4) + 0.500001)")
NSSF_11_OCT = "floor((gross_pay - (rmb or 0) - (CB or 0)) * 0.05 + 0.500001)"
NSSFER_11_OCT = "floor((gross_pay - (rmb or 0) - (CB or 0)) * 0.1 + 0.500001)"
fixed = {name: rules.pay_base_formula(name, formula) for name, formula in (
    ("Local Service Tax", LST_11_OCT), ("PAYEE", PAYE_11_OCT), ("NSSF Employee", NSSF_11_OCT),
    ("NSSF Employer 10%", NSSFER_11_OCT))}
check("(CB or 0)" not in fixed["Local Service Tax"] + fixed["NSSF Employee"] + fixed["NSSF Employer 10%"]
      and fixed["PAYEE"].count(rules.TAXABLE_PAY) == PAYE_11_OCT.count(rules.TAXABLE_PAY_WAS) == 8,
      "every place the old formulas name the pay is corrected", fixed)
check(all(rules.pay_base_formula(name, formula) == formula for name, formula in fixed.items())
      and rules.pay_base_formula("Basic", "base") == "base" and rules.pay_base_formula("PAYEE", "") == "",
      "and nothing more the second time, nor on another line")


def pay(gross, cb=0, sw=0, rmb=0):
    data = {"gross_pay": gross, "CB": cb, "SW": sw, "rmb": rmb, "end_date": "2026-09-25"}
    scope = {"__builtins__": {}, "floor": math.floor, "getdate": __import__("datetime").date.fromisoformat}
    data["LST"] = eval(fixed["Local Service Tax"], dict(scope), dict(data))
    return (data["LST"], eval(fixed["PAYEE"], dict(scope), dict(data)), eval(fixed["NSSF Employee"], dict(scope), dict(data)))


check(pay(4000000) == (25000, 1080750, 200000), "a plain 4,000,000 as before: LST 25,000, PAYE 1,080,750, NSSF 200,000",
      pay(4000000))
check(pay(4000000, cb=500000) == (25000, 1230750, 200000),
      "a car benefit of 500,000 is taxed, and no longer takes NSSF down", pay(4000000, cb=500000))
check(pay(4300000, sw=300000) == (25000, 1080750, 200000),
      "a Sacco withdrawal of 300,000 is neither taxed nor charged NSSF", pay(4300000, sw=300000))
check(pay(130000, sw=40000)[0] == 0 and pay(130000)[0] == 1250, "nor counted for LST")


class Pays:
    """A stand-in for Frappe with the components, overtime types and structure lines the second patch reads."""

    def __init__(self):
        self.components = {"Overtime": {"depends_on_payment_days": 1}, "Overtime 3": {"depends_on_payment_days": 0},
                           "Night Overtime": {"depends_on_payment_days": 1}, "Basic": {"depends_on_payment_days": 1},
                           "Leave Advance": {"formula": "base * .6\n", "amount_based_on_formula": 1}}
        self.types = ["Overtime 3", "Night Overtime", None]
        self.lines = [
            {"name": "L1", "parenttype": "Salary Structure", "salary_component": "Overtime", "depends_on_payment_days": 1},
            {"name": "L2", "parenttype": "Salary Slip", "salary_component": "Overtime", "depends_on_payment_days": 1},
            {"name": "L3", "parenttype": "Salary Structure", "salary_component": "Leave Advance", "formula": "base * .6",
             "amount_based_on_formula": 1},
            {"name": "L4", "parenttype": "Salary Structure", "salary_component": "Local Service Tax", "formula": LST_11_OCT},
            {"name": "L5", "parenttype": "Salary Structure", "salary_component": "PAYEE", "formula": PAYE_11_OCT},
            {"name": "L6", "parenttype": "Salary Structure", "salary_component": "NSSF Employee", "formula": NSSF_11_OCT},
            {"name": "L7", "parenttype": "Salary Structure", "salary_component": "NSSF Employer 10%", "formula": NSSFER_11_OCT},
            {"name": "L8", "parenttype": "Salary Slip", "salary_component": "PAYEE", "formula": PAYE_11_OCT}]
        self.writes = 0

    def frappe(self):
        site = self

        def matches(line, filters):
            for field, wanted in filters.items():
                value = line.get(field)
                if isinstance(wanted, list) and wanted[0] == "in":
                    if value not in wanted[1]:
                        return False
                elif value != wanted:
                    return False
            return True

        def get_all(doctype, filters=None, pluck=None, fields=None):
            if doctype == "Overtime Type":
                return [name for name in site.types if name]
            out = [line for line in site.lines if matches(line, filters or {})]
            if pluck:
                return [line[pluck] for line in out]
            return [types.SimpleNamespace(**{field: line.get(field) for field in fields}) for line in out]

        def set_value(doctype, name, field, value=None, update_modified=True):
            site.writes += 1
            values = field if isinstance(field, dict) else {field: value}
            record = site.components[name] if doctype == "Salary Component" else next(
                line for line in site.lines if line["name"] == name)
            record.update(values)

        module = types.ModuleType("frappe")
        module.db = types.SimpleNamespace(
            exists=lambda doctype, name=None: doctype == "DocType" or name in site.components,
            get_value=lambda doctype, name, field: site.components.get(name, {}).get(field),
            set_value=set_value)
        module.get_all = get_all
        return module


pays = Pays()
sys.modules["frappe"] = pays.frappe()
second = load("overtime_and_pay_bases", os.path.join(REPO, "hrms_addon", "patches", "v1_0", "overtime_and_pay_bases.py"))
second.execute()
by_line = {line["name"]: line for line in pays.lines}
check(pays.components["Overtime"]["depends_on_payment_days"] == 0
      and pays.components["Night Overtime"]["depends_on_payment_days"] == 0
      and pays.components["Basic"]["depends_on_payment_days"] == 1,
      "Overtime and every component an Overtime Type pays into are paid in full; Basic still by the days", pays.components)
check(by_line["L1"]["depends_on_payment_days"] == 0 and by_line["L2"]["depends_on_payment_days"] == 1,
      "and a structure's overtime line too; a slip is left alone")
check(pays.components["Leave Advance"] == {"formula": "", "amount_based_on_formula": 0}
      and by_line["L3"]["formula"] == "" and by_line["L3"]["amount_based_on_formula"] == 0,
      "Leave Advance takes no formula, on the component or a structure's line", (pays.components["Leave Advance"], by_line["L3"]))
check([by_line[name]["formula"] for name in ("L4", "L5", "L6", "L7")]
      == [fixed["Local Service Tax"], fixed["PAYEE"], fixed["NSSF Employee"], fixed["NSSF Employer 10%"]]
      and by_line["L8"]["formula"] == PAYE_11_OCT, "LST, PAYEE and both NSSF lines on the right pay; a slip untouched")
writes = pays.writes
second.execute()
check(pays.writes == writes, "the second run writes nothing", pays.writes - writes)
check("hrms_addon.patches.v1_0.overtime_and_pay_bases" in patches.split("[post_model_sync]")[1]
      and patches.index("overtime_and_pay_bases") > patches.index("salaried_structure_lines"),
      "it runs after the doctypes are migrated, and after the lines are added")
print("overtime and pay bases: overtime paid in full, Leave Advance without a formula, NSSF, LST and PAYE on the right "
      "pay, once")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL STRUCTURE LINE CHECKS PASSED")
