"""Verify the HR board pack (batch 7, 17 Nov 2026), without a bench:

    python scripts/verify_board_pack.py

Luuka's quarterly HR Board Report (LPL HR Board Report Q3 2026): head count by plant, recruitment, exits and
attrition, churn by employment type with the movement reconciliation, the year on year comparison, the wage bill and
its components, overtime, labour cost against revenue and safety, with HR's own words, as a deck and a workbook.
Decided with the user: revenue and kilograms are typed in each quarter by Finance; the wage bill is the payroll's.

  1  the rules: a month's snapshot by plant, and the quarter's tables from three of them, the quarter before and the
     same quarter a year before
  2  the paper: every field the rules, the glue and the deck name is on its doctype
  3  the glue: what it reads, what it leaves alone, who may ask it
  4  the deck: every section of Luuka's own, from the figures and the report's words
  5  wiring: the monthly snapshot, the seed, the menus, the forms' buttons
"""
import ast
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


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


def body_of_method(source, name):
    found = re.search(r"\n    def %s\(.*?(?=\n    def |\Z)" % re.escape(name), source, re.S)
    return found.group(0) if found else ""


def body_of(source, name):
    found = re.search(r"\ndef %s\(.*?(?=\ndef |\n@|\nclass |\Z)" % re.escape(name), source, re.S)
    return found.group(0) if found else ""


R = load("board_pack_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("a quarter's months, the quarter before, the label",
      R.quarter_months(2026, "Q3") == [(2026, 7), (2026, 8), (2026, 9)] and R.quarter_before(2026, "Q1") == (2025, "Q4")
      and R.quarter_before(2026, "Q3") == (2026, "Q2") and R.label(2026, "Q3") == "July – September 2026"
      and R.quarter_of("2026-11-17") == (2026, "Q4"))
check("casual is paid by the week; everyone else permanent",
      [R.kind_of({"pay_category": category}) for category in ("Weekly", "Per Piece", "Monthly", "Per Meter", None)]
      == ["Casual", "Casual", "Permanent", "Permanent", "Permanent"])
import datetime  # noqa: E402

D = datetime.date
check("employed on a day: joined by it, not relieved before it",
      R.employed_on({"date_of_joining": "2026-07-01"}, D(2026, 7, 1))
      and R.employed_on({"date_of_joining": "2020-01-01", "relieving_date": "2026-07-31"}, D(2026, 7, 31))
      and not R.employed_on({"date_of_joining": "2020-01-01", "relieving_date": "2026-07-30"}, D(2026, 7, 31))
      and not R.employed_on({"date_of_joining": "2026-08-01"}, D(2026, 7, 31)))
check("still employed when the day is over: one whose last day it was is not",
      not R.employed_after({"date_of_joining": "2020-01-01", "relieving_date": "2026-06-30"}, D(2026, 6, 30))
      and R.employed_after({"date_of_joining": "2026-06-30"}, D(2026, 6, 30)))
PEOPLE = [
    {"name": "A", "branch": "K", "gender": "Male", "pay_category": "Monthly", "date_of_joining": "2020-01-01"},
    {"name": "B", "branch": "K", "gender": "Female", "pay_category": "Weekly", "date_of_joining": "2026-07-10"},
    {"name": "C", "branch": "K", "gender": "Male", "pay_category": "Weekly", "date_of_joining": "2025-01-01",
     "relieving_date": "2026-07-20", "regrettable": 1},
    {"name": "D", "branch": "N", "gender": "Female", "pay_category": "Monthly", "date_of_joining": "2026-07-01",
     "hire_reason": "New Addition"},
    {"name": "E", "branch": "N", "gender": "Male", "pay_category": "Monthly", "date_of_joining": "2019-03-01",
     "relieving_date": "2026-06-30"},
    {"name": "F", "branch": "M", "gender": "Male", "pay_category": "Monthly", "date_of_joining": "2019-03-01",
     "relieving_date": "2026-07-15"},
]
SLIPS = [{"branch": "K", "employee": "A", "gross": 1000, "components": {"Basic Salary": 800, "Overtime 1": 200}},
         {"branch": "K", "employee": "B", "gross": 300, "components": {}},
         {"branch": "N", "employee": "D", "gross": 5000, "foreign": True, "components": {"Basic Salary": 4000}}]
snap = R.snapshot(PEOPLE, SLIPS, [{"branch": "K", "severity": "Lost Time"}, {"branch": "K", "severity": "Near Miss"}],
                  {"K": {"revenue": 1e9, "output_kg": 2000, "staff_cost": 0}}, "2026-07-01", "2026-07-31",
                  {"Basic Salary": "Basic", "Overtime 1": "Overtime"})
