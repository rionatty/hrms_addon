"""Verify Recreate Salary Slips on a payroll, without a bench:

    python scripts/verify_payroll_recreate.py

payroll_entries.py deletes a submitted payroll's draft slips and makes them
again on the same payroll (rules: payroll_entry_rules.py; the button:
public/js/payroll_entry.js):

  1  the rules: only a submitted payroll, not while slips are being made,
     never once a slip is submitted or the payroll posted
  2  the glue, on a stand-in for Frappe: refused as the rules say; else
     Queued at once and the work in the background, drafts only, then Frappe
     HR's own Create Salary Slips; a failure shown as Frappe HR shows one
  3  the button and its wiring
  4  upstream: Frappe HR's statuses, Create Salary Slips, its failure log and
     its refresh are still what the button stands on
"""
import ast
import importlib.util
import os
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(condition, label, detail=""):
    if not condition:
        fail.append("%s%s" % (label, ("   <- %s" % (detail,)) if detail != "" else ""))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 1. The rules ──────────────────────────────────────────────────────
rules = load("payroll_entry_rules", os.path.join(APP, "payroll_entry_rules.py"))
why = rules.why_not_recreate
check(why(1, "Submitted", 0, 0, 0) is None and why(1, "Failed", 0, 0, 0) is None,
      "a submitted payroll whose slips are drafts, or whose making failed, may make them again")
check("submitted payroll" in (why(0, "Draft", 0, 0, 0) or "") and "submitted payroll" in (why(2, "Cancelled", 0, 0, 0) or ""),
      "a draft or a cancelled payroll may not")
check("being made" in (why(1, "Queued", 0, 0, 0) or ""), "nor while slips are being made")
check("Cancel the payroll" in (why(1, "Submitted", 1, 0, 0) or "") and "Cancel the payroll" in (why(1, "Submitted", 0, 3, 0) or ""),
      "nor once a slip is submitted: the payroll is cancelled as Frappe HR does it")
check("posted" in (why(1, "Submitted", 0, 0, 1) or ""), "nor once the payroll is posted")
print("rules: a submitted payroll with draft slips only, not while slips are made, never once submitted or posted")


# ── 2. The glue, on a stand-in for Frappe ─────────────────────────────
class Thrown(Exception):
    pass


class Run:
    def __init__(self, site, docstatus=1, status="Submitted", submitted_flag=0):
        self.site, self.name, self.docstatus, self.status = site, "HR-PRUN-2026-00016", docstatus, status
        self.salary_slips_submitted, self.salary_slips_created, self.error_message = submitted_flag, 1, ""

    def check_permission(self, ptype):
        self.site.log.append(("permission", ptype))

    def db_set(self, values):
        self.site.log.append(("db_set", dict(values)))
        for field, value in values.items():
            setattr(self, field, value)

    def reload(self):
        self.site.log.append(("reload",))

    def create_salary_slips(self):
        self.site.log.append(("create",))
        if self.site.create_fails:
            raise RuntimeError("Please set account in Salary Component Basic")


