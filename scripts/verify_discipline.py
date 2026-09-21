"""Verify employee relations and welfare, without a bench:

    python scripts/verify_discipline.py

Luuka's revised flow charts 5.3 (Disciplinary Grievances), 5.4
(Non-Disciplinary Grievances) and Safety, and the paper they run on:
LPL/HR/30 the warning letter and LPL/HR/03 the hearing registration form.

  1  the ladder: the rungs, what escalates, what is spent
  2  the case: who may be investigated, heard and sanctioned, and by whom
  3  the concern and the incident
  4  the DocTypes carry the paper; the concern is on their own Grievance
  5  the glue reads and writes fields that exist
  6  the signatures: the chain walked end to end, every desk stamped
  7  wiring: the doc events, the workflow on migrate, the job, the seed,
     the way in

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
    folder = name.lower().replace(" ", "_").replace("'", "")
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


CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
D, G, W = load("discipline_rules"), load("grievance_rules"), load("discipline_approval")
hooks = hooks_dict()
print("loaded discipline_rules.py, grievance_rules.py and discipline_approval.py without Frappe")

# ── 1. The ladder ─────────────────────────────────────────────────────
if D.LADDER != ("Verbal Warning", "First Warning Letter", "Second Warning Letter", "Suspension",
                "Dismissal"):
    fail.append("the chart climbs verbal, two written, suspension, dismissal: %s" % (D.LADDER,))
if D.SEVERITIES != ("Minor", "Serious", "Gross"):
    fail.append("a misconduct is minor, serious or gross: %s" % (D.SEVERITIES,))
if D.next_rung(D.VERBAL) != D.FIRST_WARNING or D.next_rung(D.SUSPENSION) != D.DISMISSAL:
    fail.append("one rung up at a time")
if D.next_rung(D.DISMISSAL) != D.DISMISSAL:
    fail.append("there is nothing above dismissal")
if D.next_rung(None) != D.VERBAL:
    fail.append("a case with nothing behind it starts at the bottom")

if D.sanction_spent("2026-01-15", D.VERBAL, "2026-06-15"):
    fail.append("a verbal warning stands for six months")
if not D.sanction_spent("2026-01-15", D.VERBAL, "2026-08-15"):
    fail.append("and is spent after them")
if not D.sanction_spent("2026-01-15", D.DISMISSAL, "2026-02-01"):
    fail.append("a dismissal has no life to run: the employee is gone")

if D.escalate([], D.MINOR, "2026-06-01") != D.VERBAL:
    fail.append("nothing standing means the bottom of the ladder")
if D.escalate([], D.GROSS, "2026-06-01") != D.DISMISSAL:
    fail.append("gross misconduct may be dismissed on the first offence")
live = [{"action": D.VERBAL, "issued_on": "2026-05-01"}]
if D.escalate(live, D.MINOR, "2026-06-01") != D.FIRST_WARNING:
    fail.append("a fresh case inside a live verbal warning starts one rung up")
if D.escalate(live, D.MINOR, "2027-06-01") != D.VERBAL:
    fail.append("once the warning is spent the ladder starts again")
two = [{"action": D.VERBAL, "issued_on": "2026-05-01"},
       {"action": D.FIRST_WARNING, "issued_on": "2026-05-20"}]
if D.escalate(two, D.SERIOUS, "2026-06-01") != D.SECOND_WARNING:
    fail.append("it is the HIGHEST live sanction that is climbed from: %s"
                % D.escalate(two, D.SERIOUS, "2026-06-01"))
print("the ladder: the rungs, what escalates it, what is spent")

# ── 2. The case ───────────────────────────────────────────────────────
good = {"employee": "E1", "misconduct_type": "Late Coming", "incident_date": "2026-06-01",
        "allegation": "Reported at 09:40 without notice.", "reported_by": "sup@luuka",
        "severity": "Minor", "today": "2026-06-02"}
expect("a case that stands", D.case_errors(good))
expect("no misconduct", D.case_errors(dict(good, misconduct_type=None)), "Misconduct Type")
expect("no allegation", D.case_errors(dict(good, allegation="")), "what the employee is said to have")
expect("nobody reported it", D.case_errors(dict(good, reported_by=None)), "who reported it")
expect("an incident in the future", D.case_errors(dict(good, incident_date="2026-12-01")),
       "cannot be in the future")

expect("an investigation that stands",
       D.investigation_errors({"investigating_officer": "io@luuka",
                               "investigation_report": "Spoke to the line.",
                               "recommendation": D.CASE_TO_ANSWER}))
expect("no officer appointed",
       D.investigation_errors({"investigation_report": "x", "recommendation": D.NO_CASE}),
       "Appoint an investigating officer")
expect("no report", D.investigation_errors({"investigating_officer": "io@luuka",
                                            "recommendation": D.NO_CASE}), "investigation report")
expect("no recommendation", D.investigation_errors({"investigating_officer": "io@luuka",
                                                    "investigation_report": "x"}), "recommends")

hearing = {"hearing_on": "2026-06-10 10:00:00", "notified_on": "2026-06-08 09:00:00",
           "panel": [{"member": "gm@luuka"}, {"member": "hrm@luuka"}],
           "investigating_officer": "io@luuka"}
expect("a hearing called in time, before a panel", D.hearing_errors(hearing))
expect("a hearing called too soon",
       D.hearing_errors(dict(hearing, notified_on="2026-06-10 08:00:00")), "at least 48 hours")
expect("a hearing with no panel", D.hearing_errors(dict(hearing, panel=[])), "before a panel")
expect("the investigator sitting in judgement",
       D.hearing_errors(dict(hearing, panel=[{"member": "io@luuka"}])),
       "does not decide the case")

decision = {"outcome": D.SANCTIONED, "hearing_minutes": "Heard.", "employee_response": "Admitted.",
            "action_type": D.FIRST_WARNING}
expect("a decision that stands", D.decision_errors(decision))
expect("no minutes", D.decision_errors(dict(decision, hearing_minutes="")), "Record the hearing")
expect("the employee unheard", D.decision_errors(dict(decision, employee_response="")),
       "employee's own response")
expect("sanctioned with no sanction", D.decision_errors(dict(decision, action_type=None)),
       "which sanction")
expect("a suspension with no days",
       D.decision_errors(dict(decision, action_type=D.SUSPENSION)), "number of days")

appeal = {"appeals_authority": "ed@luuka", "appeal_grounds": "New evidence.",
          "investigating_officer": "io@luuka", "decided_by": "hrm@luuka",
          "panel": [{"member": "gm@luuka"}]}
expect("an appeal heard by someone new", D.appeal_errors(appeal))
expect("an appeal heard by the investigator",
       D.appeal_errors(dict(appeal, appeals_authority="io@luuka")), "has not already acted")
expect("an appeal heard by the panel",
       D.appeal_errors(dict(appeal, appeals_authority="gm@luuka")), "has not already acted")
expect("an appeal with no grounds", D.appeal_errors(dict(appeal, appeal_grounds="")), "grounds")

if D.appeal_window_closed("2026-06-10", "2026-06-20"):
    fail.append("fourteen days to appeal means fourteen days")
if not D.appeal_window_closed("2026-06-10", "2026-06-30"):
    fail.append("after them the case closes itself")
dates = D.suspension_dates("2026-06-10", 3)
if dates["to"] != datetime.date(2026, 6, 12) or dates["report_back"] != datetime.date(2026, 6, 13):
    fail.append("three days from the 10th ends on the 12th and reports back on the 13th: %s" % dates)
if not D.ends_in_termination(D.DISMISSED, None) or not D.ends_in_termination(None, D.DISMISSAL):
    fail.append("both ways a case reaches the involuntary exit must be caught")
if D.ends_in_termination(D.PARDONED, D.VERBAL):
    fail.append("a pardon is not a termination")
print("the case: opened, investigated, heard before a fresh panel, decided, appealed")

# ── 3. The concern and the incident ───────────────────────────────────
if G.DEFAULT_TIMELINE_DAYS != 14:
    fail.append("a concern has a fortnight unless its type says otherwise")
if G.due_on("2026-06-01", 14) != datetime.date(2026, 6, 15):
    fail.append("the timeline runs from the day it was raised")
if not G.overdue("2026-06-01", "2026-06-02"):
    fail.append("a concern past its date is overdue")
if G.overdue("2026-06-01", "2026-06-02", G.RESOLVED):
    fail.append("a resolved concern is not overdue")
if G.escalate_to("2026-06-10", "2026-06-01") != "Handler":
    fail.append("while there is time it stays with the handler")
if G.escalate_to("2026-06-10", "2026-06-10") != "Department Head":
    fail.append("on the day it goes up to the department head")
if G.escalate_to("2026-06-10", "2026-06-20") != "HR":
    fail.append("past it, to HR")

concern = {"employee": "E1", "grievance_type": "Welfare", "description": "The locker room floods.",
           "assigned_hod": "hod@luuka"}
expect("a concern that stands", G.concern_errors(concern))
expect("no HOD assigned", G.concern_errors(dict(concern, assigned_hod=None)),
       "assign a suitable Head of Department")
expect("closed with nothing written",
       G.concern_errors(dict(concern, status=G.RESOLVED)), "how the concern was resolved")
expect("an appeal heard by the handler",
       G.concern_errors(dict(concern, appeal_filed=1, appeals_authority="hod@luuka",
                             handler="hod@luuka")), "has not already handled")

incident = {"employee": "E1", "incident_on": "2026-06-01 14:00:00", "nature": "Cut on the extruder.",
            "manageable": 1}
expect("an incident that stands", G.incident_errors(incident))
expect("no account of it", G.incident_errors(dict(incident, nature="")), "what happened")
expect("taken to hospital, unnamed", G.incident_errors(dict(incident, manageable=0)), "which one")
expect("a day off with no dates", G.incident_errors(dict(incident, day_off_required=1)),
       "when the sick leave starts", "how many days")
if G.incident_status(1, 1, "HR-LAP-1", 0, None) != G.ON_SICK_LEAVE:
    fail.append("an incident with sick leave running says so")
if G.incident_status(1, 0, None, 0, None) != G.BACK:
    fail.append("one needing no day off ends with the employee at work")
if G.incident_status(1, 1, "x", 1, "HR-EMP-SEP-1") != G.SEPARATED:
    fail.append("one where the sickness persisted ends in separation")
if not [row for row in G.MISCONDUCT if row[1] == "Gross"]:
    fail.append("the seeded misconduct must include the gross kinds")
if not [row for row in G.ACTION_TYPES if row[1] == D.DISMISSAL]:
    fail.append("and the ladder must reach dismissal")
print("the concern's timeline and the incident's course")

# ── 4. The paper ──────────────────────────────────────────────────────
for name, wanted in (
    ("Disciplinary Case", ("employee", "misconduct_type", "severity", "incident_date", "allegation",
                           "reported_by", "live_sanctions", "starts_at", "previous_case",
                           "investigating_officer", "investigation_report", "recommendation",
                           "charge_issued_on", "hearing_on", "hearing_notified_on",
                           "hearing_notice_hours", "panel", "hearing_minutes", "employee_response",
                           "outcome", "action_type", "rung", "sanction_valid_until",
                           "suspension_days", "suspension_from", "suspension_to", "report_back_on",
                           "employee_signed", "signed_letter", "appeal_filed", "appeals_authority",
                           "separation", "status")),
    ("Disciplinary Panel Member", ("member", "employee", "job_title", "panel_role", "attended")),
    ("Misconduct Type", ("misconduct_name", "severity", "default_action")),
    ("Disciplinary Action Type", ("action_name", "rung", "validity_months", "suspension_days")),
    ("Safety Incident", ("employee", "incident_on", "nature", "ehs_officer", "ehs_report",
                         "manageable", "hospital", "doctor_report", "day_off_required",
                         "sick_leave", "sick_from", "sick_days", "sickness_persists", "separation",
                         "compensation_required", "compensation_amount", "status")),
):
    fields = fields_of(doctype(name))
    if not fields:
        fail.append("%s is not there" % name)
        continue
    for fieldname in wanted:
        if fieldname not in fields:
            fail.append("%s has no %s, which the chart asks for" % (name, fieldname))
case = fields_of(doctype("Disciplinary Case"))
for fieldname in ("live_sanctions", "starts_at", "hearing_notice_hours", "sanction_valid_until",
                  "suspension_from", "suspension_to", "report_back_on", "status", "separation"):
    if not (case.get(fieldname) or {}).get("read_only"):
        fail.append("Disciplinary Case.%s is worked out, not typed" % fieldname)
if (case.get("panel") or {}).get("options") != "Disciplinary Panel Member":
    fail.append("the panel is a table of Disciplinary Panel Member (LPL/HR/03)")
states = {row["state"] for row in W.STATES}
if states - set((case.get("status") or {}).get("options", "").split("\n")):
    fail.append("Disciplinary Case.status must offer every state of the workflow")
if not doctype("Disciplinary Case").get("is_submittable"):
    fail.append("a decided case is a submitted document")
if "LPL-DISC-" not in (case.get("naming_series") or {}).get("options", ""):
    fail.append("the test script asks for LPL-DISC-YYYY-#### as the case's name")

# the concern is theirs, extended
if not upstream_doctype("Employee Grievance"):
    fail.append("Frappe HR's Employee Grievance is not where it was: 5.4 is built on it")
if doctype("Employee Grievance"):
    fail.append("the concern must stay Frappe HR's own, extended, not copied here")
concern_fields = custom_fields("Employee Grievance")
for fieldname in ("custom_reported_to", "custom_assigned_hod", "custom_booked_on", "custom_due_on",
                  "custom_overdue", "custom_informal_notes", "custom_meeting_notes", "custom_remedy",
                  "custom_outcome_accepted", "custom_appeal_filed", "custom_appeals_authority"):
    if fieldname not in concern_fields:
        fail.append("Employee Grievance has no %s, which 5.4 asks for" % fieldname)
if "custom_timeline_days" not in custom_fields("Grievance Type"):
    fail.append("a kind of concern carries its own timeline")
print("the paper: the case and LPL/HR/03, the masters, the incident, the concern on their own form")

# ── 5. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "discipline.py")
known = set(fields_of(doctype("Disciplinary Case"))) | set(fields_of(doctype("Safety Incident")))
known |= set(all_fields("Employee Grievance"))
known |= {"doctype", "name", "docstatus", "employee", "company", "flags"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "append", "db_set", "get_doc_before_save", "check_permission",
                     "insert", "submit", "cancel", "save", "panel", "as_dict", "update",
                     "workflow_state"):
        continue
    if fieldname not in known:
        fail.append("discipline.py reads or writes %s, which is on none of its documents" % fieldname)
for needle, why in (
    ("rules.escalate(", "where a case starts comes from the rules"),
    ("rules.case_errors(", "and what a case must say"),
    ("rules.investigation_errors(", "and the investigation"),
    ("rules.hearing_errors(", "and the hearing"),
    ("rules.decision_errors(", "and the decision"),
    ("rules.appeal_errors(", "and the appeal"),
    ("rules.suspension_dates(", "and the dates a suspension runs"),
    ("rules.ends_in_termination(", "and whether the case ends in one"),
    ('"custom_exit_type": "Involuntary"', "a dismissal raises the involuntary exit (exits.py)"),
    ('"custom_reason": "Medical Grounds"', "and a persisting sickness a separation on medical grounds"),
    ("grievance_rules.incident_errors(", "the incident is judged by its own rules"),
    ("grievance_rules.concern_errors(", "and so is the concern"),
    ("Leave Application", "a day off becomes a real sick leave"),
):
    if needle not in glue:
        fail.append("discipline.py: %s (%r not found)" % (why, needle))
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef file_appeal\(', glue):
    fail.append("discipline.file_appeal changes something: a whitelisted POST method")
if "check_permission(" not in glue:
    fail.append("discipline.py: a whitelisted method must check the caller may act")
for name, prefix in (("disciplinary_case", "case"), ("safety_incident", "incident")):
    controller = read("hrms_addon", "hrms_addon", "doctype", name, name + ".py")
    for method in ("validate", "on_submit", "on_cancel"):
        if "    def %s(self):\n        discipline.%s_%s(self)" % (method, prefix, method) not in controller:
            fail.append("the %s controller must hand %s to discipline.%s_%s"
                        % (name, method, prefix, method))
print("glue: the rules followed, the exit raised, the sick leave real, the button whitelisted")

# ── 6. The signatures ─────────────────────────────────────────────────
walked, state, seen = [W.DRAFT], W.DRAFT, set()
while state not in seen:
    seen.add(state)
    forward = [t for t in W.TRANSITIONS if t["state"] == state
               and t["action"] in (W.INVESTIGATE, W.CHARGE, W.SCHEDULE, W.DECIDE)]
    if not forward:
        break
    state = forward[0]["next_state"]
    walked.append(state)
if walked != [W.DRAFT, W.INVESTIGATING, W.CHARGED, W.HEARING, W.DECIDED]:
    fail.append("a case is investigated, charged, heard, then decided: %s" % walked)
if not [t for t in W.TRANSITIONS if t["action"] == W.NO_CASE and t["next_state"] == W.CLOSED]:
    fail.append("\"Incident happened? No\" must end the case without a sanction")
if set(W.STAMPS) != set(W.PENDING_STATES) or set(W.ROLE_WAITING) != set(W.PENDING_STATES):
    fail.append("every desk a case passes is stamped and known: %s" % sorted(W.STAMPS))
for state in W.PENDING_STATES:
    if not [t for t in W.TRANSITIONS if t["state"] == state and t["action"] == W.RETURN]:
        fail.append("%s must be able to send the case back" % state)
expect("returned without saying why", W.step_errors(W.CHARGED, W.DRAFT, {}), "Return Remarks")
if any(W.compute_stamps(W.HEARING, W.DRAFT, "x", "2026-06-01", {"investigated_by": "a"}).values()):
    fail.append("a return clears every signature")
if W.next_states(W.HEARING, ("Investigating Officer",)):
    fail.append("the investigating officer does not decide the case")
if W.next_states(W.DRAFT, ("Employee",)):
    fail.append("nobody may open a case on a desk that is not theirs")
for role in ("Investigating Officer", "Disciplinary Panel", "EHS Officer"):
    if role not in W.NEW_ROLES:
        fail.append("%s is named on a document of ours: the workflow must create it" % role)
print("signatures: the chain walked end to end, the investigator kept off the panel")

# ── 7. Wiring ─────────────────────────────────────────────────────────
events = hooks.get("doc_events", {})
for method in ("validate", "on_submit", "on_cancel"):
    if not (events.get("Employee Grievance") or {}).get(method):
        fail.append("Employee Grievance has no %s hook" % method)
if "hrms_addon.hrms_addon.discipline.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the disciplinary workflow must be built after every migrate")
if "hrms_addon.hrms_addon.discipline.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the appeal window and the concern's timeline are watched daily")
if "hrms_addon.hrms_addon.discipline.seed_discipline_masters" not in (hooks.get("after_install") or []):
    fail.append("a fresh install seeds the ladder and the misconduct")
if "seed_discipline_masters()" not in read("hrms_addon", "patches", "v1_0", "seed_discipline.py"):
    fail.append("and so does the patch, on a site that has the app already")
if "hrms_addon.patches.v1_0.seed_discipline" not in read("hrms_addon", "patches.txt"):
    fail.append("the seed patch must be listed in patches.txt")
if "Employee Grievance" not in (hooks.get("doctype_js") or {}):
    fail.append("the concern's timeline needs its form script")
navigation = load("navigation_rules")
carded = {link[1]: page for page, cards in navigation.CARDS.items()
          for _card, links in cards for link in links}
sidebarred = {entry[1]: page for page, entries in navigation.SIDEBAR.items() for entry in entries}
for name in ("Disciplinary Case", "Safety Incident", "Misconduct Type", "Disciplinary Action Type"):
    if carded.get(name) != "Tenure":
        fail.append("%s belongs on the Tenure page with the rest of employee relations; it is on %r"
                    % (name, carded.get(name)))
    if sidebarred.get(name) != "Tenure":
        fail.append("%s's sidebar entry belongs on Tenure; it is on %r" % (name, sidebarred.get(name)))
if "Employee Grievance" in carded or "Employee Grievance" in sidebarred:
    fail.append("the concern is Frappe HR's own and already on their Grievance card: leave it alone")
print("wiring: the doc events, the workflow on migrate, the daily job, the seed, the way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL DISCIPLINE AND WELFARE CHECKS PASSED")
