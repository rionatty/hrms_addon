"""Verify leave earned by the days worked, without a bench:

    python scripts/verify_leave_accrual.py

Luuka's leave is earned: an employee may take what they have worked for.
How a type is earned is Frappe HR's standard Earned Leave setting on the
Leave Type; how much a year, the Leave Policy's annual allocation; this adds
the days worked (leave_accrual_rules.py).

  1  the periods, the day each is earned, the days worked
  2  what has been earned by a day, and what can be taken
  3  the Leave Application shows it and refuses more
  4  Frappe HR's balance is read with its own functions, without its check
  5  the Earned columns on the leave reports, ours and Frappe HR's
  6  a year's leave allocated to everyone at once; unearned leave off at the
     year's end
  7  the settings, the seed, the patch, the wiring and the way in
"""
import ast
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []
D = datetime.date


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(*parts):
    path = os.path.join(APPS_ROOT, *parts)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load("leave_accrual_rules")
print("loaded leave_accrual_rules.py without Frappe")

# ── 1. Periods, the day each is earned, the days worked ──────────────
if R.periods("2027-01-01", "2027-12-31", "Monthly")[1][:2] != (D(2027, 2, 1), D(2027, 2, 28)) \
        or len(R.periods("2027-01-01", "2027-12-31", "Monthly")) != 12:
    fail.append("Monthly: the twelve calendar months")
if [p[:2] for p in R.periods("2027-01-01", "2027-12-31", "Quarterly")] != [
        (D(2027, 1, 1), D(2027, 3, 31)), (D(2027, 4, 1), D(2027, 6, 30)), (D(2027, 7, 1), D(2027, 9, 30)),
        (D(2027, 10, 1), D(2027, 12, 31))]:
    fail.append("Quarterly: the calendar quarters, as Frappe HR counts them")
if [p[:2] for p in R.periods("2027-01-01", "2027-12-31", "Half-Yearly")] != [
        (D(2027, 1, 1), D(2027, 6, 30)), (D(2027, 7, 1), D(2027, 12, 31))]:
    fail.append("Half-Yearly: January to June, July to December")
if R.periods("2027-01-15", "2027-02-10", "Monthly") != [(D(2027, 1, 1), D(2027, 1, 31), D(2027, 1, 15), D(2027, 1, 31)),
                                                        (D(2027, 2, 1), D(2027, 2, 28), D(2027, 2, 1), D(2027, 2, 10))]:
    fail.append("a window part-way through a month keeps the whole month and the part inside")
if R.periods("2027-02-01", "2027-01-01") != []:
    fail.append("no periods in a window that ends before it starts")
first, last = D(2027, 2, 1), D(2027, 2, 28)
for how, joining, want in (("First Day", None, D(2027, 2, 1)), ("Last Day", None, D(2027, 2, 28)),
                           ("Date of Joining", "2020-01-31", D(2027, 2, 28)), ("Date of Joining", "2020-03-12", D(2027, 2, 12)),
                           (None, None, D(2027, 2, 28))):
    if R.credited_on(first, last, how, joining) != want:
        fail.append("credited_on(%s, joined %s) is %s, expected %s" % (how, joining, R.credited_on(first, last, how, joining), want))
if R.worked_days("2027-03-01", "2027-03-31") != 31 or R.worked_days("2027-03-01", "2027-03-31", "2027-03-11") != 21 \
        or R.worked_days("2027-03-01", "2027-03-31", None, "2027-03-10") != 10 \
        or R.worked_days("2027-03-01", "2027-03-31", off={D(2027, 3, 2): 1.0, D(2027, 3, 3): 0.5, D(2027, 4, 1): 1.0}) != 29.5 \
        or R.worked_days("2027-03-01", "2027-03-31", "2027-04-01") != 0:
    fail.append("worked_days: the days employed in the window, less the parts of days not worked in it")
if R.year_days("2027-01-01") != 365 or R.year_days("2028-01-01") != 366 or R.year_days("2028-02-29") != 366:
    fail.append("year_days: 365, or 366 across a 29 February")
