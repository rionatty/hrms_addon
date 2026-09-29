"""Verify the salary structure glue, without a bench:

    python scripts/verify_salary_structures.py

Frappe HR's Salary Structure and Salary Structure Assignment, once other
documents point at them (salary_structure_rules.py, salary_structures.py):

  1  the rules: the rows a save adds and takes off, what a new row takes
     from its component, what is refused, which assignment replaces which
  2  wiring: the doc events, the form scripts, the property setters
  3  upstream: the Frappe and Frappe HR behaviour the fix stands on

Frappe HR's, ERPNext's and Frappe's own files are read from FRAPPE_APPS_ROOT
(default ../ERPNext).
"""
import ast
import glob
import importlib.util
import re
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def read(*parts):
    return open(os.path.join(*parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def upstream(*parts):
    return read(APPS_ROOT, *parts)


def doctype_fields(path):
    return {field["fieldname"]: field for field in json.load(open(path, encoding="utf-8"))["fields"]}


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


R = load("salary_structure_rules")
print("loaded salary_structure_rules.py without Frappe")

# ── 1. The rules ──────────────────────────────────────────────────────
BEFORE = {"earnings": [{"name": "r1", "idx": 1, "salary_component": "Basic"},
                       {"name": "r2", "idx": 2, "salary_component": "Airtime"}],
          "deductions": [{"name": "r3", "idx": 1, "salary_component": "PAYEE"}]}
NEW = {"name": None, "idx": 3, "salary_component": "Car Benefit"}
NOW = {"earnings": BEFORE["earnings"] + [NEW], "deductions": BEFORE["deductions"]}
if R.added_rows(BEFORE, NOW) != {"earnings": [NEW]}:
    fail.append("a row the save brings is the one added: %s" % R.added_rows(BEFORE, NOW))
if R.removed_rows(BEFORE, NOW):
    fail.append("adding a row takes nothing off: %s" % R.removed_rows(BEFORE, NOW))
if R.removed_rows(BEFORE, {"earnings": BEFORE["earnings"][:1], "deductions": BEFORE["deductions"]}) \
        != [("earnings", 2, "Airtime")]:
    fail.append("a row the save leaves out is taken off, and named")
if R.removed_rows(BEFORE, {"earnings": BEFORE["earnings"], "deductions": []}) != [("deductions", 1, "PAYEE")]:
    fail.append("the deductions are watched too")
if R.added_rows(BEFORE, BEFORE) or R.removed_rows(BEFORE, BEFORE):
    fail.append("a save that changes no row adds and takes off nothing")

COMPONENT = {"type": "Earning", "disabled": 0, "depends_on_payment_days": 1, "variable_based_on_taxable_salary": 0,
             "is_tax_applicable": 1, "is_flexible_benefit": 0, "amount_based_on_formula": 1,
             "formula": "base * 0.1", "amount": 0}
filled = R.defaults_for({"salary_component": "Car Benefit"}, COMPONENT)
if filled.get("formula") != "base * 0.1" or filled.get("amount_based_on_formula") != 1 \
        or filled.get("depends_on_payment_days") != 1 or filled.get("is_tax_applicable") != 1:
    fail.append("a row with nothing of its own takes its component's formula and flags: %s" % filled)
own = R.defaults_for({"salary_component": "Car Benefit", "formula": "B * 0.2", "depends_on_payment_days": 1},
                     COMPONENT)
if "formula" in own or "amount" in own or own.get("is_tax_applicable") != 1:
    fail.append("a row with its own formula keeps it and still takes the component's flags: %s" % own)
if R.defaults_for({"salary_component": "X"}, None) != {}:
    fail.append("a row with no component takes nothing")

GOOD = {"idx": 3, "salary_component": "Car Benefit", "formula": "base * 0.1"}
expect("a good earning added", R.row_errors("earnings", GOOD, COMPONENT, ["Basic", "Airtime"]))
expect("a row with no component", R.row_errors("earnings", {"idx": 3}, None, []), "choose the salary component")
expect("a component that is not there", R.row_errors("earnings", GOOD, None, []), "no salary component")
expect("a disabled component", R.row_errors("earnings", GOOD, dict(COMPONENT, disabled=1), []), "is disabled")
expect("a deduction among the earnings", R.row_errors("earnings", GOOD, dict(COMPONENT, type="Deduction"), []),
       "is a deduction, not an earning")
expect("an earning among the employer's contributions",
       R.row_errors("employer_contributions", GOOD, COMPONENT, []), "not an employer contribution")
expect("a component already on the structure", R.row_errors("earnings", GOOD, COMPONENT, ["Car Benefit"]),
       "already on the structure")
expect("a tax-slab component given a formula",
       R.row_errors("deductions", dict(GOOD, variable_based_on_taxable_salary=1),
                    dict(COMPONENT, type="Deduction"), []), "worked out from the taxable salary")
expect("a formula counting payment days twice",
       R.row_errors("earnings", dict(GOOD, formula="B * 0.1", depends_on_payment_days=1), COMPONENT, [], ["B"]),
       "cut twice")
expect("an abbreviation only inside another word",
       R.row_errors("earnings", dict(GOOD, formula="BS * 0.1", depends_on_payment_days=1), COMPONENT, [], ["B"]))
expect("a formula on a payment-days component, in a row not cut by payment days itself",
       R.row_errors("earnings", dict(GOOD, formula="B * 0.1", depends_on_payment_days=0), COMPONENT, [], ["B"]))

if R.totals([500000, None, "20000"], [30000], 0) != {"total_earning": 520000.0, "total_deduction": 30000.0,
                                                    "net_pay": 490000.0}:
    fail.append("the totals are the rows' fixed amounts, as the form adds them: %s"
                % R.totals([500000, None, "20000"], [30000], 0))
if R.totals([500000], [30000], 1)["net_pay"] != 0.0:
    fail.append("a structure paid from timesheets has no net pay, as the form leaves it")
if R.totals([], [], 0) != {"total_earning": 0.0, "total_deduction": 0.0, "net_pay": 0.0}:
    fail.append("no rows, no totals")

OLD = {"name": "SSA-1", "employee": "E1", "from_date": "2026-10-01", "amended_from": None}
if not R.replaced(OLD, {"name": "SSA-1-1", "employee": "E1", "from_date": "2026-11-01", "amended_from": "SSA-1"}):
    fail.append("an amendment takes the cancelled assignment's place")
if not R.replaced(OLD, {"name": "SSA-2", "employee": "E1", "from_date": "2026-10-01", "amended_from": None}):
    fail.append("a new assignment for the same employee from the same date takes its place")
if R.replaced(OLD, {"name": "SSA-3", "employee": "E1", "from_date": "2027-01-01", "amended_from": None}):
    fail.append("an assignment from another date is a change of pay, not a replacement")
if R.replaced(OLD, {"name": "SSA-4", "employee": "E2", "from_date": "2026-10-01", "amended_from": None}):
    fail.append("another employee's assignment replaces nothing of this one")
if R.replaced(OLD, OLD) or R.replaced(None, OLD):
    fail.append("an assignment does not replace itself, nor nothing")
print("rules: rows added and taken off, a new row filled from its component, what is refused, what replaces what")

# ── 2. Wiring ─────────────────────────────────────────────────────────
hooks = {}
for node in ast.parse(read(PACKAGE, "hooks.py")).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
events = hooks.get("doc_events") or {}
for doctype, event, handler in (
        ("Salary Structure Assignment", "on_cancel", "salary_structures.keep_records"),
        ("Salary Structure Assignment", "on_submit", "salary_structures.follow_replacement"),
        ("Salary Structure Assignment", "validate", "grades.assignment_validate"),
        ("Salary Structure", "on_cancel", "salary_structures.keep_records"),
        ("Salary Structure", "before_update_after_submit", "salary_structures.rows_after_submit")):
    wired = (events.get(doctype) or {}).get(event)
    wired = wired if isinstance(wired, list) else [wired]
    if "hrms_addon.hrms_addon." + handler not in wired:
        fail.append("hooks.py: %s %s must run %s" % (doctype, event, handler))
scripts = hooks.get("doctype_js") or {}
for doctype, path in (("Salary Structure Assignment", "public/js/salary_structure_assignment.js"),
                      ("Salary Structure", "public/js/salary_structure.js")):
    if scripts.get(doctype) != path:
        fail.append("hooks.py: %s's form script is %s" % (doctype, path))
        continue
    script = read(PACKAGE, *path.split("/"))
    for record in R.RECORDS:
        if '"%s"' % record not in script or "frm.ignore_doctypes_on_cancel_all" not in script:
            fail.append("%s leaves %s off the Cancel All list" % (path, record))
structure_script = read(PACKAGE, "public", "js", "salary_structure.js")
if 'frm.set_df_property(table, "cannot_delete_rows", submitted)' not in structure_script or \
        any('"%s"' % table not in structure_script for table in R.TABLES):
    fail.append("a submitted structure's tables offer no row to delete")
setters = json.load(open(os.path.join(PACKAGE, "fixtures", "property_setter.json"), encoding="utf-8"))
listed = read(PACKAGE, "hooks.py")
for field in R.TABLES + R.TOTALS:
    name = "Salary Structure-%s-allow_on_submit" % field
    found = next((row for row in setters if row["name"] == name), None)
    if not found or (found["doc_type"], found["field_name"], found["property"], str(found["value"])) \
            != ("Salary Structure", field, "allow_on_submit", "1"):
        fail.append("a submitted structure's %s changes with its rows: %s" % (field, name))
    if '"%s",' % name not in listed:
        fail.append("hooks.py's fixture filter names %s" % name)
glue = read(APP, "salary_structures.py")
for needle, why in (
    ("doc.ignore_linked_doctypes = tuple(doc.get(\"ignore_linked_doctypes\") or ()) + rules.RECORDS",
     "the cancel keeps whatever links it already ignores"),
    ("rules.replaced(row, mine)", "which assignment is replaced is the rules' to say"),
    ("for doctype, field in rules.ASSIGNMENT_LINKS:", "every record that keeps an assignment follows it"),
    ("frappe.db.set_value(doctype, name, field, doc.name, update_modified=False)",
     "a record is pointed at the new assignment without being saved again"),
    ("before = doc.get_doc_before_save()", "what is added and taken off is read against the saved structure"),
    ("gone = rules.removed_rows(had, now)", "a row taken off is found"),
    ("rules.defaults_for(row.as_dict(), component)", "a new row takes what its component gives it"),
    ("rules.row_errors(table, row.as_dict(), component, others[table], abbrs)", "and is checked"),
    ("if not row.is_new()] +", "only the rows the save brings are new"),
    ("row._formula = row.formula", "a formula filled in from the component outlives Frappe HR's reset"),
    ("doc.update(rules.totals(", "the totals follow the rows added"),
):
    if needle not in glue:
        fail.append("salary_structures.py: %s (%r not found)" % (why, needle))
fields = dict(doctype_fields(os.path.join(APP, "doctype", "employee_position_change", "employee_position_change.json")))
custom = {(row["dt"], row["fieldname"]) for row in
          json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))}
