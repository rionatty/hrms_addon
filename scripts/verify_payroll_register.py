"""Checks the Salary Register tab on a Payroll Entry, without a bench:

    python scripts/verify_payroll_register.py

Luuka, 1 Nov 2026: "add a tab for salary register here". payroll_register.py
runs Frappe HR's own Salary Register for the payroll and keeps its slips
(rules: payroll_register_rules.py; the tab: public/js/payroll_entry.js, drawn
by the walk smoke_payroll_register.py):

  1  the rules: the payroll's own rows; a salary component none of them has
     gets no column; the register's own amounts always; the Excel sheet
  2  the glue, on a stand-in for Frappe: refused as the report refuses;
     drafts and submitted slips alike, cancelled ones left out; the period,
     company and currency of the payroll; the download
  3  the tab: its fields, the form script and its wiring
  4  each employee's figures on the Employees tab: read from their slip as
     the form opens, for whoever may see the register, the fields they show in;
     with no slip yet, what it will show (scripts/verify_slip_figures.py)
  5  upstream: what the glue and the tab stand on in Frappe and Frappe HR
"""
import importlib.util
import io
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "hrms_addon", "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
fail = []


def check(label, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + label + ("" if condition else "   <- %s" % (detail,)))
    if not condition:
        fail.append(label)


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("payroll_register_rules", os.path.join(APP, "payroll_register_rules.py"))  # proves it has no Frappe import
P = load("pay_days_rules", os.path.join(APP, "pay_days_rules.py"))
print("loaded payroll_register_rules.py and pay_days_rules.py without Frappe")


def amount(fieldname, label):
    return {"label": label, "fieldname": fieldname, "fieldtype": "Currency", "options": "currency", "width": 120}