if R.per_year(21, 5, "2027-01-01", "2027-12-31") != 21 or R.per_year(None, 21, "2027-01-01", "2027-12-31") != 21 \
        or abs(R.per_year(None, 10.5, "2027-01-01", "2027-12-31", "2027-07-02") * 183 / 365 - 10.5) > 0.001 \
        or R.per_year(None, 0, "2027-01-01", "2027-12-31") != 0 or R.per_year(None, 5, None, None) != 0:
    fail.append("per_year: the policy's days; else the allocation, spread over the part of the window employed")
for value, rounding, want in ((8.8, "0.25", 8.75), (8.99, "0.5", 8.5), (8.99, "1.0", 8.0), (8.999, "", 8.99),
                              (20.999999999, "1.0", 21.0), (21.0000001, "0.25", 21.0), (-0.0, "", 0.0)):
    if R.step_down(value, rounding) != want:
        fail.append("step_down(%r, %r) is %r, expected %r" % (value, rounding, R.step_down(value, rounding), want))
print("periods: the frequency's calendar periods, the day each is earned, the days worked")

# ── 2. What has been earned, what can be taken ────────────────────────
BASE = {"per_year": 21, "window_start": "2027-01-01", "window_end": "2027-12-31", "frequency": "Monthly",
        "allocate_on_day": "Last Day", "rounding": "0.25", "as_of": "2027-06-15", "joining": "2020-01-01"}


def earned(**change):
    return R.earned(dict(BASE, **change))


for label, change, want in (
    ("five months earned by 15 June, each on its last day", {}, 8.75),
    ("six by 15 June when earned on the first day", {"allocate_on_day": "First Day"}, 10.5),
    ("the whole year by 31 December", {"as_of": "2027-12-31"}, 21.0),
    ("nothing before the first month ends", {"as_of": "2027-01-30"}, 0.0),
    ("one month on the day it ends", {"as_of": "2027-01-31"}, 1.75),
    ("half a year for a joiner of 1 July", {"as_of": "2027-12-31", "joining": "2027-07-01"}, 10.5),
    ("half a year for a leaver of 30 June", {"as_of": "2027-12-31", "relieving": "2027-06-30"}, 10.5),
    ("a quarter by 15 May, quarterly", {"frequency": "Quarterly", "as_of": "2027-05-15"}, 5.25),
    ("nothing until the year ends, yearly", {"frequency": "Yearly", "as_of": "2027-12-30"}, 0.0),
    ("the year on its last day, yearly", {"frequency": "Yearly", "as_of": "2027-12-31"}, 21.0),
    ("a day of the month joined on", {"allocate_on_day": "Date of Joining", "joining": "2019-03-10", "as_of": "2027-02-10"},
     3.5),
    ("28 days a year, not rounded", {"per_year": 28, "rounding": "", "as_of": "2027-12-31"}, 28.0),
    ("nothing at a rate of none", {"per_year": 0}, 0.0),
    ("nothing before the window", {"as_of": "2026-12-31"}, 0.0),
    ("an unknown frequency is monthly", {"frequency": "Weekly"}, 8.75),
):
    got = earned(**change)["earned"]
    if got != want:
        fail.append("earned: %s is %s, expected %s" % (label, got, want))
unpaid = R.unpaid_days([{"from_date": "2027-03-01", "to_date": "2027-03-10"}])
if earned(as_of="2027-12-31", off=unpaid)["earned"] != 20.25:
    fail.append("ten days without pay earn nothing: 21 less 1.75 x 10/31, rounded down to a quarter, is 20.25")
if earned(off=unpaid)["days_worked"] != 156 or earned(off=unpaid)["days_off"] != 10:
    fail.append("days worked by 15 June are the 166 days less the ten without pay: %s" % earned(off=unpaid))
if earned(as_of="2027-12-31", joining="2027-07-01")["days_worked"] != 184:
    fail.append("a joiner has worked only since joining")
future_unpaid = R.unpaid_days([{"from_date": "2027-08-01", "to_date": "2027-08-31"}])
if earned(as_of="2027-12-31", off=future_unpaid)["earned"] != 19.25:
    fail.append("leave without pay already approved for a month still to come earns nothing for it")
