"""Checks the USD payroll's grossed-up tax, without a bench:

    python scripts/verify_usd_gross_up.py

Luuka, 8 Nov 2026: their own expatriate payroll for September 2026 grosses
the pay up, as the Income Tax Act has it (s.19(1)(c), s.58: tax an employer
pays for an employee is the employee's income too; s.19(1)(a): allowances
are). So:

  1. Luuka's own September figures come out of the formulas, to the shilling
  2. the gross-up undoes itself in every band: what PAYE and NSSF leave of
     the gross is the net, for any pay
  3. no NSSF past the age limit unless voluntary; LST only July to October;
     no allowance is none
  4. each line in USD to the cent, Tax Paid by Company their sum, so the
     employee is left the USD pay
  5. the formulas name only what Frappe HR gives a formula
  6. the patch: every USD structure's lines, by abbreviation; a missing line
     added from its component; shilling structures untouched; twice is once;
     neither the NSSF age nor the second-job patch rewrites them again
  7. the wiring: the UGX Allowance field, its fixture, the patch
"""
import ast
import contextlib
import datetime
import importlib.util
import io
import json
import math
import os
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


R = load("currency_payroll_rules", os.path.join(APP, "currency_payroll_rules.py"))  # no Frappe import
NSSF = load("nssf_age_rules", os.path.join(APP, "nssf_age_rules.py"))
SECOND = load("secondary_employment_rules", os.path.join(APP, "secondary_employment_rules.py"))
print("loaded currency_payroll_rules.py without Frappe")

GLOBALS = {"floor": math.floor, "round": round, "getdate": lambda value: datetime.date.fromisoformat(str(value)[:10]),
           "__builtins__": {}}
AMOUNTS = R.gross_up_amounts()
LINES = R.usd_gross_up_formulas()


def context(usd, allowance, rate=3920, end="2026-09-25", age=40, limit=55, voluntary=0):
    return {"USDP": usd, "custom_exchange_rate": rate, R.ALLOWANCE: allowance, "end_date": end,
            "nssf_age_limit": limit, "employee_age": age, "custom_nssf_voluntary": voluntary}


def ugx(name, **values):
    return eval(AMOUNTS[name], dict(GLOBALS), context(**values))


def usd(abbr, **values):
    return eval(LINES[abbr][1], dict(GLOBALS), context(**values))


def bands(chargeable):
    return eval(R.paye_formula("x"), dict(GLOBALS), {"x": chargeable})


# ── 1. Luuka's September 2026 ─────────────────────────────────────────
# their expatriate payroll's figures, by pay (basic USD, allowance in shillings at 3,920): gross, PAYE, NSSF 5%, 10%
SEPTEMBER = [
    (1300, 400000, 8283461.538461538, 2373288.4615384615, 415423.07692307694, 830846.1538461539),
    (1300, 200000, 7975769.23076923, 2280980.769230769, 400038.4615384615, 800076.923076923),
    (1400, 200000, 8578846.153846154, 2461903.846153846, 430192.30769230775, 860384.6153846155),
    (2000, 200000, 12596818.181818182, 3926977.272727273, 631090.9090909092, 1262181.8181818184),
    (4255, 0, 28305181.818181816, 10210322.727272727, 1416509.0909090908, 2833018.1818181816),
    (2200, 400000, 14385909.09090909, 4642613.636363636, 720545.4545454546, 1441090.9090909092),
    (2000, 400000, 12960454.545454545, 4072431.818181818, 649272.7272727273, 1298545.4545454546),
    (6000, 0, 40742272.72727273, 15185159.09090909, 2038363.6363636365, 4076727.272727273),
    (1500, 760000, 10051363.636363635, 2908795.4545454537, 503818.18181818177, 1007636.3636363635),
    (3000, 0, 19360454.545454543, 6632431.8181818165, 969272.7272727272, 1938545.4545454544),
]
off = []
for basic, allowance, gross, paye, employee, employer in SEPTEMBER:
    got = {name: ugx(name, usd=basic, allowance=allowance) for name in ("gross", "paye", "employee", "employer", "lst")}
    shillings = [math.floor(figure + 0.500001) for figure in (paye, employee, employer)]
    if abs(got["gross"] - gross) > 0.01 or [got["paye"], got["employee"], got["employer"]] != shillings or got["lst"] != 25000:
        off.append((basic, allowance, got))
