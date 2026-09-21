"""Verify the dashboards and the two LPL reports, without a bench:

    python scripts/verify_dashboards.py

The Dashboards & Reports sheet of Luuka's revised testing scripts:

  case 1  dashboards for headcount by plant, the wage bill and the leave
          liability
  case 3  the monthly manpower and headcount report that replaces the
          manual extract
  case 5  performance analytics: completion rates, average score, band
          distribution, and a cross-plant comparison

  Labour cost per kilogram (case 1's last clause) waits on the production
  feed, which is Integration case 3. It is not built here and is not
  pretended to be.

  Case 2's standard reports are Frappe HR's own — payslips, leave
  balances, attendance — and the ones this app adds are checked by their
  own modules' scripts.

  Case 4: Frappe exports a report to Excel, CSV and PDF from the report
  view. Word and PowerPoint it does not, and nothing here claims to.

  1  every chart reads a document and a field that exist
  2  the dashboard names charts that exist
  3  the two reports read what they say they read
  4  a way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import glob
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
            "parent", "parenttype", "parentfield", "_user_tags", "_comments", "_assign"}
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def our_doctype(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder,
                                      folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def field_names(doctype):
    spec = our_doctype(doctype) or upstream_doctype(doctype)
    if spec is None:
        return None
    names = {f["fieldname"] for f in spec.get("fields", [])}
    names |= {row["fieldname"] for row in CUSTOM if row.get("dt") == doctype}
    # Frappe HR adds a few to Employee in code (hrms/setup.py)
    if doctype == "Employee":
        names |= {"employment_type", "grade", "job_applicant", "default_shift"}
    return names | STANDARD


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
CHART_DIR = os.path.join(APP, "dashboard_chart")
charts = {}
for path in sorted(glob.glob(os.path.join(CHART_DIR, "*", "*.json"))):
    spec = json.load(open(path, encoding="utf-8"))
    charts[spec["name"]] = spec
print("read %d dashboard chart(s)" % len(charts))

# ── 1. Every chart reads something real ───────────────────────────────
if not charts:
    fail.append("no dashboard charts were found: case 1 asks for them")
for name, spec in charts.items():
    where = "chart %r" % name
    if spec.get("doctype") != "Dashboard Chart":
        fail.append("%s: not a Dashboard Chart" % where)
    if spec.get("module") != "HRMS Addon":
        fail.append("%s: belongs to %r, and a record this app ships must name this app"
                    % (where, spec.get("module")))
    if not spec.get("is_standard"):
        fail.append("%s: a chart shipped as a file is standard, or a migrate deletes it"
                    % where)
    document = spec.get("document_type")
    names = field_names(document) if document else None
    if names is None:
        fail.append("%s: reads %r, which is not a DocType here or upstream" % (where, document))
        continue
    for key in ("group_by_based_on", "based_on", "aggregate_function_based_on",
                "value_based_on"):
        fieldname = spec.get(key)
        if fieldname and fieldname not in names:
            fail.append("%s: %s is %r, which is not on %s" % (where, key, fieldname, document))
    for row in json.loads(spec.get("filters_json") or "[]"):
        if len(row) >= 2 and row[1] not in names and row[1] != "docstatus":
            fail.append("%s: filters on %r, which is not on %s" % (where, row[1], document))
    for row in json.loads(spec.get("dynamic_filters_json") or "[]"):
        if len(row) >= 2 and row[1] not in names:
            fail.append("%s: a dynamic filter on %r, which is not on %s"
                        % (where, row[1], document))
    if spec.get("chart_type") == "Group By" and not spec.get("group_by_based_on"):
        fail.append("%s: a Group By chart must say what it groups by" % where)
    if spec.get("timeseries") and not spec.get("based_on"):
        fail.append("%s: a timeseries must say which date it runs on" % where)
    if spec.get("chart_type") == "Group By" and spec.get("group_by_type") in ("Sum", "Average") \
            and not spec.get("aggregate_function_based_on"):
        fail.append("%s: a Group By that sums must say what it sums" % where)
    # Frappe reads value_based_on for a Sum or Average chart; given
    # aggregate_function_based_on instead it falls back to "1" and counts
    # rows, which looks like a working chart and is not one
    if spec.get("chart_type") in ("Sum", "Average"):
        if not spec.get("value_based_on"):
            fail.append("%s: a %s chart sums value_based_on, and has none"
                        % (where, spec["chart_type"]))
        if spec.get("aggregate_function_based_on"):
            fail.append("%s: a %s chart reads value_based_on; aggregate_function_based_on is "
                        "for a Group By and is ignored here" % (where, spec["chart_type"]))

# case 1 names the three by name
wanted = {"headcount": "branch", "wage bill": "base", "leave liability": None}
lowered = {name.lower(): spec for name, spec in charts.items()}
for phrase in ("headcount by plant", "wage bill", "leave liability"):
    if not any(phrase in name for name in lowered):
        fail.append("test case 1 asks for a chart of the %s" % phrase)
print("the charts: each reads a document and a field that exist")

# ── 2. The dashboard ──────────────────────────────────────────────────
boards = sorted(glob.glob(os.path.join(APP, "dashboard", "*", "*.json")))
if not boards:
    fail.append("no dashboard was found to put the charts on")
for path in boards:
    board = json.load(open(path, encoding="utf-8"))
    where = "dashboard %r" % board.get("name")
    if board.get("module") != "HRMS Addon" or not board.get("is_standard"):
        fail.append("%s: must be standard and belong to this app" % where)
    named = [row.get("chart") for row in board.get("charts") or []]
    if not named:
        fail.append("%s: has no charts on it" % where)
    for chart in named:
        if chart not in charts:
            fail.append("%s: names chart %r, which is not shipped" % (where, chart))
    if len(set(named)) != len(named):
        fail.append("%s: the same chart is on it twice" % where)
print("the dashboard: every chart on it is one this app ships")

# ── 3. The two reports ────────────────────────────────────────────────
for folder, name, ref in (("monthly_manpower_and_headcount",
                           "Monthly Manpower and Headcount", "Employee"),
                          ("performance_analytics", "Performance Analytics", "Appraisal")):
    path = os.path.join(APP, "report", folder, folder + ".json")
    if not os.path.exists(path):
        fail.append("%s is not shipped" % name)
        continue
    spec = json.load(open(path, encoding="utf-8"))
    if spec.get("ref_doctype") != ref or spec.get("is_standard") != "Yes":
        fail.append("%s: a standard report on %s" % (name, ref))
    if spec.get("module") != "HRMS Addon":
        fail.append("%s: belongs to this app" % name)
    roles = [row["role"] for row in spec.get("roles", [])]
    for role in ("HR Manager", "Auditor"):
        if role not in roles:
            fail.append("%s: %s must be able to read it" % (name, role))
    body = read("hrms_addon", "hrms_addon", "report", folder, folder + ".py")
    if "frappe.get_list(" not in body:
        fail.append("%s: reads through Frappe's permissions (get_list, not get_all)" % name)
    if "def execute(" not in body or "def columns(" not in body:
        fail.append("%s: a script report is an execute and its columns" % name)

manpower = read("hrms_addon", "hrms_addon", "report", "monthly_manpower_and_headcount",
                "monthly_manpower_and_headcount.py")
for needle, why in (
    ("Salary Structure Assignment", "the wage bill is read from the assignments in force"),
    ("attendance_rules.cycle_window", "and the month may be Luuka's own 26th-to-25th cycle"),
    ("relieving_date", "leavers are counted"),
    ("date_of_joining", "and so are joiners"),
):
    if needle not in manpower:
        fail.append("the manpower report: %s (%r not found)" % (why, needle))
for forbidden in ("Salary Slip", "Payroll Entry"):
    if forbidden in manpower:
        fail.append("the manpower report reads before a payroll run as well as after one, so "
                    "it must not read %s" % forbidden)

analytics = read("hrms_addon", "hrms_addon", "report", "performance_analytics",
                 "performance_analytics.py")
for needle, why in (
    ("appraisal_rules.BANDS", "the bands are the performance module's own"),
    ("appraisal_rules.PIP_BELOW", "and so is the line below which somebody is on a PIP"),
    ("custom_total_score", "the score is read, never recomputed"),
    ("by_plant", "test case 5 asks for a cross-plant comparison"),
):
    if needle not in analytics:
        fail.append("the analytics report: %s (%r not found)" % (why, needle))
A = load("appraisal_rules")
for _floor, band in A.BANDS:
    if band not in analytics and "BANDS" not in analytics:
        fail.append("the analytics report must show the band %r" % band)
print("the reports: the manpower extract and the analytics, reading what they say they read")

# ── 4. A way in ───────────────────────────────────────────────────────
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for name in ("Monthly Manpower and Headcount", "Performance Analytics"):
    if name not in nav:
        fail.append("%s has no way in" % name)
    if '"%s":' % name not in nav:
        fail.append("%s must say which document it is for" % name)
for folder in ("monthly_manpower_and_headcount", "performance_analytics"):
    if not os.path.exists(os.path.join(APP, "report", folder, folder + ".js")):
        fail.append("%s has no filter script" % folder)
    if not os.path.exists(os.path.join(APP, "report", folder, "__init__.py")):
        fail.append("%s is not a package" % folder)
for path in glob.glob(os.path.join(CHART_DIR, "*")):
    if os.path.isdir(path) and not os.path.exists(os.path.join(path, "__init__.py")):
        fail.append("%s is not a package" % os.path.basename(path))
print("a way in: both reports listed, both packages complete")

if fail:
    print("\nFAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("\nALL DASHBOARD AND REPORT CHECKS PASSED")