COLUMNS = [
    {"label": "Salary Slip ID", "fieldname": "salary_slip_id", "fieldtype": "Link", "options": "Salary Slip"},
    {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data"},
    {"label": "Payment Days", "fieldname": "payment_days", "fieldtype": "Float"},
    amount("absent_amount", "Absent Amount"), amount("basic", "Basic"), amount("per_meter", "Per Meter"),
    amount("gross_pay", "Gross Pay"), amount("union_dues", "Union Dues"), amount("nssf_employee", "NSSF Employee"),
    amount("total_deduction", "Total Deduction"), amount("net_pay", "Net Pay"),
    {"label": "Currency", "fieldname": "currency", "fieldtype": "Data", "options": "Currency", "hidden": 1}]
OURS = {"salary_slip_id": "SS-1", "employee_name": "One", "payment_days": 26, "absent_amount": 0, "basic": 900000,
        "per_meter": None, "gross_pay": 900000, "union_dues": 0, "nssf_employee": 45000, "total_deduction": 45000,
        "net_pay": 855000, "currency": "UGX"}
DRAFT = dict(OURS, salary_slip_id="SS-2", employee_name="Two", nssf_employee=None, total_deduction=0, net_pay=900000)
THEIRS = dict(OURS, salary_slip_id="SS-9", employee_name="Per meter", basic=None, per_meter=400000, union_dues=12000)

# ── 1. The rules ──────────────────────────────────────────────────────
columns, rows = R.register_of(COLUMNS, [OURS, THEIRS, DRAFT, "not a row"], ["SS-1", "SS-2"])
names = [column["fieldname"] for column in columns]
check("the payroll's own rows, in the register's order", [row["salary_slip_id"] for row in rows] == ["SS-1", "SS-2"],
      rows)
check("a component only another payroll's slips have gets no column, nor one that is nought on all of ours",
      "per_meter" not in names and "union_dues" not in names, names)
check("a component one of ours has is kept, though the other has none", "basic" in names and "nssf_employee" in names)
check("the register's own amounts stay, nought or not", all(name in names for name in R.TOTALS if name !=
                                                           "total_loan_repayment"), names)
check("and every column that is not an amount, the hidden Currency included",
      names[:3] == ["salary_slip_id", "employee_name", "payment_days"] and names[-1] == "currency", names)
check("nothing given, nothing back", R.register_of(None, None, None) == ([], []))
check("no slips of the payroll, no rows", R.register_of(COLUMNS, [OURS], [])[1] == [])
sheet = R.sheet(columns, rows)
check("the Excel sheet: the labels, the hidden Currency left out",
      sheet[0] == [column["label"] for column in columns if not column.get("hidden")], sheet[0])
check("then a row per slip, cell by cell under its label",
      sheet[1] == [OURS[column["fieldname"]] for column in columns if not column.get("hidden")] and len(sheet) == 3,
      sheet[1:])
check("an empty register is the labels alone", R.sheet(columns, []) == [sheet[0]])


# ── 2. The glue ───────────────────────────────────────────────────────
class Refused(Exception):
    pass


class Row(dict):
    """frappe._dict, as far as the glue reads it."""
    __getattr__ = dict.get


class Site:
    """A stand-in for Frappe with one payroll, its slips and Frappe HR's Salary Register."""

    def __init__(self, may_read=True, report_roles=True, slip_report=True, slips=None, result=None, details=(),
                 broken=False, expected=None, expected_broken=False):
        self.may_read, self.report_roles, self.slip_report = may_read, report_roles, slip_report
        self.slips = [{"name": "SS-1", "start_date": "2026-09-26", "end_date": "2026-10-25"},
                      {"name": "SS-2", "start_date": "2026-09-27", "end_date": "2026-10-25"}] if slips is None else slips
        self.result = (COLUMNS, [OURS, THEIRS, DRAFT]) if result is None else result
        self.details, self.broken = details, broken
        self.expected, self.expected_broken = expected or {}, expected_broken
        self.calls = []

    def frappe(self):
        site = self
        module = types.ModuleType("frappe")
        module.__path__ = []
        module.PermissionError = Refused
        module._ = lambda text: text

        def throw(message, exc=Exception, **kwargs):
            raise exc(message)

        class Run:
            name, company, currency = "HR-PRUN-2026-00016", "Luuka Plastics Limited", "UGX"

            def check_permission(self, ptype):
                site.calls.append(("check_permission", ptype))
                if not site.may_read:
                    raise Refused("payroll")

        class Report:
            ref_doctype = "Salary Slip"

            def is_permitted(self):
                return site.report_roles

            def execute_module(self, filters):
                site.calls.append(("report", dict(filters)))
                return site.result

        def get_doc(doctype, name):
            site.calls.append(("get_doc", doctype, name))
            return Run() if doctype == "Payroll Entry" else Report()

        def has_permission(doctype, ptype):
            site.calls.append(("has_permission", doctype, ptype))
            return site.slip_report

        def get_all(doctype, filters=None, fields=None, limit_page_length=None):
            site.calls.append(("get_all", doctype, filters, fields, limit_page_length))
            if site.broken:
                raise ValueError("unreadable")
            return [Row(row) for row in (site.details if doctype == "Salary Detail" else site.slips)]

        def log_error(title=None, defer_insert=False):
            site.calls.append(("log_error", title, defer_insert))

        module.throw, module.get_doc, module.has_permission, module.get_all = throw, get_doc, has_permission, get_all
        module.log_error = log_error
        module.whitelist = lambda *args, **kwargs: (lambda function: function)
        desk_utils = types.ModuleType("frappe.desk.utils")
        desk_utils.provide_binary_file = lambda filename, extension, content: site.calls.append(
            ("file", filename, extension, content))
        xlsxutils = types.ModuleType("frappe.utils.xlsxutils")
        xlsxutils.make_xlsx = lambda data, sheet_name: site.calls.append(("xlsx", data, sheet_name)) or io.BytesIO(
            json.dumps(data).encode())
        sys.modules.update({"frappe": module, "frappe.desk": types.ModuleType("frappe.desk"),
                            "frappe.desk.utils": desk_utils, "frappe.utils": types.ModuleType("frappe.utils"),
                            "frappe.utils.xlsxutils": xlsxutils})

        def expected(doc, employees):
            site.calls.append(("expected", doc.name, list(employees)))
            if site.expected_broken:
                raise ValueError("unreadable")
            return site.expected

        slip_figures = types.ModuleType("hrms_addon.hrms_addon.slip_figures")
        slip_figures.expected = expected
        sys.modules["hrms_addon.hrms_addon.slip_figures"] = slip_figures
        return module


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
app.payroll_register_rules, app.pay_days_rules = R, P
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app, "hrms_addon.hrms_addon.payroll_register_rules": R,
                    "hrms_addon.hrms_addon.pay_days_rules": P})


def run(site, call="register"):
    site.frappe()
    glue = load("payroll_register", os.path.join(APP, "payroll_register.py"))
    try:
        return getattr(glue, call)("HR-PRUN-2026-00016")
    except Refused as error:
        return "refused: %s" % error