K, N = snap["K"], snap["N"]
check("the month's head count: opening, closing, permanent and casual, male and female",
      (K["opening"], K["closing"], K["permanent"], K["casual"], K["male"], K["female"]) == (2, 2, 1, 1, 1, 1)
      and (K["permanent_opening"], K["casual_opening"]) == (1, 1), K)
check("one who left the day before the month is not in it", (N["opening"], N["closing"], N["exits"]) == (0, 1, 0), N)
check("hires and exits by type; a regrettable loss counted",
      (K["hires"], K["hires_casual"], K["exits"], K["exits_casual"], K["regrettable"]) == (1, 1, 1, 1, 1))
check("a hire against a New Addition requisition is an addition; any other a replacement",
      (K["replacements"], K["additions"], N["additions"]) == (1, 0, 1))
check("the wage bill and its groups; what no group claims is Other; a casual's pay and an expatriate's apart",
      (K["wage_bill"], K["basic"], K["overtime"], K["other_pay"], K["casual_pay"], N["expatriates"], N["basic"],
       N["other_pay"]) == (1300, 800, 200, 300, 300, 5000, 4000, 1000), (K, N))
check("an exit nobody marked regrettable is not", (snap["M"]["exits"], snap["M"]["regrettable"]) == (1, 0), snap["M"])
check("incidents and their severity", (K["incidents"], K["lost_time"], K["near_misses"]) == (2, 1, 1))
check("Finance's figures for the plant", (K["revenue"], K["output_kg"]) == (1e9, 2000))
check("a plant with nothing at all is left out", "Z" not in R.snapshot([], [], [], {"Z": {}}, "2026-07-01", "2026-07-31"))
check("each earning's group from its name, until HR say otherwise",
      [R.component_group(name) for name in ("Basic Salary", "Overtime 1", "Special Overtime", "Per Meter 6",
                                            "Arrear", "OT 3", "LST", "")]
      == ["Basic", "Overtime", "Special Overtime", "Per Meter", "Arrears", "Overtime", "Other", "Other"])
check("monthly attrition: exits over the average of opening and closing",
      R.attrition(3, 100, 120) == 2.7 and R.attrition(1, 0, 0) is None)
check("a change as a percentage; none from nothing", R.change(120, 100) == 20.0 and R.change(5, 0) is None)


def month(closing, opening, exits, hires=0, wage=1e8, revenue=0, kg=0, staff=0, incidents=0, perm=None):
    perm = closing if perm is None else perm
    return dict(dict.fromkeys(R.COUNTS + R.AMOUNTS, 0), closing=closing, opening=opening, exits=exits, hires=hires,
                permanent=perm, casual=closing - perm, permanent_opening=opening, exits_permanent=exits,
                hires_permanent=hires, replacements=hires, wage_bill=wage, revenue=revenue, output_kg=kg,
                staff_cost=staff, incidents=incidents, basic=wage, overtime=wage / 10, male=closing)


NOW = [{"K": month(100, 98, 2, 4, revenue=1e9, kg=2e5, incidents=1)},
       {"K": month(102, 100, 3, 5, revenue=1.1e9, kg=2.1e5)},
       {"K": month(104, 102, 6, 8, revenue=1.2e9, kg=2.2e5, staff=1.5e8)}]
BEFORE = {"K": month(98, 97, 1, perm=90)}
LAST = [{"K": month(80, 79, 1, 2, wage=8e7, incidents=2)} for _ in range(3)]
PREVIOUS = [{"K": month(97, 96, 1, 3, wage=9e7, revenue=9e8)} for _ in range(3)]
Q = R.quarter(NOW, BEFORE, LAST, ["K"], 5.0, PREVIOUS)
head = Q["head_count"][0]
check("head count at the quarter's end, its share, against the quarter before, the permanent share then and now",
      (head["total"], head["share"], head["qoq"], head["permanent_share_start"], head["permanent_share_end"])
      == (104, 100.0, 6, 91.8, 100.0), head)
check("the months' head count, now and a year before", Q["monthly_head_count"] == [100, 102, 104]
      and Q["monthly_head_count_last_year"] == [80, 80, 80])
check("recruitment: the quarter's hires against the quarter before and a year before",
      (Q["recruitment"][0]["total"], Q["recruitment"][0]["previous"], Q["recruitment"][0]["last_year"]) == (17, 9, 6))
ex = Q["exits"][0]
check("exits month by month with their attrition, the quarter's average, a year before",
      [entry["rate"] for entry in ex["months"]] == [2.0, 3.0, 5.8] and ex["total"] == 11 and ex["average"] == 3.6
      and ex["last_year_average"] == 1.3 and ex["over_target"], ex)
