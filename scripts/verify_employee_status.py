"""The employee statuses (Luuka, 18 Oct 2026: "edit the standard field to
accommodate all the status the customer provided ... have a place for
defining new one too"), checked without a bench.

employee_status_rules.py is loaded without Frappe and its rules run; the
doctype, the fixtures, the hooks, the patch, the places that move a status
(a suspension, an exit, the boot) and the Employee form and list scripts are
read as files. The walk (smoke_employee_status.py) runs the glue.
"""
import importlib.util
import io
import json
import os
import re
import sys

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


def body_of(source, name):
    start = source.index("\ndef %s(" % name)
    rest = source[start + 1:]
    end = rest.index("\ndef ", 1) if "\ndef " in rest[1:] else len(rest)
    return rest[:end]


R = load("employee_status_rules")
print("loaded employee_status_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
if R.BASE != ("Active", "Inactive", "Suspended", "Left"):
    fail.append("Frappe's four, as ERPNext's Employee.validate_status takes them: %s" % (R.BASE,))
luuka = dict(R.LUUKA)
if luuka != {"On Hold": "Inactive", "Separated": "Left", "Resigned": "Left", "Terminated": "Left",
             "Deceased": "Left", "Retired": "Left"}:
    fail.append("Luuka's statuses (the Employee sheet of 18 Oct 2026) and what each counts as: %s" % luuka)
COUNTS = dict({name: name for name in R.BASE}, **luuka)
for status, chosen, before, wanted, why in (
        ("Active", "On Hold", ("Active", "Active"), ("Inactive", "On Hold"), "a Status picked decides the System Status"),
        ("Inactive", "Active", ("Inactive", "On Hold"), ("Active", "Active"), "and back"),
        ("Active", "Resigned", None, ("Left", "Resigned"), "a new employee's Status decides it"),
        ("Left", "Resigned", None, ("Left", "Resigned"), "an import row with both is kept"),
        ("Left", None, None, ("Left", "Left"), "an employee without a Status takes their System Status's"),
        ("Active", "Terminated", ("Left", "Terminated"), ("Active", "Active"),
         "the System Status moved (a reinstatement): a Status that no longer fits gives way"),
        ("Left", "Separated", ("Left", "Separated"), ("Left", "Separated"), "nothing changed, nothing moves"),
        ("Suspended", "Active", ("Active", "Active"), ("Suspended", "Suspended"), "a suspension saved"),
        ("Left", "Retired", ("Left", "Resigned"), ("Left", "Retired"), "one Left status for another"),
        ("Active", "Gone", ("Active", "Active"), ("Active", "Active"),
         "a status the site has not got (links not checked) gives way to the System Status's own"),
):
    got = R.settle(status, chosen, before, COUNTS)
    if got != wanted:
        fail.append("settle(%r, %r, %r): %s, wanted %s (%s)" % (status, chosen, before, got, wanted, why))
if R.settle("Active", "On Hold", ("Active", "Active"), {}) != ("Active", "On Hold"):
    fail.append("without any statuses on the site, settle touches nothing")
rows = [{"name": "A", "status": "Left", "custom_employee_status": "Active"},
        {"name": "B", "status": "Active", "custom_employee_status": None},
        {"name": "C", "status": "Left", "custom_employee_status": "Resigned"},
        {"name": "D", "status": "Inactive", "custom_employee_status": "On Hold"},
        {"name": "E", "status": "Odd", "custom_employee_status": None}]
if R.drift(rows, COUNTS) != [("A", "Left"), ("B", "Active")] or R.drift(rows, {}) != []:
    fail.append("drift: those whose Status no longer counts as their System Status, or have none: %s"
                % R.drift(rows, COUNTS))
if (R.moved("On Hold", "Inactive", COUNTS), R.moved("Active", "Suspended", COUNTS), R.moved(None, "Active", COUNTS)) \
        != ("On Hold", "Suspended", "Active"):
    fail.append("moved: the Status kept while it counts as the new System Status, else its own")
options = [o for o in next(f for f in json.load(io.open(os.path.join(PACKAGE, "fixtures", "custom_field.json"),
                                                         encoding="utf-8"))
                           if f["name"] == "Employee Separation-custom_reason")["options"].split("\n") if o]
if sorted(R.EXIT_STATUSES) != sorted(options):
    fail.append("every reason an exit gives has the status it leaves: %s against %s" % (sorted(R.EXIT_STATUSES), options))
if any(luuka.get(name) != "Left" for name in R.EXIT_STATUSES.values()):
    fail.append("an exit leaves one of Luuka's statuses that counts as Left: %s" % R.EXIT_STATUSES)
for reason, counts, disabled, wanted in (("Resignation", COUNTS, (), "Resigned"), ("Death", COUNTS, ("Deceased",), "Left"),
                                         ("Retirement", {k: v for k, v in COUNTS.items() if k != "Retired"}, (), "Left"),
                                         (None, COUNTS, (), "Left"), ("Dismissal", COUNTS, (), "Terminated"),
                                         ("Resignation", dict(COUNTS, Resigned="Inactive"), (), "Left")):
    if R.exit_status(reason, counts, disabled) != wanted:
        fail.append("exit_status(%r): %s, wanted %s" % (reason, R.exit_status(reason, counts, disabled), wanted))
if (R.colour_of("On Hold", COUNTS), R.colour_of("Active", COUNTS), R.colour_of("Resigned", COUNTS, {"Resigned": "purple"}),
        R.colour_of("Resigned", COUNTS, {"Resigned": "teal"}), R.colour_of("Nobody", COUNTS)) \
        != ("red", "green", "purple", "gray", "gray"):
    fail.append("colour_of: its own colour, else the one Frappe's list gives what it counts as")


def expect(label, got, *needles):
    if len(got) != len(needles) or not all(any(n in message for message in got) for n in needles):
        fail.append("%s: expected %s, got %s" % (label, list(needles) or "no errors", got))


expect("a new status of HR's", R.status_errors("Probation", "Active", 0, 0, None))
expect("a name", R.status_errors("  ", "Active", 0, 0, None), "needs a name")
expect("one of the four", R.status_errors("Away", "Away", 0, 0, None), "Counts As must be one of")
expect("only the system statuses are built in", R.status_errors("Gone", "Left", 1, 0, None), "Only the system statuses")
expect("standard stays standard", R.status_errors("Probation", "Active", 1, 0, ("Active", 0)), "cannot be changed")
expect("and not standard stays not", R.status_errors("Left", "Left", 0, 0, ("Left", 1)), "cannot be changed")
expect("Frappe's own counts as itself", R.status_errors("Left", "Inactive", 1, 0, ("Left", 1)), "counts as itself")
expect("in use, what it counts as stays", R.status_errors("On Hold", "Left", 0, 3, ("Inactive", 0)),
       "3 employee(s) have the status On Hold")
expect("unused, it may change", R.status_errors("On Hold", "Left", 0, 0, ("Inactive", 0)))
print("rules: the four, Luuka's six, settle, drift, moved, the exit's status, the colours, what stops a save")

# ── 2. The doctype ────────────────────────────────────────────────────
spec = json.load(io.open(os.path.join(APP, "doctype", "employee_status", "employee_status.json"), encoding="utf-8"))
fields = {f["fieldname"]: f for f in spec["fields"]}
if (spec.get("autoname"), spec.get("module"), spec.get("title_field")) != ("field:status_name", "HRMS Addon", "status_name"):
    fail.append("Employee Status is named by its status, in HRMS Addon")
if fields.get("counts_as", {}).get("options", "").split("\n") != list(R.BASE) or not fields["counts_as"].get("reqd"):
    fail.append("Counts As is one of Frappe's four, required")
if not (fields.get("status_name", {}).get("reqd") and fields["status_name"].get("unique")):
    fail.append("the status's name is required and unique")
for fieldname, fieldtype in (("disabled", "Check"), ("is_standard", "Check"), ("colour", "Select"), ("description", "Small Text")):
    if fields.get(fieldname, {}).get("fieldtype") != fieldtype:
        fail.append("Employee Status has %s (%s)" % (fieldname, fieldtype))
if not fields.get("is_standard", {}).get("read_only"):
    fail.append("whether a status is Frappe's own is not for typing")
colours = [o for o in fields.get("colour", {}).get("options", "").split("\n") if o]
if colours != list(R.INDICATORS):
    fail.append("the colours offered are the ones Frappe's indicators have: %s" % colours)
perms = {p["role"]: p for p in spec.get("permissions", [])}
if not (perms.get("HR Manager", {}).get("write") and perms.get("HR Manager", {}).get("create")
        and perms.get("System Manager", {}).get("write")):
    fail.append("HR Managers (and System Managers) keep the list of statuses")
if perms.get("HR User", {}).get("write") or not perms.get("HR User", {}).get("read") \
        or not perms.get("Employee", {}).get("read") or perms.get("Employee", {}).get("write"):
    fail.append("HR Users and employees read the statuses, they do not change them")
controller = read("hrms_addon", "hrms_addon", "doctype", "employee_status", "employee_status.py")
for needle in ("rules.status_errors(", "frappe.db.count(\"Employee\", {employee_status.FIELD: self.name})",
               "employee_status.forget()", "frappe.cache.delete_key(\"bootinfo\")", "def on_trash(self):",
               "cannot be removed", "stays in use"):
    if needle not in controller:
        fail.append("the Employee Status controller: %r" % needle)
form = read("hrms_addon", "hrms_addon", "doctype", "employee_status", "employee_status.js")
if 'set_df_property("counts_as", "read_only", frm.doc.is_standard' not in form:
    fail.append("the Employee Status form locks what Frappe's own count as")
print("doctype: named by its status, Counts As one of the four, colours, HR Managers keep it")

# ── 3. Fixtures, hooks, the patch ─────────────────────────────────────
custom = {f["name"]: f for f in json.load(io.open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))}
field = custom.get("Employee-custom_employee_status", {})
if (field.get("fieldtype"), field.get("options"), field.get("insert_after"), field.get("label")) \
        != ("Link", "Employee Status", "image", "Status"):
    fail.append("Employee's Status is a link to Employee Status, labelled Status, just before Frappe's own")
