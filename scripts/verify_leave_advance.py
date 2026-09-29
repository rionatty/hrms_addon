"""Verify the Leave Advance against Luuka's own rules, without a bench:

    python scripts/verify_leave_advance.py

The minutes of 16 and 20 July 2026, §4.4: the Accounts Manager works out
60% of gross (for the Per Meter category, of the average gross of the
previous two months) and records it on the leave form; the Payroll Officer
sends Finance an Excel file of employee number, name, bank code, account
number and amount; only regular employees with no bank or company loan,
taking more than 19 days of accrued leave, qualify. The Leave Advance is
its own document, apart from the loans and the other advances.

  1  the minutes' numbers, the gross, what may be advanced, who qualifies
  2  the months it is taken back in, where it stands, the run, the file
  3  the workflow: HR, then the Accounts Manager
  4  the documents: the advance, its deductions, the run, the settings
  5  the glue: raised from the approved leave, the amount on the form, one
     bank entry, the deductions on the payroll, the payroll marking them
  6  apart from the loans: Employee Advance makes none, the search bar and
     Advance Settings no longer offer it, the leave form links the new one
  7  what Frappe HR and ERPNext must still do for this to hold
"""
import ast
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


def upstream(*parts):
    path = os.path.join(APPS_ROOT, *parts)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.loads(read("hrms_addon", "hrms_addon", "doctype", folder, folder + ".json"))


def fields_of(spec):
    return {f["fieldname"]: f for f in spec["fields"]}


def expect(label, errors, needle=None):
    if needle is None:
        if errors:
            fail.append("%s: expected no reason, got %s" % (label, errors))
    elif not any(needle in error for error in errors):
        fail.append("%s: expected a reason containing %r, got %s" % (label, needle, errors))


R = load("leave_advance_rules")
W = load("leave_advance_approval")
print("loaded leave_advance_rules.py and leave_advance_approval.py without Frappe")

# ── 1. The minutes' numbers; the gross; who qualifies ─────────────────
for key, value, why in (("advance_percent", 60.0, "the Accounts Manager calculates 60% of gross salary"),
                        ("per_meter_months", 2, "the average of the previous two months' gross"),
                        ("more_than_days", 19, "those taking more than 19 accrued days of leave"),
                        ("regular_only", 1, "applicable only to regular employees"),
                        ("no_loans", 1, "no existing bank or company loans"),
                        ("instalments", 1, "taken back from one month's pay unless agreed otherwise"),
                        ("raise_on_approval", 1, "raised as the leave is approved")):
    if R.DEFAULTS.get(key) != value:
        fail.append("%s should default to %r: %s (it is %r)" % (key, value, why, R.DEFAULTS.get(key)))
S = R.settings_from({})
if R.settings_from({"advance_percent": 0, "more_than_days": "0"})["more_than_days"] != 0 \
        or R.settings_from({"advance_percent": ""})["advance_percent"] != 60.0 \
        or R.settings_from({"not_regular_types": ["Casual", None]})["not_regular_types"] != ["Casual"]:
    fail.append("settings_from: a saved nought stays nought, a blank takes the default, the non-regular types kept")
expect("settings as the minutes set them", R.settings_errors(S))
expect("a percentage over 100", R.settings_errors(dict(S, advance_percent=120)), "no more than 100%")
expect("the usual months above the most", R.settings_errors(dict(S, instalments=4, max_instalments=3)), "cannot be more")
if R.gross_basis(R.MONTHLY, 1000000) != (1000000.0, "the monthly gross from the salary structure, UGX 1,000,000"):
    fail.append("gross_basis: a monthly employee's gross is the salary structure's: %s" % (R.gross_basis(R.MONTHLY, 1000000),))
if R.gross_basis(R.PER_METER, 1000000, [700000, 900000, 5000000], 2) != (800000.0, "the average gross of the last 2 month(s), UGX 800,000"):
    fail.append("gross_basis: Per Meter, the average of the last two months' paid gross only")
