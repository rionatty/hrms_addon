"""Verify the salary advance against Luuka's own rules, without a bench:

    python scripts/verify_salary_advance.py

The rules are in the minutes of 16 and 20 July 2026 (Human Resource,
Reward and Compensation): §4.9 for the salary advance, §4.4 for the
leave advance beside it. Every one of them is a setting on Advance
Settings, and advance_rules.DEFAULTS is what each is until Luuka changes it.

  1  the defaults are the minutes' own numbers, and the page agrees
  2  the day: the 15th, or the working day before; and the run a request joins
  3  the attendance: absences since the 26th, off-duty days not counted
  4  who qualifies, each rule with its own reason, each one a switch
  5  the amount: 40% of gross, the Per Meter standard rate, 60% for leave
  6  the glue reads the settings and watches the day
  7  the fields, the page, the patch and the way in
"""
import importlib.util
import datetime
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def expect(label, errors, needle=None):
    if needle is None:
        if errors:
            fail.append("%s: expected no reason, got %s" % (label, errors))
    elif not any(needle in error for error in errors):
        fail.append("%s: expected a reason containing %r, got %s" % (label, needle, errors))


V = load("advance_rules")
D = datetime.date
print("loaded advance_rules.py without Frappe")

# ── 1. The minutes' own numbers ───────────────────────────────────────
for key, value, why in (
    ("salary_percent", 40.0, "§4.9: the salary advance is 40% of gross salary"),
    ("per_meter_amount", 110000.0, "§4.9: a standard rate of UGX 110,000 for the Per Meter category"),
    ("salary_processing_day", 15, "§4.9: processed on the 15th of each month"),
    ("salary_move_before", 1, "§4.9: a weekend or public holiday moves it before that date"),
    ("salary_max_absent_days", 3, "§4.9: not absent for more than three days"),
    ("salary_off_duty_not_absent", 1, "§4.9: the Off-Duty Forms are checked against the absences"),
    ("salary_not_on_leave", 1, "§4.9: employees on leave are removed"),
    ("salary_no_bank_loan", 1, "§4.9: have no bank loan"),
    ("salary_regular_only", 1, "§4.9: applicable only to regular employees"),
    ("salary_min_months", 0, "the minutes set no service rule for the salary advance"),
    ("salary_instalments", 1, "it is recovered from the same month's pay"),
    ("leave_percent", 60.0, "§4.4: the Accounts Manager calculates 60% of gross salary"),
    ("leave_per_meter_months", 2, "§4.4: the average of the previous two months' gross"),
    ("leave_more_than_days", 19, "§4.4: those taking more than 19 accrued days of leave"),
    ("leave_no_loans", 1, "§4.4: no existing bank or company loans"),
    ("special_percent", 50.0, "LPL/HR/21: no more than half a month's gross"),
    ("special_max_instalments", 3, "LPL/HR/21: recovered in at most three months"),
):
    if V.DEFAULTS.get(key) != value:
        fail.append("%s should default to %r — %s (it is %r)" % (key, value, why, V.DEFAULTS.get(key)))

spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", "advance_settings", "advance_settings.json"))
page = {f["fieldname"]: f for f in spec["fields"]}
if not spec.get("issingle"):
    fail.append("Advance Settings is one page for the company, a Single")
for key, value in V.DEFAULTS.items():
    if key not in page:
        fail.append("Advance Settings has no field for %s, so it cannot be changed without a developer" % key)
        continue
    stated = page[key].get("default")
    if stated is None or float(stated) != float(value):
        fail.append("Advance Settings shows %s as %r but the rules default it to %r — the page and "
                    "the rules would disagree until somebody saved it" % (key, stated, value))
extra = sorted(fn for fn, f in page.items()
               if f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")
               and fn not in V.DEFAULTS and fn != "not_regular_types")
if extra:
    fail.append("Advance Settings has fields the rules never read: %s" % extra)
if page.get("not_regular_types", {}).get("fieldtype") != "Table MultiSelect":
    fail.append("who is not regular is a list of Employment Types, picked on the page")
print("defaults: the minutes' own numbers, and the page shows the same ones")