class Site:
    def __init__(self, run_kwargs=None, slips=None, journals=0, create_fails=False, closed=False, unverified=False):
        self.log, self.create_fails, self.closed, self.unverified = [], create_fails, closed, unverified
        self.slips = slips if slips is not None else {"S1": 0, "S2": 0, "S3": 0}
        self.journals = journals
        self.run = Run(self, **(run_kwargs or {}))

    def frappe(self):
        site = self
        frappe = types.ModuleType("frappe")
        frappe.whitelist = lambda **kwargs: (lambda function: function)
        frappe._ = lambda text: text
        frappe.get_doc = lambda doctype, name: site.run

        def throw(message, title=None):
            raise Thrown(message)

        def count(doctype, filters):
            return sum(1 for status in site.slips.values() if status == filters["docstatus"])

        def get_all(doctype, filters=None, pluck=None, distinct=False):
            if doctype == "Journal Entry Account":
                return ["JV-%d" % index for index in range(site.journals)]
            return [name for name, status in site.slips.items() if status == filters["docstatus"]]

        def delete_doc(doctype, name):
            site.log.append(("delete", name))
            site.slips.pop(name)

        frappe.throw = throw
        frappe.get_all = get_all
        frappe.delete_doc = delete_doc
        frappe.enqueue = lambda method, **kwargs: site.log.append(("enqueue", method, kwargs))
        frappe.db = types.SimpleNamespace(count=count, commit=lambda: site.log.append(("commit",)),
                                          rollback=lambda: site.log.append(("rollback",)))
        payroll_entry = types.ModuleType("hrms.payroll.doctype.payroll_entry.payroll_entry")
        payroll_entry.log_payroll_failure = lambda process, run, error: (
            site.log.append(("failed", process, str(error))), run.db_set({"status": "Failed", "error_message": str(error)}))
        hrms = types.ModuleType("hrms_addon.hrms_addon")
        hrms.payroll_entry_rules = rules

        def refuse_closed(run):
            if site.closed:
                raise Thrown("closed")

        hrms.payroll_months = types.SimpleNamespace(refuse_closed=refuse_closed)

        # each branch verifies the days first (attendance_verification.py)
        def refuse_payroll(run):
            if site.unverified:
                raise Thrown("not verified")

        hrms.attendance_verification = types.SimpleNamespace(refuse_payroll=refuse_payroll)
        sys.modules.update({"frappe": frappe, "hrms.payroll.doctype.payroll_entry.payroll_entry": payroll_entry,
                            "hrms_addon": types.ModuleType("hrms_addon"), "hrms_addon.hrms_addon": hrms,
                            "hrms_addon.hrms_addon.payroll_entry_rules": rules,
                            "hrms_addon.hrms_addon.payroll_months": hrms.payroll_months,
                            "hrms_addon.hrms_addon.attendance_verification": hrms.attendance_verification})
        return load("payroll_entries", os.path.join(APP, "payroll_entries.py"))


for label, site in (("a draft payroll", Site({"docstatus": 0, "status": "Draft"})),
                    ("a payroll making its slips", Site({"status": "Queued"})),
                    ("a payroll with a submitted slip", Site(slips={"S1": 0, "S2": 1})),
                    ("a posted payroll", Site(journals=1)),
                    ("a payroll of a closed month", Site(closed=True)),
                    ("a payroll whose branches have not verified its days", Site(unverified=True))):
    glue = site.frappe()
    try:
        glue.recreate_salary_slips(site.run.name)
        check(False, "%s is refused" % label)
    except Thrown:
        check(not [entry for entry in site.log if entry[0] in ("db_set", "enqueue", "delete")],
              "%s is refused, and nothing is touched" % label, site.log)

site = Site(slips={"S1": 0, "S2": 0, "S3": 0})
glue = site.frappe()
answer = glue.recreate_salary_slips(site.run.name)
check(answer == 3 and ("permission", "write") in site.log, "it answers how many drafts, for one who may write the payroll",
      (answer, site.log))
check(("db_set", {"status": "Queued", "salary_slips_created": 0, "error_message": ""}) in site.log,
      "the payroll shows Queued at once, its slips no longer counted made", site.log)
enqueued = [entry for entry in site.log if entry[0] == "enqueue"]
check(len(enqueued) == 1 and enqueued[0][1] == glue.REMAKE and enqueued[0][2]["queue"] == "long"
      and enqueued[0][2]["enqueue_after_commit"] and enqueued[0][2]["payroll_entry"] == site.run.name,
      "and the work goes to the long queue once the payroll is saved", enqueued)
check(not [entry for entry in site.log if entry[0] == "delete"], "nothing is deleted while the user waits")
check(glue.REMAKE == "hrms_addon.hrms_addon.payroll_entries.remake" and callable(glue.remake), "the job is the module's own remake")