periods_seen = earned()["periods"]
if len(periods_seen) != 12 or sum(1 for p in periods_seen if p["credited"]) != 5 or periods_seen[0]["worked"] != 31:
    fail.append("earned lists every period, the ones earned by the day marked: %s" % periods_seen[:2])
spans = [{"from_date": "2027-04-01", "to_date": "2027-04-05"},
         {"from_date": "2027-05-03", "to_date": "2027-05-03", "half_day": 1},
         {"from_date": "2027-06-01", "to_date": "2027-06-03", "include_holiday": 1}]
off = R.unpaid_days(spans, holidays=[D(2027, 4, 3), D(2027, 4, 4), D(2027, 6, 2)])
if off != {D(2027, 4, 1): 1.0, D(2027, 4, 2): 1.0, D(2027, 4, 5): 1.0, D(2027, 5, 3): 0.5, D(2027, 6, 1): 1.0,
           D(2027, 6, 2): 1.0, D(2027, 6, 3): 1.0}:
    fail.append("unpaid_days: the holidays inside leave without pay are not unpaid unless its type counts them; a half day "
                "is half: %s" % off)
if R.merge_off({D(2027, 1, 1): 0.5}, {D(2027, 1, 1): 1.0, D(2027, 1, 2): 2.0}) != {D(2027, 1, 1): 1.0, D(2027, 1, 2): 1.0}:
    fail.append("merge_off: the larger part of a day both give, never more than the whole day")
if R.available(21, 21, 8.75, 2) != 6.75 or R.available(10, 8.75, 8.75) != 10 or R.available(3, 1, 4) != 3:
    fail.append("available: Frappe HR's balance less what is allocated and not yet earned, less what waits for approval")
if R.unearned(21, 8.75) != 12.25 or R.unearned(8, 9) != 0:
    fail.append("unearned: what an allocation gives beyond what was earned, never below nothing")
errors = R.accrual_errors({"leave_type": "Annual Leave", "days": 10, "available": 7.75, "earned": 8.75,
                           "days_worked": 166, "carried": 2, "as_of": "2027-06-15"})
if len(errors) != 1 or "10 day(s) of Annual Leave applied for, 7.75 can be taken" not in errors[0] \
        or "8.75 day(s) are earned from 166 day(s) worked and 2 brought forward" not in errors[0] \
        or "Leave Without Pay for the other 2.25 day(s)" not in errors[0] or "15 Jun 2027" not in errors[0]:
    fail.append("the refusal says what was applied for, what can be taken, what was earned from what, and the rest: %s"
                % errors)
if R.accrual_errors({"days": 7.75, "available": 7.75}) or R.accrual_errors({"days": 1, "available": 1.0000001}):
    fail.append("leave within what can be taken is not refused")
if R.count_up_to(R.UP_TO_LEAVE_START, "2027-06-15", "2027-03-01") != D(2027, 6, 15) \
        or R.count_up_to(R.UP_TO_APPLYING, "2027-06-15", "2027-03-01") != D(2027, 3, 1) \
        or R.count_up_to(R.UP_TO_APPLYING, "2027-06-15", None) != D(2027, 6, 15):
    fail.append("count_up_to: the day the leave starts, or the day of applying, as the settings say")
if not R.earns({"is_earned_leave": 1}) or R.earns({"is_earned_leave": 1, "is_lwp": 1}) or R.earns({}) or R.earns(None):
    fail.append("earns: Frappe HR's Is Earned Leave, never leave without pay")
print("earned: period by period, by the days worked, rounded down; what can be taken; the refusal")

# ── 3. The Leave Application ──────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "leave_accrual.py")
leave_glue = read("hrms_addon", "hrms_addon", "leave.py")
custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
fields = {f["fieldname"]: f for f in custom if f["dt"] == "Leave Application"}
for name in ("custom_leave_earned", "custom_earned_by", "custom_days_worked", "custom_leave_brought_forward",
             "custom_leave_available"):
    f = fields.get(name) or {}
    if not (f.get("read_only") and f.get("no_copy")):
        fail.append("Leave Application.%s is worked out: read-only and never copied" % name)
