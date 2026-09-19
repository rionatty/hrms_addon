"""Checks for contract management, run without a bench.

contract_rules.py imports nothing from Frappe, so it is loaded directly and
exercised: a contract's status on a day, the alerts a year, a quarter and a
month before its end (each once, a late one covering the thresholds passed),
the end from the Employment Type's usual length, a renewal's dates, the
checks on a contract (dates, no two at once, the signed copy before it is
submitted).

It also cross-checks the Employee Contract DocType, the glue (the Employee's
Contract End Date, renew, do not renew, the daily job, the contract drafted
at onboarding), the scheduler and dashboard hooks, the Contract Expiry Status
report and the three print formats (contract, renewal letter, expiry letter).

    python scripts/verify_contracts.py
"""
import ast
import glob
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no errors, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d error(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected an error containing %r, got %s" % (label, needle, got))


spec = importlib.util.spec_from_file_location("contract_rules", os.path.join(APP, "contract_rules.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)  # proves it has no Frappe import
print("loaded contract_rules.py without Frappe")

# ── 1. Status and alerts ──────────────────────────────────────────────
for text, want in (("365, 90, 30", (365, 90, 30)), ("30 90 365 90", (365, 90, 30)), ("", C.DEFAULT_ALERT_DAYS),
                   (None, C.DEFAULT_ALERT_DAYS), ("0, -5, abc", C.DEFAULT_ALERT_DAYS), ("60", (60,))):
    if C.parse_alert_days(text) != want:
        fail.append("parse_alert_days(%r) is %s, expected %s" % (text, C.parse_alert_days(text), want))
if C.DEFAULT_ALERT_DAYS != (365, 90, 30):
    fail.append("the To-Be alerts a year, a quarter and a month before the end")
TODAY = "2026-10-01"
for label, got, want in (
    ("a draft", C.contract_status(0, "2027-09-30", TODAY), C.DRAFT),
    ("cancelled", C.contract_status(2, "2027-09-30", TODAY), C.CANCELLED),
    ("a year to go", C.contract_status(1, "2027-09-30", TODAY), C.ACTIVE),
    ("a quarter to go", C.contract_status(1, "2026-12-30", TODAY), C.EXPIRING),
    ("ends today", C.contract_status(1, TODAY, TODAY), C.EXPIRING),
    ("ended", C.contract_status(1, "2026-09-30", TODAY), C.EXPIRED),
    ("open-ended", C.contract_status(1, None, TODAY), C.ACTIVE),
    ("renewed", C.contract_status(1, "2026-09-30", TODAY, renewed=True), C.RENEWED),
    ("not renewed", C.contract_status(1, "2026-10-30", TODAY, not_renewed=True), C.NOT_RENEWED),
):
    if got != want:
        fail.append("contract_status, %s: %s, expected %s" % (label, got, want))
DAYS = (365, 90, 30)
for label, got, want in (
    ("more than a year out", C.alerts_due("2027-12-31", TODAY, DAYS, ""), []),
    ("a year out", C.alerts_due("2027-10-01", TODAY, DAYS, ""), [365]),
    ("the year's alert sent", C.alerts_due("2027-06-01", TODAY, DAYS, "365"), []),
    ("a quarter out", C.alerts_due("2026-12-30", TODAY, DAYS, "365"), [90]),
    ("first seen a month out", C.alerts_due("2026-10-20", TODAY, DAYS, ""), [365, 90, 30]),
    ("all sent", C.alerts_due("2026-10-20", TODAY, DAYS, "365, 90, 30"), []),
    ("ended", C.alerts_due("2026-09-30", TODAY, DAYS, ""), []),
    ("open-ended", C.alerts_due(None, TODAY, DAYS, ""), []),
    ("settings text", C.alerts_due("2026-10-20", TODAY, "90, 30", "90"), [30]),
):
    if got != want:
        fail.append("alerts_due, %s: %s, expected %s" % (label, got, want))
if C.record_alerts("365", [90, 30]) != "365, 90, 30" or C.record_alerts(None, [30]) != "30":
    fail.append("record_alerts keeps every threshold sent, largest first")
print("status and alerts: each status on its day; a year, a quarter and a month before, each once")

# ── 2. Dates and checks ───────────────────────────────────────────────
for start, months, want in (("2026-10-01", 12, "2027-09-30"), ("2026-10-01", 6, "2027-03-31"), ("2026-01-31", 1, "2026-02-27"),
                            ("2026-10-01", 0, "None"), ("2026-10-01", None, "None")):
    if str(C.end_for(start, months)) != want:
        fail.append("end_for(%s, %s) is %s, expected %s" % (start, months, C.end_for(start, months), want))
if tuple(map(str, C.renewal_dates("2027-09-30", None))) != ("2027-10-01", "2028-09-30"):
    fail.append("a renewal starts the day after the end and runs a year by default: %s" % (C.renewal_dates("2027-09-30", None),))
if tuple(map(str, C.renewal_dates("2027-09-30", 6))) != ("2027-10-01", "2028-03-31"):
    fail.append("a renewal runs the Employment Type's usual length")
OTHERS = [{"name": "HR-CON-1", "start_date": "2025-10-01", "end_date": "2026-09-30"},
          {"name": "HR-CON-2", "start_date": "2026-01-01", "end_date": None}]
if C.overlaps("2026-10-01", "2027-09-30", OTHERS[:1]) != [] or C.overlaps("2026-09-30", "2027-09-30", OTHERS[:1]) != ["HR-CON-1"] \
        or C.overlaps("2030-01-01", None, OTHERS[1:]) != ["HR-CON-2"]:
    fail.append("overlaps: dates that meet, an open end running forever")
FACTS = {"start_date": "2026-10-01", "end_date": "2027-09-30", "open_ended": False, "submitting": False}
expect("a draft", C.contract_errors(FACTS, TODAY))
expect("ends before it starts", C.contract_errors(dict(FACTS, end_date="2026-09-01"), TODAY), "The contract cannot end before it starts.")
expect("no end, not open-ended", C.contract_errors(dict(FACTS, end_date=None), TODAY), "Set the End Date")
expect("no end, open-ended", C.contract_errors(dict(FACTS, end_date=None, open_ended=True), TODAY))
expect("two at once", C.contract_errors(dict(FACTS, overlaps=["HR-CON-1"]), TODAY),
       "The employee already has a contract for these dates: HR-CON-1.")
expect("submitted unsigned", C.contract_errors(dict(FACTS, submitting=True), TODAY),
       "Record the date the employee signed", "Attach the signed contract")
expect("signed tomorrow", C.contract_errors(dict(FACTS, submitting=True, signed_on="2026-10-02", signed_contract="/private/files/c.pdf"), TODAY),
       "The date signed cannot be in the future.")
expect("submitted signed", C.contract_errors(dict(FACTS, submitting=True, signed_on=TODAY, signed_contract="/private/files/c.pdf"), TODAY))
print("dates and checks: usual lengths, renewal dates, overlaps, the signed copy before submitting")

# ── 3. The DocType ────────────────────────────────────────────────────
folder = os.path.join(APP, "doctype", "employee_contract")
EC = json.load(open(os.path.join(folder, "employee_contract.json"), encoding="utf-8"))
ec = {f["fieldname"]: f for f in EC["fields"]}
if not EC.get("is_submittable"):
    fail.append("Employee Contract is submitted once signed")
statuses = [o for o in (ec.get("status", {}).get("options") or "").split("\n") if o]
if statuses != list(C.STATUSES):
    fail.append("Employee Contract.status must offer exactly contract_rules.STATUSES: %s" % statuses)
for name in ("status", "renewed_by", "alerts_sent", "decision_remarks"):
    if not (ec.get(name, {}).get("allow_on_submit") and ec.get(name, {}).get("read_only")):
        fail.append("Employee Contract.%s is set on a submitted contract by the system: read-only and allow_on_submit" % name)
for name, (fieldtype, options) in {"employee": ("Link", "Employee"), "employment_type": ("Link", "Employment Type"),
                                   "start_date": ("Date", None), "end_date": ("Date", None), "signed_on": ("Date", None),
                                   "signed_contract": ("Attach", None), "renewal_of": ("Link", "Employee Contract"),
                                   "contract_template": ("Link", "Contract Template"), "terms": ("Text Editor", None),
                                   "branch": ("Link", "Branch")}.items():
    if (ec.get(name, {}).get("fieldtype"), ec.get(name, {}).get("options") or None) != (fieldtype, options):
        fail.append("Employee Contract.%s must be %s %s" % (name, fieldtype, options or ""))
if ec.get("terms", {}).get("fetch_from") != "contract_template.contract_terms" or ec.get("branch", {}).get("fetch_from") != "employee.branch":
    fail.append("the terms come from the Contract Template, the branch from the Employee (Branch permissions apply)")
perms = {p["role"]: p for p in EC["permissions"]}
if not all((perms.get("HR User") or {}).get(k) for k in ("read", "write", "create", "submit")):
    fail.append("the HR Officer (HR User) prepares and submits contracts")
controller = open(os.path.join(folder, "employee_contract.py"), encoding="utf-8").read()
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        contracts.%s(self)" % (method, method) not in controller:
        fail.append("the Employee Contract controller must hand %s to contracts.%s" % (method, method))
js = open(os.path.join(folder, "employee_contract.js"), encoding="utf-8").read()
glue = read("hrms_addon", "hrms_addon", "contracts.py")
for method in re.findall(r'xcall\("hrms_addon\.hrms_addon\.contracts\.(\w+)"', js):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % method, glue):
        fail.append("employee_contract.js calls %s, which is not a whitelisted POST method" % method)
if sorted(re.findall(r'xcall\("hrms_addon\.hrms_addon\.contracts\.(\w+)"', js)) != ["make_renewal", "mark_not_renewed"]:
    fail.append("the contract form offers Renew and Do Not Renew")
running = re.search(r"const running = \[(.*?)\]\.includes\(frm\.doc\.status\)", js)
if not running or sorted(re.findall(r'"([^"]+)"', running.group(1))) != sorted([C.ACTIVE, C.EXPIRING, C.EXPIRED, C.NOT_RENEWED]):
    fail.append("Renew is offered on a running contract, one not renewed too (HR may change its mind)")
if js.find('if (frm.doc.status === "Not Renewed") {') == -1 or \
        js.find('if (frm.doc.status === "Not Renewed") {') > js.find('__("Do Not Renew"),'):
    fail.append("Do Not Renew is not offered again on a contract already not renewed")
custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
months = next((f for f in custom if f["dt"] == "Employment Type" and f["fieldname"] == "custom_contract_months"), {})
if months.get("fieldtype") != "Int":
    fail.append("Employment Type.custom_contract_months (the usual contract length) must be an Int")
employee = upstream_doctype("Employee")
if employee and "contract_end_date" not in {f["fieldname"] for f in employee["fields"]}:
    fail.append("Employee.contract_end_date is gone upstream")
template = upstream_doctype("Contract Template")
if template and "contract_terms" not in {f["fieldname"] for f in template["fields"]}:
    fail.append("Contract Template.contract_terms is gone upstream")
print("doctype: statuses, the fields the system sets after submit, HR's rights, Renew and Do Not Renew wired")

# ── 4. The glue ───────────────────────────────────────────────────────
for needle, why in (
    ('if not doc.get("end_date") and months and doc.get("start_date") and doc.is_new():', "a new contract ends after the usual length"),
    ('"renewed_by": ("is", "not set")', "a renewed contract no longer counts"),
    ('"status": ["in", IN_FORCE],', "a contract not renewed still counts until its end"),
    ("IN_FORCE = LIVE + (rules.NOT_RENEWED,)", "in force: the live contracts and those not renewed"),
    ('others = [other for other in others if other.name != doc.get("renewal_of")]', "a renewal does not overlap what it renews"),
    ('"submitting": doc.docstatus == 1,', "the signed copy is needed to submit"),
    ('frappe.db.set_value("Employee", doc.employee, "contract_end_date", doc.get("end_date"))', "the Employee's Contract End Date"),
    ('{"renewed_by": doc.name, "status": rules.RENEWED}', "a renewal marks what it renews Renewed"),
    ('doc.db_set("status", rules.CANCELLED, update_modified=False)', "a cancelled contract says so"),
    ("status = rules.contract_status(1, end, today(), not_renewed=bool(reason))",
     "a cancelled renewal puts back Not Renewed where HR had decided so"),
    ('old.check_permission("write")', "Renew needs write on the contract"),
    ("if old.get(\"renewed_by\"):\n        return old.renewed_by", "one renewal per contract"),
    ('frappe.db.get_value("Employee Contract", {"renewal_of": old.name, "docstatus": 0}, "name")', "a draft renewal is reused"),
    ("start, end = rules.renewal_dates(old.end_date, _usual_months(old.employment_type))", "the renewal's dates"),
    ('frappe.throw(_("Say why the contract is not renewed."))', "a reason for not renewing"),
    ('doc.db_set({"status": rules.NOT_RENEWED, "decision_remarks": remarks.strip()})', "Not Renewed is recorded"),
    ("print the Expiry of Contract letter and follow the ", "HR is told the next steps"),
    ('filters={"docstatus": 1, "status": ["in", LIVE]}', "the daily job watches the live contracts"),
    ("due = [] if contract.employee in gone else rules.alerts_due(contract.end_date, day, alert_days, contract.alerts_sent)",
     "the alerts due, none for an employee who has left"),
    ('filters={"name": ["in", [c.employee for c in contracts]], "status": ["!=", "Active"]}', "who has left"),
    ('updates["alerts_sent"] = rules.record_alerts(contract.alerts_sent, due)', "each alert sent once"),
    ("frappe.db.set_value(\"Employee Contract\", contract.name, updates, update_modified=False)", "without touching Last Modified"),
    ("people.hr_officers(contract.branch, contract.department)", "the contract's branch HR Officer is told"),
    ('if frappe.db.exists("Employee Contract", {"employee": employee, "docstatus": ["!=", 2]}):',
     "the onboarding drafts a contract only when there is none"),
):
    if needle not in glue:
        fail.append("contracts.py: %s (%r not found)" % (why, needle))
print("glue: end dates, overlaps, the Employee's end, renew, do not renew, the daily alerts, the onboarding's draft")

# ── 5. Hooks and the report ───────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "hrms_addon.hrms_addon.contracts.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []) \
        or not re.search(r"^def daily\(\):", glue, re.M):
    fail.append("the scheduler runs contracts.daily every day")
if (hooks.get("override_doctype_dashboards") or {}).get("Employee") != "hrms_addon.hrms_addon.onboarding.employee_dashboard" \
        or '"items": ["Onboarding Review", "Probation Evaluation", "Employee Contract"]' not in read("hrms_addon", "hrms_addon", "onboarding.py"):
    fail.append("the Employee's Connections list its reviews, evaluations and contracts")
report_dir = os.path.join(APP, "report", "contract_expiry_status")
report = json.load(open(os.path.join(report_dir, "contract_expiry_status.json"), encoding="utf-8"))
if (report.get("report_type"), report.get("ref_doctype"), report.get("is_standard"), report.get("module"), report.get("name")) \
        != ("Script Report", "Employee Contract", "Yes", "HRMS Addon", "Contract Expiry Status"):
    fail.append("Contract Expiry Status must be a standard Script Report on Employee Contract")
if not {"HR User", "HR Manager"} <= {r["role"] for r in report.get("roles", [])}:
    fail.append("the HR Officer and the HR Manager open the report")
report_py = open(os.path.join(report_dir, "contract_expiry_status.py"), encoding="utf-8").read()
if "frappe.get_list(" not in report_py:
    fail.append("the report reads through Frappe's permissions (get_list), so a branch sees its own contracts")
selected = {f.split(" as ")[-1] for f in re.findall(r'"([a-z_ ]+)"', re.search(r"fields=\[(.*?)\]", report_py, re.S).group(1))}
columns = set(re.findall(r'"fieldname": "(\w+)"', report_py))
if columns - selected - {"days_left"}:
    fail.append("report columns without data: %s" % sorted(columns - selected - {"days_left"}))
for name in selected - {"contract"}:
    if name not in ec:
        fail.append("the report reads Employee Contract.%s, which does not exist" % name)
if not os.path.exists(os.path.join(report_dir, "__init__.py")) or "frappe.query_reports[\"Contract Expiry Status\"]" not in \
        open(os.path.join(report_dir, "contract_expiry_status.js"), encoding="utf-8").read():
    fail.append("the report needs its __init__.py and its filters script")
print("hooks and report: the daily job, the Employee's connections, Contract Expiry Status by branch")

# ── 6. Print formats ──────────────────────────────────────────────────
settings = {f["fieldname"] for f in json.load(open(os.path.join(APP, "doctype", "onboarding_settings", "onboarding_settings.json"),
                                                   encoding="utf-8"))["fields"]}
employee_fields = ({f["fieldname"] for f in employee["fields"]} if employee else set()) \
    | {f["fieldname"] for f in custom if f["dt"] == "Employee"}
for name, needles, signer in (
    ("Employment Contract", ("EMPLOYMENT CONTRACT", "Terms and Conditions", "For Luuka Plastics Limited"), None),
    ("Contract Renewal Letter", ("RE: CONTRACT RENEWAL", "remain the same", "Witness Legal Manager"), "executive_director"),
    ("Expiry of Contract", ("RE: EXPIRY OF YOUR EMPLOYMENT CONTRACT", "Pay for notice not served", "company property"), "head_of_hr"),
):
    folder_name = name.lower().replace(" ", "_")
    path = os.path.join(APP, "print_format", folder_name, folder_name + ".json")
    pf = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    html = pf.get("html") or ""
    if (pf.get("doc_type"), pf.get("standard"), pf.get("print_format_type")) != ("Employee Contract", "Yes", "Jinja"):
        fail.append("%s must be a standard Jinja print format of Employee Contract" % name)
    for block in ("for", "if", "macro"):
        if len(re.findall(r"{%-?\s*" + block + r"\b", html)) != len(re.findall(r"{%-?\s*end" + block + r"\b", html)):
            fail.append("%s: unbalanced {%% %s %%} blocks" % (name, block))
    for needle in needles:
        if needle not in html:
            fail.append("%s must carry %r" % (name, needle))
    if signer and 'signatory("%s"' % signer not in html:
        fail.append("%s is signed by Onboarding Settings.%s" % (name, signer))
    for setting in re.findall(r'signatory\("(\w+)"', html):
        if setting not in settings:
            fail.append("%s signs with Onboarding Settings.%s, which does not exist" % (name, setting))
    for field in set(re.findall(r"\bdoc\.([a-z_]+)", html)) - {"get_formatted", "name", "creation", "modified"}:
        if field not in ec:
            fail.append("%s prints Employee Contract.%s, which does not exist" % (name, field))
    for field in set(re.findall(r"\bemployee\.([a-z_]+)", html)) - {"name"}:
        if employee_fields and field not in employee_fields:
            fail.append("%s prints Employee.%s, which does not exist" % (name, field))
    raw = [m for m in re.findall(r"{{-?\s*(doc|employee)\.([a-z_]+)", html) if m not in (("doc", "terms"), ("doc", "get_formatted"))]
    if raw:
        fail.append("%s must print text through v() so it is escaped (only the terms are HTML): %s" % (name, raw[:3]))
    if "MUGEERE" in html.upper() or "LWOTO" in html.upper():
        fail.append("%s names a person: the signatory comes from Onboarding Settings" % name)
print("print formats: the contract, the renewal and expiry letters; signatories from the settings, fields exist")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CONTRACT CHECKS PASSED")
