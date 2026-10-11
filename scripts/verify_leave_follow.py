"""Checks a leave followed through, without a bench.

    python scripts/verify_leave_follow.py

The leave review of 11 Oct 2026 (leave_follow_rules.py, leave_follow.py):

  1  an approval that stalls: reminded, then taken a level up, each once;
     an approver on leave stood in for by whoever relieves them
  2  cover: every application read against who else is off, and who takes
     over the work
  3  after approval: ended early, extended, and overdue
  4  the glue follows the rules; the settings, the fields, the workflow's
     one more step, the form's buttons and the daily jobs are wired
"""
import ast
import datetime
import importlib.util
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


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


def same(label, got, want):
    if got != want:
        fail.append("%s: expected %r, got %r" % (label, want, got))


R, LA, L = load("leave_follow_rules"), load("leave_approval"), load("leave_rules")
print("loaded leave_follow_rules.py without Frappe")

# ── the settings ──────────────────────────────────────────────────────
same("what was never saved takes its default", R.settings_from({}), R.DEFAULTS)
same("a step saved as 0 is switched off, not defaulted", R.settings_from({"remind_after_days": "0"})["remind_after_days"], 0)
same("a figure comes back a number", R.settings_from({"escalate_after_days": "6", "most_off": "3.0"})["most_off"], 3)
expect("the defaults", R.settings_errors(R.DEFAULTS))
expect("told above before the desk is reminded",
       R.settings_errors(dict(R.DEFAULTS, remind_after_days=4, escalate_after_days=4)), "after the desk has been reminded")
expect("one switched off is no contradiction", R.settings_errors(dict(R.DEFAULTS, remind_after_days=0)))
expect("a reminder a year away", R.settings_errors(dict(R.DEFAULTS, remind_after_days=1, escalate_after_days=400)),
       "between 0 and 60 days")
expect("less than nobody off", R.settings_errors(dict(R.DEFAULTS, most_off=-1)), "less than nothing")

# ── 1. an approval that stalls ────────────────────────────────────────
D = datetime.date
for label, got, want in (
    ("a day on the desk", R.chase("2026-10-01", "2026-10-02", None, 2, 4), None),
    ("two days: reminded", R.chase("2026-10-01", "2026-10-03", None, 2, 4), R.REMINDED),
    ("reminded once", R.chase("2026-10-01", "2026-10-04", R.REMINDED, 2, 4), None),
    ("four days: the level above", R.chase("2026-10-01", "2026-10-05", R.REMINDED, 2, 4), R.ESCALATED),
    ("told once", R.chase("2026-10-01", "2026-10-09", R.ESCALATED, 2, 4), None),
    ("found late, it goes straight up", R.chase("2026-10-01", "2026-10-09", None, 2, 4), R.ESCALATED),
    ("reminders off, the level above still hears", R.chase("2026-10-01", "2026-10-05", None, 0, 4), R.ESCALATED),
    ("escalation off, the desk is still reminded", R.chase("2026-10-01", "2026-10-20", None, 2, 0), R.REMINDED),
    ("both off", R.chase("2026-10-01", "2026-10-20", None, 0, 0), None),
    ("no day kept", R.chase(None, "2026-10-20", None, 2, 4), None),
):
    same(label, got, want)
same("days on a desk", R.days_waiting("2026-10-01", D(2026, 10, 5)), 4)
same("never fewer than none", R.days_waiting("2026-10-09", "2026-10-05"), 0)
if R.LEVEL_ABOVE != {"Supervisor": "Head of Department", "Head of Department": "HR User", "HR User": "HR Manager"}:
    fail.append("a desk's level above: the HOD over the supervisor, HR over the HOD, the HR Manager over HR")
if set(LA.ROLE_WAITING.values()) - set(R.LEVEL_ABOVE):
    fail.append("every desk of the leave form has a level above: %s" % sorted(LA.ROLE_WAITING.values()))
away = {"sup": {"until": "2026-10-20", "stand_in": "ruth"}}
same("at their desk, they are asked", R.at_the_desk(["sup"]), {"ask": ["sup"], "standing_in": {}, "empty": False})
same("away, whoever relieves them is asked, where they may sign", R.at_the_desk(["sup"], away, {"ruth"}),
     {"ask": ["ruth"], "standing_in": {"ruth": "sup"}, "empty": False})
same("a reliever who may not sign leaves the desk empty", R.at_the_desk(["sup"], away, set()),
     {"ask": [], "standing_in": {}, "empty": True})
same("a reliever away themselves is not asked",
     R.at_the_desk(["sup"], dict(away, ruth={"until": "2026-10-12", "stand_in": None}), {"ruth"})["empty"], True)
same("one away, one in: the one in is asked, and the stand-in",
     R.at_the_desk(["sup", "sup3"], away, {"ruth"})["ask"], ["sup3", "ruth"])
