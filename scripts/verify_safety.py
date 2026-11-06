"""Checks for the safety module (Luuka's review list of 5 Nov 2026, items 11 to
17): the hospitals, the incident's own approval by the plant's EHS Officer, its
incident and investigation reports, the doctor's reports and rest days, light
duty and the separation a doctor recommends, the treatment order and its
transport, and the compensation the insurer pays.

Runs without a bench: the rules modules are loaded on their own, and the
DocTypes, fixtures and hooks are read as files.

    python scripts/verify_safety.py
"""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    return json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fields_of(name):
    return {f["fieldname"]: f for f in doctype(name).get("fields", [])}


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


def upstream_fields(name):
    """The fields of Frappe's, ERPNext's or Frappe HR's own doctype."""
    folder = name.lower().replace(" ", "_")
    for app in ("frappe", "erpnext", "hrms"):
        hits = glob.glob(os.path.join(APPS_ROOT, app, app, "**", "doctype", folder, folder + ".json"), recursive=True)
        if hits:
            return {f["fieldname"] for f in json.load(io.open(hits[0], encoding="utf-8"))["fields"]}
    return set()


custom = json.load(io.open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))


def roles_with(spec, right):
    return {row["role"] for row in spec.get("permissions", []) if row.get(right)}


hooks = hooks_dict()

# ── 13. The hospitals ─────────────────────────────────────────────────
# "Under safety, there need be a drop down for list of hospitals they use, and open if there is need to add another"
hospital = doctype("Hospital")
hospital_fields = fields_of("Hospital")
if (hospital.get("autoname"), hospital.get("quick_entry"), hospital_fields.get("hospital_name", {}).get("unique")) \
        != ("field:hospital_name", 1, 1):
    fail.append("a hospital is named by itself, once, and added in a quick dialog")
if not {"HR User", "HR Manager", "EHS Officer"} <= roles_with(hospital, "create"):
    fail.append("HR and the EHS Officers add a hospital from the drop-down when the one needed is not there")
if "Employee" not in roles_with(hospital, "read"):
    fail.append("anyone who reads an incident reads the hospital it names")
if any(f.get("fieldtype") == "Link" and f.get("options") == "Branch" for f in hospital_fields.values()):
    fail.append("the hospitals are one list for every plant: a plant's users would see only their own")
if (fields_of("Safety Incident").get("hospital") or {}).get("options") != "Hospital":
    fail.append("the incident's hospital is picked from the list")
patch = read("hrms_addon", "patches", "v1_0", "hospitals_from_incidents.py")
if "hrms_addon.patches.v1_0.hospitals_from_incidents" not in read("hrms_addon", "patches.txt").split("[post_model_sync]")[1] \
        or 'frappe.get_all("Safety Incident", filters={"hospital": ["is", "set"]}' not in patch \
        or 'if name and not frappe.db.exists("Hospital", name):' not in patch \
        or 'frappe.db.set_value("Safety Incident", row.name, "hospital", name or None' not in patch:
    fail.append("the hospitals already typed become the list, each once, and the incident names its own exactly")
print("hospitals: one list, added to from the drop-down, the names already typed brought in")

# ── The incident: what it must say, where the employee stands ─────────
R = load("safety_rules")
A = load("safety_approval")


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


incident = {"employee": "E1", "incident_on": "2026-06-01 14:00:00", "nature": "Cut on the extruder.",
            "manageable": 1}
expect("an incident that stands", R.incident_errors(incident))
expect("no account of it", R.incident_errors(dict(incident, nature="")), "what happened")
expect("taken to hospital, unnamed", R.incident_errors(dict(incident, manageable=0)), "which one")
print("the incident: what it must say")

# ── 12 and 16. Approved by the plant's EHS Officer, both reports acknowledged ──
# "On safety, the EHS officers are 3 i.e one per plant. Need make their approval fixed."
# "Under safety, the incident report and investigation report differ. Need acknowledge these two reports"
FORWARD = (A.SEND, A.APPROVE, A.ACKNOWLEDGE, A.SUBMIT_INVESTIGATION, A.ACKNOWLEDGE_INVESTIGATION)
walked, state = [A.DRAFT], A.DRAFT
for action in FORWARD:
    nxt = [t["next_state"] for t in A.TRANSITIONS if t["state"] == state and t["action"] == action]
    if not nxt:
        break
    state = nxt[0]
    walked.append(state)
if walked != [A.DRAFT, A.PENDING_EHS, A.PENDING_HR, A.RECORDED, A.INVESTIGATED, A.CLOSED]:
    fail.append("reported, approved by the EHS Officer, acknowledged, investigated, acknowledged: %s" % walked)
docstatus = {row["state"]: str(row.get("doc_status", "0")) for row in A.STATES}
if [docstatus[s] for s in (A.DRAFT, A.PENDING_EHS, A.PENDING_HR, A.RECORDED, A.INVESTIGATED, A.CLOSED,
                           A.CANCELLED)] != ["0", "0", "0", "1", "1", "1", "2"]:
    fail.append("the incident is recorded (submitted) when HR acknowledge its report, and investigated after: %s"
                % docstatus)
for t in A.TRANSITIONS:
    pair = (docstatus[t["state"]], docstatus[t["next_state"]])
    if pair in (("1", "0"), ("0", "2")) or pair[0] == "2":
        fail.append("Frappe refuses the step %s -> %s (%s)" % (t["state"], t["next_state"], t["action"]))
if any(row["send_email"] for row in A.STATES):
    fail.append("no state sends Frappe's own email, which goes to every EHS Officer: the glue tells the plant's")
OFFICER_OR_HRM, HR_ROLES = {"EHS Officer", "HR Manager"}, {"HR User", "HR Manager"}
for action, wanted in ((A.APPROVE, OFFICER_OR_HRM), (A.SUBMIT_INVESTIGATION, OFFICER_OR_HRM),
                       (A.ACKNOWLEDGE, HR_ROLES), (A.ACKNOWLEDGE_INVESTIGATION, HR_ROLES),
                       (A.CANCEL, {"HR Manager"})):
    allowed = {t["allowed"] for t in A.TRANSITIONS if t["action"] == action}
    if allowed != wanted:
        fail.append("%s is for %s, not %s" % (action, sorted(wanted), sorted(allowed)))
