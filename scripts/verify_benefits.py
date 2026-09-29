"""Verify benefits administration, without a bench:

    python scripts/verify_benefits.py

Luuka's revised flow chart 4.7 (Benefits Administration) and the paper it
runs on, LPL/HR/27 the Employees Claim Form. The allowance (chart 4.3) is
its own Allowance Request now: scripts/verify_allowances.py.

  1  the claim rules: what a claim must say, the standard amounts, the
     supervisor's "genuine" line, and the birthdays the script asks for
  2  the paper is carried on Frappe HR's own Expense Claim, not beside it
  3  the glue reads and writes fields that exist
  4  the signatures: the chain walked end to end, every block stamped
  5  wiring: the doc events, the workflow on migrate, the job, the seeds

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
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
B = load("benefits_rules")
CP = load("claim_approval")
hooks = hooks_dict()
print("loaded benefits_rules.py and claim_approval.py without Frappe")

# ── 1. The claim rules ────────────────────────────────────────────────
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
# the minutes of 16 and 20 July 2026, §4.8: maternity is UGX 350,000
# for a female employee, for up to three children; bereavement 70% of gross,
# for a biological mother, father or child
if (B.MATERNITY_AMOUNT, B.MATERNITY_TIMES, B.FEMALE) != (350000.0, 3, "Female"):
    fail.append("maternity is UGX 350,000, for up to three children, for female employees")
if B.BEREAVEMENT_PERCENT != 70.0 or B.BEREAVEMENT_RELATIONS != ("Mother", "Father", "Child"):
    fail.append("bereavement is 70% of gross, for a mother, father or child")
BASE = {"claim_details": "Birth, 3 Oct", "reason": "A new baby", "amount": 350000,
        "claim_type": "Maternity Benefit", "is_standard": 1, "standard_amount": 350000,
        "max_times": 3, "times_before": 2, "for_gender": "Female", "gender": "Female"}
expect("a third child", B.claim_errors(BASE))
expect("a fourth", B.claim_errors(dict(BASE, times_before=3)), "at most 3 time(s)")
expect("a male employee", B.claim_errors(dict(BASE, gender="Male")), "for female employees")
LOSS = {"claim_details": "Funeral, 3 Oct", "reason": "My father died", "amount": 700000,
        "claim_type": "Bereavement Support", "percent_of_gross": 70, "gross_pay": 1000000,
        "relations": "Mother, Father, Child", "relation": "Father"}
expect("a father, at 70% of a million", B.claim_errors(LOSS))
expect("more than 70%", B.claim_errors(dict(LOSS, amount=700001)), "70% of a gross")
expect("a cousin", B.claim_errors(dict(LOSS, relation="Other")), "mother, father or child")
expect("nobody said whose", B.claim_errors(dict(LOSS, relation=None)), "say whose it was")
expect("no gross on record", B.claim_errors(dict(LOSS, gross_pay=0)), "no gross on record")
if B.ceiling(LOSS) != 700000 or B.ceiling(BASE) != 350000:
    fail.append("the most a claim may be: its share of gross, or its standard amount")
print("claims: what a claim must say, the standard amounts, the genuine line, the birthdays")

# ── 2. The paper is on their form ─────────────────────────────────────
for name in ("Expense Claim", "Expense Claim Type"):
    if not upstream_doctype(name):
        fail.append("Frappe HR's %s is not where it was: the form is built on it" % name)
    if doctype(name):
        fail.append("%s must stay Frappe HR's own, extended, not copied here" % name)

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
for fieldname in ("custom_is_standard", "custom_standard_amount", "custom_occasion", "custom_requires_evidence"):
    if fieldname not in types:
        fail.append("Expense Claim Type has no %s: the script asks for standard claims" % fieldname)
if "custom_is_allowance_line" in types:
    fail.append("an allowance is an Allowance Type now, not an Expense Claim Type")
print("the paper: LPL/HR/27 on their Expense Claim")

# ── 3. The glue reads fields that exist ───────────────────────────────
glue_benefits = read("hrms_addon", "hrms_addon", "benefits.py")
expense_fields = dict(all_fields("Expense Claim"), **custom_fields("Expense Claim Type"))
for fieldname in sorted(set(re.findall(r'doc\.get\("(custom_\w+)"\)', glue_benefits))
                        | set(re.findall(r"doc\.(custom_\w+)\b", glue_benefits))):
    if fieldname not in expense_fields:
        fail.append("benefits.py reads or writes Expense Claim.%s, which does not exist" % fieldname)
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

# ── 4. The signatures ─────────────────────────────────────────────────
claim_route = walk(CP, CP.DRAFT, (CP.SUBMIT, CP.APPROVE, CP.PAY))
if claim_route != [CP.DRAFT, CP.PENDING_SUPERVISOR, CP.PENDING_HOD, CP.PENDING_HR, CP.PENDING_GM,
                   CP.PENDING_ACCOUNTS, CP.PAID]:
    fail.append("the claim goes Supervisor, HOD, HR, General Manager, then Accounts: %s" % claim_route)
if set(CP.STAMPS) != set(CP.PENDING_STATES):
    fail.append("every desk the claim passes is stamped: %s" % sorted(CP.STAMPS))
if set(CP.ROLE_WAITING) != set(CP.PENDING_STATES):
    fail.append("every pending state of the claim must know whose desk it is on")
for state in CP.PENDING_STATES:
    if not [t for t in CP.TRANSITIONS if t["state"] == state and t["action"] == CP.RETURN]:
        fail.append("%s must be able to return the claim" % state)
if CP.STATE_FIELD != "workflow_state":
    fail.append("the claim workflow runs on workflow_state")
expect("a claim passed on without the genuine line",
       CP.step_errors(CP.PENDING_SUPERVISOR, CP.PENDING_HOD, {}), "whether the claim is genuine")
expect("a claim the supervisor found genuine",
       CP.step_errors(CP.PENDING_SUPERVISOR, CP.PENDING_HOD, {"genuine": 1}))
if CP.upstream_approval(CP.PAID) != "Approved" or CP.upstream_approval(CP.PENDING_HOD) != "Draft":
    fail.append("Frappe HR's own approval_status stays Draft until the chain decides")
print("signatures: the chain walked end to end, every block stamped")

# ── 5. Wiring ─────────────────────────────────────────────────────────
events = hooks.get("doc_events", {})
for method in ("validate", "on_submit", "on_cancel"):
    if not (events.get("Expense Claim") or {}).get(method):
        fail.append("Expense Claim has no %s hook" % method)
if "Expense Claim" not in (hooks.get("doctype_js") or {}):
    fail.append("Expense Claim needs its form script")
if "hrms_addon.hrms_addon.benefits.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the claim workflow must be built after every migrate")
if "hrms_addon.hrms_addon.benefits.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the claims' daily job must run daily")
if "hrms_addon.hrms_addon.benefits.seed_standard_claims" not in (hooks.get("after_install") or []):
    fail.append("a fresh install seeds the standard claims")
seed = read("hrms_addon", "patches", "v1_0", "seed_benefits.py")
if "seed_standard_claims()" not in seed:
    fail.append("the patch must seed the standard claims on a site that has the app already")
if "seed_allowance_lines" in seed:
    fail.append("the seed patch calls a seed that is gone")
if "hrms_addon.patches.v1_0.seed_benefits" not in read("hrms_addon", "patches.txt"):
    fail.append("the seed patch must be listed in patches.txt")
# the minutes' figures reach a site that has the app already: made where
# missing, set where untouched, never over what HR have entered
patches = read("hrms_addon", "patches.txt")
if "hrms_addon.patches.v1_0.benefits_from_minutes" not in patches.split("[post_model_sync]")[-1]:
    fail.append("the minutes' benefits patch must run after the doctypes are migrated")
minutes = read("hrms_addon", "patches", "v1_0", "benefits_from_minutes.py")
for needle, why in (("benefits.seed_standard_claims()", "Maternity Benefit is made where it is missing"),
                    ("_make_fields()", "the claim type's new fields are made before they are written"),
                    ('"custom_standard_amount", "custom_percent_of_gross"', "only an untouched type is set"),
                    ("benefits.minutes_values(name)", "Bereavement Support is set to what the minutes say")):
    if needle not in minutes:
        fail.append("the minutes' benefits patch: %s" % why)
for name in (B.MATERNITY_BENEFIT, B.BEREAVEMENT_SUPPORT):
    if "rules.%s" % ("MATERNITY_BENEFIT" if name == B.MATERNITY_BENEFIT else "BEREAVEMENT_SUPPORT") \
            not in read("hrms_addon", "hrms_addon", "benefits.py").split("def seed_standard_claims")[1]:
        fail.append("a fresh install seeds %s" % name)
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
if "Expense Claim" in carded or "Expense Claim" in sidebarred:
    fail.append("Expense Claim is Frappe HR's own and already on their Expenses page: leave their entry alone")
if not os.path.exists(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "workspace", "expenses", "expenses.json")):
    fail.append("Frappe HR no longer ships the Expenses workspace, where the claim lives")
print("wiring: the doc events, the workflow on migrate, the daily job, the seeds")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL BENEFITS CHECKS PASSED")