site = Site()
answer = run(site)
asked = [call for call in site.calls if call[0] == "get_all"]
ran = [call[1] for call in site.calls if call[0] == "report"]
check("the payroll must be one the user may read", ("check_permission", "read") in site.calls)
check("the slips asked for are the payroll's, cancelled ones left out, all of them",
      asked == [("get_all", "Salary Slip", {"payroll_entry": "HR-PRUN-2026-00016", "docstatus": ["<", 2]},
                 ["name", "start_date", "end_date"], 0)], asked)
check("the register is run for the payroll's company and currency, over its slips' period, drafts and submitted alike",
      ran == [{"company": "Luuka Plastics Limited", "currency": "UGX", "from_date": "2026-09-26",
               "to_date": "2026-10-25"}], ran)
check("and kept to the payroll's slips by the rules", answer == R.register_of(COLUMNS, [OURS, THEIRS, DRAFT],
                                                                             ["SS-1", "SS-2"]), answer)
check("the tab is given columns and rows", run(Site(), "salary_register") == {"columns": answer[0], "rows": answer[1]})
for refused, label in ((Site(may_read=False), "a payroll the user may not read"),
                       (Site(report_roles=False), "a user without the Salary Register's roles"),
                       (Site(slip_report=False), "a user who may not report on salary slips")):
    got = run(refused)
    check("refused: %s, and the register never run" % label, str(got).startswith("refused")
          and not [call for call in refused.calls if call[0] == "report"], (got, refused.calls))
empty = Site(slips=[])
check("a payroll with no slips has an empty register, and the report is not run",
      run(empty) == ([], []) and not [call for call in empty.calls if call[0] == "report"])
check("a register that comes back empty is empty", run(Site(result=([], []))) == ([], []))
site = Site()
run(site, "download_salary_register")
made = [call for call in site.calls if call[0] in ("xlsx", "file")]
check("the download is the same register as an Excel sheet", made[:1] == [("xlsx", R.sheet(*answer), "Salary Register")],
      made[:1])
check("sent as Salary Register and the payroll's name", made[1:] and made[1][:3] == (
    "file", "Salary Register HR-PRUN-2026-00016", "xlsx") and made[1][3] == json.dumps(R.sheet(*answer)).encode(),
      made[1:])

# ── 3. The tab ────────────────────────────────────────────────────────
fields = {row["name"]: row for row in json.loads(read("hrms_addon", "fixtures", "custom_field.json"))}
tab = fields.get("Payroll Entry-custom_salary_register_tab") or {}
holder = fields.get("Payroll Entry-custom_salary_register") or {}
check("a Salary Register tab after the Accounting & Payment tab's last field",
      (tab.get("fieldtype"), tab.get("label"), tab.get("insert_after")) == ("Tab Break", "Salary Register",
                                                                           "overtime_step"), tab)
check("holding the place the register is drawn in", (holder.get("fieldtype"), holder.get("insert_after"))
      == ("HTML", "custom_salary_register_tab"), holder)
check("nothing else sits under either", [(row["dt"], row.get("insert_after")) for row in fields.values()].count(
    ("Payroll Entry", "overtime_step")) == 1 and [(row["dt"], row.get("insert_after")) for row in fields.values()].count(
    ("Payroll Entry", "custom_salary_register_tab")) == 1)
hooks_src = read("hrms_addon", "hooks.py")
check("both are in the fixtures the app ships", all('"%s",' % name in hooks_src for name in (
    "Payroll Entry-custom_salary_register_tab", "Payroll Entry-custom_salary_register")))
check("the form script is the Payroll Entry's", '"Payroll Entry": "public/js/payroll_entry.js"' in hooks_src)
script = read("hrms_addon", "public", "js", "payroll_entry.js")
glue_src = read("hrms_addon", "hrms_addon", "payroll_register.py")
check("the script names the tab and the field the fixtures make",
      'const HA_PAYROLL_REGISTER_TAB = "custom_salary_register_tab";' in script
      and 'const HA_PAYROLL_REGISTER_FIELD = "custom_salary_register";' in script)
