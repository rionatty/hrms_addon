"""Verify budget lines and training providers (the LMS rebuild, 18 Nov 2026), without a bench:

    python scripts/verify_learning_providers.py

  1  the rules: a session's rating of its provider, a provider's figures, the ranking on the five factors, a
     falling trend, expiries; budget lines, the budget against actual and forecast, the calendar's check
  2  the paper: Training Provider and its tables, the budget's lines, the calendar's check, the session's provider
  3  the glue and the wiring
"""
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


def fields(name):
    folder = name.lower().replace(" ", "_")
    spec = json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))
    return {field["fieldname"]: field for field in spec["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


P = load("learning_providers_rules")
V = load("learning_value_rules")
L = load("learning_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
ROW = P.rating_row({"name": "EV-1", "training_program": "Forklift", "day": "2026-11-02", "trainees": 4, "cost": 400000,
                    "evaluation_score": 82},
                   [{"item": "The trainer was knowledgeable", "rating": "Excellent"},
                    {"item": "Training methodology by the trainer", "rating": "Good"},
                    {"item": "Venue, refreshments", "rating": "Below Average"}],
                   [{"effective": "Effective"}, {"effective": "Effective"}, {"effective": "Not Effective"}, {"effective": ""}],
                   [{"status": "Done", "score": 80}, {"status": "Pending"}],
                   [{"result": "Improved"}, {"result": "Worse"}])
check("a session's rating: cost per trainee, the trainer items as quality, the evaluation as feedback, the pass rate, "
      "application and KPIs as impact",
      (ROW["cost_per_trainee"], ROW["quality"], ROW["feedback"], ROW["learning"], ROW["impact"])
      == (100000.0, 80.0, 82.0, 66.7, 65.0), ROW)
FIG = P.provider_figures([dict(ROW), dict(ROW, trainees=1, cost=100000, quality=None, learning=100)])
check("a provider's figures over its sessions", (FIG["sessions"], FIG["trainees"], FIG["spend"], FIG["cost_per_trainee"],
                                                 FIG["quality"], FIG["learning"]) == (2, 5, 500000.0, 100000.0, 80.0, 83.3),
      FIG)
RANKED = P.rank({"A": {"cost_per_trainee": 100000, "quality": 80, "feedback": 80, "learning": 80, "impact": 80},
                 "B": {"cost_per_trainee": 50000, "quality": 60, "feedback": 60, "learning": None, "impact": None},
                 "C": {"cost_per_trainee": None}},
                {"cost": 20, "quality": 20, "feedback": 20, "learning": 20, "impact": 20})
check("ranked on the five factors, the cheapest 100 on cost, over the factors with data; none last unranked",
      [(row["provider"], row["cost_score"], row["score"], row["rank"]) for row in RANKED]
      == [("A", 50.0, 74.0, 1), ("B", 100.0, 73.3, 2), ("C", None, None, 0)], RANKED)
check("the weights decide: cost alone puts the cheapest first", P.rank(
    {"A": {"cost_per_trainee": 100000, "quality": 90}, "B": {"cost_per_trainee": 50000, "quality": 10}},
    {"cost": 1, "quality": 0})[0]["provider"] == "B")
TREND = [{"session_date": "2026-0%d-01" % month, "feedback": value} for month, value in ((1, 90), (2, 80), (3, 60),
                                                                                         (4, 60), (5, 60))]
check("a provider's last three sessions against the ones before: falling", P.trend(TREND) == -25.0
      and P.trend(TREND[:3]) is None)
check("an accreditation or a contract: valid, expiring within 60 days, expired",
      [P.expiry_status(day, "2026-11-18") for day in ("2027-03-01", "2026-12-20", "2026-11-17", None)]
      == ["Valid", "Expiring", "Expired", "Valid"])
check("a provider refuses an accreditation or a contract ending before it starts",
      P.provider_errors({"accreditations": [{"valid_from": "2026-05-01", "expiry_date": "2026-04-01"}]})
      and P.provider_errors({"contracts": [{"start_date": "2026-05-01", "end_date": "2026-04-01"}]}))
check("the trainer's items are on the evaluation form", set(P.TRAINER_ITEMS) <= set(load("training_rules").EVALUATION_ITEMS))
check("the five factors are the settings' own", list(P.FACTORS) == [key for key, _label in L.PROVIDER_FACTORS])
check("a budget's lines: their total, an amount on every line, a month of the twelve",
      V.lines_total([{"amount": 100}, {"amount": 250.5}]) == 350.5
      and V.line_errors([{"amount": 0}]) == ["Every budget line needs an amount."]
      and V.line_errors([{"amount": 5, "month": "Smarch"}]) and not V.line_errors([{"amount": 5, "month": "May"}]))
check("a date's month", V.month_of("2026-03-15 08:00:00") == "March" and V.month_of(None) is None)
LINES = [{"branch": "K", "month": "January", "amount": 100}, {"branch": "K", "month": "June", "amount": 200},
         {"branch": "N", "month": "June", "amount": 50}]
ACTUAL = [{"branch": "K", "month": "January", "amount": 120}, {"branch": "N", "month": "March", "amount": 30}]
COMMITTED = [{"branch": "K", "month": "June", "amount": 260}]
BVA = {row["group"]: row for row in V.budget_vs_actual(LINES, ACTUAL, COMMITTED, "branch", 5)}
check("budget against actual and forecast: a closed month at what it cost, an open one at the larger of its budget "
      "and what is spent and committed in it",
      (BVA["K"]["budget"], BVA["K"]["actual"], BVA["K"]["committed"], BVA["K"]["forecast"], BVA["K"]["remaining"],
       BVA["K"]["utilisation"], BVA["K"]["variance"]) == (300.0, 120.0, 260.0, 380.0, -80.0, 126.7, -80.0)
      and (BVA["N"]["forecast"], BVA["N"]["utilisation"]) == (80.0, 60.0), BVA)
check("grouped as asked", [row["group"] for row in V.budget_vs_actual(LINES, [], [], "month", 1)] == ["June", "January"])
check("the calendar's check: over by how much, or not", V.calendar_check(500, 300) == (True, 200.0)
      and V.calendar_check(100, 300) == (False, 0.0) and V.calendar_check(100, None) == (False, 0.0))

# ── 2. The paper ──────────────────────────────────────────────────────
provider = fields("Training Provider")
for field in ("provider_name", "provider_type", "supplier", "status", "phone", "email", "expertise", "contacts",
              "trainers", "accreditations", "contracts", "ratings", "provider_rank", "score", "trend", "cost_score",
              "quality_score", "feedback_score", "learning_score", "impact_score", "sessions", "trainees", "spend",
              "cost_per_trainee"):
    check("Training Provider has %s" % field, field in provider)
check("its expertise picks from the training categories", provider["expertise"]["fieldtype"] == "Table MultiSelect")
for child, needed in (("Training Provider Accreditation", {"accreditation", "issuing_body", "expiry_date", "status",
                                                           "attachment", "alerted_for"}),
                      ("Training Provider Contract", {"contract_no", "start_date", "end_date", "value", "status",
                                                      "alerted_for"}),
                      ("Training Provider Trainer", {"trainer_name", "speciality", "email"}),
                      ("Training Provider Contact", {"contact_name", "role", "phone", "email"}),
                      ("Training Provider Rating", {"training_event", "session_date", "trainees", "cost",
                                                    "cost_per_trainee", "quality", "feedback", "learning", "impact"})):
    check("%s has %s" % (child, ", ".join(sorted(needed))), needed <= set(fields(child)))
line = fields("Training Budget Line")
check("a budget line: plant, department, cost centre, category, programme, provider, employee, month, cost type, amount",
      {"branch", "department", "cost_center", "training_category", "training_program", "provider", "employee", "month",
       "cost_type", "amount"} <= set(line)
      and [value for value in line["month"]["options"].split("\n") if value] == list(V.MONTHS)
      and [value for value in line["cost_type"]["options"].split("\n") if value] == list(V.COST_TYPES))
check("the budget takes its lines", fields("Training Budget")["lines"]["options"] == "Training Budget Line")
check("the calendar keeps its budget check", {"training_budget", "budget_remaining", "budget_note"}
      <= set(fields("Training Calendar")))
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
HOOKS = read("hrms_addon", "hooks.py")
check("the session has its provider, shipped", any(row["name"] == "Training Event-custom_provider"
                                                   and row["options"] == "Training Provider" for row in custom)
      and '"Training Event-custom_provider"' in HOOKS)

# ── 3. The glue and the wiring ────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_providers.py")
VALUE = read("hrms_addon", "hrms_addon", "learning_value.py")
check("no SQL of their own", "frappe.db.sql" not in GLUE and "frappe.db.sql" not in VALUE)
check("a session's rating made or brought up to date on its provider, none for a session not held",
      "rules.rating_row(" in GLUE and 'event.event_status == "Cancelled"' in GLUE)
check("rated again in the background as its evaluations and results change, once per session",
      'job_id="rate_training_event::%s" % training_event' in GLUE and "deduplicate=True" in GLUE)
check("every provider ranked with the settings' weights", "rules.rank(figures_by_provider(), settings_weights())" in GLUE)
check("an expiry told once to the HR Managers, in one notice", '"alerted_for", value' in GLUE
      and "enqueue_create_notification(users" in GLUE)
check("the budget is its lines where it has any", "doc.amount = rules.lines_total(lines)" in VALUE)
check("the calendar said over its budget as it goes for approval", "def calendar_budget(doc" in VALUE
      and 'title=_("Over the Training Budget")' in VALUE)
check("budget against actual reads each kind once, the invited counted by the database",
      'group_by="parent"' in VALUE and "rules.budget_vs_actual(plan, actuals, commitments, key, this_month)" in VALUE)
for needle in ('"hrms_addon.hrms_addon.learning_providers.event_validate"',
               '"hrms_addon.hrms_addon.learning_providers.feedback_changed"',
               '"hrms_addon.hrms_addon.learning_providers.result_changed"',
               '"hrms_addon.hrms_addon.learning_providers.daily"',
               '"hrms_addon.hrms_addon.learning_value.calendar_budget"'):
    check("hooks: %s" % needle, needle in HOOKS)
check("hooks: the result rates the provider when submitted, changed and cancelled",
      HOOKS.count('"hrms_addon.hrms_addon.learning_providers.result_changed"') == 3)
REPORT = read("hrms_addon", "hrms_addon", "report", "provider_performance", "provider_performance.py")
check("Provider Performance reads the providers' ratings and ranks them", "learning_providers.figures_by_provider("
      in REPORT and "rules.rank(" in REPORT and 'frappe.get_list("Training Provider"' in REPORT)
spec = json.load(open(os.path.join(APP, "report", "training_budget_vs_actual", "training_budget_vs_actual.json"),
                      encoding="utf-8"))
check("Training Budget vs Actual is a script report on the budget", spec["ref_doctype"] == "Training Budget"
      and spec["report_type"] == "Script Report")
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Training Provider", "Training Budget vs Actual"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)
check("the provider is whitelisted nowhere: its figures are the job's", not re.search(r"@frappe\.whitelist", GLUE))

if fail:
    print("FAILURES:")
    for line_ in fail:
        print("  -", line_)
    sys.exit(1)
print("verify_learning_providers: OK")