if not field.get("in_standard_filter") or field.get("in_list_view"):
    fail.append("the Status is a list filter; the list shows it as the indicator, not a second column")
setters = {p["name"]: p for p in json.load(io.open(os.path.join(PACKAGE, "fixtures", "property_setter.json"),
                                                  encoding="utf-8"))}
if (setters.get("Employee-status-label", {}).get("value"), setters.get("Employee-status-read_only", {}).get("value")) \
        != ("System Status", "1"):
    fail.append("Frappe's own status is the System Status, read-only: set from the Status")
hooks = {}
exec(compile(read("hrms_addon", "hooks.py"), "hooks.py", "exec"), hooks)
names = [name for fixture in hooks.get("fixtures", []) if isinstance(fixture, dict)
         for flt in fixture.get("filters", []) if isinstance(flt, (list, tuple)) and len(flt) == 3 and flt[1] == "in"
         for name in flt[2]]
for name in ("Employee-custom_employee_status", "Employee-status-label", "Employee-status-read_only",
             "Employee-status-description"):
    if name not in names:
        fail.append("hooks' fixtures leave out %s" % name)
    if name not in custom and name not in setters:
        fail.append("%s is listed but not in the fixtures" % name)
employee_events = (hooks.get("doc_events") or {}).get("Employee") or {}
if employee_events.get("before_validate") != "hrms_addon.hrms_addon.employee_status.employee_before_validate":
    fail.append("the Status sets the System Status before Frappe's own validation (before_validate)")