for doctype, field in R.ASSIGNMENT_LINKS:
    exists = (doctype, field) in custom or (doctype == "Employee Position Change" and field in fields)
    if not exists:
        fail.append("%s has no %s to keep its assignment in" % (doctype, field))
# every submitted document of the app's that names an assignment or a
# structure would stop its cancel: each must be a record the cancel leaves be
KEPT = ("Salary Structure Assignment", "Salary Structure")
naming = {row["dt"] for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"),
                                              encoding="utf-8"))
          if row.get("fieldtype") == "Link" and row.get("options") in KEPT}
for path in glob.glob(os.path.join(APP, "doctype", "*", "*.json")):
    spec = json.load(open(path, encoding="utf-8"))
    if spec.get("doctype") == "DocType" and spec.get("is_submittable") and \
            any(f.get("fieldtype") == "Link" and f.get("options") in KEPT for f in spec.get("fields", [])):
        naming.add(spec["name"])
if naming != set(R.RECORDS):
    fail.append("the records the cancel leaves be are every submitted document naming an assignment or a "
                "structure: %s, not %s" % (sorted(naming), sorted(R.RECORDS)))
print("wiring: the cancel and submit events, the after-submit check, both form scripts, the setters")

# ── 3. Upstream ───────────────────────────────────────────────────────
utils = upstream("hrms", "hrms", "payroll", "utils.py")
if 'COMPONENT_PARENTFIELDS = ("earnings", "deductions", "employer_contributions")' not in utils:
    fail.append("Frappe HR's component tables are no longer %s" % (R.TABLES,))
