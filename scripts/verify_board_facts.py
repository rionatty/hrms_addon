"""Verify the HR board pack's facts (18 Nov 2026), without a bench:

    python scripts/verify_board_facts.py

The 33 columns a plant used to carry on HR Snapshot Plant are now rows: one per employee per month (HR Employee
Month), one per movement (HR Movement), the pay by plant, section, population and component (HR Pay Fact) and the
incidents (HR Safety Fact). Every figure of the pack is a GROUP BY over them.

  1  the rules: who is in which population, bands, hire reasons, months, the moves from Employee Transfers and the
     employee's history, a month's row and movements, pay that adds up, LTIFR, the reconciliation, data quality,
     the old pack carried over
  2  the paper: every field the glue writes is on its doctype, the options the rules use, who may read pay
  3  the glue: the long queue, chunks and commits, GROUP BYs and no query per employee, locked months left alone,
     permissions, indexes
  4  wiring: the nightly job, the patches, the menus
"""
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []
D = datetime.date


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def options(name, field):
    return [value for value in (fields(name)[field].get("options") or "").split("\n") if value]


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


def body_of(source, name):
    found = re.search(r"\ndef %s\(.*?(?=\ndef |\n@|\nclass |\Z)" % re.escape(name), source, re.S)
    return found.group(0) if found else ""


R = load("board_facts_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("population: foreign is an expatriate, paid by the week a casual, else permanent; never two",
      [R.population(category, foreign) for category, foreign in (("Regular", 0), ("Per Meter", 0), ("Weekly", 0),
                                                                  ("Per Piece", 0), ("Regular", 1), ("Weekly", 1),
                                                                  (None, 0))]
      == ["Permanent", "Permanent", "Casual", "Casual", "Expatriate", "Expatriate", "Permanent"])
check("an expatriate is on the permanent staff's head count", R.is_permanent("Expatriate") and not R.is_permanent("Casual"))
check("age bands by completed years, unknown without a birthday",
      [R.age_band(born, D(2026, 9, 30)) for born in ("2002-10-01", "2001-09-30", "1992-01-01", "1982-06-30",
                                                     "1972-09-30", "1960-01-01", None)]
      == ["Under 25", "25-34", "25-34", "35-44", "45-54", "55 and Over", "Unknown"])
check("tenure bands by completed years of service",
      [R.tenure_band(joined, D(2026, 9, 30)) for joined in ("2026-01-01", "2025-09-30", "2023-10-01", "2020-09-30",
                                                            "2016-01-01", "2015-09-30")]
      == ["Under 1 Year", "1-2 Years", "1-2 Years", "6-10 Years", "6-10 Years", "Over 10 Years"],
      [R.tenure_band(joined, D(2026, 9, 30)) for joined in ("2026-01-01", "2025-09-30", "2023-10-01", "2020-09-30",
                                                            "2016-01-01", "2015-09-30")])
check("years of service to a tenth", R.tenure_years("2020-07-01", "2026-07-01") == 6.0
      and R.tenure_years("2026-07-02", "2026-07-01") == 0.0)
check("a new post or a new addition adds capacity, a replacement backfills, no requisition is unclassified",
      [R.hire_class(reason) for reason in ("New Addition", "New Position", "Replacement", None, "")]
      == ["Addition", "Addition", "Replacement", "Unclassified", "Unclassified"])
check("months: start, end, adding, between, the day read as at",
      R.month_start("2026-07-19") == D(2026, 7, 1) and R.month_end("2026-02-10") == D(2026, 2, 28)
      and R.add_months("2026-11-05", 3) == D(2027, 2, 1) and R.add_months("2026-01-31", -1) == D(2025, 12, 1)
      and R.months_between("2026-11-20", "2027-01-02") == [D(2026, 11, 1), D(2026, 12, 1), D(2027, 1, 1)]
      and R.as_at("2026-11-01", "2026-11-18") == D(2026, 11, 18) and R.as_at("2026-10-01", "2026-11-18") == D(2026, 10, 31))
check("employed when the day is over: one whose last day it was is not",
      R.employed_after("2020-01-01", "2026-06-30", "2026-06-29")
      and not R.employed_after("2020-01-01", "2026-06-30", "2026-06-30")
      and R.employed_after("2026-06-30", None, "2026-06-30") and not R.employed_after(None, None, "2026-06-30"))

