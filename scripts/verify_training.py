"""Checks for the training module, run without a bench.

training_rules.py, tna_approval.py and calendar_approval.py import nothing
from Frappe, so they are loaded directly and exercised: the evaluation form's
scoring (LPL/TRG/FRM05), the consolidated report, what a requisition, an
assessment and a schedule need, the calendar rows an assessment gives, the
reminder a month before and the ones a week, a day and the morning before a
session, and both workflows step by step.

It also cross-checks the DocTypes (the flowchart's blue boxes, with the
statuses and signatures the glue writes), the custom fields on Frappe HR's
Training Event and Training Feedback, that every field the glue reads
exists, the form scripts' calls, and the wiring: doc events, the scheduler,
the workflows built on migrate, the seed on install and by patch.

    python scripts/verify_training.py
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


def fields_of(spec):
    return {f["fieldname"]: f for f in spec.get("fields", [])}


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


R, T, C = load("training_rules"), load("tna_approval"), load("calendar_approval")
print("loaded training_rules.py, tna_approval.py and calendar_approval.py without Frappe")

# ── 1. The evaluation form (LPL/TRG/FRM05) ────────────────────────────
if len(R.EVALUATION_ITEMS) != 10 or R.EVALUATION_ITEMS[1] != "Course relevance" \
        or R.EVALUATION_ITEMS[-1] != "Class participation and interaction was encouraged":
    fail.append("Section A is the form's 10 items, in its order")
if R.TRAINING_MASTERS != {"Training Evaluation Item": ("item", R.EVALUATION_ITEMS)}:
    fail.append("the Training Evaluation Item list is seeded with exactly the form's items")
if R.RATINGS != ("Excellent", "Very Good", "Good", "Average", "Below Average") or R.RATING_VALUES["Excellent"] != 5 \
        or R.RATING_VALUES["Below Average"] != 1:
    fail.append("the form's five columns, worth 5 down to 1")
if len(R.QUESTIONS) != 6 or R.QUESTIONS[0][0] != "expectations" or R.QUESTIONS[-1][0] != "hr_recommendations":
    fail.append("Section B is the form's six questions, in its order")
for ratings, want in ((["Excellent"] * 10, 100.0), (["Excellent"] * 5 + ["Good"] * 5, 80.0), (["Below Average"], 20.0),
                      ([], None), (["", None, "Good"], 60.0)):
    if R.score(ratings) != want:
        fail.append("score(%s) is %s, expected %s" % (ratings, R.score(ratings), want))
for percent, want in ((100, "Excellent"), (90, "Excellent"), (89.9, "Very Good"), (75, "Very Good"), (74.9, "Good"),
                      (60, "Good"), (59.9, "Average"), (50, "Average"), (49.9, "Below Average"), (None, None)):
    if R.band(percent) != want:
        fail.append("band(%s) is %r, expected %r" % (percent, R.band(percent), want))
summary = R.consolidate([{"items": {"Course relevance": "Excellent", "Venue, refreshments": "Good"}, "score": 80.0},
                         {"items": {"Course relevance": "Good"}, "score": 60.0}, {"items": {}, "score": None}])
if summary["count"] != 3 or summary["score"] != 70.0 or summary["band"] != "Good" \
        or sorted(summary["items"]) != [("Course relevance", 80.0, 2), ("Venue, refreshments", 60.0, 1)]:
    fail.append("consolidate: each item over those who rated it, the overall over those scored: %s" % summary)
print("evaluation form: 10 items, 5 to 1, the bands, the consolidated report")

# ── 2. What each step needs ───────────────────────────────────────────
expect("a requisition", R.requisition_errors({"topic": "GMP", "skills": "Hygiene", "employees": 3}))
expect("a requisition with nothing", R.requisition_errors({}), "Give the training a topic", "Required Skills", "Target Employees")
NEED = {"topic": "GMP", "method": "Internal", "objectives": "Fewer defects"}
expect("an assessment", R.assessment_errors({"needs": [NEED], "objectives": "Fewer defects"}))
expect("an assessment with nothing", R.assessment_errors({}), "List the training needs", "training objectives")
expect("a need without a method", R.assessment_errors({"needs": [dict(NEED, method="")], "objectives": "x"}), "Propose the training method")
expect("a need without a topic", R.assessment_errors({"needs": [dict(NEED, topic=" ")], "objectives": "x"}), "must have a topic")
rows = R.calendar_rows([{"topic": "GMP", "section": "Production", "method": "External", "budget": 500, "month": "March",
                         "target_group": "Operators", "assessment": "HR-TNA-1", "need_row": "row1"}], 2027)
if rows != [{"course": "GMP", "section": "Production", "trainer": None, "trainer_type": "External", "budget": 500, "duration": None,
             "planned_month": "March", "planned_year": 2027, "target_group": "Operators", "assessment": "HR-TNA-1", "need_row": "row1"}]:
    fail.append("calendar_rows: one planner row per need, external where the method is: %s" % rows)
if R.next_month("2026-12-15") != (2027, "January") or R.next_month("2026-09-20") != (2026, "October"):
    fail.append("next_month rolls the year over")
due = R.due_for_schedule([{"planned_year": 2026, "planned_month": "October", "reminded_on": None, "scheduled": 0},
                          {"planned_year": 2026, "planned_month": "October", "reminded_on": "2026-09-01", "scheduled": 0},
                          {"planned_year": 2026, "planned_month": "October", "reminded_on": None, "scheduled": 1},
                          {"planned_year": 2026, "planned_month": "November", "reminded_on": None, "scheduled": 0}], "2026-09-20")
if len(due) != 1 or due[0]["planned_month"] != "October":
    fail.append("due_for_schedule: next month's rows not yet reminded of nor scheduled: %s" % due)
starts, ends = R.session_times("2027-02-10")
if (str(starts), str(ends)) != ("2027-02-10 07:00:00", "2027-02-10 09:00:00"):
    fail.append("a session runs 07:00 to 09:00 unless told otherwise: %s %s" % (starts, ends))
LINE = {"course": "GMP", "date": "2027-02-10", "venue": "Hall", "trainer": "PO"}
expect("a schedule", R.schedule_errors({"lines": [LINE], "month": "February", "year": 2027}))
expect("an empty schedule", R.schedule_errors({"lines": [], "month": "February", "year": 2027}), "Add the trainings")
expect("a line without a venue", R.schedule_errors({"lines": [dict(LINE, venue="")], "month": "February", "year": 2027}), "needs its venue")
expect("a line outside the month", R.schedule_errors({"lines": [dict(LINE, date="2027-03-01")], "month": "February", "year": 2027}),
       "outside February 2027")
for today, sent, want in (("2027-02-01", "", []), ("2027-02-03", "", [7]), ("2027-02-04", "7", []), ("2027-02-09", "7", [1]),
                          ("2027-02-10", "7, 1", [0]), ("2027-02-11", "7, 1, 0", []), ("2027-02-09", "", [1]), ("2027-02-10", "", [0])):
    if R.reminders_due("2027-02-10 07:00:00", today, sent) != want:
        fail.append("reminders_due on %s having sent %r is %s, expected %s" % (today, sent, R.reminders_due("2027-02-10 07:00:00", today, sent), want))
if R.record_reminders("", [1]) != "7, 1" or R.record_reminders("7", [1]) != "7, 1" or R.record_reminders("7, 1", [0]) != "7, 1, 0":
    fail.append("record_reminders marks every threshold at or beyond the one reached, so a missed one is not sent late")
if R.REMINDER_DAYS != (7, 1, 0) or R.CALENDAR_REMINDER_MONTHS != 1:
    fail.append("the reminders are a week, a day and the morning before; the HR Officer's a month before")
if len(R.event_name("x" * 200, "2027-02-10", "Kawempe")) > 140 or R.event_name("GMP", "2027-02-10") != "GMP - 2027-02-10":
    fail.append("an event's name is the course, the day and the branch, within 140 characters")
if R.attendance_days("2027-02-10", "2027-02-10") != 1 or R.attendance_days("2027-02-10", "2027-02-14") != 3:
    fail.append("the attendance sheet has one to three day columns")
print("steps: requisition, assessment, calendar rows, the month-before reminder, schedule, session reminders")

# ── 3. The workflows ──────────────────────────────────────────────────
for module, order, label in ((T, [T.DRAFT, T.PENDING_HRM, T.PENDING_GM, T.APPROVED, T.CANCELLED], "assessment"),
                             (C, [C.DRAFT, C.PENDING_GM, C.APPROVED, C.CANCELLED], "calendar")):
    states = list(dict.fromkeys(s["state"] for s in module.STATES))
    if states != order:
        fail.append("%s states %s, expected %s" % (label, states, order))
    for s in module.STATES:
        want = {module.APPROVED: "1", module.CANCELLED: "2"}.get(s["state"], "0")
        if s.get("doc_status", "0") != want:
            fail.append("%s %s must have doc_status %s" % (label, s["state"], want))
    if module.NEW_ROLES != ("General Manager",):
        fail.append("the %s workflow makes sure the General Manager role exists" % label)
got = sorted((t["state"], t["action"], t["next_state"], t["allowed"]) for t in T.TRANSITIONS)
want = sorted([(T.DRAFT, T.SUBMIT, T.PENDING_HRM, r) for r in T.PREPARERS]
              + [(T.PENDING_HRM, T.APPROVE, T.PENDING_GM, T.HRM), (T.PENDING_HRM, T.RETURN, T.DRAFT, T.HRM),
                 (T.PENDING_GM, T.APPROVE, T.APPROVED, T.GM), (T.PENDING_GM, T.RETURN, T.DRAFT, T.GM),
                 (T.APPROVED, T.CANCEL, T.CANCELLED, T.HRM)])
if got != want:
    fail.append("the assessment goes HR Manager then General Manager, each able to return it: %s" % got)
got = sorted((t["state"], t["action"], t["next_state"], t["allowed"]) for t in C.TRANSITIONS)
want = sorted([(C.DRAFT, C.SUBMIT, C.PENDING_GM, r) for r in C.PREPARERS]
              + [(C.PENDING_GM, C.APPROVE, C.APPROVED, C.GM), (C.PENDING_GM, C.RETURN, C.DRAFT, C.GM),
                 (C.APPROVED, C.CANCEL, C.CANCELLED, C.HRM)])
if got != want:
    fail.append("the calendar is approved by the General Manager, who can return it: %s" % got)
expect("to the HR Manager", T.step_errors(T.DRAFT, T.PENDING_HRM, {"assessment_errors": []}))
expect("with its problems", T.step_errors(T.DRAFT, T.PENDING_HRM, {"assessment_errors": ["List the training needs"]}), "List the training needs")
expect("a return without remarks", T.step_errors(T.PENDING_GM, T.DRAFT, {}), "Return Remarks")
expect("a return with remarks", T.step_errors(T.PENDING_HRM, T.DRAFT, {"return_remarks": "Add the budget"}))
expect("an empty calendar for approval", C.step_errors(C.DRAFT, C.PENDING_GM, {"entries": 0}), "Add the trainings")
expect("a calendar for approval", C.step_errors(C.DRAFT, C.PENDING_GM, {"entries": 3}))
stamps = T.compute_stamps(T.PENDING_HRM, T.PENDING_GM, "hrm@x", "2026-11-10", {})
if (stamps["hrm_by"], stamps["hrm_on"], stamps["gm_by"]) != ("hrm@x", "2026-11-10", None):
    fail.append("passing the HR Manager's step signs it, and only it")
if any(T.compute_stamps(T.PENDING_GM, T.DRAFT, "gm@x", "2026-11-10", {"hrm_by": "hrm@x"}).values()):
    fail.append("a return clears every signature: the approval starts again")
if T.compute_stamps(T.PENDING_HRM, T.PENDING_HRM, "typed@x", "2026-11-10", {"hrm_by": "old"})["hrm_by"] != "old":
    fail.append("a save that is not a step keeps the signatures as they were")
print("workflows: the assessment's two approvers and the calendar's one, returns, signatures")

# ── 4. The DocTypes ───────────────────────────────────────────────────
OURS = ("Training Needs Form", "Training Requisition", "Training Requisition Employee", "Training Needs Assessment",
        "TNA Requisition", "Training Need", "Training Calendar", "Training Calendar Entry", "Training Calendar Signatory",
        "Monthly Training Schedule", "Training Schedule Line", "Training Evaluation Item", "Training Evaluation Rating",
        "Meeting Record", "Meeting Participant")
specs = {name: doctype(name) for name in OURS}
for name, spec in specs.items():
    if not spec:
        fail.append("DocType %s is missing" % name)
for name, module in (("Training Needs Assessment", T), ("Training Calendar", C)):
    f = fields_of(specs[name])
    statuses = [o for o in (f.get("status", {}).get("options") or "").split("\n") if o]
    if statuses != list(dict.fromkeys(s["status"] for s in module.STATES)):
        fail.append("%s.status must offer exactly the workflow's statuses: %s" % (name, statuses))
    for field in module.ALL_STAMP_FIELDS:
        if not (f.get(field) or {}).get("read_only"):
            fail.append("%s.%s is a signature: it must exist, read-only" % (name, field))
    if not (f.get("workflow_state") or {}).get("hidden") or not specs[name].get("is_submittable"):
        fail.append("%s needs its hidden workflow_state and to be submittable" % name)
    perms = {p["role"]: p for p in specs[name].get("permissions", [])}
    for t in module.TRANSITIONS:
        need = "submit" if t["next_state"] == module.APPROVED else "cancel" if t["action"] == "Cancel" else "write"
        if not (perms.get(t["allowed"]) or {}).get(need):
            fail.append("%s: %s moves it to %s and needs %s" % (name, t["allowed"], t["next_state"], need))
req = fields_of(specs["Training Requisition"])
for field, kind in (("training_topic", "Data"), ("required_skills", "Small Text"), ("target_employees", "Table"),
                    ("department", "Link"), ("branch", "Link"), ("hr_officer", "Link"), ("assessment", "Link"),
                    ("training_event", "Link")):
    if (req.get(field) or {}).get("fieldtype") != kind:
        fail.append("Training Requisition.%s must be %s (test case 1: topic, skills, target employees)" % (field, kind))
if [o for o in (req["status"]["options"] or "").split("\n") if o] != list(R.REQUISITION_STATUSES):
    fail.append("Training Requisition.status must offer exactly training_rules.REQUISITION_STATUSES")
perms = {p["role"]: p for p in specs["Training Requisition"]["permissions"]}
if not all((perms.get("Head of Department") or {}).get(k) for k in ("create", "submit")):
    fail.append("the Head of Department raises and submits a Training Requisition")
tna = fields_of(specs["Training Needs Assessment"])
for field in ("objectives", "methods", "needs", "requisitions", "return_remarks", "calendar"):
    if field not in tna:
        fail.append("Training Needs Assessment.%s is missing (test cases 2 to 4)" % field)
need = fields_of(specs["Training Need"])
if [o for o in (need["method"]["options"] or "").split("\n") if o] != list(R.METHODS):
    fail.append("Training Need.method must offer exactly training_rules.METHODS")
if [o for o in (need["month"]["options"] or "").split("\n") if o] != list(R.MONTHS):
    fail.append("Training Need.month must offer the twelve months")
entry = fields_of(specs["Training Calendar Entry"])
for field in ("course", "trainer", "budget", "duration", "planned_month", "planned_year", "target_group", "section",
              "assessment", "need_row", "scheduled", "reminded_on"):
    if field not in entry:
        fail.append("Training Calendar Entry.%s is missing (the planner's columns, and the reminder)" % field)
for field in ("scheduled", "reminded_on"):
    if not entry[field].get("allow_on_submit"):
        fail.append("Training Calendar Entry.%s is set on an approved calendar: allow_on_submit" % field)
cal = fields_of(specs["Training Calendar"])
for field in ("board_approved_on", "signatories", "total_budget", "comments"):
    if field not in cal:
        fail.append("Training Calendar.%s is missing (the planner's approval block)" % field)
line = fields_of(specs["Training Schedule Line"])
for field in ("course", "training_date", "start_time", "end_time", "venue", "trainer", "trainer_email", "training_event",
              "calendar_entry", "department"):
    if field not in line:
        fail.append("Training Schedule Line.%s is missing (test case 6: date, time, venue, trainer)" % field)
form = fields_of(specs["Training Needs Form"])
for field in ("responsibilities", "skill_areas", "industry_trends", "collaboration_areas", "training_feedback", "comments",
              "years_of_experience", "year", "requisition"):
    if field not in form:
        fail.append("Training Needs Form.%s is missing (LPL/TRG/FRM06's questions)" % field)
rating = fields_of(specs["Training Evaluation Rating"])
if [o for o in (rating["rating"]["options"] or "").split("\n") if o] != list(R.RATINGS):
    fail.append("Training Evaluation Rating.rating must offer exactly the form's five columns")
meeting = fields_of(specs["Meeting Record"])
for field in ("topic", "department", "meeting_date", "start_time", "end_time", "participants"):
    if field not in meeting:
        fail.append("Meeting Record.%s is missing (LPL/HR/33)" % field)
# Frappe HR's Training Event and Training Feedback, extended
custom = json.loads(read("hrms_addon", "fixtures", "custom_field.json"))
te_custom = {f["fieldname"]: f for f in custom if f["dt"] == "Training Event"}
tf_custom = {f["fieldname"]: f for f in custom if f["dt"] == "Training Feedback"}
for field in ("custom_branch", "custom_department", "custom_schedule", "custom_calendar_entry", "custom_signed_attendance",
              "custom_reminders_sent", "custom_evaluations", "custom_evaluation_score", "custom_evaluation_band",
              "custom_trainer_2", "custom_trainer_3", "custom_shift", "custom_memo_approved_by", "custom_memo_approved_on"):
    if field not in te_custom:
        fail.append("Training Event.%s is missing" % field)
for field in ("custom_signed_attendance", "custom_reminders_sent", "custom_evaluations", "custom_evaluation_score", "custom_evaluation_band"):
    if not (te_custom.get(field) or {}).get("allow_on_submit"):
        fail.append("Training Event.%s is set after the training was held (submitted): allow_on_submit" % field)
if (tf_custom.get("custom_ratings") or {}).get("options") != "Training Evaluation Rating":
    fail.append("Training Feedback.custom_ratings must be a Table of Training Evaluation Rating")
for field, _question in R.QUESTIONS:
    if "custom_" + field not in tf_custom:
        fail.append("Training Feedback.custom_%s is missing (Section B)" % field)
for field in ("custom_score", "custom_band", "custom_signed_on"):
    if field not in tf_custom:
        fail.append("Training Feedback.%s is missing" % field)
setters = json.loads(read("hrms_addon", "fixtures", "property_setter.json"))
if not any(s["doc_type"] == "Training Feedback" and s.get("field_name") == "feedback" and s["property"] == "reqd" and s["value"] == "0"
           for s in setters):
    fail.append("Training Feedback.feedback is optional once the paper form's ratings and answers are keyed in")
print("doctypes: the flowchart's forms with their statuses, signatures and rights; Frappe HR's event and feedback extended")

# ── 5. The glue reads what exists ─────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "training.py")


def body_of(names):
    return "".join(m.group(0) for m in re.finditer(r"^def (\w+)\(.*?(?=^def |^@|\Z)", glue, re.M | re.S)
                   if any(m.group(1).startswith(n) for n in names))


def upstream_fields(name):
    spec = upstream_doctype(name)
    return ({f["fieldname"] for f in spec["fields"]} | {f["fieldname"] for f in custom if f["dt"] == name}) if spec else None


METHODS = {"get", "set", "name", "docstatus", "append", "is_new", "get_doc_before_save", "db_set", "flags", "save", "insert",
           "submit", "check_permission", "employees", "doctype", "update", "as_dict"}
READS = {
    "Training Needs Form": (("needs_form_",), set(fields_of(specs["Training Needs Form"]))),
    "Training Requisition": (("requisition_", "_mark_needs_forms"), set(fields_of(specs["Training Requisition"]))),
    "Training Needs Assessment": (("assessment_", "_assessment_facts", "_mark_requisitions"), set(fields_of(specs["Training Needs Assessment"]))),
    "Training Calendar": (("calendar_",), set(fields_of(specs["Training Calendar"]))),
    "Monthly Training Schedule": (("schedule_", "_book_event"), set(fields_of(specs["Monthly Training Schedule"]))),
    "Training Feedback": (("feedback_",), upstream_fields("Training Feedback")),
}
for name, (prefixes, known) in READS.items():
    if known is None:
        continue
    source = body_of(prefixes)
    used = set(re.findall(r'\bdoc\.get\("(\w+)"\)', source)) | set(re.findall(r"\bdoc\.(\w+)\b", source))
    for field in sorted(used - METHODS - known):
        fail.append("the glue reads %s.%s, which does not exist" % (name, field))
event_fields = upstream_fields("Training Event")
if event_fields:
    booked = re.search(r'"doctype": "Training Event",(.*?)\n    \}\)', glue, re.S)
    for field in sorted(set(re.findall(r'^\s+"(\w+)": ', booked.group(1), re.M)) - event_fields):
        fail.append("the session booked sets Training Event.%s, which does not exist" % field)
    spec = upstream_doctype("Training Event")
    for f in spec["fields"]:
        if f.get("reqd") and f["fieldname"] not in booked.group(1):
            fail.append("Training Event.%s is mandatory upstream and the session booked leaves it out" % f["fieldname"])
    attendance = next(f for f in upstream_doctype("Training Event Employee")["fields"] if f["fieldname"] == "attendance")
    if attendance.get("allow_on_submit"):
        fail.append("Training Event Employee.attendance is allow_on_submit upstream now: the event need not stay a draft until held")
feedback_py = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "training_feedback", "training_feedback.py")
if os.path.exists(feedback_py):
    src = open(feedback_py, encoding="utf-8").read()
    if "if training_event.docstatus != 1:" not in src or 'attendance == "Absent"' not in src:
        fail.append("Frappe HR's Training Feedback no longer needs a submitted event and a present employee: re-check create_evaluations")
for needle, why in (
    ("people.hr_officers(doc.get(\"branch\"), doc.get(\"department\"))", "the branch HR Officer is told of a requisition"),
    ('frappe.throw(_("Mark the attendance and submit the Training Event first', "evaluations only once the training was held"),
    ('if row.attendance != rules.PRESENT:', "one evaluation per participant present"),
    ('"employees": [{"employee": employee} for employee in participants]', "the session's participants are the requisition's people"),
    ('frappe.db.get_value("Employee", employee, "status") == "Active"', "an employee who left is not booked"),
    ("people.people_for(HOD_ROLE, schedule.get(\"branch\"), event.get(\"custom_department\"))", "the HOD is told and asked to confirm"),
    ("rules.due_for_schedule(", "the HR Officer reminded a month before"),
    ("rules.reminders_due(event.start_time, day, event.custom_reminders_sent)", "the session reminders"),
    ('frappe.delete_doc("Training Event", line.training_event, ignore_permissions=True)', "a cancelled schedule drops a session not held"),
    ("workflows.setup_on_migrate(tna_approval,", "the assessment workflow is built"),
    ("workflows.setup_on_migrate(calendar_approval,", "and the calendar's"),
):
    if needle not in glue:
        fail.append("training.py: %s (%r not found)" % (why, needle))
for name in ("get_needs_forms", "get_requisitions", "get_approved_needs", "get_calendar_trainings"):
    if not re.search(r"@frappe\.whitelist\(\)\ndef %s\(" % name, glue):
        fail.append("%s must be whitelisted for the form buttons" % name)
if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef create_evaluations\(', glue):
    fail.append("create_evaluations changes something: a whitelisted POST method")
# the form scripts call what is there
for js_path in glob.glob(os.path.join(APP, "doctype", "*", "*.js")) + glob.glob(os.path.join(REPO, "hrms_addon", "public", "js", "training_*.js")):
    js = open(js_path, encoding="utf-8").read()
    for method in re.findall(r'xcall\(\s*"hrms_addon\.hrms_addon\.training\.(\w+)"', js):
        if not re.search(r"^def %s\(" % method, glue, re.M):
            fail.append("%s calls training.%s, which is not there" % (os.path.basename(js_path), method))
print("glue: every field read exists, the session booked complete, the buttons' methods whitelisted")

# ── 6. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read("hrms_addon", "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
events = hooks.get("doc_events") or {}
for doctype_name, event, function in (("Training Event", "on_submit", "event_on_submit"), ("Training Event", "on_cancel", "event_on_cancel"),
                                      ("Training Feedback", "validate", "feedback_validate"),
                                      ("Training Feedback", "on_submit", "feedback_on_submit"),
                                      ("Training Feedback", "on_cancel", "feedback_on_cancel")):
    if (events.get(doctype_name) or {}).get(event) != "hrms_addon.hrms_addon.training.%s" % function:
        fail.append("doc_events %s %s must be training.%s" % (doctype_name, event, function))
if "hrms_addon.hrms_addon.training.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the scheduler runs training.daily every day (the month-before and session reminders)")
if "hrms_addon.hrms_addon.training.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("after_migrate must build both training workflows")
if "hrms_addon.hrms_addon.pick_lists.seed_training_masters" not in (hooks.get("after_install") or []):
    fail.append("a fresh install seeds the evaluation form's items")
if "hrms_addon.hrms_addon.training.consolidated" not in ((hooks.get("jinja") or {}).get("methods") or []):
    fail.append("the consolidated evaluation is a jinja method, for the summary print to come")
for doctype_name, path in (("Training Event", "public/js/training_event.js"), ("Training Feedback", "public/js/training_feedback.js")):
    if (hooks.get("doctype_js") or {}).get(doctype_name) != path or not os.path.exists(os.path.join(REPO, "hrms_addon", path)):
        fail.append("doctype_js %s must load %s" % (doctype_name, path))
if "seed_masters(training_rules.TRAINING_MASTERS)" not in read("hrms_addon", "hrms_addon", "pick_lists.py"):
    fail.append("pick_lists.seed_training_masters seeds training_rules.TRAINING_MASTERS")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
if "hrms_addon.patches.v1_0.seed_training" not in patches or "seed_training_masters()" not in read("hrms_addon", "patches", "v1_0", "seed_training.py"):
    fail.append("the seed_training patch seeds existing sites")
for name, methods in (("training_requisition", ("validate", "on_submit", "on_cancel")),
                      ("training_needs_assessment", ("validate", "on_submit", "on_cancel")),
                      ("training_calendar", ("validate", "on_submit", "on_cancel")),
                      ("monthly_training_schedule", ("validate", "on_submit", "on_cancel")),
                      ("training_needs_form", ("validate", "on_submit", "on_cancel"))):
    controller = open(os.path.join(APP, "doctype", name, name + ".py"), encoding="utf-8").read()
    prefix = {"training_requisition": "requisition", "training_needs_assessment": "assessment", "training_calendar": "calendar",
              "monthly_training_schedule": "schedule", "training_needs_form": "needs_form"}[name]
    for method in methods:
        if "    def %s(self):\n        training.%s_%s(self)" % (method, prefix, method) not in controller:
            fail.append("the %s controller must hand %s to training.%s_%s" % (name, method, prefix, method))
print("wiring: doc events, the daily job, the workflows on migrate, the seed on install and by patch, the form scripts")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL TRAINING CHECKS PASSED")