detail = doctype_fields(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_detail",
                                     "salary_detail.json"))
component = doctype_fields(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_component",
                                        "salary_component.json"))
for field in R.FROM_COMPONENT + R.IF_MISSING + ("salary_component", "abbr"):
    if field not in detail:
        fail.append("Salary Detail has no %s" % field)
for field in R.COMPONENT_FIELDS:
    if field not in component:
        fail.append("Salary Component has no %s" % field)
if set(R.TYPE_FOR.values()) - set((component.get("type") or {}).get("options", "").split("\n")):
    fail.append("a table's component type is one Frappe HR offers: %s" % sorted(R.TYPE_FOR.values()))
structure = doctype_fields(os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "salary_structure",
                                        "salary_structure.json"))
if [table for table in R.TABLES if (structure.get(table) or {}).get("options") != "Salary Detail"]:
    fail.append("Salary Structure's component tables are Salary Detail tables")
for field in R.TOTALS + ("salary_slip_based_on_timesheet",):
    if field not in structure:
        fail.append("Salary Structure has no %s" % field)
form = upstream("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.js")
body = form[form.find("var calculate_totals = function"):]
body = body[:body.find("\n};")]
if not body or set(re.findall(r"\bdoc\.(\w+) = ", body)) != set(R.TOTALS) or \
        set(R.totals([], [], 0)) != set(R.TOTALS):
    fail.append("the totals that follow the rows are those the form works out: %s, not %s"
                % (sorted(set(re.findall(r"\bdoc\.(\w+) = ", body))), sorted(R.TOTALS)))
