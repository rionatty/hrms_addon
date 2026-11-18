"""Verify talent's bulk steps in the background and the one digest each
person gets (talent_jobs_rules.py, talent_jobs.py), without a bench:

    python scripts/verify_talent_jobs.py

Luuka have more than 2,000 people in three plants: a step over a whole
review (drafting the placements, sending them to the council, finalising
them with their programmes and requisitions, a succession plan moving its
roles, a calibration session applied) runs on the long queue, one at a
time for a document, each item in a savepoint of its own and committed in
chunks, its progress and what it left kept on a Talent Job Log; what it
tells people goes once a person at the end, never once a document; and
the placement's workflow emails nobody a placement at a time.
"""
import ast
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
fail = []


def check(label, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else "   -> %r" % (detail,)))
    if not ok:
        fail.append(label)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def body_of(source, name):
    return source.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0] if "def %s(" % name in source else ""


J = load("talent_jobs_rules")
print("loaded talent_jobs_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
check("committed in chunks of 100 to 200", 100 <= J.CHUNK <= 200)
check("chunks", J.chunks(list(range(5)), 2) == [[0, 1], [2, 3], [4]] and J.chunks([], 2) == []
      and len(J.chunks(list(range(2000)))) == -(-2000 // J.CHUNK))
check("one job of a kind for a document", J.job_id("advance", "TR-1") == "hrms_addon_talent::advance::TR-1"
      and J.job_id("advance", "TR-1") != J.job_id("draft", "TR-1"))
check("progress out of a hundred", J.progress(50, 200) == 25.0 and J.progress(0, 0) == 100.0)
check("a step's end: done, done with problems, failed",
      (J.status(10, 0), J.status(10, 2), J.status(0, 0, failed=True)) == (J.DONE, J.PROBLEMS, J.FAILED))
check("the log's one line", J.summary("advance", 1980, 20, 2000)
      == "Placements Moved On: 1980 of 2000 done, 20 left with a reason." and "nothing to do" in J.summary("draft", 0, 0, 0))
entries = [("hr@x", "Requisition for Ann", "Training Requisition", "TR-1"),
           ("hr@x", "Requisition for Ben", "Training Requisition", "TR-2"),
           ("hr@x", "Requisition for Ann", "Training Requisition", "TR-1"),
           ("council@x", "Ann at flight risk", "Talent Placement", "TP-1"), (None, "x", "y", "z")]
found = J.digest(entries, limit=1)
check("one digest a person, each line once, the first few and how many more",
      set(found) == {"hr@x", "council@x"} and found["hr@x"]["count"] == 2 and found["hr@x"]["more"] == 1
      and len(found["hr@x"]["lines"]) == 1 and found["council@x"]["count"] == 1)
check("the digest's subject", J.digest_subject("advance", "Talent Review 2026", 2)
      == "Placements Moved On, Talent Review 2026: 2 items for you")

# ── 2. The log ────────────────────────────────────────────────────────
folder = os.path.join(APP, "doctype", "talent_job_log")
log = json.load(open(os.path.join(folder, "talent_job_log.json"), encoding="utf-8"))
log_fields = {row["fieldname"]: row for row in log["fields"]}
check("a job's log: the job, its document, status, who started it and when, progress, what it left",
      {"job", "job_id", "reference_doctype", "reference_name", "status", "started_by", "started_on", "finished_on",
       "total", "done", "left_count", "progress", "summary", "lines"} <= set(log_fields)
      and log_fields["lines"]["options"] == "Talent Job Line"
      and log_fields["status"]["options"].split("\n") == list(J.STATUSES) and log_fields["job_id"].get("search_index"))
check("nobody types a log", not any(row.get("write") or row.get("create") for row in log["permissions"]))

# ── 3. The glue ───────────────────────────────────────────────────────
GLUE = read("hrms_addon", "hrms_addon", "talent_jobs.py")
check("queued on the long queue, deduplicated, after the request commits",
      all(needle in body_of(GLUE, "start") for needle in ('queue="long"', "deduplicate=True", "job_id=job_id",
                                                          "enqueue_after_commit=True")))
check("a step of the same kind still running is refused", "rules.LIVE" in body_of(GLUE, "start"))
each = GLUE.split("    def each(", 1)[1].split("\n    def ", 1)[0]
check("each item in a savepoint of its own, committed chunk by chunk, its progress published",
      "frappe.db.savepoint(savepoint)" in each and "frappe.db.rollback(save_point=savepoint)" in each
      and "rules.chunks(names)" in each and "frappe.db.commit()" in each and "self.progress()" in each)
check("the progress reaches whoever started it", "frappe.publish_realtime(EVENT" in GLUE)
check("what a step tells is gathered while it runs and sent once a person",
      "entries.extend(" in body_of(GLUE, "tell") and "people.notify(users" in body_of(GLUE, "tell")
      and "rules.digest(entries)" in body_of(GLUE, "flush") and "flush(context)" in body_of(GLUE, "run"))
check("a ToDo put quietly while a step runs: the digest is the one message",
      '"doctype": "ToDo"' in body_of(GLUE, "assign") and "people.assign(" in body_of(GLUE, "assign"))

STEPS = {
    "talent.py": ("draft_placements", 'talent_jobs.start("draft"'),
    "talent_board.py": ("advance", 'talent_jobs.start("advance"'),
    "succession_plans.py": ("plan_on_submit", 'talent_jobs.start("plan_finalise"'),
    "calibration.py": ("session_on_submit", 'talent_jobs.start("calibration"'),
}
for module, (function, needle) in STEPS.items():
    check("%s.%s runs in the background" % (module[:-3], function),
          needle in body_of(read("hrms_addon", "hrms_addon", module), function))
check("the succession plan sent to the council in the background too",
      'talent_jobs.start("plan_send"' in body_of(read("hrms_addon", "hrms_addon", "succession_plans.py"), "plan_on_update"))
TALENT = read("hrms_addon", "hrms_addon", "talent.py")
check("finalising tells HR of each programme's training through the digest",
      "talent_jobs.tell(" in body_of(TALENT, "_ask_hr_to_submit") and "talent_jobs.assign(" in body_of(TALENT, "_ask_hr_to_submit"))
check("the flight risk alert and the trainees' due milestones go through the digest",
      "talent_jobs.tell(" in body_of(TALENT, "_flag_flight_risk") and "talent_jobs.send_digest(" in body_of(TALENT, "_watch_top_talent")
      and "talent_jobs.send_digest(" in body_of(TALENT, "_raise_due_milestones")
      and "talent_jobs.send_digest(" in body_of(TALENT, "_chase_milestones"))
check("a placement coming into calibration is HR's, told once a day", "if state == approval.CALIBRATION:\n        return"
      in body_of(TALENT, "_tell_placement") and "calibration_digest()" in body_of(TALENT, "daily"))

# ── 4. No email a placement ───────────────────────────────────────────
P = load("talent_approval")
S = load("succession_approval")
check("the placement's workflow emails nobody a placement at a time",
      P.SEND_EMAIL_ALERT == 0 and not any(row.get("send_email") for row in P.STATES))
check("in calibration a placement waits for HR, who alone move it on",
      P.ROLE_WAITING[P.CALIBRATION] == P.HR_OFFICER
      and {row["allowed"] for row in P.TRANSITIONS if row["state"] == P.CALIBRATION} <= set(P.HR))
check("a succession plan's roles move without Frappe's email", S.SEND_EMAIL_ALERT == 0)
WORKFLOWS = read("hrms_addon", "hrms_addon", "workflows.py")
check("workflows.py honours a module's email switch, one by default",
      'workflow.send_email_alert = int(getattr(rules, "SEND_EMAIL_ALERT", 1))' in WORKFLOWS
      and 'int(getattr(rules, "SEND_EMAIL_ALERT", 1))' in body_of(WORKFLOWS, "_ensure_workflow"))

# ── 5. The indexes a review is read by ────────────────────────────────
check("the placements indexed by review and step, and by employee and status",
      '(PLACEMENT, ["talent_review", "workflow_state"])' in TALENT and '(PLACEMENT, ["employee", "docstatus"])' in TALENT
      and '("Succession Candidate", ["employee"])' in TALENT and '("Trainee Milestone", ["appraisal"])' in TALENT)
check("added on the doctype's update and by a patch, each once",
      "talent.add_indexes()" in read("hrms_addon", "hrms_addon", "doctype", "talent_placement", "talent_placement.py")
      and "talent_indexes" in read("hrms_addon", "patches.txt") and "frappe.db.add_index(" in body_of(TALENT, "add_indexes"))

if fail:
    print("FAIL (%d):" % len(fail))
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_talent_jobs: OK")