basis = R.gross_basis(R.PER_METER, 1000000, [], 2)
if basis[0] != 1000000.0 or "no payslip yet" not in basis[1]:
    fail.append("gross_basis: Per Meter with no payslip yet falls back to the structure, saying so: %s" % (basis,))
if R.gross_basis(R.MONTHLY, 0) != (None, None) or R.allowed(None) is not None or R.allowed(800000) != 480000.0:
    fail.append("allowed: 60% of the gross, nothing when there is no gross")
GOOD = {"status": "Active", "employment_type": "Permanent", "bank_loan": False, "company_loan": 0,
        "leave_type": "Annual Leave", "earned_leave": True, "leave_days": 21, "outstanding": 0,
        "allowed": 600000, "amount": 600000, "instalments": 1}
expect("a regular employee with no loan taking 21 days of annual leave", R.eligibility_errors(GOOD, S))
for label, change, needle in (
    ("someone who has left", {"status": "Left"}, "Only an active employee"),
    ("a casual", {"employment_type": "Casual"}, "regular employees"),
    ("a bank loan", {"bank_loan": True}, "bank loan"),
    ("a company loan", {"company_loan": 150000}, "UGX 150,000 is still owed on a company loan"),
    ("sick leave", {"earned_leave": False, "leave_type": "Sick Leave"}, "for accrued leave; Sick Leave is not"),
    ("19 days", {"leave_days": 19}, "more than 19 days of accrued leave; this leave is 19"),
    ("an earlier one still owed", {"outstanding": 100000}, "earlier leave advance"),
    ("no salary to work from", {"allowed": None}, "No salary in force"),
    ("nothing asked", {"amount": 0}, "Say how much"),
    ("more than 60%", {"amount": 600001}, "The most that may be advanced is UGX 600,000, 60% of gross"),
    ("four months", {"instalments": 4}, "1 to 3 month(s)"),
    ("no months", {"instalments": 0}, "1 to 3 month(s)"),
):
    expect(label, R.eligibility_errors(dict(GOOD, **change), dict(S, not_regular_types=["Casual"])), needle)
expect("a casual where every type is regular", R.eligibility_errors(dict(GOOD, employment_type="Casual"), S))
expect("a loan where the rule is off", R.eligibility_errors(dict(GOOD, bank_loan=True), dict(S, no_loans=0)))
print("the rules: 60% of gross, the Per Meter average, who qualifies and why not")

# ── 2. The months, where it stands, the run, the file ────────────────
import datetime  # noqa: E402

D = datetime.date
if (R.payroll_date("2027-02-21"), R.payroll_date("2027-02-25"), R.payroll_date("2027-02-26"),
        R.payroll_date("2027-12-31")) != (D(2027, 2, 25), D(2027, 2, 25), D(2027, 3, 25), D(2028, 1, 25)):
    fail.append("payroll_date: the payroll month closing on the 25th on or after the day")
if R.first_deduction("2027-02-21") != D(2027, 2, 25):
    fail.append("first_deduction: the payroll month the leave ends in")
schedule = R.recovery_schedule(600000, 3, "2027-02-21")
if schedule != [(D(2027, 2, 25), 200000.0), (D(2027, 3, 25), 200000.0), (D(2027, 4, 25), 200000.0)]:
    fail.append("recovery_schedule: equal months from the first, each on the 25th: %s" % schedule)
if [amount for _month, amount in R.recovery_schedule(100000, 3, "2027-02-01")] != [33333.33, 33333.33, 33333.34]:
    fail.append("recovery_schedule: the rounding goes on the last month")
if R.recovery_schedule(0, 1, "2027-02-01") or R.recovery_schedule(1000, 1, None):
    fail.append("recovery_schedule: nothing for nothing, nothing with no first month")