TRANSFERS = [{"name": "TRF-1", "employee": "E1", "transfer_date": "2026-07-15",
              "details": [{"fieldname": "branch", "current": "Kawempe", "new": "Namanve"},
                          {"fieldname": "department", "current": "A", "new": "B"}]}]
VERSIONS = [
    {"name": "V-1", "docname": "E1", "creation": "2026-07-16 09:00:00",
     "data": json.dumps({"changed": [["branch", "Kawempe", "Namanve"]]})},
    {"name": "V-2", "docname": "E2", "creation": "2026-07-20 10:00:00",
     "data": json.dumps({"changed": [["custom_pay_category", "Weekly", "Regular"], ["cell_number", "1", "2"]]})},
    {"name": "V-3", "docname": "E3", "creation": "2026-07-21 10:00:00",
     "data": json.dumps({"changed": [["custom_pay_category", "Regular", "Per Meter"]]})},
    {"name": "V-4", "docname": "E4", "creation": "2026-08-02 10:00:00",
     "data": json.dumps({"changed": [["branch", None, "Matugga"]]})},
    {"name": "V-5", "docname": "E5", "creation": "2026-08-03 10:00:00", "data": "not json"},
]
moved = R.transfer_moves(TRANSFERS)
check("an Employee Transfer's change of plant is a transfer; its other changes are not",
      [(move["movement_type"], move["from_branch"], move["to_branch"], move["effective_date"]) for move in moved]
      == [("Transfer", "Kawempe", "Namanve", D(2026, 7, 15))], moved)
history = R.version_moves(VERSIONS)
check("the employee's history: a change of plant, a casual made permanent, a plant first given; a change of pay "
      "category within the population and an unreadable entry are nothing",
      [(move["employee"], move["movement_type"]) for move in history]
      == [("E1", "Transfer"), ("E2", "Conversion"), ("E4", "Transfer")]
      and history[1]["from_population"] == "Casual" and history[1]["to_population"] == "Permanent"
      and history[2]["from_branch"] is None, history)
merged = R.merge_moves(moved, history)
check("the transfer's own row kept where the history says the same move within a month",
      [(move["employee"], move["source_doctype"]) for move in merged]
      == [("E1", "Employee Transfer"), ("E2", "Version"), ("E4", "Version")], merged)
far = R.merge_moves(moved, [dict(history[0], effective_date=D(2026, 9, 30))])
check("a second move a long way from the transfer is a move of its own", len(far) == 2, far)
check("a plant as it was when a day was over: the earliest later move's from, else today's",
      R.attribute_at("Namanve", [m for m in merged if m["employee"] == "E1"], D(2026, 7, 14), "branch") == "Kawempe"
      and R.attribute_at("Namanve", [m for m in merged if m["employee"] == "E1"], D(2026, 7, 15), "branch") == "Namanve"
      and R.attribute_at("Regular", [m for m in merged if m["employee"] == "E2"], D(2026, 7, 19), "category")
      == "Weekly")

PERSON = {"name": "E1", "employee_name": "Ann One", "branch": "Namanve", "department": "Looms", "pay_category": "Regular",
          "gender": "Female", "date_of_birth": "1990-03-01", "date_of_joining": "2019-02-01"}
row = R.employee_month(PERSON, D(2026, 7, 1), D(2026, 7, 31), [m for m in merged if m["employee"] == "E1"],
                       {"gross_pay": 900000, "ot_pay": 100000, "hours_worked": 200})
check("moved plant in the month: opened at Kawempe, closed at Namanve, one transfer",
      (row["opening_branch"], row["branch"], row["opening"], row["closing"], row["transferred"], row["paid"])
      == ("Kawempe", "Namanve", 1, 1, 1, 1), row)
check("a month's row carries its measures and its bands",
      (row["gross_pay"], row["ot_pay"], row["hours_worked"], row["age_band"], row["tenure_band"], row["population"])
      == (900000.0, 100000.0, 200.0, "35-44", "6-10 Years", "Permanent"), row)
july = R.employee_month(PERSON, D(2026, 6, 1), D(2026, 6, 30), [m for m in merged if m["employee"] == "E1"])
check("built for June after the move: June's row says Kawempe, as it was", (july["branch"], july["transferred"])
      == ("Kawempe", 0), july)
convert = R.employee_month(dict(PERSON, name="E2", branch="Kawempe", pay_category="Regular"), D(2026, 7, 1),
                           D(2026, 7, 31), [m for m in merged if m["employee"] == "E2"])