same("a colleague at the same desk relieving is asked once, in their own right",
     R.at_the_desk(["sup", "ruth"], away, {"ruth"}), {"ask": ["ruth"], "standing_in": {}, "empty": False})
same("nobody holds the desk at all", R.at_the_desk([])["empty"], True)
print("the desk: reminded then a level up, each once; an approver away stood in for by a reliever who may sign")

# ── 2. cover ──────────────────────────────────────────────────────────
if set(R.PLANNED_LEAVE) != {L.ANNUAL, L.UNPAID}:
    fail.append("leave that can wait for cover is annual leave and leave without pay: %s" % (R.PLANNED_LEAVE,))
clash = [{"department": "Production"}]
for leave_type, clashes, blocks, want in (
    (L.ANNUAL, clash, 1, True), (L.UNPAID, clash, 1, True), (L.ANNUAL, clash, 0, False), (L.ANNUAL, [], 1, False),
    (L.SICK, clash, 1, False), (L.MATERNITY, clash, 1, False), (L.COMPASSIONATE, clash, 1, False),
):
    same("cover refuses %s (%s, blocks %s)" % (leave_type, bool(clashes), blocks),
         R.cover_refused(leave_type, clashes, blocks), want)
WHO = {"employee": "E1", "reliever": "E2", "reliever_name": "Ruth", "reliever_status": "Active", "days": 5}
expect("a reliever who can relieve", R.reliever_errors(WHO))
expect("no reliever, none asked for", R.reliever_errors({"employee": "E1", "days": 30}))
expect("no reliever on a leave that needs one", R.reliever_errors({"employee": "E1", "days": 3, "needed_from": 3}),
       "needs a reliever")
expect("a shorter leave does not", R.reliever_errors({"employee": "E1", "days": 2, "needed_from": 3}))
expect("relieving themselves", R.reliever_errors(dict(WHO, reliever="E1")), "Nobody relieves themselves")
expect("somebody who has left", R.reliever_errors(dict(WHO, reliever_status="Left")), "Ruth is not in service (Left)")
expect("somebody on leave too", R.reliever_errors(dict(WHO, reliever_away=True)), "Ruth is on leave in those days too")
print("cover: said always, refused only where Luuka say so and only leave that can wait; a reliever who can relieve")

# ── 3. after approval ─────────────────────────────────────────────────
if R.ENDED_EARLY != LA.ENDED_EARLY or set(R.CHANGE_KINDS) != set(R.ENDED_EARLY) | {R.EXTENSION}:
    fail.append("the rules and the workflow agree on how a leave ends early: %s / %s" % (R.ENDED_EARLY, LA.ENDED_EARLY))
for kind in R.ENDED_EARLY:
    if "'%s'" % kind not in LA.CHANGE_CONDITION:
        fail.append("the workflow's condition names %s" % kind)
LEAVE = {"docstatus": 1, "status": "Approved", "from_date": "2026-11-02", "to_date": "2026-11-22",
         "last_day": "2026-11-10", "kind": R.RECALLED, "reason": "The audit."}
expect("a recall", R.end_early_errors(LEAVE))
expect("an early return", R.end_early_errors(dict(LEAVE, kind=R.RETURNED)))
expect("on its first day", R.end_early_errors(dict(LEAVE, last_day="2026-11-02")))
expect("a draft", R.end_early_errors(dict(LEAVE, docstatus=0, status="Open")), "Only an approved leave")
expect("a refused one", R.end_early_errors(dict(LEAVE, status="Rejected")), "Only an approved leave")
expect("no kind", R.end_early_errors(dict(LEAVE, kind="Extension")), "recalled or came back early")
expect("no last day", R.end_early_errors(dict(LEAVE, last_day=None)), "Give the last day of leave taken")
expect("its own last day", R.end_early_errors(dict(LEAVE, last_day="2026-11-22")), "already ends on 22 Nov 2026")
expect("before it began", R.end_early_errors(dict(LEAVE, last_day="2026-11-01")), "cancelled, not ended early")
expect("no reason", R.end_early_errors(dict(LEAVE, reason="  ")), "Say why the leave ends early")
same("the days given back", R.given_back("2026-11-22", "2026-11-10"), (D(2026, 11, 11), D(2026, 11, 22)))
same("none given back", R.given_back("2026-11-22", "2026-11-22"), None)
expect("an extension", R.extension_errors(dict(LEAVE, new_to="2026-11-25")))
expect("to the same day", R.extension_errors(dict(LEAVE, new_to="2026-11-22")), "Give a later last day")
expect("with no reason", R.extension_errors(dict(LEAVE, new_to="2026-11-25", reason=None)), "Say why the leave is extended")
expect("of a leave not approved", R.extension_errors(dict(LEAVE, docstatus=0, new_to="2026-11-25")), "Only an approved leave")
same("an extension starts the day after", R.extension_window("2026-11-22", "2026-11-25"), (D(2026, 11, 23), D(2026, 11, 25)))
same("back on the first day at work after the last", R.back_on("2026-11-22", ["2026-11-20", "2026-11-25", D(2026, 11, 24)]),
     D(2026, 11, 24))