if (fields.get("custom_balance_before") or {}).get("insert_after") != "custom_leave_available":
    fail.append("Leave Due Before follows the leave earned in Part 2")
for needle, why in (
    ("earned = leave_accrual.check_application(doc)\n    _fill_balances(doc, earned)",
     "every save of the form works out what is earned before the balances"),
    ("doc.custom_balance_before = flt(earned.available)", "Leave Due Before is what can be taken, for earned leave"),
):
    if needle not in leave_glue:
        fail.append("leave.py: %s" % why)
for needle, why in (
    ('if not found or doc.get("status") == "Rejected" or doc.docstatus == 2:', "a refused leave is not held back"),
    ('if cint((leave_type_rule(doc.leave_type) or {}).get("allow_negative")):\n            frappe.msgprint(',
     "a type allowed a negative balance is told, not refused"),
    ("frappe.throw(\"<br>\".join(_(message) for message in errors), title=_(\"Leave Earned\"))", "more than earned is refused"),
    ("on = rules.count_up_to(s.count_up_to, doc.from_date, doc.get(\"posting_date\") or today())",
     "earned up to the day the settings say"),
    ("found = accrual(doc.employee, doc.leave_type, on, until=doc.get(\"to_date\"), exclude=doc.name, s=s)",
     "the application itself is not counted as waiting"),
    ("for field in APPLICATION_FIELDS:\n            doc.set(field, None)", "the figures go when the type is not earned"),
    ('if row.workflow_state in approval.PENDING_STATES', "only leave sent for approval counts as waiting"),
    ('"leave_type": ["in", list(unpaid)], "from_date": ["<=", end],', "leave without pay approved earns nothing"),
    ('"status": rules.ABSENT,', "nor a day marked absent"),
    ('if not cint(s.get("absent_days_earn")):', "unless the settings say absent days earn"),
    ("policy = s.get(\"default_leave_policy\")", "the default policy for someone with no allocation yet"),
):
    if needle not in glue:
        fail.append("leave_accrual.py: %s" % why)
if not re.search(r"@frappe\.whitelist\(\)\ndef get_application_accrual\(", glue) or "_may_see(employee)" not in glue:
    fail.append("the form's figures come from a whitelisted method, for those who may see the employee")
js = read("hrms_addon", "public", "js", "leave_application.js")
for needle, why in (
    ('"hrms_addon.hrms_addon.leave_accrual.get_application_accrual"', "the form asks for the figures"),
    ("employee(frm) {\n\t\tfrm.trigger(\"earned\");", "as the employee is chosen"),
    ("from_date(frm) {\n\t\tfrm.trigger(\"earned\");", "and the dates"),
    ('__("More than earned")', "the headline says when a leave is longer than what is earned"),
):
    if needle not in js:
        fail.append("leave_application.js: %s" % why)
print("the application: Part 2 shows what is earned and can be taken; longer is refused")

# ── 4. Frappe HR's balance, read as it reads it ───────────────────────
source = upstream("hrms", "hrms", "hr", "doctype", "leave_application", "leave_application.py")
if source:
    for signature in ("def get_leave_allocation_records(employee, date, leave_type=None):",
                      "def get_remaining_leaves(\n\tallocation: dict, leaves_taken: float, date: str, cf_expiry: str, "
                      "manually_expired_leaves: float\n)",
                      "def get_allocation_expiry_for_cf_leaves(\n\temployee: str, leave_type: str, to_date: datetime.date, "
                      "from_date: datetime.date\n)",
                      "def get_manually_expired_leaves(\n\temployee: str, leave_type: str, from_date: datetime.date, "
                      "end_date: datetime.date\n)",
                      "def get_leaves_for_period(\n\temployee: str,\n\tleave_type: str,"):
        if signature not in source:
            fail.append("Frappe HR's leave_application.py changed a function the balance is read with: %r" % signature[:60])
    if '"new_leaves_allocated": d.new_leaves,' not in source or '"unused_leaves": d.cf_leaves,' not in source:
        fail.append("Frappe HR's allocation records no longer give the new and brought-forward leave by those names")
    if "validate_leave_access(employee)" not in source:
        fail.append("Frappe HR's balance no longer checks who asks: the reason it is read, not called, may be gone")
    print("upstream: the balance functions and what they return")