for args, want in (((0, "Draft"), R.DRAFT), ((0, R.PENDING), R.PENDING), ((0, R.REJECTED), R.REJECTED),
                   ((1, "Approved"), R.APPROVED), ((1, "Approved", True), R.PROCESSING),
                   ((1, "Approved", True, True, 600000, 0), R.PAID),
                   ((1, "Approved", True, True, 600000, 200000), R.RECOVERING),
                   ((1, "Approved", True, True, 600000, 600000), R.RECOVERED), ((2, "Approved"), R.CANCELLED)):
    if R.advance_status(*args) != want:
        fail.append("advance_status%s is %s, expected %s" % (args, R.advance_status(*args), want))
RUN = {"included": 2, "bank_account": "Stanbic - LPL", "payment_method": "Bank Transfer", "reference_no": "EFT-1",
       "reference_date": "2027-02-01"}
expect("a run ready for Finance", R.run_errors(RUN))
for label, change, needle in (("nobody paid", {"included": 0}, "Nobody"), ("no account", {"bank_account": None}, "bank or cash"),
                              ("no method", {"payment_method": ""}, "payment method"),
                              ("no reference", {"reference_no": ""}, "reference number"),
                              ("no account number", {"no_account": ["John Okello"]}, "No bank account number for: John Okello"),
                              ("paid elsewhere", {"not_approved": ["LPL-LVA-2027-00001"]}, "No longer waiting")):
    expect(label, R.run_errors(dict(RUN, **change)), needle)
expect("cash needs no reference", R.run_errors(dict(RUN, payment_method="Cash", reference_no="")))
rows = R.bank_file_rows([{"employee": "HR-EMP-00100", "employee_name": "John Okello", "bank_code": "031",
                          "bank_ac_no": "9030001", "amount": 600000, "include": 1, "branch": "Kawempe"},
                         {"employee": "HR-EMP-00101", "employee_name": "Left Out", "amount": 1, "include": 0}])
if rows != [["Employee No", "Employee Name", "Bank Code", "Account Number", "Amount"],
            ["HR-EMP-00100", "John Okello", "031", "9030001", 600000.0]]:
    fail.append("the file for Finance: exactly the minutes' five columns, for each line paid: %s" % rows)
if R.RECOVERY_COMPONENT != "Leave Advance Recovery" or R.ACCOUNT_NAME != "Leave Advances":
    fail.append("the deduction is Leave Advance Recovery, into Leave Advances")
print("the months: equal, on the 25th; where it stands; the run's checks; the five columns")

# ── 3. The workflow ───────────────────────────────────────────────────
if (W.DOCTYPE, W.STATE_FIELD, W.STATUS_FIELD) != ("Leave Advance", "workflow_state", "approval_status"):
    fail.append("the workflow is on Leave Advance, its state beside the advance's own status")
if W.next_states(W.DRAFT, ["HR User"]) != [(W.SUBMIT, W.PENDING_ACCOUNTS_MANAGER)] \
        or W.next_states(W.DRAFT, ["Accounts Manager"]) \
        or set(W.next_states(W.PENDING_ACCOUNTS_MANAGER, ["Accounts Manager"])) != {
            (W.APPROVE, W.APPROVED), (W.RETURN, W.DRAFT), (W.REJECT, W.REJECTED)} \
        or W.next_states(W.PENDING_ACCOUNTS_MANAGER, ["HR User", "HR Manager"]):
    fail.append("HR send it on; only the Accounts Manager approves, returns or refuses it")
if (W.APPROVED, "1") not in [(row["state"], row.get("doc_status")) for row in W.STATES]:
    fail.append("approval submits the advance")
expect("a return with no remarks", W.step_errors(W.PENDING_ACCOUNTS_MANAGER, W.DRAFT, {"qualifies": 1}), "remarks")
expect("a refusal with no remarks", W.step_errors(W.PENDING_ACCOUNTS_MANAGER, W.REJECTED, {}), "remarks")
expect("sent on when it does not qualify", W.step_errors(W.DRAFT, W.PENDING_ACCOUNTS_MANAGER, {"qualifies": 0}),
       "does not qualify")
