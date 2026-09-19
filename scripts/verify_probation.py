"""Checks for the probation and the 30-60-90 reviews, run without a bench.

probation_rules.py, probation_approval.py and review_approval.py import
nothing from Frappe, so they are loaded directly and exercised:

  * the End of probation evaluation form (LPL/HR/32): the 13 ratable factors
    in the form's order, N/A left out, Section A weighing 60 and Section B
    40, the bands, the pass mark, the probation's end and an extension's,
    the objectives taken from the Job Title's Key Result Areas;
  * its workflow: HR, the supervisor, the branch General Manager for a
    non-administrative position only, the Head of Department, the HR
    Manager's recommendation and the Executive Director's decision; every
    step's checks and signatures;
  * the Staff Onboarding Form (LPL/HR/04) at 30, 60 and 90 days: HR, the
    supervisor's comments, the HR Manager's remarks.

It also cross-checks the DocTypes (every field the glue and the print
formats use exists; statuses, signatures, permissions for each step's
role), the glue (the decision applied to the Employee, the extension's new
evaluation, the termination hand-off, the reviews made once each), the
settings and their defaults, the seeds, hooks and patches.

    python scripts/verify_probation.py
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


def fields_of(spec):
    return {f["fieldname"]: f for f in spec.get("fields", [])}


R = load("probation_rules")
P = load("probation_approval")
V = load("review_approval")
C = load("contract_rules")
org = load("org_rules")
print("loaded probation_rules.py, probation_approval.py and review_approval.py without Frappe")

# ── 1. The form's scoring (LPL/HR/32) ─────────────────────────────────
if len(R.FACTORS) != 13 or R.FACTORS[0] != "Job performance, work output, quality of work" \
        or R.FACTORS[-1] != "Participates in cost cutting measures":
    fail.append("the ratable factors are the form's 13, in its order")
if R.PROBATION_MASTERS != {"Probation Factor": ("factor_name", R.FACTORS)}:
    fail.append("the Probation Factor list is seeded with exactly the form's factors")
if any(c in f for f in R.FACTORS for c in "<>"):
    fail.append("a factor is a record name: no < or >")
if R.RATINGS != ("1", "2", "3", "4", "5", "N/A"):
    fail.append("ratings are 1 to 5 or N/A")
for label, got, want in (
    ("all fives", R.scores(["5"] * 13, ["5"] * 3), {"factors": 60.0, "objectives": 40.0, "total": 100.0}),
    ("N/A left out", R.scores(["4", "N/A", "4", "", None], ["3", "3"]), {"factors": 48.0, "objectives": 24.0, "total": 72.0}),
    ("objectives not rated", R.scores(["4", "4"], ["", "N/A"]), {"factors": 48.0, "objectives": None, "total": 80.0}),
    ("nothing rated", R.scores([], []), {"factors": None, "objectives": None, "total": None}),
    ("mixed", R.scores(["5", "3"], ["2"]), {"factors": 48.0, "objectives": 16.0, "total": 64.0}),
):
    if got != want:
        fail.append("scores, %s: %s, expected %s" % (label, got, want))
for total, band in ((100, "Excellent"), (90, "Excellent"), (89.9, "Very Good"), (75, "Very Good"), (74.9, "Good"),
                    (60, "Good"), (59.9, "Average"), (50, "Average"), (49.9, "Below Average"), (0, "Below Average"),
                    (None, None)):
    if R.band(total) != band:
        fail.append("band(%s) is %r, expected %r (the form's Section C)" % (total, R.band(total), band))
if not R.passed(60, 60) or R.passed(59.9, 60) or R.passed(None, 60):
    fail.append("passed: the total reaches the pass mark; nothing rated never passes")
for start, months, want in (("2026-01-31", 1, "2026-02-28"), ("2028-01-31", 1, "2028-02-29"), ("2026-09-19", 6, "2027-03-19"),
                            ("2026-11-30", 3, "2027-02-28"), ("2026-12-15", 1, "2027-01-15")):
    if str(R.add_months(start, months)) != want:
        fail.append("add_months(%s, %d) is %s, expected %s" % (start, months, R.add_months(start, months), want))
if str(R.probation_end("2026-09-19", 6)) != "2027-03-19":
    fail.append("probation_end: the joining date plus the probation months")
kras = ["Meet the daily output target", "  meet the daily   output target ", "Zero defects", "", None] + ["KPI %d" % n for n in range(10)]
if R.objectives_from_kras(kras) != ["Meet the daily output target", "meet the daily output target", "Zero defects",
                                    "KPI 0", "KPI 1", "KPI 2", "KPI 3", "KPI 4"]:
    fail.append("objectives_from_kras: each Key Result Area once (spaces tidied), at most the form's 8: %s"
                % R.objectives_from_kras(kras))
if set(R.STATUS_AFTER) != set(R.DECISIONS) or R.STATUS_AFTER[R.CONFIRM] != R.CONFIRMED \
        or R.STATUS_AFTER[R.EXTEND] != R.EXTENDED or R.STATUS_AFTER[R.TERMINATE] != R.NOT_CONFIRMED:
    fail.append("each decision leaves the Employee Confirmed, Extended or Not Confirmed")
print("scoring: 13 factors, N/A left out, 60/40, the form's bands, pass mark, probation dates, objectives from the JD")

# ── 2. The probation workflow ─────────────────────────────────────────
state_names = list(dict.fromkeys(s["state"] for s in P.STATES))
ORDER = [P.DRAFT, P.PENDING_SUPERVISOR, P.PENDING_GM, P.PENDING_HOD, P.PENDING_HRM, P.PENDING_ED, P.DECIDED, P.CANCELLED]
if state_names != ORDER:
    fail.append("probation states %s, expected %s" % (state_names, ORDER))
for name in state_names:
    rows = [s for s in P.STATES if s["state"] == name]
    docstatus = {P.DECIDED: "1", P.CANCELLED: "2"}.get(name, "0")
    if {s.get("doc_status", "0") for s in rows} != {docstatus}:
        fail.append("probation %s must have doc_status %s" % (name, docstatus))
    if {s["status"] for s in rows} != {name}:
        fail.append("probation %s writes its own name as the Status" % name)
    if {bool(s["send_email"]) for s in rows} != {name.startswith("Pending")}:
        fail.append("probation %s must %ssend email" % (name, "" if name.startswith("Pending") else "not "))
EDITORS = {P.DRAFT: set(P.PREPARERS), P.PENDING_SUPERVISOR: set(P.SUPERVISORS), P.PENDING_GM: {P.GM},
           P.PENDING_HOD: {P.HOD}, P.PENDING_HRM: {P.HRM}, P.PENDING_ED: {P.ED}, P.DECIDED: {P.HRM}, P.CANCELLED: {P.HRM}}
for name, roles in EDITORS.items():
    if {s["allow_edit"] for s in P.STATES if s["state"] == name} != roles:
        fail.append("probation %s must be editable by %s" % (name, sorted(roles)))
for category, route in (("Non-Administrative", [P.PENDING_GM, P.PENDING_HOD]), ("Administrative", [P.PENDING_HOD]),
                        (None, [P.PENDING_GM, P.PENDING_HOD])):
    state, path = P.PENDING_SUPERVISOR, []
    for _ in range(3):
        role = {P.PENDING_SUPERVISOR: "Supervisor", P.PENDING_GM: P.GM, P.PENDING_HOD: P.HOD}.get(state)
        moves = [move for move in P.next_states(state, [role], category) if move[0] == P.APPROVE]
        if len(moves) != 1:
            fail.append("%s evaluation at %s: exactly one Approve expected, got %s" % (category, state, moves))
            break
        state = moves[0][1]
        path.append(state)
        if state == P.PENDING_HRM:
            break
    if path[:-1] != route or path[-1] != P.PENDING_HRM:
        fail.append("a %s evaluation goes %s, expected %s then the HR Manager" % (category, path, route))
if P.next_states(P.PENDING_HRM, [P.HRM]) != [(P.APPROVE, P.PENDING_ED)] or \
        P.next_states(P.PENDING_ED, [P.ED]) != [(P.DECIDE, P.DECIDED)]:
    fail.append("the HR Manager recommends to the Executive Director, who decides")
if P.next_states(P.PENDING_SUPERVISOR, ["Supervisor"], "Administrative")[-1:] != [(P.RETURN, P.DRAFT)]:
    fail.append("the supervisor can return the evaluation to HR")
if P.next_states(P.PENDING_ED, ["HR Manager", "General Manager", "Supervisor"]):
    fail.append("only the Executive Director decides")
for t in P.TRANSITIONS:
    if t.get("condition") not in (None, P.IS_ADMINISTRATIVE, P.NOT_ADMINISTRATIVE):
        fail.append("unknown condition %r" % t.get("condition"))
if P.CATEGORY_FIELD not in P.IS_ADMINISTRATIVE or P.CATEGORY_FIELD not in P.NOT_ADMINISTRATIVE \
        or '"%s"' % org.ADMINISTRATIVE not in P.IS_ADMINISTRATIVE:
    fail.append("the route conditions read the evaluation's %s against org_rules.ADMINISTRATIVE" % P.CATEGORY_FIELD)
if not set(P.NEW_ROLES) >= {"Supervisor", "General Manager", "Head of Department", "Executive Director"}:
    fail.append("the probation workflow makes sure its roles exist")
print("probation workflow: %d states; the General Manager only for non-administrative positions; one Approve per step"
      % len(state_names))

# ── 3. The probation steps and signatures ─────────────────────────────
RATED = [{"label": "Attendance", "employee_rating": "4", "supervisor_rating": "4"}]
FACTS = {"factors": RATED, "objectives": RATED, "supervisor_remarks": "Good start", "manager_remarks": "Agree",
         "hod_remarks": "Agree", "hrm_recommendation": "Confirm", "hrm_remarks": "Confirm", "ed_decision": "Confirm",
         "end_of_probation": "2027-03-19", "confirmation_date": "2027-03-19", "new_end_of_probation": None}
step = P.step_errors
expect("to the supervisor", step(P.DRAFT, P.PENDING_SUPERVISOR, FACTS))
expect("no self-assessment", step(P.DRAFT, P.PENDING_SUPERVISOR, dict(FACTS, factors=[{"label": "Attendance", "employee_rating": ""}])),
       "The employee's self-assessment first: rate every factor, or N/A where it does not fit the job (Section A): Attendance.")
expect("no objectives", step(P.DRAFT, P.PENDING_SUPERVISOR, dict(FACTS, objectives=[])), "List the probation objectives")
expect("no factors", step(P.DRAFT, P.PENDING_SUPERVISOR, dict(FACTS, factors=[])), "List the ratable factors")
expect("supervisor done", step(P.PENDING_SUPERVISOR, P.PENDING_GM, FACTS))
expect("supervisor has not rated", step(P.PENDING_SUPERVISOR, P.PENDING_HOD, dict(FACTS, objectives=[{"label": "KPI 1", "employee_rating": "3"}])),
       "Give the supervisor's rating for every factor and objective: KPI 1.")
expect("supervisor without remarks", step(P.PENDING_SUPERVISOR, P.PENDING_GM, dict(FACTS, supervisor_remarks=" ")),
       "Write the Immediate Supervisor's remarks")
expect("return without a reason", step(P.PENDING_SUPERVISOR, P.DRAFT, dict(FACTS, supervisor_remarks="")),
       "Write in the Immediate Supervisor's remarks what HR should correct")
expect("the General Manager without remarks", step(P.PENDING_GM, P.PENDING_HOD, dict(FACTS, manager_remarks="")),
       "Write the Manager's remarks")
expect("the Head of Department without remarks", step(P.PENDING_HOD, P.PENDING_HRM, dict(FACTS, hod_remarks="")),
       "Write the Head of Department's remarks")
expect("the HR Manager without a recommendation", step(P.PENDING_HRM, P.PENDING_ED, dict(FACTS, hrm_recommendation="", hrm_remarks="")),
       "Choose the HR Manager's recommendation", "Write the HR Manager's remarks")
expect("a decision", step(P.PENDING_ED, P.DECIDED, FACTS))
expect("no decision", step(P.PENDING_ED, P.DECIDED, dict(FACTS, ed_decision="")), "Choose the Executive Director's decision")
expect("an extension ending too soon", step(P.PENDING_ED, P.DECIDED, dict(FACTS, ed_decision="Extend Probation",
                                                                           new_end_of_probation="2027-03-01")),
       "The extended probation must end after the current End of Probation (2027-03-19).")
expect("an extension", step(P.PENDING_ED, P.DECIDED, dict(FACTS, ed_decision="Extend Probation", new_end_of_probation="2027-06-19")))
expect("a confirmation with no date", step(P.PENDING_ED, P.DECIDED, dict(FACTS, confirmation_date=None)), "Set the Confirmation Date")
expect("a termination", step(P.PENDING_ED, P.DECIDED, dict(FACTS, ed_decision="Terminate")))
USER, TODAY = "sup@luuka", "2027-03-01"
current = {"supervisor_by": "old@x", "supervisor_on": "2027-02-01"}
stamps = P.compute_stamps(P.PENDING_SUPERVISOR, P.PENDING_GM, USER, TODAY, {})
if (stamps["supervisor_by"], stamps["supervisor_on"]) != (USER, TODAY) or stamps["hod_by"]:
    fail.append("passing the supervisor's step signs it, and only it: %s" % stamps)
stamps = P.compute_stamps(P.PENDING_SUPERVISOR, P.DRAFT, USER, TODAY, current)
if stamps["supervisor_by"] or stamps["supervisor_on"]:
    fail.append("a return to HR clears the supervisor's signature")
stamps = P.compute_stamps(P.PENDING_HOD, P.PENDING_HOD, "typed@x", TODAY, current)
if (stamps["supervisor_by"], stamps["supervisor_on"]) != ("old@x", "2027-02-01"):
    fail.append("a save that is not a step keeps the signatures as they were")
stamps = P.compute_stamps(P.PENDING_ED, P.DECIDED, "ed@luuka", TODAY, current)
if (stamps["ed_by"], stamps["ed_on"]) != ("ed@luuka", TODAY):
    fail.append("the decision is signed by the Executive Director")
if P.compute_stamps(None, P.DRAFT, USER, TODAY, current) != dict.fromkeys(P.ALL_STAMP_FIELDS):
    fail.append("a new evaluation starts unsigned")
print("probation steps: self-assessment, ratings, each reviewer's remarks, the recommendation and the decision checked")

# ── 4. The 30-60-90 reviews (LPL/HR/04) ───────────────────────────────
if V.REVIEW_DAYS != (30, 60, 90):
    fail.append("the reviews are at 30, 60 and 90 days")
review_states = list(dict.fromkeys(s["state"] for s in V.STATES))
if review_states != [V.DRAFT, V.PENDING_SUPERVISOR, V.PENDING_HRM, V.COMPLETED, V.CANCELLED]:
    fail.append("review states %s" % review_states)
got = sorted((t["state"], t["action"], t["next_state"], t["allowed"]) for t in V.TRANSITIONS)
want = sorted([(V.DRAFT, V.SUBMIT, V.PENDING_SUPERVISOR, r) for r in V.PREPARERS]
              + [(V.PENDING_SUPERVISOR, V.FORWARD, V.PENDING_HRM, r) for r in V.SUPERVISORS]
              + [(V.PENDING_HRM, V.COMPLETE, V.COMPLETED, V.HRM), (V.COMPLETED, V.CANCEL, V.CANCELLED, V.HRM)])
if got != want:
    fail.append("review transitions %s, expected %s" % (got, want))
for s in V.STATES:
    want_status = {V.COMPLETED: "1", V.CANCELLED: "2"}.get(s["state"], "0")
    if s.get("doc_status", "0") != want_status:
        fail.append("review %s must have doc_status %s" % (s["state"], want_status))
if set(V.SUPERVISORS) != {"Supervisor", "Head of Department"}:
    fail.append("the supervisor's step is open to the Supervisor and the Head of Department (the To-Be: the HOD monitors)")
REVIEW_FACTS = {"roles_responsibilities": "Operate the extruder", "feel_about_role": "Happy", "supervisor_comments": "Good",
                "hrm_remarks": "Noted"}
expect("to the supervisor", V.step_errors(V.DRAFT, V.PENDING_SUPERVISOR, REVIEW_FACTS))
expect("the employee's answers missing", V.step_errors(V.DRAFT, V.PENDING_SUPERVISOR, {}),
       "Record the roles and responsibilities", "Record how the new employee feels")
expect("no supervisor's comments", V.step_errors(V.PENDING_SUPERVISOR, V.PENDING_HRM, {}), "Write the supervisor's general comments")
expect("no HR Manager's remarks", V.step_errors(V.PENDING_HRM, V.COMPLETED, {}), "Write the Human Resources Manager's remarks")
expect("complete", V.step_errors(V.PENDING_HRM, V.COMPLETED, REVIEW_FACTS))
stamps = V.compute_stamps(V.PENDING_HRM, V.COMPLETED, "hrm@x", "2026-11-01", {"supervisor_by": "sup@x", "supervisor_on": "2026-10-30"})
if (stamps["hrm_by"], stamps["hrm_on"], stamps["supervisor_by"]) != ("hrm@x", "2026-11-01", "sup@x"):
    fail.append("completing signs the HR Manager's part and keeps the supervisor's: %s" % stamps)
print("30-60-90 reviews: the form's three steps, each one's answers or remarks, signatures")

# ── 5. DocTypes ───────────────────────────────────────────────────────
PE, OR, SET = doctype("Probation Evaluation"), doctype("Onboarding Review"), doctype("Onboarding Settings")
pe, orv, settings = fields_of(PE), fields_of(OR), fields_of(SET)
for spec, rules_module, label in ((pe, P, "Probation Evaluation"), (orv, V, "Onboarding Review")):
    statuses = [o for o in (spec.get("status", {}).get("options") or "").split("\n") if o]
    if statuses != list(dict.fromkeys(s["status"] for s in rules_module.STATES)):
        fail.append("%s.status must offer exactly the workflow's statuses: %s" % (label, statuses))
    for field in rules_module.ALL_STAMP_FIELDS:
        if not (spec.get(field) or {}).get("read_only"):
            fail.append("%s.%s is a signature: it must exist, read-only" % (label, field))
    if not (spec.get("workflow_state") or {}).get("hidden"):
        fail.append("%s needs its hidden workflow_state field" % label)
for spec_json, rules_module, label in ((PE, P, "Probation Evaluation"), (OR, V, "Onboarding Review")):
    perms = {p["role"]: p for p in spec_json.get("permissions", [])}
    if not spec_json.get("is_submittable"):
        fail.append("%s must be submittable" % label)
    for s in rules_module.STATES:
        if not (perms.get(s["allow_edit"]) or {}).get("write"):
            fail.append("%s: %s edits it at %s but has no write" % (label, s["allow_edit"], s["state"]))
    for t in rules_module.TRANSITIONS:
        need = "submit" if t["next_state"] in (P.DECIDED, V.COMPLETED) else "cancel" if t["action"] == "Cancel" else "write"
        if not (perms.get(t["allowed"]) or {}).get(need):
            fail.append("%s: %s moves it to %s and needs %s" % (label, t["allowed"], t["next_state"], need))
if (pe.get("position_category") or {}).get("fetch_from") != "department.custom_position_category":
    fail.append("Probation Evaluation.position_category must come from the Department (the route's condition)")
for child, fieldnames in (("Probation Evaluation Factor", ("employee_rating", "supervisor_rating")),
                          ("Probation Evaluation Objective", ("employee_rating", "supervisor_rating"))):
    child_fields = fields_of(doctype(child))
    for fieldname in fieldnames:
        options = [o for o in ((child_fields.get(fieldname) or {}).get("options") or "").split("\n") if o]
        if options != list(R.RATINGS):
            fail.append("%s.%s must offer exactly the ratings %s" % (child, fieldname, R.RATINGS))
for table, child in (("factors", "Probation Evaluation Factor"), ("objectives", "Probation Evaluation Objective"),
                     ("training_needs", "Probation Training Need"), ("next_objectives", "Probation Next Objective")):
    if ((pe.get(table) or {}).get("fieldtype"), (pe.get(table) or {}).get("options")) != ("Table", child):
        fail.append("Probation Evaluation.%s must be a Table of %s" % (table, child))
decision = [o for o in ((pe.get("ed_decision") or {}).get("options") or "").split("\n") if o]
recommendation = [o for o in ((pe.get("hrm_recommendation") or {}).get("options") or "").split("\n") if o]
if decision != list(R.DECISIONS) or recommendation != list(R.DECISIONS):
    fail.append("the recommendation and the decision offer exactly %s" % (R.DECISIONS,))
glue = read("hrms_addon", "hrms_addon", "probation.py")
reviews_glue = read("hrms_addon", "hrms_addon", "reviews.py")
def functions(source, names):
    """The bodies of these top-level functions of a module."""
    return "".join(m.group(0) for m in re.finditer(r"^def (\w+)\(.*?(?=^def |^@|\Z)", source, re.M | re.S)
                   if m.group(1) in names)


METHODS = {"get", "set", "name", "docstatus", "append", "is_new", "get_doc_before_save", "db_set", "flags", "save"}
for source, spec, label in ((functions(glue, ("validate", "_facts", "on_submit", "on_cancel")), pe, "Probation Evaluation"),
                            (functions(reviews_glue, ("validate",)), orv, "Onboarding Review"),
                            (functions(glue, ("settings", "validate_settings", "save_default_settings")), settings,
                             "Onboarding Settings")):
    used = set(re.findall(r'doc\.get\("(\w+)"\)', source)) | set(re.findall(r"\bdoc\.(\w+)\b", source))
    for name in sorted(used - METHODS - set(spec)):
        fail.append("the glue reads %s.%s, which does not exist" % (label, name))
defaults = ast.literal_eval(re.search(r"^DEFAULTS = (\{.*?\})$", glue, re.M).group(1))
for field, value in defaults.items():
    if float((settings.get(field) or {}).get("default") or 0) != float(value):
        fail.append("Onboarding Settings.%s defaults to %s but probation.py falls back to %s"
                    % (field, (settings.get(field) or {}).get("default"), value))
if C.parse_alert_days((settings.get("contract_alert_days") or {}).get("default")) != C.DEFAULT_ALERT_DAYS:
    fail.append("Onboarding Settings' contract alerts default to contract_rules.DEFAULT_ALERT_DAYS")
for field in ("executive_director", "head_of_hr", "confirmed_employment_type"):
    if field not in settings:
        fail.append("Onboarding Settings.%s is missing" % field)
if not SET.get("issingle"):
    fail.append("Onboarding Settings is a single")
for name, methods, module in (("probation_evaluation", ("validate", "on_submit", "on_cancel"), "probation"),
                              ("onboarding_review", ("validate",), "reviews")):
    controller = open(os.path.join(APP, "doctype", name, name + ".py"), encoding="utf-8").read()
    for method in methods:
        if "    def %s(self):\n        %s.%s(self)" % (method, module, method) not in controller:
            fail.append("the %s controller must hand %s to %s.%s" % (name, method, module, method))
settings_controller = open(os.path.join(APP, "doctype", "onboarding_settings", "onboarding_settings.py"), encoding="utf-8").read()
if "probation.validate_settings(self)" not in settings_controller:
    fail.append("Onboarding Settings must be checked by probation.validate_settings")
employee = upstream_doctype("Employee")
if employee:
    custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
    employee_fields = {f["fieldname"] for f in employee["fields"]} | {f["fieldname"] for f in custom if f["dt"] == "Employee"} \
        | {"employment_type", "job_applicant"}
    for name in ("final_confirmation_date", "reports_to", "employment_type", "custom_probation_status",
                 "custom_probation_end_date", "salutation", "first_name", "employee_number", "department", "branch"):
        if name not in employee_fields:
            fail.append("Employee.%s, which the probation uses, does not exist" % name)
    status = next((f for f in custom if f["dt"] == "Employee" and f["fieldname"] == "custom_probation_status"), {})
    if [o for o in (status.get("options") or "").split("\n") if o] != list(R.PROBATION_STATUSES):
        fail.append("Employee.custom_probation_status must offer exactly probation_rules.PROBATION_STATUSES")
print("doctypes: statuses, signatures, the ratings, each step's role able to act; settings' defaults match the fallbacks")

# ── 6. The glue ───────────────────────────────────────────────────────
for needle, why in (
    ('frappe.get_all("Probation Factor", order_by="creation asc", pluck="name")', "a new evaluation lists the factors in order"),
    ("rules.objectives_from_kras(_key_result_areas(doc.designation))", "the objectives come from the Job Title's KRAs"),
    ('"parentfield": "custom_jd_key_result_areas"', "the Job Description tab's Key Result Areas"),
    ("rules.add_months(doc.end_of_probation, s.extension_months)", "an extension defaults to the settings' months"),
    ("doc.confirmation_date = doc.end_of_probation", "a confirmation defaults to the end of probation"),
    ("rules.passed(result[\"total\"], flt(doc.pass_mark))", "the pass mark decides Passed"),
    ("approval.step_errors(old_state, new_state, _facts(doc))", "each step is checked"),
    ("approval.compute_stamps(old_state, new_state, frappe.session.user, today(), current)", "each step is signed"),
    ("employee.custom_probation_status = rules.STATUS_AFTER[doc.ed_decision]", "the decision is the Employee's status"),
    ("employee.final_confirmation_date = doc.confirmation_date", "a confirmation is the Employee's Confirmation Date"),
    ("employee.custom_probation_end_date = doc.new_end_of_probation", "an extension moves the Employee's end of probation"),
    ('doc.db_set("next_evaluation", following.name)', "an extension makes the next evaluation"),
    ("follow the termination process", "a probation not confirmed goes to the termination process"),
    ('frappe.delete_doc("Probation Evaluation", following, ignore_permissions=True)', "a cancelled decision drops the next draft"),
    ("employee.flags.ignore_permissions = True\n    employee.save()", "the Employee is saved through its controller"),
):
    if needle not in glue:
        fail.append("probation.py: %s (%r not found)" % (why, needle))
for needle, why in (
    ("doc.due_date = add_days(doc.date_of_joining, cint(doc.review_day))", "a review is due its days after joining"),
    ('already has the {1}-day review', "one review of each kind per employee"),
    ("for day in approval.REVIEW_DAYS:", "the three reviews"),
    ('if frappe.db.exists("Onboarding Review", {"employee": employee, "review_day": str(day), "docstatus": ["!=", 2]}):',
     "a review already made is left alone"),
    ("date=review.due_date", "each is on the HR Officer's list for its date"),
    ("approval.step_errors(old_state, new_state, {", "each step is checked"),
):
    if needle not in reviews_glue:
        fail.append("reviews.py: %s (%r not found)" % (why, needle))
people = read("hrms_addon", "hrms_addon", "people.py")
for needle, why in (
    ('["name", "not in", ["Administrator", "Guest"]]', "tasks go to people, never Administrator"),
    ("return people_for(HR_OFFICER, branch, department) or people_for(\"HR Manager\", branch, department)",
     "the branch's HR Officers, else the HR Manager"),
    ('if frappe.db.exists("ToDo", {"reference_type": doctype, "reference_name": name, "allocated_to": user,',
     "nobody is given the same document twice"),
    ("enqueue_create_notification(users, {", "alerts go through Frappe's notifications (and email as each user set)"),
):
    if needle not in people:
        fail.append("people.py: %s (%r not found)" % (why, needle))
print("glue: factors, KRAs, scores, steps, the decision on the Employee, extension, termination; reviews once each")

# ── 7. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
for path in ("hrms_addon.hrms_addon.reviews.setup_workflow_on_migrate", "hrms_addon.hrms_addon.probation.setup_workflow_on_migrate"):
    if path not in (hooks.get("after_migrate") or []):
        fail.append("after_migrate must build %s" % path)
if "workflows.setup_on_migrate(approval, " not in glue or "workflows.setup_on_migrate(approval, " not in reviews_glue:
    fail.append("both workflows are built by workflows.py from their approval modules")
if "hrms_addon.hrms_addon.probation.after_install" not in (hooks.get("after_install") or []) \
        or not re.search(r"def after_install\(\):\n    save_default_settings\(\)", glue):
    fail.append("a fresh install saves the settings' defaults")
pick_lists = read("hrms_addon", "hrms_addon", "pick_lists.py")
if "seed_masters({**onboarding_rules.ONBOARDING_MASTERS, **probation_rules.PROBATION_MASTERS})" not in pick_lists \
        or "    seed_onboarding_masters()\n" not in pick_lists.split("def after_install():")[1]:
    fail.append("pick_lists seeds the Tool Providers and the probation factors, on install too")
patch = read("hrms_addon", "patches", "v1_0", "seed_onboarding_phase2.py")
if "hrms_addon.patches.v1_0.seed_onboarding_phase2" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1] \
        or "seed_onboarding_masters()" not in patch or "save_default_settings()" not in patch:
    fail.append("the seed_onboarding_phase2 patch seeds the masters and saves the settings")
print("wiring: both workflows built on migrate, settings and seeds on install and by patch")

# ── 8. Print formats ──────────────────────────────────────────────────
def print_format(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "print_format", folder, folder + ".json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


employee_all = employee_fields if employee else set()
for name, doc_type, spec, needles in (
    ("End of Probation Evaluation Form", "Probation Evaluation", pe, ("LPL/HR/32", "Section A: Ratable Factors", "/60", "/40",
                                                                      "Human Resources Manager's recommendation")),
    ("Confirmation in Service", "Probation Evaluation", pe, ("CONFIRMATION IN SERVICE", "remain the same", "Congratulations!",
                                                             'signatory("executive_director", "EXECUTIVE DIRECTOR")')),
    ("Staff Onboarding Form", "Onboarding Review", orv, ("LPL/HR/04", "Section A:", "Section B:",
                                                         "Human Resources Manager's remarks:")),
):
    pf = print_format(name)
    if (pf.get("doc_type"), pf.get("standard"), pf.get("print_format_type"), pf.get("module")) != (doc_type, "Yes", "Jinja", "HRMS Addon"):
        fail.append("%s must be a standard Jinja print format of %s" % (name, doc_type))
    html = pf.get("html") or ""
    for block in ("for", "if", "macro"):
        if len(re.findall(r"{%-?\s*" + block + r"\b", html)) != len(re.findall(r"{%-?\s*end" + block + r"\b", html)):
            fail.append("%s: unbalanced {%% %s %%} blocks" % (name, block))
    for needle in needles:
        if needle not in html:
            fail.append("%s must carry %r" % (name, needle))
    for field in set(re.findall(r"\bdoc\.([a-z_]+)", html)) - {"get_formatted"}:
        if field not in spec and field not in ("name", "creation", "modified"):
            fail.append("%s prints %s.%s, which does not exist" % (name, doc_type, field))
    for field in set(re.findall(r"\bemployee\.([a-z_]+)", html)):
        if employee_all and field not in employee_all and field != "name":
            fail.append("%s prints Employee.%s, which does not exist" % (name, field))
    if re.findall(r"{{-?\s*(?:doc|row|employee)\.[a-z_]+", html):
        fail.append("%s must print text through v() so it is escaped" % name)
    for setting in re.findall(r'get_single_value\("Onboarding Settings", ([a-z_]+)\)', html.replace('"', "")):
        if setting not in settings:
            fail.append("%s signs with Onboarding Settings.%s, which does not exist" % (name, setting))
# each table the probation form walks prints only its own columns
LOOPS = {"doc.factors": "Probation Evaluation Factor", "objectives": "Probation Evaluation Objective",
         "needs": "Probation Training Need", "next_objectives": "Probation Next Objective"}
html = print_format("End of Probation Evaluation Form").get("html") or ""
walked = re.findall(r"for row in (\S+?)(?: or \[\])? %}(.*?){%-? endfor", html, re.S)
if sorted(variable for variable, _ in walked) != sorted(LOOPS):
    fail.append("the probation form must walk the factors, objectives, training needs and next objectives: %s"
                % [variable for variable, _ in walked])
for variable, body in walked:
    columns = fields_of(doctype(LOOPS.get(variable, "")))
    for attribute in set(re.findall(r"\brow\.([a-z_]+)", body)):
        if attribute not in columns:
            fail.append("the probation form prints %s.%s, which does not exist" % (LOOPS.get(variable, variable), attribute))
print("print formats: LPL/HR/32, the confirmation letter and LPL/HR/04; every printed field exists, text escaped")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL PROBATION CHECKS PASSED")
