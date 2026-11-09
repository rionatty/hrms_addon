"""Checks the UGX Payroll tab of a USD payroll (usd_sheet.py, usd_sheet_rules.py), without a bench:

    python scripts/verify_usd_sheet.py

Luuka, 10 Nov 2026: "where the UGX values for USD payroll", then "please
proceed" to a tab laid out as their own expatriate payroll sheet.

  1. the columns, in the sheet's order
  2. Luuka's September 2026 sheet comes out of the USD structure's own
     formulas, row by row and in its totals, to the shilling
  3. the Excel file: the company, the title, the columns, the rows, the total
  4. the glue, the form, the fields
"""
import importlib.util
import io
import json
import math
import os
import re
import sys
import datetime

from openpyxl import load_workbook

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(label, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read().replace("\r\n", "\n")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


S = load("usd_sheet_rules")
R = load("currency_payroll_rules")

# ── 1. The columns ────────────────────────────────────────────────────
check("the sheet's columns, in its order",
      [label for _name, label, *_rest in S.COLUMNS] == [
          "S/N", "EMP.No", "NAME", "DEPT", "BASIC USD", "RATE", "NET(SHS)", "ALLOWANCE", "TOTAL NET", "GROSS", "LST",
          "TOTAL GROSS", "PAYE", "NSSF 5%", "NSSF 10%", "NSSF 15%", "ADVANCE", "T.D", "NETPAY"])
check("the department without the company's abbreviation", S.department_label("PE Department - LPT", "LPT")
      == "PE Department" and S.department_label("PE Department", "LPT") == "PE Department"
      and S.department_label(None, "LPT") == "")
check("the title the month the payroll ends in", S.sheet_title("2026-09-25") == "USD PAYROLL FOR THE MONTH OF "
      "SEPTEMBER 2026", S.sheet_title("2026-09-25"))
check("to the shilling, a half up", (S.shilling(2.5), S.shilling(2.49), S.shilling(-2.5)) == (3, 2, -3))

# ── 2. Luuka's September 2026 sheet ───────────────────────────────────
GLOBALS = {"floor": math.floor, "round": round, "getdate": lambda value: datetime.date.fromisoformat(str(value)[:10]),
           "__builtins__": {}}
AMOUNTS = R.gross_up_amounts()
# a label for each person (not their employee number), BASIC USD, ALLOWANCE, ADVANCE, then the sheet's NET(SHS), TOTAL NET, GROSS, LST, TOTAL GROSS, PAYE, NSSF 5%,
# NSSF 10%, NSSF 15%, T.D and NETPAY
SHEET = [
    ("E1", 1300, 400000, 0, 5096000, 5496000, 8283462, 25000, 8308462, 2373288, 415423, 830846, 1246269, 2813712,
     5494750),
    ("E2", 1300, 200000, 0, 5096000, 5296000, 7975769, 25000, 8000769, 2280981, 400038, 800077, 1200115, 2706019,
     5294750),
    ("E3", 1300, 200000, 0, 5096000, 5296000, 7975769, 25000, 8000769, 2280981, 400038, 800077, 1200115, 2706019,
     5294750),
    ("E4", 1400, 200000, 0, 5488000, 5688000, 8578846, 25000, 8603846, 2461904, 430192, 860385, 1290577, 2917096,
     5686750),
    ("E5", 2000, 200000, 0, 7840000, 8040000, 12596818, 25000, 12621818, 3926977, 631091, 1262182, 1893273, 4583068,
     8038750),
    ("E6", 4255, 0, 0, 16679600, 16679600, 28305182, 25000, 28330182, 10210323, 1416509, 2833018, 4249527, 11651832,
     16678350),
    ("E7", 2200, 400000, 0, 8624000, 9024000, 14385909, 25000, 14410909, 4642614, 720545, 1441091, 2161636, 5388159,
     9022750),
    ("E8", 2000, 400000, 0, 7840000, 8240000, 12960455, 25000, 12985455, 4072432, 649273, 1298545, 1947818, 4746705,
     8238750),
    ("E9", 6000, 0, 0, 23520000, 23520000, 40742273, 25000, 40767273, 15185159, 2038364, 4076727, 6115091, 17248523,
     23518750),
    ("E10", 1500, 760000, 360000, 5880000, 6640000, 10051364, 25000, 10076364, 2908795, 503818, 1007636, 1511455,
     3797614, 6278750),
    ("E11", 3000, 0, 3528000, 11760000, 11760000, 19360455, 25000, 19385455, 6632432, 969273, 1938545, 2907818,
     11154705, 8230750),
]
# the sheet's TOTAL row
SHEET_TOTAL = {"basic_usd": 26255, "net": 102919600, "allowance": 2760000, "total_net": 105679600, "gross": 171216301,
               "lst": 275000, "total_gross": 171491301, "paye": 56975886, "nssf_5": 8574565, "nssf_10": 17149130,
               "nssf_15": 25723695, "advance": 3888000, "deductions": 69713451, "net_pay": 101777850}
COLUMNS = ("net", "total_net", "gross", "lst", "total_gross", "paye", "nssf_5", "nssf_10", "nssf_15", "deductions",
           "net_pay")
rows, off = [], []
for number, (employee, basic, allowance, advance, *figures) in enumerate(SHEET, start=1):
    context = {"USDP": basic, "custom_exchange_rate": 3920, R.ALLOWANCES: allowance, "end_date": "2026-09-25",
               "nssf_age_limit": 55, "employee_age": 40, "custom_nssf_voluntary": 0}
    worked = {key: eval(AMOUNTS[key], dict(GLOBALS), dict(context))
              for key in ("gross", "lst", "paye_exact", "employee_exact", "employer_exact")}
    row = S.sheet_row(number, {"employee": employee, "employee_name": employee, "department": "PE Department"},
                      {"usd": basic, "rate": 3920, "allowance": allowance, "gross": worked["gross"], "lst": worked["lst"],
                       "paye": worked["paye_exact"], "employee": worked["employee_exact"],
                       "employer": worked["employer_exact"], "advance": advance})
    rows.append(row)
    got = [row[name] for name in COLUMNS]
    if got != list(figures) or (row["basic_usd"], row["rate"], row["allowance"], row["advance"]) \
            != (basic, 3920, allowance, advance):
        off.append((employee, [(name, row[name], want) for name, want in zip(COLUMNS, figures) if row[name] != want]))
check("every row of Luuka's sheet, every column to the shilling: NET(SHS), TOTAL NET, GROSS, LST, TOTAL GROSS, PAYE, "
      "NSSF 5%, 10% and 15%, T.D and NETPAY", not off, off)
total = S.totals(rows)
total_off = {name: (total[name], want) for name, want in SHEET_TOTAL.items() if total[name] != want}
check("and its TOTAL row to the shilling, each column added up before it is rounded, as the sheet's SUM is",
      not total_off, total_off)
check("the total row leaves the count and the rate empty, and says TOTAL:",
      total["employee_name"] == "TOTAL:" and "idx" not in total and "rate" not in total)
shown = S.shown(rows)
check("the form is sent the rows without their exact amounts, and the total row last, marked",
      len(shown) == 12 and "exact" not in shown[0] and shown[-1].get("is_total") == 1
      and shown[-1]["paye"] == 56975886 and S.shown([]) == [])

# ── 3. The Excel file ─────────────────────────────────────────────────
book = load_workbook(io.BytesIO(S.workbook("Luuka Payroll Testing", S.sheet_title("2026-09-25"), rows)))
sheet = book.active
values = [[cell.value for cell in row] for row in sheet.iter_rows()]
check("the company and the title above, as Luuka's sheet",
      values[0][2] == "LUUKA PAYROLL TESTING" and values[1][2] == "USD PAYROLL FOR THE MONTH OF SEPTEMBER 2026"
      and sheet["C1"].font.b and sheet["C2"].font.b, values[:2])
check("the columns on the fourth row, bold", values[3] == [label for _name, label, *_rest in S.COLUMNS]
      and all(cell.font.b for cell in sheet[4]), values[3])
check("a row a slip, then the total row, bold", len(values) == 4 + len(rows) + 1
      and values[4][:4] == [1, "E1", "E1", "PE Department"] and values[-1][2] == "TOTAL:"
      and values[-1][12] == 56975886 and all(cell.font.b for cell in sheet[len(values)]), values[-1])
check("amounts with thousands, the USD to the cent only when it has cents",
      sheet.cell(row=5, column=7).number_format == "#,##0" and sheet.cell(row=5, column=5).number_format == "#,##0"
      and S.workbook("X", "T", [S.sheet_row(1, {}, {"usd": 1300.5, "rate": 3920})]) is not None)
trap = load_workbook(io.BytesIO(S.workbook("X", "T", [S.sheet_row(1, {"employee_name": "=HYPERLINK(\"x\")"},
                                                                  {"usd": 1, "rate": 1})])))
check("a name that begins with = stays a name", trap.active.cell(row=5, column=3).data_type == "s")

# ── 4. The glue, the form, the fields ─────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "usd_sheet.py")
for name in ("ugx_payroll", "download_ugx_payroll"):
    check("usd_sheet.%s is called from the form" % name,
          re.search(r"@frappe\.whitelist\(\)\ndef %s\(payroll_entry\):" % name, glue) is not None)
for needle, why in (
    ('run.check_permission("read")', "the payroll must be readable"),
    ('frappe.has_permission(SLIP, "read", throw=True)', "and its slips, whose figures these are"),
    ("if not currency_payroll_rules.foreign(run.currency, home):", "a shilling payroll has no such tab"),
    ('filters={"payroll_entry": run.name, "docstatus": ["<", 2]}', "its slips, drafts or submitted, none cancelled"),
    ("data, _default = slip.get_data_for_eval()", "each slip's figures as its own formulas see them"),
    ("_evaluate(AMOUNTS[key], dict(slip.whitelisted_globals), data) for key in WORKED",
     "worked out by the USD structure's own formulas, as Frappe HR works the slip's out"),
    ("from hrms.payroll.utils import _safe_eval as _evaluate", "with the evaluator the slip uses"),
    ('"usd": data.get(currency_payroll_rules.PAY_ABBR)', "the USD pay as the slip's formulas are given it"),
    ('"paye": worked["paye_exact"], "employee": worked["employee_exact"]', "before they are rounded"),
    ('if row.get("additional_salary")', "ADVANCE: what the slip takes back through Additional Salary"),
    ("provide_binary_file(", "the Excel file"),
):
    check("usd_sheet.py: %s" % why, needle in glue, needle)
js = read("hrms_addon", "public", "js", "payroll_entry.js")
check("the payroll form draws the tab from the glue, and downloads it",
      'const HA_PAYROLL_UGX_TAB = "custom_ugx_payroll_tab";' in js and "ha_payroll_ugx(frm);" in js
      and 'HA_PAYROLL_UGX_METHOD = "hrms_addon.hrms_addon.usd_sheet.ugx_payroll"' in js
      and 'HA_PAYROLL_UGX_DOWNLOAD = "hrms_addon.hrms_addon.usd_sheet.download_ugx_payroll"' in js)
check("it loads when its tab is opened, as the Salary Register tab does",
      "tab.df.fieldname !== HA_PAYROLL_UGX_TAB) return;" in js
      and re.search(r"on_tab_change\(frm\) \{\s*ha_payroll_register\(frm\);\s*ha_payroll_ugx\(frm\);\s*\}", js))
check("the total row is the server's, kept last: no sorting, no filters, no total of the table's own",
      "sortable: false," in js and "dropdown: false," in js
      and "showTotalRow" not in js.split("function ha_payroll_ugx_draw(")[1].split("function ")[0])
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
tab, html = fields.get("Payroll Entry-custom_ugx_payroll_tab") or {}, fields.get("Payroll Entry-custom_ugx_payroll") or {}
check("the tab: UGX Payroll, after the Salary Register, on a payroll in another currency only",
      (tab.get("fieldtype"), tab.get("label"), tab.get("insert_after"), tab.get("depends_on"))
      == ("Tab Break", "UGX Payroll", "custom_salary_register", 'eval:doc.currency && doc.currency != "UGX"'), tab)
check("and in it the table", (html.get("fieldtype"), html.get("insert_after")) == ("HTML", "custom_ugx_payroll_tab"),
      html)
hooks = read("hrms_addon", "hooks.py")
check("both ship with the app", '"Payroll Entry-custom_ugx_payroll_tab",' in hooks
      and '"Payroll Entry-custom_ugx_payroll",' in hooks)

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL UGX PAYROLL CHECKS PASSED")
