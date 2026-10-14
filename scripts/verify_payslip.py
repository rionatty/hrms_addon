"""Checks Luuka's pay slip and the payroll period, without a bench.

    python scripts/verify_payslip.py

  1  the lines of the slip: money paid or taken, never the payroll's
     working (statistical components, the employer's NSSF share), never a
     line of nought
  2  the month a slip is for, what absence took off, leave and absent days
  3  the payroll period: the 26th to the 25th, the same cycle as the
     attendance register and the advances; a monthly payroll for any other
     dates is refused, with the dates to use
  4  the Pay Slip is a standard Jinja print of this app, the one a Salary
     Slip opens with, and reads only what payslip.pay_slip hands it
  5  it prints Luuka's August slip for LPL1834 as their own payroll laid it
     out, with Local Service Tax on it and the working left off
  6  wiring: the jinja method and the two validate hooks

Read by jinja_subset.py as Frappe's Jinja reads it, with nothing left
undefined.
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)
        print("FAIL", label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name, folder=APP):
    spec = importlib.util.spec_from_file_location(name, os.path.join(folder, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("payslip_rules")
A = load("attendance_rules")
V = load("advance_rules")
J = load("jinja_subset", os.path.join(REPO, "scripts"))

# ── 1. the lines ────────────────────────────────────────────────────────
EARNINGS = [
    {"salary_component": "Basic", "amount": 736058, "default_amount": 736058, "depends_on_payment_days": 1},
    {"salary_component": "House Rent Allowance", "amount": 72342, "default_amount": 72342,
     "depends_on_payment_days": 1},
    {"salary_component": "Transport Allowance", "amount": 70000, "default_amount": 70000,
     "depends_on_payment_days": 1},
    # the old structure's working, listed among the earnings
    {"salary_component": "Taxable Salary", "amount": 736058, "statistical_component": 1},
]
DEDUCTIONS = [
    {"salary_component": "Taxable Pay", "amount": 878400, "statistical_component": 1},
    {"salary_component": "Cash Gross Pay", "amount": 878400, "statistical_component": 1},
    {"salary_component": "NSSF Employee", "amount": 43920},
    {"salary_component": "PAYE", "amount": 145770},
    {"salary_component": "Local Service Tax", "amount": 20000},
    {"salary_component": "Advance Recovery", "amount": 351360, "additional_salary": "HR-ADS-26-09-00001"},
    {"salary_component": "NSSF Employer 10%", "amount": 87840, "do_not_include_in_total": 1},
    {"salary_component": "Penalty Recovery", "amount": 0},
]
paid, taken = R.lines(EARNINGS), R.lines(DEDUCTIONS)
check([line["component"] for line in paid] == ["Basic", "House Rent Allowance", "Transport Allowance"],
      "a statistical earning (Taxable Salary) is not a payment: %s" % [line["component"] for line in paid])
check([line["component"] for line in taken] == ["NSSF Employee", "PAYE", "Local Service Tax", "Advance Recovery"],
      "deductions: the working, the employer's share and a line of nought are left off: %s"
      % [line["component"] for line in taken])
check([line["name"] for line in paid] == ["BASIC", "HOUSE RENT ALLOWANCE", "TRANSPORT ALLOWANCE"],
      "a line nobody has named reads as its component, in capitals: %s" % [line["name"] for line in paid])
# how a site's components read on Luuka's slip, once the seed has named and placed them
SITE = ("Basic", "House Rent Allowance", "Transport Allowance", "Local Service Tax", "Payee", "PAYE", "NSSF Employee",
        "Advance Recovery", "Penalty Recovery")
SHOWN = {name: R.seed_for(name) for name in SITE if R.seed_for(name)}
check(SHOWN == {"House Rent Allowance": {"name": "HRA"}, "Local Service Tax": {"order": 3},
                "Payee": {"name": "PAYE", "order": 2}, "PAYE": {"order": 2},
                "NSSF Employee": {"name": "NSSF", "order": 1},
                "Advance Recovery": {"name": "Advance Salary", "order": 4}},
      "the seed names HRA, NSSF, PAYE and Advance Salary, and places the deductions as Luuka's slip does: %s" % SHOWN)
check(R.seed_for("house rent allowance ") == {"name": "HRA"} and R.seed_for("Basic") == {} and R.seed_for(None) == {},
      "whatever the case; a component their slip names the same is left alone")
check(R.seed_for("NSSF Employee", {"name": "Social Security", "order": 0}) == {"order": 1}
      and R.seed_for("NSSF Employee", {"name": "", "order": 7}) == {"name": "NSSF"}
      and R.seed_for("NSSF Employee", {"name": "NSSF", "order": 1}) == {},
      "what somebody has typed is theirs: only a blank is filled")
check([line["name"] for line in R.lines(EARNINGS, None, SHOWN)] == ["BASIC", "HRA", "TRANSPORT ALLOWANCE"],
      "the payments read as theirs: %s" % [line["name"] for line in R.lines(EARNINGS, None, SHOWN)])
# on the site the structure works out the Local Service Tax before PAYE; the slip prints it after
site_order = [DEDUCTIONS[index] for index in (0, 1, 4, 3, 2, 5, 6, 7)]
check([line["name"] for line in R.lines(site_order, None, SHOWN)] == ["NSSF", "PAYE", "LOCAL SERVICE TAX", "Advance Salary"],
      "the deductions read and are placed as theirs, whatever order the structure has them in: %s"
      % [line["name"] for line in R.lines(site_order, None, SHOWN)])
mixed = R.lines([{"salary_component": "Loan Repayment", "amount": 5}, {"salary_component": "PAYE", "amount": 9},
                 {"salary_component": "Penalty Recovery", "amount": 7}, {"salary_component": "NSSF Employee", "amount": 3}],
                None, SHOWN)
check([line["name"] for line in mixed] == ["NSSF", "PAYE", "LOAN REPAYMENT", "PENALTY RECOVERY"],
      "a line with a place comes first; the rest follow in the slip's own order: %s" % [line["name"] for line in mixed])
check(R.slip_name("Basic", "  ") == "BASIC" and R.slip_name("Advance Recovery", " Advance Salary ") == "Advance Salary",
      "a name typed is printed as typed; a blank one is no name")
check(R.total(paid) == 878400 and R.total(taken) == 561050, "the lines shown add up to the gross and the total")
check(R.lines([{"salary_component": "Local Service Tax", "amount": 0}]) == [],
      "Local Service Tax outside July to October is not printed")
check(R.lines([{"salary_component": "Local Service Tax", "amount": 20000}])[0]["amount"] == 20000,
      "Local Service Tax in its months is printed")
overtime = R.lines([{"salary_component": "Overtime", "amount": 54000, "additional_salary": "ADS-1"},
                    {"salary_component": "Basic", "amount": 500000}], {"ADS-1": 12.5})
check(overtime[0]["hours"] == 12.5 and overtime[1]["hours"] is None, "overtime carries its hours, other lines none")
check(R.lines(None) == [] and R.lines([{"salary_component": "X", "amount": "abc"}]) == [], "nothing, or no figure")

# ── 2. what the slip says besides ───────────────────────────────────────
check(R.slip_for("2026-09-25") == "SEPTEMBER 2026" and R.slip_for("2026-09-24") == "SEPTEMBER 2026",
      "a slip is for the month its period closes in")
check(R.slip_for(datetime.date(2027, 1, 25)) == "JANUARY 2027" and R.slip_for(None) == "", "January, and no date")
check(R.absent_amount(EARNINGS) == 0, "full payment days: nothing lost to absence")
short = [{"salary_component": "Basic", "amount": 664827, "default_amount": 736058, "depends_on_payment_days": 1},
         {"salary_component": "Airtime", "amount": 30000, "default_amount": 30000, "depends_on_payment_days": 0},
         {"salary_component": "Overtime", "amount": 10000, "default_amount": 0, "depends_on_payment_days": 1,
          "additional_salary": "ADS-2"},
         {"salary_component": "Taxable Salary", "amount": 600000, "default_amount": 736058,
          "depends_on_payment_days": 1, "statistical_component": 1}]
check(R.absent_amount(short) == 71231, "what three days not paid took off Basic: %s" % R.absent_amount(short))
fixed = [{"salary_component": "Commission", "amount": 10000, "default_amount": 50000, "depends_on_payment_days": 0}]
check(R.absent_amount(fixed) == 0, "an earning that does not follow the payment days lost nothing to absence")
days = [{"status": "Present"}, {"status": "On Leave", "leave_type": "Annual Leave"},
        {"status": "Half Day", "leave_type": "Annual Leave"}, {"status": "Half Day", "leave_type": None},
        {"status": "Absent"}, {"status": "Absent"}, {"status": "Work From Home"}]
check(R.day_counts(days) == (1.5, 2.5), "leave taken and days absent, halves counted: %s" % (R.day_counts(days),))
check(R.day_counts([]) == (0.0, 0.0) and R.day_counts(None) == (0.0, 0.0), "no attendance, no days")

# ── 3. the payroll period ───────────────────────────────────────────────
check((R.CYCLE_START_DAY, R.CYCLE_END_DAY) == (A.CYCLE_START_DAY, A.CYCLE_END_DAY) == (V.CYCLE_START_DAY, V.CYCLE_END_DAY),
      "one cycle for the slip, the attendance register and the advances")
day, same = datetime.date(2026, 1, 1), True
while day <= datetime.date(2027, 3, 1):
    same = same and R.period_of(day) == V.payroll_period(day) == A.cycle_window(*A.cycle_of(day))
    day += datetime.timedelta(days=1)
check(same, "the slip's period is the advances' payroll period and the register's cycle, every day of a year")
check(R.period_of("2026-09-15") == (datetime.date(2026, 8, 26), datetime.date(2026, 9, 25)), "September 2026")
check(R.period_of("2026-12-26") == (datetime.date(2026, 12, 26), datetime.date(2027, 1, 25)), "over the new year")
check(R.period_errors("Monthly", "2026-08-26", "2026-09-25") == [], "the 26th to the 25th runs")
wrong = R.period_errors("Monthly", "2026-08-25", "2026-09-24")
check(len(wrong) == 1 and "26-08-2026 to 25-09-2026" in wrong[0] and "not 25-08-2026 to 24-09-2026" in wrong[0]
      and "September 2026" in wrong[0], "the 25th to the 24th is refused, with the dates to use: %s" % wrong)
calendar_month = R.period_errors("Monthly", "2026-09-01", "2026-09-30")
check(len(calendar_month) == 1 and "26-08-2026 to 25-09-2026" in calendar_month[0],
      "the calendar month is refused for the cycle most of it falls in: %s" % calendar_month)
check(R.period_errors("Monthly", "2026-08-26", "2026-09-24") != [] and R.period_errors("Monthly", "2026-08-25", "2026-09-25") != [],
      "the right first day with the wrong last day is refused, and the other way round")
check(R.period_errors(None, "2026-08-25", "2026-09-24") != [], "no frequency is monthly")
check(R.period_errors("Weekly", "2026-09-01", "2026-09-07") == [] and R.period_errors("Daily", "2026-09-01", "2026-09-01") == [],
      "other frequencies are not this cycle")
check(R.period_errors("Monthly", None, "2026-09-25") == [] and R.period_errors("Monthly", "2026-08-26", None) == [],
      "dates not filled in yet are not judged")
# what the rule is for: a salary advance processed in the month is recovered on the period's closing day
s = V.settings_from({})
recovered_on = V.payroll_period(V.processing_date(2026, 9, s))[1]
check(recovered_on == datetime.date(2026, 9, 25) and R.period_of("2026-09-15")[0] <= recovered_on <= R.period_of("2026-09-15")[1],
      "September's advance is recovered on the 25th, inside September's period")
check(not (datetime.date(2026, 8, 25) <= recovered_on <= datetime.date(2026, 9, 24)),
      "and outside a payroll run for the 25th to the 24th, which is why that run is refused")

# ── 4. the print format ─────────────────────────────────────────────────
form = json.loads(read("hrms_addon", "hrms_addon", "print_format", "pay_slip", "pay_slip.json"))
html = form["html"]
check((form["name"], form["doc_type"], form["standard"], form["print_format_type"], form["custom_format"],
       form["module"]) == ("Pay Slip", "Salary Slip", "Yes", "Jinja", 1, "HRMS Addon"),
      "Pay Slip is a standard Jinja print of this app, on Salary Slip")
check(os.path.exists(os.path.join(APP, "print_format", "pay_slip", "__init__.py")), "its folder is a package")
setters = json.loads(read("hrms_addon", "fixtures", "property_setter.json"))
ours = [row for row in setters if row.get("name") == "Salary Slip-main-default_print_format"]
check(len(ours) == 1 and ours[0]["value"] == "Pay Slip" and ours[0]["doc_type"] == "Salary Slip"
      and ours[0]["property"] == "default_print_format", "a Salary Slip opens with the Pay Slip")
hooks_source = read("hrms_addon", "hooks.py")
check('"Salary Slip-main-default_print_format"' in hooks_source, "the hooks fixtures list that setter")
glue_source = read("hrms_addon", "hrms_addon", "payslip.py")
handed = set()
for node in ast.walk(ast.parse(glue_source)):
    if isinstance(node, ast.FunctionDef) and node.name == "pay_slip":
        for inner in ast.walk(node):
            if isinstance(inner, ast.Dict):
                handed |= {key.value for key in inner.keys if isinstance(key, ast.Constant)}
read_keys = set(re.findall(r"\bp\.(\w+)", html))
check(read_keys and read_keys <= handed, "the print reads only what pay_slip hands it: %s" % sorted(read_keys - handed))
check(handed <= read_keys, "and prints all of it: %s" % sorted(handed - read_keys))
check(not handed & set(dir(dict)), "no key that a dict's own method would hide: %s" % sorted(handed & set(dir(dict))))
for said in ("NAME", "DEPT", "PAYROLL NO.", "PAY SLIP FOR", "DESIGNATION", "CATEGORY", "SECTION",
             '<span class="spaced">PAYMENTS</span>', "AMOUNT", "HOURS", "GROSS PAY", "DEDUCTIONS", "TOTAL",
             '<span class="spaced">NETPAY</span>', "NET PAY R/o", "PAYMENT BY :",
             "Paid Days", "Working Days", "Holidays", "Absent Amount", "Leave Taken", "Absent Days"):
    check(said in html, "the slip says %s, as Luuka's does" % said)
# Laid out to Luuka's own slip, measured from their PDF: a 270pt by 600pt box,
# Arial 8pt on a 10pt line, the deductions in a serif, rules of 5pt dashes.
# And with no table: Frappe's print styles pad every cell (6px in
# standard.css, 10px in the Redesign style) and grey every heading with
# !important, whatever the format says, which is how the first Pay Slip came
# out three times as tall as theirs on the site.
check(not re.search(r"<(table|tr|td|th)\b", html), "no table, so no print style can pad or grey its cells")
check(not re.search(r"<(p|label|h\d)\b", html), "nor a paragraph, a label or a heading, which they space too")
check(html.count("<svg ") == 6 and html.count('viewBox="0 0 235 1"') == 3 and html.count('viewBox="0 0 188 1"') == 1
      and html.count('viewBox="0 0 195 1"') == 2,
      "six rules, as theirs: three across the slip, one under the gross, two round the total")
style = html.split("<style>")[1].split("</style>")[0]
selectors = [rule.split("{")[0].strip() for rule in re.sub(r"/\*.*?\*/", "", style, flags=re.S).split("}")
             if "{" in rule and not rule.strip().startswith("@supports")]
check(selectors and all(part.strip().startswith(".print-format .lpl-slip") for selector in selectors
                        for part in selector.split(",")),
      "every rule is written under .print-format .lpl-slip, so it outranks the site's own: %s"
      % [selector for selector in selectors if not selector.startswith(".print-format .lpl-slip")])
for needle, why in (
    ("width: 270pt; min-height: 600pt; border: 1pt solid #000;", "the box is theirs, 270pt by 600pt, framed"),
    ("font-family: Arial, Helvetica, sans-serif !important; font-size: 8pt !important; line-height: 10pt !important;",
     "Arial 8pt on a 10pt line, whatever the print style sets on a div or a span"),
    ('font-family: "DejaVu Serif"', "the deductions in their serif"),
    ("line-height: 11pt !important;", "on an 11pt line"),
    ('stroke="#000" stroke-width="1" stroke-dasharray="5 3"',
     "rules of 5pt dashes 3pt apart, drawn as lines so a PDF keeps them sharp"),
    (".print-format .lpl-slip .n { float: left; width: 93pt; text-align: right;",
     "the amounts end 209pt in, as theirs do"),
    ('"{:,.4f}".format', "payments, the gross and the net to four places, as their slip prints them"),
    ('"{:,.2f}".format', "the deductions to two"),
):
    check(needle in html, "the print: %s (%r not found)" % (why, needle))
check("doc.earnings" not in html and "doc.deductions" not in html,
      "the lines come from pay_slip, never straight off the slip (the working would print)")
for typed in re.findall(r"\{\{\s*(p\.(?:employee_name|department|payroll_no|designation|category|section|payment_by)"
                        r"|line\.name)\s*\}\}", html):
    check(False, "%s is printed without v(), unescaped" % typed)

# ── 5. Luuka's August slip for LPL1834 ──────────────────────────────────
def figures(slip, employee, attendance=(), holidays=0, hours=None, section=None, shown=None, currency=None):
    """What payslip.pay_slip hands the print, from the same rules."""
    leave, absent = R.day_counts(attendance)
    return {"employee_name": slip["employee_name"], "department": slip["department"], "payroll_no": slip["employee"],
            "slip_for": R.slip_for(slip["end_date"]), "designation": slip["designation"],
            "category": employee.get("custom_pay_category") or employee.get("employment_type"),
            "section": section, "payments": R.lines(slip["earnings"], hours, shown),
            "gross": slip["gross_pay"], "deductions": R.lines(slip["deductions"], None, shown),
            "total_deductions": slip["total_deduction"], "net": slip["net_pay"],
            "rounded": slip.get("rounded_total") or round(slip["net_pay"]),
            "payment_by": " ".join(part for part in (slip.get("mode_of_payment"), slip.get("bank_name"),
                                                     slip.get("bank_account_no")) if part) or None,
            "paid_days": slip["payment_days"], "working_days": slip["total_working_days"], "holidays": holidays,
            "absent_amount": R.absent_amount(slip["earnings"]), "leave_taken": leave,
            "absent_days": slip.get("absent_days") or absent, "currency": currency}


AUGUST = {"employee": "LPL1834", "employee_name": "SARAH AMUGE", "department": "PP DEPARTMENT",
          "designation": "ASSISTANT SUPERVISOR", "branch": "LPL Kawempe", "start_date": "2026-07-26",
          "end_date": "2026-08-25", "earnings": EARNINGS, "deductions": DEDUCTIONS, "gross_pay": 878400,
          "total_deduction": 561050, "net_pay": 317350, "rounded_total": 317350, "payment_days": 31,
          "total_working_days": 31, "mode_of_payment": "Bank", "bank_name": "Stanbic", "bank_account_no": "9030001"}
check(set(figures(AUGUST, {})) == handed, "this check hands the print what pay_slip does")
db = type("db", (), {"get_single_value": staticmethod(lambda kind, field: "/files/luuka.png")})
frappe = type("frappe", (), {"db": db})
render = J.compile_template(html)


def page_of(slip, employee, **more):
    values = figures(slip, employee, **more)
    return render({"doc": J.wrap(slip), "frappe": frappe, "pay_slip": lambda doc: J.wrap(values)})


def text_of(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S))).strip()


page = page_of(AUGUST, {"custom_pay_category": "Monthly"}, section="Human Resource", shown=SHOWN)
text = text_of(page)
check(not re.findall(r"\{\{ [\w.]+ \}\}", page), "nothing left undefined: %s" % re.findall(r"\{\{ [\w.]+ \}\}", page))
for said in ("NAME : SARAH AMUGE", "DEPT : PP DEPARTMENT", "PAYROLL NO. : LPL1834", "PAY SLIP FOR : AUGUST 2026",
             "DESIGNATION : ASSISTANT SUPERVISOR", "CATEGORY : Monthly", "SECTION : Human Resource",
             "PAYMENTS AMOUNT HOURS BASIC 736,058.0000 HRA 72,342.0000 "
             "TRANSPORT ALLOWANCE 70,000.0000 GROSS PAY 878,400.0000",
             "DEDUCTIONS AMOUNT HOURS NSSF 43,920.00 PAYE 145,770.00 LOCAL SERVICE TAX 20,000.00 "
             "Advance Salary 351,360.00 TOTAL 561,050.00",
             "NETPAY 317,350.0000 NET PAY R/o 317,350.0000", "PAYMENT BY : Bank Stanbic 9030001",
             "= Paid Days 31 = Working Days 31 = Holidays 0 = Absent Amount 0.0000 = Leave Taken 0.0000 "
             "= Absent Days 0.0000"):
    check(said in text, "the August slip reads: %s" % said)
check("USD" not in text and text.count("AMOUNT HOURS") == 2,
      "a slip in shillings names no currency, as Luuka's never has")
dollars = text_of(page_of(AUGUST, {"custom_pay_category": "Monthly"}, section="Human Resource", shown=SHOWN,
                          currency="USD"))
check("PAYMENTS AMOUNT USD HOURS BASIC" in dollars and "DEDUCTIONS AMOUNT USD HOURS NSSF" in dollars
      and dollars.count("USD") == 2,
      "a slip in another currency says it over both columns of figures, and nowhere else")
glue = io.open(os.path.join(REPO, "hrms_addon", "hrms_addon", "payslip.py"), encoding="utf-8").read()
said = glue.split("def _currency(")[1].split("\ndef ")[0]
check('"currency": _currency(doc),' in glue
      and "return currency if currency_payroll_rules.foreign(currency, home) else None" in said
      and "currency_payroll.company_currency(doc.get(\"company\"))" in said,
      "the slip's currency is named only where it is not the company's own, by the USD payroll's own rule")
for hidden in ("Taxable", "Cash Gross Pay", "NSSF Employer", "Penalty Recovery"):
    check(hidden not in text, "%s is not on the slip" % hidden)
check('<img src="/files/luuka.png">' in page, "the company's logo is on it")

OCTOBER = dict(AUGUST, employee_name="John <Okello>", start_date="2026-09-26", end_date="2026-10-25",
               earnings=short + [{"salary_component": "Overtime", "amount": 54000, "additional_salary": "ADS-1"}],
               deductions=[{"salary_component": "PAYE", "amount": 0}, {"salary_component": "NSSF Employee", "amount": 34941.35}],
               gross_pay=758827, total_deduction=34941.35, net_pay=723885.65, rounded_total=0, payment_days=28,
               mode_of_payment=None, bank_name=None, bank_account_no=None, absent_days=0)
text = text_of(page_of(OCTOBER, {"employment_type": "Permanent"}, attendance=days, holidays=1, hours={"ADS-1": 12.5}))
for said in ("NAME : John &lt;Okello&gt;", "PAY SLIP FOR : OCTOBER 2026", "CATEGORY : Permanent SECTION : PAYMENTS",
             "OVERTIME 54,000.0000 12.5", "NSSF EMPLOYEE 34,941.35 TOTAL 34,941.35",
             "NETPAY 723,885.6500 NET PAY R/o 723,886.0000", "PAYMENT BY : = Paid Days 28",
             "= Holidays 1 = Absent Amount 71,231.0000 = Leave Taken 1.5000 = Absent Days 2.5000"):
    check(said in text, "another slip reads: %s" % said)
check("PAYE" not in text, "a deduction of nought is not printed")

# ── 6. wiring ───────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(hooks_source).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
check("hrms_addon.hrms_addon.payslip.pay_slip" in hooks["jinja"]["methods"], "pay_slip is a jinja method")
check(re.search(r"^def pay_slip\(doc\):", glue_source, re.M) and 'doc.check_permission("read")' in glue_source,
      "and it reads a slip only for someone who may read it")
for doctype in ("Salary Slip", "Payroll Entry"):
    check(hooks["doc_events"].get(doctype, {}).get("validate") == "hrms_addon.hrms_addon.payslip.period_validate",
          "%s validate checks the payroll period" % doctype)
check(re.search(r"^def period_validate\(doc, method=None\):", glue_source, re.M), "period_validate(doc, method=None)")
check(hooks["doc_events"]["Salary Slip"].get("on_submit") == "hrms_addon.hrms_addon.recoveries.slip_on_submit",
      "the slip still marks its recoveries on submit")
check("salary_slip_based_on_timesheet" in glue_source, "a timesheet slip keeps its own dates")
custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
named, placed = custom.get("Salary Component-custom_slip_name") or {}, custom.get("Salary Component-custom_slip_order") or {}
check((named.get("fieldtype"), named.get("insert_after"), named.get("label")) == ("Data", "description", "Name on Pay Slip")
      and (placed.get("fieldtype"), placed.get("insert_after"), placed.get("label"))
      == ("Int", "custom_slip_name", "Order on Pay Slip"),
      "a Salary Component says what it is called on the slip, and where it stands")
for name in ("Salary Component-custom_slip_name", "Salary Component-custom_slip_order"):
    check('"%s"' % name in hooks_source, "the hooks fixtures list %s" % name)
for needle, why in (
    ("shown = _shown({row.get(\"salary_component\") for row in earnings + deductions if row.get(\"salary_component\")})",
     "the slip's components are asked how they read"),
    ("rules.lines(earnings, _overtime_hours(earnings), shown)", "the payments are named and placed by it"),
    ("rules.lines(deductions, None, shown)", "and the deductions"),
    ("if not components or not all(meta.has_field(field) for field in SHOWN):\n        return {}",
     "a site without the two fields prints as before"),
    ("values = rules.seed_for(row.name, {\"name\": row.custom_slip_name, \"order\": row.custom_slip_order})",
     "the seed fills only what is blank"),
):
    check(needle in glue_source, "payslip.py: %s (%r not found)" % (why, needle))
patch = read("hrms_addon", "patches", "v1_0", "pay_slip_names.py")
check("hrms_addon.patches.v1_0.pay_slip_names" in read("hrms_addon", "patches.txt")
      and patch.index('sync_fixtures("hrms_addon")') < patch.index("payslip.seed_slip_names()"),
      "a listed patch seeds Luuka's names, after the fields are there")

print()
print("FAILED: %d" % len(fail) if fail else "ALL PAY SLIP CHECKS PASSED")
sys.exit(1 if fail else 0)
