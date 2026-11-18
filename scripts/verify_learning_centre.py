"""Verify the Learning Command Centre, its snapshot, health, insights, print and deck (the LMS rebuild, items 6 and
12, 18 Nov 2026), without a bench:

    python scripts/verify_learning_centre.py
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


R = load("learning_centre_rules")
L = load("learning_rules")

# ── 1. The rules ──────────────────────────────────────────────────────
C = dict(R.blank(), headcount=100, required=200, done=150, overdue=20, mandatory_required=100, mandatory_done=90,
         cert_valid=45, cert_expired=5, cert_expiring=6, trained=80, attended=90, marked=100, assessed=40, passed=30,
         competent=60, skills_assessed=80, critical_ok=3, critical_total=4, reviews_done=10, review_score=700,
         kpis_measured=4, kpis_improved=2, spend=900, budget=1000, hours=320)
P = R.parts_of(C)
check("the nine parts from the counts", P == {"mandatory": 90.0, "certification": 90.0, "coverage": 80.0,
                                              "competency": 75.0, "attendance": 90.0, "assessment": 75.0,
                                              "effectiveness": 60.0, "budget_use": 90.0, "critical": 75.0}, P)
check("the parts are the settings' parts", list(R.PART_SETTING.values()) == [key for key, _l in L.HEALTH_PARTS])
check("budget use: 100 on budget, less the further over or under, none without a budget",
      R.budget_use(1000, 1000) == 100.0 and R.budget_use(1200, 1000) == 80.0 and R.budget_use(500, 1000) == 50.0
      and R.budget_use(3000, 1000) == 0.0 and R.budget_use(10, 0) is None)
WEIGHTS = L.weights(None, "health_", L.HEALTH_PARTS)
score, status = R.health(P, WEIGHTS)
check("the health score: the parts weighed as the settings say (20, 15, 10 ...)", (score, status) == (
    round((90 * 20 + 90 * 15 + 80 * 10 + 75 * 10 + 90 * 10 + 75 * 10 + 60 * 10 + 90 * 5 + 75 * 10) / 100.0, 1),
    "Healthy" if score >= 85 else "Watch"), (score, status))
check("a part with no data neither helps nor harms", R.health({"mandatory": 50}, WEIGHTS) == (50.0, "At Risk")
      and R.health({}, WEIGHTS) == (None, "No Data"))
check("weights by the settings' names count too", R.health({"budget_use": 40}, {"budget": 1})[0] == 40.0)
F = R.figures(C)
check("the tiles' figures", (F["compliance"], F["mandatory"], F["certification"], F["coverage"], F["pass_rate"],
                             F["budget_used"], F["cost_per_employee"]) == (75.0, 90.0, 90.0, 80.0, 75.0, 90.0, 11.25), F)
check("a month's series", R.month_series([dict(C, month_start="2026-10-01"), dict(C, month_start="2026-09-01",
                                                                                    done=100)], "compliance")
      == [("2026-09", 50.0), ("2026-10", 75.0)])
LINES = [dict(R.blank(), branch="Namanve", department="Admin", required=100, done=50, overdue=30, cert_expiring=2,
              cert_expired=1),
         dict(R.blank(), branch="Kawempe", department="Extrusion", required=100, done=95)]
FOUND = R.insights(LINES, programmes=[{"training_program": "Forklift", "assessed": 5, "pass_rate": 40, "held": 2,
                                       "behaviour_on": True, "reviews_done": 0}],
                   covers=[{"skill": "Extruder", "branch": "Matugga", "status": "Single Point of Failure", "critical": 1},
                           {"skill": "5S", "branch": "Matugga", "status": "Thin", "critical": 1}],
                   budgets=[{"name": "2026 LPL", "status": "Near the Limit", "utilisation": 88}],
                   providers=[{"name": "SafeCo", "trend": -8}, {"name": "Acme", "trend": 2}])
texts = [item["text"] for item in FOUND]
check("insights: a plant below the threshold, certificates expiring and run out, the department furthest behind, a "
      "low pass rate, no level 3 evidence, a single point of failure, a budget near its limit, a falling provider",
      any("Namanve: 50% of required training done" in text for text in texts)
      and any("2 certificate(s) run out within 90 days" in text for text in texts)
      and any("1 certificate(s) have run out" in text for text in texts)
      and any(text.startswith("Admin, Namanve: 50% done, 30 overdue") for text in texts)
      and any("Forklift: only 40% passed" in text for text in texts)
      and any("no supervisor has said" in text for text in texts)
      and any("Extruder at Matugga: single point of failure" in text for text in texts)
      and any("2026 LPL is 88% used" in text for text in texts)
      and any("SafeCo: ratings falling" in text for text in texts)
      and not any("Kawempe" in text for text in texts) and not any("Acme" in text for text in texts)
      and not any("5S" in text for text in texts), texts)
check("insights: the most pressing first, each linking to its list", [item["severity"] for item in FOUND]
      == sorted([item["severity"] for item in FOUND], key=lambda s: {"High": 0, "Medium": 1, "Low": 2}[s])
      and all(item["route"] for item in FOUND))
check("the version a user opens on", [R.view_for(roles) for roles in (
    ["HR Manager"], ["HR User"], ["Head of Department"], ["Supervisor", "Employee"], ["Employee"])]
      == ["Company", "Plant", "Department", "My Team", "My Learning"])

# ── 2. The paper ──────────────────────────────────────────────────────
snapshot, line = fields("Learning Snapshot"), fields("Learning Snapshot Line")
for key in R.COUNTS:
    check("the snapshot and its lines keep %s" % key, key in snapshot and key in line)
for key in R.PARTS:
    check("the snapshot and its lines keep the part %s" % key, "part_" + key in snapshot and "part_" + key in line)
check("a line per plant and department, with its health", {"branch", "department", "health_score"} <= set(line))
check("the snapshot's month, source, health and lines", {"company", "month_start", "source", "health_score",
                                                         "health_status", "built_on", "lines"} <= set(snapshot))
SETTINGS = fields("Learning Settings")
for key, _label in L.HEALTH_PARTS:
    check("Learning Settings weighs %s" % key, "health_" + key in SETTINGS)
PRINT = json.load(open(os.path.join(APP, "print_format", "learning_snapshot_summary", "learning_snapshot_summary.json"),
                       encoding="utf-8"))
check("the one-page print on the snapshot, its parts and its lines", PRINT["doc_type"] == "Learning Snapshot"
      and "part_" in PRINT["html"] and "doc.lines" in PRINT["html"] and "<table" not in PRINT["html"])

# ── 3. The glue and the wiring ────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "learning_centre.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("counted by the database, by plant and department", GLUE.count("_grouped(") >= 8
      and 'group_by=", ".join(by)' in GLUE)
check("the plants a user sees: all for HR and management, else what their own permissions reach",
      "def permitted_plants():" in GLUE and 'frappe.get_list("Employee"' in GLUE)
check("the month kept on the 1st, and on demand", "def monthly():" in GLUE and "def build_now(" in GLUE
      and "take_snapshot(company, month)" in GLUE)
for name in ("centre", "build_now", "download_deck"):
    check("%s is whitelisted" % name, re.search(r"@frappe\.whitelist\([^)]*\)\ndef %s\(" % name, GLUE))
check("five versions: the company, a plant, a department, a supervisor's team, the employee's own",
      "def my_team(own):" in GLUE and "def my_learning(own):" in GLUE and "rules.view_for(" in GLUE)
check("the insights from the data, no outside service", "rules.insights(lines, programmes, covers, budgets, providers"
      in GLUE and "requests" not in GLUE and "openai" not in GLUE.lower())
DECK = read("hrms_addon", "hrms_addon", "learning_deck.py")
check("the deck: native tables and charts, python-pptx asked for by name",
      "add_chart(" in DECK and "add_table(" in DECK and "bench pip install python-pptx" in DECK)
HEALTH = read("hrms_addon", "hrms_addon", "report", "learning_health", "learning_health.py")
check("Learning Health: the nine parts, the plants the user may see", "learning_centre.permitted_plants()" in HEALTH
      and "rules.PARTS" in HEALTH and "frappe.get_all(" not in HEALTH)
PAGE = read("hrms_addon", "hrms_addon", "page", "learning_command_centre", "learning_command_centre.js")
check("the page: tiles that open their reports, insights that open their lists, trends and plants charted, the "
      "team and the employee's own", "data-tile" in PAGE and "data-insight" in PAGE and "frappe.Chart" in PAGE
      and "render_team" in PAGE and "render_mine" in PAGE and "frappe.utils.escape_html" in PAGE)
HOOKS = read("hrms_addon", "hooks.py")
check("hooks: the month kept", '"hrms_addon.hrms_addon.learning_centre.monthly"' in HOOKS)
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Learning Command Centre", "Learning Snapshot"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)
DASH = read("hrms_addon", "hrms_addon", "dashboards_rules.py")
check("the desk home's training tab leads with compliance and certificates",
      '"cards": ("training_compliance", "certificates_valid", "certificates_expiring", "trainings_month")' in DASH
      and '("learning-command-centre", "Learning Command Centre")' in DASH)

if fail:
    print("FAILURES:")
    for item in fail:
        print("  -", item)
    sys.exit(1)
print("verify_learning_centre: OK")