check("and the two methods the glue whitelists", all(
    'const HA_PAYROLL_REGISTER_%s = "hrms_addon.hrms_addon.payroll_register.%s";' % (const, method) in script
    and "@frappe.whitelist()\ndef %s(payroll_entry):" % method in glue_src
    for const, method in (("METHOD", "salary_register"), ("DOWNLOAD", "download_salary_register"))))
check("it loads when the tab is opened, and on refresh only while the tab is open",
      re.search(r"refresh\(frm\) \{\s*ha_payroll_recreate_button\(frm\);\s*ha_payroll_share_buttons\(frm\);\s*(ha_payroll_bank_file_button\(frm\);\s*)?ha_payroll_register\(frm\);\s*(ha_payroll_ugx\(frm\);\s*)?ha_payroll_period\(frm\);\s*ha_weekly\(frm\);\s*(ha_weekly_pieces_button\(frm\);\s*)?(ha_payroll_attendance\(frm\);\s*)?\}", script)
      and re.search(r"on_tab_change\(frm\) \{\s*ha_payroll_register\(frm\);\s*(ha_payroll_ugx\(frm\);\s*)?\}", script)
      and "tab.df.fieldname !== HA_PAYROLL_REGISTER_TAB) return;" in script)
check("with fetch, so a register that cannot load says so in the tab, not in a dialog",
      'fetch("/api/method/" + HA_PAYROLL_REGISTER_METHOD' in script and ".call({" not in script.split(
          "function ha_payroll_register(")[1])
check("drawn as Frappe's reports draw it: a filter row, a total row, the hidden columns left out",
      "inlineFilters: true," in script and "showTotalRow: true," in script
      and "hooks: { columnTotal: frappe.utils.report_column_total }," in script
      and ".filter((column) => !column.hidden)" in script and "new frappe.DataTable(" in script)

# ── 4. Each employee's figures on the Employees tab ───────────────────
class EntryRow:
    def __init__(self, employee):
        self.employee, self.shown = employee, {"custom_absent_amount": 999, "custom_basic_salary": 999}

    def update(self, values):
        self.shown.update(values)


class Entry:
    name = "HR-PRUN-2026-00016"

    def __init__(self, employees):
        self.rows = [EntryRow(employee) for employee in employees]

    def get(self, field):
        return self.rows if field == "employees" else None


SLIPS = [{"name": "SS-1", "employee": "E1", "total_working_days": 26, "payment_days": 25, "absent_days": 1,
          "custom_days_in_period": 31, "custom_days_paid": 30, "custom_absent_amount": 30769.23},
         {"name": "SS-2", "employee": "E2", "total_working_days": 26, "payment_days": 25.5, "absent_days": 0.5,
          "custom_days_in_period": 31, "custom_days_paid": 30.5, "custom_absent_amount": 5769.23}]
BASICS = [{"parent": "SS-1", "default_amount": 800000, "additional_amount": 0},
          {"parent": "SS-2", "default_amount": 300000, "additional_amount": 0},
          {"parent": "SS-2", "default_amount": 0, "additional_amount": 50000}]


def figures(site):
    site.frappe()
    glue = load("payroll_register", os.path.join(APP, "payroll_register.py"))
    entry = Entry(("E1", "E2", "E3"))
    glue.employee_figures(entry)
    return {row.employee: row.shown for row in entry.rows}


site = Site(slips=SLIPS, details=BASICS)
shown = figures(site)
# Luuka, 1 Nov 2026: "then you should include holiday sunday", as their own register counts
check("a row is given the days its slip shows, Sundays and holidays included, not the 26 pay works from; its absent "
      "days and absent amount, and the month's Basic",
      shown["E1"] == {"custom_working_days": 31, "custom_paid_days": 30, "custom_absent_days": 1,
                      "custom_absent_amount": 30769.23, "custom_basic_salary": 800000}, shown["E1"])
check("half days as they are, and the Basic with an Additional Salary on it whole", shown["E2"] == {
    "custom_working_days": 31, "custom_paid_days": 30.5, "custom_absent_days": 0.5, "custom_absent_amount": 5769.23,
    "custom_basic_salary": 350000}, shown["E2"])
check("a row with no slip and nothing expected shows nothing of an earlier one", shown["E3"] == R.NO_FIGURES, shown["E3"])
check("only those with no slip are worked out", ("expected", "HR-PRUN-2026-00016", ["E3"]) in site.calls, site.calls)
asked = [call for call in site.calls if call[0] == "get_all"]
check("the slips read are the payroll's, cancelled ones left out, all of them",
      asked[0] == ("get_all", "Salary Slip", {"payroll_entry": "HR-PRUN-2026-00016", "docstatus": ["<", 2]},
                   ["name", "employee", "custom_days_in_period", "custom_days_paid", "absent_days",
                    "custom_absent_amount"], 0),
      asked[0])