for state in (A.PENDING_EHS, A.PENDING_HR):
    if not [t for t in A.TRANSITIONS if t["state"] == state and t["next_state"] == A.DRAFT]:
        fail.append("%s may send the incident back to its reporter" % state)
if not [t for t in A.TRANSITIONS if t["state"] == A.INVESTIGATED and t["next_state"] == A.RECORDED]:
    fail.append("HR may send the investigation back to the EHS Officer")
if not set(A.REPORTERS) >= {"Supervisor", "Head of Department", "HR User", "EHS Officer"}:
    fail.append("the supervisor who saw the accident reports it, as HR and the EHS Officer may")

facts = {"user": "ehs.kawempe@luuka", "ehs_officer": "ehs.kawempe@luuka", "branch": "Kawempe",
         "incident_report": "/private/files/report.pdf"}
expect("the plant's officer approves the report", A.step_errors(A.PENDING_EHS, A.PENDING_HR, facts))
expect("another plant's officer, though an EHS Officer too",
       A.step_errors(A.PENDING_EHS, A.PENDING_HR, dict(facts, user="ehs.matugga@luuka")),
       "Kawempe plant's EHS Officer")
expect("the HR Manager, standing in for the officer",
       A.step_errors(A.PENDING_EHS, A.PENDING_HR, dict(facts, user="hrm@luuka", is_hrm=1)))
expect("approved with no incident report", A.step_errors(A.PENDING_EHS, A.PENDING_HR,
                                                          dict(facts, incident_report=None)), "Attach the incident report")
expect("returned by another plant's officer, with a reason",
       A.step_errors(A.PENDING_EHS, A.DRAFT, dict(facts, user="ehs.matugga@luuka", return_remarks="Wrong day.")),
       "Kawempe plant's EHS Officer")
expect("returned with no reason", A.step_errors(A.PENDING_HR, A.DRAFT, dict(facts, user="hro@luuka")),
       "Return Remarks")
expect("sent from a plant with no EHS Officer", A.step_errors(A.DRAFT, A.PENDING_EHS, dict(facts, ehs_officer=None)),
       "No EHS Officer serves the Kawempe plant")
expect("an investigation with nothing in it", A.step_errors(A.RECORDED, A.INVESTIGATED, facts),
       "Attach the investigation report", "Root Cause", "findings")
expect("an investigation by someone else",
       A.step_errors(A.RECORDED, A.INVESTIGATED, dict(facts, user="hro@luuka", investigation_report="/x.pdf",
                                                      root_cause="Guard off.", findings="Guard refitted.")),
       "investigation report is submitted by ehs.kawempe@luuka")
expect("the investigation sent back with no reason", A.step_errors(A.INVESTIGATED, A.RECORDED, facts),
       "Investigation Remarks")
expect("a save that takes no step", A.step_errors(A.RECORDED, A.RECORDED, dict(facts, user="x")))

stamps = A.compute_stamps(A.PENDING_EHS, A.PENDING_HR, "ehs.kawempe@luuka", "2026-06-02", {})
if (stamps["incident_report_by"], stamps["incident_report_on"]) != ("ehs.kawempe@luuka", "2026-06-02"):
    fail.append("the officer's approval of the incident report is signed and dated: %s" % stamps)
saved = dict(stamps)
stamps = A.compute_stamps(A.PENDING_HR, A.RECORDED, "hro@luuka", "2026-06-03", saved)
if (stamps["incident_acknowledged_by"], stamps["incident_report_by"]) != ("hro@luuka", "ehs.kawempe@luuka"):
    fail.append("HR's acknowledgement of the incident report is signed beside the officer's: %s" % stamps)
saved = dict(stamps)
stamps = A.compute_stamps(A.RECORDED, A.INVESTIGATED, "ehs.kawempe@luuka", "2026-06-10", saved)
if stamps["investigated_by"] != "ehs.kawempe@luuka" or stamps["investigation_acknowledged_by"]:
    fail.append("the investigation report has its own signatures: %s" % stamps)
back = A.compute_stamps(A.INVESTIGATED, A.RECORDED, "hro@luuka", "2026-06-11", stamps)
if back["investigated_by"] or back["incident_acknowledged_by"] != "hro@luuka":
    fail.append("an investigation sent back loses its signature, and the incident report keeps its own: %s" % back)
closed = A.compute_stamps(A.INVESTIGATED, A.CLOSED, "hro@luuka", "2026-06-12", stamps)
if closed["investigation_acknowledged_by"] != "hro@luuka":
    fail.append("HR's acknowledgement of the investigation report is signed: %s" % closed)
returned = A.compute_stamps(A.PENDING_HR, A.DRAFT, "hro@luuka", "2026-06-03", saved)
if any(returned[field] for field in A.INCIDENT_STAMP_FIELDS):
    fail.append("an incident sent back to its reporter loses its signatures: %s" % returned)
if any(A.compute_stamps(None, A.DRAFT, "x", "2026-06-01", {"incident_report_by": "forged",
                                                          "investigated_by": "forged"}).values()):
    fail.append("a new incident, or one copied, starts unsigned")
if A.compute_stamps(A.RECORDED, A.RECORDED, "x", "2026-06-05", saved) != dict(saved, **{
        f: None for f in A.ALL_STAMP_FIELDS if f not in saved}):
    fail.append("a save that takes no step keeps the signatures as saved")
for old, new, wanted in ((A.DRAFT, A.PENDING_EHS, True), (A.PENDING_EHS, A.PENDING_HR, True),
                         (A.PENDING_HR, A.RECORDED, True), (A.RECORDED, A.INVESTIGATED, True),
                         (A.RECORDED, A.RECORDED, True), (A.PENDING_HR, A.PENDING_HR, False),
                         (A.INVESTIGATED, A.CLOSED, False), (A.CLOSED, A.CLOSED, False)):
    if A.officer_fixed(old, new) != wanted:
        fail.append("the plant's EHS Officer %s named again on %s -> %s" % ("is" if wanted else "is not", old, new))
print("12, 16: approved by the plant's own EHS Officer, each report signed and acknowledged")