check("converted in the month: opened casual, closed permanent, one conversion",
      (convert["opening_population"], convert["population"], convert["converted"], convert["pay_category"])
      == ("Casual", "Permanent", 1, "Regular"), convert)
hired = R.employee_month(dict(PERSON, name="E6", date_of_joining="2026-07-10", pay_category="Weekly"),
                         D(2026, 7, 1), D(2026, 7, 31), [], {}, None, {"reason": "New Position", "job_requisition": "JR-1"})
check("hired in the month: not at the opening, a casual addition with its requisition",
      (hired["opening"], hired["closing"], hired["hired"], hired["hire_reason"], hired["job_requisition"],
       hired["population"], hired["paid"]) == (0, 1, 1, "Addition", "JR-1", "Casual", 0), hired)
gone = R.employee_month(dict(PERSON, name="E7", relieving_date="2026-07-31"), D(2026, 7, 1), D(2026, 7, 31), [], {},
                        {"name": "SEP-1", "reason": "Resignation", "exit_type": "Voluntary", "regrettable": 1})
check("left on the month's last day: the month's exit, with its reason, type and regret; not at the close",
      (gone["opening"], gone["closing"], gone["exited"], gone["exit_reason"], gone["exit_type"], gone["regrettable"])
      == (1, 0, 1, "Resignation", "Voluntary", 1), gone)
check("nor at the next month's opening", R.employee_month(dict(PERSON, relieving_date="2026-07-31"), D(2026, 8, 1),
                                                         D(2026, 8, 31)) is None)
check("one who joins after the day the month is read as at is not in it yet",
      R.employee_month(dict(PERSON, date_of_joining="2026-11-25"), D(2026, 11, 1), D(2026, 11, 18)) is None)
check("one who left before the month is not in it",
      R.employee_month(dict(PERSON, relieving_date="2026-06-30"), D(2026, 7, 1), D(2026, 7, 31)) is None)
steps = R.movement_rows(dict(PERSON, date_of_joining="2026-07-02", relieving_date="2026-07-28"), D(2026, 7, 1),
                        D(2026, 7, 31), [m for m in merged if m["employee"] == "E1"],
                        {"name": "SEP-9", "reason": "Desertion", "exit_type": "Involuntary"},
                        {"reason": "Replacement", "job_requisition": "JR-2", "job_applicant": "APP-2"})
check("a month's movements in order: the hire where it was made, the transfer, the exit where it left",
      [(step["movement_type"], step["branch"]) for step in steps]
      == [("Hire", "Kawempe"), ("Transfer", "Namanve"), ("Exit", "Namanve")]
      and steps[0]["hire_reason"] == "Replacement" and steps[0]["job_applicant"] == "APP-2"
      and steps[2]["exit_reason"] == "Desertion" and steps[2]["source_doctype"] == "Employee Separation"
      and steps[1]["source_name"] == "TRF-1", steps)
measures = R.attendance_measures({"days": 26, "worked": 24.5, "absent": 1, "hours": 180, "unclocked": 2,
                                  "ot_hours": 6, "clocked": 23}, 8)
check("hours worked: the clock's, and the standard day for a day it gave none",
      measures == {"hours_worked": 196.0, "days_worked": 24.5, "days_absent": 1.0, "ot_hours": 6.0,
                   "attendance_days": 26.0, "clock_days": 23.0}, measures)
pay = R.pay_rows([{"branch": "K", "work_section": "S1", "population": "Permanent", "salary_component": "Basic Salary",
                   "amount": 800, "heads": 2},
                  {"branch": "K", "work_section": "S1", "population": "Permanent", "salary_component": "Overtime 1",
                   "amount": 150, "heads": 1},
                  {"branch": "K", "work_section": None, "population": "Expatriate", "salary_component": "Basic Salary",
                   "amount": 4000, "heads": 1}],
                 [{"branch": "K", "work_section": "S1", "population": "Permanent", "gross": 1000, "heads": 2},
                  {"branch": "K", "work_section": None, "population": "Expatriate", "gross": 4000, "heads": 1},
                  {"branch": None, "work_section": None, "population": "Casual", "gross": 300, "heads": 3}],
                 {"Basic Salary": "Basic", "Overtime 1": "Overtime"})