else:
    print("upstream checks SKIPPED (no %s)" % APPS_ROOT)
for name in ("get_allocation_expiry_for_cf_leaves", "get_leave_allocation_records", "get_leaves_for_period",
             "get_manually_expired_leaves", "get_remaining_leaves"):
    if name not in glue:
        fail.append("leave_accrual.py reads Frappe HR's balance with %s" % name)
if "get_leave_balance_on(" in glue:
    fail.append("leave_accrual.py must not call get_leave_balance_on: an approver's save would be refused")

# ── 5. The Earned columns ─────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if (hooks.get("extend_doctype_class") or {}).get("Report") != ["hrms_addon.hrms_addon.report_extensions.LeaveReportColumns"]:
    fail.append("Frappe HR's leave reports gain the Earned columns through extend_doctype_class on Report")
mixin = read("hrms_addon", "hrms_addon", "report_extensions.py")
for needle, why in (
    ("result = super().execute_module(filters)", "the report runs as Frappe HR wrote it"),
    ("if self.name not in leave_accrual.REPORTS:\n            return result", "every other report is untouched"),
    ("except Exception:", "and a failure gives the report back as it was"),
):
    if needle not in mixin:
        fail.append("report_extensions.py: %s" % why)
reports_root = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "report")
if os.path.isdir(reports_root):
    for name in re.search(r"REPORTS = \((.*?)\)", glue).group(1).replace('"', "").split(","):
        name = name.strip()
        if name and not os.path.isdir(os.path.join(reports_root, name.lower().replace(" ", "_"))):
            fail.append("Frappe HR has no report %s" % name)
    balance = upstream("hrms", "hrms", "hr", "report", "employee_leave_balance", "employee_leave_balance.py") or ""
    if '"fieldname": "closing_balance",' not in balance or "row.employee = employee.name" not in balance:
        fail.append("Employee Leave Balance changed its rows: the Earned columns go after closing_balance, by employee")
    summary = upstream("hrms", "hrms", "hr", "report", "employee_leave_balance_summary",
                       "employee_leave_balance_summary.py") or ""
    if 'columns.append(_(leave_type) + ":Float:160")' not in summary or ".orderby(LeaveType.name, order=frappe.qb.asc)" not in summary:
        fail.append("Employee Leave Balance Summary changed: one Float column per leave type, in name order")
framework = upstream("frappe", "frappe", "model", "base_document.py") or ""
if framework and 'extensions = frappe.get_hooks("extend_doctype_class", {}).get(doctype)' not in framework:
    fail.append("Frappe no longer mixes in extend_doctype_class: the Earned columns would not appear")
report_core = upstream("frappe", "frappe", "core", "doctype", "report", "report.py") or ""
if report_core and "def execute_module(self, filters):" not in report_core:
    fail.append("Frappe's Report no longer runs a report through execute_module")
schedule = read("hrms_addon", "hrms_addon", "report", "leave_schedule", "leave_schedule.py")
adherence = read("hrms_addon", "hrms_addon", "report", "leave_plan_adherence", "leave_plan_adherence.py")
if '"fieldname": "earned"' not in schedule or "leave_accrual.earned_for(" not in schedule:
    fail.append("Leave Schedule shows the leave earned so far")
if '"fieldname": "days_earned"' not in adherence or "leave_accrual.earned_for(" not in adherence:
    fail.append("Leave Plan Adherence shows the days earned beside the days planned")
own = json.loads(read("hrms_addon", "hrms_addon", "report", "leave_accrual", "leave_accrual.json"))
if (own.get("report_type"), own.get("is_standard"), own.get("ref_doctype")) != ("Script Report", "Yes", "Leave Application"):
    fail.append("the Leave Accrual report is a standard script report on Leave Application")
own_py = read("hrms_addon", "hrms_addon", "report", "leave_accrual", "leave_accrual.py")
for column in ("per_year", "days_worked", "days_off", "earned", "brought_forward", "taken", "pending", "available"):
    if '"fieldname": "%s"' % column not in own_py:
        fail.append("the Leave Accrual report shows %s" % column)
