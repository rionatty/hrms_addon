"""Verify the non-disciplinary grievance, without a bench:

    python scripts/verify_grievances.py

Luuka's chart 5.4 (Non-Disciplinary Grievances) and the test sheet's Non
Disciplinary cases, on Frappe HR's own Employee Grievance:

  1-2  HR raise it and the head of department it goes to is told and has
       it on their to-do list: Route to Handler (sections 3, 5, 8)
  3    the timeline is watched and the handler told as it falls due (1, 8)
  4    resolved, HR close it; not resolved, back to the handler: Accept,
       Reopen (3, 5)
  5    a draft the employee writes, with its type and the informal notes (7)
  6    LPL-GRV-YYYY-####, Open, the employee told it is received, HR told
       it waits (3, 7, 8)
  7    HR route it to the type's usual handler and the clock starts (3, 5, 8)
  8    the handler records the findings, cause, outcome and remedy;
       Resolved, and the employee told (3, 5)
  9    the employee accepts (Closed) or appeals (Appealed), heard by someone
       not involved (1, 3)
  10   one level up the chain as the date nears, HR once it is past (1, 8)
  11   the decision fields at level one, read-only to the employee (7)

  1  the timeline          5  what each step writes, the flow walked
  2  the stages            6  grievances raised before the workflow
  3  each step             7  the paper: fields, levels, numbering
  4  a save with no step   8  the glue and the wiring

Frappe HR's own fields are read from FRAPPE_APPS_ROOT (default ../ERPNext).
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


def upstream(name, ext="json"):
    folder = name.lower().replace(" ", "_")
    hits = glob.glob(os.path.join(APPS_ROOT, "hrms", "hrms", "**", "doctype", folder, folder + "." + ext),
                     recursive=True)
    if not hits:
        return None
    text = open(hits[0], encoding="utf-8").read()
    return json.loads(text) if ext == "json" else text


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


G, A = load("grievance_rules"), load("grievance_approval")
hooks = hooks_dict()
CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
SETTERS = json.load(open(os.path.join(PACKAGE, "fixtures", "property_setter.json"), encoding="utf-8"))
THEIRS = upstream("Employee Grievance")
print("loaded grievance_rules.py and grievance_approval.py without Frappe")

# ── 1. The timeline ───────────────────────────────────────────────────
day = datetime.date
if G.due_on("2026-10-07", 14) != day(2026, 10, 21) or G.due_on("2026-10-07", 0) != day(2026, 10, 21) \
        or G.due_on(None, 5) is not None:
    fail.append("a grievance is due its type's days after routing, a fortnight when the type says none")
if G.days_left("2026-10-21", "2026-10-07") != 14 or G.days_left(None, "2026-10-07") is not None:
    fail.append("days_left counts the days to the due date")
for due, today, state, wanted in (("2026-10-21", "2026-10-22", A.UNDER_REVIEW, True),
                                  ("2026-10-21", "2026-10-21", A.UNDER_REVIEW, False),
                                  ("2026-10-21", "2026-10-30", A.APPEALED, True),
                                  ("2026-10-21", "2026-10-30", A.RESOLVED, False),
                                  ("2026-10-21", "2026-10-30", A.OPEN, False),
                                  (None, "2026-10-30", A.UNDER_REVIEW, False)):
    if G.overdue(due, today, state) != wanted:
        fail.append("overdue(%s, %s, %s) should be %s: only a grievance someone has, past its date"
                    % (due, today, state, wanted))
if set(G.TIMED) != set(A.TIMED):
    fail.append("the rules and the workflow agree on when a grievance is against the clock")
for today, state, wanted in (("2026-10-10", A.UNDER_REVIEW, G.NOT_ESCALATED),
                             ("2026-10-19", A.UNDER_REVIEW, G.AT_RISK),
                             ("2026-10-21", A.UNDER_REVIEW, G.AT_RISK),
                             ("2026-10-22", A.UNDER_REVIEW, G.BREACHED),
                             ("2026-10-22", A.APPEALED, G.BREACHED),
                             ("2026-10-22", A.RESOLVED, G.NOT_ESCALATED),
                             ("2026-10-22", A.OPEN, G.NOT_ESCALATED)):
    if G.escalation("2026-10-21", today, state) != wanted:
        fail.append("case 10: due the 21st, on the %s in %s it is %r, not %r"
                    % (today, state, G.escalation("2026-10-21", today, state), wanted))
if G.escalation("2026-10-18", "2026-10-15", A.UNDER_REVIEW) != G.NOT_ESCALATED:
    fail.append("three days out is not yet at risk (AT_RISK_DAYS is %d)" % G.AT_RISK_DAYS)
if not (G.escalates("", G.AT_RISK) and G.escalates(G.AT_RISK, G.BREACHED) and G.escalates(None, G.BREACHED)):
    fail.append("each level up the chain is told")
if G.escalates(G.AT_RISK, G.AT_RISK) or G.escalates(G.BREACHED, G.AT_RISK) or G.escalates(G.AT_RISK, ""):
    fail.append("a level is told once, and never again on the way down")
if G.told_at(G.AT_RISK) != (G.HANDLER, G.DEPARTMENT_HEAD) \
        or G.told_at(G.BREACHED) != (G.HANDLER, G.DEPARTMENT_HEAD, G.HR):
    fail.append("case 10: handler, then the department head, then HR")
if G.told_at(G.AT_RISK, appeal=True) != (G.HANDLER,) or G.told_at(G.BREACHED, appeal=True) != (G.HANDLER, G.HR):
    fail.append("an appeal goes from who hears it straight to HR")
if G.told_at(G.NOT_ESCALATED):
    fail.append("nobody is told of a grievance with time on it")
holders = [{"user": "prod.hod", "branches": {"Namanve"}, "departments": {"Production"}},
           {"user": "prod.head.everywhere", "branches": set(), "departments": {"Production"}},
           {"user": "kampala.prod.hod", "branches": {"Kampala"}, "departments": {"Production"}},
           {"user": "free.hod", "branches": set(), "departments": set()},
           {"user": "fin.hod", "branches": {"Namanve"}, "departments": {"Finance"}}]
if G.department_heads(holders, "Namanve", "Production") != ["prod.head.everywhere", "prod.hod"]:
    fail.append("the department's heads: held to it, in this branch or every branch, %s"
                % G.department_heads(holders, "Namanve", "Production"))
if G.department_heads(holders, "Namanve", None) or G.department_heads(holders, "Namanve", "Stores"):
    fail.append("a grievance is never spread to heads of no department in particular")
if G.appeal_authority(["gm", "hrm", "ed"], ["gm", "employee"]) != "hrm" \
        or G.appeal_authority(["gm"], []) != "gm" or G.appeal_authority(["gm"], ["gm"]) is not None \
        or G.appeal_authority([None, "ed"], [None]) != "ed":
    fail.append("case 9: the first authority not already involved hears the appeal")
print("the timeline: due, at risk, breached; up the chain once a level; who hears an appeal")

# ── 2. The stages ─────────────────────────────────────────────────────
states = {}
for row in A.STATES:
    states.setdefault(row["state"], set()).add((row.get("doc_status", "0"), row["status"]))
for state, kinds in sorted(states.items()):
    if len(kinds) != 1:
        fail.append("%s is one stage: every row of it must agree on docstatus and status, %s" % (state, kinds))
docstatus = {state: next(iter(kinds))[0] for state, kinds in states.items()}
theirs_status = next((f for f in THEIRS["fields"] if f["fieldname"] == "status"), {}) if THEIRS else {}
options = (theirs_status.get("options") or "").split("\n")
if tuple(options) != A.FRAPPE_STATUSES:
    fail.append("Frappe HR's statuses have moved: %s, the workflow writes %s" % (options, A.FRAPPE_STATUSES))
for state, status in A.FRAPPE_STATUS.items():
    if status not in options:
        fail.append("%s writes %r into status, which Frappe HR's Select refuses" % (state, status))
for row in A.STATES:
    if row["status"] != A.FRAPPE_STATUS[row["state"]]:
        fail.append("%s writes %r, FRAPPE_STATUS says %r" % (row["state"], row["status"], A.FRAPPE_STATUS[row["state"]]))
if set(states) != set(A.FRAPPE_STATUS):
    fail.append("every stage has Frappe HR's status: %s" % (set(states) ^ set(A.FRAPPE_STATUS)))
filed = {state for state, kind in docstatus.items() if kind == "1"}
if filed != set(A.FILED) or docstatus.get(A.CANCELLED) != "2":
    fail.append("filed: %s, FILED says %s; Cancelled is docstatus 2" % (sorted(filed), A.FILED))
# Frappe HR files a grievance only at Resolved or Invalid
controller = upstream("Employee Grievance", "py") or ""
submit_rule = re.search(r"self\.status not in \[([^\]]+)\]", controller)
allowed_status = set(re.findall(r'"(\w+)"', submit_rule.group(1))) if submit_rule else set()
if allowed_status != {"Invalid", "Resolved"}:
    fail.append("Frappe HR's submit rule has moved: %s" % allowed_status)
for state in A.FILED:
    if A.FRAPPE_STATUS[state] not in allowed_status:
        fail.append("%s files the grievance with status %s, which Frappe HR refuses to submit"
                    % (state, A.FRAPPE_STATUS[state]))
# what Frappe's Workflow refuses (frappe/workflow/doctype/workflow/workflow.py validate_docstatus)
for t in A.TRANSITIONS:
    if t["state"] not in states or t["next_state"] not in states:
        fail.append("transition %s from %s to %s names a state that is not one" % (t["action"], t["state"], t["next_state"]))
        continue
    before, after = docstatus[t["state"]], docstatus[t["next_state"]]
    if before == "2" or (before == "1" and after == "0") or (before == "0" and after == "2"):
        fail.append("Frappe refuses %s: %s (%s) to %s (%s)" % (t["action"], t["state"], before, t["next_state"], after))
    if t["action"] not in A.ACTIONS:
        fail.append("%s is not in ACTIONS, so its button is never made" % t["action"])
for action in A.ACTIONS:
    if not [t for t in A.TRANSITIONS if t["action"] == action]:
        fail.append("%s is an action no transition takes" % action)
# whoever takes a step into a filed stage submits, and needs the right
theirs_submit = {p["role"] for p in (THEIRS or {}).get("permissions", []) if p.get("submit")}
submitters = theirs_submit | {role for role, ptypes in A.PERMISSIONS[A.DOCTYPE].items() if "submit" in ptypes}
for t in A.TRANSITIONS:
    if docstatus.get(t["next_state"]) in ("1", "2") and docstatus.get(t["state"]) == "0" \
            and t["allowed"] not in submitters:
        fail.append("%s may %s, which files the grievance, and cannot submit it" % (t["allowed"], t["action"]))
theirs_cancel = {p["role"] for p in (THEIRS or {}).get("permissions", []) if p.get("cancel")}
for t in A.TRANSITIONS:
    if docstatus.get(t["next_state"]) == "2" and t["allowed"] not in theirs_cancel:
        fail.append("%s may %s and cannot cancel" % (t["allowed"], t["action"]))
# each stage someone moves on from, they can open and edit
for t in A.TRANSITIONS:
    editors = {row["allow_edit"] for row in A.STATES if row["state"] == t["state"]}
    if t["allowed"] not in editors and docstatus[t["state"]] == "0":
        fail.append("%s may %s from %s, where the form is read-only to them" % (t["allowed"], t["action"], t["state"]))


def walk(*actions):
    state = A.DRAFT
    for action in actions:
        nxt = [t["next_state"] for t in A.TRANSITIONS if t["state"] == state and t["action"] == action]
        if not nxt:
            return None
        state = nxt[0]
    return state


for actions, wanted in (((A.RAISE, A.ROUTE, A.RESOLVE, A.ACCEPT), A.CLOSED),
                        ((A.RAISE, A.ROUTE, A.RESOLVE, A.APPEAL, A.DECIDE_APPEAL), A.APPEAL_DECIDED),
                        ((A.RAISE, A.MARK_INVALID), A.INVALID),
                        ((A.RAISE, A.ROUTE, A.RETURN, A.ROUTE, A.RESOLVE, A.REOPEN, A.RESOLVE, A.ACCEPT), A.CLOSED),
                        ((A.RAISE, A.ROUTE, A.RESOLVE, A.ACCEPT, A.CANCEL), A.CANCELLED)):
    if walk(*actions) != wanted:
        fail.append("%s should end %s, ends %s" % (" > ".join(actions), wanted, walk(*actions)))
if dict(A.next_states(A.DRAFT, (A.EMPLOYEE,))) != {A.RAISE: A.OPEN}:
    fail.append("case 5-6: the employee raises their own grievance")
if A.next_states(A.OPEN, (A.EMPLOYEE,)) or A.next_states(A.UNDER_REVIEW, (A.EMPLOYEE,)):
    fail.append("the employee neither routes nor resolves their own grievance")
if set(dict(A.next_states(A.RESOLVED, (A.EMPLOYEE,)))) != {A.ACCEPT, A.REOPEN, A.APPEAL}:
    fail.append("case 9: the employee accepts, reopens or appeals the outcome")
if set(dict(A.next_states(A.OPEN, (A.HR_OFFICER,)))) != {A.ROUTE, A.MARK_INVALID}:
    fail.append("case 7: the HR Officer routes it, or marks it invalid")
if set(dict(A.next_states(A.UNDER_REVIEW, (A.HOD,)))) != {A.RESOLVE, A.RETURN}:
    fail.append("case 8: the handler resolves it, or hands it back to HR")
if A.next_states(A.APPEALED, (A.HOD,)) or A.next_states(A.APPEALED, (A.EMPLOYEE,)):
    fail.append("an appeal is decided by neither the handler nor the employee")
if set(A.AUTHORITIES) - {t["allowed"] for t in A.TRANSITIONS if t["action"] == A.DECIDE_APPEAL}:
    fail.append("every authority who may hear an appeal may decide it")
for role in (A.HOD, A.GM, A.ED):
    if role not in A.NEW_ROLES:
        fail.append("%s is named in the workflow: it must be created" % role)
# Frappe's own workflow email goes, with the print, to every holder of the
# next role who can read the grievance (workflow_action.py)
emailing = sorted({row["state"] for row in A.STATES if row.get("send_email")})
if emailing:
    fail.append("a grievance is confidential: no stage sends Frappe's workflow email, %s do" % emailing)
expect("the employee deletes their own draft", A.delete_errors(A.DRAFT, [A.EMPLOYEE]))
expect("or a draft thrown away", A.delete_errors(A.CANCELLED, [A.HR_OFFICER]))
expect("the employee deletes it once raised", A.delete_errors(A.UNDER_REVIEW, [A.EMPLOYEE]), "kept on the record")
expect("the HR Officer deletes it once raised", A.delete_errors(A.OPEN, [A.HR_OFFICER, A.EMPLOYEE]), "kept on the record")
expect("the HR Manager may", A.delete_errors(A.RESOLVED, [A.HRM]))
print("the stages: Frappe HR's statuses, its submit rule, Frappe's docstatus rules, who may file it, "
      "no broadcast email, who may delete it")

# ── 3. Each step ──────────────────────────────────────────────────────
employee, hr, hod, gm, other = "emp@luuka", "hro@luuka", "hod@luuka", "gm@luuka", "someone@luuka"
raise_facts = {"user": employee, "raiser": employee, "grievance_type": "Welfare", "subject": "Lockers",
               "description": "The locker room floods."}
expect("case 6: the employee raises their own", A.step_errors(A.DRAFT, A.OPEN, raise_facts))
expect("HR raise it for them", A.step_errors(A.DRAFT, A.OPEN, dict(raise_facts, user=hr, is_hr=1)))
expect("someone else raises it", A.step_errors(A.DRAFT, A.OPEN, dict(raise_facts, user=other)), "raised by the employee")
expect("raised with nothing in it", A.step_errors(A.DRAFT, A.OPEN, {"user": employee, "raiser": employee}),
       "Grievance Type", "subject", "own words")
route = {"user": hr, "is_hr": 1, "raiser": employee, "handler": hod, "handler_roles": [A.HOD, A.EMPLOYEE]}
expect("case 7: routed to a head of department", A.step_errors(A.OPEN, A.UNDER_REVIEW, route))
expect("routed to HR themselves", A.step_errors(A.OPEN, A.UNDER_REVIEW, dict(route, handler=hr, handler_roles=[A.HR_OFFICER])))
expect("routed to nobody", A.step_errors(A.OPEN, A.UNDER_REVIEW, dict(route, handler=None)), "Name the handler")
expect("routed to the employee", A.step_errors(A.OPEN, A.UNDER_REVIEW, dict(route, handler=employee)),
       "not handled by the employee who raised it")
expect("routed to someone who cannot resolve it",
       A.step_errors(A.OPEN, A.UNDER_REVIEW, dict(route, handler=other, handler_roles=[A.EMPLOYEE])),
       "Head of Department role")
expect("invalid, with the reason", A.step_errors(A.OPEN, A.INVALID, {"user": hr, "is_hr": 1, "outcome": "Not a grievance."}))
expect("invalid, saying nothing", A.step_errors(A.OPEN, A.INVALID, {"user": hr, "is_hr": 1}), "why the grievance is not taken up")
resolve = {"user": hod, "handler": hod, "meeting_notes": "<p>Met the canteen supplier.</p>", "cause": "Blocked drain.",
           "outcome": "Drain cleared.", "remedy": "Weekly check."}
expect("case 8: the handler resolves it", A.step_errors(A.UNDER_REVIEW, A.RESOLVED, resolve))
expect("HR resolve it", A.step_errors(A.UNDER_REVIEW, A.RESOLVED, dict(resolve, user=hr, is_hr=1)))
expect("another head resolves it", A.step_errors(A.UNDER_REVIEW, A.RESOLVED, dict(resolve, user=other)),
       "resolved by its handler")
expect("resolved with an empty editor and nothing else",
       A.step_errors(A.UNDER_REVIEW, A.RESOLVED, {"user": hod, "handler": hod, "meeting_notes": "<div><p><br></p></div>"}),
       "meeting notes", "caused", "outcome", "remedy")
expect("handed back with a reason", A.step_errors(A.UNDER_REVIEW, A.OPEN, {"user": hod, "handler": hod, "remarks": "Not mine."}))
expect("handed back saying nothing", A.step_errors(A.UNDER_REVIEW, A.OPEN, {"user": hod, "handler": hod}), "remarks")
expect("handed back by another head", A.step_errors(A.UNDER_REVIEW, A.OPEN, {"user": other, "handler": hod, "remarks": "x"}),
       "Only its handler")
answer = {"user": employee, "raiser": employee}
expect("case 9: the employee accepts", A.step_errors(A.RESOLVED, A.CLOSED, answer))
expect("case 4: HR close it for them", A.step_errors(A.RESOLVED, A.CLOSED, {"user": hr, "is_hr": 1, "raiser": employee}))
expect("the handler accepts for them", A.step_errors(A.RESOLVED, A.CLOSED, {"user": hod, "raiser": employee}),
       "answers its outcome")
expect("case 4: reopened, saying what is wrong", A.step_errors(A.RESOLVED, A.UNDER_REVIEW, dict(answer, remarks="Still floods.")))
expect("reopened saying nothing", A.step_errors(A.RESOLVED, A.UNDER_REVIEW, answer), "still not resolved")
appeal = dict(answer, appeal_grounds="The remedy is not done.", authority=gm, authority_roles=[A.GM],
              involved=[employee, hr, hod])
expect("case 9: appealed to the General Manager", A.step_errors(A.RESOLVED, A.APPEALED, appeal))
expect("appealed with no grounds", A.step_errors(A.RESOLVED, A.APPEALED, dict(appeal, appeal_grounds=" ")), "grounds")
expect("appealed to the handler", A.step_errors(A.RESOLVED, A.APPEALED, dict(appeal, authority=hod, authority_roles=[A.GM])),
       "not already acted")
expect("appealed to nobody", A.step_errors(A.RESOLVED, A.APPEALED, dict(appeal, authority=None)), "Name who hears the appeal")
expect("appealed to someone with no say", A.step_errors(A.RESOLVED, A.APPEALED, dict(appeal, authority=other, authority_roles=[A.HOD])),
       "General Manager, the HR Manager or the Executive Director")
decide = {"user": gm, "authority": gm, "appeal_outcome": "Upheld."}
expect("the appeal decided by who hears it", A.step_errors(A.APPEALED, A.APPEAL_DECIDED, decide))
expect("the HR Manager records it", A.step_errors(A.APPEALED, A.APPEAL_DECIDED, dict(decide, user=hr, is_hrm=1)))
expect("decided by someone else, with nothing written",
       A.step_errors(A.APPEALED, A.APPEAL_DECIDED, {"user": other, "authority": gm}), "decided by who hears it", "outcome")
expect("a save that takes no step", A.step_errors(A.OPEN, A.OPEN, {}))
print("each step: who may take it and what it needs")

# ── 4. A save with no step ────────────────────────────────────────────
expect("the employee edits their draft", A.change_errors(A.DRAFT, ["description", "custom_informal_notes"], {"is_hr": 0}))
expect("the employee rewrites it once raised", A.change_errors(A.OPEN, ["description"], {"is_hr": 0}), "only HR change")
expect("HR correct it", A.change_errors(A.UNDER_REVIEW, ["grievance_type", "subject"], {"is_hr": 1}))
expect("HR hand it to another head", A.change_errors(A.UNDER_REVIEW, ["custom_assigned_hod"],
                                                     {"is_hr": 1, "handler": other, "handler_roles": [A.HOD]}))
expect("the head hands it on himself", A.change_errors(A.UNDER_REVIEW, ["custom_assigned_hod"],
                                                       {"is_hr": 0, "handler": other, "handler_roles": [A.HOD]}),
       "Only HR hand")
expect("HR hand it to the employee", A.change_errors(A.UNDER_REVIEW, ["custom_assigned_hod"],
                                                     {"is_hr": 1, "handler": employee, "raiser": employee}),
       "not handled by the employee")
expect("the head moves the date", A.change_errors(A.UNDER_REVIEW, ["custom_due_on"], {"is_hr": 0}), "due")
expect("HR move the date", A.change_errors(A.UNDER_REVIEW, ["custom_due_on"], {"is_hr": 1}))
expect("HR give the appeal to someone involved",
       A.change_errors(A.APPEALED, ["custom_appeals_authority"], {"is_hr": 1, "authority": hod, "involved": [hod],
                                                                  "authority_roles": [A.GM]}), "not already acted")
expect("the authority hands the appeal on", A.change_errors(A.APPEALED, ["custom_appeals_authority"], {"is_hr": 0}),
       "Only HR change who hears")
print("a save with no step: the employee's account fixed once raised, the handler and date HR's to change")

# ── 5. What each step writes, the flow walked ─────────────────────────
D7, D21 = day(2026, 10, 7), day(2026, 10, 21)
changes = A.step_changes(A.OPEN, A.UNDER_REVIEW, {"user": hr}, D7, D21)
if (changes.get("custom_booked_on"), changes.get("custom_due_on"), changes.get("custom_reported_to")) != (D7, D21, hr) \
        or changes.get("custom_escalation") != "" or "custom_return_remarks" not in changes:
    fail.append("case 2 and 7: routed, it is booked today, due in its days, routed by HR: %s" % changes)
changes = A.step_changes(A.UNDER_REVIEW, A.OPEN, {"user": hod}, D7, D21)
if changes.get("custom_due_on", "x") is not None or "custom_return_remarks" in changes:
    fail.append("handed back, the clock stops and the remarks stay for HR: %s" % changes)
changes = A.step_changes(A.UNDER_REVIEW, A.RESOLVED, {"user": hod}, D7, D21)
if (changes.get("resolved_by"), changes.get("resolution_date")) != (hod, D7) or "custom_due_on" in changes:
    fail.append("resolved, the handler and the day are written, and the due date stays as the record: %s" % changes)
changes = A.step_changes(A.RESOLVED, A.UNDER_REVIEW, {"user": employee}, D7, D21)
if changes.get("resolved_by", "x") is not None or changes.get("custom_due_on") != D21 \
        or "custom_reported_to" in changes or "custom_return_remarks" in changes:
    fail.append("case 4: reopened, it is not resolved, has a new date and keeps the remarks: %s" % changes)
if A.step_changes(A.RESOLVED, A.CLOSED, {}, D7, D21).get("custom_outcome_accepted") != 1:
    fail.append("accepted, the record says so")
changes = A.step_changes(A.RESOLVED, A.APPEALED, {}, D7, D21)
if (changes.get("custom_appeal_filed"), changes.get("custom_appealed_on"), changes.get("custom_due_on")) != (1, D7, D21):
    fail.append("appealed, the record says when, and the appeal has its own date: %s" % changes)
if A.step_changes(A.OPEN, A.OPEN, {}, D7, D21):
    fail.append("a save that takes no step writes nothing")
for (old, new) in [(t["state"], t["next_state"]) for t in A.TRANSITIONS]:
    keep = (old, new) in ((A.UNDER_REVIEW, A.OPEN), (A.RESOLVED, A.UNDER_REVIEW))
    if ("custom_return_remarks" in A.step_changes(old, new, {}, D7, D21)) == keep:
        fail.append("%s to %s: remarks %s" % (old, new, "kept for whoever has it next" if keep else "cleared"))
print("what each step writes: the clock, the resolver, the answer, the remarks")

# ── 6. Grievances raised before the workflow ──────────────────────────
for args, wanted in (((0, "Open", None, False), A.OPEN), ((0, "Open", hod, False), A.UNDER_REVIEW),
                     ((0, "Investigated", hod, False), A.UNDER_REVIEW), ((0, "Investigated", None, False), A.OPEN),
                     ((0, "Resolved", hod, False), A.RESOLVED), ((0, "Invalid", hod, False), A.OPEN),
                     ((1, "Resolved", hod, False), A.CLOSED), ((1, "Resolved", hod, True), A.APPEAL_DECIDED),
                     ((1, "Invalid", None, False), A.INVALID), ((2, "Resolved", hod, False), A.CANCELLED)):
    if A.stage_of(*args) != wanted:
        fail.append("stage_of%s should be %s, is %s" % (args, wanted, A.stage_of(*args)))
for args in ((0, "Open"), (1, "Resolved"), (1, "Invalid"), (2, "Cancelled")):
    if docstatus[A.stage_of(*args)] != str(args[0]):
        fail.append("stage_of%s: the stage must match the grievance's docstatus" % (args,))
patch = read("hrms_addon", "patches", "v1_0", "grievances_on_workflow.py")
for needle, why in (("approval.stage_of(", "the patch places each grievance by stage_of"),
                    ('"is", "not set"', "and leaves one that has a stage alone"),
                    ('"Workflow State"', "and makes Frappe's state field where the site has none"),
                    ("update_modified=False", "without touching when it was last changed")):
    if needle not in patch:
        fail.append("grievances_on_workflow.py: %s (%r)" % (why, needle))
patches = read("hrms_addon", "patches.txt")
if "hrms_addon.patches.v1_0.grievances_on_workflow" not in patches.split("[post_model_sync]", 1)[-1]:
    fail.append("the patch runs after the model sync, before after_migrate builds the workflow")
print("grievances raised before: each at the stage it stands at")

# ── 7. The paper ──────────────────────────────────────────────────────
if not THEIRS:
    fail.append("Frappe HR's Employee Grievance is not where it was: 5.4 is built on it")
if os.path.exists(os.path.join(APP, "doctype", "employee_grievance")):
    fail.append("the grievance stays Frappe HR's own, extended, not copied here")
theirs = {f["fieldname"]: f for f in (THEIRS or {}).get("fields", [])}
ours = {row["fieldname"]: row for row in CUSTOM if row.get("dt") == A.DOCTYPE}
fields = dict(theirs, **ours)
setters = {(row["doc_type"], row.get("field_name"), row["property"]): row["value"] for row in SETTERS}
for fieldname in ("custom_reported_to", "custom_assigned_hod", "custom_booked_on", "custom_branch", "custom_department",
                  "custom_due_on", "custom_overdue", "custom_escalation", "custom_return_remarks",
                  "custom_informal_notes", "custom_meeting_notes", "custom_remedy", "custom_outcome_accepted",
                  "custom_appeal_filed", "custom_appealed_on", "custom_appeal_grounds", "custom_appeals_authority",
                  "custom_appeal_outcome"):
    if fieldname not in ours:
        fail.append("Employee Grievance has no %s" % fieldname)
if ours.get("custom_escalation", {}).get("options", "").split("\n") != list(G.ESCALATIONS):
    fail.append("Escalation's options are the chain's levels, blank first: %r" % ours.get("custom_escalation", {}).get("options"))
if (ours.get("custom_department") or {}).get("fetch_from") != "raised_by.department":
    fail.append("case 11: the department comes from the employee, so heads are held to theirs by User Permission")


def level(fieldname):
    if fieldname in ours:
        return int(ours[fieldname].get("permlevel") or 0)
    return int(setters.get((A.DOCTYPE, fieldname, "permlevel"), theirs.get(fieldname, {}).get("permlevel") or 0))


for fieldname in A.DECISION_FIELDS + A.DECISION_CUSTOM_FIELDS + ("cause_of_grievance",):
    if level(fieldname) != A.LEVEL:
        fail.append("case 11: %s decides the grievance and sits at level %d, not %d" % (fieldname, level(fieldname), A.LEVEL))
for fieldname in A.STATEMENT_FIELDS + ("custom_return_remarks", "custom_appeal_grounds"):
    if level(fieldname) != 0:
        fail.append("%s is the employee's to write, at level 0, not %d" % (fieldname, level(fieldname)))
if set(A.LEVEL_ONE[A.EMPLOYEE]) != {"read"}:
    fail.append("case 11: the employee reads the decision and changes none of it")
for role in A.HANDLER_ROLES + A.AUTHORITIES:
    if "write" not in A.LEVEL_ONE.get(role, ()):
        fail.append("%s decides at level one and must write there" % role)
for fieldname in ("custom_reported_to", "custom_booked_on", "custom_overdue", "custom_escalation", "custom_outcome_accepted",
                  "custom_appeal_filed", "custom_appealed_on"):
    if not ours.get(fieldname, {}).get("read_only"):
        fail.append("%s is written by the steps alone: read-only" % fieldname)
if setters.get((A.DOCTYPE, "status", "read_only")) != "1":
    fail.append("the status follows the stage: read-only")
for fieldname in ("resolved_by", "resolution_date"):
    if setters.get((A.DOCTYPE, fieldname, "read_only")) != "1":
        fail.append("%s is written when it is resolved: read-only" % fieldname)
for fieldname in ("grievance_against_party", "grievance_against"):
    if setters.get((A.DOCTYPE, fieldname, "reqd")) != "0":
        fail.append("a grievance about conditions is against nobody: %s optional" % fieldname)
if setters.get((A.DOCTYPE, "cause_of_grievance", "mandatory_depends_on")) != 'eval: doc.status == "Resolved"':
    fail.append("the cause is found by the handler, and asked for once resolved, not while under review")
autoname = setters.get((A.DOCTYPE, None, "autoname"))
if autoname != "LPL-GRV-.YYYY.-.####":
    fail.append("case 6: LPL-GRV-YYYY-#### names the grievance, not %r" % autoname)
for fieldname, row in ours.items():
    if fieldname.startswith("custom_") and row.get("fieldtype") not in ("Section Break", "Column Break") \
            and fieldname not in ("custom_branch", "custom_department", "custom_informal_notes") and not row.get("no_copy"):
        fail.append("%s belongs to this grievance's handling: no_copy, so an amendment starts clean" % fieldname)
for fieldname, row in ours.items():
    for state in re.findall(r'"([A-Z][\w ]+)"', row.get("depends_on") or ""):
        if state not in states:
            fail.append("%s depends on %r, which is not a stage" % (fieldname, state))
type_fields = {row["fieldname"] for row in CUSTOM if row.get("dt") == "Grievance Type"}
if not {"custom_timeline_days", "custom_default_handler"} <= type_fields:
    fail.append("case 7: a Grievance Type carries its days and its usual handler")
print("the paper: the fields, the decision at level one, LPL-GRV numbering, the employee's own words")

# ── 8. The glue and the wiring ────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "grievances.py")
known = set(fields) | type_fields | {"name", "owner", "docstatus", "doctype", A.STATE_FIELD, "employee_name"}
for fieldname in sorted(set(re.findall(r'doc\.get\("(\w+)"\)', glue)) | set(re.findall(r'before\.get\("(\w+)"\)', glue))
                        | set(re.findall(r'"(custom_\w+)"', glue)) | set(re.findall(r"row\.(custom_\w+)", glue))):
    if fieldname not in known:
        fail.append("grievances.py reads or writes %s, which Employee Grievance does not have" % fieldname)
for fieldname in sorted(set(re.findall(r'"(custom_\w+|resolved_by|resolution_date)"', read("hrms_addon", "hrms_addon",
                                                                                                "grievance_approval.py")))):
    if fieldname not in fields:
        fail.append("grievance_approval.py names %s, which Employee Grievance does not have" % fieldname)
for needle, why in (
    ("approval.step_errors(", "case 6-9: each step is judged by the workflow's rules"),
    ("approval.change_errors(", "a save with no step too"),
    ("approval.step_changes(", "and writes what the rules say"),
    ("rules.appeal_authority(", "case 9: the appeal goes to someone not involved"),
    ("rules.due_on(", "case 7: the clock starts on routing"),
    ("rules.escalation(", "case 10: the daily job climbs the chain"),
    ("rules.department_heads(", "to the head of the employee's department"),
    ("people.hr_officers(", "and to HR"),
    ("people.assign(", "case 2: the handler has it on their to-do list"),
    ("people.withdraw(", "and it comes off whoever had it"),
    ("not in approval.FILED", "a grievance is filed by its buttons only"),
    ('"custom_default_handler"', "case 7: the type's usual handler"),
    ("limit_page_length=0", "the daily job reads every grievance against the clock"),
    ("_let_act([handler], doc)", "the handler can write the findings, whatever their User Permissions"),
    ("_let_act([authority], doc, submit=True)", "and who hears an appeal can file the decision"),
    ("_let_act([doc.custom_assigned_hod], doc)", "and so can a handler HR hand it on to"),
    ("_let_act([doc.custom_appeals_authority], doc, submit=True)", "and an authority HR name instead"),
    ('add_docshare(DOCTYPE, doc.name, user, write=1', "by a share that writes, where Frappe's assignment only reads"),
    ("approval.delete_errors(", "once raised, a grievance is kept"),
    ('"Custom DocPerm", filters={"parent": DOCTYPE, "permlevel": 0}', "level one only for roles Frappe lets have it"),
    ("if role in level_zero}", "the roles with nothing at level 0 left out of the grant"),
):
    if needle not in glue:
        fail.append("grievances.py: %s (%r not found)" % (why, needle))
if not re.search(r"@frappe\.whitelist\(\)\ndef holders_of\(", glue):
    fail.append("the pickers' query must be whitelisted")
if "Your grievance {0} is received" not in glue or "Your grievance {0} is resolved" not in glue:
    fail.append("case 6 and 8: the employee is told it is received, and told the outcome")
discipline = read("hrms_addon", "hrms_addon", "discipline.py")
if "concern_" in discipline or "_chase_concerns" in discipline:
    fail.append("the old concern handlers must be gone from discipline.py: grievances.py has the grievance")

events = (hooks.get("doc_events") or {}).get(A.DOCTYPE) or {}
if events != {"validate": "hrms_addon.hrms_addon.grievances.grievance_validate",
              "on_discard": "hrms_addon.hrms_addon.grievances.grievance_on_discard",
              "on_trash": "hrms_addon.hrms_addon.grievances.grievance_on_trash"}:
    fail.append("Employee Grievance's events go to grievances.py alone: %s" % events)
daily = (hooks.get("scheduler_events") or {}).get("daily") or []
if "hrms_addon.hrms_addon.grievances.daily" not in daily:
    fail.append("case 3 and 10: the timeline is watched daily")
after = hooks.get("after_migrate") or []
mine, security = "hrms_addon.hrms_addon.grievances.setup_on_migrate", "hrms_addon.hrms_addon.security.setup_on_migrate"
if mine not in after or (security in after and after.index(mine) < after.index(security)):
    fail.append("the workflow is built on migrate, after security makes the Auditor who reads level one")
if (hooks.get("doctype_js") or {}).get(A.DOCTYPE) != "public/js/employee_grievance.js":
    fail.append("the grievance's form script")
script = read("hrms_addon", "public", "js", "employee_grievance.js")
timed = re.search(r"HA_GRIEVANCE_TIMED = \[([^\]]*)\]", script)
if not timed or set(re.findall(r'"([^"]+)"', timed.group(1))) != set(A.TIMED):
    fail.append("the form's due-date headline shows in the same stages the clock runs in")
if "HA_GRIEVANCE_AT_RISK_DAYS = %d;" % G.AT_RISK_DAYS not in script:
    fail.append("the form marks a grievance at risk as the daily job does")
if "hrms_addon.hrms_addon.grievances.holders_of" not in script:
    fail.append("the Handler and Appeal Heard By pickers offer only those who can act")
for state in set(re.findall(r'workflow_state === "([^"]+)"', script)):
    if state not in states:
        fail.append("the form script names %r, which is not a stage" % state)
navigation = load("navigation_rules")
carded = {link[1] for _page, cards in navigation.CARDS.items() for _card, links in cards for link in links}
sidebarred = {entry[1] for _page, entries in navigation.SIDEBAR.items() for entry in entries}
if A.DOCTYPE in carded or A.DOCTYPE in sidebarred:
    fail.append("the grievance is Frappe HR's own and already on their Grievance card: leave it alone")
print("glue and wiring: the rules followed, the people told, the events, the daily job, the workflow on migrate")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL GRIEVANCE CHECKS PASSED")
