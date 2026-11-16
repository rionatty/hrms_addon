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
import types

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
check(R.payroll_rate(4061.72, None) == (4061.72, R.RECORD) and R.payroll_rate(3650, 3720) == (3720, R.MONTHS)
      and R.payroll_rate(3720, 3720) == (3720, None) and R.payroll_rate(0, 3720) == (3720, R.MONTHS)
      and R.payroll_rate(0, None) == (None, R.REFUSE) and R.payroll_rate(None, None) == (None, R.REFUSE),
      "a payroll runs at its month's rate, told so when it showed another; a month with none takes the payroll's "
      "own, saved as the month's; with a rate on neither it is refused")
check(R.recorded_message("USD", "UGX", 4061.72, D(2026, 9, 25))
      == "1 USD = 4,061.72 UGX saved for September 2026 in Currency Exchange."
      and R.month_message("USD", "UGX", 3700, D(2026, 9, 25))
      == "Run at the rate set for September 2026 in Currency Exchange: 1 USD = 3,700 UGX. Change it there if it is wrong."
      and R.payroll_rate_message("USD", "UGX", D(2027, 1, 25)) == "Enter the exchange rate for January 2027: 1 USD in UGX.",
      "and says which, in plain figures")
check(R.show_rate(4061.72) == "4,061.72" and R.show_rate(3700) == "3,700" and R.show_rate(1 / 3700.0) == "0.00027",
      "a rate shown as it is read")
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
check('if not rules.foreign(doc.get("currency"), home):\n        return' in entry
      and 'day = getdate(doc.get("end_date") or doc.get("posting_date"))' in entry
      and 'rate, step = rules.payroll_rate(doc.get("exchange_rate"), month_rate(doc.get("currency"), home, day))' in entry
      and entry.rstrip().endswith("doc.exchange_rate = rate"),
      "a USD Payroll Entry is run at the rate of the month its period ends in; a shilling one is left as it is")
check("if step == rules.REFUSE:\n        frappe.throw(_(rules.payroll_rate_message(" in entry
      and "if step == rules.RECORD:\n        _save_rate(" in entry and "rules.recorded_message(" in entry
      and "elif step == rules.MONTHS:\n        frappe.msgprint(_(rules.month_message(" in entry,
      "a month with no rate takes the payroll's own, saved in Currency Exchange and said; with none on the payroll "
      "either it is refused")
save = function_of(glue, "_save_rate")
check('"doctype": EXCHANGE, "date": str(day), "from_currency": from_currency,' in save
      and '"exchange_rate": rate, "for_buying": 1,' in save and '"for_selling": 1}).insert(ignore_permissions=True)' in save,
      "saved as a Currency Exchange of its own, dated the day the period ends, for whoever runs the payroll")
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
method = next(node for node in ast.walk(ast.parse(glue)) if isinstance(node, ast.FunctionDef)
              and node.name == "_statistical_earnings")
statistical = "\n".join(glue.splitlines()[method.lineno - 1:method.end_lineno])
check("if foreign:\n            self._statistical_earnings(data, default_data)" in glue
      and 'if not (row.get("statistical_component") or row.get("accrual_component")):' in statistical
      and "amount = self.eval_condition_and_formula(row, data)" in statistical
      and "default_data[row.abbr] = flt(amount)" in statistical
      and 'amount = flt(amount) * flt(self.get("payment_days")) / days if days else 0' in statistical,
      "a USD slip's deductions are given its statistical earnings, the USD pay among them, as its earnings are: "
      "Frappe HR v16 builds each table's data afresh from the slip's rows (Luuka, 10 Nov 2026)")
print("glue: a USD payroll at its month's rate, or its own saved as the month's; its slips at the month's or "
      "refused; a shilling payroll left alone")

# ── 3. The gross the other modules read ─────────────────────────────────
pay = read("hrms_addon", "hrms_addon", "pay.py")
gross = function_of(pay, "monthly_gross")
structure_gross = function_of(pay, "_structure_gross")
check("foreign = _is_foreign(assignment)" in gross
      and "structure -= flt(_structure_amounts(assignment).get(currency_payroll_rules.TAX_COVER))" in structure_gross
      and "month = _in_company_currency(flt(rules.per_month(period, frequency), 2), assignment, on)" in gross,
      "an employee paid in USD has a gross in shillings, without the tax the company pays on top; anybody else's "
      "is as before")
check('own = [row for row in allowances if (row.get("currency") or home) != home]' in gross
      and "return flt(month + rules.per_month(rules.gross_per_period(0, shillings), frequency), 2)" in gross,
      "a USD salary's shilling allowances are added as they are, never put through the rate again "
      "(Luuka, 10 Nov 2026)")
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
      and (wired["Salary Slip"].get("before_validate") or [None])[0] == "hrms_addon.hrms_addon.currency_payroll.salary_slip_before_validate",
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
# the house rent and transport the USD Net Pay formulas read come with the
# app, never from a Custom Field import (the user, 6 Nov 2026: "everything
# should be on the app not manual definition of fields"); the labels are the
# ones the assignment import files head their columns with
for name, label, after in (
        ("Salary Structure Assignment-custom_house_rent_allowance", "House Rent Allowance", "variable"),
        ("Salary Structure Assignment-custom_transport_allowance", "Transport Allowance",
         "custom_house_rent_allowance")):
    row = fields.get(name) or {}
    check((row.get("fieldtype"), row.get("options"), row.get("label"), row.get("insert_after"), row.get("non_negative"))
          == ("Currency", "currency", label, after, 1) and ('"%s",' % name) in hooks,
          "%s: an amount in the assignment's currency, never below 0, under Variable, and in the fixtures" % name)