# the paper
incident = doctype("Safety Incident")
fields = fields_of("Safety Incident")
for fieldname in A.ALL_STAMP_FIELDS:
    if not (fields.get(fieldname) or {}).get("read_only"):
        fail.append("Safety Incident.%s is signed by the step, not typed" % fieldname)
for fieldname in ("investigation_report", "root_cause", "findings", "investigation_remarks", "investigated_by",
                  "investigated_on", "investigation_acknowledged_by", "investigation_acknowledged_on",
                  "workflow_state", "approval_status", "status", "ehs_officer"):
    if not (fields.get(fieldname) or {}).get("allow_on_submit"):
        fail.append("Safety Incident.%s changes after the incident is recorded: allow it on submit" % fieldname)
if not (fields.get("ehs_officer") or {}).get("read_only"):
    fail.append("the EHS Officer is the plant's, filled in: nobody picks another")
options = set((fields.get(A.STATUS_FIELD) or {}).get("options", "").split("\n"))
if {row["status"] for row in A.STATES} - options:
    fail.append("%s must offer every state" % A.STATUS_FIELD)
if (fields.get("ehs_report") or {}).get("label") != "Incident Report" or "investigation_report" not in fields:
    fail.append("the incident report and the investigation report are two attachments")
for role in ("Supervisor", "Head of Department", "HR User", "EHS Officer"):
    if role not in roles_with(incident, "create"):
        fail.append("%s may report an accident" % role)
for role in ("HR User", "EHS Officer"):
    if role not in roles_with(incident, "submit"):
        fail.append("%s updates a recorded incident (Frappe's Update needs submit)" % role)
print("the paper: both reports, their signatures, what changes once recorded")

# the glue
glue = read("hrms_addon", "hrms_addon", "safety.py")
# each function's doc is the document it is handed: the treatment order's
# and the Cash Entry's functions read theirs, the rest the incident
ORDER_FUNCTIONS = ("order_validate", "order_on_update", "order_on_submit", "order_on_cancel", "_tell_order",
                   "make_transport_entry")
JOURNAL_FUNCTIONS = ("journal_on_submit", "journal_on_cancel")
journal_fields = upstream_fields("Journal Entry") | {f["fieldname"] for f in custom if f["dt"] == "Journal Entry"}
for node in ast.parse(glue).body:
    if not isinstance(node, ast.FunctionDef):
        continue
    source = ast.get_source_segment(glue, node)
    if node.name in ORDER_FUNCTIONS:
        name, known = "Medical Treatment Order", set(fields_of("Medical Treatment Order"))
    elif node.name in JOURNAL_FUNCTIONS:
        name, known = "Journal Entry", set(journal_fields)
    else:
        name, known = "Safety Incident", set(fields)
    known |= {"doctype", "name", "docstatus", "owner", "flags"}
    for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', source))
                            | set(re.findall(r"(?<![\w])doc\.(\w+)\b", source))):
        if fieldname in ("get", "set", "db_set", "get_doc_before_save", "check_permission", "name", "docstatus"):
            continue
        if fieldname not in known:
            fail.append("safety.py %s reads or writes %s, which the %s does not have" % (node.name, fieldname, name))
for needle, why in (
    ("if approval.officer_fixed(old_state, new_state):\n        doc.ehs_officer = ehs_officer(doc.get(\"branch\"))",
     "the plant's EHS Officer is named by the role, at every step they take"),
    ("people.people_for(approval.EHS, branch)", "from who holds the role for the plant"),
    ("approval.step_errors(old_state, new_state, _step_facts(doc))", "every step is checked"),
    ("current = {field: before.get(field) for field in approval.ALL_STAMP_FIELDS} if before else {}",
     "the signatures come from the saved incident, not the form"),
    ("rules.incident_errors(", "the incident is judged by its own rules"),
    ('"custom_reason": "Medical Grounds"', "a separation on medical grounds"),
    ('"doctype": "Leave Application"', "a day off becomes a real sick leave"),
    ('doc.db_set("status", rules.CANCELLED', "a cancelled incident says so (on_cancel runs after the write)"),
):
    if needle not in glue:
        fail.append("safety.py: %s (%r not found)" % (why, needle[:60]))
controller = read("hrms_addon", "hrms_addon", "doctype", "safety_incident", "safety_incident.py")
for method in ("validate", "on_update", "on_submit", "before_update_after_submit", "on_update_after_submit",
               "on_cancel"):
    if "    def %s(self):\n        safety.incident_%s(self)" % (method, method) not in controller:
        fail.append("the Safety Incident controller must hand %s to safety.incident_%s" % (method, method))
print("glue: the officer named by the role, the steps checked, the signatures from what is saved")

# wiring
if "hrms_addon.hrms_addon.safety.setup_workflows_on_migrate" not in (hooks.get("after_migrate") or []):
    fail.append("the incident's workflow is built after every migrate")
patches = read("hrms_addon", "patches.txt").split("[post_model_sync]")[1]
states_patch = read("hrms_addon", "patches", "v1_0", "safety_incident_states.py")
if "hrms_addon.patches.v1_0.safety_incident_states" not in patches \
        or 'STATES = ((0, "Draft"), (1, "Recorded"), (2, "Cancelled"))' not in states_patch \
        or '{"workflow_state": state, "approval_status": state}' not in states_patch:
    fail.append("the incidents already recorded stand at Recorded, their investigation to come")
navigation = load("navigation_rules")
carded = {link[1]: page for page, cards in navigation.CARDS.items() for _card, links in cards for link in links}
sidebarred = {entry[1]: page for page, entries in navigation.SIDEBAR.items() for entry in entries}
for name in ("Safety Incident", "Hospital"):
    if carded.get(name) != "Tenure" or sidebarred.get(name) != "Tenure":
        fail.append("%s belongs on the Tenure page with the rest of employee relations" % name)
print("wiring: the workflow on migrate, the incidents already recorded, the way in")

