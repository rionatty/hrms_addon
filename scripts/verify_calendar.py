"""Verify the HR calendar without a bench:

    python scripts/verify_calendar.py

  1  the rules: the month and its days, what a roster day shows, what an
     empty day's click and a drag may do, how a block moves
  2  the glue: fields that exist, one rule for who sees what, every change
     through the checks and approvals that stand
  3  the view (public/js/hr_calendar_view.js): its styles, its calls, its
     dragging
  4  the page, the two forms that draw it, how it loads, a way in

Frappe HR's and ERPNext's own fields are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
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
CUSTOM = json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
fail = []


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def spec_of(name):
    folder = name.lower().replace(" ", "_")
    path = os.path.join(APP, "doctype", folder, folder + ".json")
    if not os.path.exists(path):
        hits = glob.glob(os.path.join(APPS_ROOT, "*", "*", "**", "doctype", folder, folder + ".json"), recursive=True)
        path = hits[0] if hits else None
    return json.load(open(path, encoding="utf-8")) if path else None


def fields_of(name):
    spec = spec_of(name)
    if spec is None:
        return None
    return {f["fieldname"] for f in spec.get("fields", [])} | {row["fieldname"] for row in CUSTOM if row.get("dt") == name}


def body(source, name):
    """The text of one top-level function."""
    return source.split("def %s(" % name)[1].split(chr(10) + "def ")[0] if "def %s(" % name in source else ""


C = load("calendar_rules")
print("loaded calendar_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if C.month_of(None, None, "2026-09-24") != (2026, 9) or C.month_of("2027", "3", "2026-09-24") != (2027, 3):
    fail.append("the month asked for, else the one today is in")
try:
    C.month_of(2027, 13, "2026-09-24")
    fail.append("there is no thirteenth month")
except ValueError:
    pass
if C.month_window(2028, 2) != (datetime.date(2028, 2, 1), datetime.date(2028, 2, 29)):
    fail.append("a leap February has 29 days")
if C.month_title(2027, 3) != "March 2027" or C.month_number("March") != 3 or C.month_number("Marzo") != 0:
    fail.append("the month is named in full, and its name read back")
days = C.days(2027, 3, {"2027-03-08": "Women's Day"}, "2027-03-02")
if len(days) != 31 or days[0]["weekday"] != "Mon" or days[7]["holiday"] != "Women's Day" or days[0]["holiday"] \
        or not days[1]["today"] or days[0]["today"]:
    fail.append("a day knows its weekday, its holiday and whether it is today: %s" % days[:9])
if C.common_holidays([{"a": "x", "b": "y"}, {"b": "y", "c": "z"}]) != {"b": "y"} or C.common_holidays([]) != {}:
    fail.append("the header shades the holidays everybody shown shares")
for docstatus, status, kind in ((0, "Open", C.APPLIED), (1, "Approved", C.APPROVED), (1, "Rejected", None),
                                (2, "Cancelled", None), (0, "Cancelled", None), ("1", "Approved", C.APPROVED)):
    if C.leave_kind(docstatus, status) != kind:
        fail.append("a leave with docstatus %r and status %r is %r on the calendar" % (docstatus, status, kind))
for event_status, docstatus, status in (("Scheduled", 0, C.SCHEDULED), ("Scheduled", 1, C.SCHEDULED),
                                        ("Completed", 1, C.COMPLETED), ("Cancelled", 1, None), ("Scheduled", 2, None)):
    if C.session_status(event_status, docstatus) != status:
        fail.append("a %s event with docstatus %s shows as %r" % (event_status, docstatus, status))
for docstatus, status, state in ((0, "Draft", C.PLAN_DRAFT), (0, None, C.PLAN_DRAFT), (0, "Pending HOD", C.PLAN_PENDING),
                                 (0, "Pending HR Officer", C.PLAN_PENDING), (1, "Approved", C.PLAN_APPROVED),
                                 (2, "Cancelled", None)):
    if C.plan_state(docstatus, status) != state:
        fail.append("a plan with docstatus %s and status %r is %r" % (docstatus, status, state))
for is_hr, is_self, state, mode in (
    (True, False, None, C.ADD_PLAN), (True, False, C.PLAN_DRAFT, C.ADD_PLAN), (True, False, C.PLAN_APPROVED, C.ADD_APPLY),
    (True, False, C.PLAN_PENDING, C.ADD_APPLY), (False, True, C.PLAN_DRAFT, C.ADD_APPLY),
    (False, True, C.PLAN_APPROVED, C.ADD_APPLY), (False, False, C.PLAN_APPROVED, None), (False, False, None, None),
):
    if C.leave_add_mode(is_hr, is_self, state) != mode:
        fail.append("an empty day clicked by hr=%s self=%s on a %s plan does %r, got %r"
                    % (is_hr, is_self, state, mode, C.leave_add_mode(is_hr, is_self, state)))
for is_hr, is_self, state, applied, moving, mode in (
    (True, False, C.PLAN_DRAFT, False, False, C.MOVE_DIRECT), (False, True, C.PLAN_DRAFT, False, False, None),
    (True, False, C.PLAN_APPROVED, False, False, C.MOVE_ASK), (False, True, C.PLAN_APPROVED, False, False, C.MOVE_ASK),
    (False, False, C.PLAN_APPROVED, False, False, None), (True, False, C.PLAN_APPROVED, True, False, None),
    (True, False, C.PLAN_APPROVED, False, True, None), (True, False, C.PLAN_PENDING, False, False, None),
):
    if C.leave_move_mode(is_hr, is_self, state, applied, moving) != mode:
        fail.append("planned leave dragged by hr=%s self=%s on a %s plan (applied=%s, moving=%s) moves %r"
                    % (is_hr, is_self, state, applied, moving, mode))
if C.span_days("2027-02-27", "2027-03-02", "2027-03-01", "2027-03-31") != ["2027-03-01", "2027-03-02"] \
        or C.span_days(None, "2027-03-02", "2027-03-01", "2027-03-31") != []:
    fail.append("a block that starts before the month is drawn from its first day; no dates, no days")
LEAVE = [{"key": "row:1", "row": "E", "from": "2027-03-01", "to": "2027-03-12", "kind": C.PLANNED},
         {"key": "app:1", "row": "E", "from": "2027-03-03", "to": "2027-03-05", "kind": C.APPROVED},
         {"key": "app:2", "row": "E", "from": "2027-03-05", "to": "2027-03-06", "kind": C.APPLIED},
         {"key": "chg:1", "row": "E", "from": "2027-03-10", "to": "2027-04-02", "kind": C.MOVING},
         {"key": "app:3", "row": "F", "from": "2027-02-20", "to": "2027-03-01", "kind": C.APPLIED}]
MONTH = C.days(2027, 3)
cells = C.pick_cells(LEAVE, {"E": {"2027-03-07": "Sunday", "2027-04-04": "Next month"}}, MONTH)
got = {day: cells["E"].get(day, {}).get("blocks") for day in ("2027-03-01", "2027-03-03", "2027-03-05", "2027-03-06",
                                                               "2027-03-10", "2027-03-13", "2027-03-31")}
if got != {"2027-03-01": ["row:1"], "2027-03-03": ["app:1"], "2027-03-05": ["app:1"], "2027-03-06": ["app:2"],
           "2027-03-10": ["row:1"], "2027-03-13": ["chg:1"], "2027-03-31": ["chg:1"]}:
    fail.append("a leave day shows its strongest block: approved, applied for, planned, a move asked: %s" % got)
if cells["E"]["2027-03-07"]["holiday"] != "Sunday" or "2027-04-04" in cells["E"] or cells["F"]["2027-03-01"]["blocks"] != ["app:3"]:
    fail.append("a holiday is marked on its day, nothing outside the month, a block from before the month is drawn")
counts = C.off_counts(cells, LEAVE, MONTH)
if (counts["off"]["2027-03-01"], counts["off"]["2027-03-03"], counts["off"]["2027-03-07"], counts["off"]["2027-03-13"],
        counts["planned"]["2027-03-02"], counts["planned"]["2027-03-10"], counts["planned"]["2027-03-13"]) \
        != (1, 1, 0, 0, 1, 1, 0):
    fail.append("off counts leave approved or applied for; planned the rest; a holiday or a move asked counts "
                "nobody: %s" % counts)
SESSIONS = [{"key": "line:2", "row": "D", "from": "2027-03-10", "to": "2027-03-10", "kind": C.PLANNED_SESSION,
             "start": "14:00"},
            {"key": "evt:1", "row": "D", "from": "2027-03-10", "to": "2027-03-11", "kind": C.SCHEDULED, "start": "07:00"}]
sessions = C.pick_cells(SESSIONS, {"D": {"2027-03-11": "Holiday"}}, MONTH, one_per_day=False)
if sessions["D"]["2027-03-10"]["blocks"] != ["evt:1", "line:2"] or sessions["D"]["2027-03-11"] != \
        {"blocks": ["evt:1"], "holiday": "Holiday"}:
    fail.append("a department's day shows every session, the earliest first, a holiday marked but not hiding them")
if not C.too_many(2, 1) or C.too_many(1, 1) or C.too_many(5, 0) or C.too_many(5, None):
    fail.append("a day is over the plan's Most Off at Once when more than it are off; no limit, never")
if C.shifted("2027-03-01", "2027-03-05", "2027-03-29") != (datetime.date(2027, 3, 29), datetime.date(2027, 4, 2)):
    fail.append("a span moved keeps its length")
if C.shifted_session("2027-03-12 07:30:00", "2027-03-12 09:30:00", "2027-03-19") != \
        (datetime.datetime(2027, 3, 19, 7, 30), datetime.datetime(2027, 3, 19, 9, 30)) or \
        C.shifted_session(datetime.datetime(2027, 3, 12, 22, 0), datetime.datetime(2027, 3, 13, 6, 0), "2027-03-20") != \
        (datetime.datetime(2027, 3, 20, 22, 0), datetime.datetime(2027, 3, 21, 6, 0)):
    fail.append("a session moved keeps its hours, a night one its morning after")
if not C.in_month("2027-03-31", 2027, 3) or C.in_month("2027-04-01", 2027, 3) or C.in_month(None, 2027, 3) \
        or C.in_month("2026-03-10", 2027, 3):
    fail.append("a day is in its month or not")
for given, shown in (("2027-03-10 07:00:00", "07:00"), ("7:00:00", "07:00"), (datetime.time(14, 30), "14:30"),
                     (datetime.timedelta(hours=9), "09:00"), (None, ""), ("", ""),
                     (datetime.datetime(2027, 3, 10, 7, 5), "07:05"), ("2027-03-10T16:00:00", "16:00")):
    if C.clock(given) != shown:
        fail.append("the hour as the form sends it, the database keeps it or Python has it: %r shows %r, not %r"
                    % (given, C.clock(given), shown))
print("the rules: the month, a roster day, an empty day's click, a drag, a move")

# ── 2. The glue ───────────────────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "calendar_board.py")
for doctype, wanted in (
    ("Leave Application", ("employee", "from_date", "to_date", "leave_type", "status", "company")),
    ("Leave Plan Change", ("plan_row", "employee", "new_from", "new_to", "approval_status", "workflow_state")),
    ("Training Event", ("event_name", "course", "event_status", "location", "trainer_name", "start_time", "end_time",
                        "custom_branch", "custom_department", "employees")),
    ("Training Event Employee", ("employee", "employee_name", "department")),
    ("Holiday", ("holiday_date", "description", "weekly_off")),
    ("Company", ("default_holiday_list",)),
    ("Employee", ("employee_name", "department", "designation", "holiday_list", "company", "branch", "status",
                  "user_id")),
    ("Annual Leave Plan", ("year", "branch", "department", "most_off", "status", "company", "posting_date",
                           "employees")),
    ("Annual Leave Plan Employee", ("employee", "planned_from", "planned_to", "planned_days", "leave_application")),
    ("Monthly Training Schedule", ("month", "year", "branch", "company", "prepared_by", "training_calendar", "lines")),
    ("Training Schedule Line", ("course", "training_date", "start_time", "end_time", "venue", "trainer",
                                "department", "target_group", "training_event", "calendar_entry", "training_program")),
    ("Training Calendar Entry", ("course", "trainer", "target_group", "section", "planned_month", "planned_year",
                                 "scheduled", "training_program")),
):
    have = fields_of(doctype)
    if have is None:
        fail.append("%s is not to be found" % doctype)
        continue
    if doctype == "Leave Plan Change":
        have |= {"workflow_state"}  # made by the Workflow when it is saved
    missing = [field for field in wanted if field not in have]
    if missing:
        fail.append("the calendar reads %s of %s, which it has not got" % (missing, doctype))
for method in ("month",):
    if "@frappe.whitelist()\ndef %s(" % method not in glue:
        fail.append("the view has to be able to call %s" % method)
for method in ("leave_info", "save_leave", "remove_leave", "apply_leave", "save_session", "move_session",
               "remove_session"):
    if '@frappe.whitelist(methods=["POST"])\ndef %s(' % method not in glue:
        fail.append("%s changes the site, so it is whitelisted for POST only" % method)
if "own = leave.own_place(frappe.session.user)" not in body(glue, "month"):
    fail.append("who sees what follows the leave plan: HR, heads of department and supervisors everything, "
                "an employee their own plant and department")
if "OPENS_TO & roles" not in body(glue, "month"):
    fail.append("Training Event is HR's to read; the page's own roles gate the call")
if 'check_permission("read")' not in body(glue, "month"):
    fail.append("a plan or a schedule is drawn only for somebody who may read it")
if "leave_rules.plan_errors(" not in body(glue, "_check_employee"):
    fail.append("planned leave put on a plan is checked as the plan checks it when it is sent")
for name in ("save_leave", "_move_leave"):
    if "_check_employee(doc" not in body(glue, name):
        fail.append("%s checks the employee's planned leave before it saves" % name)
if "rules.leave_move_mode(" not in body(glue, "_move_leave") or "rules.leave_move_mode(" not in body(glue, "_leave"):
    fail.append("the view and the call agree how a planned block moves: both ask the rules")
if "rules.leave_add_mode(" not in body(glue, "_leave"):
    fail.append("what an empty day does comes from the rules")
ask = body(glue, "_move_leave")
if "leave.request_change(" not in ask or "change_approval.PENDING_SUPERVISOR" not in ask \
        or "frappe.delete_doc(CHANGE, name" not in ask:
    fail.append("on an approved plan a move is asked (a Leave Plan Change sent to the supervisor), and a refused "
                "one leaves no draft behind to block the next")
if "Say why the leave is moving" not in ask:
    fail.append("a move is asked with its reason")
if "_drawing_up_or_throw(doc)" not in body(glue, "save_leave") or "_drawing_up_or_throw(doc)" not in body(glue, "remove_leave"):
    fail.append("only a plan still being drawn up is changed straight")
if "leave._may_act_for(employee)" not in body(glue, "apply_leave") or "leave._may_act_for(employee)" not in \
        body(glue, "leave_info"):
    fail.append("only the employee or HR apply for leave or see what is left")
for name in ("save_session", "move_session", "remove_session"):
    if "_hr_only()" not in body(glue, name):
        fail.append("%s is HR's" % name)
if "_tell_moved(event)" not in body(glue, "move_session"):
    fail.append("a booked training moved tells its people")
if "_session_day_or_throw(doc, day)" not in body(glue, "move_session"):
    fail.append("a line stays in its schedule's month")
if "PEOPLE_LIMIT" not in body(glue, "_people"):
    fail.append("the roster is capped, and the view says so")
print("the glue: fields that exist, who sees what, every change through the checks that stand")

# ── 3. The view ───────────────────────────────────────────────────────
view = read("hrms_addon", "public", "js", "hr_calendar_view.js")
if "if (hrms_addon.HRCalendarView) return;" not in view or "hrms_addon.HRCalendarView = class" not in view:
    fail.append("the view is defined once, whichever way it was loaded")
if 'const METHOD = "hrms_addon.hrms_addon.calendar_board.";' not in view:
    fail.append("the view calls calendar_board")
called = set(re.findall(r'METHOD \+ "([a-z_]+)"', view)) | set(re.findall(r'this\.change\(\s*"([a-z_]+)"', view))
whitelisted = set(re.findall(r"@frappe\.whitelist\([^)]*\)\ndef ([a-z_]+)\(", glue))
if called - whitelisted:
    fail.append("the view calls what calendar_board does not offer: %s" % sorted(called - whitelisted))
if {"month", "save_leave", "remove_leave", "apply_leave", "leave_info", "save_session", "move_session",
        "remove_session"} - called:
    fail.append("the view leaves a call unused: %s" % sorted({"month", "save_leave", "remove_leave", "apply_leave",
                                                              "leave_info", "save_session", "move_session",
                                                              "remove_session"} - called))
if "hrms_addon.hrms_addon.leave.apply_from_plan" not in view:
    fail.append("planned leave on an approved plan is applied for from the plan")
if "frappe.datetime.add_days(" in view or "frappe.datetime.get_day_diff(" in view:
    fail.append("frappe.datetime.add_days returns a whole timestamp: the view counts its days itself")
css = view.split("const HRV_STYLE = `")[1].split("`;")[0] if "const HRV_STYLE = `" in view else ""
constructor = view.split("constructor(opts) {")[1].split("\n\t\t}\n")[0] if "constructor(opts) {" in view else ""
if not css or "hrv_style();" not in constructor:
    fail.append("the view puts its own styles on the head as it is made (see attendance_board.js)")
for kind in C.LEAVE_KINDS + C.SESSION_KINDS:
    if ".hrv-chip.hrv-k-%s" % kind not in css:
        fail.append("a %s block has no look of its own" % kind)
if ".hrv-training .hrv-chip.hrv-k-planned" not in css:
    fail.append("a session on a draft schedule is drawn apart from one booked")
if "td.hrv-holiday" not in css or "td.hrv-drop" not in css or "td.hrv-bad" not in css:
    fail.append("holidays, where a dragged block would land and a day over the limit are all drawn")
used = set(re.findall(r"var\((--hrv-[a-z0-9-]+)", css))
mine = set(re.findall(r"^\s*(--hrv-[a-z0-9-]+)\s*:", css, re.M))
if used - mine:
    fail.append("a var() that resolves to nothing takes its whole declaration with it: %s" % sorted(used - mine))
bare = sorted({name for name, fallback in re.findall(r"var\((--hra-[a-z0-9-]+)(\s*,[^)]*)?\)", css) if not fallback})
if bare:
    fail.append("every theme colour the view borrows needs a fallback: %s" % bare)
if ".hrv-" in read("hrms_addon", "public", "css", "hrms_addon.bundle.css"):
    fail.append("the view's styles are in ONE place, or the two copies will drift")
for needle, why in (
    ('root.on("dragstart"', "a block is picked up"),
    ('root.on("dragover", "td.hrv-cell"', "a day says whether the block may land on it"),
    ('root.on("drop", "td.hrv-cell"', "and takes it"),
    ('root.on("click", "td.hrv-can-add"', "an empty day is clicked to add"),
    ('root.on("click", ".hrv-chip"', "a block is clicked to change it"),
    ("escape_html", "names, courses and venues are typed by people and printed as HTML"),
    ('block.move === "direct"', "a plan being drawn up is changed straight"),
    ('block.move === "ask"', "an approved plan's leave is asked to move"),
    ('row.add === "plan"', "HR plan leave on an empty day"),
    ('row.add === "apply"', "an employee applies on an empty day"),
    ("before_change", "a form saves its own edits before the calendar changes the document"),
    ("after_change", "and reloads after"),
):
    if needle not in view:
        fail.append(why)
target = view.split("target_of(cell) {")[1].split("\n\t\t}\n")[0] if "target_of(cell) {" in view else ""
if "row !== block.row" not in target or 'block.key.indexOf("evt:") === 0' not in target or "!block.move" not in target:
    fail.append("leave and booked trainings stay on their row; only a block that may move is dragged")
for mode in (C.MOVE_DIRECT, C.MOVE_ASK, C.ADD_PLAN, C.ADD_APPLY):
    if '"%s"' % mode not in view:
        fail.append("the view knows the mode %r the rules give" % mode)
if '"session" if is_hr' not in glue:
    fail.append("HR add sessions on an empty day")
print("the view: its styles, its calls, its dragging, drawn like the roster")

# ── 4. The page, the forms, how it loads, a way in ────────────────────
hooks = read("hrms_addon", "hooks.py")
asset = "/assets/hrms_addon/js/hr_calendar_view.js"
if '"%s"' % asset not in hooks.split("app_include_js = [")[1].split("]")[0]:
    fail.append("the view is loaded on every desk page, as a plain asset needing no build")
page_js = read("hrms_addon", "hrms_addon", "page", "hr_calendar", "hr_calendar.js")
page_json = json.loads(read("hrms_addon", "hrms_addon", "page", "hr_calendar", "hr_calendar.json"))
if page_json["name"] != "hr-calendar" or page_json.get("page_name") != "hr-calendar" \
        or page_json.get("standard") != "Yes" or page_json.get("module") != "HRMS Addon":
    fail.append("the page is hr-calendar, standard, in this module")
roles = {row["role"] for row in page_json.get("roles", [])}
if roles != {"HR User", "HR Manager", "Head of Department", "Supervisor", "Employee"}:
    fail.append("the calendar opens to HR, heads of department, supervisors and employees: %s" % sorted(roles))
for role in roles:
    if '"%s"' % role not in glue.split("OPENS_TO = ")[1].split(chr(10))[0]:
        fail.append("the call must open to everybody the page opens to (%s)" % role)
if 'frappe.pages["hr-calendar"].on_page_load' not in page_js or "on_page_show" not in page_js:
    fail.append("the page registers on its own name and shows what is true when it is come back to")
if "new hrms_addon.HRCalendarView(" not in page_js or "switchable: true" not in page_js:
    fail.append("the page draws the view, both leave and training")
for form, scope in (("annual_leave_plan", "plan: frm.doc.name"), ("monthly_training_schedule", "schedule: frm.doc.name")):
    script = read("hrms_addon", "hrms_addon", "doctype", form, form + ".js")
    spec = json.loads(read("hrms_addon", "hrms_addon", "doctype", form, form + ".json"))
    field = next((f for f in spec["fields"] if f["fieldname"] == "calendar_html"), None)
    if not field or field["fieldtype"] != "HTML" or "calendar_html" not in spec["field_order"]:
        fail.append("the %s form has a place for the calendar" % form)
    if "frm.fields_dict.calendar_html" not in script or scope not in script or 'frm.trigger("draw_calendar")' not in script:
        fail.append("the %s form draws the calendar of itself on every refresh" % form)
    if "frm.is_dirty() ? frm.save() : null" not in script or "after_change: () => frm.reload_doc()" not in script:
        fail.append("the %s form saves its edits first and reloads after the calendar changes it" % form)
    if "frm.is_new()" not in script:
        fail.append("a %s not yet saved has no calendar to draw" % form)
for script in (page_js, read("hrms_addon", "hrms_addon", "doctype", "annual_leave_plan", "annual_leave_plan.js"),
               read("hrms_addon", "hrms_addon", "doctype", "monthly_training_schedule", "monthly_training_schedule.js")):
    if 'frappe.require("%s"' % asset not in script:
        fail.append("a script that draws the view loads it itself when the desk has not yet")
nav = read("hrms_addon", "hrms_addon", "navigation_rules.py")
if nav.count('"hr-calendar", PAGE') < 4:
    fail.append("the calendar needs a way in from the leave page and the training card, and from both sidebars")
print("the page, the plan, the schedule: each draws the view; loaded on every desk page; a way in")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL CALENDAR CHECKS PASSED")
