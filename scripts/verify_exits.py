"""Verify the two exits and the cessation benefits, without a bench:

    python scripts/verify_exits.py

Luuka's revised flow charts 4.5 (Voluntary Exit), 4.6 (Involuntary Exit)
and 4.9 (Cessation Benefits), and the paper they run on: LPL/HR/22 the
Clearance Form and LPL/HR/20 the Full and Final Settlement Agreement.

  1  the exit rules: the notice the Act asks for, whether it was served,
     and the ten boxes of LPL/HR/22
  2  the settlement rules: what is due, what comes off, and the net
  3  the paper is carried on Frappe HR's own Employee Separation, Exit
     Interview and Full and Final Statement; only the clearance form is
     ours
  4  the glue reads and writes fields that exist
  5  the signatures: all three chains walked end to end, every desk stamped
  6  wiring: the doc events, the workflows on migrate, the job, the way in

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


def walk(module, start, forward_actions, condition=None):
    walked, state, seen = [start], start, set()
    while state not in seen:
        seen.add(state)
        forward = [t for t in module.TRANSITIONS if t["state"] == state and t["action"] in forward_actions
                   and (condition is None or t.get("condition") in (None, condition))]
        if not forward:
            break
        state = forward[0]["next_state"]
        walked.append(state)
    return walked


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
E, S = load("exit_rules"), load("settlement_rules")
IA, CA, SA = load("exit_interview_approval"), load("clearance_approval"), load("settlement_approval")
hooks = hooks_dict()
print("loaded exit_rules.py, settlement_rules.py and the three approval modules without Frappe")

# ── 1. The exit rules ─────────────────────────────────────────────────
if E.EXIT_TYPES != ("Voluntary", "Involuntary"):
    fail.append("there are two exits, 4.5 and 4.6: %s" % (E.EXIT_TYPES,))
if "Resignation" not in E.reasons_for(E.VOLUNTARY) or "Dismissal" in E.reasons_for(E.VOLUNTARY):
    fail.append("a voluntary exit is resignation, retirement or the end of a contract")
if "Dismissal" not in E.reasons_for(E.INVOLUNTARY) or "Desertion" not in E.reasons_for(E.INVOLUNTARY):
    fail.append("desertion and dismissal are involuntary, as the print-out list says")

# the minutes of 16 and 20 July 2026, §4.13: 0-6 months 7 days, 6-12
# months 14, 1-5 years a month, 5-10 years two, above 10 years three
if E.notice_days(3) != 7 or E.notice_days(7) != 14 or E.notice_days(24) != 30 \
        or E.notice_days(72) != 60 or E.notice_days(130) != 90:
    fail.append("Luuka's notice periods (minutes §4.13): %s"
                % [E.notice_days(n) for n in (3, 7, 24, 72, 130)])
if E.notice_days(0) != 7:
    fail.append("even the first months of service carry seven days' notice")
if E.months_served("2020-01-15", "2026-01-14") != 71:
    fail.append("a month is not served until the day of the month comes round")
if E.days_worked("2026-01-01", "2026-01-31") != 31:
    fail.append("both ends of the service are counted")
if E.last_working_day("2026-10-01", 30) != datetime.date(2026, 10, 30):
    fail.append("thirty days' notice from the 1st ends on the 30th")

full = E.notice_served("2026-10-01", "2026-10-30", 30)
if not full["served"] or full["short"]:
    fail.append("a notice served in full is served: %s" % full)
short = E.notice_served("2026-10-01", "2026-10-10", 30)
if short["served"] or short["short"] != 20:
    fail.append("a notice cut short says by how many days: %s" % short)
if not E.notice_served(None, None, 0)["served"]:
    fail.append("where no notice is required, none is short")

good = {"exit_type": E.VOLUNTARY, "reason": "Resignation", "notice_given": "2026-10-01",
        "relieving_date": "2026-10-30", "date_of_joining": "2020-01-15"}
expect("a voluntary exit that stands", E.separation_errors(good))
expect("no reason", E.separation_errors(dict(good, reason=None)), "why the employee is leaving")
expect("a reason from the other chart", E.separation_errors(dict(good, reason="Dismissal")),
       "not a reason for voluntary exit")
expect("no last day", E.separation_errors(dict(good, relieving_date=None)), "last day of service")
expect("leaving before joining", E.separation_errors(dict(good, relieving_date="2019-01-01")),
       "before the day they joined", "before the notice was given")
expect("no resignation letter date", E.separation_errors(dict(good, notice_given=None)),
       "resignation letter")
sacked = {"exit_type": E.INVOLUNTARY, "reason": "Dismissal", "relieving_date": "2026-10-30",
          "date_of_joining": "2020-01-15", "termination_date": "2026-10-30"}
expect("an involuntary exit that stands", E.separation_errors(sacked))
expect("no date on the letter", E.separation_errors(dict(sacked, termination_date=None)),
       "date of termination")
expect("a letter signed after the last day",
       E.separation_errors(dict(sacked, letter_signed_on="2026-12-01")),
       "signed after the last day")

if [code for code, _n, _i in E.SECTIONS] != list("ABCDEFGHIJ"):
    fail.append("LPL/HR/22 prints ten boxes, A to J: %s" % (E.SECTION_CODES,))
if E.SECTION_NAMES["B"] != "Information Technology" or E.SECTION_NAMES["J"] != "Accounts / Salaries":
    fail.append("the boxes keep the paper's own names")
rows = E.default_rows()
if len(rows) != sum(len(items) for _c, _n, items in E.SECTIONS):
    fail.append("every item of every box is drawn up")
if not all(row["section"] in E.SECTION_CODES and row["item"] for row in rows):
    fail.append("each drawn-up row knows its box and what it is")

expect("a clearance form with nothing on it", E.clearance_errors({"rows": []}), "nothing on it")
expect("a box that is not on the paper",
       E.clearance_errors({"rows": [{"section": "Z", "item": "Keys", "returned": 1}]}),
       "Z is not one of them")
expect("an item not returned and not accounted for",
       E.clearance_errors({"rows": [{"section": "A", "item": "Laptop", "returned": 0}]}),
       "say what became of it")
expect("an item not returned but costed",
       E.clearance_errors({"rows": [{"section": "A", "item": "Laptop", "returned": 0, "cost": 800000}]}))
if E.outstanding_cost([{"returned": 0, "cost": 800000}, {"returned": 1, "cost": 500000}]) != 800000:
    fail.append("box I counts only what was not returned")
items = [{"section": "A", "item": "Keys", "returned": 1}, {"section": "B", "item": "Laptop", "returned": 1}]
if E.cleared_sections(items, [{"section": "A", "signed_by": "hr"}]) != ["A"]:
    fail.append("a box is cleared when it is accounted for AND signed")
if E.clearance_complete(items, [{"section": "A", "signed_by": "hr"}]):
    fail.append("a form with an unsigned box is not complete")
if not E.clearance_complete(items, [{"section": "A", "signed_by": "hr"}, {"section": "B", "signed_by": "it"}]):
    fail.append("a form whose every used box is signed is complete")
print("exits: the notice the Act asks for, whether it was served, the ten boxes of LPL/HR/22")

# ── 2. The settlement rules ───────────────────────────────────────────
if S.PAYABLES != ("Final Salary", "Leave Encashment", "Notice Pay", "Severance Pay", "Net Claims"):
    fail.append("LPL/HR/20 names five things the settlement is made of: %s" % (S.PAYABLES,))
if S.NSSF not in S.STATUTORY or S.PAYE not in S.STATUTORY or S.LST not in S.STATUTORY:
    fail.append("the agreement names the three statutory deductions")
if S.daily_rate(1300000) != 50000:
    fail.append("a day is a month's gross over the 26 the register counts by")
if S.final_salary(1300000, 10) != 500000:
    fail.append("the part-month worked is days times the daily rate")
if S.leave_encashment(1300000, 21) != 1050000:
    fail.append("untaken leave is worth the daily rate a day")
if S.notice_pay(1300000, 30) != 1500000:
    fail.append("pay in lieu is the daily rate a day")
# severance (minutes §4.13): whole months of gross by length of
# service, for somebody who served their notice
for months, expected, why in (
    (24, 0, "under three years there is no severance"),
    (36, 1300000, "three to five years: one month's gross"),
    (59, 1300000, "still one month just short of five years"),
    (60, 2600000, "five to ten years: two months"),
    (120, 3900000, "above ten years: three months"),
    (240, 3900000, "and three is the most"),
):
    if S.severance_pay(1300000, months) != expected:
        fail.append("severance after %d months should be %s: %s (it is %s)"
                    % (months, expected, why, S.severance_pay(1300000, months)))
if S.severance_pay(1300000, 72, notice_served=False) != 0:
    fail.append("somebody who did not serve their notice has the shortfall deducted, not severance paid")

figures = S.totals([{"amount": 1000000}, {"amount": 500000}], [{"amount": 200000}])
if figures != {"payable": 1500000, "receivable": 200000, "net": 1300000}:
    fail.append("the foot of the computation: due, off, net: %s" % figures)
served = S.suggest({"gross_pay": 1300000, "days_worked_in_month": 10, "leave_balance": 21,
                    "months_served": 48, "notice_short_days": 0})
served_payable = {row["component"]: row["amount"] for row in served["payables"]}
if served_payable.get(S.SEVERANCE_PAY) != 1300000:
    fail.append("four years served and the notice served: one month's gross in severance (%s)"
                % served_payable)
found = S.suggest({"gross_pay": 1300000, "days_worked_in_month": 10, "leave_balance": 21,
                   "months_served": 48, "notice_short_days": 20, "advances_outstanding": 100000,
                   "loans_outstanding": 0, "unreturned_cost": 800000})
payable = {row["component"] for row in found["payables"]}
if S.FINAL_SALARY not in payable or S.LEAVE_ENCASHMENT not in payable:
    fail.append("what Accounts work out must cover the paper's own list: %s" % sorted(payable))
if S.SEVERANCE_PAY in payable:
    fail.append("notice not served: the shortfall comes off and no severance is paid (minutes §4.13)")
if S.NOTICE_PAY in payable:
    fail.append("pay in lieu is only where the COMPANY cut the notice short")
receivable = {row["component"] for row in found["receivables"]}
if S.NOTICE_SHORTFALL not in receivable or S.UNRETURNED not in receivable:
    fail.append("and what comes off must cover the notice not served and the items not returned")
if S.LOANS in receivable:
    fail.append("a line worth nothing is left off the computation")

statement = {"relieving_date": "2026-10-30", "payables": [{"component": S.FINAL_SALARY, "amount": 500000}],
             "receivables": [], "clearance": "HR-CLR-2026-00001"}
expect("a settlement that stands", S.settlement_errors(statement))
expect("no last day", S.settlement_errors(dict(statement, relieving_date=None)), "last day of service")
expect("nothing due", S.settlement_errors(dict(statement, payables=[])), "nothing due on it")
expect("no clearance form", S.settlement_errors(dict(statement, clearance=None)), "LPL/HR/22")
expect("deductions larger than what is due",
       S.settlement_errors(dict(statement, receivables=[{"component": S.LOANS, "amount": 900000}])),
       "owed to the company")
expect("a line with no name",
       S.settlement_errors(dict(statement, payables=[{"amount": 500000}])), "does not say what it is for")

expect("an agreement with an account and a signature",
       S.payment_errors({"account_name": "J Okello", "bank_name": "Stanbic", "account_number": "01234",
                         "employee_signed": 1}))
expect("no account number",
       S.payment_errors({"account_name": "J Okello", "bank_name": "Stanbic", "employee_signed": 1}),
       "Account Number")
expect("unsigned by the employee",
       S.payment_errors({"account_name": "J Okello", "bank_name": "Stanbic", "account_number": "01234"}),
       "confirms and signs")
expect("scheduled with no run", S.schedule_errors({"approved": "ed@luuka"}), "which payroll run")
expect("scheduled before the Executive Director approved",
       S.schedule_errors({"payroll_date": "2026-11-30"}), "Executive Director approves")
print("settlement: what is due, what comes off, the net, the account it is remitted to")

# ── 3. The paper is on their forms ────────────────────────────────────
for name in ("Employee Separation", "Exit Interview", "Full and Final Statement"):
    if not upstream_doctype(name):
        fail.append("Frappe HR's %s is not where it was: the exit is built on it" % name)
    if doctype(name):
        fail.append("%s must stay Frappe HR's own, extended, not copied here" % name)
for name, wanted in (
    ("Clearance Form", ("employee", "exit_type", "separation", "leaving_date", "notice_date",
                        "days_worked", "salary", "leave_balance", "items", "sections",
                        "outstanding_cost", "boxes_cleared", "complete", "hr_by", "finance_by",
                        "gm_by", "accounts_by", "hrm_by", "return_remarks", "approval_status")),
    ("Clearance Item", ("section", "section_name", "item", "returned", "cost", "remarks", "tool")),
    ("Clearance Section", ("section", "section_name", "signed_by", "signed_on", "remarks")),
):
    fields = fields_of(doctype(name))
    if not fields:
        fail.append("%s is not there" % name)
        continue
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which LPL/HR/22 asks for" % (name, fieldname))
clearance = fields_of(doctype("Clearance Form"))
for fieldname in ("outstanding_cost", "boxes_cleared", "complete", "days_worked", "approval_status"):
    if not (clearance.get(fieldname) or {}).get("read_only"):
        fail.append("Clearance Form.%s is worked out, not typed" % fieldname)
if (fields_of(doctype("Clearance Item")).get("section") or {}).get("options", "").split("\n") \
        != list(E.SECTION_CODES):
    fail.append("a clearance line belongs to one of the ten boxes")
if (fields_of(doctype("Clearance Item")).get("tool") or {}).get("options") != "Tool of Work":
    fail.append("box A pulls in the employee's own tools of work (step 6 of 4.5)")
# they are rows on the Employee, not a doctype of their own, so the read
# must name the table they sit in
if 'custom_employee_tools' not in read("hrms_addon", "hrms_addon", "exits.py"):
    fail.append("the tools of work are rows on the Employee: read them where they live")

separation = custom_fields("Employee Separation")
for fieldname in ("custom_exit_type", "custom_reason", "custom_notice_given", "custom_notice_days",
                  "custom_relieving_date", "custom_notice_served", "custom_notice_short_days",
                  "custom_termination_date", "custom_termination_reason", "custom_summoned_on",
                  "custom_letter_signed_on", "custom_property_handed_on", "custom_exit_interview",
                  "custom_clearance", "custom_settlement", "custom_tools_handed",
                  "custom_status_updated"):
    if fieldname not in separation:
        fail.append("Employee Separation has no %s, which the two charts ask for" % fieldname)
if (separation.get("custom_exit_type") or {}).get("options", "").split("\n") != list(E.EXIT_TYPES):
    fail.append("Employee Separation.custom_exit_type must offer exactly the two exits")
for fieldname in ("custom_notice_days", "custom_notice_served", "custom_notice_short_days",
                  "custom_status_updated"):
    if not (separation.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Separation.%s is worked out, not typed" % fieldname)

interview = custom_fields("Exit Interview")
for fieldname in ("custom_exit_status", "custom_separation", "custom_supervisor_by", "custom_hod_by",
                  "custom_hr_by", "custom_return_remarks"):
    if fieldname not in interview:
        fail.append("Exit Interview has no %s, which 4.5 step 4 asks for" % fieldname)

statement_fields = custom_fields("Full and Final Statement")
for fieldname in ("custom_settlement_status", "custom_separation", "custom_clearance",
                  "custom_exit_type", "custom_gross_pay", "custom_months_served",
                  "custom_notice_short_days", "custom_leave_balance", "custom_net_payable",
                  "custom_net_in_words", "custom_account_name", "custom_bank_name",
                  "custom_bank_branch", "custom_account_number", "custom_employee_signed",
                  "custom_ed_by", "custom_payroll_by", "custom_payroll_date",
                  "custom_additional_salary", "custom_return_remarks"):
    if fieldname not in statement_fields:
        fail.append("Full and Final Statement has no %s, which LPL/HR/20 asks for" % fieldname)
for fieldname in ("custom_net_payable", "custom_net_in_words", "custom_gross_pay",
                  "custom_settlement_status", "custom_additional_salary"):
    if not (statement_fields.get(fieldname) or {}).get("read_only"):
        fail.append("Full and Final Statement.%s is worked out, not typed" % fieldname)
print("the paper: LPL/HR/22 our own, both exits and LPL/HR/20 on their forms")

# ── 4. The glue ───────────────────────────────────────────────────────
def named(source, holder):
    """The custom_ fields a glue module reads off `holder`. The lookbehind
    matters: exits.py and settlements.py both reach the separation through
    an `exit_doc`, whose fields are the separation's and not the form the
    module is validating."""
    return set(re.findall(r'(?<![\w])%s\.get\("(custom_\w+)"\)' % holder, source)) \
        | set(re.findall(r"(?<![\w])%s\.(custom_\w+)\b" % holder, source))


glue_exits = read("hrms_addon", "hrms_addon", "exits.py")
known = dict(all_fields("Employee Separation"), **all_fields("Exit Interview"))
for fieldname in sorted(named(glue_exits, "doc") | named(glue_exits, "exit_doc")):
    if fieldname not in known:
        fail.append("exits.py reads or writes %s, which is on neither their separation nor their "
                    "interview" % fieldname)
glue_settlements = read("hrms_addon", "hrms_addon", "settlements.py")
statement_all = all_fields("Full and Final Statement")
for fieldname in sorted(named(glue_settlements, "doc")):
    if fieldname not in statement_all:
        fail.append("settlements.py reads or writes Full and Final Statement.%s, which does not exist"
                    % fieldname)
separation_all = all_fields("Employee Separation")
for fieldname in sorted(named(glue_settlements, "exit_doc")):
    if fieldname not in separation_all:
        fail.append("settlements.py reads Employee Separation.%s, which does not exist" % fieldname)
for needle, why in (
    ("rules.notice_days(", "the notice comes from the rules"),
    ("rules.notice_served(", "and whether it was served"),
    ("rules.clearance_errors(", "the clearance form is judged by them"),
    ("rules.cleared_sections(", "and which boxes are done"),
    ("rules.default_rows(", "the ten boxes are drawn up from them"),
    ("Employee Tool", "step 6: the tools of work come onto box A"),
    ('employee.status = "Left"', "step 2 of the cessation chart: the employee is made inactive"),
):
    if needle not in glue_exits:
        fail.append("exits.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("rules.suggest(", "what is due and what comes off is worked out by the rules"),
    ("rules.totals(", "and the net by them"),
    ("rules.settlement_errors(", "the statement is judged by them"),
    ("rules.payment_errors(", "and the account it is remitted to"),
    ("rules.schedule_errors(", "and the run it is scheduled in"),
    ("money_in_words(", "LPL/HR/20 says the total in words"),
    ("Additional Salary", "step 6: the payroll process pays it"),
    ('custom_status_updated',
     "step 2 comes before step 3: their statement reads its relieving date off the Employee"),
):
    if needle not in glue_settlements:
        fail.append("settlements.py: %s (%r not found)" % (why, needle))
for name, glue, module in (("draw_up_clearance", glue_exits, "exits"),
                           ("draw_up", glue_settlements, "settlements")):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("%s.%s changes something: a whitelisted POST method" % (module, name))
    if "check_permission(" not in glue:
        fail.append("%s.py: a whitelisted method must check the caller may act" % module)
controller = read("hrms_addon", "hrms_addon", "doctype", "clearance_form", "clearance_form.py")
for method in ("validate", "on_submit", "on_cancel"):
    if "    def %s(self):\n        exits.clearance_%s(self)" % (method, method) not in controller:
        fail.append("the Clearance Form controller must hand %s to exits.clearance_%s" % (method, method))
print("glue: fields that exist upstream, the rules followed, the buttons whitelisted")

# ── 5. The signatures ─────────────────────────────────────────────────
route = walk(IA, IA.DRAFT, (IA.SUBMIT, IA.APPROVE))
if route != [IA.DRAFT, IA.PENDING_SUPERVISOR, IA.PENDING_HOD, IA.PENDING_HR, IA.APPROVED]:
    fail.append("the exit interview goes Supervisor, HOD, HR Officer: %s" % route)
expect("an interview sent up empty", IA.step_errors(IA.DRAFT, IA.PENDING_SUPERVISOR, {}),
       "fills the exit interview in")
expect("an interview filled in",
       IA.step_errors(IA.DRAFT, IA.PENDING_SUPERVISOR, {"interview_summary": "Better pay elsewhere."}))
expect("returned without a reason", IA.step_errors(IA.PENDING_HOD, IA.DRAFT, {}), "Return Remarks")

for exit_type, wanted in (
    (E.VOLUNTARY, [CA.DRAFT, CA.PENDING_HR, CA.PENDING_FINANCE, CA.PENDING_GM, CA.CLEARED]),
    (E.INVOLUNTARY, [CA.DRAFT, CA.PENDING_GM, CA.PENDING_ACCOUNTS, CA.PENDING_HRM, CA.CLEARED]),
):
    walked = walk(CA, CA.DRAFT, (CA.SUBMIT, CA.APPROVE, CA.CLEAR), CA.CONDITIONS[exit_type])
    if walked != wanted:
        fail.append("a %s clearance goes %s, not %s" % (exit_type.lower(), wanted, walked))
    if list(CA.route(exit_type)) != wanted:
        fail.append("clearance_approval.route(%r) must say the same: %s" % (exit_type, CA.route(exit_type)))
if set(CA.CONDITIONS) != set(E.EXIT_TYPES):
    fail.append("the clearance workflow must route both exits")
if set(CA.STAMPS) != set(CA.PENDING_STATES) or set(CA.ROLE_WAITING) != set(CA.PENDING_STATES):
    fail.append("every desk a clearance passes is stamped and known: %s" % sorted(CA.STAMPS))
expect("a clearance sent up with a box unaccounted for",
       CA.step_errors(CA.DRAFT, CA.PENDING_HR, {}), "accounted for and signed")
expect("a clearance whose boxes are all done",
       CA.step_errors(CA.DRAFT, CA.PENDING_HR, {"complete": 1}))
expect("returned without a reason", CA.step_errors(CA.PENDING_FINANCE, CA.DRAFT, {}), "Return Remarks")
if CA.next_states(CA.DRAFT, ("HR User",), E.INVOLUNTARY) != [(CA.SUBMIT, CA.PENDING_GM)]:
    fail.append("an involuntary clearance leaves Draft for the General Manager")
if CA.next_states(CA.DRAFT, ("HR User",), E.VOLUNTARY) != [(CA.SUBMIT, CA.PENDING_HR)]:
    fail.append("a voluntary one leaves Draft for the HR Officer")

settlement_route = walk(SA, SA.DRAFT, (SA.SUBMIT, SA.APPROVE, SA.SCHEDULE))
if settlement_route != [SA.DRAFT, SA.PENDING_ACCOUNTS, SA.PENDING_EMPLOYEE, SA.PENDING_ED,
                        SA.PENDING_PAYROLL, SA.SCHEDULED]:
    fail.append("the settlement goes Accounts, the employee, the Executive Director, payroll: %s"
                % settlement_route)
if set(SA.STAMPS) != set(SA.PENDING_STATES) or set(SA.ROLE_WAITING) != set(SA.PENDING_STATES):
    fail.append("every desk the settlement passes is stamped and known: %s" % sorted(SA.STAMPS))
if any(SA.compute_stamps(SA.PENDING_ED, SA.DRAFT, "x", "2026-03-04",
                         {"custom_accounts_by": "a"}).values()):
    fail.append("a returned settlement clears every signature")
print("signatures: all three chains walked end to end, the clearance conditional on the exit")

# ── 6. Wiring ─────────────────────────────────────────────────────────
events = hooks.get("doc_events", {})
for dt in ("Employee Separation", "Exit Interview", "Full and Final Statement"):
    for method in ("validate", "on_submit", "on_cancel"):
        if not (events.get(dt) or {}).get(method):
            fail.append("%s has no %s hook" % (dt, method))
for path in ("hrms_addon.hrms_addon.exits.setup_workflows_on_migrate",
             "hrms_addon.hrms_addon.settlements.setup_workflows_on_migrate"):
    if path not in (hooks.get("after_migrate") or []):
        fail.append("%s must run after every migrate" % path)
if "hrms_addon.hrms_addon.exits.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("a notice period running out is watched daily")
for dt in ("Employee Separation", "Full and Final Statement"):
    if dt not in (hooks.get("doctype_js") or {}):
        fail.append("%s needs its form script" % dt)
navigation = load("navigation_rules")
# the page each thing is on, not merely whether it is on SOME page: the
# exit documents were listed in Recruitment's sidebar while their card sat
# on Tenure, each anchored after an entry only Tenure has, so none of them
# could seat where it was meant to
carded = {link[1]: page for page, cards in navigation.CARDS.items()
          for _card, links in cards for link in links}
sidebarred = {entry[1]: page for page, entries in navigation.SIDEBAR.items() for entry in entries}
for name in ("Clearance Form", "Employee Separation", "Exit Interview", "Full and Final Statement"):
    if carded.get(name) != "Tenure":
        fail.append("%s belongs on the Tenure page, where leaving belongs; it is on %r"
                    % (name, carded.get(name)))
if "Employee Separation" in sidebarred:
    fail.append("Employee Separation is their own sidebar entry: leave it where they put it")
for name in ("Clearance Form", "Exit Interview", "Full and Final Statement"):
    if sidebarred.get(name) != "Tenure":
        fail.append("%s's sidebar entry belongs on Tenure, beside Employee Separation; it is on %r"
                    % (name, sidebarred.get(name)))
print("wiring: the doc events, both workflows on migrate, the daily job, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL EXIT AND CESSATION CHECKS PASSED")