# ── 14 and 17. The doctor's reports, light duty, and the doctor's word ──
# "the doctor's report is more than one. Need a provision for multiple reports and rest days"
# "light work is sometimes recommended if sickness persists. Termination comes on doctor's recommendation"
if str(R.rest_to("2026-11-03", 3)) != "2026-11-05" or R.rest_to("2026-11-03", 0) is not None \
        or R.rest_to(None, 3) is not None:
    fail.append("a rest runs from its first day, both ends counted: %s" % R.rest_to("2026-11-03", 3))
first = {"name": "r1", "idx": 1, "report_date": "2026-11-02", "recommendation": R.REST, "rest_from": "2026-11-03",
         "rest_days": 3}
second = {"name": "r2", "idx": 2, "report_date": "2026-11-06", "recommendation": R.LIGHT_DUTY,
          "light_duties": "Sorting at the bench, no lifting."}
same_day = {"name": "r3", "idx": 3, "report_date": "2026-11-06", "recommendation": R.FIT}
if (R.latest_report([first, second]) or {}).get("name") != "r2" \
        or (R.latest_report([second, first]) or {}).get("name") != "r2" \
        or (R.latest_report([first, second, same_day]) or {}).get("name") != "r3":
    fail.append("the latest report is the last dated, and of two on one day the later row")
for rows, manageable, separation, wanted in (([first], 1, None, R.ON_SICK_LEAVE), ([first, second], 1, None,
                                             R.ON_LIGHT_DUTY), ([first, second, same_day], 1, None, R.BACK),
                                            ([dict(first, recommendation=R.UNFIT)], 1, None, R.UNFIT_FOR_WORK),
                                            ([], 0, None, R.RECORDED), ([], 1, None, R.BACK),
                                            ([dict(first, recommendation=R.UNFIT)], 1, "SEP-1", R.SEPARATED)):
    got = R.incident_status(1, rows, manageable, separation)
    if got != wanted:
        fail.append("the employee stands where the latest report puts them: %s, not %s" % (wanted, got))
if R.incident_status(0, [first], 1, None) != R.DRAFT or R.incident_status(2, [first], 1, None) != R.CANCELLED:
    fail.append("a draft or a cancelled incident says so, whatever its reports")
expect("two reports that stand", R.report_errors([first, second], "2026-11-02 14:00:00"))
expect("a report the doctor gave on no day", R.report_errors([dict(first, report_date=None)], "2026-11-02"),
       "say when the doctor gave it")
expect("a report dated before the accident", R.report_errors([dict(first, report_date="2026-11-01")],
                                                             "2026-11-02"), "dated before the accident")
expect("a report recommending nothing", R.report_errors([dict(first, recommendation="")], "2026-11-02"),
       "say what the doctor recommends")
expect("rest with no days", R.report_errors([dict(first, rest_days=0)], "2026-11-02"), "for how many days")
expect("rest from before the accident", R.report_errors([dict(first, rest_from="2026-10-30")], "2026-11-02"),
       "starts before the accident")
expect("light duty with the work unsaid", R.report_errors([dict(second, light_duties=" ")], "2026-11-02"),
       "what light work the doctor allows")
expect("two rests at once", R.report_errors([first, dict(first, name="r4", idx=4, report_date="2026-11-04",
                                                         rest_from="2026-11-05", rest_days=2)], "2026-11-02"),
       "one sick leave at a time")
expect("a rest after the last one ended", R.report_errors([first, dict(first, name="r4", idx=4,
                                                                       report_date="2026-11-06",
                                                                       rest_from="2026-11-06", rest_days=5)],
                                                          "2026-11-02"))
given = dict(first, leave_application="HR-LAP-2026-00001")
expect("a report that gave a sick leave, kept", R.fixed_row_errors([given], [dict(given)]))
expect("one that gave none, changed freely", R.fixed_row_errors([first], [dict(first, rest_days=9)]))
expect("one that gave a sick leave, removed", R.fixed_row_errors([given], []), "it stays on the incident")
expect("its days changed", R.fixed_row_errors([given], [dict(given, rest_days=5)]), "change the leave itself")
expect("its first day changed", R.fixed_row_errors([given], [dict(given, rest_from="2026-11-04")]),
       "change the leave itself")
expect("its leave unlinked", R.fixed_row_errors([given], [dict(given, leave_application=None)]),
       "change the leave itself")
if str(R.rest_ended([first], "2026-11-06")) != "2026-11-05" or R.rest_ended([first], "2026-11-07") \
        or R.rest_ended([first, second], "2026-11-06") or R.rest_ended([first], "2026-11-05"):
    fail.append("the doctor's next word is asked for the day after a rest ends, once, and not once they report")
unfit = dict(same_day, name="r5", idx=5, report_date="2026-11-20", recommendation=R.UNFIT)
expect("the HR Manager, on the doctor's word", R.separation_errors(1, [first, unfit], None, ["HR Manager"]))
expect("anyone else", R.separation_errors(1, [first, unfit], None, ["HR User"]), "Only the HR Manager")
expect("before the incident is recorded", R.separation_errors(0, [first, unfit], None, ["HR Manager"]),
       "Record the incident first")
expect("twice", R.separation_errors(1, [first, unfit], "HR-EMP-SEP-1", ["HR Manager"]), "already being separated")
expect("with no doctor's finding", R.separation_errors(1, [first, second], None, ["HR Manager"]),
       "only on the doctor's recommendation")
expect("on an older finding the doctor has since revised",
       R.separation_errors(1, [unfit, dict(second, report_date="2026-11-25")], None, ["HR Manager"]),
       "only on the doctor's recommendation")
long_rest = dict(first, name="r6", idx=6, report_date="2026-11-10", rest_from="2026-11-10", rest_days=30)
if str(R.last_day_of_work([first, unfit], "2026-11-21")) != "2026-11-20" \
        or str(R.last_day_of_work([first, long_rest, unfit], "2026-11-21")) != "2026-12-09":
    fail.append("the last day of work is the end of the last rest or the doctor's finding, whichever is later")
print("14, 17: the doctor's reports, each rest its own sick leave, light duty, the separation on the doctor's word")

row_spec = doctype("Safety Medical Report")
row_fields = fields_of("Safety Medical Report")
if not row_spec.get("istable") or (fields.get("medical_reports") or {}).get("options") != "Safety Medical Report" \
        or not (fields.get("medical_reports") or {}).get("allow_on_submit"):
    fail.append("the doctor's reports are a table on the incident, added to once it is recorded")