check("Luuka's own September payroll comes out of the formulas: the gross to the cent, PAYE and NSSF 5% and 10% "
      "to the shilling, LST 25,000, for each of its ten pays", not off, off)
print("Luuka's September: reproduced")

# ── 2. The gross-up undoes itself ─────────────────────────────────────
bad = []
for net_shillings in (0, 50000, 200000, 318250, 318251, 350000, 374500, 374501, 400000, 427000, 427001, 500000,
                      5096000, 6611750, 6611751, 9000000, 27000000):
    for exempt in (False, True):
        values = dict(usd=net_shillings / 3920.0, allowance=0, age=60 if exempt else 40)
        gross, paye = ugx("gross", **values), ugx("paye", **values)
        rate = 0 if exempt else 0.05
        left = gross - bands(gross) - rate * gross
        if abs(left - net_shillings) > 0.01 or paye != math.floor(bands(gross) + 0.500001):
            bad.append((net_shillings, exempt, gross, left, paye, bands(gross)))
check("in every band, what the 2026 PAYE and NSSF 5% leave of the gross is the net, and PAYE is the bands' on "
      "the gross; without NSSF too", not bad, bad[:3])
check("each band's top is where the next starts: 335,000 / 410,000 / 485,000 / 10,000,000 of gross",
      [round(ugx("gross", usd=n / 3920.0, allowance=0)) for n in (318250, 374500, 427000, 6611750)]
      == [335000, 410000, 485000, 10000000])
print("the gross-up: inverts the bands, with and without NSSF")

# ── 3. NSSF's age, LST's months, no allowance ─────────────────────────
check("past the NSSF age limit, no NSSF either side, and the pay grossed up for PAYE alone",
      (ugx("employee", usd=1300, allowance=400000, age=60), ugx("employer", usd=1300, allowance=400000, age=60))
      == (0, 0) and abs(ugx("gross", usd=1300, allowance=400000, age=60)
                        - (1300 * 3920 + 400000 - 111750) / 0.7) < 0.01)
check("unless NSSF Voluntary is ticked", ugx("employee", usd=1300, allowance=400000, age=60, voluntary=1) == 415423)
check("and a limit of 0 is none", ugx("employee", usd=1300, allowance=400000, age=70, limit=0) == 415423)
check("LST only July to October: none on a November slip",
      ugx("lst", usd=1300, allowance=0, end="2026-11-25") == 0 and ugx("lst", usd=1300, allowance=0, end="2026-07-25") == 25000)
check("LST by the month's pay, as the shilling structures have it",
      [ugx("lst", usd=n / 3920.0, allowance=0) for n in (100000, 150000, 950000, 1000001)] == [0, 1250, 22500, 25000])
check("no allowance is none", ugx("gross", usd=1300, allowance=None) == ugx("gross", usd=1300, allowance=0))
print("NSSF's age, LST's months, an empty allowance")

# ── 4. The slip's lines, in USD ───────────────────────────────────────
tables = {abbr: table for abbr, (table, _formula) in LINES.items()}
check("the lines by their tables: Tax Paid by Company an earning, LST, PAYE and NSSF Employee deductions, the "
      "employer's 10% an employer contribution",
      tables == {"TPBC": "earnings", "LST": "deductions", "payee": "deductions", "NSSFE": "deductions",
                 "NSSFEC": "employer_contributions"}, tables)
nets = []
for basic, allowance, *_figures in SEPTEMBER:
    line = {abbr: usd(abbr, usd=basic, allowance=allowance) for abbr in LINES}
    nets.append(round(basic + line["TPBC"] - line["LST"] - line["payee"] - line["NSSFE"], 2) == basic)
check("Tax Paid by Company is LST, PAYE and NSSF 5% to the cent, so each employee is left the USD pay", all(nets))
line = {abbr: usd(abbr, usd=1300, allowance=400000) for abbr in LINES}
check("each line is its shillings at the month's rate, to the cent: PAYE 605.43, NSSF 105.98, LST 6.38",
      (line["payee"], line["NSSFE"], line["LST"]) == (605.43, 105.98, 6.38), line)
print("the slip: in USD to the cent, the net the USD pay")

# ── 5. What the formulas name ─────────────────────────────────────────
GIVEN = {"USDP", "custom_exchange_rate", R.ALLOWANCE, "end_date", NSSF.LIMIT, NSSF.AGE, NSSF.VOLUNTARY,
         "floor", "round", "getdate"}
