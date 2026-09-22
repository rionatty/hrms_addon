"""Verify the allowance application and benefits administration, without
a bench:

    python scripts/verify_benefits.py

Luuka's revised flow charts 4.3 (Allowance Application) and 4.7 (Benefits
Administration), and the paper they run on: LPL.HR.31 the travel allowance
and LPL/HR/27 the Employees Claim Form.

  1  the allowance rules: the lines, the totals, who qualifies
  2  the claim rules: what a claim must say, the standard amounts, the
     supervisor's "genuine" line, and the birthdays the script asks for
  3  the paper is carried on Frappe HR's own Travel Request and Expense
     Claim, not beside them
  4  the glue reads and writes fields that exist
  5  the signatures: both chains walked end to end, every block stamped
  6  wiring: the doc events, the workflows on migrate, the jobs, the seeds

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import datetime
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


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


def all_fields(name):
    spec = doctype(name) or upstream_doctype(name)
    return dict(fields_of(spec), **custom_fields(name))


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


def walk(module, start, forward_actions):
    walked, state, seen = [start], start, set()
    while state not in seen:
        seen.add(state)
        forward = [t for t in module.TRANSITIONS if t["state"] == state and t["action"] in forward_actions]
        if not forward:
            break
        state = forward[0]["next_state"]
        walked.append(state)
    return walked


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
A, B = load("allowance_rules"), load("benefits_rules")
AP, CP = load("allowance_approval"), load("claim_approval")
hooks = hooks_dict()
print("loaded allowance_rules.py, benefits_rules.py and both approval modules without Frappe")

# ── 1. The allowance rules ────────────────────────────────────────────
if A.ALLOWANCE_LINES != ("Lodging", "Daily Allowance", "Conveyance", "Labour Charges", "Other Expenses"):
    fail.append("LPL.HR.31 prints five lines, in its own order: %s" % (A.ALLOWANCE_LINES,))
if A.line_amount(3, 50000) != 150000:
    fail.append("a line is its days times its rate")
if A.line_amount(None, 50000) != 0:
    fail.append("a line with no days comes to nothing")
figures = A.totals([{"days": 3, "rate": 50000}, {"days": 3, "rate": 20000}], 100000)
if figures != {"total": 210000, "less_advance": 100000, "balance": 110000}:
    fail.append("the foot of the form: total, less advance, balance due: %s" % figures)
refund = A.totals([{"days": 1, "rate": 20000}], 50000)
if refund["balance"] != -30000:
    fail.append("an advance larger than the claim is refunded, so the balance goes negative: %s" % refund)
if A.totals([{"amount": 75000}])["total"] != 75000:
    fail.append("a line costed straight, without days and a rate, still counts")
if A.days_between("2026-10-01", "2026-10-03") != 3:
    fail.append("both ends of a trip are counted")

good = {"status": "Active", "purpose": "Delivery to Mbale", "start_date": "2026-10-01",
        "end_date": "2026-10-03", "lines": [{"expense_type": "Lodging", "days": 2, "rate": 50000}]}
expect("a request that qualifies", A.eligibility_errors(good))
expect("no purpose", A.eligibility_errors(dict(good, purpose="")), "Purpose of Travel")
expect("no dates", A.eligibility_errors(dict(good, start_date=None, end_date=None)), "dates the travel")
expect("ending before it starts", A.eligibility_errors(dict(good, end_date="2026-09-30")),
       "ends before it starts")
expect("no lines", A.eligibility_errors(dict(good, lines=[])), "at least one line")
expect("a line worth nothing",
       A.eligibility_errors(dict(good, lines=[{"expense_type": "Lodging", "days": 0, "rate": 0}])),
       "comes to nothing")
expect("more days than the trip covers",
       A.eligibility_errors(dict(good, lines=[{"expense_type": "Lodging", "days": 9, "rate": 50000}])),
       "the travel covers 3")
expect("someone who left", A.eligibility_errors(dict(good, status="Left")), "active employee")
expect("paying more than is due", A.payment_errors({"balance": 100000, "paid_amount": 150000,
                                                    "paid_on": "2026-10-05"}), "only UGX 100,000 is due")
expect("paying without a date", A.payment_errors({"balance": 100000, "paid_amount": 100000}), "when the")
print("allowance: the five lines, the days and the rate, the totals, who qualifies")

# ── 2. The claim rules ────────────────────────────────────────────────
claim = {"claim_details": "Hospital bill, 3 Oct", "reason": "Child admitted", "amount": 200000}
expect("a claim that stands", B.claim_errors(claim))
expect("nothing claimed", B.claim_errors(dict(claim, claim_details="")), "Claimed details")
expect("no reason", B.claim_errors(dict(claim, reason="")), "reason for the claim")
expect("no amount", B.claim_errors(dict(claim, amount=0)), "needs an amount")
expect("more than the standard",
       B.claim_errors(dict(claim, is_standard=1, standard_amount=100000, claim_type="Wedding Gift")),
       "standard claim of UGX 100,000")
expect("within the standard",
       B.claim_errors(dict(claim, amount=100000, is_standard=1, standard_amount=100000,
                           claim_type="Wedding Gift")))
expect("evidence not attached", B.claim_errors(dict(claim, requires_evidence=1)), "paid on evidence")
expect("evidence attached", B.claim_errors(dict(claim, requires_evidence=1, evidence="/files/bill.pdf")))
if B.standard_amount("Wedding Gift", {"Wedding Gift": {"is_standard": 1, "standard_amount": 150000}}) != 150000:
    fail.append("a standard claim is worth what the type says")
if B.standard_amount("Fuel", {"Fuel": {"is_standard": 0, "standard_amount": 150000}}) is not None:
    fail.append("a type that is not standard has no standard amount")

expect("passed on without saying whether it is genuine", B.genuine_errors({}), "whether the claim is genuine")
expect("found not genuine with no reason", B.genuine_errors({"genuine": 0}), "remarks saying why")
expect("found not genuine, with the reason",
       B.genuine_errors({"genuine": 0, "supervisor_remarks": "The receipt is for someone else."}))
expect("found genuine", B.genuine_errors({"genuine": 1}))
expect("paying more than was approved",
       B.payment_errors({"amount": 200000, "sanctioned_amount": 150000, "paid_amount": 200000,
                         "paid_on": "2026-10-05"}), "only UGX 150,000 was approved")

if not B.birthday_on("1990-03-04", "2026-03-04"):
    fail.append("a birthday falls on the day it falls")
if B.birthday_on("1990-03-04", "2026-03-05"):
    fail.append("and on no other day")
if not B.birthday_on("1992-02-29", "2027-02-28"):
    fail.append("someone born on the 29th of February has it on the 28th in a year that has no 29th")
if B.birthday_on("1992-02-29", "2028-02-28"):
    fail.append("but not in a leap year, when the 29th is there")
if not B.birthday_on("1992-02-29", "2028-02-29"):
    fail.append("in a leap year it falls on the 29th")
due = B.birthdays_due([{"name": "E1", "date_of_birth": "1990-03-04"},
                       {"name": "E2", "date_of_birth": "1990-03-11"},
                       {"name": "E3", "date_of_birth": "1990-06-01"}], "2026-03-04")
if sorted(due) != [("E1", 0), ("E2", 7)]:
    fail.append("a birthday is told a week before and on the day: %s" % (due,))
if B.age_on("1990-03-04", "2026-03-04") != 36:
    fail.append("the age is the years since, counted on the day")
if B.age_on("1990-03-05", "2026-03-04") != 35:
    fail.append("and not a day early")
print("claims: what a claim must say, the standard amounts, the genuine line, the birthdays")

# ── 3. The paper is on their forms ────────────────────────────────────
for name in ("Travel Request", "Travel Request Costing", "Expense Claim", "Expense Claim Type"):
    if not upstream_doctype(name):
        fail.append("Frappe HR's %s is not where it was: the form is built on it" % name)
    if doctype(name):
        fail.append("%s must stay Frappe HR's own, extended, not copied here" % name)

travel = custom_fields("Travel Request")
for fieldname in ("custom_badge_no", "custom_grade", "custom_department", "custom_branch",
                  "custom_start_date", "custom_start_time", "custom_end_date", "custom_end_time",
                  "custom_allowance_status", "custom_total", "custom_less_advance", "custom_balance_due",
                  "custom_advance", "custom_qualifies", "custom_eligibility_remarks",
                  "custom_supervisor_by", "custom_hr_by", "custom_gm_by", "custom_accounts_by",
                  "custom_return_remarks", "custom_paid_amount", "custom_paid_on",
                  "custom_payment_reference"):
    if fieldname not in travel:
        fail.append("Travel Request has no %s, which LPL.HR.31 asks for" % fieldname)
for fieldname in ("custom_total", "custom_balance_due", "custom_qualifies", "custom_allowance_status"):
    if not (travel.get(fieldname) or {}).get("read_only"):
        fail.append("Travel Request.%s is worked out, not typed" % fieldname)
costing = custom_fields("Travel Request Costing")
for fieldname in ("custom_days", "custom_rate"):
    if fieldname not in costing:
        fail.append("Travel Request Costing has no %s: LPL.HR.31 costs a line by days and rate" % fieldname)
if "expense_type" not in fields_of(upstream_doctype("Travel Request Costing")):
    fail.append("the line's kind is their own expense_type, shared with the claim form")

claim_fields = custom_fields("Expense Claim")
for fieldname in ("custom_badge_no", "custom_work_section", "custom_branch", "custom_occasion",
                  "custom_claim_details", "custom_reason", "custom_evidence", "custom_claim_status",
                  "custom_genuine", "custom_supervisor_by", "custom_hod_by", "custom_hr_by",
                  "custom_gm_by", "custom_accounts_by", "custom_return_remarks", "custom_paid_on",
                  "custom_payment_reference"):
    if fieldname not in claim_fields:
        fail.append("Expense Claim has no %s, which LPL/HR/27 asks for" % fieldname)
if (claim_fields.get("custom_occasion") or {}).get("options", "").split("\n") != list(B.OCCASIONS):
    fail.append("Expense Claim.custom_occasion must offer the occasions Luuka pay for")
types = custom_fields("Expense Claim Type")
for fieldname in ("custom_is_standard", "custom_standard_amount", "custom_occasion",
                  "custom_requires_evidence", "custom_is_allowance_line"):
    if fieldname not in types:
        fail.append("Expense Claim Type has no %s: the script asks for standard claims" % fieldname)
print("the paper: LPL.HR.31 on their Travel Request, LPL/HR/27 on their Expense Claim")

# ── 4. The glue reads fields that exist ───────────────────────────────
glue_allowances = read("hrms_addon", "hrms_addon", "allowances.py")
# the module writes the request, its costing lines, and the Expense Claim
# Types the five lines are seeded as
travel_fields = dict(all_fields("Travel Request"), **custom_fields("Travel Request Costing"),
                     **custom_fields("Expense Claim Type"))
for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue_allowances))
                        | set(re.findall(r"doc\.(custom_\w+)\b", glue_allowances))
                        | set(re.findall(r'row\.get\("(custom_\w+)"\)', glue_allowances))):
    if fieldname not in travel_fields:
        fail.append("allowances.py reads or writes %s, which is on neither the request nor its lines"
                    % fieldname)
glue_benefits = read("hrms_addon", "hrms_addon", "benefits.py")
expense_fields = dict(all_fields("Expense Claim"), **custom_fields("Expense Claim Type"))
for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue_benefits))
                        | set(re.findall(r"doc\.(custom_\w+)\b", glue_benefits))):
    if fieldname not in expense_fields:
        fail.append("benefits.py reads or writes Expense Claim.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.line_amount(", "a line is costed by the rules"),
    ("rules.totals(", "and the foot of the form worked out by them"),
    ("rules.eligibility_errors(", "\"Qualified?\" is judged by the rules"),
    ("rules.payment_errors(", "and so is what Accounts pay"),
    ("rules.ALLOWANCE_LINES", "the five lines are seeded from the rules"),
):
    if needle not in glue_allowances:
        fail.append("allowances.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("rules.claim_errors(", "a claim is judged by the rules"),
    ("rules.genuine_errors(", "the supervisor's own line is judged by them"),
    ("rules.payment_errors(", "and so is what Accounts pay"),
    ("rules.birthdays_due(", "the birthdays come from the rules"),
    ("approval.upstream_approval(", "Frappe HR's own approval_status is kept in step"),
):
    if needle not in glue_benefits:
        fail.append("benefits.py: %s (%r not found)" % (why, needle))
print("glue: fields that exist upstream, the rules followed, their own status kept in step")

# ── 5. The signatures ─────────────────────────────────────────────────
route = walk(AP, AP.DRAFT, (AP.SUBMIT, AP.APPROVE, AP.PAY))
if route != [AP.DRAFT, AP.PENDING_SUPERVISOR, AP.PENDING_HR, AP.PENDING_GM, AP.PENDING_ACCOUNTS, AP.PAID]:
    fail.append("the allowance goes Supervisor, HR Officer, General Manager, then Accounts: %s" % route)
claim_route = walk(CP, CP.DRAFT, (CP.SUBMIT, CP.APPROVE, CP.PAY))
if claim_route != [CP.DRAFT, CP.PENDING_SUPERVISOR, CP.PENDING_HOD, CP.PENDING_HR, CP.PENDING_GM,
                   CP.PENDING_ACCOUNTS, CP.PAID]:
    fail.append("the claim goes Supervisor, HOD, HR, General Manager, then Accounts: %s" % claim_route)
for module, what in ((AP, "allowance"), (CP, "claim")):
    if set(module.STAMPS) != set(module.PENDING_STATES):
        fail.append("every desk the %s passes is stamped: %s" % (what, sorted(module.STAMPS)))
    if set(module.ROLE_WAITING) != set(module.PENDING_STATES):
        fail.append("every pending state of the %s must know whose desk it is on" % what)
    for state in module.PENDING_STATES:
        if not [t for t in module.TRANSITIONS if t["state"] == state and t["action"] == module.RETURN]:
            fail.append("%s must be able to return the %s" % (state, what))
    if module.STATE_FIELD != "workflow_state":
        fail.append("the %s workflow runs on workflow_state" % what)
expect("an allowance returned without saying why", AP.step_errors(AP.PENDING_HR, AP.DRAFT, {}),
       "Return Remarks")
expect("an allowance refused without saying why", AP.step_errors(AP.PENDING_GM, AP.REJECTED, {}),
       "General Manager's remarks")
if any(AP.compute_stamps(AP.PENDING_GM, AP.DRAFT, "x", "2026-03-04", {"custom_supervisor_by": "a"}).values()):
    fail.append("a returned allowance clears every signature")
expect("a claim passed on without the genuine line",
       CP.step_errors(CP.PENDING_SUPERVISOR, CP.PENDING_HOD, {}), "whether the claim is genuine")
expect("a claim the supervisor found genuine",
       CP.step_errors(CP.PENDING_SUPERVISOR, CP.PENDING_HOD, {"genuine": 1}))
if CP.upstream_approval(CP.PAID) != "Approved" or CP.upstream_approval(CP.PENDING_HOD) != "Draft":
    fail.append("Frappe HR's own approval_status stays Draft until the chain decides")
if AP.next_states(AP.PENDING_GM, ("Employee",)):
    fail.append("nobody may act on a desk that is not theirs")
print("signatures: both chains walked end to end, every block stamped")

# ── 6. Wiring ─────────────────────────────────────────────────────────
events = hooks.get("doc_events", {})
for dt in ("Travel Request", "Expense Claim"):
    for method in ("validate", "on_submit", "on_cancel"):
        if not (events.get(dt) or {}).get(method):
            fail.append("%s has no %s hook" % (dt, method))
    if dt not in (hooks.get("doctype_js") or {}):
        fail.append("%s needs its form script" % dt)
for path in ("hrms_addon.hrms_addon.allowances.setup_workflows_on_migrate",
             "hrms_addon.hrms_addon.benefits.setup_workflows_on_migrate"):
    if path not in (hooks.get("after_migrate") or []):
        fail.append("%s must run after every migrate" % path)
for path in ("hrms_addon.hrms_addon.allowances.daily", "hrms_addon.hrms_addon.benefits.daily"):
    if path not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
        fail.append("%s must run daily" % path)
for path in ("hrms_addon.hrms_addon.allowances.seed_allowance_lines",
             "hrms_addon.hrms_addon.benefits.seed_standard_claims"):
    if path not in (hooks.get("after_install") or []):
        fail.append("a fresh install seeds %s" % path)
seed = read("hrms_addon", "patches", "v1_0", "seed_benefits.py")
for needle in ("seed_allowance_lines()", "seed_standard_claims()"):
    if needle not in seed:
        fail.append("the patch must seed %s on a site that has the app already" % needle)
if "hrms_addon.patches.v1_0.seed_benefits" not in read("hrms_addon", "patches.txt"):
    fail.append("the seed patch must be listed in patches.txt")
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
for name in ("Travel Request", "Expense Claim"):
    if name in carded or name in sidebarred:
        fail.append("%s is Frappe HR's own and already on their Expenses page: leave their entry alone"
                    % name)
if not os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "workspace", "expenses",
                                   "expenses.json")):
    fail.append("Frappe HR no longer ships the Expenses workspace, where both forms live")
# Allowance case 1: the employee raises it, the supervisor is asked to
# act, and the HR Officer is told it exists — told at the raising, not
# only when it reaches their own step
glue = read("hrms_addon", "hrms_addon", "allowances.py")
if "_tell_hr_it_was_raised" not in glue:
    fail.append("test case 1: the HR Officer must be told when an allowance request is raised")
# and actually called, on the step that leaves Draft: a function nobody
# calls is not a notification
raising = glue.split("def _check_step")[1].split(chr(10) + "def ")[0]
if "_tell_hr_it_was_raised(doc)" not in raising:
    fail.append("and told on the step that leaves Draft, or nothing tells them")
raised = glue.split("def _tell_hr_it_was_raised")[1].split("\ndef ")[0]
if "people.hr_officers(" not in raised:
    fail.append("and it is the branch's own HR Officers who are told")
if "people.assign(" in raised:
    fail.append("they are told, not assigned: their turn comes at Pending HR Officer")
# case 3: Accounts set it to Paid and the HR Officer hears about it
paid = glue.split("def allowance_on_submit")[1].split("\ndef ")[0]
if "people.hr_officers(" not in paid or "paid" not in paid.lower():
    fail.append("test case 3: the HR Officer must be told once Accounts have paid it")
print("the three allowance cases: raised and told, routed and approved, paid and told")

print("wiring: the doc events, both workflows on migrate, the daily jobs, the seeds")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL ALLOWANCE AND BENEFITS CHECKS PASSED")
