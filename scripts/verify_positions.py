"""Verify contract management, without a bench:

    python scripts/verify_positions.py

The Contract Management forms (20 Sep 2026): the promotion, change of
designation and salary review letters and the Candidate Preamble that leads
to them; the bank account and phone number change requests (LPL/HR/34 and
LPL/HR/33) and the details LPL/HR/26 collects; and the Intern Placement
Letter.

  1  the rules: what each letter must say, the figure written out, what
     happens to the contract
  2  the Candidate Preamble's signatures, Supervisor to Executive Director
  3  the DocTypes carry every box on the paper, with the rights each role
     needs
  4  the glue reads and writes fields that exist, here and upstream
  5  the letters print what the paper says, from fields that exist
  6  wiring: the doc events, the workflow and roles on migrate, the jinja
     method the letters need, the daily job, the patch

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
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return json.load(open(hits[0], encoding="utf-8"))
    return None


def fields_of(spec):
    return {f["fieldname"]: f for f in spec.get("fields", [])}


def custom_fields(dt):
    return {row["fieldname"]: row for row in CUSTOM if row.get("dt") == dt}


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


def print_format(name):
    folder = name.lower().replace(" ", "_").replace("'", "")
    path = os.path.join(APP, "print_format", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
R, D, A = load("position_rules"), load("employee_data_rules"), load("position_approval")
print("loaded position_rules.py, employee_data_rules.py and position_approval.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if R.CHANGE_TYPES != ("Promotion", "Change of Designation", "Salary Increment"):
    fail.append("the three letters Luuka writes are Promotion, Change of Designation and Salary Increment")
if set(R.LETTERS) != set(R.CHANGE_TYPES):
    fail.append("every change type must name the letter it prints: %s" % R.LETTERS)
if R.changes("Promotion") != (True, True) or R.changes("Change of Designation") != (True, False) \
        or R.changes("Salary Increment") != (False, True):
    fail.append("a promotion moves both the designation and the pay; a designation change the designation; "
                "a salary review the pay")
if not R.wants_preamble("Promotion") or R.wants_preamble("Salary Increment"):
    fail.append("the Candidate Preamble belongs to a promotion")

WHOLE = {"change_type": "Promotion", "employee": "HR-EMP-00001", "effective_date": "2026-10-01",
         "date_of_joining": "2023-01-09", "current_designation": "Machine Operator", "new_designation": "Shift Supervisor",
         "current_salary": 900000, "new_salary": 1400000, "new_supervisor": "HR-EMP-00002",
         "contract_action": R.AMEND, "contract": "HR-CON-00001", "contract_end": "2027-12-31",
         "job_description": "Shift Supervisor"}
expect("a promotion with everything", R.change_errors(WHOLE))
expect("no effective date", R.change_errors(dict(WHOLE, effective_date=None)), "Effective Date")
expect("effective before joining", R.change_errors(dict(WHOLE, effective_date="2022-01-01")), "before the employee joined")
expect("no new designation", R.change_errors(dict(WHOLE, new_designation=None)), "new designation")
expect("the designation already held", R.change_errors(dict(WHOLE, new_designation="Machine Operator")),
       "the one held already")
expect("nobody to report to", R.change_errors(dict(WHOLE, new_supervisor=None)), "report to")
expect("a promotion that lowers the pay", R.change_errors(dict(WHOLE, new_salary=800000)), "is below the current")
expect("a promotion that changes no pay", R.change_errors(dict(WHOLE, new_salary=900000)), "paid already")
expect("no job description", R.change_errors(dict(WHOLE, job_description=None)), "job description")
expect("nothing to amend", R.change_errors(dict(WHOLE, contract=None)), "no running contract")
expect("a new contract starting after the old one ends",
       R.change_errors(dict(WHOLE, contract_action=R.NEW, effective_date="2028-01-01")), "leave a gap")
expect("no contract, and told to leave it alone", R.change_errors(dict(WHOLE, contract=None, contract_action=R.NONE)))
INCREMENT = {"change_type": "Salary Increment", "employee": "HR-EMP-00001", "effective_date": "2026-07-01",
             "current_salary": 900000, "new_salary": 990000, "contract_action": R.NONE}
expect("a salary review", R.change_errors(INCREMENT))
expect("a salary review with no figure", R.change_errors(dict(INCREMENT, new_salary=None)), "new gross salary")
DESIGNATION = {"change_type": "Change of Designation", "employee": "HR-EMP-00001", "effective_date": "2026-07-01",
               "current_designation": "Clerk", "new_designation": "Senior Clerk", "new_supervisor": "HR-EMP-00002",
               "current_salary": 700000, "new_salary": 700000, "contract_action": R.NONE}
expect("a change of designation restating the same pay", R.change_errors(DESIGNATION))
expect("no type at all", R.change_errors({}), "what the letter is for")

PREAMBLE = {"change_type": "Promotion", "desired_position": "Shift Supervisor", "certification": "Diploma",
            "institution": "UTC", "experience": [{"designation": "Operator"}], "appraisal_score": 82}
expect("a preamble with everything", R.preamble_errors(PREAMBLE))
expect("no desired position", R.preamble_errors(dict(PREAMBLE, desired_position="")), "desired position")
expect("no certification", R.preamble_errors(dict(PREAMBLE, certification=" ")), "certification achieved")
expect("no experience", R.preamble_errors(dict(PREAMBLE, experience=[])), "work experience")
expect("no appraisal score", R.preamble_errors(dict(PREAMBLE, appraisal_score=None)), "appraisal score")
expect("a salary review needs no preamble", R.preamble_errors(dict(PREAMBLE, change_type="Salary Increment",
                                                                   desired_position="", experience=[])))

plan = R.contract_plan(R.AMEND, "HR-CON-00001", "2026-10-01")
if plan != {"amend": "HR-CON-00001"}:
    fail.append("amending leaves the contract where it is: %s" % plan)
plan = R.contract_plan(R.NEW, "HR-CON-00001", "2026-10-01", months=12)
if plan.get("close") != "HR-CON-00001" or plan.get("closed_on") != datetime.date(2026, 9, 30) \
        or plan["open"]["start_date"] != datetime.date(2026, 10, 1) or plan["open"]["end_date"] != datetime.date(2027, 9, 30):
    fail.append("a new contract runs from the effective date, the old one closed the day before: %s" % plan)
plan = R.contract_plan(R.NEW, "HR-CON-00001", "2026-11-01", months=12, end="2027-12-31")
if plan["open"]["end_date"] != datetime.date(2027, 10, 31):
    fail.append("a length given is what was asked for, whatever the contract it replaces would have run to: %s" % plan)
plan = R.contract_plan(R.NEW, "HR-CON-00001", "2026-10-01", end="2027-12-31")
if plan["open"]["end_date"] != datetime.date(2027, 12, 31):
    fail.append("with no length given, the new contract ends when the one it replaces would have: %s" % plan)
if R.contract_plan(R.NONE, "HR-CON-00001", "2026-10-01") or R.contract_plan(R.AMEND, None, "2026-10-01"):
    fail.append("nothing is done to the contract when there is none, or when it is to be left alone")
if R.DEFAULT_CONTRACT_ACTION != R.AMEND:
    fail.append("the letters say the other terms stand, so amending is the default")
if len(R.CONTRACT_ACTIONS) != 3 or R.NEW not in R.CONTRACT_ACTIONS:
    fail.append("Luuka asked for both: amend the running contract, or issue a new one")

for amount, words in ((0, "Zero"), (1, "One"), (15, "Fifteen"), (40, "Forty"), (100, "One Hundred"),
                      (118, "One Hundred and Eighteen"), (1000, "One Thousand"),
                      (900000, "Nine Hundred Thousand"),
                      (1400000, "One Million Four Hundred Thousand"),
                      (2450500, "Two Million Four Hundred and Fifty Thousand Five Hundred"),
                      (1000000000, "One Billion")):
    got = R.in_words(amount)
    if got != words:
        fail.append("%s written out must read %r, not %r" % (amount, words, got))
if R.in_words(None) != "" or R.in_words("") != "" or R.in_words("x") != "":
    fail.append("nothing written out is nothing at all, never a crash")
for amount, words in ((1400000.4, "One Million Four Hundred Thousand"),
                      (2499999.7, "Two Million Five Hundred Thousand")):
    if R.in_words(amount) != words:
        fail.append("the letters carry no cents: %s is rounded to %r, not %r" % (amount, words, R.in_words(amount)))
print("rules: what each letter must say, the preamble, the contract plan, the figure written out")

# ── 2. The signatures ─────────────────────────────────────────────────
if A.DOCTYPE != "Employee Position Change" or A.STATE_FIELD != "workflow_state":
    fail.append("the workflow is the Employee Position Change's")
route = [A.DRAFT, A.PENDING_SUPERVISOR, A.PENDING_HRM, A.PENDING_GM, A.PENDING_ED, A.APPROVED]
walked, state = [A.DRAFT], A.DRAFT
while True:
    forward = [t for t in A.TRANSITIONS if t["state"] == state and t["action"] in (A.SUBMIT, A.APPROVE)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != route:
    fail.append("the form is signed Supervisor, HR Manager, General Manager, Executive Director: %s" % walked)
if [row for row in A.STATES if row["state"] == A.APPROVED and row.get("doc_status") != "1"]:
    fail.append("the Executive Director's approval submits the form")
for state in A.PENDING_STATES:
    if not [t for t in A.TRANSITIONS if t["state"] == state and t["action"] == A.RETURN and t["next_state"] == A.DRAFT]:
        fail.append("%s must be able to return the form to Draft" % state)
if set(A.STAMPS) != set(A.PENDING_STATES):
    fail.append("every signature block on the paper is stamped: %s" % sorted(A.STAMPS))
if set(A.REMARK_FIELDS) != set(A.PENDING_STATES):
    fail.append("every signatory writes comments on the form: %s" % sorted(A.REMARK_FIELDS))
if "Legal Manager" not in A.NEW_ROLES:
    fail.append("the Legal Manager witnesses the renewal and salary letters: the role must be created on migrate")
for role in ("Supervisor", "Head of Department", "General Manager", "Executive Director"):
    if role not in A.NEW_ROLES:
        fail.append("%s signs the form: the role must be created on migrate" % role)

stamped = A.compute_stamps(A.PENDING_SUPERVISOR, A.PENDING_HRM, "sup@luuka.test", "2026-09-22", {})
if stamped["supervisor_by"] != "sup@luuka.test" or stamped["supervisor_on"] != "2026-09-22":
    fail.append("the step just passed is signed by whoever passed it: %s" % stamped)
if any(stamped[field] for field in ("hrm_by", "gm_by", "ed_by")):
    fail.append("only the step passed is signed: %s" % stamped)
signed = {"supervisor_by": "a", "supervisor_on": "2026-09-01", "hrm_by": "b", "hrm_on": "2026-09-02"}
if any(A.compute_stamps(A.PENDING_GM, A.DRAFT, "x", "2026-09-22", signed).values()):
    fail.append("a return to Draft clears every signature")
if A.compute_stamps(A.PENDING_HRM, A.PENDING_HRM, "x", "2026-09-22", signed) != dict(
        signed, gm_by=None, gm_on=None, ed_by=None, ed_on=None):
    fail.append("a save that changes no state leaves the signatures as they were")
expect("returned without saying why", A.step_errors(A.PENDING_GM, A.DRAFT, {}), "Return Remarks")
expect("returned with a reason", A.step_errors(A.PENDING_GM, A.DRAFT, {"return_remarks": "Wrong grade"}))
expect("passed on without comments", A.step_errors(A.PENDING_HRM, A.PENDING_GM, {}), "HR Manager's comments")
expect("passed on with comments", A.step_errors(A.PENDING_HRM, A.PENDING_GM, {"hrm_remarks": "Supported"}))
if A.next_states(A.PENDING_ED, ["Executive Director"]) != [(A.APPROVE, A.APPROVED), (A.RETURN, A.DRAFT)]:
    fail.append("the Executive Director may approve or return: %s" % A.next_states(A.PENDING_ED, ["Executive Director"]))
if A.next_states(A.PENDING_ED, ["HR User"]):
    fail.append("nobody but the Executive Director acts on a form waiting for them")
print("signatures: Supervisor to Executive Director, returns, stamps, the Legal Manager role")

# ── 3. The forms carry the paper ──────────────────────────────────────
PAPER = {
    "Employee Position Change": [
        # the preamble's six sections
        "employee", "employee_name", "employee_number", "employee_contact", "current_designation", "department",
        "date_of_joining", "current_supervisor", "desired_position", "education", "a_level", "o_level", "experience",
        "appraisal_score",
        # what the letter says
        "change_type", "new_designation", "new_supervisor", "new_salary", "new_salary_in_words", "effective_date",
        "current_salary", "job_description",
        # what happens to the contract
        "contract", "contract_action", "new_contract", "salary_structure_assignment",
        # the signatures
        "supervisor_remarks", "hrm_remarks", "gm_remarks", "ed_remarks", "return_remarks", "status", "workflow_state",
        *A.ALL_STAMP_FIELDS,
    ],
    "Employee Data Change Request": [
        "change_type", "employee", "employee_name", "designation", "request_date", "status",
        "current_bank_name", "current_branch", "current_account_name", "current_account_number",
        "new_bank_name", "new_branch", "new_account_name", "new_account_number",
        "current_phone_number", "current_registered_names", "new_phone_number", "new_registered_names",
        "hr_remarks", "approved_by", "approved_on", "applied",
    ],
    "Intern Placement": [
        "intern_name", "salutation", "school", "applied_on", "start_date", "end_date", "branch", "department",
        "section", "supervisor", "supervisor_designation", "status",
    ],
}
for name, wanted in PAPER.items():
    spec = doctype(name)
    if not spec:
        fail.append("%s is not there" % name)
        continue
    fields = fields_of(spec)
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the paper asks for" % (name, fieldname))
    if not spec.get("is_submittable"):
        fail.append("%s must be submittable: it is approved, and cancelling puts back what it changed" % name)
    roles = {row["role"] for row in spec.get("permissions", [])}
    if not {"HR Manager", "HR User"} <= roles:
        fail.append("%s: the HR Manager and the branch HR Officer must be able to work it (%s)" % (name, sorted(roles)))

spec = doctype("Employee Position Change")
fields = fields_of(spec)
if (fields.get("change_type") or {}).get("options", "").split("\n") != list(R.CHANGE_TYPES):
    fail.append("Employee Position Change.change_type must offer exactly %s" % (R.CHANGE_TYPES,))
if (fields.get("contract_action") or {}).get("options", "").split("\n") != list(R.CONTRACT_ACTIONS):
    fail.append("Employee Position Change.contract_action must offer exactly %s" % (R.CONTRACT_ACTIONS,))
if (fields.get("status") or {}).get("options", "").split("\n") != list(R.STATUSES):
    fail.append("Employee Position Change.status must follow the workflow's states")
for fieldname in ("current_designation", "current_salary", "new_salary_in_words", "new_contract",
                  "salary_structure_assignment", *A.ALL_STAMP_FIELDS):
    if not (fields.get(fieldname) or {}).get("read_only"):
        fail.append("Employee Position Change.%s is worked out, not typed: it must be read-only" % fieldname)
for role in ("Supervisor", "General Manager", "Executive Director"):
    if role not in {row["role"] for row in spec["permissions"]}:
        fail.append("Employee Position Change: %s signs it and must be able to open it" % role)
if not [row for row in spec["permissions"] if row["role"] == "Executive Director" and row.get("submit")]:
    fail.append("Employee Position Change: the Executive Director's approval submits it, so they need submit")
for fieldname, depends in (("new_designation", "Salary Increment"), ("desired_position", "Promotion")):
    if depends not in (fields[fieldname].get("depends_on") or ""):
        fail.append("Employee Position Change.%s must be shown only where it belongs" % fieldname)

spec = doctype("Employee Data Change Request")
fields = fields_of(spec)
if (fields.get("change_type") or {}).get("options", "").split("\n") != list(D.CHANGE_TYPES):
    fail.append("Employee Data Change Request.change_type must offer exactly %s" % (D.CHANGE_TYPES,))
for change_type in D.CHANGE_TYPES:
    for field, source, label in D.fields_for(change_type):
        for prefix in (D.CURRENT, D.NEW):
            if prefix % field not in fields:
                fail.append("Employee Data Change Request has no %s (%s)" % (prefix % field, label))
        if not (fields.get(D.CURRENT % field) or {}).get("read_only"):
            fail.append("Employee Data Change Request.%s is read off the employee: it must be read-only" % (D.CURRENT % field))
if not [row for row in spec["permissions"] if row["role"] == "Employee" and row.get("if_owner")]:
    fail.append("an employee must be able to raise their own change request, and only their own")
employee_fields = fields_of(upstream_doctype("Employee") or {})
ours = custom_fields("Employee")
for change_type in D.CHANGE_TYPES:
    for field, source, label in D.fields_for(change_type):
        if source not in employee_fields and source not in ours:
            fail.append("the request writes Employee.%s (%s), which is neither upstream nor one of our custom fields"
                        % (source, label))
for fieldname in ("custom_nssf_no", "custom_tin", "custom_nin", "custom_salary_from_month", "custom_bank_declared_on",
                  "custom_bank_witness", "custom_signed_bank_form"):
    if fieldname not in ours:
        fail.append("LPL/HR/26 asks for Employee.%s, which is not among our custom fields" % fieldname)
print("forms: the preamble's six sections, both change requests, the placement, with the rights each role needs")

# ── 4. The glue ───────────────────────────────────────────────────────
positions = read("hrms_addon", "hrms_addon", "positions.py")
employee_data = read("hrms_addon", "hrms_addon", "employee_data.py")
own = {name: fields_of(doctype(name)) for name in PAPER}
for fieldname in sorted(set(re.findall(r'doc\.db_set\("(\w+)"', positions))
                        | set(re.findall(r'doc\.db_set\(\{"(\w+)"', positions))
                        | set(re.findall(r'doc\.get\("(\w+)"\)', positions))):
    if fieldname not in own["Employee Position Change"]:
        fail.append("positions.py reads or writes %s, which the Employee Position Change does not have" % fieldname)
PLACEMENT = set(own["Intern Placement"])
for fieldname in sorted(set(re.findall(r'doc\.set\("(\w+)"', employee_data))
                        | set(re.findall(r'doc\.db_set\(\{"(\w+)"', employee_data))
                        | set(re.findall(r'doc\.db_set\("(\w+)"', employee_data))
                        | set(re.findall(r'doc\.get\("(\w+)"\)', employee_data))):
    if fieldname not in own["Employee Data Change Request"] and fieldname not in PLACEMENT:
        fail.append("employee_data.py reads or writes %s, which neither the request nor the placement has"
                    % fieldname)
for name, spec in (("Employee Contract", None), ("Salary Structure Assignment", None)):
    if not doctype(name) and upstream_doctype(name) is None:
        fail.append("%s is not there to write to" % name)
ssa = fields_of(upstream_doctype("Salary Structure Assignment") or {})
for fieldname in ("employee", "salary_structure", "from_date", "base", "company"):
    if ssa and fieldname not in ssa:
        fail.append("the salary assignment sets %s, which Salary Structure Assignment does not have" % fieldname)
contract = fields_of(doctype("Employee Contract"))
for fieldname in ("designation", "base_salary", "start_date", "end_date", "status", "renewed_by", "employment_type"):
    if fieldname not in contract:
        fail.append("positions.py works Employee Contract.%s, which does not exist" % fieldname)
for needle, why in (
    ('if doc.docstatus == 1:\n        return  # what was approved stands', "what was approved is not overwritten later"),
    ("rules.contract_plan(", "the contract follows the plan the rules give"),
    ("rules.change_errors(facts) + rules.preamble_errors(facts)", "the change and the preamble are judged as it is sent on"),
    ("approval.compute_stamps(", "the signatures are stamped by the workflow"),
    ("def _apply(doc):", "the approved change is applied in one place"),
    ("assignment.submit()", "the new gross is assigned and submitted, so payroll pays it"),
    ("people.notify(", "whoever signs next is told"),
    ("doc.new_salary_in_words = rules.in_words(", "the letter's figure is written out on every save"),
):
    if needle not in positions:
        fail.append("positions.py: %s (%r not found)" % (why, needle))
def body_of(source, name):
    """A function's own lines, so a needle cannot be satisfied by another."""
    start = source.index("\ndef %s(" % name)
    rest = source[start + 1:]
    end = rest.index("\ndef ", 1) if "\ndef " in rest[1:] else len(rest)
    return rest[:end]