expect("approved when it does not qualify", W.step_errors(W.PENDING_ACCOUNTS_MANAGER, W.APPROVED, {"qualifies": 0}),
       "does not qualify")
expect("sent on when it qualifies", W.step_errors(W.DRAFT, W.PENDING_ACCOUNTS_MANAGER, {"qualifies": 1}))
stamps = W.compute_stamps(W.PENDING_ACCOUNTS_MANAGER, W.APPROVED, "am@luuka", "2027-01-27", {})
if stamps != {"accounts_manager_by": "am@luuka", "accounts_manager_on": "2027-01-27"} \
        or W.compute_stamps(W.PENDING_ACCOUNTS_MANAGER, W.DRAFT, "am@luuka", "2027-01-27", stamps) != dict.fromkeys(stamps):
    fail.append("the Accounts Manager signs as it is approved; a return clears it")
print("workflow: HR, then the Accounts Manager, who signs")

# ── 4. The documents ──────────────────────────────────────────────────
advance = doctype("Leave Advance")
f = fields_of(advance)
if not advance.get("is_submittable") or advance.get("autoname") != "naming_series:":
    fail.append("Leave Advance is submittable and numbered")
for name, kind, options in (("leave_application", "Link", "Leave Application"), ("employee", "Link", "Employee"),
                            ("amount", "Currency", None), ("recoveries", "Table", "Leave Advance Recovery"),
                            ("processing", "Link", "Leave Advance Processing"), ("journal_entry", "Link", "Journal Entry"),
                            ("workflow_state", "Link", "Workflow State")):
    if (f.get(name, {}).get("fieldtype"), f.get(name, {}).get("options")) != (kind, options):
        fail.append("Leave Advance.%s must be %s %s" % (name, kind, options or ""))
if [o for o in (f["status"].get("options") or "").split("\n") if o] != list(R.STATUSES):
    fail.append("Leave Advance.status offers exactly the rules' statuses")
if {o for o in (f["approval_status"].get("options") or "").split("\n") if o} != {row["status"] for row in W.STATES}:
    fail.append("Leave Advance.approval_status offers exactly the workflow's statuses")
for name in ("instalments", "first_deduction", "recoveries", "status", "outstanding", "recovered_amount", "processing",
             "journal_entry", "paid_on"):
    if not f.get(name, {}).get("allow_on_submit"):
        fail.append("Leave Advance.%s changes after approval: allow_on_submit" % name)
for name in ("gross_pay", "allowed_amount", "qualifies", "eligibility_remarks", "gross_basis"):
    if not f.get(name, {}).get("read_only"):
        fail.append("Leave Advance.%s is worked out: read-only" % name)
perms = {p["role"]: p for p in advance["permissions"]}
if not (perms.get("Accounts Manager", {}).get("submit") and perms.get("HR User", {}).get("create")
        and not perms.get("HR User", {}).get("submit") and perms.get("Payroll Officer", {}).get("read")
        and perms.get("Finance Officer", {}).get("read")):
    fail.append("HR raise it, the Accounts Manager approves it; Payroll and Finance read it")
recovery = fields_of(doctype("Leave Advance Recovery"))
for name in ("payroll_date", "amount", "additional_salary", "recovered"):
    if not recovery.get(name, {}).get("allow_on_submit"):
        fail.append("Leave Advance Recovery.%s is written after approval: allow_on_submit" % name)
run = doctype("Leave Advance Processing")
g = fields_of(run)
if not run.get("is_submittable") or g.get("employees", {}).get("options") != "Leave Advance Processing Employee":
    fail.append("Leave Advance Processing is submittable, its lines the leave advances")
if [o for o in (g["status"].get("options") or "").split("\n") if o] != list(R.RUN_STATUSES):
    fail.append("Leave Advance Processing.status offers exactly the rules' run statuses")
if [o for o in (g["payment_method"].get("options") or "").split("\n") if o] != list(R.PAYMENT_METHODS):
    fail.append("the payment methods are the rules'")