if 'conditions["name"] = mine' not in own_py:
    fail.append("an employee sees only their own leave earned")
print("reports: Frappe HR's three and ours show what is earned; the Leave Accrual report")

# ── 6. Allocating to everyone; unearned leave off at the year's end ──
for needle, why in (
    ('"assignment_based_on": "Leave Period",', "a policy for the leave period"),
    ('"effective_to": period.to_date, "carry_forward": 1})', "brought forward carried"),
    ('"leave_period": period.name, "effective_from": period.from_date,', "the period's dates, so a second run skips them"),
    ("policy = _last_policy(person.name) or s.default_leave_policy", "the policy of the year before, else the default"),
    ("if _allocated_in(person.name, policy, period):", "nobody already allocated is given a second"),
    ('frappe.db.savepoint("hrms_addon_leave_policy")', "one failure does not stop the rest"),
    ('frappe.enqueue("hrms_addon.hrms_addon.leave_accrual.allocate"', "Allocate Now runs in the background"),
    ('frappe.only_for(("HR Manager", "System Manager"))', "for the HR Manager"),
    ('"adjustment_type": "Reduce",', "unearned leave comes off with Frappe HR's own Leave Adjustment"),
    ('if frappe.db.exists("Leave Adjustment", {"leave_allocation": allocation.name, "docstatus": 1}):',
     "Frappe HR allows one adjustment an allocation"),
    ("cut = round(min(found.unearned, max(found.balance, 0.0)), 2) if found else 0",
     "never more than is left of the allocation"),
    ('"to_date": ["between", [add_days(on, -60), add_days(on, -1)]]}', "only allocations just ended"),
    ("    remove_unearned()\n    frappe.db.commit()\n    if settings().auto_allocate:\n        allocate()",
     "the year's unearned leave off before the new year's is allocated, which carries forward"),
):
    if needle not in glue:
        fail.append("leave_accrual.py: %s" % why)
if "hrms_addon.hrms_addon.leave_accrual.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the scheduler runs leave_accrual.daily")
if source:
    assignment = json.loads(upstream("hrms", "hrms", "hr", "doctype", "leave_policy_assignment",
                                     "leave_policy_assignment.json") or "{}")
    names = {f["fieldname"]: f for f in assignment.get("fields", [])}
    for field in ("employee", "leave_policy", "assignment_based_on", "leave_period", "carry_forward"):
        if field not in names:
            fail.append("Leave Policy Assignment has no %s upstream" % field)
    if "Leave Period" not in (names.get("assignment_based_on") or {}).get("options", ""):
        fail.append("Leave Policy Assignment is no longer made by Leave Period")
    adjustment = json.loads(upstream("hrms", "hrms", "hr", "doctype", "leave_adjustment", "leave_adjustment.json") or "{}")
    names = {f["fieldname"]: f for f in adjustment.get("fields", [])}
    for field in ("employee", "leave_type", "leave_allocation", "posting_date", "adjustment_type", "leaves_to_adjust",
                  "reason_for_adjustment"):
        if field not in names:
            fail.append("Leave Adjustment has no %s upstream" % field)
    period = json.loads(upstream("hrms", "hrms", "hr", "doctype", "leave_period", "leave_period.json") or "{}")
    if {"company", "from_date", "to_date", "is_active"} - {f["fieldname"] for f in period.get("fields", [])}:
        fail.append("Leave Period changed its fields")
print("allocation: everyone's policy at once, in the background; unearned leave off when the year ends")

# ── 7. Settings, seed, patch, wiring, the way in ──────────────────────
A = load("leave_advance_rules")
settings_spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", "leave_management_settings",
                                "leave_management_settings.json"))
page = {f["fieldname"]: f for f in settings_spec["fields"]}
if not settings_spec.get("issingle"):
    fail.append("Leave Management Settings is one page, a Single")
for name, default in (("absent_days_earn", "0"), ("count_up_to", R.UP_TO_LEAVE_START), ("remove_unearned", "1"),
                      ("auto_allocate", "0")):
    if str((page.get(name) or {}).get("default")) != default:
        fail.append("Leave Management Settings.%s defaults to %s" % (name, default))
