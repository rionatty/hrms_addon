"""Checks cancelling an advance run (Salary Advance Processing, Leave Advance
Processing), without a bench.

    python scripts/verify_advance_runs.py

  1  what a run's cancel does with its bank entry, and which salary slip
     has already taken a recovery
  2  the forms: every submitted document that names a run, its advances or
     its bank entry is left out of Frappe's "Cancel All Documents", because
     the run takes it back itself
  3  the order on the server: a deduction is let go of before it is
     cancelled, a draft bank entry before it is deleted, and a deleted
     run by the advances that named it
  4  wiring: the hooks, the form script for the bank entry, the run's
     on_trash, and the notice for a draft salary slip that still carries
     a cancelled deduction
  5  a deduction cancelled by itself: the row of the standing advance, loan
     or penalty lets go and remembers it, so nothing makes it again

Frappe refuses to cancel a document a submitted document names, and to
delete one anything names. Those refusals are what this guards against,
and a fake that cancels and deletes whatever it is told to cannot see
them: the walks that do (smoke_advance_run_cancel.py,
smoke_leave_run_cancel.py) put Frappe's rules on the fake first.

The rules are loaded without Frappe.
"""
import ast
import glob
import importlib.util
import io
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
fail = []


def check(condition, label):
    if not condition:
        fail.append(label)
        print("FAIL", label)


def read(*parts):
    return io.open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # proves it has no Frappe import
    return module


def function(source, name):
    """The source of one top-level function."""
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def before(text, first, second):
    return first in text and second in text and text.index(first) < text.index(second)


R = load("advance_run_rules")
SALARY, LEAVE = R.SALARY_RUN, R.LEAVE_RUN

# ── 1. the rules ────────────────────────────────────────────────────────
check([R.bank_entry_step(status, may) for status in (None, 0, 1, 2) for may in (False, True)] ==
      [R.NOTHING, R.NOTHING, R.DELETE, R.DELETE, R.REFUSE, R.CANCEL, R.NOTHING, R.NOTHING],
      "a draft bank entry is deleted, a posted one cancelled only by somebody who may, a cancelled one left")
check(R.bank_entry_step("1", True) == R.CANCEL and R.bank_entry_step("0", False) == R.DELETE,
      "whatever type the state comes in")
check(R.first_taken([("AS-1", "ADV-1"), ("AS-2", "ADV-2")], {"AS-2": "SLIP-9"}) == ("ADV-2", "SLIP-9"),
      "the advance a slip has taken a recovery of, with the slip")
check(R.first_taken([("AS-1", "ADV-1")], {}) is None and R.first_taken([], {"AS-1": "SLIP-9"}) is None,
      "nothing taken, nothing named")

# ── 2. the forms ────────────────────────────────────────────────────────
specs = {}
for path in glob.glob(os.path.join(APP, "doctype", "*", "*.json")):
    spec = json.load(io.open(path, encoding="utf-8"))
    if isinstance(spec, dict) and spec.get("doctype") == "DocType":
        specs[spec["name"]] = spec
custom = json.load(io.open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))
# Frappe HR's and ERPNext's own documents this app puts a Link on, all submitted on a site
SUBMITTED_UPSTREAM = {"Employee Advance", "Leave Application", "Additional Salary", "Journal Entry"}
tables = {(name, field["options"]) for name, spec in specs.items() for field in spec["fields"]
          if field["fieldtype"] == "Table"}
tables |= {(row["dt"], row["options"]) for row in custom if row.get("fieldtype") == "Table"}


def submitted(doctype):
    return bool(specs.get(doctype, {}).get("is_submittable")) or doctype in SUBMITTED_UPSTREAM


def naming(target):
    """The submitted documents with a Link to `target`, on themselves or on
    a row of one of their tables."""
    links = {(name, field["fieldname"]) for name, spec in specs.items() for field in spec["fields"]
             if field["fieldtype"] == "Link" and field.get("options") == target and field["fieldname"] != "amended_from"}
    links |= {(row["dt"], row["fieldname"]) for row in custom
              if row.get("fieldtype") == "Link" and row.get("options") == target}
    owners = set()
    for doctype, _field in links:
        parents = {parent for parent, child in tables if child == doctype} or {doctype}
        owners |= {parent for parent in parents if submitted(parent) and parent != target}
    return owners


