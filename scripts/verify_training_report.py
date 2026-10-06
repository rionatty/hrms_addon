"""Checks for the Training Report (Training, case 10), run without a bench.

training_rules.py imports nothing from Frappe, so the report's arithmetic is
walked on one worked example: a training held with someone absent and
someone never marked, three evaluation forms (one with nothing rated), the
marks of two of them and a blank one, a training still to come and one
called off. Each view is checked against it, then one department's view of
it, the figures on top and the charts.

It also checks the Script Report itself (its record, that every column of
every view is in the rows the rules give, the filters its script declares
and reads, what it reads and from where), that the evaluation form is
scored the same way on the training and in the report, where HR finds it,
and against Frappe HR (../ERPNext, or FRAPPE_APPS_ROOT) the fields it reads.

    python scripts/verify_training_report.py
"""
import datetime
import importlib.util
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
UPSTREAM_OK = os.path.isdir(APPS_ROOT)
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def check(label, got, want):
    if got != want:
        fail.append("%s: got %r, want %r" % (label, got, want))


R = load("training_rules")
print("loaded training_rules.py without Frappe")

# ── 1. One worked example ─────────────────────────────────────────────
I1, I2, I3, I4 = "Course content", "Course relevance", "Trainer knowledge", "Venue"
ORDER = (I1, I2, I3, I4)
D = datetime.datetime
events = [
    {"name": "Fire Safety - 2026-03-10", "training_program": "Fire Safety", "branch": "Namanve", "department": "Production",
     "start": D(2026, 3, 10, 7), "end": D(2026, 3, 10, 9), "trainer": "A. Okello", "docstatus": 1, "event_status": "Scheduled"},
    {"name": "Forklift - 2026-11-04", "training_program": "Forklift", "branch": "Namanve", "department": "Stores",
     "start": D(2026, 11, 4, 7), "end": D(2026, 11, 5, 9), "trainer": None, "docstatus": 0, "event_status": "Scheduled"},
    {"name": "First Aid - 2026-05-02", "training_program": "First Aid", "branch": "Kawempe", "department": None,
     "start": "2026-05-02 07:00:00", "end": None, "trainer": None, "docstatus": 0, "event_status": "Cancelled"},
]
FIRE, FORK, AID = (event["name"] for event in events)
participants = [
    {"training_event": FIRE, "employee": "E1", "employee_name": "Alice", "department": "Production", "attendance": "Present"},
    {"training_event": FIRE, "employee": "E2", "employee_name": "Daniel", "department": "Production", "attendance": "Absent"},
    {"training_event": FIRE, "employee": "E3", "employee_name": "Brian", "department": "Stores", "attendance": "Present"},
    {"training_event": FIRE, "employee": "E4", "employee_name": "Carol", "department": "Stores", "attendance": None},
    {"training_event": FORK, "employee": "E1", "employee_name": "Alice", "department": "Production", "attendance": None},
    {"training_event": FORK, "employee": "E5", "employee_name": "Eve", "department": "Production", "attendance": None},
]
evaluations = [
    # keyed in out of name order: the comments still come by name
    {"name": "TF-2", "training_event": FIRE, "employee": "E3", "employee_name": "Brian",
     "items": {I1: "Good", I2: "Below Average", I3: "Average", "Handouts": "Good", "Ignored": "Fair"},
     "comments": {I2: "Too fast", "Handouts": "Too few"},
     "answers": {"learnt": "The PASS method", "expectations": "Know the alarms"}},
    {"name": "TF-1", "training_event": FIRE, "employee": "E1", "employee_name": "Alice",
     "items": {I1: "Excellent", I2: "Very Good"}, "comments": {},
     "answers": {"expectations": "Learn the extinguishers", "learnt": "  "}},
    {"name": "TF-3", "training_event": FIRE, "employee": "E4", "employee_name": "Carol",
     "items": {}, "comments": {}, "answers": {"hr_recommendations": "More time for questions"}},
]
for form in evaluations:
    form["score"] = R.score(list(form["items"].values()))