named = set()
for _table, formula in LINES.values():
    named |= {node.id for node in ast.walk(ast.parse(formula, mode="eval")) if isinstance(node, ast.Name)}
check("the formulas name only the USD pay, the rate, the allowance, the slip's end, NSSF's age, and Frappe HR's "
      "floor, round and getdate", named <= GIVEN, sorted(named - GIVEN))
check("NSSF's age is read by the names nssf_age.py gives a formula",
      R.NSSF_EXEMPT == "%s and %s >= %s and not %s" % (NSSF.LIMIT, NSSF.AGE, NSSF.LIMIT, NSSF.VOLUNTARY))
utils = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "utils.py")
if os.path.exists(utils):
    source = open(utils, encoding="utf-8").read()
    block = source[source.index("COMPONENT_EVAL_GLOBALS = {"):source.index("}", source.index("COMPONENT_EVAL_GLOBALS = {"))]
    check("Frappe HR gives a formula floor, round and getdate",
          all('"%s":' % name in block for name in ("floor", "round", "getdate")), block)
else:
    print("Frappe HR's formula globals: NOT CHECKED, not found under %s" % APPS_ROOT)
check("the second-job patch leaves the USD PAYE alone, and the NSSF age patch the USD NSSF",
      SECOND.secondary_formula(LINES["payee"][1]) == LINES["payee"][1]
      and NSSF.exempt_formula(LINES["NSSFE"][1]) == LINES["NSSFE"][1])
print("the formulas: only what Frappe HR gives them")


# ── 6. The patch ──────────────────────────────────────────────────────
class Row(dict):
    __getattr__ = dict.get


SITE = {}


def fresh_site():
    SITE["components"] = {
        "PAYEE": Row(name="PAYEE", salary_component_abbr="payee", statistical_component=0, is_tax_applicable=0,
                     is_flexible_benefit=0, variable_based_on_taxable_salary=0, depends_on_payment_days=0,
                     do_not_include_in_total=0, exempted_from_income_tax=0, do_not_include_in_accounts=0,
                     accrual_component=0)}
    SITE["details"] = [
        Row(name="D1", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure", parentfield="earnings",
            abbr="USDP", formula="base"),
        Row(name="D2", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure", parentfield="earnings",
            abbr="TPBC", formula="old cover"),
        Row(name="D3", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure", parentfield="deductions",
            abbr="LST", formula="old lst"),
        Row(name="D4", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure", parentfield="deductions",
            abbr="NSSFE", formula="old nssf"),
        Row(name="D5", parent="Luuka USD Net Pay 2026-27", parenttype="Salary Structure",
            parentfield="employer_contributions", abbr="NSSFEC", formula="old employer"),
        Row(name="D6", parent="Luuka Salaried 2026-27", parenttype="Salary Structure", parentfield="deductions",
            abbr="payee", formula="shilling paye"),
        Row(name="D7", parent="Luuka Salaried 2026-27", parenttype="Salary Structure", parentfield="deductions",
            abbr="LST", formula="shilling lst"),
        Row(name="D8", parent="Sal Slip/0001", parenttype="Salary Slip", parentfield="earnings", abbr="USDP",
            formula="base")]
    SITE["cleared"] = []


class Structure:
    def __init__(self, name):
        self.name, self.docstatus = name, 1

    def append(self, table, values):
        row = Row(values, parent=self.name, parenttype="Salary Structure", parentfield=table,
                  idx=1 + len([d for d in SITE["details"] if d.parent == self.name and d.parentfield == table]))

        def db_insert():
            row["name"] = "D%d" % (len(SITE["details"]) + 1)
            SITE["details"].append(row)
        row.db_insert = db_insert
        return row


def get_all(doctype, filters=None, fields=None, **kwargs):
    assert doctype == "Salary Detail", doctype
    return [Row(d) for d in SITE["details"] if all(d.get(key) == value for key, value in (filters or {}).items())]


def set_value(doctype, name, values, value=None, update_modified=True):
    row = next(d for d in SITE["details"] if d.name == name)
    row.update(values if isinstance(values, dict) else {values: value})


def get_value(doctype, filters, fields, as_dict=False):
    found = next((c for c in SITE["components"].values()
                  if c.salary_component_abbr == filters.get("salary_component_abbr")), None)
    return Row({field: found.get(field) for field in fields}) if found else None