check("pay lines add up to the slips' gross: earnings by group, the rest as Other with no component",
      round(sum(line["amount"] for line in pay), 2) == 5300
      and [(line["component_group"], line["salary_component"], line["amount"]) for line in pay
           if line["population"] == "Permanent"] == [("Basic", "Basic Salary", 800.0), ("Overtime", "Overtime 1", 150.0),
                                                     ("Other", None, 50.0)]
      and [(line["population"], line["amount"]) for line in pay if line["branch"] is None] == [("Casual", 300.0)],
      pay)
split = R.pay_rows([{"branch": "N", "population": "Permanent", "salary_component": "Basic Salary", "amount": 2800,
                     "heads": 2},
                    {"branch": "N", "population": "Permanent", "salary_component": "Basic Salary", "amount": 700,
                     "heads": 1}],
                   [{"branch": "N", "population": "Permanent", "gross": 2890, "heads": 2},
                    {"branch": "N", "population": "Permanent", "gross": 700, "heads": 1}], {"Basic Salary": "Basic"})
check("one plant and population given in two groups (two pay categories) is one: nothing taken away twice",
      sorted((line["component_group"], line["amount"], line["heads"]) for line in split)
      == [("Basic", 3500.0, 3), ("Other", 90.0, 3)], split)
check("a day lost is the longer of the sick days and the doctor's rest", R.days_lost(3, 5) == 5 and R.days_lost(4, 0) == 4)
check("with no clock hours, the month's people at the standard day and month", R.standard_hours(10, 8, 26) == 2080)
check("LTIFR: lost-time injuries per million hours", R.ltifr(2, 400000) == 5.0 and R.ltifr(1, 0) is None)
rows, total = R.reconciliation(
    {"Kawempe": {"opening": 100, "transferred": 2}, "Namanve": {"opening": 50, "transferred": 0}},
    {"Kawempe": {"closing": 99, "hired": 5, "exited": 4, "transferred": 0, "paid": 97},
     "Namanve": {"closing": 53, "hired": 2, "exited": 1, "transferred": 2, "paid": 53},
     "No Plant": {"closing": 1, "hired": 1, "exited": 0, "transferred": 0, "paid": 0}})
check("the reconciliation by plant: opening + hires - exits + transfers in - transfers out = closing, the payroll "
      "beside it, the plant with none last",
      [(row["branch"], row["expected"], row["variance"], row["payroll_variance"]) for row in rows]
      == [("Kawempe", 99, 0, 2), ("Namanve", 53, 0, 0), ("No Plant", 1, 0, 1)]
      and (total["opening"], total["closing"], total["transfers_in"], total["transfers_out"], total["variance"])
      == (150, 153, 2, 2, 0), (rows, total))
quality, issues = R.data_quality({"blank_branch": 3, "slips_without_branch": 2})
check("data quality: each check in the panel's order, how many in all",
      [row["key"] for row in quality] == ["blank_branch", "left_without_date", "hires_without_requisition",
                                          "slips_without_branch"] and issues == 5, quality)
check("a locked or imported month is never built again", R.may_build(0, "System") and not R.may_build(1, "System")
      and not R.may_build(0, "Imported"))
check("each night: the month running and the open months before it",
      R.refresh_due(["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01", "2026-11-01"], "2026-11-18", 2)
      == [D(2026, 9, 1), D(2026, 10, 1), D(2026, 11, 1)])
check("a system row is named by its month and employee, so a rebuild writes the same names",
      R.fact_name("2026-07-19", "E-1") == "2026-07 E-1")
check("written 500 rows at a time", [len(part) for part in R.chunks(range(1203))] == [500, 500, 203])
LEGACY = {"branch": "Kawempe", "opening": 98, "closing": 104, "permanent": 90, "casual": 14, "male": 70, "female": 30,
          "permanent_opening": 86, "casual_opening": 12, "hires": 12, "hires_permanent": 8, "hires_casual": 4,
          "replacements": 9, "additions": 3, "exits": 6, "exits_permanent": 4, "exits_casual": 2, "regrettable": 1,
          "incidents": 5, "near_misses": 2, "lost_time": 1, "fatalities": 0, "wage_bill": 1000, "basic": 600,
          "per_meter": 50, "overtime": 100, "special_overtime": 30, "arrears": 20, "other_pay": 200, "expatriates": 150,
          "casual_pay": 120}
people, pay, safety = R.legacy_rows(LEGACY)


