"""Verify output pay — Per Meter, Per Piece and the hourly casuals — without
a bench:

    python scripts/verify_output_pay.py

The minutes of 16 and 20 July 2026 (Human Resource, Reward and
Compensation), §4.6: each machine has its own rate, which changes with
the width of the material (Per Meter) or the piece category (Per Piece);
the shift supervisor records each person's output on each machine; the
month — 26th to 25th — is summed and added on top of the basic salary. The
hourly casuals are paid hours x the standard rate, their overtime priced
by the overtime module.

  1  the rates: each machine's own, by width or category, from a date
  2  a shift: output x rate, and the target it is measured against
  3  the month: lines folded per person per machine, then per person
  4  the hourly casuals: the standard hours paid, the overtime not twice
  5  the paper: the DocTypes carry what the Per Meter Template carries
  6  the glue: priced on the day, paid as Additional Salary, never twice
  7  the wiring: events, the patch, the field, and the way in
"""
import importlib.util
import json
import os
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
            fail.append("%s: expected nothing wrong, got %s" % (label, errors))
    elif not any(needle in error for error in errors):
        fail.append("%s: expected %r among %s" % (label, needle, errors))


O = load("output_rules")
A = load("attendance_rules")
print("loaded output_rules.py without Frappe")

# ── 1. The rates ──────────────────────────────────────────────────────
LOOM = [{"width_cm": 45, "rate": 18, "daily_target": 900, "valid_from": "2026-01-01"},
        {"width_cm": 74, "rate": 25, "daily_target": 700, "valid_from": "2026-01-01"},
        {"width_cm": 45, "rate": 20, "daily_target": 900, "valid_from": "2026-09-01"}]
if O.rate_for(LOOM, "2026-08-30", 45)["rate"] != 18:
    fail.append("August's output at 45 cm is paid August's rate")
if O.rate_for(LOOM, "2026-09-02", 45)["rate"] != 20:
    fail.append("a rate that starts on 1 September prices September's output, not August's")
if O.rate_for(LOOM, "2026-09-02", 74)["rate"] != 25:
    fail.append("the width decides the rate: 74 cm pays more than 45 cm on the same machine")
if O.rate_for(LOOM, "2026-09-02", 60) is not None:
    fail.append("a width the machine has no rate for has no rate — not nought")
if O.rate_for(LOOM, "2025-12-31", 45) is not None:
    fail.append("and output from before any rate began has none either")
PRESS = [{"piece_category": "A", "rate": 150, "valid_from": "2026-01-01"},
         {"piece_category": "B", "rate": 200, "valid_from": "2026-01-01"}]
if (O.rate_for(PRESS, "2026-09-05", category="b", section=O.PER_PIECE) or {}).get("rate") != 200:
    fail.append("a Per Piece price is found by its category, whatever its case")
expect("a sound loom", O.rate_errors(O.PER_METER, LOOM))
expect("a sound press", O.rate_errors(O.PER_PIECE, PRESS))
expect("a Per Meter rate without a width", O.rate_errors(O.PER_METER, [{"rate": 5, "valid_from": "2026-01-01"}]),
       "width of material")
expect("a Per Piece rate without a category", O.rate_errors(O.PER_PIECE, [{"rate": 5, "valid_from": "2026-01-01"}]),
       "piece category")
expect("a rate of nothing", O.rate_errors(O.PER_METER, [{"width_cm": 45, "rate": 0, "valid_from": "2026-01-01"}]),
       "more than nothing")
expect("a rate with no start", O.rate_errors(O.PER_METER, [{"width_cm": 45, "rate": 5}]), "the day the rate starts")
expect("the same width from the same day twice", O.rate_errors(O.PER_METER, [
    {"width_cm": 45, "rate": 5, "valid_from": "2026-01-01"},
    {"width_cm": 45, "rate": 6, "valid_from": "2026-01-01"}]), "already there")
expect("a machine with no rates", O.rate_errors(O.PER_METER, []), "at least one rate")
print("rates: each machine's own, by width or category, from a date")

# ── 2. A shift ────────────────────────────────────────────────────────
if O.line(850, 18, 900) != {"amount": 15300.0, "achieved": 94.4}:
    fail.append("a shift earns output x rate, and is measured against its target: %s" % O.line(850, 18, 900))
if O.line(850, 18)["achieved"] is not None:
    fail.append("with no target there is nothing to have achieved")
ok_row = {"employee": "E1", "machine": "L1", "width_cm": 45, "output": 10, "rate": 20}
expect("a sound line", O.report_errors(O.PER_METER, [ok_row], {"E1": "Per Meter"}, {"L1": "Per Meter"}))
for label, change, cats, needle in (
    ("a machine from the other section", {"machine": "P1"}, {"E1": "Per Meter"}, "Per Piece machine"),
    ("somebody paid monthly", {}, {"E1": "Monthly"}, "paid Monthly"),
    ("no width on a loom", {"width_cm": 0}, {"E1": "Per Meter"}, "width of the material"),
    ("no rate for it", {"rate": None}, {"E1": "Per Meter"}, "no rate for"),
    ("less than nothing", {"output": -1}, {"E1": "Per Meter"}, "less than nothing"),
):
    expect(label, O.report_errors(O.PER_METER, [dict(ok_row, **change)], cats,
                                  {"L1": "Per Meter", "P1": "Per Piece"}), needle)