for needle, why in (
    ("rules.request_errors(", "a change request is judged by the rules"),
    ("rules.employee_update(", "only the fields the rules map are written to the employee"),
    ('doc.db_set({"status": "Approved"', "approving records who did it and when"),
    ("people.hr_officers(", "the branch HR Officer is told of a request"),
):
    if needle not in employee_data:
        fail.append("employee_data.py: %s (%r not found)" % (why, needle))
for name, needle, why in (
    ("approve", 'doc.check_permission("submit")', "approve must check the caller may submit: it writes to the Employee"),
    ("reject", 'doc.check_permission("submit")', "reject must check the caller may submit"),
    ("approve", 'frappe.db.set_value("Employee", doc.employee, update', "approving is what writes to the Employee"),
    ("request_on_cancel", 'if doc.get("applied"):',
     "cancelling only puts back what was really applied"),
    ("request_on_cancel", 'frappe.db.set_value("Employee", doc.employee, back',
     "cancelling puts the old details back"),
):
    if needle not in body_of(employee_data, name):
        fail.append("employee_data.%s: %s (%r not found there)" % (name, why, needle))
if 'frappe.db.set_value("Employee"' in body_of(employee_data, "request_on_submit"):
    fail.append("employee_data.request_on_submit must not write to the Employee: HR approves first")