# a stored nought is a nought
merged = V.settings_from({"salary_max_absent_days": "0", "salary_percent": "35", "salary_move_before": "0"})
if merged["salary_max_absent_days"] != 0:
    fail.append("a saved nought must stay nought: 'no absence at all' is a real policy")
if merged["salary_percent"] != 35.0 or merged["salary_move_before"] != 0:
    fail.append("what was saved stands over the default")
if V.settings_from({})["salary_percent"] != 40.0:
    fail.append("and anything never saved takes the minutes' number")
expect("a percentage of nought", V.settings_errors({"salary_percent": 0}), "more than 0")
expect("a processing day that some months do not have", V.settings_errors({"salary_processing_day": 31}),
       "every month")
expect("settings as they come", V.settings_errors({}))

# ── 2. The day ────────────────────────────────────────────────────────
for year, month, closed, expected, why in (
    (2026, 9, (), D(2026, 9, 15), "the 15th of September 2026 is a Tuesday"),
    (2026, 8, (), D(2026, 8, 14), "a Saturday 15th moves to the Friday"),
    (2026, 11, (), D(2026, 11, 13), "a Sunday 15th moves past the Saturday to the Friday"),
    (2026, 10, ("2026-10-15",), D(2026, 10, 14), "a public holiday on the 15th moves it back a day"),
    (2026, 10, ("2026-10-15", "2026-10-14"), D(2026, 10, 13), "and keeps going until a working day"),
):
    got = V.processing_date(year, month, None, closed)
    if got != expected:
        fail.append("processing_date(%d-%02d) is %s, expected %s: %s" % (year, month, got, expected, why))
if V.processing_date(2026, 8, {"salary_move_before": 0}) != D(2026, 8, 15):
    fail.append("with the move switched off, the day is the day")
if V.processing_date(2026, 9, {"salary_processing_day": 10}) != D(2026, 9, 10):
    fail.append("the day is a setting")

if V.request_deadline(D(2026, 9, 15)) != D(2026, 9, 12):
    fail.append("requests close three days before the run by default")
if V.run_for("2026-09-12") != D(2026, 9, 15):
    fail.append("a request on the closing day is in time")
if V.run_for("2026-09-13") != D(2026, 10, 15):
    fail.append("a late request waits for the next run rather than being turned away")
if V.run_for("2026-12-20") != D(2027, 1, 15):
    fail.append("and December's late ones join January's")
if V.run_for("2026-09-13", {"salary_request_days_before": 0}) != D(2026, 9, 15):
    fail.append("how early requests close is a setting")

if V.payroll_period("2026-09-15") != (D(2026, 8, 26), D(2026, 9, 25)):
    fail.append("the 15th of September is in the period that runs 26 August to 25 September")
if V.payroll_period("2026-09-26") != (D(2026, 9, 26), D(2026, 10, 25)):
    fail.append("from the 26th the days belong to the next period")
if V.payroll_period("2026-01-15")[0] != D(2025, 12, 26):
    fail.append("January's period opens in December")

if V.held_until("2026-09-15", "2026-09-14") is None:
    fail.append("a salary advance does not go to Finance before the day it is processed")
if V.held_until("2026-09-15", "2026-09-15") is not None:
    fail.append("but it does on the day")
if V.held_until("2026-09-15", "2026-09-14", {"salary_hold_until_processing": 0}) is not None:
    fail.append("and holding it is a setting")
print("the day: the 15th or the working day before, the run a request joins, and the hold")

# ── 3. The attendance ─────────────────────────────────────────────────
ABSENT = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]
if V.days_absent(ABSENT, ["2026-09-02", "2026-09-04"]) != 3:
    fail.append("an approved off-duty day recorded as absent is not an absence (§4.9)")
if V.days_absent(ABSENT, ["2026-09-02"], {"salary_off_duty_not_absent": 0}) != 5:
    fail.append("and not counting them is a setting")
if V.days_absent(ABSENT + ["2026-09-01"]) != 5:
    fail.append("a day is counted once however many records say it")
print("attendance: absences since the 26th, approved off-duty days not held against anyone")