expect("the same person on the same machine twice",
       O.report_errors(O.PER_METER, [ok_row, dict(ok_row)], {"E1": "Per Meter"}, {"L1": "Per Meter"}),
       "already on this report")
expect("the same person on the same machine at two widths is two lines, not a repeat",
       O.report_errors(O.PER_METER, [ok_row, dict(ok_row, width_cm=74)], {"E1": "Per Meter"}, {"L1": "Per Meter"}))
print("a shift: output x rate, measured against target, and every wrong line refused")

# ── 3. The month ──────────────────────────────────────────────────────
DAYS = [{"employee": "E1", "machine": "L1", "width_cm": 45, "output": 850, "amount": 15300, "target": 900},
        {"employee": "E1", "machine": "L1", "width_cm": 45, "output": 900, "amount": 18000, "target": 900},
        {"employee": "E1", "machine": "L1", "width_cm": 74, "output": 600, "amount": 15000, "target": 700},
        {"employee": "E2", "machine": "L3", "width_cm": 45, "output": 700, "amount": 15400, "target": 750}]
merged = O.merge_lines(DAYS)
first = [row for row in merged if row["employee"] == "E1" and row["width_cm"] == 45]
if not first or first[0]["shifts"] != 2 or first[0]["amount"] != 33300:
    fail.append("a person's shifts on one machine at one width fold into one line, each at its own "
                "day's pay — the Per Meter Template's shape: %s" % first)
if len(merged) != 3:
    fail.append("a second width on the same machine is a line of its own: %s" % merged)
people = {row["employee"]: row for row in O.per_employee(merged)}
if people["E1"]["amount"] != 48300 or people["E2"]["amount"] != 15400:
    fail.append("each person's month is their lines added up: %s" % people)
if A.cycle_window(2026, 9) != (__import__("datetime").date(2026, 8, 26), __import__("datetime").date(2026, 9, 25)):
    fail.append("the payroll month is the 26th to the 25th")
print("the month: shifts folded per person per machine per width, then per person")

# ── 4. The hourly casuals ─────────────────────────────────────────────
month = O.hourly_pay([12, 10, 8, 0], 2500)
if month != {"days": 3, "hours": 28.0, "overtime": 2.0, "amount": 70000.0}:
    fail.append("an hourly casual is paid their standard hours; a twelve-hour day pays ten here and its "
                "two hours of overtime are the overtime module's: %s" % month)
if O.STANDARD_HOURS != A.STANDARD_HOURS:
    fail.append("the standard hours are the attendance register's: a twelve-hour shift, two of them overtime")
expect("hours but no rate", O.run_errors(O.HOURLY, [{"employee": "H1", "hours": 20, "amount": 0}], {"H1": 0}),
       "no hourly rate")
expect("a run with nobody in it", O.run_errors(O.PER_METER, []), "nothing in this run")
print("hourly: the standard hours paid at the rate, the overtime counted but not paid twice")

# ── 5. The paper ──────────────────────────────────────────────────────


def spec(name):
    folder = name.lower().replace(" ", "_")
    return json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))


def fields(name):
    return {row["fieldname"]: row for row in spec(name)["fields"]}


machine = fields("Production Machine")
if machine.get("rates", {}).get("options") != "Machine Rate":
    fail.append("a machine carries its own rates")
rate = fields("Machine Rate")
for fieldname in ("width_cm", "piece_category", "rate", "daily_target", "valid_from"):
    if fieldname not in rate:
        fail.append("a machine's rate row says %s" % fieldname)
if spec("Production Machine").get("autoname") != "field:machine_name":
    fail.append("a machine is known by its own name, which the daily report links to")
report = spec("Daily Production Report")
if not report.get("is_submittable"):
    fail.append("the daily report is submitted by the shift supervisor, and only then counted")
line = fields("Daily Production Line")
for fieldname in ("employee", "machine", "width_cm", "piece_category", "output", "target", "rate", "amount"):
    if fieldname not in line:
        fail.append("a daily line says %s — employee, machine, width or category, output, the rate "
                    "and what it earned" % fieldname)
for fieldname in ("rate", "amount", "achieved"):
    if not line.get(fieldname, {}).get("read_only"):
        fail.append("the %s on a daily line is worked out, not typed" % fieldname)
run = spec("Output Pay Run")
if not run.get("is_submittable"):
    fail.append("the month's run is submitted, and only then paid")