if "hrms_addon.hrms_addon.employee_status.install" not in hooks.get("after_migrate", []):
    fail.append("every migrate makes Frappe's four and gives employees their Status")
if "hrms_addon.hrms_addon.employee_status.reconcile" not in (hooks.get("scheduler_events") or {}).get("daily", []):
    fail.append("the daily job puts right a System Status set without a save")
if (hooks.get("doctype_list_js") or {}).get("Employee") != "public/js/employee_list.js" \
        or not os.path.exists(os.path.join(PACKAGE, "public", "js", "employee_list.js")):
    fail.append("the Employee list script is listed and there")
if "hrms_addon.patches.v1_0.employee_statuses" not in read("hrms_addon", "patches.txt").split():
    fail.append("the patch that seeds Luuka's statuses is listed")
if "employee_status.install_luuka()" not in read("hrms_addon", "patches", "v1_0", "employee_statuses.py"):
    fail.append("the patch seeds Luuka's statuses")
glue = read("hrms_addon", "hrms_addon", "employee_status.py")
for name, needles in (("install", ("for name in rules.BASE:", "_make(name, name, True)", "reconcile()")),
                      ("install_luuka", ("install()", "for name, counts_as in rules.LUUKA:")),
                      ("employee_before_validate", ("rules.settle(", "no longer used", "doc.status = status")),
                      ("move", ("rules.moved(", "update_modified=False")),
                      ("reconcile", ("rules.drift(", "update_modified=False")),
                      ("exit_status", ("disabled()",))):
    for needle in needles:
        if needle not in body_of(glue, name):
            fail.append("employee_status.%s: %r" % (name, needle))