check("and of their earnings the Basic rows, all of them",
      asked[1] == ("get_all", "Salary Detail", {"parenttype": "Salary Slip", "parentfield": "earnings",
                                                "salary_component": "Basic", "parent": ["in", ["SS-1", "SS-2"]]},
                   ["parent", "default_amount", "additional_amount"], 0) and len(asked) == 2, asked[1:])
EXPECTED = {"custom_working_days": 31, "custom_paid_days": 29, "custom_absent_days": 2, "custom_absent_amount": 61538.46,
            "custom_basic_salary": 800000}
site = Site(slips=SLIPS, details=BASICS, expected={"E3": EXPECTED})
shown = figures(site)
check("a row with no slip yet shows what its slip will, beside those read from theirs",
      shown["E3"] == EXPECTED and shown["E1"]["custom_absent_amount"] == 30769.23, shown)
site = Site(slips=SLIPS, details=BASICS, expected_broken=True)
shown = figures(site)
check("what cannot be worked out leaves the slips' figures standing, and is logged",
      shown["E1"]["custom_absent_amount"] == 30769.23 and shown["E3"] == R.NO_FIGURES
      and ("log_error", "HRMS Addon: employee figures on HR-PRUN-2026-00016", True) in site.calls, site.calls)
site = Site(slips=[], expected={"E1": EXPECTED, "E2": EXPECTED, "E3": EXPECTED})
shown = figures(site)
check("a payroll with no slips yet: every row shows what its slip will, with only the slips and nothing more read here",
      all(row == EXPECTED for row in shown.values()) and ("expected", "HR-PRUN-2026-00016", ["E1", "E2", "E3"]) in site.calls
      and [call[1] for call in site.calls if call[0] == "get_all"] == ["Salary Slip"], site.calls)
for refused, label in ((Site(report_roles=False, slips=SLIPS), "the Salary Register's roles"),
                       (Site(slip_report=False, slips=SLIPS), "report on salary slips")):
    shown = figures(refused)
    check("whoever may not %s sees none of it, and no slip is read or worked out" % label,
          all(row == R.NO_FIGURES for row in shown.values())
          and not [call for call in refused.calls if call[0] in ("get_all", "expected")], refused.calls)
site = Site(slips=SLIPS, broken=True)
shown = figures(site)
check("figures that cannot be read leave the payroll opening, with nothing on the rows",
      all(row == R.NO_FIGURES for row in shown.values()) and not [call for call in site.calls if call[0] == "expected"])
check("and are logged, in a way that outlives a read's rollback",
      ("log_error", "HRMS Addon: employee figures on HR-PRUN-2026-00016", True) in site.calls, site.calls)
check("Frappe sends a row's blank number as nought, so the rows are given nought",
      set(R.NO_FIGURES.values()) == {0})
check("the figures are given as the payroll's form opens", re.search(
    r'"Payroll Entry": \{[^}]*"onload": "hrms_addon\.hrms_addon\.payroll_register\.employee_figures"', hooks_src))
check("the slip's Absent Amount is the field pay_days.py keeps it in",
      'ABSENT_FIELD = "custom_absent_amount"' in read("hrms_addon", "hrms_addon", "pay_days.py")
      and R.SLIP_FIGURES["custom_absent_amount"] == "custom_absent_amount")
LOOK = (("custom_working_days", "Working Days", "Float", 2, "is_salary_withheld"),
        ("custom_paid_days", "Paid Days", "Float", 1, "custom_working_days"),
        ("custom_absent_days", "Absent", "Float", 1, "custom_paid_days"),
        ("custom_absent_amount", "Absent Amount", "Currency", 2, "custom_absent_days"),
        ("custom_basic_salary", "Basic Salary", "Currency", 2, "custom_absent_amount"))