if not g.get("journal_entry", {}).get("allow_on_submit") or g.get("get_advances", {}).get("fieldtype") != "Button":
    fail.append("the run has its Get Leave Advances button and keeps its bank entry")
run_perms = {p["role"]: p for p in run["permissions"]}
if not (run_perms.get("Payroll Officer", {}).get("create") and run_perms.get("Payroll Officer", {}).get("submit")
        and run_perms.get("Finance Officer", {}).get("read")):
    fail.append("the Payroll Officer prepares and submits the run; Finance read it")
line = fields_of(doctype("Leave Advance Processing Employee"))
for name in ("employee", "employee_name", "bank_code", "bank_ac_no", "amount"):
    if not line.get(name, {}).get("in_list_view"):
        fail.append("the run's lines show %s, one of the file's columns" % name)
if sum(int(field.get("columns") or 0) for field in line.values() if field.get("in_list_view")) > 10:
    fail.append("the run's lines fit the grid's ten columns")
for name in ("leave_advance", "leave_advance_processing", "leave_management_settings"):
    if not os.path.exists(os.path.join(APP, "doctype", name, name + ".js")):
        fail.append("%s has its form script" % name)
print("documents: the advance, its months, the run and its lines, who does what")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "leave_advances.py")
for needle, why in (
    ('frappe.db.savepoint("hrms_addon_leave_advance")', "raising it never stops the leave"),
    ("return _raise(leave, send=True)", "it is raised and sent as the leave is approved"),
    ("if not leave_accrual.settings().raise_on_approval:", "unless the settings say HR raise it"),
    ("if send and advance.qualifies:\n", "only one that qualifies is sent on"),
    ("advance = frappe.get_doc(ADVANCE, advance.name)\n        advance.workflow_state = rules.PENDING",
     "sent on from the draft as stored, so the workflow sees the step"),
    ('"first_deduction": rules.first_deduction(leave.to_date),', "taken back from the month the leave ends in"),
    ("monthly = pay.monthly_gross(doc.employee, leave.from_date)", "the gross from the salary structure (pay.py)"),
    ('"end_date": ["<", leave.from_date]},', "the Per Meter average is of the months before the leave"),
    ('pluck="gross_pay", order_by="end_date desc", limit=max(int(s.per_meter_months), 1))', "the latest months"),
    ('"earned_leave": leave_accrual_rules.earns(leave_accrual.leave_type_rule(leave.leave_type)),',
     "accrued leave is Frappe HR's earned leave"),
    ('errors.insert(0, _("The leave is not approved yet."))', "only for an approved leave"),
    ('if doc.get("paid_on"):\n        _totals(doc)\n        return', "once paid, the months stay as they are"),
    ('"custom_leave_advance": doc.name, "custom_advance_amount": doc.amount,', "the amount recorded on the leave form"),
    ('frappe.throw(_("The deductions are on the payroll already.', "months not changed once on the payroll"),
    ('entry.append("accounts", {"account": account, "debit_in_account_currency": flt(row.amount),',
     "one bank entry, a line an advance"),
    ('entry.append("accounts", {"account": doc.bank_account, "credit_in_account_currency": doc.total_amount})',
     "paid from the chosen account"),
    ('"overwrite_salary_structure_amount": 0, "ref_doctype": ADVANCE, "ref_docname": advance.name,',
     "each month an Additional Salary referring to the advance"),
    ('frappe.throw(_("The payroll has already taken back part of {0}. The payment stays.")',
     "a payment the payroll has taken from stays"),
    ('frappe.throw(_("Cancel the bank entry {0} first.").format(doc.journal_entry), title=_(RUN))',
     "a run whose bank entry is submitted is not cancelled"),
    ("rows = rules.bank_file_rows([row.as_dict() for row in doc.get(\"employees\") or []])", "the file is the rules'"),
    ('frappe.response["filecontent"] = make_xlsx(rows, "Leave Advances").getvalue()', "as an Excel file"),
    ('"depends_on_payment_days": 0,', "a deduction not cut by the days paid"),
    ('beside = frappe.get_cached_value("Company", company, "default_employee_advance_account")',
     "Leave Advances is made beside the employee advance account"),
):
    if needle not in glue:
        fail.append("leave_advances.py: %s" % why)
