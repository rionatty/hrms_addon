"""Verify the HR board pack's measures (18 Nov 2026), without a bench:

    python scripts/verify_board_kpis.py

Targets with amber and red bands, the traffic lights, the seven board KPIs and the eight health ratings worked out
from the figures with HR's own and their reason, the insight drafted for each slide, HR's words checked against the
figures, the board actions carried quarter to quarter, the Board Dashboard and the reports each figure opens.

  1  the rules: targets, lights, KPIs, ratings, insights, the words checked, actions, hiring measures
  2  the paper: the targets', actions' and ratings' fields and options are the rules'
  3  the dashboard and the reports: who may open them, money only for those who see pay, cached, held to a user's
     plants, every figure opening its records
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


K = load("board_kpi_rules")
P = load("board_pack_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
TARGETS = [
    {"metric": "Monthly Attrition", "branch": None, "from_date": "2025-01-01", "target": 5, "direction": K.LOWER,
     "amber_band": 0, "red_band": 1},
    {"metric": "Monthly Attrition", "branch": None, "from_date": "2026-07-01", "target": 4, "direction": K.LOWER,
     "amber_band": 0.5, "red_band": 1.5},
    {"metric": "Monthly Attrition", "branch": "Matugga", "from_date": "2026-01-01", "target": 6, "direction": K.LOWER},
    {"metric": "Revenue per Employee", "branch": None, "from_date": "2026-01-01", "to_date": "2026-06-30",
     "target": 30e6, "direction": K.HIGHER, "amber_band": 1e6, "red_band": 4e6},
]
found = K.target_for(TARGETS, "Monthly Attrition", None, "2026-07-01", "2026-09-30")
check("the target that stands: the latest start for the company", found and found["target"] == 4, found)
check("a plant's own target before the company's", K.target_for(TARGETS, "Monthly Attrition", "Matugga", "2026-07-01",
                                                                 "2026-09-30")["target"] == 6)
check("a target that ended before the period does not stand",
      K.target_for(TARGETS, "Revenue per Employee", None, "2026-07-01", "2026-09-30") is None
      and K.target_for(TARGETS, "Revenue per Employee", None, "2026-04-01", "2026-06-30")["target"] == 30e6)
lower = TARGETS[1]
check("lower is better: on target, within the amber band still On Track, to the red band Watch, past it Action Needed",
      [K.light(value, lower) for value in (3.9, 4.0, 4.5, 5.2, 5.5, 5.6, None)]
      == ["On Track", "On Track", "On Track", "Watch", "Watch", "Action Needed", None])
higher = TARGETS[3]
check("higher is better, the same bands the other way",
      [K.light(value, higher) for value in (31e6, 29.5e6, 27e6, 25.5e6)] == ["On Track", "On Track", "Watch",
                                                                            "Action Needed"])
check("with no red band, past the amber band is Action Needed",
      K.light(5.5, {"target": 5, "direction": K.LOWER, "amber_band": 0.2}) == "Action Needed")
check("no target, against the period before: no worse On Track, a little worse On Track, worse Watch, much worse "
      "Action Needed; from nought Watch",
      [K.trend_light(now, before, K.LOWER) for now, before in ((3, 4), (4.3, 4), (4.6, 4), (5, 4), (2, 0), (None, 4))]
      == ["On Track", "On Track", "Watch", "Action Needed", "Watch", None])
check("the worst light of several", K.worst(["On Track", None, "Watch"]) == "Watch" and K.worst([None]) is None)
errors = K.target_errors({"metric": "Nonsense", "from_date": "2026-07-01", "to_date": "2026-06-01", "amber_band": 2,
                          "red_band": 1})
check("a target refused: no such metric, ending before it starts, a red band inside the amber",
      len(errors) == 3, errors)
NOW = {"attrition": 3.6, "casual_churn": 27.8, "permanent_churn": 3.6, "permanent_share": 73.5, "regrettable": 6,
       "exits": 220, "staff_cost_share": 8.9, "overtime_share": 10.7, "cost_per_kg": 586, "revenue_per_employee": 38.7e6,
       "wage_per_employee": 2.46e6, "revenue_to_wage": 15.7, "output_per_employee": 1500, "ltifr": 2.1,
       "incidents": 16, "training_per_employee": 4.2, "absence_rate": 3.0, "clock_share": 81.5, "time_to_fill": 32,
       "retention_90": 88.0, "retention_cohort": 40, "succession_coverage": 40.0, "critical_roles": 10,
       "covered_roles": 4, "ready_now": 5, "top_talent_at_risk": 2, "skills_gap": 22.0, "skills_assessed": 150,
       "data_issues": 3, "capa_overdue": 1}
BEFORE = dict(NOW, attrition=3.2, regrettable=3, revenue_per_employee=35.7e6, clock_share=70.0)
YEAR = dict(NOW, attrition=2.8, casual_churn=16.3, ltifr=3.0, incidents=23)
kpis = K.board_kpis(NOW, BEFORE, YEAR, TARGETS, "2026-07-01", "2026-09-30", ["Kawempe"],
                    {"Kawempe": {"output_per_employee": 1936}})
check("the seven KPIs, in the board's order, each read by its metric",
      [(row["number"], row["name"], row["metric"]) for row in kpis] == [tuple(row) for row in K.BOARD_KPIS])
check("productivity read from revenue per employee and each plant's output",
      "38.7M" in kpis[0]["reading"] and "Kawempe 1,936 kg" in kpis[0]["reading"], kpis[0]["reading"])
check("regrettable attrition worse than a year before is lit, and what it tells drafted",
      kpis[1]["light"] in K.LIGHTS and kpis[1]["tells"], kpis[1])
building = K.board_kpis({}, {}, {}, [], "2026-07-01", "2026-09-30")
check("a KPI with nothing to read it from is Building", all(row["light"] == "Building" for row in building))
ratings = K.area_ratings(NOW, BEFORE, YEAR, TARGETS, "2026-07-01", "2026-09-30")
check("the eight areas, in the board's order", [row["area"] for row in ratings] == list(K.AREAS) == list(P.AREAS))
retention = next(row for row in ratings if row["area"] == "Retention & Turnover")
check("an area is as good as its worst metric: casual churn up 70% on a year before is Action Needed",
      retention["rating"] == "Action Needed" and "Casual Churn" in retention["basis"], retention)
safety = next(row for row in ratings if row["area"] == "Safety (EHS)")
check("safety better than a year before is On Track", safety["rating"] == "On Track", safety)
check("an override needs its reason", K.override_errors({"override": 1, "override_reason": " "})
      and not K.override_errors({"override": 1, "override_reason": "Board asked"}) and not K.override_errors({}))


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)


row = {"computed_rating": "Watch", "rating": "On Track", "override": 0}
check("not overridden, the rating is the figures'", K.settle(row, "computed_rating", "rating")["rating"] == "Watch")
row = {"computed_rating": "Watch", "rating": "On Track", "override": 1}
check("overridden, HR's stands", K.settle(row, "computed_rating", "rating")["rating"] == "On Track")
obj = type("Child", (), {"get": lambda self, key: getattr(self, key, None)})()
obj.computed_status, obj.status, obj.override = "Action Needed", "", 0
K.settle(obj, "computed_status", "status")
check("a child row as Frappe hands it is settled too", obj.status == "Action Needed")
check("a metric shown as the board reads it",
      [K.show(metric, value) for metric, value in (("Monthly Attrition", 3.6), ("Revenue per Employee", 38.7e6),
                                                   ("Labour Cost per kg", 586), ("LTIFR", 2.1), ("Incidents", 16),
                                                   ("Incidents", None))]
      == ["3.6%", "UGX 38.7M", "UGX 586", "2.1", "16", "–"])

# the insights and the words checked, from a quarter worked out by the pack's own rules


def month(closing, opening, exits, hires, wage, casual=0, revenue=0, staff=0, incidents=0, near=0):
    return {"closing": closing, "opening": opening, "exits": exits, "hires": hires, "replacements": hires,
            "casual": casual, "casual_opening": casual, "exits_casual": 0, "wage_bill": wage, "basic": wage,
            "overtime_all": wage / 10, "overtime": wage / 10, "revenue": revenue, "staff_cost": staff,
            "incidents": incidents, "near_misses": near, "male": closing}


NOW_MONTHS = [{"Kawempe": month(100, 98, 2, 4, 1e8, revenue=1e9), "Matugga": month(50, 45, 1, 6, 5e7, revenue=5e8)},
              {"Kawempe": month(101, 100, 3, 4, 1e8, revenue=1e9), "Matugga": month(55, 50, 4, 9, 5e7, revenue=5e8)},
              {"Kawempe": month(102, 101, 2, 3, 1e8, revenue=1e9), "Matugga": month(60, 55, 1, 6, 5e7, revenue=5e8)}]
BEFORE_MONTH = {"Kawempe": month(98, 97, 1, 2, 9e7), "Matugga": month(45, 44, 1, 2, 4e7)}
LAST = [{"Kawempe": month(90, 90, 1, 1, 8e7, incidents=2)} for _ in range(3)]
PREVIOUS = [{"Kawempe": month(97, 96, 1, 2, 9e7, revenue=9e8)} for _ in range(3)]
Q = P.quarter(NOW_MONTHS, BEFORE_MONTH, LAST, None, 5.0, PREVIOUS)
drafts = K.insights(Q)
check("each slide's insight drafted from the figures",
      {"head_count_insight", "recruitment_insight", "exits_insight", "churn_insight", "wage_insight",
       "overtime_insight", "labour_insight", "ehs_insight", "yoy_insight", "headline"} <= set(drafts), sorted(drafts))
check("the head count's: risen 19 to 162, led by Matugga", drafts["head_count_insight"].startswith(
    "Head count rose 19") and "to 162" in drafts["head_count_insight"] and "led by Matugga (+15)"
      in drafts["head_count_insight"], drafts["head_count_insight"])
check("the exits': the months against the target, the plant over it named",
      "against a target of 5%" in drafts["exits_insight"] and "Matugga" in drafts["exits_insight"],
      drafts["exits_insight"])
check("the churn's: the movements reconcile", "reconcile to the head count" in drafts["churn_insight"],
      drafts["churn_insight"])
september = Q["exits"][-1]["months"][-1]["rate"]
flags = K.text_flags({"head_count_insight": "Head count fell sharply this quarter.",
                      "exits_insight": "Attrition was %s%% in September." % september,
                      "wage_insight": "The wage bill held at 12.34% of revenue."}, Q,
                     {"head_count_insight": "Head Count", "exits_insight": "Exits", "wage_insight": "Wage Bill"})
check("HR's words against the figures: a fall that was a rise, a bill said to hold that moved, a figure the slides "
      "do not print; a true figure quoted is not flagged",
      [field for field, _issue in flags] == ["Head Count", "Wage Bill", "Wage Bill"]
      and "head count fell; the figures show it rose (+19)" in flags[0][1] and "wage bill held" in flags[1][1]
      and "12.34%" in flags[2][1], flags)
check("words that agree with the figures are not flagged", K.text_flags({"head_count_insight": "Head count rose."}, Q)
      == [])

check("an action is due on its quarter's last day", K.due_date(2026, "Q4") == D(2026, 12, 31)
      and K.due_date(2026, "Q1") == D(2026, 3, 31) and K.due_date(None, "Q1") is None)
check("an action refused: no such status, progress past 100, due before it was raised",
      len(K.action_errors({"status": "Maybe", "progress": 120, "raised_year": 2026, "raised_quarter": "Q3",
                           "due_year": 2026, "due_quarter": "Q2"})) == 3)
ACTIONS = [{"imperative": "A", "status": "On Track", "due_date": "2026-12-31"},
           {"imperative": "B", "status": "Done", "done_on": "2026-08-10", "due_date": "2026-09-30"},
           {"imperative": "C", "status": "Done", "done_on": "2026-03-10", "due_date": "2026-03-31"},
           {"imperative": "D", "status": "At Risk", "due_date": "2026-09-30"},
           {"imperative": "E", "status": "Dropped", "done_on": "2026-07-02", "due_date": "2026-09-30"}]
check("a quarter's pack carries every open action and those closed in it, the ones at risk first",
      [row["imperative"] for row in K.actions_for(ACTIONS, 2026, "Q3")] == ["D", "A", "B", "E"])
check("an open action past its due date is overdue", K.overdue(ACTIONS[3], "2026-10-01")
      and not K.overdue(ACTIONS[1], "2026-10-01"))
retention, cohort = K.retention_90({"E1": "2026-04-10", "E2": "2026-05-01", "E3": "2026-06-20", "E4": "2026-09-01"},
                                   {"E2": "2026-06-01", "E3": "2026-07-01"}, "2026-07-01", "2026-09-30")
check("90-day retention: of the hires whose 90th day fell in the quarter, those still there on it",
      (retention, cohort) == (33.3, 3), (retention, cohort))
fill = K.fill_days([{"requested": "2026-06-01", "advertised": "2026-06-05", "offered": "2026-06-20",
                     "joined": "2026-07-01"},
                    {"requested": "2026-06-10", "advertised": None, "offered": None, "joined": "2026-07-20"}])
check("time to fill: requisition to joining and each step", (fill["total"], fill["to_advert"], fill["to_offer"],
                                                             fill["to_join"], fill["hires"]) == (35, 4, 15, 11, 2), fill)

# ── 2. The paper ──────────────────────────────────────────────────────
check("a target's metric is one of the rules'", options("Board KPI Target", "metric") == list(K.METRIC_NAMES))
check("a target's direction, amber and red bands", options("Board KPI Target", "direction") == [K.LOWER, K.HIGHER]
      and {"amber_band", "red_band", "branch", "from_date", "to_date", "target", "unit"} <= set(fields("Board KPI Target")))
check("an action: imperative, lever, owner, due quarter, status, progress, the quarters it went through",
      {"imperative", "lever", "action_owner", "due_year", "due_quarter", "due_date", "status", "progress", "milestone",
       "progress_note", "updates", "board_report"} <= set(fields("Board Action"))
      and options("Board Action", "status") == list(K.ACTION_STATUSES)
      and fields("Board Action")["due_date"].get("read_only") == 1
      and {"year", "quarter", "status", "progress", "note"} <= set(fields("Board Action Update")))
check("a rating: worked out, final, set by HR with the reason",
      {"computed_rating", "rating", "override", "override_reason", "basis", "note"} <= set(fields("Board Health Rating"))
      and options("Board Health Rating", "rating") == list(K.LIGHTS)
      and fields("Board Health Rating")["override_reason"].get("mandatory_depends_on"))
check("a KPI line: its value, target, light from the figures, HR's own with the reason",
      {"measure", "value", "target", "unit", "computed_status", "status", "override", "override_reason", "reading",
       "tells"} <= set(fields("Board Metric Line"))
      and options("Board Metric Line", "status") == list(K.LIGHTS) + ["Building"])
report = fields("HR Board Report")
check("the report keeps the words against the figures, carries its actions, and no typed agenda",
      report["text_flags"]["options"] == "Board Text Flag" and "actions_html" in report and "agenda" not in report
      and "priorities" not in report and "ehs_insight" in report)

# ── 3. The dashboard and the reports ──────────────────────────────────
DASH = read("hrms_addon", "hrms_addon", "board_dashboard.py")
page = json.load(open(os.path.join(APP, "page", "board_dashboard", "board_dashboard.json"), encoding="utf-8"))
roles = re.search(r"^ROLES = \((.*?)\)", DASH, re.S | re.M).group(1)
check("the page and its call are for the same roles: HR, the GM, the ED, the board, management",
      {row["role"] for row in page["roles"]} == set(re.findall(r'"([^"]+)"', roles))
      and {"Board Member", "General Manager", "Executive Director", "HR Manager"} <= {row["role"] for row in page["roles"]})
check("one call, cached five minutes per user and choice", "frappe.cache.get_value(key, user=user)" in DASH
      and "expires_in_sec=CACHE_SECONDS" in DASH and "CACHE_SECONDS = 300" in DASH)
check("the call asks who is looking first", "_reach()" in body_of(DASH, "overview")
      and "frappe.PermissionError" in body_of(DASH, "_reach"))
check("money only for those who see pay", "kpi.MONEY_METRICS" in body_of(DASH, "figures")
      and "if not money and metric in kpi.MONEY_METRICS" in DASH)
check("a user held to plants sees only theirs", "User Permission" in body_of(DASH, "_held_plants")
      and "branch not in held" in body_of(DASH, "overview"))
check("the figures from one GROUP BY over the facts for the eight quarters, each quarter by the pack's own rules",
      "board_facts.month_figures(company, first, last)" in DASH and "rules.summary(" in DASH
      and "rules.quarters_back(year, quarter, 8)" in DASH)
check("a figure opens its report only for one who may open it", "is_permitted()" in body_of(DASH, "_permitted")
      and "_permitted(report)" in body_of(DASH, "_route"))
PAGE_JS = read("hrms_addon", "hrms_addon", "page", "board_dashboard", "board_dashboard.js")
check("the page: quarter and plant chosen, cards with their light and eight quarters, the scorecard, data quality, "
      "every value escaped", all(needle in PAGE_JS for needle in (
          'fieldname: "quarter"', 'fieldname: "branch"', "sparkline(", "scorecard(", "quality(",
          "frappe.utils.escape_html", "board_dashboard.overview")))
REPORTS = read("hrms_addon", "hrms_addon", "board_reports.py")
for name, function in (("Board Head Count", "head_count"), ("Board Leavers", "leavers"), ("Board Hires", "hires"),
                       ("Board Incidents", "incidents"), ("Board Pay by Component", "pay"),
                       ("Board Data Quality", "data_quality")):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    code = read("hrms_addon", "hrms_addon", "report", folder, folder + ".py")
    check("%s: a script report on board_reports.%s" % (name, function),
          spec["report_type"] == "Script Report" and "return board_reports.%s(filters)" % function in code
          and "\ndef %s(" % function in REPORTS)
    ref = doctype(spec["ref_doctype"])
    readers = {row["role"] for row in ref["permissions"] if row.get("report")}
    missing = [row["role"] for row in spec["roles"] if row["role"] not in readers | {"Management Viewer", "Auditor"}]
    check("%s: every role it is for may report on %s" % (name, spec["ref_doctype"]), not missing, missing)
check("the lists read through the user's permissions", "frappe.get_list(" in body_of(REPORTS, "_movements")
      and "frappe.get_list(" in body_of(REPORTS, "data_quality"))
check("a cut chosen from a fixed list before it reaches the SQL", "PAY_CUTS.get(" in body_of(REPORTS, "pay")
      and "CUT_OF.get(" in body_of(REPORTS, "head_count"))
check("those who may not open the incidents see them counted", 'frappe.has_permission("Safety Incident", "read")'
      in body_of(REPORTS, "incidents") and "`tabHR Safety Fact`" in body_of(REPORTS, "incidents"))
RULES = read("hrms_addon", "hrms_addon", "dashboards_rules.py")
check("the desk home tells of a month whose build failed and of an action past its quarter",
      '"board_months_failed"' in RULES and '"board_actions_overdue"' in RULES)

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_board_kpis: OK")