print("wiring: the hooks, the two rate fields, the two allowances")

# an expatriate's Additional Salary in shillings (Luuka, 16 Nov 2026: "Epertiates are currency in uSD yet their
# advance are un UGX on basic salary")
check(R.additional_currencies("USD", "UGX") == ["USD", "UGX"] and R.additional_currencies("UGX", "UGX") == ["UGX"]
      and R.additional_currencies(None, "UGX") == ["UGX"],
      "an Additional Salary in the employee's pay currency or the company's: USD or UGX for an expatriate, UGX else")
check(R.additional_amount(616000, "UGX", "USD", "UGX", 3850) == 160.0
      and R.additional_amount(160, "USD", "USD", "UGX", 3850) == 160,
      "616,000 shillings come off a USD slip at 3,850 as 160.00 dollars; one in dollars as it stands")
glue = read("hrms_addon", "hrms_addon", "currency_payroll.py")
check_part = glue.split("def additional_validate(", 1)[1].split("\ndef ", 1)[0] if "def additional_validate(" in glue \
    else ""
check('rules.additional_currencies(pay_currency(doc.employee, doc.get("payroll_date")),' in check_part
      and "doc.currency = allowed[0]" in check_part and "elif doc.currency not in allowed:" in check_part
      and "frappe.throw(" in check_part,
      "an Additional Salary's currency is the employee's pay's or the company's: none set means their pay's, any "
      "other refused")
choice = glue.split("def additional_currencies(", 1)[1].split("\ndef ", 1)[0] if "def additional_currencies(" in glue \
    else ""
check('frappe.has_permission("Employee", "read", employee, throw=True)' in choice
      and "@frappe.whitelist()\ndef additional_currencies(employee, company):" in glue,
      "the form asks the server which, for an employee it may read")
paid_in = glue.split("def pay_currency(", 1)[1].split("\ndef ", 1)[0] if "def pay_currency(" in glue else ""
check('filters = {"employee": employee, "docstatus": 1}' in paid_in and 'filters["from_date"] = ["<=", getdate(day)]'
      in paid_in and 'order_by="from_date desc"' in paid_in,
      "the pay currency is the submitted assignment's in force on the payroll date")
hooks_src = read("hrms_addon", "hooks.py")
check('"hrms_addon.hrms_addon.currency_payroll.additional_validate"]' in hooks_src
      and '"Additional Salary-currency-read_only",' in hooks_src,
      "the check runs on every Additional Salary, and the currency field opens with the app's fixtures")
setters = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "property_setter.json"))}
setter = setters.get("Additional Salary-currency-read_only") or {}
check((setter.get("doc_type"), setter.get("field_name"), setter.get("property"), setter.get("value"))
      == ("Additional Salary", "currency", "read_only", "0"),
      "Frappe HR's read-only currency opened")
script = read("hrms_addon", "public", "js", "additional_salary.js")
check('"hrms_addon.hrms_addon.currency_payroll.additional_currencies"' in script
      and 'frm.set_query("currency", () => ({ filters: { name: ["in", allowed] } }));' in script
      and "if (doc.docstatus !== 0 || !doc.employee || !doc.company) return;" in script,
      "the form offers only those two, on a draft")
lifted = [node for node in ast.parse(glue).body if isinstance(node, ast.FunctionDef)
          and node.name in ("pay_currency", "additional_validate")]


class Refused(Exception):
    pass


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


ASSIGNED = {"EXP-1": [("2026-01-01", "UGX"), ("2026-07-01", "USD")], "LOC-1": [("2026-01-01", "UGX")]}


def stand_in_get_all(doctype, filters=None, fields=None, order_by=None, limit_page_length=None, **kwargs):
    rows = [(day, currency) for day, currency in ASSIGNED.get(filters["employee"], [])
            if "from_date" not in filters or day <= str(filters["from_date"][1])]
    rows.sort(reverse=order_by == "from_date desc")
    return [Row(currency=currency) for _day, currency in rows[:limit_page_length or None]]


stand_in = types.SimpleNamespace(get_all=stand_in_get_all,
                                 throw=lambda message, title=None: (_ for _ in ()).throw(Refused(message)))
space = {"frappe": stand_in, "rules": R, "_": lambda text: text, "getdate": lambda day: day,
         "company_currency": lambda company: "UGX"}
exec(compile(ast.Module(body=lifted, type_ignores=[]), "currency_payroll.py(lifted)", "exec"), space)


def saved(employee, currency, payroll_date="2026-11-25"):
    doc = Row(employee=employee, employee_name=employee, company="Luuka", currency=currency, payroll_date=payroll_date)
    try:
        space["additional_validate"](doc)
    except Refused as error:
        return "refused: %s" % error
    return doc.currency


check(len(lifted) == 2 and saved("EXP-1", "UGX") == "UGX" and saved("EXP-1", "USD") == "USD"
      and saved("EXP-1", None) == "USD",
      "an expatriate's Additional Salary kept in shillings or dollars; none set, their pay's")
check(saved("EXP-1", "EUR") == "refused: EXP-1 is paid in USD: record this in USD or UGX.",
      "any other currency refused, saying which")
check(saved("LOC-1", "USD") == "refused: LOC-1 is paid in UGX: record this in UGX." and saved("LOC-1", None) == "UGX",
      "somebody paid in shillings, in shillings only")
check(saved("EXP-1", "USD", payroll_date="2026-03-25") == "refused: EXP-1 is paid in UGX: record this in UGX.",
      "the assignment in force on the payroll date decides: before the dollar one, shillings")
print("an expatriate's Additional Salary: USD or UGX, shillings taken at the payroll's rate")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL CURRENCY PAYROLL CHECKS PASSED")