results = [
    {"training_event": FIRE, "employee": "E1", "marks": 80.0, "effective": "Effective"},
    {"training_event": FIRE, "employee": "E3", "marks": 45.0, "effective": "Not Effective"},
    # a mark never given: Frappe keeps it as 0, with no verdict
    {"training_event": FIRE, "employee": "E4", "marks": 0.0, "effective": None},
]
check("an evaluation with nothing rated has no score", evaluations[2]["score"], None)
check("an evaluation scored from its ratings", [evaluations[1]["score"], evaluations[0]["score"]], [90.0, 45.0])

check("held once submitted", R.training_status(1, "Scheduled"), R.HELD)
check("still to come while a draft", R.training_status(0, "Scheduled"), R.SCHEDULED)
check("called off", [R.training_status(0, "Cancelled"), R.training_status(1, "Cancelled")], [R.CANCELLED] * 2)

rows = R.training_rows(events, participants, evaluations, results)
fire, fork, aid = rows
check("one row per training, in the order given", [row["training_event"] for row in rows], [FIRE, FORK, AID])
check("the held training", {key: fire[key] for key in (
    "status", "participants", "present", "absent", "attendance_rate", "evaluations", "evaluation_score", "rating",
    "assessed", "average_marks", "effective", "effectiveness", "from_date", "to_date", "trainer", "training_program")},
    {"status": "Held", "participants": 4, "present": 2, "absent": 1, "attendance_rate": 50.0, "evaluations": 3,
     "evaluation_score": 67.5, "rating": "Good", "assessed": 2, "average_marks": 62.5, "effective": 1,
     "effectiveness": 50.0, "from_date": datetime.date(2026, 3, 10), "to_date": datetime.date(2026, 3, 10),
     "trainer": "A. Okello", "training_program": "Fire Safety"})
check("a training still to come has no attendance yet", (fork["status"], fork["participants"], fork["attendance_rate"],
                                                         fork["evaluations"], fork["evaluation_score"], fork["rating"],
                                                         fork["assessed"], fork["effectiveness"], fork["to_date"]),
      ("Scheduled", 2, None, 0, None, None, 0, None, datetime.date(2026, 11, 5)))
check("a training called off", (aid["status"], aid["participants"], aid["from_date"], aid["to_date"]),
      ("Cancelled", 0, datetime.date(2026, 5, 2), None))

people = R.participant_rows(events, participants, evaluations, results)
check("a row per person booked, training by training", [(row["training_event"], row["employee"]) for row in people],
      [(FIRE, "E1"), (FIRE, "E2"), (FIRE, "E3"), (FIRE, "E4"), (FORK, "E1"), (FORK, "E5")])
check("attendance, a blank as Not Marked", [row["attendance"] for row in people],
      ["Present", "Absent", "Present", "Not Marked", "Not Marked", "Not Marked"])
check("each person's evaluation and how it reads", [(row["training_feedback"], row["evaluation_score"], row["rating"])
                                                   for row in people[:4]],
      [("TF-1", 90.0, "Excellent"), (None, None, None), ("TF-2", 45.0, "Below Average"), ("TF-3", None, None)])
check("each person's result; a mark never given shows nothing", [(row["marks"], row["result"]) for row in people[:4]],
      [(80.0, "Effective"), (None, None), (45.0, "Not Effective"), (None, None)])
check("the same evaluation on another training is not theirs", (people[4]["training_feedback"], people[4]["marks"]),
      (None, None))

items = R.item_rows(evaluations, ORDER)
check("the items in the form's order, any other after them, then the overall",
      [row["item"] for row in items], [I1, I2, I3, "Handouts", "Overall"])
by_item = {row["item"]: row for row in items}
check("an item's ratings, how many rated it, its score", {key: by_item[I1][key] for key in (
    "rated_excellent", "rated_very_good", "rated_good", "rated_average", "rated_below_average", "responses", "score", "rating")},
    {"rated_excellent": 1, "rated_very_good": 0, "rated_good": 1, "rated_average": 0, "rated_below_average": 0,
     "responses": 2, "score": 80.0, "rating": "Very Good"})
check("an item rated low", (by_item[I2]["score"], by_item[I2]["rating"], by_item[I3]["score"], by_item[I3]["rating"]),
      (50.0, "Average", 40.0, "Below Average"))