if "party_type" in glue or '"party":' in glue:
    fail.append("the leave advance account is not a receivable: no party on its lines (Frappe HR's payroll books "
                "the recovery without one)")
for name, methods in (("raise_advance", 'methods=["POST"]'), ("get_advances", 'methods=["POST"]'), ("bank_file", "")):
    if not re.search(r"@frappe\.whitelist\(%s\)\ndef %s\(" % (re.escape(methods), name), glue):
        fail.append("leave_advances.%s must be whitelisted (%s)" % (name, methods or "GET"))
for name, needle in (("get_advances", 'doc.check_permission("write")'), ("bank_file", 'doc.check_permission("read")'),
                     ("raise_advance", 'frappe.has_permission(ADVANCE, "create", throw=True)')):
    body = glue.split("def %s(" % name)[1].split("\ndef ")[0]
    if needle not in body:
        fail.append("leave_advances.%s checks the caller may act" % name)
accrual = read("hrms_addon", "hrms_addon", "leave_accrual.py")
if 'found.account_type in ("Receivable", "Payable") or found.root_type != "Asset" or found.is_group' not in accrual:
    fail.append("Leave Management Settings refuses a receivable, payable, non-asset or group account")
leave_glue = read("hrms_addon", "hrms_addon", "leave.py")
if "leave_advances.on_leave_approved(doc)" not in leave_glue.split("def application_on_submit")[1].split("\ndef ")[0]:
    fail.append("the approved leave raises its Leave Advance")
recoveries = read("hrms_addon", "hrms_addon", "recoveries.py")
if '"Leave Advance Recovery": ("Leave Advance",),' not in recoveries or '"Leave Advance": leave_advances.refresh_recovered' not in recoveries:
    fail.append("the Salary Slip marks the months of a leave advance as recovered (recoveries.py)")
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
je = (hooks.get("doc_events") or {}).get("Journal Entry") or {}
if "hrms_addon.hrms_addon.leave_advances.payment_on_submit" not in je.get("on_submit", []) \
        or "hrms_addon.hrms_addon.leave_advances.payment_on_cancel" not in je.get("on_cancel", []):
    fail.append("Finance submitting or cancelling the bank entry reaches the leave advances")
if "hrms_addon.hrms_addon.leave_advances.setup_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the Leave Advance workflow is built on every migrate")
for name, handed in (
    ("leave_advance", (("validate", "advance_validate"), ("before_update_after_submit", "advance_before_update"),
                       ("on_submit", "advance_on_submit"), ("on_cancel", "advance_on_cancel"))),
    ("leave_advance_processing", (("validate", "run_validate"), ("before_submit", "run_before_submit"),
                                  ("on_submit", "run_on_submit"), ("on_cancel", "run_on_cancel"))),
):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    for method, glue_function in handed:
        if "    def %s(self):\n        leave_advances.%s(self)" % (method, glue_function) not in controller:
            fail.append("the %s controller hands %s to leave_advances.%s" % (name, method, glue_function))
print("glue: raised from the leave, worked out, approved, paid in one bank entry, taken back by the payroll")

# ── 6. Apart from the loans ───────────────────────────────────────────
advances = read("hrms_addon", "hrms_addon", "advances.py")
if "if doc.custom_advance_type == rules.LEAVE_ADVANCE and doc.is_new():" not in advances or "def from_leave(" in advances:
    fail.append("Employee Advance makes no new leave advance")
if '"Leave Advance"' in read("hrms_addon", "public", "js", "hrms_addon_search.js"):
    fail.append("the search bar no longer sends Leave Advance to Employee Advance")
