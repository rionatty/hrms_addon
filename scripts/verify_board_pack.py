"""Verify the HR board pack (batch 7, 17 Nov 2026; on its facts, 18 Nov 2026), without a bench:

    python scripts/verify_board_pack.py

Luuka's quarterly HR Board Report (LPL HR Board Report Q3 2026): head count by plant, recruitment, exits and
attrition, churn by employment type with the movement reconciliation, the year on year comparison, the wage bill and
its components, overtime, labour cost against revenue and safety, with HR's own words, as a deck and a workbook.
Decided with the user: revenue and kilograms are typed in each quarter by Finance; the wage bill is the payroll's.
Since 18 Nov 2026 every figure is a GROUP BY over the facts (verify_board_facts.py), and the review's five figure bugs
are put right: expatriates and casuals are populations, never rows overlapping the components; staff cost is
Finance's for each plant and month where typed; a New Position is an addition and no requisition is unclassified;
near misses are not incidents; the people and pay with no plant are a row of their own.

  1  the rules: a quarter's tables from its months, the quarter before and the same quarter a year before; a
     quarter in one line for the trends
  2  the paper: every field the rules, the glue and the deck name is on its doctype
  3  the glue: what it reads, what it leaves alone, who may ask it
  4  the deck: every section of Luuka's own and what was added, from the figures and the report's words
  5  wiring: the seed, the menus, the forms' buttons
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
check("a quarter's months, the quarter before, the label, the quarters back",
      R.quarter_months(2026, "Q3") == [(2026, 7), (2026, 8), (2026, 9)] and R.quarter_before(2026, "Q1") == (2025, "Q4")
      and R.quarter_before(2026, "Q3") == (2026, "Q2") and R.label(2026, "Q3") == "July – September 2026"
      and R.quarter_of("2026-11-17") == (2026, "Q4") and R.short_label(2026, "Q3") == "Q3 26"
      and R.quarters_back(2026, "Q2", 4) == [(2025, "Q3"), (2025, "Q4"), (2026, "Q1"), (2026, "Q2")])


def month(**values):
    return values


# a quarter of two plants and the people with no plant, as board_facts.month_figures gives it
JULY = {"Kawempe": month(opening=100, closing=104, casual=20, casual_opening=18, hires=8, hires_casual=5,
                         replacements=5, additions=2, unclassified=1, exits=4, exits_casual=3, regrettable=1,
                         voluntary=3, involuntary=1, transfers_in=0, transfers_out=1, conversions=2, payroll_heads=103,
                         male=70, female=34, wage_bill=1000, basic=600, overtime=80, special_overtime=20, other_pay=50,
                         expatriates=150, casual_pay=100, overtime_all=120, revenue=10000, output_kg=2000,
                         staff_cost=1200, incidents=2, near_misses=3, lost_time=1, hours_worked=20000, days_lost=4),
        "Namanve": month(opening=50, closing=52, casual=10, casual_opening=10, hires=3, hires_casual=1, replacements=3,
                         exits=2, exits_casual=1, transfers_in=1, payroll_heads=52, male=30, female=22, wage_bill=500,
                         basic=400, casual_pay=100, revenue=4000, output_kg=1000, incidents=1, hours_worked=10000),
        "No Plant": month(opening=2, closing=3, hires=1, unclassified=1, payroll_heads=0, wage_bill=30, basic=30)}
AUGUST = {"Kawempe": dict(JULY["Kawempe"], opening=104, closing=106, staff_cost=0),
          "Namanve": dict(JULY["Namanve"], opening=52, closing=53, transfers_in=0, hires=1),
          "No Plant": dict(JULY["No Plant"], opening=3, closing=3, hires=0, unclassified=0)}
SEPTEMBER = {"Kawempe": dict(AUGUST["Kawempe"], opening=106, closing=101, exits=9, exits_casual=6),
             "Namanve": dict(AUGUST["Namanve"], opening=53, closing=54),
             "No Plant": dict(AUGUST["No Plant"])}
BEFORE = {"Kawempe": month(closing=99, casual=19), "Namanve": month(closing=50, casual=10), "No Plant": month(closing=2)}
LAST = [{"Kawempe": month(opening=90, closing=90, casual=30, casual_opening=30, exits=2, exits_casual=2, hires=2,
                          wage_bill=800, basic=500, expatriates=100, casual_pay=200, overtime_all=60, incidents=4)}] * 3
PREVIOUS = [{"Kawempe": month(opening=97, closing=99, hires=3, wage_bill=900, revenue=9000, staff_cost=950,
                              output_kg=1800, regrettable=1)}] * 3
Q = R.quarter([JULY, AUGUST, SEPTEMBER], BEFORE, LAST, None, 5.0, PREVIOUS)
check("the plants in order, the people with no plant a row of their own and last",
      Q["plants"] == ["Kawempe", "Namanve", "No Plant"], Q["plants"])
total = Q["head_count"][-1]
check("the plants add up to the total: no plant left out of the table but counted in it",
      total["total"] == sum(row["total"] for row in Q["head_count"][:-1]) == 158, Q["head_count"])
kawempe = Q["head_count"][0]
check("head count: permanent (with the expatriates) and casual, QoQ, the permanent share then and now, conversions",
      (kawempe["permanent"], kawempe["casual"], kawempe["qoq"], kawempe["permanent_share_start"],
       kawempe["permanent_share_end"], kawempe["conversions"]) == (81, 20, 2, 80.8, 80.2, 6), kawempe)
hiring = Q["recruitment"][-1]
check("recruitment: replacements, additions, the hires with no requisition apart",
      (hiring["replacements"], hiring["additions"], hiring["unclassified"], hiring["total"])
      == (24, 6, 4, 30), hiring)
gone = Q["exits"][0]
check("exits month by month, the months over the target marked, voluntary and involuntary",
      [entry["rate"] for entry in gone["months"]] == [3.9, 3.8, 8.7] and gone["over_target_months"] == [2]
      and gone["over_target"] and (gone["voluntary"], gone["involuntary"]) == (9, 3), gone)
recon = Q["reconciliation"]
check("the reconciliation: opening + hires - exits + transfers in - transfers out, for each plant and the total",
      all(row["expected"] == row["opening"] + row["hires"] - row["exits"] + row["transfers_in"] - row["transfers_out"]
          and row["variance"] == row["reported"] - row["expected"] for row in recon)
      and [row["plant"] for row in recon] == ["Kawempe", "Namanve", "No Plant", None]
      and (recon[-1]["opening"], recon[-1]["transfers_in"], recon[-1]["transfers_out"]) == (152, 1, 3), recon)
check("and the payroll's heads beside the closing", recon[0]["payroll_heads"] == 103
      and recon[0]["payroll_variance"] == recon[0]["reported"] - 103, recon[0])
components = Q["components"]
check("the components of the permanent staff's pay, then expatriates and casuals: rows that add up to the wage bill",
      [row["group"] for row in components] == list(R.GROUPS) + ["Expatriates", "Casuals"]
      and round(sum(row["now"] for row in components), 2) == Q["components_total"]["wage_bill"] == 4590.0
      and Q["components_total"]["now"] == Q["components_total"]["wage_bill"], (components, Q["components_total"]))
labour = Q["labour_cost"][0]
check("staff cost: Finance's for July where typed, the wage bill for August and September",
      labour["staff_cost"] == 1200 + 1000 + 1000 and labour["from_finance"] == "Part"
      and labour["monthly_share"] == [12.0, 10.0, 10.0], labour)
check("and the total is each plant's own, never one typed figure for all",
      Q["labour_cost"][-1]["staff_cost"] == 3200 + 1500 + 90, Q["labour_cost"][-1])
check("output per employee and revenue per employee", labour["output_per_employee_month"] == 19
      and labour["revenue_per_employee"] == 289, labour)
safe = Q["safety"][0]
check("safety: incidents without the near misses, near misses apart, LTIFR from the hours worked",
      (safe["total"], safe["near_misses"], safe["lost_time"], safe["ltifr"]) == (6, 9, 3, 50.0), safe)
pay = Q["wage_bill"][0]
check("the wage bill against the quarter before and a year before, overtime of every kind and its share",
      (pay["wage_bill"], pay["qoq"], pay["yoy"], pay["overtime"], pay["overtime_share"])
      == (3000, 11.1, 25.0, 360, 12.0), pay)
check("the totals row follows the plants", all(rows[-1]["plant"] is None for rows in (
    Q["head_count"], Q["recruitment"], Q["exits"], Q["churn"], Q["reconciliation"], Q["wage_bill"], Q["labour_cost"],
    Q["safety"], Q["people"])))
check("no year before: the comparisons say so rather than nought",
      R.quarter([JULY], None, [], None)["recruitment"][0]["last_year"] is None
      and R.quarter([JULY], None, [], None)["head_count"][0]["qoq"] is None)
line = R.summary([JULY, AUGUST, SEPTEMBER])
check("a quarter in one line: head count, attrition, churn, pay, cost per kg, safety",
      (line["head_count"], line["attrition"], line["hires"], line["exits"], line["wage_bill"], line["incidents"],
       line["near_misses"]) == (158, 4.8, 30, 23, 4590.0, 9, 9) and set(R.SUMMARY_FIELDS) <= set(line), line)
check("and for one plant", R.summary([JULY, AUGUST, SEPTEMBER], "Namanve")["head_count"] == 54)
check("a quarter with nothing is blank, not nought", R.summary([])["head_count"] is None)
check("monthly attrition: exits over the average of opening and closing",
      R.attrition(3, 100, 120) == 2.7 and R.attrition(1, 0, 0) is None)
check("a change as a percentage; none from nothing", R.change(120, 100) == 20.0 and R.change(5, 0) is None)
check("each earning's group from its name, until HR say otherwise",
      [R.component_group(name) for name in ("Basic Salary", "Overtime 1", "Special Overtime", "Per Meter 6",
                                            "Arrear", "OT 3", "LST", "")]
      == ["Basic", "Overtime", "Special Overtime", "Per Meter", "Arrears", "Overtime", "Other", "Other"])

# ── 2. The paper ──────────────────────────────────────────────────────
snapshot = fields("HR Monthly Snapshot")
check("a month's build: company, month, source, status, locked", {"company", "month_start", "source", "status",
                                                                   "locked", "built_on", "build"} <= set(snapshot)
      and snapshot["source"]["options"].split("\n") == ["System", "Imported"])
line = fields("Board Finance Line")
check("Finance's line: plant, month, revenue, output, staff cost",
      {"branch", "month_start", "revenue", "output_kg", "staff_cost"} <= set(line))
check("Finance's quarter: company, year, quarter, lines", {"company", "year", "quarter", "add_lines", "lines"}
      <= set(fields("Board Finance Figures")))
roles = {row["role"] for row in doctype("Board Finance Figures")["permissions"] if row.get("write")}
check("Finance type their own figures", {"Accounts Manager", "Accounts User", "Finance Officer", "HR Manager"} <= roles)
settings = fields("Board Report Settings")
check("the settings: hours in a day, the months built each night, the trend tolerance, the component groups, "
      "the past months built", {"hours_per_day", "refresh_months", "trend_tolerance", "component_groups",
                                "build_company", "build_from", "build_months"} <= set(settings)
      and fields("Board Component Group")["component_group"]["options"].split("\n") == list(R.GROUPS))
report = fields("HR Board Report")
DECK = read("hrms_addon", "hrms_addon", "board_deck.py")
named = set(re.findall(r'self\.doc\.get\("(\w+)"\)', DECK)) | set(re.findall(r"self\.doc\.(\w+)\b", DECK))
named -= {"get", "quarter", "year"}
for field in sorted(named):
    check("HR Board Report has %s, which the deck reads" % field, field in report)
check("the report is approved by the HR Manager", any(row["role"] == "HR Manager" and row.get("submit")
                                                     for row in doctype("HR Board Report")["permissions"])
      and doctype("HR Board Report").get("is_submittable") == 1)
check("the board reads the report", any(row["role"] == "Board Member" and row.get("read")
                                        for row in doctype("HR Board Report")["permissions"]))
safety = fields("Safety Incident")
for field in ("severity", "hazard", "off_site", "corrective_action", "capa_owner", "capa_due", "capa_status",
              "capa_closed_on", "sick_days"):
    check("Safety Incident has %s" % field, field in safety)
check("a safety incident's severities are the board's", safety["severity"]["options"].split("\n")[1:]
      == list(R.SEVERITIES))
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
for name in ("Employee Separation-custom_regrettable", "Employee Separation-custom_reason",
             "Employee Separation-custom_exit_type", "Employee-custom_is_foreign", "Employee-custom_pay_category",
             "Employee-custom_work_section", "Job Requisition-custom_reason_type"):
    check("the custom field the facts read ships: %s" % name, any(row["name"] == name for row in custom))
reasons = next(row for row in custom if row["name"] == "Job Requisition-custom_reason_type")["options"].split("\n")
check("a requisition's reasons are those the hire classes read", {"New Position", "Replacement", "New Addition"}
      <= set(reasons), reasons)

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "board_pack.py")
check("the figures from the facts: a GROUP BY over them for the eight quarters, the old plant rows gone",
      "board_facts.month_figures(company, first, last)" in body_of(GLUE, "quarter_figures")
      and "HR Snapshot Plant" not in GLUE and "rules.quarter(" in GLUE and "rules.summary(" in GLUE)
check("a month not built is missing, not nought", "board_facts.ready(company, window)" in GLUE
      and "if ready.get(day) else None" in GLUE)
check("the KPIs and the ratings from the figures, the insights drafted",
      all(needle in body_of(GLUE, "quarter_figures") for needle in ("kpi.board_kpis(", "kpi.area_ratings(",
                                                                    "kpi.insights(figures)")))
check("HR's own words kept: a draft only where they wrote nothing",
      'if doc.meta.has_field(field) and not (doc.get(field) or "").strip():' in body_of(GLUE, "_take")
      and 'if not (doc.get("regrettable_note") or "").strip()' in body_of(GLUE, "_take"))
check("HR's words checked against the figures", "kpi.text_flags(" in body_of(GLUE, "_take"))
check("a rating or a KPI HR set themselves needs their reason, the rest follow the figures",
      "kpi.override_errors(" in body_of(GLUE, "report_validate") and "kpi.settle(" in body_of(GLUE, "report_validate"))
check("approved, the figures taken afresh, refused while a month is missing, its months locked; cancelled, let go",
      "quarter_figures(" in body_of(GLUE, "report_before_submit") and 'figures["missing"]' in
      body_of(GLUE, "report_before_submit") and "board_facts.lock(" in body_of(GLUE, "report_on_submit")
      and "board_facts.unlock(" in body_of(GLUE, "report_on_cancel"))
check("each action as it stood when the board approved the pack", '"updates"' in body_of(GLUE, "_record_actions")
      and "_record_actions(doc)" in body_of(GLUE, "report_on_submit"))
check("the training value is the learning module's", "learning_value.value_by(" in body_of(GLUE, "_training_value"))
check("the sessions' attendance counted in one query, not one per session",
      "frappe.db.count(" not in body_of(GLUE, "_training_held"))
check("succession and talent risk from the talent records", all(name in body_of(GLUE, "_talent") for name in (
    "Succession Position", "Talent Placement", "Competency Assessment")))
check("every method asks the reader's permission first",
      all("doc.check_permission(" in body_of(GLUE, name) for name in ("add_finance_lines", "get_figures",
                                                                      "download_deck", "download_workbook",
                                                                      "report_actions", "build_from_settings")))
check("an approved report's figures stand", "The report is approved: its figures stand." in GLUE)
check("the deck has the company's logo, else keeps its place", "company_logo" in body_of(GLUE, "_logo")
      and "logo=_logo(doc.company)" in GLUE)

# ── 4. The deck ───────────────────────────────────────────────────────
tree = ast.parse(DECK)
deck_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_Deck")
methods = {node.name for node in deck_class.body if isinstance(node, ast.FunctionDef)}
for slide in ("cover", "contents", "summary", "scorecard", "trends", "head_count", "head_count_yoy", "recruitment",
              "exits", "churn", "comparative", "wage_bill", "components", "labour_cost", "metrics", "talent",
              "learning", "training_value", "safety", "memoriam", "achievements", "agenda", "outlook", "closing"):
    check("the deck has its %s slide, in the build" % slide,
          slide in methods and re.search(r"self\.%s[,)]" % slide, body_of_method(DECK, "build")))
check("traffic lights on the ratings and the KPIs", "self.dot(" in body_of_method(DECK, "summary")
      and "self.dot(" in body_of_method(DECK, "metrics") and "self.legend(" in DECK)
check("each change coloured by whether it is good news", "good_or_bad(" in body_of_method(DECK, "comparative")
      and "good_or_bad(" in body_of_method(DECK, "components") and "good_or_bad(" in body_of_method(DECK, "safety"))
check("the figures their deck left out drawn: the months over target, the permanent share, output per employee, "
      "near misses, days lost",
      'entry.get("over_target")' in body_of_method(DECK, "exits")
      and "permanent share" in body_of_method(DECK, "head_count")
      and "output_per_employee_month" in body_of_method(DECK, "labour_cost")
      and "near_misses" in body_of_method(DECK, "safety") and "days_lost" in body_of_method(DECK, "safety"))
check("eight quarters of trends, charted", "self.chart(" in body_of_method(DECK, "trends")
      and 'self.f.get("trends")' in body_of_method(DECK, "trends"))
check("each slide's definitions at its foot", "DEFINITIONS[foot]" in body_of_method(DECK, "slide")
      and DECK.count('foot="') >= 10)
check("a place kept for the logo", '"LOGO"' in body_of_method(DECK, "mark") and "add_picture(" in body_of_method(DECK, "mark"))
check("talent risk and succession from the figures", 'self.f.get("talent")' in body_of_method(DECK, "talent"))
check("the agenda and the priorities are the board actions", 'self.f.get("actions")' in body_of_method(DECK, "agenda")
      and 'self.f.get("actions")' in body_of_method(DECK, "outlook"))
check("the deck needs python-pptx, and says so", "bench pip install python-pptx" in DECK)
check("native charts and tables, so the board can still edit them", "add_chart(" in DECK and "add_table(" in DECK)
check("the deck is refused before there are figures", "Get the figures first" in DECK)

# ── 5. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("hooks: the component groups, the board's role and target seeded on migrate",
      '"hrms_addon.hrms_addon.board_pack.setup_on_migrate"' in HOOKS)
check("hooks: the regrettable flag shipped", '"Employee Separation-custom_regrettable"' in HOOKS)
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("HR Board Report", "HR Monthly Snapshot", "Board Finance Figures", "Board Report Settings",
             "Board Action", "Board KPI Target"):
    check("the HR Setup page's Board Pack card lists %s" % name, '("%s", "%s", DOCTYPE)' % (name, name) in NAV)
check("the Board Pack card and the sidebar open the dashboard", '("Board Dashboard", "board-dashboard", PAGE)' in NAV
      and '("Board Dashboard", "board-dashboard", PAGE, None, None)' in NAV)
for doctype_name, method in (("board_finance_figures", "board_pack.add_finance_lines"),
                             ("hr_monthly_snapshot", "board_facts.build"),
                             ("hr_board_report", "board_pack.get_figures"),
                             ("board_report_settings", "board_pack.build_from_settings")):
    script = read("hrms_addon", "hrms_addon", "doctype", doctype_name, doctype_name + ".js")
    check("%s's button asks %s" % (doctype_name, method), '"hrms_addon.hrms_addon.%s"' % method in script)
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