check("a rating off the form's scale is left out", by_item["Handouts"]["responses"], 1)
overall = by_item["Overall"]
check("the overall: every rating given, every form, the training's own score",
      (overall["rated_excellent"], overall["rated_very_good"], overall["rated_good"], overall["rated_average"],
       overall["rated_below_average"], overall["responses"], overall["score"], overall["rating"]),
      (1, 1, 2, 1, 1, 3, 67.5, "Good"))
check("no evaluations, no rows", R.item_rows([], ORDER), [])

QUESTIONS = [(field, "%d. %s" % (number, field)) for number, (field, _question) in enumerate(R.QUESTIONS, 1)]
said = R.comment_rows(events, evaluations, QUESTIONS, ORDER)
check("the comments as the form runs: items first, then each question, everyone's answer by name",
      [(row["employee_name"], row["question"], row["answer"]) for row in said],
      [("Brian", I2, "Too fast"), ("Brian", "Handouts", "Too few"),
       ("Alice", "1. expectations", "Learn the extinguishers"), ("Brian", "1. expectations", "Know the alarms"),
       ("Brian", "2. learnt", "The PASS method"),
       ("Carol", "6. hr_recommendations", "More time for questions")])
check("every comment names its training", {row["training_event"] for row in said}, {FIRE})

# ── 2. One department's people ───────────────────────────────────────
n_events, n_people, n_forms, n_results = R.narrow(events, participants, evaluations, results, "Stores")
check("a department: the trainings its people were booked on", [event["name"] for event in n_events], [FIRE])
check("a department: its people only", [row["employee"] for row in n_people], ["E3", "E4"])
check("a department: their evaluations and results only", ([form["name"] for form in n_forms],
                                                            [row["employee"] for row in n_results]),
      (["TF-2", "TF-3"], ["E3", "E4"]))
stores = R.training_rows(n_events, n_people, n_forms, n_results)[0]
check("a department's figures", (stores["participants"], stores["present"], stores["attendance_rate"],
                                 stores["evaluations"], stores["evaluation_score"], stores["assessed"],
                                 stores["effectiveness"]), (2, 1, 50.0, 2, 45.0, 1, 0.0))
everything = R.narrow(events, participants, evaluations, results, None)
check("no department, everything", everything, (events, participants, evaluations, results))
check("a department with nobody booked", R.narrow(events, participants, evaluations, results, "Finance"), ([], [], [], []))

# ── 3. The figures on top ─────────────────────────────────────────────
figures = R.summary(rows, participants, evaluations, results)
check("the figures over the trainings held", figures,
      {"held": 1, "scheduled": 1, "trained": 2, "attendance": 50.0, "evaluation_score": 67.5, "rating": "Good",
       "effectiveness": 50.0})
check("nothing held", R.summary(R.training_rows(events[1:], participants, [], []), participants, [], []),
      {"held": 0, "scheduled": 1, "trained": 0, "attendance": None, "evaluation_score": None, "rating": None,
       "effectiveness": None})
check("the colours on the form's scale", [R.tone(value) for value in (None, 95, 75, 74.9, 50, 49.9)],
      ["Grey", "Green", "Green", "Orange", "Orange", "Red"])
cards = R.summary_cards(figures)
check("the cards", [(label, value, datatype) for label, value, datatype, _colour in cards],
      [("Trainings Held", 1, "Int"), ("Scheduled", 1, "Int"), ("People Trained", 2, "Int"), ("Attendance", 50.0, "Percent"),
       ("Evaluation Score", 67.5, "Percent"), ("Effectiveness", 50.0, "Percent")])
check("the cards' colours", [colour for *_rest, colour in cards], ["Blue", "Blue", "Blue", "Orange", "Orange", "Orange"])

# ── 4. The charts ─────────────────────────────────────────────────────
bars = R.chart(R.TRAININGS, rows, rows)
check("trainings: attendance and the evaluation score of those held", (bars["type"], bars["data"]["labels"],
                                                                       [d["values"] for d in bars["data"]["datasets"]]),
      ("bar", ["Fire Safety"], [[50.0], [67.5]]))
