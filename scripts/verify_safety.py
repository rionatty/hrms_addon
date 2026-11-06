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
import importlib.util
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
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
expect("a day off with no dates", R.incident_errors(dict(incident, day_off_required=1)),
       "when the sick leave starts", "how many days")
if R.incident_status(1, 1, "HR-LAP-1", 0, None) != R.ON_SICK_LEAVE:
    fail.append("an incident with sick leave running says so")
if R.incident_status(1, 0, None, 0, None) != R.BACK:
    fail.append("one needing no day off ends with the employee at work")
if R.incident_status(1, 1, "x", 1, "HR-EMP-SEP-1") != R.SEPARATED:
    fail.append("one where the sickness persisted ends in separation")
print("the incident: what it must say, where the employee stands after it")

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
known = set(fields) | {"doctype", "name", "docstatus", "owner", "flags"}
for fieldname in sorted(set(re.findall(r'(?<![\w])doc\.get\("(\w+)"\)', glue))
                        | set(re.findall(r"(?<![\w])doc\.(\w+)\b", glue))):
    if fieldname in ("get", "set", "db_set", "get_doc_before_save", "name", "docstatus"):
        continue
    if fieldname not in known:
        fail.append("safety.py reads or writes %s, which the Safety Incident does not have" % fieldname)
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

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL SAFETY CHECKS PASSED")