settings = fields_of(doctype("Advance Settings"))
if not settings.get("leave_section", {}).get("hidden"):
    fail.append("Advance Settings no longer shows the leave advance rules: they are in Leave Management Settings")
custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
by_name = {c["name"]: c for c in custom}
if (by_name.get("Leave Application-custom_leave_advance", {}).get("options") != "Leave Advance"
        or by_name.get("Leave Application-custom_advance_amount", {}).get("label") != "Leave Advance Amount"
        or by_name.get("Leave Application-custom_salary_requested_in_advance", {}).get("label") != "Leave Advance Requested"
        or by_name.get("Leave Application-custom_advance", {}).get("depends_on") != "eval:doc.custom_advance"):
    fail.append("the leave form says Leave Advance throughout, and shows an old Employee Advance only where there is one")
if (by_name.get("Employee-custom_bank_code", {}).get("fieldtype"), by_name.get("Employee-custom_bank_code", {}).get(
        "insert_after")) != ("Data", "custom_bank_account_name"):
    fail.append("the Employee has a Bank Code beside the bank details, for the file")
js = read("hrms_addon", "public", "js", "leave_application.js")
if 'frappe.set_route("Form", "Leave Advance", advance)' not in js or '"Employee Advance"' in js:
    fail.append("the leave form's buttons open the Leave Advance")
run_js = read("hrms_addon", "hrms_addon", "doctype", "leave_advance_processing", "leave_advance_processing.js")
if "hrms_addon.hrms_addon.leave_advances.bank_file" not in run_js or "leave_advances.get_advances" not in run_js:
    fail.append("the run downloads the file and gets the advances")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
loans = nav.split('"Loans": [')[1].split("],\n")[0] if '"Loans": [' in nav else ""
if '"Leave Advance"' in loans or '("Leave Advance", "Leave Advance", DOCTYPE, None, "hr-calendar"),' not in nav:
    fail.append("the Leave Advance is reached from the Leaves page, not the loans")
print("apart: Employee Advance, the search bar and Advance Settings leave it; the leave form links it")

# ── 7. What Frappe HR and ERPNext must still do ───────────────────────
payroll = upstream("hrms", "hrms", "payroll", "doctype", "payroll_entry", "payroll_entry.py")
if payroll:
    if 'if ref_doctype == "Employee Advance":\n\t\t\t\treturn ref_docname' not in payroll:
        fail.append("Frappe HR's payroll books other advances against the employee now: the leave advance account "
                    "could be a receivable again")
    additional = upstream("hrms", "hrms", "payroll", "doctype", "additional_salary", "additional_salary.py") or ""
    if 'if self.ref_doctype == "Employee Advance":\n\t\t\tself.validate_employee_advance_return()' not in additional:
        fail.append("Frappe HR's Additional Salary checks another reference now: re-check the leave advance's")
    component = json.loads(upstream("hrms", "hrms", "payroll", "doctype", "salary_component",
                                    "salary_component.json") or "{}")
    if "depends_on_payment_days" not in {x["fieldname"] for x in component.get("fields", [])}:
        fail.append("Salary Component has no depends_on_payment_days upstream")
    je_account = json.loads(upstream("erpnext", "erpnext", "accounts", "doctype", "journal_entry_account",
                                     "journal_entry_account.json") or "{}")
    if "user_remark" not in {x["fieldname"] for x in je_account.get("fields", [])}:
        fail.append("a Journal Entry line no longer has its own remark")
    xlsx = upstream("frappe", "frappe", "utils", "xlsxutils.py") or ""
    if "def make_xlsx(" not in xlsx:
        fail.append("frappe.utils.xlsxutils.make_xlsx is gone")
    print("upstream: the payroll's party rule, Additional Salary, the component, the entry's lines, the Excel writer")
else:
    print("upstream checks SKIPPED (no %s)" % APPS_ROOT)

print()
if fail:
    print("FAILURES:")
    for item in fail:
        print("  -", item)
    sys.exit(1)
print("ALL LEAVE ADVANCE CHECKS PASSED")