same("a day at work inside the leave is not a return", R.back_on("2026-11-22", ["2026-11-22"]), None)
for label, today, more, want in (
    ("the day due back", "2026-11-23", {}, 0), ("a day late", "2026-11-24", {}, 1), ("five days late", "2026-11-28", {}, 5),
    ("reported back", "2026-11-28", {"reported_back": True}, 0),
    ("an extension takes the day with it", "2026-11-28", {"extended_to": "2026-11-26"}, 1),
    ("not counted before the days in the settings", "2026-11-25", {"after_days": 3}, 0),
    ("counted from the day due once they pass", "2026-11-26", {"after_days": 3}, 3),
    ("switched off", "2026-11-28", {"after_days": 0}, 0),
):
    same("overdue: %s" % label, R.overdue_days("2026-11-22", today, **more), want)
print("after approval: ended early with the days given back, extended from the day after, overdue by the clock")

# ── 4. the glue, and the wiring ───────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "leave_follow.py")
leave = read("hrms_addon", "hrms_addon", "leave.py")
for needle, why in (
    ("due = rules.chase(since, today(), row.custom_chased, kept.remind_after_days, kept.escalate_after_days)",
     "what is due on a leave is the rules' answer"),
    ("since = row.custom_at_desk_since or getdate(row.modified)", "a leave from before the day was kept is still chased"),
    ('if due == rules.ESCALATED or found["empty"]', "the level above hears on escalation, or of an empty desk"),
    ('{"custom_chased": due, "custom_at_desk_since": since}', "and each step is kept, so it is said once"),
    ("found = rules.at_the_desk(users, dict(stand_ins_away, **away), able)", "who is asked is the rules' answer"),
    ("able = {user for user in stand_ins if signing & set(frappe.get_roles(user))}",
     "a stand-in is somebody who holds a role that signs at that desk"),
    ('add_docshare(APPLICATION, doc.name, user, write=1, submit=1, flags={"ignore_share_permission": True})',
     "a stand-in is given the leave to sign"),
    ('"custom_leave_status": ["in", list(approval.PENDING_STATES) + [approval.APPROVED]],',
     "who is off is leave approved and leave on a desk"),
    ("found = leave_rules.clashes(rows, limit)", "the cover is counted as the plan's clashes are"),
    ('"planned_from": max(getdate(row.from_date), first),', "on the days shared with this leave only"),
    ("if rules.cover_refused(doc.get(\"leave_type\"), found, kept.cover_blocks):", "refusing is the rules' answer"),
    ("errors += rules.reliever_errors({", "and so is who may relieve"),
    ("errors = rules.end_early_errors({", "ending early is judged by the rules"),
    ("    _only_hr()\n    doc = frappe.get_doc(APPLICATION, name)\n    errors = rules.end_early_errors(", "by HR only"),
    ("    doc.flags.ignore_links = True\n    doc.cancel()\n", "the first leave is cancelled, its records kept"),
    ("standing = apply_workflow(standing, approval.APPROVE_CHANGE)", "and the one that stands approved by the workflow"),
    ("for doctype, field in POINTING:", "what pointed at the first points at the one that stands"),
    ("_free_for_the_clock(doc.employee, first_back, last_back)", "the days given back are freed for the clock"),
    ('"skip_auto_attendance": 1, "attendance": ["is", "not set"],', "only punches set aside and never marked"),
    ("errors = rules.extension_errors({", "an extension is judged by the rules"),
    ('"custom_extends": doc.name,\n        "custom_change_kind": rules.EXTENSION,', "and is a leave that says what it extends"),
    ("back = rules.back_on(last, seen)", "who is back is the rules' reading of the clock"),
    ("overdue = rules.overdue_days(row.to_date, now, False, last, kept.overdue_after_days)", "and who is overdue"),
    ('"custom_reported_back": ["!=", 1]', "only a leave nobody is back from is watched"),
    ('values["custom_overstay_told"] = 1', "HR and the supervisor are told once"),
):
    if needle not in glue:
        fail.append("leave_follow.py: %s (%r not found)" % (why, needle))