def summed(rows, field, **where):
    return sum(row.get(field) or 0 for row in rows if all(row.get(key) == value for key, value in where.items()))


check("the old pack's month carried over: every total it held kept",
      (summed(people, "opening"), summed(people, "closing"), summed(people, "closing", population="Casual"),
       summed(people, "hired"), summed(people, "hired", hire_reason="Addition"), summed(people, "exited"),
       summed(people, "exited", population="Casual"), summed(people, "exited", regrettable=1),
       summed(people, "closing", gender="Male"), summed(people, "closing", gender="Female"),
       summed(people, "opening", population="Casual"))
      == (98, 104, 14, 12, 3, 6, 2, 1, 70, 30, 12), people)
check("its pay adds up to the old wage bill, expatriates and casuals as populations of their own, their pay "
      "taken out of Other first, then Basic",
      round(sum(line["amount"] for line in pay), 2) == 1000
      and summed(pay, "amount", population="Expatriate") == 150 and summed(pay, "amount", population="Casual") == 120
      and summed(pay, "amount", population="Permanent", component_group="Other") == 0
      and summed(pay, "amount", population="Permanent", component_group="Basic") == 530, pay)
check("its incidents by severity, near misses apart",
      sorted((line["severity"] or "", line["incidents"]) for line in safety)
      == [("", 2), ("Lost Time", 1), ("Near Miss", 2)], safety)

# ── 2. The paper ──────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "board_facts.py")
spec = importlib.util.spec_from_file_location("fields_only", os.path.join(APP, "board_facts.py"))
names = {}
for name in ("MONTH_FIELDS", "MOVEMENT_FIELDS", "PAY_FIELDS", "SAFETY_FIELDS"):
    found = re.search(r"^%s = (\(.*?\))(?:\s*\+.*?)?$" % name, GLUE, re.S | re.M)
    names[name] = found is not None
check("the glue names what it writes", all(names.values()), names)
for table, wanted in (("HR Employee Month", ["employee", "employee_name", "branch", "department", "work_section",
                                             "designation", "grade", "employment_type", "pay_category", "population",
                                             "gender", "age_band", "tenure_band", "is_foreign", "opening_branch",
                                             "opening_population", "hire_reason", "job_requisition", "exit_reason",
                                             "exit_type", "regrettable"] + list(R.COUNTS) + list(R.MEASURES)),
                      ("HR Movement", ["movement_type", "effective_date", "employee", "employee_name", "heads", "branch",
                                       "from_branch", "to_branch", "department", "designation", "work_section",
                                       "population", "from_population", "to_population", "from_category",
                                       "to_category", "hire_reason", "job_requisition", "job_applicant",
                                       "exit_reason", "exit_type", "regrettable", "tenure_years", "tenure_band",
                                       "source_doctype", "source_name"]),
                      ("HR Pay Fact", ["branch", "work_section", "population", "component_group", "salary_component",
                                       "amount", "heads"]),
                      ("HR Safety Fact", ["branch", "department", "severity", "hazard", "off_site", "incidents",
                                          "days_lost"])):
    have = fields(table)
    missing = [field for field in wanted + ["company", "month", "source"] if field not in have]
    check("%s has every field the build writes" % table, not missing, missing)
    if table != "HR Movement":
        check("%s says which month's build it belongs to" % table, "snapshot" in have)
    spec_json = doctype(table)
    check("%s can be imported, for the months before the system" % table, spec_json.get("allow_import") == 1)
    check("%s's source is System or Imported, and a user's row Imported" % table,
          options(table, "source") == list(R.SOURCES) and have["source"].get("default") == "Imported"
          and have["source"].get("read_only") == 1)
check("the populations, the hire reasons, the age and tenure bands are the rules'",
      options("HR Employee Month", "population") == list(R.POPULATIONS)
      and options("HR Employee Month", "hire_reason") == list(R.HIRE_REASONS)
      and options("HR Employee Month", "age_band") == list(R.AGE_BANDS)
      and options("HR Employee Month", "tenure_band") == list(R.TENURE_BANDS)
      and options("HR Movement", "movement_type") == list(R.MOVEMENTS)
      and options("HR Safety Fact", "severity") == list(R.SEVERITIES))
check("an imported row may count a group of people: heads, 1 for an employee",
      fields("HR Employee Month")["heads"].get("default") == "1" and "Blank" in
      (fields("HR Employee Month")["employee"].get("description") or ""))