print("fixtures, hooks, patch: the Status field, System Status read-only, before_validate, the migrate, the daily job")

# ── 4. What moves a status ────────────────────────────────────────────
move_employee = body_of(read("hrms_addon", "hrms_addon", "suspensions.py"), "_move_employee")
if "employee_status.move(doc.employee, new)" not in move_employee or '"status", new' in move_employee:
    fail.append("a suspension moves the Status with the System Status")
inactive = body_of(read("hrms_addon", "hrms_addon", "exits.py"), "_make_inactive")
if 'employee_status.exit_status(doc.get("custom_reason"))' not in inactive \
        or inactive.index("exit_status") > inactive.index("employee.save()"):
    fail.append("an exit leaves the employee with the status for its reason, before the save")
theme = body_of(read("hrms_addon", "hrms_addon", "theme.py"), "boot_session")
if "bootinfo.hrms_addon_employee_statuses = employee_status.statuses()" not in theme:
    fail.append("the statuses come with the boot")
print("moves: a suspension, an exit, the boot")

# ── 5. The Employee form and list ─────────────────────────────────────
form = read("hrms_addon", "public", "js", "employee.js")
handler = re.search(r"custom_employee_status\(frm\) \{(.*?)\n\t\},", form, flags=re.S)
if not handler or 'frm.set_value("status", counts_as)' not in handler.group(1):
    fail.append("on the form, the Status picked sets the System Status at once (Left asks for its relieving date)")
if "frappe.boot.hrms_addon_employee_statuses" not in form \
        or 'frappe.db.get_value("Employee Status", status, "counts_as")' not in form:
    fail.append("the form reads what a status counts as from the boot, else the site")
listing = read("hrms_addon", "public", "js", "employee_list.js")
for needle in ('"custom_employee_status"', "settings.get_indicator = function (doc)",
               "frappes_own.call(this, doc)", '"custom_employee_status,=," + chosen',
               "frappe.boot.hrms_addon_employee_statuses"):
    if needle not in listing:
        fail.append("the Employee list: %r" % needle)
print("form and list: the System Status follows the Status; the indicator is the Status, in its colour")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL EMPLOYEE STATUS CHECKS PASSED")