def ignored(script):
    """What a form script adds to ignore_doctypes_on_cancel_all."""
    block = script.split("frm.ignore_doctypes_on_cancel_all = [", 1)[1].split("];", 1)[0]
    return set(re.findall(r'^\s*"([^"]+)",\s*$', block, re.M))


FORMS = {SALARY: read("hrms_addon", "hrms_addon", "doctype", "salary_advance_processing",
                      "salary_advance_processing.js"),
         LEAVE: read("hrms_addon", "hrms_addon", "doctype", "leave_advance_processing",
                     "leave_advance_processing.js")}
for run, script in FORMS.items():
    check("...(frm.ignore_doctypes_on_cancel_all || [])" in script and "setup(frm)" in script,
          "%s: the form adds to the Cancel All exceptions as it is set up" % run)
    check(ignored(script) == set(R.TAKEN_BACK[run]), "%s: exactly what the run takes back: %s"
          % (run, sorted(ignored(script))))
    check(naming(run) <= set(R.TAKEN_BACK[run]), "%s: every submitted document that names the run: %s"
          % (run, sorted(naming(run))))
check(naming(SALARY) == {"Employee Advance"} and naming(LEAVE) == {"Leave Advance"},
      "an advance names its run: %s, %s" % (sorted(naming(SALARY)), sorted(naming(LEAVE))))

entry_form = read("hrms_addon", "public", "js", "journal_entry.js")
check(ignored(entry_form) == set(R.BANK_ENTRY_KEPT_BY) and "...(frm.ignore_doctypes_on_cancel_all || [])" in entry_form,
      "the bank entry's form keeps ERPNext's exceptions and adds the runs: %s" % sorted(ignored(entry_form)))
ours = {SALARY, LEAVE, "Employee Advance", "Leave Advance"}
check(naming("Journal Entry") & ours <= set(R.BANK_ENTRY_KEPT_BY),
      "every run and advance that names its bank entry: %s" % sorted(naming("Journal Entry") & ours))
check({SALARY, LEAVE} <= naming("Journal Entry"), "both runs name their bank entry")

# ── 3. the order on the server ──────────────────────────────────────────
glue = read("hrms_addon", "hrms_addon", "advance_runs.py")
take_back = function(glue, "take_back_bank_entry")
check(before(take_back, 'doc.db_set("journal_entry", None', "frappe.delete_doc(ENTRY, name"),
      "a draft bank entry is deleted after the run lets go of it")
check("frappe.get_doc(ENTRY, name)._cancel()" in take_back and "ignore_permissions" not in take_back.split(
    "rules.DELETE")[0], "a posted bank entry is cancelled under the user's own permission")
check(".cancel()" not in take_back, "and there and then: ERPNext's own cancel queues an entry of more than 100 lines")
check('frappe.has_permission(ENTRY, "cancel", name)' in take_back and "rules.REFUSE" in take_back,
      "and refused to somebody who may not cancel bank entries")
check("rules.BANK_ENTRY_KEPT_BY" in function(glue, "journal_on_cancel")
      and 'doc.get("ignore_linked_doctypes")' in function(glue, "journal_on_cancel"),
      "Finance cancelling the bank entry: the run is added to what ERPNext already leaves out")

salary = read("hrms_addon", "hrms_addon", "salary_advances.py")
on_cancel = function(salary, "run_on_cancel")
check(before(on_cancel, "advance_runs.recovered_on(ADVANCE, made)", "advance_runs.take_back_bank_entry(doc, RUN)")
      and before(on_cancel, "advance_runs.take_back_bank_entry(doc, RUN)", "advance.cancel()"),
      "salary advance run: a recovery already taken stops it; then the bank entry, then the advances")
on_trash = function(salary, "run_on_trash")
check('"custom_salary_advance_run": doc.name' in on_trash and '"custom_salary_advance_run", None' in on_trash,
      "a deleted run is let go of by the advances that named it")