pay_readers = {row["role"] for row in doctype("HR Employee Month")["permissions"] if row.get("read")}
check("a person's month (their pay) is read by HR, the payroll and the auditor, not the managers or the board",
      pay_readers == {"System Manager", "HR Manager", "HR User", "Payroll Officer", "Auditor"}, pay_readers)
board = {row["role"] for row in doctype("HR Pay Fact")["permissions"] if row.get("read")}
check("the pay by plant and component is the board's to read", {"Board Member", "General Manager",
                                                                "Executive Director"} <= board, board)
snapshot = fields("HR Monthly Snapshot")
check("the month's build: status, lock, progress, totals, reconciliation, data quality, rows",
      {"status", "locked", "locked_by", "built_on", "as_at", "progress", "build", "build_error", "total_opening",
       "total_hires", "total_exits", "total_transfers", "total_conversions", "total_closing", "total_payroll_heads",
       "total_wage_bill", "reconciliation_variance", "payroll_variance", "reconciliation", "employee_rows",
       "movement_rows", "pay_rows", "safety_rows"} <= set(snapshot)
      and options("HR Monthly Snapshot", "status") == list(R.STATUSES)
      and all(key in snapshot for key, _label in R.DATA_CHECKS))
recon = fields("HR Snapshot Reconciliation")
check("the reconciliation's lines hold what the rules work out",
      set(R.reconciliation({"K": {}}, {})[0][0]) <= set(recon) and doctype("HR Snapshot Reconciliation").get("istable"),
      set(R.reconciliation({"K": {}}, {})[0][0]) - set(recon))
check("the old plant columns are gone", not os.path.exists(os.path.join(APP, "doctype", "hr_snapshot_plant"))
      and "plants" not in snapshot)
for table in ("HR Employee Month", "HR Movement", "HR Pay Fact", "HR Safety Fact"):
    folder = table.lower().replace(" ", "_")
    controller = read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".py")
    check("%s's rows are checked, its month's totals kept, its indexes made" % table,
          all(needle in controller for needle in ("board_facts.fact_validate(self)", "board_facts.fact_on_update(self)",
                                                  "board_facts.fact_on_trash(self)",
                                                  'board_facts.add_indexes("%s")' % table, "def on_doctype_update():")))

# ── 3. The glue ───────────────────────────────────────────────────────
check("the build runs on the long queue, once however often it is asked",
      'queue="long"' in body_of(GLUE, "queue") and "deduplicate=True" in body_of(GLUE, "queue")
      and "job_id=" in body_of(GLUE, "queue") and "enqueue_after_commit=True" in body_of(GLUE, "queue"))
check("rows written 500 at a time, a commit after each, the progress shown",
      "rules.chunks(rows)" in body_of(GLUE, "_insert") and "frappe.db.bulk_insert(" in body_of(GLUE, "_insert")
      and "frappe.db.commit()" in body_of(GLUE, "_insert") and "frappe.publish_progress(" in body_of(GLUE, "_progress"))
loop = re.search(r"    for person in people:\n(.*?)\n    _replace\(", body_of(GLUE, "_build"), re.S)
check("nothing asked of the site per employee: the loop over the people only works the rules",
      loop and "frappe." not in loop.group(1), loop.group(1) if loop else "")
check("every aggregate a GROUP BY", GLUE.count("GROUP BY") >= 10, GLUE.count("GROUP BY"))
check("a plant and month with no clock hours read at the settings' standard month",
      "rules.standard_hours(" in body_of(GLUE, "month_figures") and '"days_per_month"' in GLUE
      and "days_per_month" in {field["fieldname"] for field in json.load(open(os.path.join(
          APP, "doctype", "board_report_settings", "board_report_settings.json"), encoding="utf-8"))["fields"]})
check("SQL names its tables and columns with backticks, its values as parameters",
      not re.search(r'(FROM|JOIN)\s+"?tab', GLUE) and "%(company)s" in GLUE and not re.search(r"%s['\"]\s*%\s*company", GLUE))
check("a cut is one of the rules' before it reaches the SQL", "if by not in rules.CUTS" in body_of(GLUE, "cut_figures"))
check("a locked or imported month is never built again",
      all("rules.may_build(" in body_of(GLUE, name) for name in ("build", "build_months", "nightly", "build_month")))