recommendation = row_fields.get("recommendation") or {}
if recommendation.get("options", "").split("\n") != [""] + list(R.RECOMMENDATIONS) or not recommendation.get("reqd"):
    fail.append("each report says what the doctor recommends, starting blank: %r" % recommendation.get("options"))
for fieldname in ("report_date", "hospital", "doctor", "report", "rest_from", "rest_days", "rest_to", "light_duties",
                  "leave_application"):
    if fieldname not in row_fields:
        fail.append("a doctor's report has no %s" % fieldname)
for fieldname in ("rest_to", "leave_application"):
    if not (row_fields.get(fieldname) or {}).get("read_only"):
        fail.append("Safety Medical Report.%s is worked out, not typed" % fieldname)
if (row_fields.get("hospital") or {}).get("options") != "Hospital":
    fail.append("the report's hospital is picked from the list")
if set(R.STATUSES) - set((fields.get("status") or {}).get("options", "").split("\n")):
    fail.append("the incident's Status must offer every place the employee may stand")
for legacy in ("doctor_report", "day_off_required", "sick_from", "sick_days", "sickness_persists"):
    if not (fields.get(legacy) or {}).get("hidden"):
        fail.append("Safety Incident.%s is the single report the table replaces: hidden, kept for the record" % legacy)
for needle, why in (
    ("rules.report_errors(rows, doc.get(\"incident_on\"))", "the doctor's reports are judged by their own rules"),
    ("rules.fixed_row_errors(_rows(before), rows)", "a report that gave a sick leave stays as it was"),
    ('if row.get("recommendation") == rules.REST and not row.get("leave_application"):\n            _raise_sick_leave(doc, row)',
     "each rest becomes a sick leave, once"),
    ('row.db_set("leave_application", leave.name, update_modified=False)', "and the report says which"),
    ("_tell(_line_managers(doc), doc,", "light duty is told to whoever the employee works under"),
    ('frappe.db.get_value("Employee", doc.employee, "reports_to")', "who they report to among them"),
    ('@frappe.whitelist(methods=["POST"])\ndef separate_on_medical_grounds(incident, last_day=None):',
     "the separation is the HR Manager's own step"),
    ("rules.separation_errors(doc.docstatus, rows, doc.get(\"separation\"), frappe.get_roles())",
     "taken only on the doctor's recommendation"),
    ('doc.check_permission("write")', "by someone who may change the incident"),
):
    if needle not in glue:
        fail.append("safety.py: %s (%r not found)" % (why, needle[:60]))
if "sickness_persists" in glue:
    fail.append("a sickness that persists no longer separates anyone by itself: the doctor's word does (item 17)")
if "hrms_addon.hrms_addon.safety.daily" not in ((hooks.get("scheduler_events") or {}).get("daily") or []):
    fail.append("the doctor's next report is asked for daily")
if "hrms_addon.patches.v1_0.medical_reports_from_incidents" not in patches:
    fail.append("the single doctor's report already recorded becomes the first row")
legacy_patch = read("hrms_addon", "patches", "v1_0", "medical_reports_from_incidents.py")
for needle in ('"recommendation": "Rest" if rest else "Fit to Work"', '"leave_application": row.sick_leave if rest else None',
               'if frappe.db.exists("Safety Medical Report", {"parent": row.name, "parenttype": "Safety Incident"}):'):
    if needle not in legacy_patch:
        fail.append("medical_reports_from_incidents: %r" % needle)
form = read("hrms_addon", "hrms_addon", "doctype", "safety_incident", "safety_incident.js")
if 'frappe.user.has_role("HR Manager")' not in form or "hrms_addon.hrms_addon.safety.separate_on_medical_grounds" not in form:
    fail.append("the form offers the HR Manager Separate on Medical Grounds once the doctor finds the employee unfit")
steps = load("next_steps_rules").STEPS.get("Safety Incident") or ()
if ("Leave Application", "rows:medical_reports.leave_application", "Sick Leave") not in steps:
    fail.append("Next Steps open every sick leave the doctor's reports gave")
print("the paper and the glue: the table, the rest to sick leave, the separation the HR Manager's own")

# Luuka's letter, on the separation
_spec = importlib.util.spec_from_file_location("jinja_subset", os.path.join(REPO, "scripts", "jinja_subset.py"))
jinja_subset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jinja_subset)
letter_path = os.path.join(APP, "print_format", "termination_on_medical_grounds", "termination_on_medical_grounds.json")
letter = json.load(io.open(letter_path, encoding="utf-8")) if os.path.exists(letter_path) else {}
if (letter.get("doc_type"), letter.get("print_format_type"), letter.get("standard"), letter.get("module"),
        letter.get("name")) != ("Employee Separation", "Jinja", "Yes", "HRMS Addon", "Termination on Medical Grounds"):
    fail.append("Termination on Medical Grounds is a standard Jinja print of the Employee Separation")
html = letter.get("html") or ""
for needle in ("RE: TERMINATION ON MEDICAL GROUNDS", "decision to retire you on medical grounds",
               "your last day of work was", "Salary to the last day of work", "Outstanding leave if any.",
               "Less any monies owing to the company.", "Hand in to your head of department all company property",
               "EXECUTIVE DIRECTOR", "have read and understood the terms and conditions", "Witness HRM",
               "Witness Legal Manager", 'frappe.db.get_single_value("Onboarding Settings", "executive_director")'):
    if needle not in html:
        fail.append("the Termination on Medical Grounds letter does not say %r, which Luuka's does" % needle)
signer = re.search(r'<p class="who">([^<]*)</p>\s*<p class="who">EXECUTIVE DIRECTOR</p>', html)
if not signer or not signer.group(1).strip().startswith("{{"):
    fail.append("the letter names its signer from Onboarding Settings, never by name typed into it: the repository "
                "is public")
separation = upstream_fields("Employee Separation") | {f["fieldname"] for f in custom if f["dt"] == "Employee Separation"}
for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html)) - {"name", "creation"}):
    if fieldname not in separation:
        fail.append("the letter prints doc.%s, which the Employee Separation does not have" % fieldname)
