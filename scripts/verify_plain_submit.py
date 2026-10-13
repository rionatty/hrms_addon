"""Checks that a document one of the app's workflows approves cannot be
submitted past its approval steps, without a bench.

    python scripts/verify_plain_submit.py

  1  the rules (workflow_rules.py): which states submit, and when a submit
     skips the steps before them
  2  every workflow the app builds: none opens on a state that submits, so
     a plain submit of a new document is always one that skips
  3  the hook: before_submit on every document, answering for the app's own
     workflows and nobody else's
  4  Frappe's own order on a submit, read from its source beside the app,
     which is why the hook is before_submit and why validate cannot do this
  5  the app's own submits of such documents set the state first

The rules are loaded without Frappe.
"""
import glob
import importlib.util
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)


def read(*parts):
    return io.open(os.path.join(*parts), encoding="utf-8").read()


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


R = load(os.path.join(APP, "workflow_rules.py"))
print("loaded workflow_rules.py without Frappe")

# ── 1. The rules ────────────────────────────────────────────────────────
STATES = [{"state": "Draft"}, {"state": "Pending", "doc_status": "0"}, {"state": "Approved", "doc_status": "1"},
          {"state": "Rejected", "doc_status": 1}, {"state": "Cancelled", "doc_status": "2"}]
check(R.submitting_states(STATES) == ["Approved", "Rejected"] and R.submitting_states(None) == [],
      "the states that submit are those with doc_status 1, written as text or as a number: %s" % R.submitting_states(STATES))
for state, skips in (("Draft", True), ("Pending", True), (None, True), ("", True), ("Cancelled", True),
                     ("Approved", False), ("Rejected", False)):
    check(R.skips_approval(STATES, state) is skips,
          "a submit at %r %s the approval" % (state, "skips" if skips else "is the end of"))
check(R.skips_approval([{"state": "Draft"}, {"state": "Reviewed", "doc_status": "0"}], "Draft") is False,
      "a workflow with no state that submits only follows a document submitted the ordinary way")
print("rules: a submit is the end of an approval only at a state that submits")

# ── 2. Every workflow the app builds ────────────────────────────────────
approvals = [load(path) for path in sorted(glob.glob(os.path.join(APP, "*_approval.py")))]
check(len(approvals) >= 35 and all(getattr(module, name, None) for module in approvals
                                   for name in ("DOCTYPE", "WORKFLOW_NAME", "STATE_FIELD", "STATES")),
      "every *_approval module declares its doctype, workflow, state field and states (%d found)" % len(approvals))
check(len({module.WORKFLOW_NAME for module in approvals}) == len(approvals)
      and len({module.DOCTYPE for module in approvals}) == len(approvals),
      "one workflow a doctype, each under its own name")
by_step = [module for module in approvals if R.submitting_states(module.STATES)]
for module in by_step:
    first = module.STATES[0]["state"]
    check(R.skips_approval(module.STATES, first) and R.skips_approval(module.STATES, None),
          "%s opens on a state that does not submit, so a plain submit of a new one skips its approval"
          % module.WORKFLOW_NAME)
check(len(by_step) >= 30 and {"Clearance Form", "Overtime Request", "Leave Application", "Employee Loan"}
      <= {module.WORKFLOW_NAME for module in by_step},
      "nearly all of them submit their document by a step: %d of %d" % (len(by_step), len(approvals)))
print("workflows: %d of %d submit their document by a step, none opens on a state that submits"
      % (len(by_step), len(approvals)))

# ── 3. The hook ─────────────────────────────────────────────────────────
scope = {}
exec(compile(read(REPO, "hrms_addon", "hooks.py"), "hooks.py", "exec"), scope)
every = scope["doc_events"]["*"]
check(every.get("before_submit") == "hrms_addon.hrms_addon.workflows.refuse_plain_submit",
      "the hook is on before_submit of every document: %s" % every.get("before_submit"))
check("validate" not in every, "and nothing is hung on every document's validate")
glue = read(APP, "workflows.py")
guard = glue.split("def refuse_plain_submit(")[1].split("\ndef ")[0]
check("name = frappe_workflow.get_workflow_name(doc.doctype)" in guard
      and "if not name or name not in ours():\n        return" in guard,
      "it answers only for a doctype whose active workflow is one of the app's own")