# ── 4. Who qualifies ──────────────────────────────────────────────────
OK = {"advance_type": "Salary Advance", "status": "Active", "employment_type": "Permanent",
      "pay_category": "Monthly", "date_of_joining": "2026-08-01", "gross_pay": 1000000, "amount": 400000,
      "outstanding": 0, "instalments": 1, "processing_date": "2026-09-15", "window_start": "2026-08-26",
      "days_absent": 3, "on_leave": None, "bank_loan": False}
S = V.settings_from({"not_regular_types": ["Casual"]})
expect("a regular employee three days absent, asking 40%", V.eligibility_errors(OK, S))
expect("nobody asks how long a salary advance applicant has served",
       V.eligibility_errors(dict(OK, date_of_joining="2026-09-01"), S))
for label, change, needle in (
    ("four days absent", {"days_absent": 4}, "no more than 3"),
    ("a casual", {"employment_type": "Casual"}, "regular employees"),
    ("on leave on the day", {"on_leave": "HR-LAP-0001"}, "On leave on 15 Sep 2026"),
    ("a bank loan", {"bank_loan": True}, "bank loan"),
    ("an earlier advance still owed", {"outstanding": 50000}, "still owed"),
    ("more than 40% of gross", {"amount": 400001}, "40% of a gross"),
    ("recovered over two months", {"instalments": 2}, "recovered in 1 month"),
    ("somebody who has left", {"status": "Left"}, "active employee"),
    ("nothing asked for", {"amount": 0}, "how much"),
):
    errors = V.eligibility_errors(dict(OK, **change), S)
    expect(label, errors, needle)
    if len(errors) != 1 and label != "nothing asked for":
        fail.append("%s must give its own one reason, not %s" % (label, errors))

# each rule is a switch, and a switched-off rule is silent
for label, change, switch in (
    ("four days absent", {"days_absent": 9}, {"salary_max_absent_days": 9}),
    ("a casual", {"employment_type": "Casual"}, {"salary_regular_only": 0}),
    ("on leave", {"on_leave": "HR-LAP-0001"}, {"salary_not_on_leave": 0}),
    ("a bank loan", {"bank_loan": True}, {"salary_no_bank_loan": 0}),
    ("an earlier advance", {"outstanding": 50000}, {"salary_no_outstanding": 0}),
):
    expect("%s, with the rule switched off" % label,
           V.eligibility_errors(dict(OK, **change), V.settings_from(dict(switch, not_regular_types=["Casual"]))))
expect("no absence allowed at all", V.eligibility_errors(dict(OK, days_absent=1),
                                                        V.settings_from({"salary_max_absent_days": "0"})),
       "no more than 0")

# the leave advance beside it (§4.4)
LEAVE = {"advance_type": "Leave Advance", "status": "Active", "employment_type": "Permanent",
         "pay_category": "Monthly", "gross_pay": 1000000, "amount": 600000, "outstanding": 0,
         "instalments": 1, "leave_days": 21, "bank_loan": False, "company_loan": 0}
expect("a regular employee taking 21 days, asking 60%", V.eligibility_errors(LEAVE, S))
expect("nineteen days of leave", V.eligibility_errors(dict(LEAVE, leave_days=19), S), "more than 19 days")
expect("a company loan still owed", V.eligibility_errors(dict(LEAVE, company_loan=200000), S), "company loan")
expect("a bank loan", V.eligibility_errors(dict(LEAVE, bank_loan=True), S), "bank loan")
expect("more than 60%", V.eligibility_errors(dict(LEAVE, amount=600001), S), "60% of a gross")
print("who qualifies: each of the minutes' conditions its own reason, and each one a switch")