try:
    render = jinja_subset.compile_template(html)
    employee = jinja_subset.wrap({"salutation": "Mr", "first_name": "John", "employee_name": "John <Okello>",
                                  "employee_number": "LPL1834", "department": "Production", "branch": "Kawempe"})
    utils = type("utils", (), {"format_date": staticmethod(lambda value: str(value))})
    db = type("db", (), {"get_value": staticmethod(lambda doctype, name, field: "Ed " + name),
                         "get_single_value": staticmethod(lambda doctype, field: "HR-EMP-0001"
                                                          if field == "executive_director" else None)})
    frappe_stub = type("frappe", (), {"utils": utils, "db": db, "get_doc": staticmethod(lambda doctype, name: employee)})
    sample = {"employee": "HR-EMP-0002", "custom_reason": "Medical Grounds", "custom_relieving_date": "2026-12-09",
              "custom_termination_date": "2026-11-21", "creation": "2026-11-21"}
    page = render({"doc": jinja_subset.wrap(sample), "frappe": frappe_stub})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S)))
    for needle in ("2026-11-21", "Mr John &lt;Okello&gt;", "LPL1834", "Division &ndash; Production", "Plant, Kawempe",
                   "Dear John,", "your last day of work was 2026-12-09", "ED HR-EMP-0001 EXECUTIVE DIRECTOR"):
        if needle not in text:
            fail.append("the Termination on Medical Grounds letter should read %r: %s" % (needle, text))
    other = render({"doc": jinja_subset.wrap(dict(sample, custom_reason="Resignation")), "frappe": frappe_stub})
    if "RE: TERMINATION ON MEDICAL GROUNDS" in other or "for a separation on medical grounds" not in other:
        fail.append("the letter is for a separation on medical grounds only, and says so on any other")
except Exception as error:  # noqa: BLE001
    fail.append("the Termination on Medical Grounds letter does not compile or render: %s" % error)
print("the letter: Luuka's own words, the last day of work, the Executive Director from the settings")


# ── 11. The medical treatment order ───────────────────────────────────
# "Under safety, need a provision for medical treatment order, one employee uses to access the hospital treatment."
T = load("treatment_approval")
walked, state = [T.DRAFT], T.DRAFT
for action in (T.SEND, T.ISSUE):
    nxt = [t["next_state"] for t in T.TRANSITIONS if t["state"] == state and t["action"] == action]
    if not nxt:
        break
    state = nxt[0]
    walked.append(state)
if walked != [T.DRAFT, T.PENDING_EHS, T.ISSUED]:
    fail.append("a treatment order is sent to the plant's EHS Officer, who issues it: %s" % walked)
order_docstatus = {row["state"]: str(row.get("doc_status", "0")) for row in T.STATES}
if [order_docstatus[s] for s in (T.DRAFT, T.PENDING_EHS, T.ISSUED, T.CANCELLED)] != ["0", "0", "1", "2"]:
    fail.append("an issued order is submitted, a cancelled one cancelled: %s" % order_docstatus)
if any(row["send_email"] for row in T.STATES):
    fail.append("no state of the order sends Frappe's own email to every EHS Officer")
if {t["allowed"] for t in T.TRANSITIONS if t["action"] == T.ISSUE} != {"EHS Officer", "HR Manager"}:
    fail.append("the order is issued by the EHS Officer, or the HR Manager standing in")
if not {"Supervisor", "Head of Department", "HR User", "EHS Officer"} <= {
        t["allowed"] for t in T.TRANSITIONS if t["action"] == T.SEND}:
    fail.append("the supervisor, the head of department, HR and the EHS Officer may ask for an order")
facts = {"user": "ehs.kawempe@luuka", "ehs_officer": "ehs.kawempe@luuka", "branch": "Kawempe"}
expect("the plant's officer issues it", T.step_errors(T.PENDING_EHS, T.ISSUED, facts))
expect("another plant's officer", T.step_errors(T.PENDING_EHS, T.ISSUED, dict(facts, user="ehs.matugga@luuka")),
       "Kawempe plant's EHS Officer")
expect("the HR Manager standing in", T.step_errors(T.PENDING_EHS, T.ISSUED, dict(facts, user="hrm@luuka", is_hrm=1)))
expect("returned with no reason", T.step_errors(T.PENDING_EHS, T.DRAFT, facts), "Return Remarks")
expect("sent from a plant with no officer", T.step_errors(T.DRAFT, T.PENDING_EHS, dict(facts, ehs_officer=None)),
       "No EHS Officer serves the Kawempe plant")
issued = T.compute_stamps(T.PENDING_EHS, T.ISSUED, "ehs.kawempe@luuka", "2026-12-01", {})
if (issued["issued_by"], issued["issued_on"]) != ("ehs.kawempe@luuka", "2026-12-01"):
    fail.append("the officer who issues the order signs and dates it: %s" % issued)
if T.compute_stamps(T.ISSUED, T.ISSUED, "x", "2026-12-02", issued) != issued:
    fail.append("a later save keeps the signature as it was")
if any(T.compute_stamps(T.PENDING_EHS, T.DRAFT, "x", "2026-12-01", issued).values()) \
        or any(T.compute_stamps(None, T.DRAFT, "x", "2026-12-01", {"issued_by": "forged"}).values()):
    fail.append("an order sent back, or a new one, carries no signature")
for old, new, wanted in ((T.DRAFT, T.PENDING_EHS, True), (T.PENDING_EHS, T.ISSUED, True), (T.ISSUED, T.ISSUED, False)):
    if T.officer_fixed(old, new) != wanted:
        fail.append("the plant's EHS Officer %s named again on the order's %s -> %s"
                    % ("is" if wanted else "is not", old, new))