check('workflow = frappe.get_cached_doc("Workflow", name)' in guard
      and '[{"state": row.state, "doc_status": row.doc_status} for row in workflow.states]' in guard
      and "workflow_rules.skips_approval(states, doc.get(workflow.workflow_state_field))" in guard,
      "it reads the states from the Workflow as the site holds it, a desk-managed one included, and the state the "
      "document stands at")
check("frappe.throw(" in guard and "It cannot be submitted directly." in guard and "msgprint" not in guard,
      "and refuses: it does not warn")
names = glue.split("def ours(")[1].split("\ndef ")[0]
check('found.name.endswith("_approval")' in names and "rules.WORKFLOW_NAME" in names
      and re.search(r"except Exception:\n(\s+#.*\n)*\s+frappe\.log_error\(.*\n\s+continue", names),
      "the app's own workflows are its *_approval modules, and one that cannot be read is logged, not left to stop "
      "every submit on the site")
print("hook: before_submit on every document, for the app's own workflows")

# ── 4. Frappe's own order on a submit ───────────────────────────────────
document_path = os.path.join(APPS_ROOT, "frappe", "frappe", "model", "document.py")
workflow_path = os.path.join(APPS_ROOT, "frappe", "frappe", "model", "workflow.py")
check(os.path.exists(document_path) and os.path.exists(workflow_path),
      "Frappe's source is beside the app (FRAPPE_APPS_ROOT, here %s)" % APPS_ROOT)
if os.path.exists(document_path) and os.path.exists(workflow_path):
    document, workflow = read(document_path), read(workflow_path)
    save = document.split("\tdef _save(")[1].split("\n\tdef ")[0]
    check("self.run_before_save_methods()" in save and "self._validate()" in save
          and save.index("self.run_before_save_methods()") < save.index("self._validate()"),
          "Frappe runs a document's own validate and before_submit first, and only then its own checks")
    before = document.split("\tdef run_before_save_methods(")[1].split("\n\tdef ")[0]
    check(re.search(r'elif self\._action == "submit":\s+self\.run_method\("validate"\)\s+self\.run_method\("before_submit"\)',
                    before), "on a submit that is validate, then before_submit")
    own = document.split("\tdef _validate(")[1].split("\n\tdef ")[0]
    check("self.validate_workflow()" in own, "its own checks end with the workflow")
    moved = document.split("\tdef validate_workflow(")[1].split("\n\tdef ")[0]
    check(re.search(r'if self\._action != "save":\s+set_workflow_state_on_action\(self, workflow, self\._action\)', moved),
          "where a document submitted without a step is handed to set_workflow_state_on_action")
    sets = workflow.split("def set_workflow_state_on_action(")[1].split("\ndef ")[0]
    check(re.search(r"if state\.doc_status == docstatus:\s+doc\.set\(workflow_state_field, state\.state\)\s+return", sets),
          "which moves it to the first state that submits, after validate has run: so validate cannot see it, "
          "and before_submit still reads the state the document stood at")
    step = workflow.split("def apply_workflow(")[1].split("\ndef ")[0]
    check("doc.set(workflow.workflow_state_field, transition.next_state)" in step and "doc.submit()" in step
          and step.index("doc.set(workflow.workflow_state_field, transition.next_state)") < step.index("doc.submit()"),
          "a step sets its state before it submits, so the hook lets it through")
print("frappe: validate and before_submit, then the workflow's own move to the first state that submits")

# ── 5. The app's own submits ────────────────────────────────────────────
run = read(APP, "salary_advances.py")
check("        advance.workflow_state = approval.PAID\n        advance.submit()" in run,
      "a Salary Advance Processing writes its advances as Paid, then submits them")
board = read(APP, "talent_board.py").split("def advance(")[1] if "def advance(" in read(APP, "talent_board.py") else read(
    APP, "talent_board.py")
check("doc.workflow_state = allowed[action]" in board and "doc.submit()" in board
      and board.index("doc.workflow_state = allowed[action]") < board.index("doc.submit()"),
      "the Talent Board sets a placement's state, then submits it")
print("own submits: the state first")

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL PLAIN SUBMIT CHECKS PASSED")