# ── 5. The amount ─────────────────────────────────────────────────────
for args, expected, why in (
    (("Salary Advance", 1000000, "Monthly"), 400000.0, "40% of gross"),
    (("Salary Advance", 1000000, "Per Meter"), 110000.0, "the Per Meter standard rate, whatever the gross"),
    (("Salary Advance", 0, "Per Meter"), 110000.0, "even with no gross on record"),
    (("Salary Advance", 0, "Monthly"), None, "and nothing to work 40% of when there is no gross"),
    (("Leave Advance", 1000000, "Monthly"), 600000.0, "60% of gross for leave"),
    (("Special Advance", 1000000, "Monthly"), 500000.0, "half for the special advance"),
):
    if V.entitled(*args) != expected:
        fail.append("entitled%s is %r, expected %r: %s" % (args, V.entitled(*args), expected, why))
if V.entitled("Leave Advance", 1000000, "Per Meter", None, 800000) != 480000.0:
    fail.append("a Per Meter leave advance is 60% of the average of the last two months (§4.4)")
if V.entitled("Salary Advance", 1000000, "Per Meter", {"per_meter_amount": 0}) != 400000.0:
    fail.append("with no standard rate set, Per Meter staff get the percentage like anyone else")
print("the amount: 40% of gross, the Per Meter standard rate, 60% for leave, half for a special advance")

# ── 6. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "advances.py")


def body(name):
    if ("def %s(" % name) not in glue:
        fail.append("advances.py has no %s" % name)
        return ""
    return glue.split("def %s(" % name)[1].split("\ndef ")[0]


reading = body("settings")
if "get_singles_dict" not in reading or "rules.settings_from(" not in reading:
    fail.append("the settings are read from what was stored and merged over the minutes' numbers, "
                "so a stored nought stays a nought")
for constant in ("limit_for(", "DEFAULT_LIMIT_FRACTION", "MIN_MONTHS_SERVED", "MAX_INSTALMENTS"):
    if constant in body("_fill_money") + body("_facts") + body("_plan_salary"):
        fail.append("the salary advance must be worked out from the settings, not the constant %s" % constant)
validate = body("advance_validate")
if "settings()" not in validate or "_plan_salary(doc, s)" not in validate:
    fail.append("every advance reads the settings once, and a salary advance is planned against them")
plan = body("_plan_salary")
for needle, why in (
    ("rules.run_for(", "the run a request joins follows when it was handed in"),
    ("custom_requested_on", "which is the day it left Draft, not the day somebody started typing"),
    ("rules.payroll_period(", "absences are counted from the start of the payroll period"),
    ("attendance._off_duty_between(", "the approved off-duty days are the ones attendance.py already reads"),
    ("rules.days_absent(", "and taken off the absences by the rule, not by hand"),
    ("_closed_days(", "the public holidays come from the company's own holiday list"),
    ("min(getdate(today()), processed_on)", "until the day, absences are counted to today"),
):
    if needle not in plan:
        fail.append("_plan_salary: %s" % why)
if "Leave Application" not in body("_on_leave") or '"Approved"' not in body("_on_leave"):
    fail.append("on leave means an approved leave application covering the day")
if "custom_has_bank_loan" not in body("_bank_loan") or "custom_bank_loan_until" not in body("_bank_loan"):
    fail.append("a bank loan is read from the employee, and one that has run out no longer counts")
if "_has(" not in body("_bank_loan") or "_has(" not in body("_pay_category"):
    fail.append("the new Employee fields are asked about only once they exist: fixtures sync after patches")

step = body("_check_step")
if "PENDING_PAYROLL" not in step or "PENDING_FINANCE" not in step or "rules.held_until(" not in step:
    fail.append("the Payroll Officer ticks only the qualifying (§4.9): on passing a salary advance "
                "to Finance the eligibility is asked again and the processing date is held to")

if "_watch_salary_run()" not in body("daily"):
    fail.append("step 2 of chart 4.10, the system monitoring the payment date, runs every day")
watch = body("_watch_salary_run")
if "rules.request_deadline(" not in watch or "_work_out_again(" not in watch:
    fail.append("it tells the HR Officers when a run closes, and works the run out again on the day")
again = body("_work_out_again")
for needle in ("_plan_salary(", "_check_eligibility(", "db_set("):
    if needle not in again:
        fail.append("on the processing date each request is recounted and its result written down (%s)"
                    % needle)
if "Payroll Officer" not in again:
    fail.append("and the Payroll Officer is given the ones that still qualify")