leave = read("hrms_addon", "hrms_addon", "leave_advances.py")
on_cancel = function(leave, "run_on_cancel")
check(before(on_cancel, "_take_back_payment(doc.name)", "advance_runs.take_back_bank_entry(doc, RUN)")
      and before(on_cancel, "advance_runs.take_back_bank_entry(doc, RUN)", '"processing": None'),
      "leave advance run: the deductions, then the bank entry, then the advances wait again")
check("_take_back_payment(run)" in function(leave, "payment_on_cancel"),
      "the bank entry cancelled on its own takes the payment back the same way")

LET_GO = (("advances.py", "unschedule_beyond_paid", 'row.db_set("additional_salary", None'),
          ("leave_advances.py", "_take_back_payment", 'row.db_set("additional_salary", None'),
          ("loans.py", "_cancel_untaken", 'frappe.db.set_value(ROW, row.name, "additional_salary", None'))
for filename, name, let_go in LET_GO:
    body = function(read("hrms_addon", "hrms_addon", filename), name)
    check(before(body, let_go, "deduction.cancel()"),
          "%s %s: the row lets go of its deduction before the deduction is cancelled" % (filename, name))

# ── 4. wiring ───────────────────────────────────────────────────────────
hooks = {}
exec(compile(read("hrms_addon", "hooks.py"), "hooks.py", "exec"), hooks)
listed = hooks["doc_events"]["Journal Entry"]["on_cancel"]
check("hrms_addon.hrms_addon.advance_runs.journal_on_cancel" in listed, "the bank entry's cancel is hooked: %s" % listed)
check({"hrms_addon.hrms_addon.advances.payment_on_cancel", "hrms_addon.hrms_addon.leave_advances.payment_on_cancel"}
      <= set(listed), "beside what takes the payment back")
check(hooks["doctype_js"].get("Journal Entry") == "public/js/journal_entry.js"
      and os.path.exists(os.path.join(PACKAGE, "public", "js", "journal_entry.js")), "the bank entry's form script is loaded")
controller = read("hrms_addon", "hrms_addon", "doctype", "salary_advance_processing", "salary_advance_processing.py")
check("def on_trash(self):" in controller and "salary_advances.run_on_trash(self)" in controller
      and "salary_advances.run_on_cancel(self)" in controller, "the salary advance run's on_cancel and on_trash")
check("leave_advances.run_on_cancel(self)" in read("hrms_addon", "hrms_addon", "doctype", "leave_advance_processing",
                                                    "leave_advance_processing.py"), "the leave advance run's on_cancel")
check("import frappe" in glue and "import frappe" not in read("hrms_addon", "hrms_addon", "advance_run_rules.py"),
      "the rules stay free of Frappe")
notice = function(read("hrms_addon", "hrms_addon", "recoveries.py"), "addition_on_cancel")
check(hooks["doc_events"]["Additional Salary"]["on_cancel"] == "hrms_addon.hrms_addon.recoveries.addition_on_cancel"
      and '"docstatus": 0' in notice and '"additional_salary": doc.name' in notice and "frappe.msgprint(" in notice
      and "frappe.throw(" not in notice,
      "a draft salary slip that still carries a cancelled deduction is named, and holds nothing up")


# ── 5. a deduction cancelled by itself ──────────────────────────────────
# Luuka, 1 Nov 2026: "its should allow canceling". On a stand-in for Frappe; the
# walks put Frappe's own link rules on theirs (smoke_advance_run_cancel.py).
class Row(dict):
    __getattr__ = dict.get


def matches(row, filters):
    for field, wanted in (filters or {}).items():
        value = row.get(field)
        if isinstance(wanted, list):
            if (wanted[0] == "in" and value not in wanted[1]) or (wanted[0] == "!=" and (value or 0) == wanted[1]):
                return False
        elif value != wanted:
            return False
    return True


def recoveries_on(rows, docstatus):
    """recoveries.py on a site of these {table: [rows]}, and what it told."""
    told = []
    site = types.ModuleType("frappe")
    site._ = lambda text: text
    utils = types.ModuleType("frappe.utils")
    utils.today = lambda: "2026-11-01"
    site.utils = utils

    def get_all(doctype, filters=None, fields=None, pluck=None, **_kwargs):
        found = [Row(row) for row in rows.get(doctype, []) if matches(row, filters)]
        return [row[pluck] for row in found] if pluck else found

    def set_value(doctype, name, values, update_modified=True):
        check(update_modified is False, "a row let go of does not move the document it is on")
        next(row for row in rows[doctype] if row["name"] == name).update(values)

    site.get_all, site.msgprint = get_all, lambda message, **_kwargs: told.append(message)
    site.whitelist = lambda *_a, **_k: (lambda function_: function_)
    site.db = types.SimpleNamespace(get_value=lambda doctype, name, field: docstatus[(doctype, name)], set_value=set_value)
    sys.modules.update({"frappe": site, "frappe.utils": utils})
    return load("recoveries"), told