run_fields = fields("Output Pay Run")
if run_fields.get("section", {}).get("options", "").split("\n") != list(O.SECTIONS):
    fail.append("a run is for exactly the sections the rules know: %s" % (O.SECTIONS,))
if "additional_salary" not in fields("Output Pay Employee"):
    fail.append("each person's line keeps the Additional Salary it wrote")
settings = spec("Output Pay Settings")
if not settings.get("issingle"):
    fail.append("Output Pay Settings is one page for the company")
if fields("Output Pay Settings").get("standard_hours", {}).get("default") != "10":
    fail.append("the standard day is ten hours by default, as the attendance register has it")
print("the paper: machines with rates, the daily report, the month's run, the settings")

# ── 6. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "output_pay.py")


def body(name):
    marker = "def %s(" % name
    if marker not in glue:
        fail.append("output_pay.py has no %s" % name)
        return ""
    return glue.split(marker)[1].split("\ndef ")[0]


priced = body("report_validate")
if 'rules.rate_for(rates, doc.get("report_date")' not in priced:
    fail.append("a daily line is priced at its machine's rate on the day it was made, so a rate "
                "change reprices nothing already made")
if "rules.report_errors(" not in priced:
    fail.append("and every wrong line refused by the rules")
if "_paid_run(" not in body("report_on_submit"):
    fail.append("a report for a month already paid is refused, or the shift is never counted")
if "output_pay_run" not in body("report_on_cancel"):
    fail.append("a paid report cannot be cancelled from under its pay")
if "attendance_rules.cycle_window(" not in body("_set_period"):
    fail.append("the payroll month is the attendance register's own 26th to 25th, not a second copy")
if "docstatus" not in body("_one_run_a_month"):
    fail.append("one plant's month is paid once")
paying = body("run_on_submit")
for needle, why in (
    ('"Additional Salary"', "the pay is an Additional Salary, which the payroll run already reads"),
    ('"payroll_date": doc.to_date', "on the last day of the payroll month"),
    ('"overwrite_salary_structure_amount": 0', "on top of the basic salary, not in place of it"),
    ('"ref_doctype": RUN', "and traceable to the run that wrote it"),
    ("earning.submit()", "and submitted, or the payroll never sees it"),
    ('row.get("additional_salary")', "and never written twice for the same person"),
):
    if needle not in paying:
        fail.append("run_on_submit: %s" % why)
if "earning.cancel()" not in body("run_on_cancel"):
    fail.append("cancelling a run takes its pay back")
component = body("_component")
if '"depends_on_payment_days": 0' not in component:
    fail.append("the earnings are not pro-rated by payment days: the output is already what was "
                "earned, and pro-rating it would take a missed day off twice")
if '"type": "Earning"' not in component:
    fail.append("output pay is an earning")
hours = body("_fill_hours")
if "rules.hourly_pay(" not in hours or "PRESENT" not in hours:
    fail.append("an hourly casual is paid the standard hours of the days they were present")
if "custom_hourly_rate" not in body("_hourly_rates") or "standard_hourly_rate" not in body("_hourly_rates"):
    fail.append("their own rate first, the standard one otherwise")
kept = body("get_output")
if "from_reports" not in kept or "HAND_LINE_FIELDS" not in kept:
    fail.append("getting the output again keeps the lines somebody typed in by hand")
print("glue: priced on the day, paid once as Additional Salary, and taken back on cancel")

# ── 7. The wiring ─────────────────────────────────────────────────────
hooks = read("hrms_addon", "hooks.py")
for doctype, events in (("Production Machine", ("validate",)),
                        ("Daily Production Report", ("validate", "on_submit", "on_cancel")),
                        ("Output Pay Run", ("validate", "on_submit", "on_cancel"))):
    block = hooks.split('"%s": {' % doctype)[1].split("},")[0] if '"%s": {' % doctype in hooks else ""
    for event in events:
        if '"%s"' % event not in block:
            fail.append("%s has no %s event" % (doctype, event))
if "hrms_addon.patches.v1_0.seed_output_pay" not in read("hrms_addon", "patches.txt"):
    fail.append("the earnings and the settings are made on migrate")
seed = read("hrms_addon", "patches", "v1_0", "seed_output_pay.py")
if '"depends_on_payment_days": 0' not in seed:
    fail.append("and the migrate makes them the same way the code does")
rows = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
if not [row for row in rows if row["dt"] == "Employee" and row["fieldname"] == "custom_hourly_rate"]:
    fail.append("an hourly casual can carry their own rate")
if '"Employee-custom_hourly_rate"' not in hooks:
    fail.append("and that field is in the fixtures hooks.py syncs")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Daily Production Report", "Output Pay Run", "Production Machine", "Output Pay Settings"):
    if nav.count('"%s"' % name) < 2:
        fail.append("%s needs a way in from the Payroll page and its sidebar" % name)
print("wiring: the events, the patch, the hourly rate, and the Payroll page")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL OUTPUT PAY CHECKS PASSED")
