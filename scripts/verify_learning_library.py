"""Verify the learning library (the LMS rebuild, item 11, 18 Nov 2026), without a bench:

    python scripts/verify_learning_library.py
"""
import importlib.util
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
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def doctype(name):
    folder = name.lower().replace(" ", "_")
    return json.load(open(os.path.join(APP, "doctype", folder, folder + ".json"), encoding="utf-8"))


def fields(name):
    return {field["fieldname"]: field for field in doctype(name)["fields"]}


def check(label, ok, detail=""):
    if not ok:
        fail.append("%s%s" % (label, (": %s" % (detail,)) if detail != "" else ""))


R = load("learning_library_rules")
Q = {"question": "Which colour is the fire exit sign?", "options": "Red\nGreen\nBlue", "answer": "Green", "marks": 2}
check("an answer counts by its text, its letter or its number, in any case",
      R.right(Q, "green") and R.right(Q, "B") and R.right(Q, "2") and not R.right(Q, "A") and not R.right(Q, ""))
check("an answer written as a letter matches the option's text", R.right(dict(Q, answer="b"), "Green"))
check("a quiz scored by marks", R.score([dict(Q, name="q1"), {"name": "q2", "question": "PPE?", "answer": "yes"}],
                                        {"q1": "B", "q2": "No"}) == (66.7, 2.0, 3.0, ["PPE?"]))
check("passed at the pass mark", R.after_attempt(70, 70) == R.PASSED and R.after_attempt(69.9, 70) == R.FAILED
      and R.after_attempt(50, 0) == R.FAILED)
check("a quiz refuses a question without an answer, or an answer not among the options",
      R.quiz_errors([{"question": "x", "answer": ""}]) and R.quiz_errors([dict(Q, answer="Purple")])
      and not R.quiz_errors([Q]))
check("content refused: an unknown type, a quiz without questions, a link without its address, a document with nothing",
      R.content_errors({"content_type": "Poster"}) and R.content_errors({"content_type": "Quiz"})
      == ["A quiz needs its questions."] and R.content_errors({"content_type": "Link"})
      and R.content_errors({"content_type": "SOP"}) and not R.content_errors({"content_type": "SOP", "file": "/f.pdf"}))
check("a new version when the file, the address, the text or the questions change",
      R.new_version({"file": "a.pdf"}, {"file": "b.pdf"}) and not R.new_version({"file": "a.pdf"}, {"file": "a.pdf"})
      and R.new_version({"questions": [Q]}, {"questions": [dict(Q, answer="Red")]})
      and not R.new_version(None, {"file": "b.pdf"}))
check("acknowledging completes content that asks for it; a quiz only by passing",
      R.completes("SOP", 1, True) and not R.completes("SOP", 1, False) and R.completes("Video", 0, False)
      and not R.completes("Quiz", 0, True))
check("the acknowledgement figures", R.acknowledgement_figures(
    [{"status": "Completed"}, {"status": "Assigned", "due_date": "2026-11-01"}, {"status": "Assigned"},
     {"status": "Withdrawn"}], "2026-11-18") == {"assigned": 3, "done": 1, "pending": 2, "overdue": 1, "share": 33.3})

content, assignment = fields("Learning Content"), fields("Learning Content Assignment")
options = lambda spec, field: [value for value in spec[field]["options"].split("\n") if value]  # noqa: E731
check("content: its type, category, training, skill, version, file or address, owner, active, its questions and history",
      {"content_type", "training_category", "training_program", "skill", "version", "file", "url", "body",
       "content_owner", "is_active", "needs_acknowledgement", "questions", "pass_mark", "versions"} <= set(content)
      and options(content, "content_type") == list(R.CONTENT_TYPES))
check("a question: its text, options, answer and marks", {"question", "options", "answer", "marks"}
      <= set(fields("Learning Quiz Question")))
check("an assignment: status, score, attempts, acknowledged, its attempts kept",
      {"status", "score", "best_score", "attempts", "acknowledged_on", "completed_on", "attempt_log", "version",
       "training_program", "branch", "work_section"} <= set(assignment)
      and options(assignment, "status") == list(R.STATUSES))
check("assignments are named LCA-, which the requirements read as their proof",
      doctype("Learning Content Assignment")["autoname"].startswith("LCA-")
      and 'CONTENT_ASSIGNMENT, CONTENT_PREFIX = "Learning Content Assignment", "LCA-"' in read(
          "hrms_addon", "hrms_addon", "learning.py"))
LEARNING = read("hrms_addon", "hrms_addon", "learning.py")
check("content completed or a quiz passed counts for its training's requirement",
      "_content_done(employees)" in LEARNING and 'CONTENT_DONE = ("Completed", "Passed")' in LEARNING)
check("one assignment per employee and content", '"Learning Content Assignment": ("learning_content", "employee")'
      in LEARNING)
GLUE = read("hrms_addon", "hrms_addon", "learning_library.py")
check("no SQL of its own", "frappe.db.sql" not in GLUE)
check("assigned in the background, a hundred at a time, each person told once",
      'queue="long"' in GLUE and "for start in range(0, len(fresh), PART):" in GLUE and "_tell(fresh, content" in GLUE)
check("assigned by a rule's reach, a plant, section or department, or a list",
      "learning_rules.in_scope(rule, person)" in GLUE and '"custom_work_section", work_section' in GLUE)
check("a new version reopens what was done before it, in the background", "def reopen(content, version):" in GLUE
      and '"version": ["<", cint(version)]' in GLUE)
check("the quiz never sends its answers", '"question", "options", "marks"' in GLUE
      and re.search(r"def quiz\(assignment\):.*?fields=\[\"name\", \"question\", \"options\", \"marks\"\]", GLUE, re.S))
check("only the employee or HR take their quiz or acknowledge", "def _mine(assignment):" in GLUE
      and GLUE.count("_mine(assignment)") >= 4)
for name in ("assign", "start", "acknowledge", "quiz", "submit_quiz"):
    check("%s is whitelisted" % name, re.search(r"@frappe\.whitelist\([^)]*\)\ndef %s\(" % name, GLUE))
check("acknowledgement counted by the database", 'group_by="%s, status" % by' in GLUE)
HOOKS = read("hrms_addon", "hooks.py")
check("hooks: an employee lists their own", '"Learning Content Assignment": "hrms_addon.hrms_addon.learning_library.'
      'assignment_query"' in HOOKS)
check("the quiz and acknowledgement helpers ship with the desk", "hrms_addon.take_quiz" in read(
    "hrms_addon", "public", "js", "hrms_addon_learning.js"))
NAV = read("hrms_addon", "hrms_addon", "navigation_rules.py")
for entry in ("Learning Content", "Learning Content Assignment", "SOP Acknowledgement"):
    check("the menus name %s, on the card and in the sidebar" % entry, NAV.count('("%s", ' % entry) >= 2)

if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("verify_learning_library: OK")