TABLES = {"Advance Recovery": "advance_recovery", "Leave Advance Recovery": "leave_advance_recovery",
          "Loan Repayment": "loan_repayment"}
PARENTS = {"Advance Recovery": ("Employee Advance",), "Leave Advance Recovery": ("Leave Advance",),
           "Loan Repayment": ("Employee Loan", "Employee Penalty")}
for table, parents in PARENTS.items():
    for parent in parents:
        rows = {table: [{"name": "R1", "parent": "D1", "parenttype": parent, "additional_salary": "AS-1", "recovered": 0},
                        {"name": "R2", "parent": "D1", "parenttype": parent, "additional_salary": "AS-2", "recovered": 0}]}
        module, told = recoveries_on(rows, {(parent, "D1"): 1})
        module.addition_on_cancel(Row(doctype="Additional Salary", name="AS-1", salary_component="Advance Recovery"))
        check((rows[table][0]["additional_salary"], rows[table][0].get("cancelled_deduction")) == (None, "AS-1"),
              "%s: the row of a standing %s lets go, and keeps the name of what was cancelled" % (table, parent))
        check(rows[table][1]["additional_salary"] == "AS-2" and not rows[table][1].get("cancelled_deduction"),
              "%s: and no other month does" % table)
        check(told == ["AS-1 will not be deducted. It stays outstanding on D1."], "%s: and they are told" % table)
        rows[table].append({"name": "R3", "parent": "D1", "parenttype": parent, "additional_salary": None,
                            "cancelled_deduction": "AS-1"})
        amount = module.INSTALMENT[table]
        module.addition_on_submit(Row(doctype="Additional Salary", name="AS-9", amended_from="AS-1", amount=5,
                                      payroll_date="2026-12-25"))
        check((rows[table][0]["additional_salary"], rows[table][0].get("cancelled_deduction"),
               rows[table][0]["payroll_date"], rows[table][0][amount]) == ("AS-9", None, "2026-12-25", 5),
              "%s: amended, the new deduction takes the month, at its date and amount" % table)
        before_plain = json.dumps(rows, sort_keys=True)
        module.addition_on_submit(Row(doctype="Additional Salary", name="AS-8", amount=7, payroll_date="2026-12-25"))
        check(json.dumps(rows, sort_keys=True) == before_plain, "%s: a new deduction touches no row" % table)
    rows = {table: [{"name": "R1", "parent": "D1", "parenttype": parents[0], "additional_salary": "AS-1", "recovered": 0}]}
    module, told = recoveries_on(rows, {(parents[0], "D1"): 2})
    module.addition_on_cancel(Row(doctype="Additional Salary", name="AS-1", salary_component="X"))
    check(rows[table][0]["additional_salary"] == "AS-1" and not rows[table][0].get("cancelled_deduction") and not told,
          "%s: a document being cancelled has taken its deductions back itself, nothing to tell" % table)
    rows = {table: [{"name": "R1", "parent": "D1", "parenttype": parents[0], "additional_salary": "AS-1", "recovered": 1}]}
    module, told = recoveries_on(rows, {(parents[0], "D1"): 1})
    module.addition_on_cancel(Row(doctype="Additional Salary", name="AS-1", salary_component="X"))
    check(rows[table][0]["additional_salary"] == "AS-1" and not told, "%s: a month recovered does not let go" % table)
    check(sorted(module.SCHEDULES.items()) == sorted(PARENTS.items()) and set(module.INSTALMENT) == set(PARENTS),
          "every table a deduction is kept in is let go of")
    source = json.loads(read("hrms_addon", "hrms_addon", "doctype", TABLES[table], TABLES[table] + ".json"))
    field = next((one for one in source["fields"] if one["fieldname"] == module.CANCELLED), {})
    check((field.get("fieldtype"), field.get("read_only"), field.get("no_copy")) == ("Data", 1, 1)
          and module.CANCELLED in source["field_order"],
          "%s: the name is kept in a Data field nobody types in: a Link to it would hold the cancel" % table)
    check(source["modified"] >= "2026-11-01", "%s: its modified moves on, or migrate keeps the old table" % table)
    check(module.INSTALMENT[table] in {one["fieldname"] for one in source["fields"]}, "%s: its amount field" % table)
