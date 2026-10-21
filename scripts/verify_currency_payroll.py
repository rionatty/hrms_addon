"""Checks a payroll in another currency than the company's (Luuka's USD
staff), without a bench.

    python scripts/verify_currency_payroll.py

  1  the rules: the rate a month's payroll is run at, the rate a gross is
     put into shillings with, and what the payroll says without one
  2  the glue: a USD Payroll Entry and its slips take the month's rate or
     are refused, the slip's formulas are given it, a shilling payroll is
     left as it is, and an assignment's own working out has a rate too
  3  the gross the app's other modules read: in shillings, without the tax
     the company pays on top
  4  the wiring: the hooks and the two fields the formulas read

The rules are loaded without Frappe.
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def function_of(source, name):
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


spec = importlib.util.spec_from_file_location("currency_payroll_rules", os.path.join(APP, "currency_payroll_rules.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)  # proves it has no Frappe import
print("loaded currency_payroll_rules.py without Frappe")
D = datetime.date

# ── 1. The rules ────────────────────────────────────────────────────────
ROWS = [
    {"from_currency": "USD", "to_currency": "UGX", "exchange_rate": 3650, "date": "2026-09-01"},
    {"from_currency": "USD", "to_currency": "UGX", "exchange_rate": 3700, "date": "2026-10-01"},
    {"from_currency": "USD", "to_currency": "UGX", "exchange_rate": 3720, "date": "2026-10-15"},
    {"from_currency": "UGX", "to_currency": "USD", "exchange_rate": 0.0002702703, "date": "2026-11-03"},
    {"from_currency": "EUR", "to_currency": "UGX", "exchange_rate": 4100, "date": "2026-10-20"},
    {"from_currency": "USD", "to_currency": "UGX", "exchange_rate": 0, "date": "2026-10-28"},
    # nought entered the other way round would be divided by
    {"from_currency": "UGX", "to_currency": "USD", "exchange_rate": 0, "date": "2026-10-29"},
]
check(R.month_rate(ROWS, "USD", "UGX", D(2026, 10, 25)) == 3720,
      "a month's payroll is run at the latest rate set in that month, not an earlier month's, another currency's, "
      "or a rate of nought either way round")
check(R.month_rate(ROWS, "USD", "UGX", D(2026, 9, 25)) == 3650 and R.month_rate(ROWS, "USD", "UGX", D(2026, 12, 25)) is None,
      "each month by its own rate, and a month with none has none: it is never guessed")
check(abs(R.month_rate(ROWS, "USD", "UGX", D(2026, 11, 25)) - 3700) < 0.01,
      "a rate entered the other way round is taken as its inverse")
same_day = [{"from_currency": "UGX", "to_currency": "USD", "exchange_rate": 1 / 3800.0, "date": "2026-10-10"},
            {"from_currency": "USD", "to_currency": "UGX", "exchange_rate": 3750, "date": "2026-10-10"}]
check(R.month_rate(same_day, "USD", "UGX", D(2026, 10, 25)) == 3750,
      "of two rates on one day, the one entered in the payroll's own direction")
check(R.latest_rate(ROWS, "USD", "UGX", D(2026, 12, 5)) and abs(R.latest_rate(ROWS, "USD", "UGX", D(2026, 12, 5)) - 3700) < 0.01
      and R.latest_rate(ROWS, "USD", "UGX", D(2026, 8, 31)) is None and R.latest_rate(ROWS, "USD", "UGX", D(2026, 10, 3)) == 3720,
      "for a figure that only needs a near rate, the latest up to the end of the month; none before the first")
check(R.rate_message("USD", "UGX", D(2026, 12, 25)) == "Set the USD to UGX rate for December 2026 in Currency Exchange.",
      "a payroll without its month's rate says which rate to set, and where")
check(R.month_bounds(D(2028, 2, 10)) == (D(2028, 2, 1), D(2028, 2, 29)) and R.month_bounds("2026-10-25") == (D(2026, 10, 1), D(2026, 10, 31)),
      "a month runs from its first day to its last, February in a leap year included")
check(R.foreign("USD", "UGX") and not R.foreign("UGX", "UGX") and not R.foreign(None, "UGX") and not R.foreign("USD", None),
      "only a currency that is not the company's own is another")
check(R.in_company_currency(2000, 3720) == 7440000.0 and R.in_company_currency(1234.567, 3700) == 4567897.9,
      "an amount in shillings, at the rate")
check(R.TAX_COVER == "Tax Paid by Company" and R.RATE_FIELD == "custom_exchange_rate",
      "the tax cover earning and the rate field, by the names the import files give them")
print("rules: the month's own rate, never guessed; a near rate only for the app's own figures")

# ── 2. The glue ─────────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "currency_payroll.py")
entry = function_of(glue, "payroll_entry_before_validate")
slip = function_of(glue, "salary_slip_before_validate")
strict = function_of(glue, "_strict_rate")
check('if not rules.foreign(doc.get("currency"), company_currency(doc.get("company"))):\n        return' in entry
      and 'doc.exchange_rate = _strict_rate(doc, doc.get("end_date") or doc.get("posting_date"))' in entry,
      "a USD Payroll Entry is run at the rate of the month its period ends in; a shilling one is left as it is")
check('rate = month_rate(doc.get("currency"), home, day)' in strict and "if not rate:\n        frappe.throw(" in strict
      and "rules.rate_message(" in strict,
      "and without that month's rate it is refused, saying which rate to set")
check('doc.set(rules.RATE_FIELD, 1)\n        return' in slip and 'rate = _strict_rate(doc, doc.get("end_date") or doc.get("posting_date"))' in slip
      and "doc.exchange_rate = rate" in slip and "doc.set(rules.RATE_FIELD, rate)" in slip,
      "each USD slip too, its formulas given the same rate as its accounting; a shilling slip's formulas get 1")
rows_part = function_of(glue, "_rows")
check('for one, other in ((from_currency, to_currency), (to_currency, from_currency)):' in rows_part
      and '"date": ["<=", str(until)]' in rows_part,
      "the rates are read both ways round, up to the end of the month")
assigned = function_of(glue, "assignment_validate")
check('flt(rate_for(doc.get("currency"), home, doc.get("from_date"))) or 1' in assigned and "doc.set(rules.RATE_FIELD, 1)" in assigned,
      "a USD assignment works its own formulas out at the latest rate there is, 1 before there is any")
check("rules.latest_rate(" in function_of(glue, "rate_for") and "rules.month_rate(" in function_of(glue, "month_rate"),
      "a near rate for the app's own figures, the month's own for a payroll")
print("glue: a USD payroll and its slips at the month's rate or refused, a shilling payroll left alone")

# ── 3. The gross the other modules read ─────────────────────────────────
pay = read("hrms_addon", "hrms_addon", "pay.py")
gross = function_of(pay, "monthly_gross")
check("foreign = _is_foreign(assignment)" in gross
      and "structure -= flt(_structure_amounts(assignment).get(currency_payroll_rules.TAX_COVER))" in gross
      and "return _in_company_currency(month, assignment, on) if foreign else month" in gross,
      "an employee paid in USD has a gross in shillings, without the tax the company pays on top; anybody else's "
      "is as before")
converted = function_of(pay, "_in_company_currency")
check("currency_payroll.rate_for(" in converted and "if rate else 0" in converted,
      "put into shillings at the month's rate, else the latest before it; with no rate at all, no gross")
check("_is_foreign(assignment)" in function_of(pay, "assignment_gross")
      and "currency_payroll_rules.TAX_COVER" in function_of(pay, "assignment_gross"),
      "and so is the gross an assignment works out to")
print("gross: in shillings, the tax cover left out")

# ── 4. The wiring ───────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
events = next(node.value for node in ast.parse(hooks).body
              if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "doc_events")
wired = {ast.literal_eval(key): {ast.literal_eval(k): ast.literal_eval(v) for k, v in zip(value.keys, value.values)}
         for key, value in zip(events.keys, events.values)}
check(wired["Payroll Entry"].get("before_validate") == "hrms_addon.hrms_addon.currency_payroll.payroll_entry_before_validate"
      and wired["Salary Slip"].get("before_validate") == "hrms_addon.hrms_addon.currency_payroll.salary_slip_before_validate",
      "the rate is set before the Payroll Entry and the slip are validated, so the slip's formulas are worked out at it")
slip_checks = wired["Salary Slip"].get("validate")
check("hrms_addon.hrms_addon.currency_payroll.assignment_validate" in wired["Salary Structure Assignment"]["validate"]
      and (slip_checks if isinstance(slip_checks, list) else [slip_checks])[0]
      == "hrms_addon.hrms_addon.payslip.period_validate",
      "the assignment's rate on its validate, and the slip's own checks as before")
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
for name, after in (("Salary Slip-custom_exchange_rate", "exchange_rate"),
                    ("Salary Structure Assignment-custom_exchange_rate", "currency")):
    row = fields.get(name) or {}
    check((row.get("fieldtype"), row.get("hidden"), row.get("read_only"), row.get("default"), row.get("insert_after"),
           row.get("precision")) == ("Float", 1, 1, "1", after, "9") and ('"%s",' % name) in hooks,
          "%s: hidden, read only, 1 until it is set, nine places, and in the fixtures" % name)
check(len({(row["dt"], row.get("insert_after")) for row in fields.values()
           if row["dt"] in ("Salary Slip", "Salary Structure Assignment")}) ==
      len([row for row in fields.values() if row["dt"] in ("Salary Slip", "Salary Structure Assignment")]),
      "each of the fields under its own field, so none moves another")
print("wiring: the hooks and the two fields")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL CURRENCY PAYROLL CHECKS PASSED")