recon = Q["reconciliation"][-1]
check("the reconciliation: opening, plus hires, less exits, against what is reported",
      (recon["opening"], recon["hires"], recon["exits"], recon["expected"], recon["reported"], recon["variance"])
      == (98, 17, 11, 104, 104, 0), recon)
churn = Q["churn"][0]
check("churn by type over the quarter, a year before beside it",
      churn["permanent"] == (11, 10.9) and churn["permanent_last_year"] == (3, 3.8), churn)
pay = Q["wage_bill"][0]
check("the wage bill: month by month, cost per kg, against the quarter before and a year before",
      pay["wage_bill"] == 3e8 and pay["months"][0]["cost_per_kg"] == 500 and pay["qoq"] == 11.1 and pay["yoy"] == 25.0
      and pay["per_employee_month"] == 980392, pay)
labour = Q["labour_cost"][0]
check("labour cost: Finance's staff cost where typed, the wage bill where not",
      labour["staff_cost"] == 1.5e8 and labour["from_finance"] and labour["share"] == 4.5
      and labour["monthly_share"] == [10.0, 9.1, 12.5], labour)
check("revenue per employee and output per employee a month", labour["revenue_per_employee"] == 32352941
      and labour["output_per_employee_month"] == 2059, labour)
check("components against a year before, and each one's share of the increase",
      [(row["group"], row["share_of_increase"]) for row in Q["components"][:2]] == [("Basic", 100.0), ("Per Meter", 0.0)]
      and Q["components"][0]["yoy"] == 25.0, Q["components"])
check("safety: incidents by month, the quarter against a year before",
      Q["safety"][0]["months"] == [1, 0, 0] and Q["safety"][0]["total"] == 1 and Q["safety"][0]["last_year"] == 6)
check("the totals row follows the plants", all(rows[-1]["plant"] is None for rows in (
    Q["head_count"], Q["recruitment"], Q["exits"], Q["churn"], Q["reconciliation"], Q["wage_bill"], Q["labour_cost"],
    Q["safety"])))
check("no year before: the comparisons say so rather than nought",
      R.quarter(NOW, None, [], ["K"])["recruitment"][0]["last_year"] is None
      and R.quarter(NOW, None, [], ["K"])["head_count"][0]["qoq"] is None)
check("the board's eight areas and seven metrics, ready to fill", len(R.default_ratings()) == 8
      and [row["metric"] for row in R.default_metrics()] == list(R.METRICS))

# ── 2. The paper ──────────────────────────────────────────────────────
plant = fields("HR Snapshot Plant")
for field in R.COUNTS + R.AMOUNTS:
    check("HR Snapshot Plant has %s" % field, field in plant)
snapshot = fields("HR Monthly Snapshot")
check("a snapshot: company, month, source, locked, plants, totals",
      {"company", "month_start", "source", "locked", "built_on", "build", "plants", "total_closing", "total_wage_bill"}
      <= set(snapshot) and snapshot["source"]["options"].split("\n") == ["System", "Imported"]
      and doctype("HR Monthly Snapshot").get("allow_import") == 1)
line = fields("Board Finance Line")
check("Finance's line: plant, month, revenue, output, staff cost",
      {"branch", "month_start", "revenue", "output_kg", "staff_cost"} <= set(line))
check("Finance's quarter: company, year, quarter, lines", {"company", "year", "quarter", "add_lines", "lines"}
      <= set(fields("Board Finance Figures")))
roles = {row["role"] for row in doctype("Board Finance Figures")["permissions"] if row.get("write")}
check("Finance type their own figures", {"Accounts Manager", "Accounts User", "Finance Officer", "HR Manager"} <= roles)
settings = fields("Board Report Settings")
check("the settings: the attrition target and the component groups",
      {"attrition_target", "component_groups"} <= set(settings)
      and fields("Board Component Group")["component_group"]["options"].split("\n") == list(R.GROUPS))
report = fields("HR Board Report")
DECK = read("hrms_addon", "hrms_addon", "board_deck.py")
named = set(re.findall(r'self\.doc\.get\("(\w+)"\)', DECK)) | set(re.findall(r"self\.doc\.(\w+)\b", DECK))
named -= {"get", "quarter", "year"}
for field in sorted(named):
    check("HR Board Report has %s, which the deck reads" % field, field in report)
check("the report's ratings are the board's", fields("Board Health Rating")["rating"]["options"].split("\n")[1:]
      == list(R.RATINGS))
check("the report is approved by the HR Manager", any(row["role"] == "HR Manager" and row.get("submit")
                                                     for row in doctype("HR Board Report")["permissions"])
      and doctype("HR Board Report").get("is_submittable") == 1)