sys.modules.pop("frappe", None)
sys.modules.pop("frappe.utils", None)

check(hooks["doc_events"]["Additional Salary"].get("on_submit") == "hrms_addon.hrms_addon.recoveries.addition_on_submit",
      "the amended deduction reaches the row")
check(module.INSTALMENT == {"Loan Repayment": "total", "Advance Recovery": "amount", "Leave Advance Recovery": "amount"}
      and "sum(flt(child.total) for child in doc.repayments if child.recovered)" in read("hrms_addon", "hrms_addon", "loans.py")
      and "sum(flt(row.total) for row in doc.get(\"repayments\") or [] if row.recovered)" in read(
          "hrms_addon", "hrms_addon", "penalties.py")
      and "sum(flt(child.amount) for child in doc.get(\"custom_recoveries\") or [] if child.recovered)" in read(
          "hrms_addon", "hrms_addon", "advances.py")
      and "sum(flt(row.amount) for row in doc.get(\"recoveries\") or [] if row.recovered)" in read(
          "hrms_addon", "hrms_addon", "leave_advances.py"),
      "an amended amount goes in the field each document sums what it has recovered from")
for path, needle, why in (
    (("advances.py",), 'if not (row.additional_salary or row.recovered or row.get("cancelled_deduction"))]',
     "an advance's payment does not make it again"),
    (("advances.py",), 'if any(not (row.additional_salary or row.recovered or row.get("cancelled_deduction"))',
     "nor the daily job, which would take it as waiting"),
    (("leave_advances.py",), 'if row.additional_salary or row.recovered or row.get("cancelled_deduction"):',
     "nor a leave advance"),
    (("loans.py",), 'if row.get("additional_salary") or row.get("recovered") or row.get("cancelled_deduction"):',
     "nor a loan"),
    (("penalties.py",), 'if row.additional_salary or row.recovered or row.get("cancelled_deduction"):', "nor a penalty"),
    (("home_panels.py",), '"cancelled_deduction": ["is", "not set"]},', "the desk does not count it as not posted"),
):
    check(needle in read("hrms_addon", "hrms_addon", *path), why)
check("!row.additional_salary && !row.recovered && !row.cancelled_deduction" in read(
    "hrms_addon", "public", "js", "employee_advance.js"), "the advance's form does not say it waits for the payment")
check(hooks["doctype_js"].get("Additional Salary") == "public/js/additional_salary.js", "the deduction's form script")
form = read("hrms_addon", "public", "js", "additional_salary.js")
check("frm.ignore_doctypes_on_cancel_all" in form and all('"%s",' % parent in form for parents in PARENTS.values()
                                                         for parent in parents),
      "its Cancel does not offer to cancel what the deduction recovers")
upstream = os.path.join(os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext")), "frappe", "frappe")
if os.path.exists(upstream):
    document = io.open(os.path.join(upstream, "model", "document.py"), encoding="utf-8").read()
    check('self.run_method("on_cancel")\n\t\t\tself.check_no_back_links_exist()' in document.replace("\r\n", "\n"),
          "Frappe runs on_cancel before it looks for what names the document: that is what lets the row let go")
    check("ignore_doctypes_on_cancel_all" in io.open(os.path.join(upstream, "public", "js", "frappe", "form", "form.js"),
                                                     encoding="utf-8").read(),
          "Frappe's form leaves these out of Cancel All Documents")
else:
    print("Frappe's own code: NOT CHECKED, it was not found under %s" % upstream)

print()
print("FAILED: %d" % len(fail) if fail else "ALL ADVANCE RUN CHECKS PASSED")
sys.exit(1 if fail else 0)