many = [dict(rows[0], training_event="T%02d" % n, training_program="Programme number %02d of the year" % n)
        for n in range(15)]
labels = R.chart(R.TRAININGS, many, many)["data"]["labels"]
check("only the latest held, the names cut short", (len(labels), labels[0], labels[-1]),
      (R.CHART_TRAININGS, "Programme number 03 of…", "Programme number 14 of…"))
came = R.chart(R.PARTICIPANTS, rows, people)
check("participants: who came, of those booked on a training held", (came["type"], came["data"]["labels"],
                                                                     came["data"]["datasets"][0]["values"]),
      ("donut", ["Present", "Absent", "Not Marked"], [2, 1, 1]))
fell = R.chart(R.ITEMS, rows, items)
check("evaluation items: how the ratings fell", (fell["type"], fell["data"]["labels"], fell["data"]["datasets"][0]["values"],
                                                 len(fell["colors"])),
      ("donut", list(R.RATINGS), [1, 1, 2, 1, 1], 5))
check("no chart for the comments, nor without data",
      [R.chart(R.COMMENTS, rows, said), R.chart(R.TRAININGS, rows[1:], rows[1:]), R.chart(R.ITEMS, rows, []),
       R.chart(R.PARTICIPANTS, rows[1:], people[4:])], [None, None, None, None])
print("arithmetic: trainings, participants, the consolidated form, the comments, a department's view, the figures, the charts")

# ── 5. Every column is in the rows ────────────────────────────────────
views = {R.TRAININGS: rows, R.PARTICIPANTS: people, R.ITEMS: items, R.COMMENTS: said}
check("the four views", tuple(views), R.VIEWS)
for view, produced in views.items():
    columns = [column[0] for column in R.REPORT_COLUMNS[view]]
    if len(columns) != len(set(columns)):
        fail.append("%s: each column once" % view)
    for row in produced:
        missing = set(columns) - set(row)
        if missing:
            fail.append("%s shows columns its rows do not have: %s" % (view, sorted(missing)))
            break
    for fieldname, label, fieldtype, options, width in R.REPORT_COLUMNS[view]:
        if (fieldtype == "Link") != bool(options) or not label or not width:
            fail.append("%s.%s: a label, a width, and options for a Link only" % (view, fieldname))
print("columns: every view's columns are in its rows")

# ── 6. The report ─────────────────────────────────────────────────────
base = os.path.join(APP, "report", "training_report")
spec = json.load(open(os.path.join(base, "training_report.json"), encoding="utf-8"))
if (spec.get("name"), spec.get("report_name"), spec.get("report_type"), spec.get("ref_doctype"), spec.get("module"),
        spec.get("is_standard"), spec.get("disabled")) != ("Training Report", "Training Report", "Script Report",
                                                           "Training Event", "HRMS Addon", "Yes", 0):
    fail.append("Training Report must be a standard, enabled Script Report of Training Event in HRMS Addon")
if {row["role"] for row in spec.get("roles", [])} != {"HR User", "HR Manager", "System Manager"}:
    fail.append("Training Report is HR's: HR User, HR Manager and System Manager")
if spec.get("add_total_row"):
    fail.append("Training Report must not add a total row: it would add up the percentages")
if not os.path.exists(os.path.join(base, "__init__.py")):
    fail.append("Training Report needs its __init__.py")