check("a failed build says why on the month, and the error is logged",
      "rules.FAILED" in body_of(GLUE, "build_month") and "frappe.log_error(" in body_of(GLUE, "build_month")
      and "frappe.db.rollback()" in body_of(GLUE, "build_month"))
check("the methods ask permission first",
      "doc.check_permission(\"write\")" in body_of(GLUE, "build")
      and "frappe.has_permission(SNAPSHOT, \"write\")" in body_of(GLUE, "build_months")
      and "check_permission(\"write\")" in body_of(GLUE, "refresh_totals"))
check("a user's row: imported, its month's header Imported, never a locked or system month's",
      all(needle in body_of(GLUE, "fact_validate") for needle in ("doc.source = rules.IMPORTED", "cint(stored.locked)",
                                                                  "stored.source != rules.IMPORTED")))
check("an approved report locks its months, a cancelled one lets go",
      '"locked": 1, "locked_by": report' in body_of(GLUE, "lock") and '"locked": 0' in body_of(GLUE, "unlock"))
check("the pay facts: one GROUP BY over the slips' earnings, statistical lines left out, an expatriate's converted",
      "`statistical_component` = 0" in body_of(GLUE, "_pay_facts") and "`do_not_include_in_total` = 0" in
      body_of(GLUE, "_pay_facts") and "`base_gross_pay`" in GLUE and "`exchange_rate`" in GLUE)
check("a hire's reason from their requisition: applicant, opening, requisition",
      all(name in body_of(GLUE, "_hire_reasons") for name in ("Job Applicant", "Job Opening", "Job Requisition",
                                                               "custom_reason_type")))
check("moves from submitted transfers and the employee's history of changes",
      '"docstatus": 1' in body_of(GLUE, "_moves") and "`tabVersion`" in body_of(GLUE, "_moves")
      and "rules.merge_moves(" in body_of(GLUE, "_moves"))
check("composite indexes on the facts and on what a build reads",
      ("company", "month", "branch") in [tuple(index) for index in eval(re.search(
          r"INDEXES = (\{.*?\n\})", GLUE, re.S).group(1).replace("EMPLOYEE_MONTH", "'m'").replace(
          "MOVEMENT", "'v'").replace("PAY", "'p'").replace("SAFETY", "'s'"))["m"]]
      and '"Version": (("ref_doctype", "creation"),)' in GLUE and "frappe.db.add_index(" in body_of(GLUE, "add_indexes"))

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("hooks: the nightly build on the long queue's schedule, the old 1st-of-the-month build gone",
      re.search(r'"daily_long": \[.*?"hrms_addon\.hrms_addon\.board_facts\.nightly"', HOOKS, re.S)
      and "board_pack.monthly" not in HOOKS)
PATCHES = read("hrms_addon", "patches.txt")
for patch in ("board_facts_from_snapshots", "board_fact_indexes", "board_member_access"):
    check("the %s patch is listed and there" % patch, "hrms_addon.patches.v1_0.%s" % patch in PATCHES
          and os.path.exists(os.path.join(PACKAGE, "patches", "v1_0", patch + ".py")))
MIGRATION = read("hrms_addon", "patches", "v1_0", "board_facts_from_snapshots.py")
check("the old pack carried over: plant rows, agenda lines, priorities, statuses, the attrition target; each step "
      "on its own", all(needle in MIGRATION for needle in ("board_facts.convert_legacy(", "`tabBoard Agenda Line`",
                                                            "has_column(\"HR Board Report\", \"priorities\")",
                                                            "'Action Needed'", "attrition_target",
                                                            "frappe.log_error(")))
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("HR Employee Month", "HR Movement", "HR Pay Fact", "HR Safety Fact", "HR Monthly Snapshot"):
    check("the Board Pack card and the HR Setup sidebar list %s" % name,
          '("%s", "%s", DOCTYPE)' % (name, name) in NAV and '("%s", "%s", DOCTYPE, None, None)' % (name, name) in NAV)
SNAPSHOT_JS = read("hrms_addon", "hrms_addon", "doctype", "hr_monthly_snapshot", "hr_monthly_snapshot.js")
check("the month's form: build it, see its rows, refresh an imported month's totals",
      '"hrms_addon.hrms_addon.board_facts.build"' in SNAPSHOT_JS and '"HR Employee Month"' in SNAPSHOT_JS
      and '"hrms_addon.hrms_addon.board_facts.refresh_totals"' in SNAPSHOT_JS)

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_board_facts: OK")