for name in ("get_background", "letter_for"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, positions):
        fail.append("positions.%s must be whitelisted for the form" % name)
for name in ("approve", "reject"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, employee_data):
        fail.append("employee_data.%s changes something: a whitelisted POST method" % name)
print("glue: fields that exist here and upstream, the plan followed, the buttons' methods whitelisted")

# ── 5. The letters ────────────────────────────────────────────────────
LETTERS = {
    "Promotion Letter": ("Employee Position Change", ["RE: PROMOTION", "decided to promote you", "revised upwards",
                                                      "attached job description", "EXECUTIVE DIRECTOR",
                                                      "All other terms and conditions remain the same"]),
    "Change of Designation Letter": ("Employee Position Change", ["RE: CHANGE OF DESIGNATION", "change your job designation",
                                                                  "in line with your job description",
                                                                  "statutory", "EXECUTIVE DIRECTOR"]),
    "Salary Increment Letter": ("Employee Position Change", ["RE: SALARY REVIEW", "salary review exercise",
                                                             "monthly gross pay", "accepts(legal=1)",
                                                             "EXECUTIVE DIRECTOR"]),
    "Candidate Preamble Promotion Form": ("Employee Position Change", [
        "Personal Information", "Current Position", "Desired Position", "Education", "Work Experience",
        "Performance Evaluation",
        *['comment("%s"' % who for who in ("Supervisor", "Human Resource Manager", "General Manager",
                                            "Executive Director")]]),
    "Intern Placement Letter": ("Intern Placement", ["RE: PLACEMENT FOR INTERNSHIP", "internship placement effective",
                                                     "assignment of duties", "HUMAN RESOURCE MANAGER"]),
    "Bank Account Change Request": ("Employee Data Change Request", ["LPL/HR/34", "Request for Change of Salary Account",
                                                                     "future salary payments"]),
    "Phone Number Change Request": ("Employee Data Change Request", ["LPL/HR/33", "Request for Change of Phone Number",
                                                                     "Registered Names", "future wage payments"]),
    "Employee Bank Account NSSF and TIN Form": ("Employee", ["LPL/HR/26", "EMPLOYEE ADVICE AND INSTRUCTIONS",
                                                             "EMPLOYEE DECLARATION", "NSSF Number", "Tin Number",
                                                             "NIN Number", "Witnessed by"]),
}
for name, (doc_type, needles) in LETTERS.items():
    spec = print_format(name)
    if not spec:
        fail.append("the %s print format is not there" % name)
        continue
    if spec.get("doc_type") != doc_type:
        fail.append("%s must print a %s, not a %s" % (name, doc_type, spec.get("doc_type")))
    html = spec.get("html") or ""
    for needle in needles:
        if needle not in html:
            fail.append("%s does not say %r, which the paper does" % (name, needle))
    if "{{" not in html:
        fail.append("%s fills nothing in" % name)
    available = own.get(doc_type) or fields_of(upstream_doctype(doc_type) or {}) or {}
    available = dict(available)
    if doc_type == "Employee":
        available.update(custom_fields("Employee"))
    for fieldname in sorted(set(re.findall(r"doc\.(\w+)", html))):
        if fieldname in ("name", "creation", "owner", "modified", "doctype", "docstatus", "get"):
            continue
        if fieldname not in available:
            fail.append("%s prints doc.%s, which the %s does not have" % (name, fieldname, doc_type))