for field in R.TOTALS:
    if (structure.get(field) or {}).get("allow_on_submit"):
        fail.append("Frappe HR lets %s change after submit now: its setter can go" % field)
for path, needle, why in (
    (("frappe", "frappe", "model", "delete_doc.py"),
     'if method == "Cancel" and (doc_ignore_flags := doc.get("ignore_linked_doctypes")):',
     "a cancel passes the links its document says to ignore"),
    (("frappe", "frappe", "model", "document.py"),
     'self.run_method("on_cancel")\n\t\t\tself.check_no_back_links_exist()',
     "on_cancel runs before the links are checked, so keep_records is in time"),
    (("frappe", "frappe", "model", "document.py"),
     "if d.is_new() and self.meta.get_field(d.parentfield).allow_on_submit:",
     "a new row in a table that allows it is not refused after submit"),
    (("frappe", "frappe", "desk", "form", "linked_with.py"),
     "ignore_doctypes_on_cancel_all and parent_dt in ignore_doctypes_on_cancel_all",
     "Cancel All leaves out the doctypes the form names, and what hangs from them"),
    (("frappe", "frappe", "public", "js", "frappe", "form", "form.js"),
     "ignore_doctypes_on_cancel_all: me.ignore_doctypes_on_cancel_all",
     "the form sends its list with the cancel"),
    (("frappe", "frappe", "public", "js", "frappe", "form", "grid.js"),
     "if (this.df.cannot_delete_rows) {", "a table can hide its delete buttons"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.py"),
     "def before_update_after_submit(self):\n\t\tself.sanitize_condition_and_formula_fields()",
     "Frappe HR tidies the formulas of a submitted structure before our check reads them"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.py"),
     "row._formula, row.formula = row.formula, sanitize_expression(row.formula)",
     "it keeps each formula as read in row._formula"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.py"),
     "def on_update_after_submit(self):\n\t\tself.reset_condition_and_formula_fields()",
     "and puts it back once a submitted structure is saved"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.py"),
     "row.formula = row._formula\n\n\t\tself.db_update_all()", "writing it to the database"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.js"),
     "amount: function (frm) {\n\t\tcalculate_totals(frm.doc);",
     "the form works the totals out again when a row's amount is set"),
    (("hrms", "hrms", "payroll", "doctype", "salary_structure", "salary_structure.js"),
     "doc.net_pay = 0.0;\n\tif (doc.salary_slip_based_on_timesheet == 0) {\n"
     "\t\tdoc.net_pay = flt(total_earn) - flt(total_ded);",
     "as rules.totals does"),
):
    if needle not in upstream(*path):
        fail.append("%s: %s (%r not found)" % ("/".join(path), why, needle))
print("upstream: Frappe's cancel honours the ignored links, a new row is let through, Cancel All leaves "
      "out the named doctypes")

print()
if fail:
    print("FAILURES:")
    for f in fail:
        print("  -", f)
    sys.exit(1)
print("ALL SALARY STRUCTURE CHECKS PASSED")