if [o for o in ((page.get("count_up_to") or {}).get("options") or "").split("\n") if o] != list(R.UP_TO):
    fail.append("Count Leave Earned Up To offers exactly the rules' two days")
for key, value in A.DEFAULTS.items():
    if key in page and str(page[key].get("default")) != str(value if not isinstance(value, float) else "%g" % value):
        fail.append("Leave Management Settings.%s defaults to %s, as leave_advance_rules.DEFAULTS" % (key, value))
for name in ("default_leave_policy", "allocate_now", "leave_advance_account"):
    if name not in page:
        fail.append("Leave Management Settings has no %s" % name)
# The recovery component is only made on the first Leave Advance Processing;
# a Link to it refuses every save (and the migrate's patch) until then.
component = page.get("recovery_component") or {}
if (component.get("fieldtype"), component.get("read_only")) != ("Data", 1):
    fail.append("Leave Management Settings.recovery_component names the deduction as read-only text, not a Link to "
                "a Salary Component that is only made on the first run")
# every other Link a Single's code fills must point at a record there already is
for name, spec in page.items():
    if spec.get("fieldtype") == "Link" and spec.get("read_only"):
        fail.append("Leave Management Settings.%s is a read-only Link: code fills it, so a missing record would "
                    "refuse every save" % name)
seed = re.search(r"def leave_type_values\(name\):(.*?)(?:\n\n\n|\Z)", leave_glue, re.S)
if not seed or '"is_earned_leave": 1' not in seed.group(1) or '"earned_leave_frequency": "Monthly"' not in seed.group(1) \
        or '"rounding": ""' not in seed.group(1):
    fail.append("a new site's Annual Leave is earned monthly, not rounded")
patch = read("hrms_addon", "patches", "v1_0", "leave_accrual_and_advance.py")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.leave_accrual_and_advance" not in patches:
    fail.append("the patch runs after the model is synced")
for needle, why in (
    ('if frappe.get_all("Leave Allocation", filters={"leave_type": ANNUAL, "docstatus": 1, "to_date": [">=", start],',
     "Annual Leave is left alone where a policy's allocation would be credited twice"),
    ('"leave_policy_assignment": ["is", "set"]}, limit=1):', "only a policy's allocation"),
    ("if frappe.db.get_singles_dict(SETTINGS):\n        return", "settings saved before are Luuka's own"),
    ('"leave_percent": "advance_percent"', "the leave advance rules come across from Advance Settings"),
    ("if not leave_advance_rules.settings_errors(leave_advance_rules.settings_from(moved)):",
     "values the settings would refuse stay at their defaults instead of stopping the migrate"),
    ("doc.flags.ignore_links = True", "a link that is gone does not stop the migrate"),
):
    if needle not in patch:
        fail.append("the patch: %s" % why)
if "if not days or cint(frappe.db.get_value(\"Leave Type\", rules.ANNUAL, \"is_earned_leave\")):\n" \
        "            days = _policy_days(" not in leave_glue \
        or 'fields=["new_leaves_allocated", "unused_leaves"])' not in leave_glue:
    fail.append("the leave plan takes the year's days from the policy for earned leave, and what was brought forward "
                "from unused_leaves")
if "flt(sum(flt(row.unused_leaves) for row in allocations))" not in leave_glue:
    fail.append("the leave plan's brought forward is what came into the allocation (unused_leaves)")
settings_controller = read("hrms_addon", "hrms_addon", "doctype", "leave_management_settings",
                           "leave_management_settings.py")
if "    def validate(self):\n        leave_accrual.settings_validate(self)" not in settings_controller:
    fail.append("Leave Management Settings are checked as they are saved (leave_accrual.settings_validate)")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for needle in ('("Leave Accrual", "Leave Accrual", REPORT, "Reports", None),',
               '("Leave Management Settings", "Leave Management Settings", DOCTYPE, "Setup", None),'):
    if needle not in nav:
        fail.append("the Leaves page reaches %s" % needle.split(",")[0].strip("( "))
print("wiring: the settings, the seed, the patch, the daily job, the reports and the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL LEAVE ACCRUAL CHECKS PASSED")