py = open(os.path.join(base, "training_report.py"), encoding="utf-8").read()
js = open(os.path.join(base, "training_report.js"), encoding="utf-8").read()
for needle, why in (
        ("def execute(filters=None):", "must have execute()"),
        ("from hrms_addon.hrms_addon import training_rules as rules", "must run on the tested rules"),
        ('view = filters.get("view") if filters.get("view") in rules.VIEWS else rules.TRAININGS',
         "must fall back to the Trainings view"),
        ("return columns(view), rows, None, rules.chart(view, trainings, rows), summary",
         "must give the chart and the figures on top"),
        ("rules.REPORT_COLUMNS[view]", "must take its columns from the rules"),
        ('frappe.get_list("Training Event"', "must read the trainings as the user may see them (a plant's own)"),
        ('events, participants, evaluations, results = rules.narrow(', "must narrow everything to a department's people"),
        ('participants, evaluations, results = _participants(names), _evaluations(names), _results(names)',
         "must read what hangs off the trainings it may see, and nothing else"),
        ('events, participants, evaluations, results, filters.get("department"))',
         "must narrow what it read, the talent filter's narrowing included, to a department's people"),
        ('if filters.get("talent_only"):\n        events, participants, evaluations, results = _talent_only(',
         "Talent Programmes Only keeps the sessions a development plan booked, and those people on them"),
        ('"score": rules.score([row.rating for row in rows])', "must score each form from its ratings"),
        ('"parenttype": "Training Event"', "must read the people booked on the trainings"),
        ('"parenttype": "Training Feedback"', "must read the ratings of the evaluation forms"),
        ('"parenttype": "Training Result"', "must read the marks of the results"),
        ('latest[(result.training_event, row.employee)]', "must keep each person's latest result"),
        ('if filters.get("training_event"):', "must show a training picked by name whatever the dates"),
        ('conditions.append(["start_time", "<", str(add_days(getdate(filters.get("to_date")), 1))])',
         "must take in the whole of the last day"),
        ('meta.get_label("custom_%s" % field)', "must label the questions as the form does"),
        ("rules.item_rows(evaluations, _items())", "must list the items in the form's order"),
        ("rules.comment_rows(events, evaluations, _questions(), _items())", "must give the comments in the form's order")):
    if needle not in py:
        fail.append("training_report.py %s" % why)
if py.count('filters={"training_event": ["in", names], "docstatus": 1}') != 2:
    fail.append("training_report.py must read submitted evaluations and submitted results only")
if 'frappe.query_reports["Training Report"] = {' not in js:
    fail.append("training_report.js must register the report by its name")
declared = re.findall(r'fieldname: "(\w+)"', js)
if len(declared) != len(set(declared)):
    fail.append("training_report.js declares a filter twice")
for used in set(re.findall(r'filters\.get\("(\w+)"\)', py)):
    if used not in declared:
        fail.append("training_report.py reads the filter %s, which its script does not offer" % used)
for wanted in ("view", "company", "from_date", "to_date", "branch", "department", "training_program", "training_event"):
    if wanted not in declared:
        fail.append("training_report.js must offer the %s filter" % wanted)
options = re.search(r'fieldname: "view",.*?options: \[([^\]]*)\]', js, re.S)
if not options or tuple(re.findall(r'"([^"]+)"', options.group(1))) != R.VIEWS:
    fail.append("the Show filter must offer the four views, in order: %s" % (R.VIEWS,))
if 'default: "Trainings"' not in js:
    fail.append("the report opens on the Trainings view")
pills = dict(re.findall(r'^\t"?([A-Za-z ]+?)"?: "(\w+)",$', js.split("const HA_TRAINING_PILLS = {")[-1].split("};")[0], re.M))
for word in R.RATINGS + (R.PRESENT, R.ABSENT, R.NOT_MARKED, R.EFFECTIVE, R.NOT_EFFECTIVE, R.HELD, R.SCHEDULED, R.CANCELLED):
    if word not in pills:
        fail.append("training_report.js gives %s no colour" % word)
for word, colour in pills.items():
    if word in R.RATINGS and colour != R.tone({"Excellent": 95, "Very Good": 80, "Good": 65, "Average": 55,
                                                "Below Average": 10}[word]).lower():
        fail.append("training_report.js colours %s %s, the figures on top another" % (word, colour))
text = re.search(r"const HA_TRAINING_TEXT = \[([^\]]*)\]", js)
typed = {"trainer", "employee_name", "item", "question", "answer"}
if not text or set(re.findall(r'"(\w+)"', text.group(1))) != typed:
    fail.append("training_report.js must show what was typed in as text: %s" % sorted(typed))
if "frappe.utils.escape_html(" not in js or "data.item === \"%s\"" % R.OVERALL not in js:
    fail.append("training_report.js must escape typed text and set the overall apart")