for name in ("end_early", "extend"):
    if not re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef %s\(' % name, glue):
        fail.append("leave_follow.%s changes something: a whitelisted POST method" % name)
for needle, why in (
    ("    if doc.docstatus == 0:\n        # who else of the department is off the same days, for each desk to see\n"
     "        leave_follow.check_cover(doc)", "the cover is read on every save of a leave not yet decided"),
    ("rules.application_errors(_application_facts(doc)) + leave_follow.sending_errors(doc) + errors",
     "and judged as the leave is sent"),
    ("            leave_follow.arrived(doc, new_state)\n        else:\n            leave_follow.left_the_desk(doc)",
     "the desk reached is told, and the day kept"),
    ("        leave_follow.signed_as(doc)\n", "a leave ended early is signed as the first was"),
    ("    if doc.get(\"amended_from\") and doc.get(\"custom_change_kind\") in leave_follow.rules.ENDED_EARLY:\n"
     "        # a leave ended early keeps the advance and the reliever of the one first approved\n        return\n",
     "and raises no second advance"),
    ("    leave_follow.tell_reliever(doc)\n", "the reliever is told on approval"),
    ("for watch in (leave_follow.chase_approvals, leave_follow.watch_returns):", "both watches run daily"),
    ('"amended_from": doc.get("amended_from"), "change_kind": doc.get("custom_change_kind"),',
     "the step is told what the application is"),
):
    if needle not in leave:
        fail.append("leave.py: %s (%r not found)" % (why, needle))
if "def _tell_application(" in leave or "def _ask_report_back(" in leave:
    fail.append("leave.py no longer tells the desk or asks after returns itself: leave_follow does")

settings = json.loads(read("hrms_addon", "hrms_addon", "doctype", "leave_management_settings",
                           "leave_management_settings.json"))
kept = {f["fieldname"]: f for f in settings["fields"]}
for key, default in R.DEFAULTS.items():
    spec = kept.get(key) or {}
    if spec.get("fieldtype") not in ("Int", "Check"):
        fail.append("Leave Management Settings has no %s" % key)
    elif default and str(spec.get("default")) != str(default):
        fail.append("Leave Management Settings.%s opens at %s, the rules' default" % (key, default))
if "leave_follow.settings_errors(doc)" not in read("hrms_addon", "hrms_addon", "leave_accrual.py"):
    fail.append("the settings are checked as they are saved")

custom = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
hooks = read("hrms_addon", "hooks.py")
FIELDS = {"custom_reliever": "Link", "custom_handover": "Small Text", "custom_cover": "Small Text",
          "custom_overstay_days": "Int", "custom_change_kind": "Select", "custom_change_reason": "Small Text",
          "custom_first_approved_to": "Date", "custom_extends": "Link", "custom_at_desk_since": "Date",
          "custom_chased": "Data", "custom_overstay_told": "Check"}
for fieldname, fieldtype in FIELDS.items():
    row = custom.get("Leave Application-%s" % fieldname) or {}
    if row.get("fieldtype") != fieldtype or '"Leave Application-%s",' % fieldname not in hooks:
        fail.append("Leave Application.%s is a %s field, synced with the fixtures" % (fieldname, fieldtype))
    if fieldname not in ("custom_reliever", "custom_handover") and not row.get("read_only"):
        fail.append("Leave Application.%s is the system's to fill, and read only" % fieldname)
if (custom.get("Leave Application-custom_change_kind") or {}).get("options", "").split("\n")[1:] != list(R.CHANGE_KINDS):
    fail.append("the Change field offers what the rules know: %s" % (R.CHANGE_KINDS,))
after = [row.get("insert_after") for row in custom.values() if row.get("dt") == "Leave Application"]
if len(after) != len(set(after)):
    fail.append("two Leave Application fields sit after the same one: their order would be the database's")
for fieldname in sorted(set(re.findall(r"\bcustom_\w+", glue))):
    if "Leave Application-%s" % fieldname not in custom:
        fail.append("leave_follow.py reads or writes %s, which the leave form does not have" % fieldname)

form = read("hrms_addon", "public", "js", "leave_application.js")
for needle, why in (
    ('"hrms_addon.hrms_addon.leave_follow.end_early"', "End Early"), ('"hrms_addon.hrms_addon.leave_follow.extend"', "Extend"),
    ('frappe.user.has_role(["HR User", "HR Manager"])', "End Early is HR's"),
    ('options: ["Returned Early", "Recalled"],', "it asks which"),
    ("frappe.utils.escape_html(frm.doc.custom_cover)", "the cover is shown, escaped"),
    ("frm.doc.custom_overstay_days && !frm.doc.custom_reported_back", "and who is overdue"),
):
    if needle not in form:
        fail.append("leave_application.js: %s (%r not found)" % (why, needle))
tree = ast.parse(read("hrms_addon", "hooks.py"))
if "hrms_addon.hrms_addon.leave.daily" not in hooks:
    fail.append("the leave watches run from the daily job")
print("glue and wiring: the rules followed, the settings, the fields, the form and the daily watches")

print()
if fail:
    print("FAILURES:")
    for message in fail:
        print("  -", message)
    sys.exit(1)
print("ALL LEAVE FOLLOW CHECKS PASSED")