for fieldname, label, fieldtype, columns, after in LOOK:
    field = fields.get("Payroll Employee Detail-%s" % fieldname) or {}
    check("the Employees table's %s: in that order, a column of its own" % label,
          (field.get("fieldname"), field.get("label"), field.get("fieldtype"), field.get("columns"),
           field.get("insert_after"), field.get("in_list_view")) == (fieldname, label, fieldtype, columns, after, 1), field)
    check("and nobody types in it; a submitted payroll saved with it shown is not refused",
          field.get("read_only") == 1 and field.get("allow_on_submit") == 1 and field.get("no_copy") == 1, field)
    check("and it reads as days with their halves, or in the payroll's currency",
          field.get("precision") == "1" if fieldtype == "Float" else field.get("options") == "currency", field)
    check("and it is in the fixtures the app ships", '"Payroll Employee Detail-%s",' % fieldname in hooks_src)
check("every figure the rules give has its field", set(R.NO_FIGURES) == {one[0] for one in LOOK})
check("and nothing else sits under them",
      all([(row["dt"], row.get("insert_after")) for row in fields.values()].count(("Payroll Employee Detail", one[4])) == 1
          for one in LOOK), [row["name"] for row in fields.values() if row["dt"] == "Payroll Employee Detail"])

# ── 5. Upstream ───────────────────────────────────────────────────────
hrms = os.path.join(APPS_ROOT, "hrms", "hrms")
frappe_app = os.path.join(APPS_ROOT, "frappe", "frappe")
entry_json = os.path.join(hrms, "payroll", "doctype", "payroll_entry", "payroll_entry.json")
register_py = os.path.join(hrms, "payroll", "report", "salary_register", "salary_register.py")
register_json = os.path.join(hrms, "payroll", "report", "salary_register", "salary_register.json")
if all(os.path.exists(path) for path in (entry_json, register_py, register_json, frappe_app)):
    entry = json.load(open(entry_json, encoding="utf-8"))
    order = entry["field_order"]
    types_of = {field["fieldname"]: field["fieldtype"] for field in entry["fields"]}
    check("Frappe HR's Payroll Entry: Overtime Step closes the Accounting & Payment tab, a tab follows it",
          "overtime_step" in order and types_of.get(order[order.index("overtime_step") + 1]) == "Tab Break",
          order[order.index("overtime_step"):] if "overtime_step" in order else order)
    report = open(register_py, encoding="utf-8").read()
    for needle, why in (
            ('"salary_slip_id": ss.name,', "a row names its slip"),
            ('if filters.get("docstatus"):', "with no Document Status every slip is listed, drafts and submitted"),
            ("salary_slip.start_date >= filters.get(\"from_date\")", "slips from the period's start"),
            ("salary_slip.end_date <= filters.get(\"to_date\")", "to its end"),
            ('salary_slip.company == filters.get("company")', "of the company"),
            ('if filters.get("currency") and filters.get("currency") != company_currency:', "in the currency asked"),
            ('"fieldname": frappe.scrub(earning),\n\t\t\t\t"fieldtype": "Currency",', "an earning is an amount column"),
            ('"fieldname": frappe.scrub(deduction),\n\t\t\t\t"fieldtype": "Currency",', "and so is a deduction")):
        check("Frappe HR's Salary Register: %s" % why, needle in report)
    meta = json.load(open(register_json, encoding="utf-8"))
    check("Frappe HR's Salary Register reports on Salary Slip, for HR", meta.get("ref_doctype") == "Salary Slip"
          and {"HR User", "HR Manager"} <= {role["role"] for role in meta.get("roles", [])})
    report_py = open(os.path.join(frappe_app, "core", "doctype", "report", "report.py"), encoding="utf-8").read()
    check("Frappe's Report runs a report's module in execute_module, and says who may see it",
          "\tdef execute_module(self, filters):" in report_py and "\tdef is_permitted(self):" in report_py)
    query_report = open(os.path.join(frappe_app, "desk", "query_report.py"), encoding="utf-8").read()
    check("Frappe refuses a report as the glue does", "if not doc.is_permitted():" in query_report
          and 'if not frappe.has_permission(doc.ref_doctype, "report"):' in query_report)
    check("Frappe sends a file with provide_binary_file and makes Excel with make_xlsx",
          "def provide_binary_file(filename: str, extension: str, content: bytes) -> None:" in open(
              os.path.join(frappe_app, "desk", "utils.py"), encoding="utf-8").read()
          and "def make_xlsx(\n\tdata: list[list[Any]],\n\tsheet_name: str," in open(
              os.path.join(frappe_app, "utils", "xlsxutils.py"), encoding="utf-8").read())
    form = open(os.path.join(frappe_app, "public", "js", "frappe", "form", "form.js"), encoding="utf-8").read()
    check("Frappe's form says when a tab is opened, and which", 'this.script_manager.trigger("on_tab_change");' in form
          and "\tget_active_tab() {" in form)
    desk = open(os.path.join(frappe_app, "public", "js", "desk.bundle.js"), encoding="utf-8").read()
    check("the desk carries Frappe's DataTable and its column totals",
          'import "./frappe/ui/datatable.js";' in desk and "frappe.DataTable = DataTable;" in open(
              os.path.join(frappe_app, "public", "js", "frappe", "ui", "datatable.js"), encoding="utf-8").read()
          and "\treport_column_total: function (values, column, type) {" in open(
              os.path.join(frappe_app, "public", "js", "frappe", "utils", "utils.js"), encoding="utf-8").read())
    check("Frappe ships DataTable 1.20.7, the version the walk draws with", '"frappe-datatable": "1.20.7"' in open(
        os.path.join(APPS_ROOT, "frappe", "package.json"), encoding="utf-8").read())
    payroll = os.path.join(hrms, "payroll", "doctype")

    def doctype_fields(name):
        data = json.load(open(os.path.join(payroll, name, name + ".json"), encoding="utf-8"))
        return data["field_order"], {field["fieldname"]: field for field in data["fields"]}

    order, _rows = doctype_fields("payroll_employee_detail")
    check("Frappe HR's Employees table ends with Is Salary Withheld, under which the figures go",
          order[-1] == "is_salary_withheld", order)
    _order, slip_fields = doctype_fields("salary_slip")
    check("a slip has its Working Days, Payment Days and Absent Days",
          {"total_working_days", "payment_days", "absent_days"} <= set(slip_fields))
    _order, detail_fields = doctype_fields("salary_detail")
    check("a slip's row has the month's amount and an Additional Salary's whole amount",
          {"default_amount", "additional_amount"} <= set(detail_fields))
    check("the Employees table's Currency finds the payroll's currency", "currency" in doctype_fields("payroll_entry")[1]
          and "} else if (cur_frm && cur_frm.doc[df.options]) {" in open(os.path.join(
              frappe_app, "public", "js", "frappe", "model", "meta.js"), encoding="utf-8").read())
    entry_py = open(os.path.join(payroll, "payroll_entry", "payroll_entry.py"), encoding="utf-8").read()
    check("Frappe HR makes a payroll's slips one by one, by the payroll's name",
          '"payroll_entry": args.get("payroll_entry"),' in entry_py and "frappe.get_doc(slip_args).insert()" in entry_py)
    load_py = open(os.path.join(frappe_app, "desk", "form", "load.py"), encoding="utf-8").read()
    save_py = open(os.path.join(frappe_app, "desk", "form", "save.py"), encoding="utf-8").read()
    document_py = open(os.path.join(frappe_app, "model", "document.py"), encoding="utf-8").read()
    check("Frappe runs onload as a form opens and after it is saved, with the app's hooks",
          "\trun_onload(doc)" in load_py and "\trun_onload(doc)" in save_py and 'doc.run_method("onload")' in load_py
          and "doc_events.get(self.doctype, {}).get(method, [])" in document_py)
    base_document = open(os.path.join(frappe_app, "model", "base_document.py"), encoding="utf-8").read()
    check("Frappe sends a blank number as nought", "elif fieldtype in float_like_fields and not isinstance(value, float):"
          "\n\t\t\t\t\tvalue = flt(value)" in base_document)
    check("and refuses a submitted row changed, unless the field allows it",
          "if df and not df.allow_on_submit and not df.is_virtual and (self.get(key) or db_value):" in base_document)
    check("Frappe's table scrolls past ten column units, wider than Frappe HR's five",
          'current_grid.addClass("column-limit-reached");' in open(os.path.join(
              frappe_app, "public", "js", "frappe", "form", "grid_row.js"), encoding="utf-8").read())
else:
    print("Frappe and Frappe HR's own code: NOT CHECKED, they were not found under %s" % APPS_ROOT)
check("the app's Absent Amount reaches the register through execute_module", "def execute_module(self, filters):"
      in read("hrms_addon", "hrms_addon", "report_extensions.py"))

print()
if fail:
    print("%d FAILED" % len(fail))
    sys.exit(1)
print("ALL PAYROLL REGISTER CHECKS PASSED")
