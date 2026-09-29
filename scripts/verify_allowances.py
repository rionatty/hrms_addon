"""Verify the Allowance Request without a bench:

    python scripts/verify_allowances.py

Luuka's revised flow chart 4.3 (Allowance Application): the employee
creates the request, the HR Officer is told; Qualified?; the Supervisor,
the HR Officer and the General Manager approve and Accounts are told;
Accounts pay it and set it to Paid, and the HR Officer is told. The paper
is LPL.HR.31, the Employee Travel Allowance form; the minutes (§4.7) add the
airtime, travel and acting allowances, acting ones paid through the payroll.

The allowance is its own document. It was kept on Frappe HR's Travel
Request once, and the user said a travel request is not an allowance.

  1  the rules: the types, a line, the totals, who qualifies, what Accounts
     must give, the journal entry, the payroll month
  2  the workflow: the chart's four signatures, returns and refusals
  3  the documents: the request, its lines, the type and its accounts;
     Travel Request is Frappe HR's own again
  4  the glue: the scale read before the lines are costed, the entry and
     the payroll additions on Pay, both undone on Cancel, who is told
  5  the move: the patch copies what was on Travel Request and takes the
     old workflow and fields off it
  6  wiring: the controllers, seeds, jobs, the way in, the signature
  7  what Frappe HR and ERPNext must still do for this to hold
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
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
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
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def upstream_doctype(name):
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"),
                         recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in (spec or {}).get("fields", [])}


def function(source, name):
    match = re.search(r"(?m)^def %s\(.*?(?=^def |^@|^# ──|\Z)" % name, source, re.S)
    return match.group(0) if match else ""


def expect(label, got, *needles):
    if not needles:
        if got:
            fail.append("%s: expected no reason, got %s" % (label, got))
        return
    if len(got) != len(needles):
        fail.append("%s: expected %d reason(s), got %s" % (label, len(needles), got))
    for needle in needles:
        if not any(needle in message for message in got):
            fail.append("%s: expected a reason containing %r, got %s" % (label, needle, got))


def hooks_dict():
    tree = ast.parse(read("hrms_addon", "hooks.py"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


R, W = load("allowance_rules"), load("allowance_approval")
hooks = hooks_dict()
print("loaded allowance_rules.py and allowance_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if R.FIELD_LINES != ("Lodging", "Daily Allowance", "Conveyance", "Labour Charges", "Other Expenses"):
    fail.append("LPL.HR.31 prints five lines, in its own order: %s" % (R.FIELD_LINES,))
seeded = {row["allowance_type"]: row for row in R.SEED_TYPES}
if list(seeded) != list(R.FIELD_LINES) + ["Airtime Allowance", "Travel Allowance", "Acting Allowance"]:
    fail.append("the minutes' allowances: LPL.HR.31's five, then airtime, travel and acting: %s" % list(seeded))
if not all(seeded[name]["needs_trip"] for name in R.FIELD_LINES):
    fail.append("LPL.HR.31's lines ask for the trip")
if [seeded[name]["per_diem_column"] for name in ("Lodging", "Daily Allowance", "Conveyance")] \
        != ["Lodging", "Daily Allowance", "Conveyance"] or seeded["Labour Charges"]["per_diem_column"]:
    fail.append("lodging, the daily allowance and conveyance come off the per-diem scale; nothing else does")
if seeded["Acting Allowance"]["paid_through"] != R.PAYROLL or not seeded["Acting Allowance"]["needs_acting_for"]:
    fail.append("an acting allowance names whom the employee stands in for, and the payroll pays it (§4.7)")
if any(row["paid_through"] != R.ACCOUNTS for name, row in seeded.items() if name != "Acting Allowance"):
    fail.append("Accounts pay every other allowance")
if R.line_amount(3, 50000) != 150000 or R.line_amount(None, 20000) != 20000 or R.line_amount(2, 0) != 0:
    fail.append("a line is its days times its rate, or its rate where it has no days")
if R.trip_days("2026-10-01", "2026-10-03") != 3 or R.trip_days("2026-10-03", "2026-10-01") != 0:
    fail.append("a trip counts both its ends, and a backwards one counts nothing")
figures = R.totals([{"amount": 150000}, {"amount": 60000}, {"amount": 90000, "paid_through": "Payroll"}], 100000)
if figures != {"total": 300000, "through_accounts": 210000, "through_payroll": 90000, "less_advance": 100000,
               "balance": 110000}:
    fail.append("the foot of the form: the advance comes off what Accounts pay, the payroll's is apart: %s" % figures)
if R.totals([{"amount": 20000}], 50000)["balance"] != -30000:
    fail.append("an advance larger than the allowance is refunded: the balance goes negative")

GOOD = {"status": "Active", "employee": "E1", "purpose": "Delivery to Mbale", "start_date": "2026-10-01",
        "end_date": "2026-10-03",
        "lines": [{"allowance_type": "Lodging", "days": 2, "amount": 100000, "needs_trip": 1,
                   "paid_through": "Accounts"}]}
expect("a request that qualifies", R.eligibility_errors(GOOD))
expect("someone who left", R.eligibility_errors(dict(GOOD, status="Left")), "active employee")
expect("no purpose", R.eligibility_errors(dict(GOOD, purpose=" ")), "what the allowance is for")
expect("nothing asked for", R.eligibility_errors(dict(GOOD, lines=[])), "at least one allowance")
expect("a trip with no dates", R.eligibility_errors(dict(GOOD, start_date=None)), "dates the field work")
expect("a trip ending before it starts", R.eligibility_errors(dict(GOOD, end_date="2026-09-30")),
       "ends before it starts")
expect("more days than the trip", R.eligibility_errors(dict(GOOD, lines=[dict(GOOD["lines"][0], days=9)])),
       "the travel covers 3")
expect("a line worth nothing", R.eligibility_errors(dict(GOOD, lines=[dict(GOOD["lines"][0], amount=0)])),
       "comes to nothing")
expect("a type no longer paid", R.eligibility_errors(dict(GOOD, lines=[dict(GOOD["lines"][0], disabled=1)])),
       "no longer paid")
expect("airtime needs no trip", R.eligibility_errors({"status": "Active", "employee": "E1", "purpose": "Airtime",
                                                      "lines": [{"allowance_type": "Airtime Allowance",
                                                                 "amount": 30000}]}))
ACTING = {"status": "Active", "employee": "E1", "purpose": "Standing in", "acting_for": "E2",
          "acting_from": "2026-10-01", "acting_to": "2026-10-31",
          "lines": [{"allowance_type": "Acting Allowance", "amount": 200000, "needs_acting_for": 1,
                     "paid_through": "Payroll", "salary_component": "Acting Allowance"}]}
expect("an acting allowance that qualifies", R.eligibility_errors(ACTING))
expect("acting for nobody", R.eligibility_errors(dict(ACTING, acting_for=None)), "whom the employee stands in for")
expect("acting for themselves", R.eligibility_errors(dict(ACTING, acting_for="E1")), "cannot stand in for themselves")
expect("acting with no days", R.eligibility_errors(dict(ACTING, acting_to=None)), "acts from and to")
expect("the payroll with no component",
       R.eligibility_errors(dict(ACTING, lines=[dict(ACTING["lines"][0], salary_component=None)])),
       "set its salary component")
expect("an advance taken off", R.eligibility_errors(dict(GOOD, less_advance=50000, advance="EA-1",
                                                           advance_employee="E1", advance_left=50000)))
expect("an advance with none picked", R.eligibility_errors(dict(GOOD, less_advance=50000)), "Advance Taken")
expect("another employee's advance", R.eligibility_errors(dict(GOOD, less_advance=5, advance="EA-1",
                                                                 advance_employee="E9", advance_left=50)),
       "another employee's")
expect("more than the advance has left", R.eligibility_errors(dict(GOOD, less_advance=60000, advance="EA-1",
                                                                     advance_employee="E1", advance_left=50000)),
       "Only UGX 50,000")
if R.advance_left(300000, 100000, 50000) != 150000 or R.advance_left(0, 0, 0) != 0 or R.advance_left(10, 20) != 0:
    fail.append("an advance has left what was paid, less what was claimed and returned, never less than nothing")

PAY = {"balance": 100000, "through_accounts": 100000, "payment_account": "Stanbic - LPL",
       "payment_method": "Bank Transfer", "reference_no": "EFT-1", "reference_date": "2026-10-05",
       "paid_on": "2026-10-05", "account_ok": True, "account_currency_ok": True}
expect("a payment Accounts can make", R.payment_errors(PAY))
expect("paid on no day", R.payment_errors(dict(PAY, paid_on=None)), "when the allowance was paid")
expect("from no account", R.payment_errors(dict(PAY, payment_account=None)), "bank or cash account")
expect("from someone else's account", R.payment_errors(dict(PAY, account_ok=False)), "bank or cash account of the company")
expect("from a dollar account", R.payment_errors(dict(PAY, account_currency_ok=False)), "company's currency")
expect("no method", R.payment_errors(dict(PAY, payment_method=None)), "payment method")
expect("a transfer with no reference", R.payment_errors(dict(PAY, reference_no=None)), "reference number")
expect("cash needs no reference", R.payment_errors(dict(PAY, payment_method="Cash", reference_no=None)))
expect("an allowance with no expense account", R.payment_errors(dict(PAY, no_account=["Lodging"])),
       "expense account for Lodging")
expect("the advance covers it all: no bank", R.payment_errors(dict(PAY, balance=0, payment_account=None,
                                                                   payment_method=None)))
expect("a foreign request with no rate", R.payment_errors(dict(PAY, foreign=True, exchange_rate=0)), "exchange rate")
rows = R.journal_rows([{"expense_account": "Travel - LPL", "amount": 150000},
                       {"expense_account": "Travel - LPL", "amount": 30000},
                       {"expense_account": "Airtime - LPL", "amount": 20000},
                       {"amount": 90000, "paid_through": "Payroll"}], 50000)
if rows != {"expenses": [("Travel - LPL", 180000.0), ("Airtime - LPL", 20000.0)], "advance": 50000.0, "bank": 150000.0}:
    fail.append("the entry: an expense account a debit, the advance and the bank the credits, the payroll's apart: %s" % rows)
if R.journal_rows([{"expense_account": "Travel - LPL", "amount": 40000}], 50000)["bank"] != -10000:
    fail.append("an advance larger than the allowance: the refund comes into the bank")
if R.journal_rows([{"expense_account": "Travel - LPL", "amount": 100}], 0, 3700) != \
        {"expenses": [("Travel - LPL", 370000.0)], "advance": 0.0, "bank": 370000.0}:
    fail.append("a request in dollars is entered in shillings at the exchange rate")
if (str(R.payroll_date("2026-10-25")), str(R.payroll_date("2026-10-26")), str(R.payroll_date("2026-12-30"))) \
        != ("2026-10-25", "2026-11-25", "2027-01-25"):
    fail.append("the payroll month closes on the 25th")
if R.status_for(2, "Paid") != "Cancelled" or R.status_for(0, None) != "Draft" or R.status_for(1, "Paid") != "Paid":
    fail.append("the list shows where a request stands")
expect("a type the payroll pays, with its earning", R.type_errors({"paid_through": "Payroll",
                                                                   "salary_component": "Acting Allowance",
                                                                   "component_type": "Earning"}))
expect("the payroll with no component", R.type_errors({"paid_through": "Payroll"}), "needs its salary component")
expect("a deduction for an allowance", R.type_errors({"paid_through": "Payroll", "salary_component": "PAYE",
                                                      "component_type": "Deduction"}), "not an earning")
expect("an account of another company",
       R.type_errors({"paid_through": "Accounts", "accounts": [{"company": "LPL", "account": "X - O",
                                                                "account_company": "Other"}]}), "not an account of")
expect("a company twice",
       R.type_errors({"paid_through": "Accounts", "accounts": [{"company": "LPL", "account": "A", "account_company": "LPL"},
                                                               {"company": "LPL", "account": "B", "account_company": "LPL"}]}),
       "two expense accounts")
expect("a group account", R.type_errors({"paid_through": "Accounts", "accounts": [
    {"company": "LPL", "account": "Expenses", "account_company": "LPL", "is_group": 1}]}), "group account")
print("rules: the types, a line, the totals, who qualifies, what Accounts give, the entry, the payroll month")

# ── 2. The workflow ───────────────────────────────────────────────────
route, state = [W.DRAFT], W.DRAFT
while True:
    forward = [t for t in W.TRANSITIONS if t["state"] == state and t["action"] in (W.SUBMIT, W.APPROVE, W.PAY)]
    if not forward:
        break
    state = forward[0]["next_state"]
    route.append(state)
if route != [W.DRAFT, W.PENDING_SUPERVISOR, W.PENDING_HR, W.PENDING_GM, W.PENDING_ACCOUNTS, W.PAID]:
    fail.append("the request goes Supervisor, HR Officer, General Manager, then Accounts: %s" % route)
if (W.DOCTYPE, W.WORKFLOW_NAME, W.STATE_FIELD, W.STATUS_FIELD) != ("Allowance Request", "Allowance Request",
                                                                    "workflow_state", "status"):
    fail.append("the workflow is the Allowance Request's own")
for state in W.PENDING_STATES:
    if not [t for t in W.TRANSITIONS if t["state"] == state and t["action"] == W.RETURN]:
        fail.append("%s can return the request" % state)
if set(W.STAMPS) != set(W.PENDING_STATES) or set(W.ROLE_WAITING) != set(W.PENDING_STATES):
    fail.append("every desk is stamped, and knows whose it is")
if "Employee" not in W.PREPARERS:
    fail.append("the employee creates the request (step 1)")
if W.next_states(W.PENDING_ACCOUNTS, ("Accounts User",)) != [(W.PAY, W.PAID), (W.RETURN, W.DRAFT)]:
    fail.append("Accounts pay it or return it")
if W.next_states(W.PENDING_GM, ("Employee",)):
    fail.append("nobody may act on a desk that is not theirs")
paid_state = [row for row in W.STATES if row["state"] == W.PAID]
if not paid_state or any(row.get("doc_status") != "1" for row in paid_state):
    fail.append("Paid submits the request, which makes the payment")
if {t["allowed"] for t in W.TRANSITIONS if t["action"] == W.CANCEL} != {"HR Manager", "Accounts Manager"}:
    fail.append("the HR Manager or the Accounts Manager cancel a paid request")
expect("sent on without qualifying", W.step_errors(W.DRAFT, W.PENDING_SUPERVISOR, {}), "does not qualify")
expect("sent on, qualifying", W.step_errors(W.DRAFT, W.PENDING_SUPERVISOR, {"qualifies": 1}))
expect("returned without saying why", W.step_errors(W.PENDING_HR, W.DRAFT, {"qualifies": 1}), "Return Remarks")
expect("refused without saying why", W.step_errors(W.PENDING_GM, W.REJECTED, {}), "General Manager's remarks")
expect("paid, qualifying", W.step_errors(W.PENDING_ACCOUNTS, W.PAID, {"qualifies": 1}))
if any(W.compute_stamps(W.PENDING_GM, W.DRAFT, "x", "2026-10-05", {"supervisor_by": "a"}).values()):
    fail.append("a returned request clears every signature")
if W.compute_stamps(W.PENDING_SUPERVISOR, W.PENDING_HR, "sup@luuka", "2026-10-05", {})["supervisor_by"] != "sup@luuka":
    fail.append("the supervisor's approval is signed")
print("workflow: the chart's four signatures, returned and refused with reasons")

# ── 3. The documents ──────────────────────────────────────────────────
request = doctype("Allowance Request")
fields = fields_of(request)
if not request.get("is_submittable") or request.get("module") != "HRMS Addon":
    fail.append("the Allowance Request is a submittable document of this app's own")
for fieldname in ("employee", "employee_name", "badge_no", "grade", "department", "branch", "purpose", "lines",
                  "destination", "start_date", "start_time", "end_date", "end_time", "acting_for", "acting_from",
                  "acting_to", "total", "advance", "less_advance", "balance_due", "qualifies",
                  "eligibility_remarks", "supervisor_by", "hr_by", "gm_by", "accounts_by", "return_remarks",
                  "payment_account", "payment_method", "reference_no", "reference_date", "paid_on", "journal_entry",
                  "cost_center", "exchange_rate", "workflow_state", "status", "amended_from", "travel_request"):
    if fieldname not in fields:
        fail.append("the Allowance Request has no %s" % fieldname)
if fields.get("badge_no", {}).get("fetch_from") != "employee.attendance_device_id":
    fail.append("the badge number is the employee's device id, as the other forms read it")
if [o for o in fields.get("status", {}).get("options", "").split("\n") if o] != [
        W.DRAFT, W.PENDING_SUPERVISOR, W.PENDING_HR, W.PENDING_GM, W.PENDING_ACCOUNTS, W.PAID, W.REJECTED,
        W.CANCELLED]:
    fail.append("the status offers exactly the workflow's states")
if [o for o in fields.get("payment_method", {}).get("options", "").split("\n") if o] != list(R.PAYMENT_METHODS):
    fail.append("the payment methods are the rules' own")
for fieldname in ("total", "balance_due", "qualifies", "eligibility_remarks", "journal_entry", "paid_amount",
                  "status", "supervisor_by", "accounts_by"):
    if not fields.get(fieldname, {}).get("read_only"):
        fail.append("Allowance Request.%s is worked out, not typed" % fieldname)
if fields.get("travel_request", {}).get("options") != "Travel Request":
    fail.append("a request may name the travel request it is for, which stays Frappe HR's own")
perms = {p["role"]: p for p in request.get("permissions", [])}
if not perms.get("Employee", {}).get("create"):
    fail.append("the employee creates the request (step 1)")
for role in ("Supervisor", "Head of Department", "General Manager", "Accounts User", "Accounts Manager", "HR User"):
    if not perms.get(role, {}).get("submit"):
        fail.append("%s may submit: a refusal and the payment submit the request" % role)
line = fields_of(doctype("Allowance Request Line"))
for fieldname, source in (("paid_through", "allowance_type.paid_through"), ("needs_trip", "allowance_type.needs_trip"),
                          ("needs_acting_for", "allowance_type.needs_acting_for")):
    if line.get(fieldname, {}).get("fetch_from") != source:
        fail.append("a line reads %s from its type" % fieldname)
for fieldname in ("days", "rate", "amount", "remarks", "from_scale", "expense_account", "additional_salary"):
    if fieldname not in line:
        fail.append("an allowance line has no %s" % fieldname)
kind = doctype("Allowance Type")
kind_fields = fields_of(kind)
if [o for o in kind_fields.get("paid_through", {}).get("options", "").split("\n") if o] != list(R.PAID_THROUGH):
    fail.append("an Allowance Type is paid by Accounts or the payroll")
if [o for o in kind_fields.get("per_diem_column", {}).get("options", "").split("\n") if o] != list(R.PER_DIEM_COLUMNS):
    fail.append("an Allowance Type is paid off one of the scale's three columns, or none")
if kind_fields.get("salary_component", {}).get("mandatory_depends_on") != "eval:doc.paid_through=='Payroll'":
    fail.append("a type the payroll pays needs its salary component")
if kind_fields.get("accounts", {}).get("options") != "Allowance Type Account":
    fail.append("a type's expense account is set a company at a time")
if kind.get("autoname") != "field:allowance_type":
    fail.append("a type is named by what it is")
custom = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
leftovers = [row["name"] for row in custom if row["dt"] in ("Travel Request", "Travel Request Costing")
             or row["fieldname"] == "custom_is_allowance_line"]
if leftovers:
    fail.append("Travel Request is Frappe HR's own again: no allowance fields on it (%s)" % ", ".join(leftovers))
print("documents: the request, its lines, the type and its accounts; Travel Request left alone")

# ── 4. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "allowances.py")
validate = function(glue, "request_validate")
order = [validate.find(step) for step in ("_fill_lines(doc, types)", "grades.apply_scale(doc, types)",
                                           "_cost_lines(doc, types)", "_fill_advance(doc)", "_fill_totals(doc)",
                                           "_check_eligibility(doc", "_check_step(doc")]
if -1 in order or order != sorted(order):
    fail.append("on save: the types, then the scale, then the lines costed, the advance, the totals, "
                "Qualified? and the step, in that order")
if "if not doc.flags.get(MOVED):" not in validate:
    fail.append("a request copied from a Travel Request is not asked for its signatures again")
for needle, why in (
    ("rules.eligibility_errors(_facts(doc, types, advance))", "Qualified? is judged by the rules"),
    ("doc.qualifies = 0 if errors else 1", "and written on the form, not thrown"),
    ("errors += rules.payment_errors(_payment_facts(doc, figures))", "Accounts must give what the rules ask to pay"),
    ("rules.journal_rows(", "the entry is laid out by the rules"),
    ('"reference_type": ADVANCE, "reference_name": doc.advance,', "the advance taken is settled against itself"),
    ('"party_type": "Employee",', "for the employee"),
    ('"is_advance": "Yes"', "as Frappe HR's own return entry does"),
    ('entry.voucher_type = "Cash Entry" if doc.get("payment_method") == rules.CASH else "Bank Entry"',
     "cash is a cash entry, the rest a bank entry"),
    ("entry.cheque_no = doc.get(\"reference_no\")", "the bank entry carries the reference"),
    ("\"cost_center\": cost_center", "an expense is charged to a cost center"),
    ("entry.submit()", "the entry is made when Accounts pay"),
    ('"ref_doctype": DOCTYPE, "ref_docname": doc.name,', "each payroll addition names its request"),
    ("rules.payroll_date(", "in the payroll month it is paid in"),
    ('"overwrite_salary_structure_amount": 0,', "added to the salary, not written over it"),
    ("addition.submit()", "and put on the payroll"),
    ("entry.cancel()", "cancelled with the request"),
    ("addition.cancel()", "and so are the payroll additions"),
    ("_tell_hr_it_was_raised(doc)", "step 1: the HR Officer is told it was raised"),
    ("_tell_paid(doc)", "step 4: the HR Officer is told it was paid"),
    ("people.people_for(approval.ROLE_WAITING[state]", "each desk's own people are told"),
):
    if needle not in glue:
        fail.append("allowances.py: %s (%r not found)" % (why, needle))
submit = function(glue, "request_on_submit")
if 'doc.get("workflow_state") != approval.PAID or doc.flags.get(MOVED)' not in submit:
    fail.append("only a request Accounts pay is paid: not a refusal, and not one paid on its Travel Request")
raised = function(glue, "_tell_hr_it_was_raised")
if "people.hr_officers(" not in raised or "people.assign(" in raised:
    fail.append("the HR Officer is told when it is raised, not assigned: their turn comes at Pending HR Officer")
if "_tell_hr_it_was_raised(doc)" not in function(glue, "_check_step"):
    fail.append("and told on the step that leaves Draft")
if "people.hr_officers(" not in function(glue, "_tell_paid"):
    fail.append("the branch's HR Officers are told it was paid")
seed = function(glue, "seed_allowance_types")
if "rules.SEED_TYPES" not in seed or "if frappe.db.exists(TYPE, name):" not in seed \
        or '"Expense Claim Account"' not in seed:
    fail.append("the minutes' types are made once, with the accounts the old lines had")
grades = read("hrms_addon", "hrms_addon", "grades.py")
if "def apply_scale(doc, types):" not in grades or 'doc.get("destination")' not in grades:
    fail.append("the scale is read onto the Allowance Request")
print("glue: the scale before the lines, the entry and the payroll on Pay, undone on Cancel, who is told")

# ── 5. The move ───────────────────────────────────────────────────────
patch = read("hrms_addon", "patches", "v1_0", "allowance_request.py")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.allowance_request" not in patches:
    fail.append("the move runs after the model is synced")
for needle, why in (
    ("allowances.seed_allowance_types()", "the types are there before anything is copied onto them"),
    ('filters={"custom_allowance_status": ["is", "set"], "docstatus": ["<", 2]}', "a cancelled allowance stays"),
    ('frappe.db.exists(REQUEST, {"travel_request": name})', "nothing is copied twice"),
    ('frappe.db.savepoint("hrms_addon_allowance_copy")', "one that will not copy costs only itself"),
    ("doc.flags[allowances.MOVED] = True", "a copy asks nobody again and pays nothing again"),
    ('"docstatus": 1 if travel.docstatus == 1 else 0', "a paid one stays paid"),
    ('frappe.delete_doc("Workflow", name', "the old workflow comes off Travel Request"),
    ("if failed:", "the old fields stay while anything is left to copy"),
    ('frappe.delete_doc("Custom Field", name', "then they come off"),
):
    if needle not in patch:
        fail.append("the patch: %s" % why)
old_source = re.search(r"(?ms)^OLD_FIELDS = (\(.*?^\))", patch)
old_fields = eval(old_source.group(1)) if old_source else ()  # the patch's own list, pure Python
if len(old_fields) != 49 or len(set(old_fields)) != 49:
    fail.append("the patch takes off the 49 fields the allowance had on Frappe HR's documents: %d" % len(old_fields))
if any(not (name.startswith(("Travel Request-custom_", "Travel Request Costing-custom_"))
            or name == "Expense Claim Type-custom_is_allowance_line") for name in old_fields):
    fail.append("the patch takes off only the allowance's own fields")
for name in ("Travel Request-custom_allowance_status", "Travel Request Costing-custom_rate",
             "Travel Request-custom_per_diem_rate"):
    if name not in old_fields:
        fail.append("the patch leaves %s behind" % name)
print("move: copied where it stood, the old workflow and fields taken off Travel Request")

# ── 6. Wiring ─────────────────────────────────────────────────────────
for name, calls in (("allowance_request", ("validate", "request_validate", "on_submit", "request_on_submit",
                                           "on_cancel", "request_on_cancel")),
                    ("allowance_type", ("validate", "type_validate"))):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    for method, glue_function in zip(calls[::2], calls[1::2]):
        if "    def %s(self):\n        allowances.%s(self)" % (method, glue_function) not in controller:
            fail.append("the %s controller hands %s to allowances.%s" % (name, method, glue_function))
events = hooks.get("doc_events", {})
if "Travel Request" in events or "Travel Request" in (hooks.get("doctype_js") or {}):
    fail.append("Travel Request is Frappe HR's own again: no hooks and no form script of ours")
if "hrms_addon.hrms_addon.allowances.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the workflow is built on every migrate")
if "hrms_addon.hrms_addon.allowances.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("Accounts are reminded daily of what waits for them")
if "hrms_addon.hrms_addon.allowances.seed_allowance_types" not in (hooks.get("after_install") or []):
    fail.append("a fresh install has the minutes' allowances")
if "allowances.seed_allowance_types()" not in read("hrms_addon", "patches", "v1_0", "seed_benefits.py"):
    fail.append("the older seed patch seeds the types too, where it has not run")
navigation = load("navigation_rules")
card = dict(navigation.CARDS.get("Expenses", [])).get("Allowances", [])
if [link[1] for link in card] != ["Allowance Request", "Allowance Type", "Per Diem Rate", "Travel Destination"]:
    fail.append("the Expenses page has an Allowances card: the request, its types and the scale")
sidebar = {entry[1]: entry for entry in navigation.SIDEBAR.get("Expenses", [])}
if sidebar.get("Allowance Request", (None,) * 5)[4] != "Expense Claim" or \
        sidebar.get("Allowance Type", (None,) * 5)[3] != "Setup":
    fail.append("the sidebar has the request after Expense Claim and its types under Setup")
signatures = load("signature_rules")
if "Allowance Request" not in signatures.SIGNABLE or "Travel Request" in signatures.SIGNABLE:
    fail.append("the allowance is signed on the Allowance Request, not on Travel Request")
signing = read("hrms_addon", "public", "js", "e_signature.js")
if '"Allowance Request",' not in signing or '"Travel Request",' in signing:
    fail.append("and the desk's Sign button follows it")
form = read("hrms_addon", "hrms_addon", "doctype", "allowance_request", "allowance_request.js")
for needle, why in (('frm.set_query("payment_account"', "Accounts pick a bank or cash account of the company"),
                    ('frm.set_query("advance"', "the advance picked is the employee's own"),
                    ("ha_add_field_lines", "LPL.HR.31's lines added in one go")):
    if needle not in form:
        fail.append("the form: %s" % why)
if os.path.exists(os.path.join(PACKAGE, "public", "js", "travel_request.js")):
    fail.append("the old Travel Request form script is gone")
print("wiring: the controllers, the seeds, the daily reminder, the Expenses page, the signature")

# ── 7. Upstream ───────────────────────────────────────────────────────
checks = (
    ("Employee Advance", ("employee", "paid_amount", "claimed_amount", "return_amount", "advance_account")),
    ("Additional Salary", ("employee", "company", "salary_component", "amount", "payroll_date", "currency",
                           "overwrite_salary_structure_amount", "ref_doctype", "ref_docname")),
    ("Journal Entry", ("voucher_type", "company", "posting_date", "cheque_no", "cheque_date", "user_remark")),
    ("Journal Entry Account", ("account", "debit_in_account_currency", "credit_in_account_currency", "party_type",
                               "party", "reference_type", "reference_name", "is_advance", "cost_center")),
    ("Expense Claim Account", ("company", "default_account")),
    ("Travel Request", ("purpose_of_travel", "description", "cost_center", "company", "costings")),
    ("Company", ("cost_center", "default_currency")),
)
if not upstream_doctype("Employee Advance"):
    print("upstream: Frappe HR and ERPNext not found at %s, skipped" % APPS_ROOT)
else:
    for name, needed in checks:
        found = fields_of(upstream_doctype(name))
        for fieldname in needed:
            if fieldname not in found:
                fail.append("%s has no %s any more" % (name, fieldname))
    je_row = fields_of(upstream_doctype("Journal Entry Account"))
    if "Employee Advance" not in (je_row.get("reference_type", {}).get("options") or ""):
        fail.append("a journal entry line can no longer settle an Employee Advance")
    print("upstream: the advance, the payroll addition, the journal entry and Travel Request as this relies on")

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL ALLOWANCE CHECKS PASSED")
