"""Checks for the three interview reports, run without a bench.

interview_analytics_rules.py imports nothing from Frappe, so it is loaded
directly and its arithmetic walked: each panel member against the
colleagues who scored the same candidates, each round's pass rate, and the
days a hire takes. It also checks each Script Report (its record, its
columns against what the rules give, the filters its script declares and
reads, the fields it reads) and where HR finds them, and against Frappe HR
(../ERPNext, or FRAPPE_APPS_ROOT) what they read there.

    python scripts/verify_interview_reports.py
"""
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream(app, *parts):
    return open(os.path.join(APPS_ROOT, app, app, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


A = load("interview_analytics_rules")
rules = load("interview_rules")
print("loaded interview_analytics_rules.py without Frappe")

# ── 1. Calibration ────────────────────────────────────────────────────
sheets = [
    {"interviewer": "hod@lpl", "interview": "I1", "percent": 90, "recommendation": "Offer"},
    {"interviewer": "sup@lpl", "interview": "I1", "percent": 70, "recommendation": "Shortlist"},
    {"interviewer": "hod@lpl", "interview": "I2", "percent": 60, "recommendation": "Reject"},
    {"interviewer": "sup@lpl", "interview": "I2", "percent": 50, "recommendation": "Reject"},
    {"interviewer": "hr@lpl", "interview": "I2", "percent": 40, "recommendation": "Reject"},
    {"interviewer": "hod@lpl", "interview": "I3", "percent": 80, "recommendation": "Offer"},
    {"interviewer": "", "interview": "I3", "percent": 10, "recommendation": "Reject"},
]
rows = {row["interviewer"]: row for row in A.calibration(sheets)}
if list(rows) != ["hod@lpl", "hr@lpl", "sup@lpl"]:
    fail.append("one row per panel member, by user, a sheet with no interviewer aside: %s" % list(rows))
hod = rows.get("hod@lpl") or {}
if (hod.get("sheets"), hod.get("average"), hod.get("others_average"), hod.get("difference"), hod.get("compared"),
        hod.get("offer_share"), hod.get("reject_share")) != (3, 76.67, 57.5, 17.5, 2, 66.67, 33.33):
    fail.append("the HOD: 3 sheets averaging 76.67%%, 17.5 above colleagues on the 2 interviews shared: %s" % hod)
if ((rows.get("hr@lpl") or {}).get("difference"), (rows.get("sup@lpl") or {}).get("difference")) != (-15.0, -10.0):
    fail.append("below colleagues shows below 0: %s" % rows)
alone = A.calibration([{"interviewer": "x@lpl", "interview": "I9", "percent": 55, "recommendation": ""}])
if alone != [{"interviewer": "x@lpl", "sheets": 1, "average": 55.0, "others_average": None, "difference": None,
              "compared": 0, "offer_share": None, "reject_share": None}]:
    fail.append("a panel member who never shared an interview has nothing to compare: %s" % alone)
if A.calibration([]) != [] or A.calibration(None) != []:
    fail.append("no sheets, no rows")

# ── 2. Pass rates ─────────────────────────────────────────────────────
rates = A.pass_rates([
    {"job_opening": "O1", "interview_type": "R1", "round": 1, "status": "Cleared", "docstatus": 1},
    {"job_opening": "O1", "interview_type": "R1", "round": 1, "status": "Rejected", "docstatus": 1},
    {"job_opening": "O1", "interview_type": "R1", "round": 1, "status": "Cancelled", "docstatus": 0, "attendance": "No-Show"},
    {"job_opening": "O1", "interview_type": "R1", "round": 1, "status": "Pending", "docstatus": 0, "attendance": "Withdrew"},
    {"job_opening": "O1", "interview_type": "R1", "round": 1, "status": "Under Review", "docstatus": 0},
    {"job_opening": "O1", "interview_type": "R2", "round": 2, "status": "Pending", "docstatus": 0},
    {"job_opening": "O1", "interview_type": "R2", "round": 2, "status": "Cancelled", "docstatus": 0},
    {"job_opening": "O1", "interview_type": "R2", "round": 2, "status": "Cleared", "docstatus": 0},
    {"job_opening": "O0", "interview_type": "S1", "round": 1, "status": "Cleared", "docstatus": 1},
])
if [(r["job_opening"], r["round"], r["booked"], r["attended"], r["absent"], r["cleared"], r["rejected"], r["awaiting"],
     r["pass_rate"]) for r in rates] != [("O0", 1, 1, 1, 0, 1, 0, 0, 100.0), ("O1", 1, 5, 3, 2, 1, 1, 1, 50.0),
                                         ("O1", 2, 3, 2, 1, 0, 0, 2, None)]:
    fail.append("each opening's rounds: booked, came, did not come, cleared, rejected, awaiting, pass rate of those decided: %s"
                % rates)
if tuple(A.ABSENT) != tuple(rules.ABSENT):
    fail.append("the reports count as absent what the interviews do (interview_rules.ABSENT)")

# ── 3. Time to hire ───────────────────────────────────────────────────
import datetime  # noqa: E402

if A.hire_timeline("2026-09-01 10:22:05.123", datetime.date(2026, 9, 10), "2026-09-20", None) \
        != {"days_to_interview": 9, "days_to_offer": 19, "days_to_join": None}:
    fail.append("days from the application to the first interview, the offer and joining")
if A.hire_timeline(None, "2026-09-10", "2026-09-20", "2026-10-01") != {"days_to_interview": None, "days_to_offer": None,
                                                                       "days_to_join": None}:
    fail.append("with no application date there is nothing to count from")
if A.averages([{"a": 10, "b": None}, {"a": 20, "b": 5}, {"a": None}], ("a", "b", "c")) != {"a": 15.0, "b": 5.0, "c": None}:
    fail.append("averages leave out what is not set")
print("arithmetic: calibration against colleagues, pass rates per round, days to hire")

# ── 4. The reports ────────────────────────────────────────────────────
custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
custom_names = {row["name"] for row in custom}
REPORTS = {"Interviewer Calibration": "Interview Feedback", "Interview Pass Rate": "Interview", "Time to Hire": "Job Offer"}
for name, ref in REPORTS.items():
    folder = name.lower().replace(" ", "_")
    base = os.path.join(APP, "report", folder)
    spec = json.load(open(os.path.join(base, folder + ".json"), encoding="utf-8"))
    if (spec.get("name"), spec.get("report_name"), spec.get("report_type"), spec.get("ref_doctype"), spec.get("module"),
            spec.get("is_standard"), spec.get("disabled")) != (name, name, "Script Report", ref, "HRMS Addon", "Yes", 0):
        fail.append("%s must be a standard, enabled Script Report of %s in HRMS Addon" % (name, ref))
    if {row["role"] for row in spec.get("roles", [])} != {"HR User", "HR Manager", "System Manager"}:
        fail.append("%s is HR's: HR User, HR Manager and System Manager" % name)
    if not os.path.exists(os.path.join(base, "__init__.py")):
        fail.append("%s needs its __init__.py" % name)
    py = open(os.path.join(base, folder + ".py"), encoding="utf-8").read()
    js = open(os.path.join(base, folder + ".js"), encoding="utf-8").read()
    if "def execute(filters=None):" not in py or "from hrms_addon.hrms_addon import interview_analytics_rules as rules" not in py:
        fail.append("%s must run execute() on the tested arithmetic" % name)
    if 'frappe.query_reports["%s"] = {' % name not in js:
        fail.append("%s.js must register the report by its name" % name)
    declared = set(re.findall(r'fieldname: "(\w+)"', js))
    for used in set(re.findall(r'filters\.get\("(\w+)"\)', py)):
        if used not in declared:
            fail.append("%s reads the filter %s, which its script does not offer" % (name, used))
    if not {"from_date", "to_date"} <= declared:
        fail.append("%s needs its From and To dates" % name)
    for field in set(re.findall(r'"(custom_\w+)"', py)):
        dt = "Interview Feedback" if field in ("custom_score_percent", "custom_recommendation") else "Interview"
        if "%s-%s" % (dt, field) not in custom_names:
            fail.append("%s reads %s.%s, which does not exist" % (name, dt, field))
    columns = re.findall(r'\{"fieldname": "(\w+)"', py.split("def columns():")[-1])
    if len(columns) != len(set(columns)) or not columns:
        fail.append("%s: each column once" % name)
    if name == "Interviewer Calibration":
        given = set(A.calibration(sheets)[0]) | {"full_name"}
    elif name == "Interview Pass Rate":
        given = set(rates[0])
    else:
        given = set(re.findall(r'^\s+"(\w+)": ', py.split("rows.append(dict({")[-1].split("})")[0], re.M)) \
            | set(A.hire_timeline(None, None, None, None))
    if not set(columns) <= given:
        fail.append("%s shows columns its rows do not have: %s" % (name, sorted(set(columns) - given)))
tth = read("hrms_addon", "hrms_addon", "report", "time_to_hire", "time_to_hire.py")
if "return columns(), rows, None, None, summary" not in tth or "means = rules.averages(rows, DAYS)" not in tth:
    fail.append("Time to Hire must put the average days on top (its report summary)")
if '"status": ["in", ["Awaiting Response", "Accepted"]]' in tth:
    fail.append("Time to Hire lists every offer made, declined ones too")
cal = read("hrms_addon", "hrms_addon", "report", "interviewer_calibration", "interviewer_calibration.py")
if 'filters={"interview": ["in", interviews or [""]], "docstatus": 1}' not in cal:
    fail.append("Interviewer Calibration counts the submitted sheets of the interviews in range")
print("reports: records, columns, filters and the fields they read resolve")

# ── 5. Where HR finds them ────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("navigation_rules", os.path.join(APP, "navigation_rules.py"))
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
card = dict(N.CARDS.get("Recruitment", [])).get("Reports") or []
if [link[1] for link in card] != list(REPORTS) or any(link[2] != N.REPORT for link in card):
    fail.append("the Recruitment page's Reports card must list the three reports: %s" % card)
side = [entry for entry in N.SIDEBAR.get("Recruitment", []) if entry[2] == N.REPORT]
if [entry[1] for entry in side] != list(REPORTS) or any(entry[3] != "Reports" for entry in side):
    fail.append("the Recruitment sidebar's Reports section must list the three reports: %s" % side)
for name in REPORTS:
    if N.report_facts(name)[0] not in N.QUERY_REPORT_TYPES:
        fail.append("%s must open as a query report from the menu" % name)
print("menu: Recruitment's Reports card and sidebar")

# ── 6. What they read in Frappe HR ────────────────────────────────────
if UPSTREAM_OK:
    offer = {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "job_offer", "job_offer.json"))["fields"]}
    if not {"job_applicant", "applicant_name", "designation", "offer_date", "status"} <= offer:
        fail.append("Frappe HR's Job Offer changed: recheck Time to Hire")
    interview = {f["fieldname"]: f for f in json.loads(upstream("hrms", "hr", "doctype", "interview", "interview.json"))["fields"]}
    if not {"job_opening", "interview_type", "scheduled_on", "status", "job_applicant", "designation"} <= set(interview):
        fail.append("Frappe HR's Interview changed: recheck the reports")
    if "job_title" not in {f["fieldname"] for f in json.loads(upstream("hrms", "hr", "doctype", "job_applicant",
                                                                      "job_applicant.json"))["fields"]}:
        fail.append("Frappe HR's Job Applicant has no job_title: recheck Time to Hire's opening")
    if '"fieldname": "job_applicant"' not in upstream("hrms", "setup.py") \
            and "job_applicant" not in upstream("hrms", "setup.py"):
        fail.append("Frappe HR no longer adds job_applicant to Employee: recheck Time to Hire's joining date")
    upstream_note = "checked against Frappe HR"
else:
    upstream_note = "Frappe HR not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL INTERVIEW REPORT CHECKS PASSED")
