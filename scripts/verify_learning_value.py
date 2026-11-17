"""Verify LMS phase 5, value (17 Nov 2026), without a bench:

    python scripts/verify_learning_value.py

The blueprint's section 4.10: each session's costs and the trainees' time, a year's training budget for a company,
a plant or a department with what is spent, committed and left, HR and Finance told once at its alert level, each
programme's ROI or benefit score, the providers ranked, and each plant's learning health.

  1  the rules
  2  the paper: the cost lines, the session's cost fields, the budget, the reports
  3  the glue
  4  wiring
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


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def options(name, field):
    return [option for option in (fields(name)[field].get("options") or "").split("\n") if option]


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %r" % (detail,)) if detail != "" else ""))


R = load("learning_value_rules")
T = load("training_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
check("costs: the lines added up", R.direct_cost([{"amount": 150000}, {"amount": 50000.5}, {}]) == 200000.5)
check("costs: a person-hour from the section's person-shift", R.hourly_rate(24000, 12) == 2000.0
      and R.hourly_rate(None, 12) == 0.0 and R.hourly_rate(24000, 0) == 0.0)
check("costs: the trainees' time at their rates", R.time_cost([2000, 1500, 0], 4) == 14000.0)
check("costs: the session's cost and per trainee", R.session_cost([{"amount": 200000}], [2000, 2000], 4, 2)
      == {"direct": 200000.0, "time": 16000.0, "total": 216000.0, "per_trainee": 108000.0}
      and R.session_cost([], [], 4, 0)["per_trainee"] == 0.0)
check("committed: the costs typed, else the programme's cost per person for each invited",
      R.planned_cost([{"amount": 90000}], 50000, 10) == 90000.0 and R.planned_cost([], 50000, 10) == 500000.0)
BUDGET = {"company": "LPT", "year": 2026, "branch": "Kawempe", "department": None}
check("a session counts against the budgets of its company, year, plant and department",
      R.in_scope(BUDGET, {"company": "LPT", "year": 2026, "branch": "Kawempe", "department": "PE"})
      and not R.in_scope(BUDGET, {"company": "LPT", "year": 2026, "branch": "Namanve"})
      and not R.in_scope(BUDGET, {"company": "LPT", "year": 2025, "branch": "Kawempe"})
      and not R.in_scope(BUDGET, {"company": "Other", "year": 2026, "branch": "Kawempe"})
      and R.in_scope({"company": "LPT", "year": 2026}, {"company": "LPT", "year": 2026, "branch": "Namanve"})
      and not R.in_scope(dict(BUDGET, department="QC"), {"company": "LPT", "year": 2026, "branch": "Kawempe",
                                                        "department": "PE"}))
check("budget: spent, committed, left and used", R.budget_state(1000000, 600000, 150000, 80) == {
    "spent": 600000.0, "committed": 150000.0, "remaining": 250000.0, "utilisation": 75.0, "status": R.WITHIN})
check("budget: near the limit at its alert level, over past the whole",
      R.budget_state(1000000, 800000, 0, 80)["status"] == R.NEAR and R.budget_state(1000000, 900000, 200000, 80)[
          "status"] == R.OVER and R.budget_state(1000000, 1000000, 0, 80)["status"] == R.NEAR)
check("budget: told once on reaching it, the mark off when it falls back",
      R.newly_alerting(0, R.NEAR) == (True, 1) and R.newly_alerting(1, R.OVER) == (False, 1)
      and R.newly_alerting(1, R.WITHIN) == (False, 0) and R.newly_alerting(0, R.WITHIN) == (False, 0))
check("ROI: the benefit over the cost", R.roi(300000, 200000) == 50.0 and R.roi(0, 200000) is None
      and R.roi(100000, 0) is None and R.roi(100000, 200000) == -50.0)
check("benefit score: 20, 20, 30, 30, re-weighted over the levels with data",
      R.benefit_score({"reaction": 80, "pass_rate": 90, "application": 70, "kpi_share": 50}) == 70.0
      and R.benefit_score({"reaction": 80, "pass_rate": None, "application": 60, "kpi_share": None}) == 68.0
      and R.benefit_score({}) is None)
check("KPIs improved as a share", R.kpi_share(4, 3) == 75.0 and R.kpi_share(0, 0) is None)
check("providers: the best score first, then the cheaper, those with no score last", [
    row["provider"] for row in R.rank_providers([
        {"provider": "A", "score": 70, "per_trainee": 50000}, {"provider": "B", "score": None, "per_trainee": 1},
        {"provider": "C", "score": 70, "per_trainee": 30000}, {"provider": "D", "score": 90, "per_trainee": 90000}])]
      == ["D", "C", "A", "B"])
check("health: the parts with data, equally weighed, against the matrix bands",
      R.health({"compliance": 90, "certificates": 80, "attendance": None, "reaction": 100}) == (90.0, "Healthy")
      and R.health({"compliance": 70}) == (70.0, "Watch") and R.health({"compliance": 50}) == (50.0, "At Risk")
      and R.health({"compliance": 85}) == (85.0, "Healthy") and R.health({"compliance": 65}) == (65.0, "Watch")
      and R.health({}) == (None, "No Data"))

# ── 2. The paper ──────────────────────────────────────────────────────
COST = fields("Training Event Cost")
check("paper: a cost line's kinds are the rules', and it may be typed after the session",
      options("Training Event Cost", "cost_type") == list(R.COST_TYPES)
      and all(COST[name].get("allow_on_submit") for name in COST))
CUSTOM = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
check("paper: the session's cost fields, worked out, kept after submit", all(
    CUSTOM["Training Event-custom_" + name].get("read_only") and CUSTOM["Training Event-custom_" + name].get(
        "allow_on_submit") for name in ("direct_cost", "time_cost", "total_cost", "cost_per_trainee"))
      and CUSTOM["Training Event-custom_costs"]["options"] == "Training Event Cost"
      and CUSTOM["Training Event-custom_costs"].get("allow_on_submit"))
B = fields("Training Budget")
check("paper: the budget's statuses are the rules'", options("Training Budget", "status") == list(R.BUDGET_STATUSES))
check("paper: the budget's worked-out fields are read only", all(B[name].get("read_only") for name in (
    "spent", "committed", "remaining", "utilisation", "status", "alerted")))
check("paper: Finance may keep the budget", {"Finance Officer", "Accounts Manager"} <= {
    row["role"] for row in doctype("Training Budget")["permissions"] if row.get("write")})
REPORTERS = {"System Manager", "HR Manager", "HR User"} | {
    role for role, ptypes in T.PERMISSIONS["Training Event"].items() if "report" in ptypes}
for folder in ("training_roi", "provider_performance", "learning_health"):
    spec = json.load(open(os.path.join(APP, "report", folder, folder + ".json"), encoding="utf-8"))
    check("paper: everyone %s is for may report on the Training Event" % spec["name"],
          spec["ref_doctype"] == "Training Event" and {row["role"] for row in spec["roles"]} <= REPORTERS,
          {row["role"] for row in spec["roles"]} - REPORTERS)

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_value.py")


def body(name):
    found = re.search(r"\ndef %s\(.*?(?=\n(?:def |@frappe|[A-Z_]+ = )|\Z)" % re.escape(name), GLUE, re.S)
    return found.group(0) if found else ""


check("glue: only those who came cost time", 'row.attendance == "Present"' in body("event_costs"))
check("glue: a held session is spent, the rest committed", 'event.docstatus == 1 and event.event_status == "Completed"'
      in body("_sessions") and '"event_status": ["!=", "Cancelled"]' in body("_sessions"))
check("glue: the budget told once, to HR and Finance", "rules.newly_alerting" in body("refresh_budgets")
      and 'people.people_for("HR Manager"' in body("_tell") and "FINANCE_ROLES" in body("_tell"))
check("glue: the reports read held sessions through the user's permissions", "frappe.get_list(EVENT"
      in body("sessions_in") and '"docstatus": 1' in body("sessions_in"))

# ── 4. Wiring ─────────────────────────────────────────────────────────
HOOKS = read("hrms_addon", "hooks.py")
check("wiring: the session's costs on save and after submit", '"hrms_addon.hrms_addon.learning_value.event_costs",'
      in HOOKS and '"before_update_after_submit": "hrms_addon.hrms_addon.learning_value.event_costs"' in HOOKS)
check("wiring: the budgets on every save, submit, change and cancel, and daily",
      HOOKS.count('"hrms_addon.hrms_addon.learning_value.event_changed"') == 4
      and '"hrms_addon.hrms_addon.learning_value.daily"' in HOOKS)
check("wiring: the session's cost fields ship", all('"%s"' % name in HOOKS for name in CUSTOM
                                                    if name.startswith("Training Event-custom_cost")
                                                    or name in ("Training Event-custom_direct_cost",
                                                                "Training Event-custom_time_cost",
                                                                "Training Event-custom_total_cost")))
CONTROLLER = read("hrms_addon", "hrms_addon", "doctype", "training_budget", "training_budget.py")
for method, call in (("autoname", "budget_autoname"), ("validate", "budget_validate"), ("on_update", "budget_on_update")):
    check("wiring: the budget's %s calls learning_value.%s" % (method, call), "def %s(self)" % method in CONTROLLER
          and "learning_value.%s(self)" % call in CONTROLLER and "\ndef %s(" % call in GLUE)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_value: OK")