safety = fields("Safety Incident")
for field in ("severity", "hazard", "off_site", "corrective_action", "capa_owner", "capa_due", "capa_status",
              "capa_closed_on"):
    check("Safety Incident has %s, kept up after it is recorded" % field,
          field in safety and safety[field].get("allow_on_submit") == 1)
check("a safety incident's severities are the board's", safety["severity"]["options"].split("\n")[1:]
      == list(R.SEVERITIES))
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
check("a separation may be marked a regrettable loss", any(row["name"] == "Employee Separation-custom_regrettable"
                                                         and row.get("allow_on_submit") for row in custom))

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "board_pack.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("the rules decide", "rules.snapshot(" in GLUE and "rules.quarter(" in GLUE)
check("a locked or imported month stands as it is",
      'cint(doc.locked) or doc.get("source") == "Imported"' in body_of(GLUE, "rebuild_snapshot")
      and 'not cint(doc.locked) and doc.get("source") != "Imported"' in body_of(GLUE, "take_snapshot"))
check("on the 1st, the month just ended", "(first - datetime.timedelta(days=1)).replace(day=1)" in body_of(GLUE, "monthly"))
check("the payroll's wage bill: submitted slips, in the company's currency, statistical lines left out",
      '"docstatus": 1' in body_of(GLUE, "_slips") and '"statistical_component": 0' in GLUE
      and '"do_not_include_in_total": 0' in GLUE and "base_gross_pay" in GLUE)
check("a hire's reason from their requisition: applicant, opening, requisition",
      all(name in body_of(GLUE, "_hire_reasons") for name in ("Job Applicant", "Job Opening", "Job Requisition",
                                                               "custom_reason_type")))
check("the quarter takes the quarter before and the same quarter a year before",
      "rules.quarter_before(year, quarter)" in GLUE and "_snapshot(company, y - 1, m)" in GLUE)
check("every method asks the reader's permission first",
      all("doc.check_permission(" in body_of(GLUE, name) for name in ("add_finance_lines", "rebuild_snapshot",
                                                                      "get_figures", "download_deck",
                                                                      "download_workbook")))
check("an approved report's figures stand", "The report is approved: its figures stand." in GLUE)
check("the regrettable losses written in where HR have written nothing",
      'if not (doc.get("regrettable_note") or "").strip()' in body_of(GLUE, "get_figures"))

# ── 4. The deck ───────────────────────────────────────────────────────
tree = ast.parse(DECK)
deck_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_Deck")
methods = {node.name for node in deck_class.body if isinstance(node, ast.FunctionDef)}
for slide in ("cover", "contents", "summary", "head_count", "head_count_yoy", "recruitment", "exits", "churn",
              "comparative", "wage_bill", "components", "labour_cost", "metrics", "learning", "training_value",
              "safety", "memoriam", "achievements", "agenda", "outlook", "closing"):
    check("the deck has its %s slide, in the build" % slide,
          slide in methods and re.search(r"self\.%s[,)]" % slide, body_of_method(DECK, "build")))
check("the deck needs python-pptx, and says so", "bench pip install python-pptx" in DECK)
check("native charts and tables, so the board can still edit them",
      "add_chart(" in DECK and "add_table(" in DECK)
check("the deck is refused before there are figures", "Get the figures first" in DECK)

# ── 5. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("hooks: the month's snapshot on the 1st", re.search(
    r'"monthly": \[.*?"hrms_addon\.hrms_addon\.board_pack\.monthly"', HOOKS, re.S))
check("hooks: the component groups seeded on migrate", '"hrms_addon.hrms_addon.board_pack.setup_on_migrate"' in HOOKS)
check("hooks: the regrettable flag shipped", '"Employee Separation-custom_regrettable"' in HOOKS)
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("HR Board Report", "HR Monthly Snapshot", "Board Finance Figures", "Board Report Settings"):
    check("the HR Setup page's Board Pack card lists %s" % name, '("%s", "%s", DOCTYPE)' % (name, name) in NAV)
for doctype_name, method in (("board_finance_figures", "add_finance_lines"), ("hr_monthly_snapshot", "rebuild_snapshot"),
                             ("hr_board_report", "get_figures")):
    script = read("hrms_addon", "hrms_addon", "doctype", doctype_name, doctype_name + ".js")
    check("%s's button asks board_pack.%s" % (doctype_name, method),
          '"hrms_addon.hrms_addon.board_pack.%s"' % method in script)
REPORT_JS = read("hrms_addon", "hrms_addon", "doctype", "hr_board_report", "hr_board_report.js")
check("the report offers the deck and the workbook once it has figures",
      "download_deck" in REPORT_JS and "download_workbook" in REPORT_JS and "frm.doc.figures_json" in REPORT_JS)
check("the report's preview escapes what it shows", "frappe.utils.escape_html" in REPORT_JS)

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_board_pack: OK")