# both reminders go to people who already hold the request on their list
# from the workflow, and people.assign will not put a document there twice
# — a task would be dropped, silently, on exactly the day it matters
for name, where in (("_tell_run_closed", "the day requests close"),
                    ("_work_out_again", "the processing date")):
    told = body(name)
    if "people.assign(" in told or "people.notify(" not in told:
        fail.append("the reminder on %s must be a notification: the person already holds the "
                    "request as a task, and a second task is silently skipped" % where)

controller = read("hrms_addon", "hrms_addon", "doctype", "advance_settings", "advance_settings.py")
if "advances.settings_validate(self)" not in controller:
    fail.append("the settings page refuses settings that make no sense")
print("glue: the settings read once, the salary advance planned, held to its day, and watched")

# ── 7. The fields, the patch and the way in ───────────────────────────
rows = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
fields = {(row["dt"], row["fieldname"]): row for row in rows}
category = fields.get(("Employee", "custom_pay_category"))
if not category:
    fail.append("the employee must say how their pay is earned, or a Per Meter advance cannot be told apart")
elif category.get("options", "").split("\n") != list(V.PAY_CATEGORIES):
    fail.append("the employee's Pay Category must offer exactly the categories the rules know: %s"
                % (V.PAY_CATEGORIES,))
for fieldname in ("custom_has_bank_loan", "custom_bank_loan_until"):
    if ("Employee", fieldname) not in fields:
        fail.append("the employee has nowhere to record a bank loan (%s)" % fieldname)
for fieldname in ("custom_processing_date", "custom_period_start", "custom_days_absent",
                  "custom_off_duty_days", "custom_requested_on", "custom_pay_category"):
    row = fields.get(("Employee Advance", fieldname))
    if not row:
        fail.append("the advance must show what it was worked out on (%s)" % fieldname)
    elif not row.get("read_only"):
        fail.append("%s is worked out, not typed, so it is read-only" % fieldname)

hooks = read("hrms_addon", "hooks.py")
for (dt, fieldname) in fields:
    if fieldname.startswith("custom_") and (dt, fieldname) in (
            ("Employee", "custom_pay_category"), ("Employee", "custom_has_bank_loan"),
            ("Employee Advance", "custom_processing_date")):
        if '"%s-%s"' % (dt, fieldname) not in hooks:
            fail.append("%s-%s is not in hooks.py's fixture list, so it is never synced" % (dt, fieldname))

patches = read("hrms_addon", "patches.txt")
if "hrms_addon.patches.v1_0.seed_advance_settings" not in patches:
    fail.append("the settings are saved once on migrate, or the page shows numbers nobody stored")
seed = read("hrms_addon", "patches", "v1_0", "seed_advance_settings.py")
if "has_column" in seed or "get_table_columns" in seed:
    fail.append("Advance Settings is a Single and has no table to ask a column of")
if "casual" not in seed.lower():
    fail.append("the seed puts the casuals on the list of those who are not regular")
if "stored" not in seed:
    fail.append("and leaves a page somebody has already saved exactly as they saved it")

nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if nav.count('"Advance Settings"') < 2:
    fail.append("Advance Settings needs a way in from the Advances card and the sidebar")
print("fields, patch and way in: the employee's pay category and bank loan, the advance's workings")

# "Salary Advance" typed in the search bar found nothing: it is not a
# DocType, it is Frappe HR's Employee Advance with an Advance Type
search = read("hrms_addon", "public", "js", "hrms_addon_search.js")
for kind in ("Salary Advance", "Leave Advance", "Special Advance"):
    if '"%s"' % kind not in search:
        fail.append("the search bar must know %s by name" % kind)
if "make_function_searchable" not in search or "custom_advance_type: kind" not in search:
    fail.append("each advance's name opens the advances of that type, as Frappe's own searchable names do")
if "/assets/hrms_addon/js/hrms_addon_search.js" not in read("hrms_addon", "hooks.py"):
    fail.append("the search names load on every desk page (app_include_js)")
print("the search bar: the three advances by name")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL SALARY ADVANCE CHECKS PASSED")