order = {"employee": "E1", "hospital": "Mengo Hospital", "complaint": "Burn to the arm."}
expect("an order that stands", R.order_errors(order))
expect("no hospital", R.order_errors(dict(order, hospital="")), "which hospital")
expect("nothing to treat", R.order_errors(dict(order, complaint=" ")), "to be treated for")
expect("transport with no amount", R.order_errors(dict(order, transport_required=1)), "how much the transport")
expect("someone else's incident", R.order_errors(dict(order, incident_employee="E2")), "someone else")
expect("their own incident", R.order_errors(dict(order, incident_employee="E1")))
order_spec = doctype("Medical Treatment Order")
order_fields = fields_of("Medical Treatment Order")
if not order_spec.get("is_submittable") or "LPL-MTO-" not in (order_fields.get("naming_series") or {}).get("options", ""):
    fail.append("the order is a submitted document numbered LPL-MTO-YYYY-")
if (order_fields.get("hospital") or {}).get("options") != "Hospital" or not (order_fields.get("hospital") or {}).get("reqd"):
    fail.append("the order names its hospital from the list")
if (order_fields.get("safety_incident") or {}).get("options") != "Safety Incident":
    fail.append("the order names the incident it is for, where there is one")
for fieldname in ("ehs_officer", "issued_by", "issued_on", "transport_entry", "transport_paid_amount",
                  "transport_paid_on", "status"):
    if not (order_fields.get(fieldname) or {}).get("read_only"):
        fail.append("Medical Treatment Order.%s is filled in, not typed" % fieldname)
for fieldname in ("transport_entry", "transport_paid_amount", "transport_paid_on"):
    if not (order_fields.get(fieldname) or {}).get("allow_on_submit"):
        fail.append("Medical Treatment Order.%s is written once the order is issued: allow it on submit" % fieldname)
if {row["status"] for row in T.STATES} - set((order_fields.get("status") or {}).get("options", "").split("\n")):
    fail.append("the order's Status must offer every state")
for role in ("Supervisor", "Head of Department", "HR User", "EHS Officer"):
    if role not in roles_with(order_spec, "create"):
        fail.append("%s may ask for a treatment order" % role)
if "Accounts User" not in roles_with(order_spec, "read"):
    fail.append("the plant's accountant reads the order whose transport they pay")
if order_spec.get("default_print_format") != "Medical Treatment Order":
    fail.append("the order prints as the Medical Treatment Order")
order_print_path = os.path.join(APP, "print_format", "medical_treatment_order", "medical_treatment_order.json")
order_print = json.load(io.open(order_print_path, encoding="utf-8")) if os.path.exists(order_print_path) else {}
html = order_print.get("html") or ""
if (order_print.get("doc_type"), order_print.get("print_format_type"), order_print.get("standard")) \
        != ("Medical Treatment Order", "Jinja", "Yes") or not html.startswith("{{ print_control(doc) }}\n"):
    fail.append("the Medical Treatment Order is a standard Jinja print with its control line first")
for needle in ("MEDICAL TREATMENT ORDER", "The Doctor in Charge", "To be treated for", "For the hospital",
               "Diagnosis", "Treatment given", "Light duty", "Unfit for work", "Hospital stamp", "EHS Officer"):
    if needle not in html:
        fail.append("the Medical Treatment Order does not say %r" % needle)
for fieldname in sorted(set(re.findall(r"\bdoc\.(\w+)", html)) - {"name"}):
    if fieldname not in order_fields:
        fail.append("the order's print reads doc.%s, which the order does not have" % fieldname)
order_frappe = type("frappe", (), {
    "utils": type("utils", (), {"format_date": staticmethod(lambda value: str(value))}),
    "db": type("db", (), {"get_value": staticmethod(lambda doctype, name, field: "Ed " + name),
                          "get_single_value": staticmethod(lambda doctype, field: None)}),
    "get_doc": staticmethod(lambda doctype, name: jinja_subset.wrap({"employee_number": "LPL1834"}))})
try:
    render = jinja_subset.compile_template(html)
    page = render({"doc": jinja_subset.wrap({
        "name": "LPL-MTO-2026-00001", "employee": "E1", "employee_name": "Grace <Nakato>", "branch": "Kawempe",
        "department": "Production", "designation": "Operator", "company": "Luuka Plastics Limited",
        "hospital": "Mengo Hospital", "complaint": "Burn to the arm.", "issued_on": "2026-12-01",
        "issued_by": "ehs@luuka", "valid_until": None, "safety_incident": "LPL-EHS-2026-00009"}),
        "frappe": order_frappe})
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.S)))
    for needle in ("LPL-MTO-2026-00001", "Mengo Hospital", "Grace &lt;Nakato&gt;", "Burn to the arm.",
                   "LPL-EHS-2026-00009", "Ed ehs@luuka, EHS Officer"):
        if needle not in text:
            fail.append("the Medical Treatment Order should read %r: %s" % (needle, text))
except Exception as error:  # noqa: BLE001
    fail.append("the Medical Treatment Order does not compile or render: %s" % error)
print("11: the treatment order, issued by the plant's EHS Officer, printed for the hospital")

# ── 15. The transport in cash, the compensation on the insurance ──────
# "If compensation is required, it should be linked to insurance. Branch accountant makes the employee transport
# to the hospital payment-normall cash payment." The user: "insuranecy pays the employee not the company."
transport = {"docstatus": 1, "transport_required": 1, "transport_amount": 15000, "account": "Staff Transport - LPL",
             "cash_account": "Cash - LPL", "roles": ["Accounts User"]}
expect("the plant's accountant pays it", R.transport_errors(transport))
expect("someone else pays it", R.transport_errors(dict(transport, roles=["HR User"])), "accountant pays")
expect("paid before the order is issued", R.transport_errors(dict(transport, docstatus=0)), "once the order is issued")
expect("an order needing none", R.transport_errors(dict(transport, transport_required=0)), "needs no transport")
expect("paid twice", R.transport_errors(dict(transport, transport_entry="ACC-JV-2026-00001")), "paid already")
expect("no transport account", R.transport_errors(dict(transport, account=None)), "Safety Settings")
expect("no cash account", R.transport_errors(dict(transport, cash_account=None)), "Default Cash Account")
paid_rows = [{"account": "Staff Transport - LPL", "debit_in_account_currency": 15000},
             {"account": "Cash - LPL", "credit_in_account_currency": 15000}]
if R.transport_paid(paid_rows, "Staff Transport - LPL") != 15000 or R.transport_paid(paid_rows, None) != 0 \
        or R.transport_paid(paid_rows, "Cash - LPL") != -15000:
    fail.append("what an entry pays toward the transport is its debit on the transport account")