for name in ("Promotion Letter", "Change of Designation Letter", "Salary Increment Letter"):
    html = (print_format(name) or {}).get("html") or ""
    printed = html.split("lpl-letter\">", 1)[-1]  # past the macros, into the letter itself
    if printed.count("hrms_addon_in_words") < (2 if name != "Change of Designation Letter" else 1):
        fail.append("%s must print the gross it moves from and to in words, not only in figures" % name)
    guard = re.search(r'\{%-? if doc\.change_type != "([^"]+)"', html)
    if not guard:
        fail.append("%s must say so when it is printed for another kind of change" % name)
    elif guard.group(1) not in R.CHANGE_TYPES:
        fail.append("%s guards on %r, which is not a change type" % (name, guard.group(1)))
for name, expected in R.LETTERS.items():
    if expected not in LETTERS:
        fail.append("position_rules names the letter %r for a %s, and there is no such print format" % (expected, name))
for name, (_doc_type, _needles) in LETTERS.items():
    html = (print_format(name) or {}).get("html") or ""
    for bad in re.findall(r"\{\{\s*doc\.(\w+)\s*\}\}", html):
        fail.append("%s prints doc.%s unescaped: use v()" % (name, bad))
print("letters: the paper's words, from fields that exist, the figure in words, nothing printed unescaped")