frappe = types.ModuleType("frappe")
frappe.db = types.SimpleNamespace(exists=lambda doctype, name=None: True, set_value=set_value, get_value=get_value)
frappe.get_all = get_all
frappe.get_doc = lambda doctype, name: Structure(name)
frappe.clear_document_cache = lambda doctype, name: SITE["cleared"].append(name)
package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
app.currency_payroll_rules = R
sys.modules.update({"frappe": frappe, "hrms_addon": package, "hrms_addon.hrms_addon": app,
                    "hrms_addon.hrms_addon.currency_payroll_rules": R})
P = load("usd_gross_up", os.path.join(REPO, "hrms_addon", "patches", "v1_0", "usd_gross_up.py"))
fresh_site()
said = io.StringIO()
with contextlib.redirect_stdout(said):
    P.execute()
usd_rows = {d.abbr: d for d in SITE["details"] if d.parent == "Luuka USD Net Pay 2026-27"}
check("the USD structure's lines are written over, by abbreviation",
      all(usd_rows[abbr].formula == LINES[abbr][1] for abbr in ("TPBC", "LST", "NSSFE", "NSSFEC")))
added = usd_rows.get("payee") or Row()
check("its missing PAYE line is added from the component the site abbreviates payee, in its deductions, with the "
      "component's own flags, as submitted as the structure",
      (added.salary_component, added.parentfield, added.formula, added.amount_based_on_formula, added.docstatus,
       added.depends_on_payment_days, added.idx) == ("PAYEE", "deductions", LINES["payee"][1], 1, 1, 0, 3), added)
check("and the migrate's output says so", "Luuka USD Net Pay 2026-27 had no PAYEE line: added" in said.getvalue(),
      said.getvalue())
check("the USD pay itself, the shilling structure and a slip's own lines are untouched",
      usd_rows["USDP"].formula == "base"
      and [d.formula for d in SITE["details"] if d.parent == "Luuka Salaried 2026-27"] == ["shilling paye", "shilling lst"]
      and next(d for d in SITE["details"] if d.parenttype == "Salary Slip").formula == "base")
check("the structure is read afresh by the next slip", SITE["cleared"] == ["Luuka USD Net Pay 2026-27"])
before = [dict(d) for d in SITE["details"]]
with contextlib.redirect_stdout(io.StringIO()):
    P.execute()
check("run twice, it is the same as once", [dict(d) for d in SITE["details"]] == before)
fresh_site()
SITE["components"] = {}
said = io.StringIO()
with contextlib.redirect_stdout(said):
    P.execute()
check("a line no component is abbreviated for is named, not guessed",
      "still has no line abbreviated payee" in said.getvalue()
      and not [d for d in SITE["details"] if d.abbr == "payee" and d.parent == "Luuka USD Net Pay 2026-27"],
      said.getvalue())
print("the patch: the USD structure's lines, a missing one added, the rest untouched")

# ── 7. The wiring ─────────────────────────────────────────────────────
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
allowance = fields.get("Salary Structure Assignment-custom_ugx_allowance") or {}
check("the assignment's UGX Allowance: shillings (the company's currency), filled in after submit, never below "
      "nought, under Transport Allowance, by the name the formulas read",
      (allowance.get("fieldname"), allowance.get("fieldtype"), allowance.get("options"), allowance.get("allow_on_submit"),
       allowance.get("non_negative"), allowance.get("insert_after"), allowance.get("label"))
      == (R.ALLOWANCE, "Currency", "Company:company:default_currency", 1, 1, "custom_transport_allowance", "UGX Allowance"),
      allowance)
check("shown on a USD assignment only", allowance.get("depends_on") == 'eval:doc.currency && doc.currency != "UGX"')
anchors = [(row["dt"], row.get("insert_after")) for row in fields.values()]
check("nothing else sits under Transport Allowance",
      anchors.count(("Salary Structure Assignment", "custom_transport_allowance")) == 1)
check("it ships in the app's fixtures", '"Salary Structure Assignment-custom_ugx_allowance",' in read("hrms_addon", "hooks.py"))
patches = read("hrms_addon", "patches.txt")
check("the patch runs after the doctypes are migrated",
      "hrms_addon.patches.v1_0.usd_gross_up" in patches.split("[post_model_sync]")[1])
print("the wiring: the field, its fixture, the patch")

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL USD GROSS-UP CHECKS PASSED")