claim = {"compensation_required": 1, "compensation_amount": 2000000, "incident_on": "2026-11-02 14:00:00",
         "claim_status": "Not Lodged"}
expect("a claim not yet lodged", R.compensation_errors(claim))
expect("no amount claimed", R.compensation_errors(dict(claim, compensation_amount=0)), "how much compensation")
expect("lodged with nothing said", R.compensation_errors(dict(claim, claim_status="Lodged")),
       "which insurance policy", "claim number", "when the claim was lodged")
lodged = dict(claim, claim_status="Lodged", insurance_policy="Workmen's Compensation 2026", claim_number="CLM-1",
              claim_lodged_on="2026-11-05", policy_from="2026-01-01", policy_to="2026-12-31")
expect("lodged on a policy in force", R.compensation_errors(lodged))
expect("paid with nothing said", R.compensation_errors(dict(lodged, claim_status="Paid")),
       "how much the insurer paid the employee", "when the insurer paid the employee")
expect("on a policy that had lapsed", R.compensation_errors(dict(lodged, policy_to="2026-10-31")), "does not cover")
expect("no compensation, nothing asked", R.compensation_errors({"claim_status": "Lodged"}))
for fieldname in ("compensation_required", "compensation_amount", "insurance_policy", "insurer", "claim_status",
                  "claim_number", "claim_lodged_on", "insurer_paid_amount", "insurer_paid_on"):
    if not (fields.get(fieldname) or {}).get("allow_on_submit"):
        fail.append("Safety Incident.%s is followed after the incident is recorded: allow it on submit" % fieldname)
if (fields.get("insurance_policy") or {}).get("options") != "Insurance Policy" \
        or (fields.get("insurer") or {}).get("fetch_from") != "insurance_policy.insurer":
    fail.append("the claim is made on an Insurance Policy, its insurer read from it")
if (fields.get("claim_status") or {}).get("options", "").split("\n") != list(R.CLAIM_STATUSES):
    fail.append("the claim's status offers %s" % (R.CLAIM_STATUSES,))
if "insurer pays the employee" not in (fields.get("compensation_section") or {}).get("description", ""):
    fail.append("the form says the insurer pays the employee, and nothing is booked")
policy = fields_of("Insurance Policy")
if not {"policy_name", "insurer", "policy_number", "cover", "valid_from", "valid_to", "enabled"} <= set(policy) \
        or doctype("Insurance Policy").get("autoname") != "field:policy_name":
    fail.append("an Insurance Policy has its name, insurer, number, cover and dates")
settings = doctype("Safety Settings")
if not settings.get("issingle") or (fields_of("Safety Settings").get("transport_account") or {}).get("options") != "Account":
    fail.append("Safety Settings says which account the transport cash is booked to")
for needle, why in (
    ('@frappe.whitelist(methods=["POST"])\ndef make_transport_entry(order):', "the accountant's entry is drafted on request"),
    ('"voucher_type": "Cash Entry"', "as a cash payment"),
    ('"custom_medical_treatment_order": doc.name', "knowing the order it pays for"),
    ("rules.transport_errors(", "only when the order may be paid"),
    ('frappe.get_cached_value("Company", doc.company, "default_cash_account")', "out of the company's cash"),
    ('{"transport_entry": doc.name, "transport_paid_amount": paid,', "the order says it is paid, by what, how much"),
    ('{"transport_entry": None, "transport_paid_amount": 0,', "and lets go of a cancelled entry"),
    ("rules.compensation_errors(_claim_facts(doc))", "the claim is checked on every save"),
    ("workflows.setup_on_migrate(treatment,", "the order's workflow is built on migrate"),
    ("rules.order_errors(", "the order is judged by its own rules"),
):
    if needle not in glue:
        fail.append("safety.py: %s (%r not found)" % (why, needle[:60]))
journal_hooks = ((hooks.get("doc_events") or {}).get("Journal Entry") or {})
if "hrms_addon.hrms_addon.safety.journal_on_submit" not in (journal_hooks.get("on_submit") or []) \
        or "hrms_addon.hrms_addon.safety.journal_on_cancel" not in (journal_hooks.get("on_cancel") or []):
    fail.append("a Cash Entry's submit and cancel reach the order it pays for")
link = next((f for f in custom if f["name"] == "Journal Entry-custom_medical_treatment_order"), {})
if (link.get("fieldtype"), link.get("options"), link.get("read_only")) != ("Link", "Medical Treatment Order", 1):
    fail.append("the Cash Entry names its order, read-only")
if "Journal Entry-custom_medical_treatment_order" not in read("hrms_addon", "hooks.py"):
    fail.append("the Journal Entry field ships with the fixtures")
order_form = read("hrms_addon", "hrms_addon", "doctype", "medical_treatment_order", "medical_treatment_order.js")
if "hrms_addon.hrms_addon.safety.make_transport_entry" not in order_form or 'has_role("Accounts User")' not in order_form:
    fail.append("the order offers the plant's accountant Pay Transport")
if 'frappe.new_doc("Medical Treatment Order"' not in read("hrms_addon", "hrms_addon", "doctype", "safety_incident",
                                                         "safety_incident.js"):
    fail.append("the incident makes the treatment order the employee takes to hospital")
controller = read("hrms_addon", "hrms_addon", "doctype", "medical_treatment_order", "medical_treatment_order.py")
for method in ("validate", "on_update", "on_submit", "on_cancel"):
    if "    def %s(self):\n        safety.order_%s(self)" % (method, method) not in controller:
        fail.append("the Medical Treatment Order controller must hand %s to safety.order_%s" % (method, method))
for name in ("Medical Treatment Order", "Insurance Policy", "Safety Settings"):
    if carded.get(name) != "Tenure" or sidebarred.get(name) != "Tenure":
        fail.append("%s belongs on the Tenure page with the safety incident" % name)
if ("Medical Treatment Order", "back:safety_incident") not in steps:
    fail.append("Next Steps open the treatment orders an incident gave")
print("15: the transport paid in cash by the plant's accountant, the claim followed on the insurance")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL SAFETY CHECKS PASSED")