# ── 6. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
if "hrms_addon.hrms_addon.positions.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must build the position change workflow and its roles")
if "hrms_addon.hrms_addon.positions.in_words" not in ((hooks.get("jinja") or {}).get("methods") or []):
    fail.append("the letters print the gross in words through a jinja method")
if "hrms_addon.hrms_addon.positions.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the scheduler closes an internship whose end date has passed")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.seed_position_roles" not in patches:
    fail.append("a site that has the app already must get the new roles by patch")
if "position_approval.NEW_ROLES" not in read("hrms_addon", "patches", "v1_0", "seed_position_roles.py"):
    fail.append("the patch must seed exactly the roles the workflow declares")
for name, module, prefix, methods in (
        ("employee_position_change", "positions", "change", ("validate", "on_submit", "on_cancel")),
        ("employee_data_change_request", "employee_data", "request", ("validate", "on_submit", "on_cancel")),
        ("intern_placement", "employee_data", "placement", ("validate", "on_submit", "on_cancel"))):
    controller = open(os.path.join(APP, "doctype", name, name + ".py"), encoding="utf-8").read()
    for method in methods:
        if "    def %s(self):\n        %s.%s_%s(self)" % (method, module, prefix, method) not in controller:
            fail.append("the %s controller must hand %s to %s.%s_%s" % (name, method, module, prefix, method))
navigation = load("navigation_rules")
carded = {link[1] for cards in navigation.CARDS.values() for _card, links in cards for link in links}
sidebarred = {entry[1] for entries in navigation.SIDEBAR.values() for entry in entries}
for name in PAPER:
    if name not in carded:
        fail.append("%s is on no workspace card: it could only be found by searching for its DocType" % name)
    if name not in sidebarred:
        fail.append("%s is in no sidebar: HR would have to open the workspace page every time" % name)
conn = read("hrms_addon", "hrms_addon", "connections.py")
for name in ("Employee Position Change", "Employee Data Change Request"):
    if name not in conn:
        fail.append("%s must show on the Employee's Connections" % name)
for name in PAPER:
    folder = name.lower().replace(" ", "_")
    if not os.path.exists(os.path.join(APP, "doctype", folder, folder + "_dashboard.py")):
        fail.append("%s has no Connections of its own (%s_dashboard.py)" % (name, folder))
print("wiring: the workflow and roles on migrate, the jinja method, the daily job, the patch, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CONTRACT MANAGEMENT CHECKS PASSED")