# what it reads is there: Frappe HR's fields, or ours
custom = json.load(open(os.path.join(REPO, "hrms_addon", "fixtures", "custom_field.json"), encoding="utf-8"))
custom_names = {row["name"] for row in custom}
labels = {row["name"]: row.get("label") for row in custom}
for field in ("custom_branch", "custom_department"):
    if "Training Event-%s" % field not in custom_names:
        fail.append("training_report.py reads Training Event.%s, which is not a custom field" % field)
for field, _question in R.QUESTIONS:
    if "Training Feedback-custom_%s" % field not in custom_names:
        fail.append("training_report.py reads Training Feedback.custom_%s, which is not a custom field" % field)
for field in ("custom_marks", "custom_effective"):
    if "Training Result Employee-%s" % field not in custom_names:
        fail.append("training_report.py reads Training Result Employee.%s, which is not a custom field" % field)
rating = json.load(open(os.path.join(APP, "doctype", "training_evaluation_rating", "training_evaluation_rating.json"),
                        encoding="utf-8"))
if not {"item", "rating", "comment"} <= {f["fieldname"] for f in rating["fields"]}:
    fail.append("Training Evaluation Rating must have item, rating and comment")
# the training's own score and the report's agree on a form with nothing rated
training = read("hrms_addon", "hrms_addon", "training.py")
if "feedback.custom_score = rules.score([r.rating for r in ratings])" not in training:
    fail.append("training.consolidated must score each form from its ratings, as the report does")
print("report: its record, filters, columns, what it reads and the training's own score agree")

# ── 7. Where HR finds it ──────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("navigation_rules", os.path.join(APP, "navigation_rules.py"))
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
card = dict(N.CARDS.get("Tenure", [])).get("Training") or []
if ("Training Report", "Training Report", N.REPORT) not in card:
    fail.append("the Tenure page's Training card must list the Training Report")
if ("Training Report", "Training Report", N.REPORT, "Reports", None) not in N.SIDEBAR.get("Tenure", []):
    fail.append("the Tenure sidebar must list the Training Report under Reports")
if N.report_facts("Training Report")[0] not in N.QUERY_REPORT_TYPES:
    fail.append("the Training Report must open as a query report from the menu")
# Frappe runs a report for those with report on its document, and exports,
# prints and makes a PDF of it only for those who may with that document
officer = set((R.PERMISSIONS.get("Training Event") or {}).get("HR User") or ())
if not {"read", "report", "export", "print"} <= officer:
    fail.append("the HR Officer (HR User) must be granted report, export and print on Training Event to download it: %s"
                % sorted(officer))
print("menu: the Training card and the Tenure sidebar's Reports; the HR Officer may download it")

# ── 8. What it reads in Frappe HR ─────────────────────────────────────
if UPSTREAM_OK:
    def fields(folder):
        path = os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", folder, folder + ".json")
        return {f["fieldname"] for f in json.load(open(path, encoding="utf-8"))["fields"]}

    for folder, wanted in (
            ("training_event", {"training_program", "course", "start_time", "end_time", "trainer_name", "event_status",
                                "company", "employees"}),
            ("training_event_employee", {"employee", "employee_name", "department", "attendance"}),
            ("training_feedback", {"training_event", "employee", "employee_name"}),
            ("training_result", {"training_event", "employees"}),
            ("training_result_employee", {"employee"})):
        missing = wanted - fields(folder)
        if missing:
            fail.append("Frappe HR's %s has no %s: recheck the Training Report" % (folder, sorted(missing)))
    event_spec = json.load(open(os.path.join(APPS_ROOT, "hrms", "hrms", "hr", "doctype", "training_event",
                                             "training_event.json"), encoding="utf-8"))
    manager = next((p for p in event_spec["permissions"] if p.get("role") == "HR Manager" and not p.get("permlevel")), {})
    if not all(manager.get(ptype) for ptype in ("read", "report", "export", "print")):
        fail.append("Frappe HR no longer lets the HR Manager report, export and print Training Event: grant it here")
    upstream_note = "checked against Frappe HR"
else:
    upstream_note = "Frappe HR not found at %s, upstream contract not checked" % APPS_ROOT
print("upstream: %s" % upstream_note)

print()
if fail:
    print("FAILURES:")
    for problem in fail:
        print("  -", problem)
    sys.exit(1)
print("ALL TRAINING REPORT CHECKS PASSED")