site = Site(slips={"S1": 0, "S2": 0})
glue = site.frappe()
glue.remake(site.run.name)
steps = [entry[0] for entry in site.log]
check(steps == ["delete", "delete", "commit", "reload", "create"] and site.slips == {},
      "in the background: every draft deleted, then Frappe HR's own Create Salary Slips", steps)

site = Site(slips={"S1": 0, "S2": 0}, create_fails=True)
glue = site.frappe()
glue.remake(site.run.name)
check(("failed", "recreation", "Please set account in Salary Component Basic") in site.log
      and site.run.status == "Failed" and "rollback" in [entry[0] for entry in site.log]
      and [entry[0] for entry in site.log][-1] == "commit",
      "a failure is shown on the payroll as Frappe HR shows its own, with the reason", site.log)
print("glue: refused as the rules say; else Queued at once, drafts deleted and made again in the background")

# ── 3. The button and its wiring ──────────────────────────────────────
script = open(os.path.join(REPO, "hrms_addon", "public", "js", "payroll_entry.js"), encoding="utf-8").read()
check('frappe.ui.form.on("Payroll Entry"' in script and '__("Recreate Salary Slips")' in script
      and 'method: "hrms_addon.hrms_addon.payroll_entries.recreate_salary_slips"' in script
      and "frappe.confirm(" in script and "frm.reload_doc()" in script,
      "the button asks first, calls the payroll's recreate and shows the payroll again")
check("doc.docstatus !== 1" in script and "cint(doc.salary_slips_submitted)" in script
      and '["Queued", "Cancelled"].includes(doc.status)' in script and "frm.perm[0].write" in script
      and '!cint(doc.salary_slips_created) && doc.status !== "Failed"' in script,
      "shown only on a submitted payroll with draft slips, or whose making failed, to one who may write it")
hooks = ast.parse(open(os.path.join(REPO, "hrms_addon", "hooks.py"), encoding="utf-8").read())
doctype_js = next(ast.literal_eval(node.value) for node in hooks.body if isinstance(node, ast.Assign)
                  and any(getattr(target, "id", "") == "doctype_js" for target in node.targets))
check(doctype_js.get("Payroll Entry") == "public/js/payroll_entry.js", "hooks.py loads it on the payroll", doctype_js.get("Payroll Entry"))
print("button: on the payroll, asked first, for one who may write it")

# ── 4. Upstream ───────────────────────────────────────────────────────
folder = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_entry")
if os.path.isdir(folder):
    import json

    fields = {field["fieldname"]: field for field in json.load(open(os.path.join(folder, "payroll_entry.json"), encoding="utf-8"))["fields"]}
    check({"Queued", "Failed"} <= set((fields["status"].get("options") or "").split("\n"))
          and {"salary_slips_created", "salary_slips_submitted", "error_message"} <= set(fields),
          "Frappe HR's payroll has the statuses and flags the button sets")
    source = open(os.path.join(folder, "payroll_entry.py"), encoding="utf-8").read()
    check("\tdef create_salary_slips(self) -> None:" in source and "def log_payroll_failure(process, payroll_entry, error):" in source
          and "employees = list(set(employees) - set(salary_slips_exist_for))" in source,
          "Create Salary Slips, its failure log, and a retry that makes only the slips still missing")
    form = open(os.path.join(folder, "payroll_entry.js"), encoding="utf-8").read()
    check("if (frm.custom_buttons) frm.clear_custom_buttons();" in form,
          "Frappe HR clears a submitted payroll's buttons in its refresh, before the app's own adds one")
    print("upstream: the statuses, Create Salary Slips, the failure log and the refresh the button stands on")
else:
    print("upstream: %s not found, skipped" % folder)

print()
if fail:
    print("FAILURES:")
    for line in fail:
        print("  -", line)
    sys.exit(1)
print("ALL PAYROLL RECREATE CHECKS PASSED")
