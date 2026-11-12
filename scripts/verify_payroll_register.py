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
W = load("weekly_pay_rules", os.path.join(APP, "weekly_pay_rules.py"))  # what tells a weekly payroll
O = load("output_rules", os.path.join(APP, "output_rules.py"))
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

# a weekly payroll: the casuals' master payroll (Luuka, 12 Nov 2026: "i hope the register for casuals it not less
# than this these fields are the most inportnat for casuals, also add overtme hours on it")
CASUAL_SLIPS = [
    {"name": "S1", "employee": "C1", "employee_name": "Alex", "department": "Blow - LPT", "currency": "UGX",
     "hours": 50, "rate": 857, "overtime_hours": 10, "gross_pay": 55705, "net_pay": 55705},
    {"name": "S2", "employee": "C2", "employee_name": "Agnes", "department": "Blow - LPT", "currency": "UGX",
     "hours": 0, "rate": 0, "overtime_hours": 0, "gross_pay": 37340, "net_pay": 37340},
    {"name": "S3", "employee": "C3", "employee_name": "Zed", "department": "Alpha - LPT", "currency": "UGX",
     "hours": 60, "rate": 857, "overtime_hours": 17, "gross_pay": 85414.5, "net_pay": 80414.5},
    {"name": "S4", "employee": "C4", "employee_name": "Mona", "department": "Blow - LPT", "currency": "UGX",
     "hours": 0, "rate": 0, "overtime_hours": 0, "gross_pay": 9000, "net_pay": 9000}]
CASUAL_LINES = [
    {"parent": "S1", "parentfield": "earnings", "salary_component": "Hourly Earnings", "amount": 42850},
    {"parent": "S1", "parentfield": "earnings", "salary_component": "Casual Overtime", "amount": 12855},
    {"parent": "S2", "parentfield": "earnings", "salary_component": "Per Piece Earnings", "amount": 37340},
    {"parent": "S3", "parentfield": "earnings", "salary_component": "Hourly Earnings", "amount": 51420},
    {"parent": "S3", "parentfield": "earnings", "salary_component": "Casual Overtime", "amount": 21853.5},
    {"parent": "S3", "parentfield": "earnings", "salary_component": "Arrears", "amount": 11141},
    {"parent": "S3", "parentfield": "earnings", "salary_component": "Allowance", "amount": 1000},
    {"parent": "S3", "parentfield": "deductions", "salary_component": "Advance Recovery", "amount": 5000},
    {"parent": "S3", "parentfield": "deductions", "salary_component": "Employer NSSF", "amount": 999,
     "do_not_include_in_total": 1},
    {"parent": "S4", "parentfield": "earnings", "salary_component": "Per Piece Earnings", "amount": 9000},
    {"parent": "S9", "parentfield": "earnings", "salary_component": "Hourly Earnings", "amount": 777}]
CASUAL_NAMES = {"basic": "Hourly Earnings", "overtime": "Casual Overtime", "arrears": "Arrears",
                "pieces": {"Per Piece Earnings"}, "advance": "Advance Recovery"}
CASUAL_PEOPLE = {"C1": {"tin": "T1", "nssf": "N1"}, "C3": {"tin": "T3", "nssf": None}}
by_size = R.pieces_by_size(
    [{"slip": "S2", "source": "OPR-1", "employee": "C2"}, {"slip": "S2", "source": "OPR-1", "employee": "C2"},
     {"slip": "S2", "source": "DPR-9", "employee": "C2"}, {"slip": None, "source": "OPR-1", "employee": "C2"}],
    [{"source": "OPR-1", "employee": "C2", "size": "PIECE RATE 1", "amount": 30000},
     {"source": "OPR-1", "employee": "C2", "size": "PIECE RATE 2", "amount": 4140},
     {"source": "OPR-1", "employee": "C9", "size": "PIECE RATE 1", "amount": 999},
     {"source": "DPR-9", "employee": "C2", "size": "PIECE RATE 1", "amount": 3200},
     {"source": "DPR-9", "employee": "C2", "size": None, "amount": 5}])
check("a slip's pieces by their category: from each run or report that wrote its pay, read once however many "
      "earnings it wrote, and its own person's lines only",
      by_size == {"S2": {"PIECE RATE 1": 33200.0, "PIECE RATE 2": 4140.0}}, by_size)
weekly_columns, weekly_rows = R.casual_register(CASUAL_SLIPS, CASUAL_LINES, CASUAL_PEOPLE, by_size, CASUAL_NAMES, "LPT")
labels = [column["label"] for column in weekly_columns]
check("a weekly payroll's register in the Casual Master Payroll's own columns and order, the overtime hours beside "
      "the overtime pay",
      labels == ["Sr No", "Payroll No", "Employee Name", "Department", "Hours Worked", "Wage Rate", "Basic",
                 "PIECE RATE 1", "PIECE RATE 2", "Per Piece Earnings", "Overtime Hours", "OT Amount", "Arrears",
                 "Allowance", "Gross Amount", "Salary Advance", "Net Pay", "TIN", "NSSF", "Salary Slip"], labels)
check("a row a casual, by department and then by name, numbered; the department without the company's letters",
      [(row["serial"], row["employee"], row["department"]) for row in weekly_rows]
      == [(1, "C3", "Alpha"), (2, "C2", "Blow"), (3, "C1", "Blow"), (4, "C4", "Blow")],
      [(row["serial"], row["employee"], row["department"]) for row in weekly_rows])
by_slip = {row["salary_slip_id"]: row for row in weekly_rows}
check("the hours, the rate, the basic and the overtime, hours and pay, are the slip's own",
      [by_slip["S1"][key] for key in ("hours_worked", "wage_rate", "basic", "overtime_hours", "overtime_amount",
                                      "gross_pay", "net_pay", "tin", "nssf")]
      == [50.0, 857.0, 42850.0, 10.0, 12855.0, 55705.0, 55705.0, "T1", "N1"], by_slip["S1"])
check("the pieces under their categories, as the run worked them out; pieces no run accounts for under their "
      "earning's own name",
      (by_slip["S2"]["piece_1"], by_slip["S2"]["piece_2"], by_slip["S2"]["piece_rest"]) == (33200.0, 4140.0, 0.0)
      and (by_slip["S4"]["piece_1"], by_slip["S4"]["piece_rest"]) == (0.0, 9000.0), (by_slip["S2"], by_slip["S4"]))
check("the arrears, any other earning and each deduction have their own columns; a line shown and not taken is "
      "no deduction; another payroll's line is nobody's",
      (by_slip["S3"]["arrears"], by_slip["S3"]["earning_1"], by_slip["S3"]["salary_advance"]) == (11141.0, 1000.0, 5000.0)
      and "deduction_1" not in by_slip["S3"] and "S9" not in by_slip, by_slip["S3"])
earning_fields = [column["fieldname"] for column in weekly_columns
                  if column["fieldname"] in ("basic", "overtime_amount", "arrears", "piece_rest")
                  or column["fieldname"].startswith(("piece_", "earning_"))]
check("every row's earnings add up to its gross, and its gross less what was taken to its net",
      all(abs(sum(row[field] for field in set(earning_fields)) - row["gross_pay"]) < 0.01
          and abs(row["gross_pay"] - row["salary_advance"]
                  - sum(value for key, value in row.items() if key.startswith("deduction_")) - row["net_pay"]) < 0.01
          for row in weekly_rows),
      [(row["employee"], sum(row[field] for field in set(earning_fields)), row["gross_pay"]) for row in weekly_rows])
check("amounts are in the slips' currency; a serial number and a rate are figures with no total",
      all(column.get("options") == "currency" for column in weekly_columns if column["fieldtype"] == "Currency")
      and all(row["currency"] == "UGX" for row in weekly_rows)
      and [column["fieldname"] for column in weekly_columns if column.get("no_total")] == ["serial", "wage_rate"],
      [column["fieldname"] for column in weekly_columns if column.get("no_total")])
weekly_sheet = R.sheet(weekly_columns, weekly_rows, total=True)
totals = dict(zip(labels, weekly_sheet[-1]))
check("the Excel sheet ends with the totals, as the team's own does: Total under the name, each column of figures "
      "summed, none for the serial number or the rate",
      len(weekly_sheet) == 6 and totals["Employee Name"] == "Total" and totals["Hours Worked"] == 110.0
      and totals["Basic"] == 94270.0 and totals["Overtime Hours"] == 27.0 and totals["OT Amount"] == 34708.5
      and totals["Gross Amount"] == 187459.5 and totals["Net Pay"] == 182459.5 and totals["Sr No"] is None
      and totals["Wage Rate"] is None and totals["TIN"] is None, totals)
check("a register with nobody on it has no total row, and the monthly register none either",
      len(R.sheet(weekly_columns, [], total=True)) == 1 and len(R.sheet(columns, rows)) == 3)
lent_columns, lent_rows = R.casual_register([dict(CASUAL_SLIPS[0], total_loan_repayment=5000, net_pay=50705)],
                                           CASUAL_LINES[:2], None, None, CASUAL_NAMES, None)
check("a loan repayment, which a slip keeps apart from its deductions, has a column where anybody repays one, "
      "between the deductions and the net; nobody repaying, there is none",
      [column["label"] for column in lent_columns][-7:-4] == ["Gross Amount", "Salary Advance", "Loan Repayment"]
      and lent_rows[0]["total_loan_repayment"] == 5000.0 and lent_rows[0]["gross_pay"] - 5000.0 == lent_rows[0]["net_pay"]
      and "Loan Repayment" not in labels, [column["label"] for column in lent_columns])
bare_columns, bare_rows = R.casual_register(CASUAL_SLIPS[:1], CASUAL_LINES[:2], None, None, CASUAL_NAMES, None)
check("with no pieces, no other earning and nothing taken off, only the sheet's own columns are there",
      [column["label"] for column in bare_columns] == [
          "Sr No", "Payroll No", "Employee Name", "Department", "Hours Worked", "Wage Rate", "Basic", "Overtime Hours",
          "OT Amount", "Arrears", "Gross Amount", "Salary Advance", "Net Pay", "TIN", "NSSF", "Salary Slip"]
      and bare_rows[0]["department"] == "Blow - LPT" and bare_rows[0]["tin"] is None
      and bare_rows[0]["salary_advance"] == 0.0,
      [column["label"] for column in bare_columns])
fined_columns, fined_rows = R.casual_register(
    CASUAL_SLIPS[:1], CASUAL_LINES[:2] + [
        {"parent": "S1", "parentfield": "deductions", "salary_component": "Fine", "amount": 100},
        {"parent": "S1", "parentfield": "deductions", "salary_component": "Advance Recovery", "amount": 700}],
    None, None, CASUAL_NAMES, None)
check("Salary Advance is always there, as on the team's sheet, and holds what was recovered of an advance; any "
      "other deduction has its own column after it",
      [column["label"] for column in fined_columns][-7:-4] == ["Gross Amount", "Salary Advance", "Fine"]
      and (fined_rows[0]["salary_advance"], fined_rows[0]["deduction_1"]) == (700.0, 100.0),
      [column["label"] for column in fined_columns])
renamed_columns, renamed_rows = R.casual_register(
    CASUAL_SLIPS[:1], CASUAL_LINES[:2] + [
        {"parent": "S1", "parentfield": "earnings", "salary_component": "Arrear", "amount": 100},
        {"parent": "S1", "parentfield": "earnings", "salary_component": "Arrears", "amount": 11141}],
    None, None, dict(CASUAL_NAMES, arrears={"Arrear", "Arrears"}), None)
check("arrears are one column under whichever earning they were paid: the one in use now, and the one earlier runs "
      "paid under",
      renamed_rows[0]["arrears"] == 11241.0 and [column["label"] for column in renamed_columns].count("Arrears") == 1
      and "Arrear" not in [column["label"] for column in renamed_columns],
      (renamed_rows[0]["arrears"], [column["label"] for column in renamed_columns]))
unnamed = R.casual_register(CASUAL_SLIPS[:1], CASUAL_LINES[:2], None, None, dict(CASUAL_NAMES, advance=None), None)[0]
check("a site that names no advance deduction has no such column until somebody has a deduction",
      "Salary Advance" not in [column["label"] for column in unnamed], [column["label"] for column in unnamed])


# ── 2. The glue ───────────────────────────────────────────────────────
class Refused(Exception):
    pass


class Row(dict):
    """frappe._dict, as far as the glue reads it."""
    __getattr__ = dict.get


class Site:
    """A stand-in for Frappe with one payroll, its slips and Frappe HR's Salary Register."""

    def __init__(self, may_read=True, report_roles=True, slip_report=True, slips=None, result=None, details=(),
                 broken=False, expected=None, expected_broken=False, frequency="Monthly", tables=None):
        # a weekly payroll: its frequency, and each doctype's rows as the glue reads them
        self.frequency, self.tables = frequency, tables
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
            payroll_frequency, salary_slip_based_on_timesheet = site.frequency, 0

            def get(self, key, default=None):
                return getattr(self, key, default)

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
            if site.tables is not None:
                return [Row(row) for row in site.tables.get(doctype, [])]
            return [Row(row) for row in (site.details if doctype == "Salary Detail" else site.slips)]

        def log_error(title=None, defer_insert=False):
            site.calls.append(("log_error", title, defer_insert))

        module.throw, module.get_doc, module.has_permission, module.get_all = throw, get_doc, has_permission, get_all
        module.log_error = log_error
        module.get_cached_value = lambda doctype, name, field: site.calls.append(("cached", doctype, name, field)) or "LPT"
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
app.payroll_register_rules, app.pay_days_rules, app.weekly_pay_rules, app.output_rules = R, P, W, O
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app, "hrms_addon.hrms_addon.payroll_register_rules": R,
                    "hrms_addon.hrms_addon.pay_days_rules": P, "hrms_addon.hrms_addon.weekly_pay_rules": W,
                    "hrms_addon.hrms_addon.output_rules": O})
# what a weekly payroll's register reads of the modules that pay the casuals: their names for the slip's fields
# and for the earnings, stood in for here and checked against the modules' own text below
weekly_pay = types.ModuleType("hrms_addon.hrms_addon.weekly_pay")
weekly_pay.HOURS, weekly_pay.RATE, weekly_pay.OVERTIME_HOURS = (
    "custom_weekly_hours", "custom_weekly_rate", "custom_weekly_overtime_hours")
weekly_pay.OVERTIME_COMPONENT = ("Casual Overtime", "COT")
output_pay = types.ModuleType("hrms_addon.hrms_addon.output_pay")
output_pay.SIZE, output_pay.RUN, output_pay.REPORT, output_pay.REPORT_LINE = (
    "Output Rate", "Output Pay Run", "Daily Production Report", "Daily Production Line")
output_pay._component_name = lambda section: {O.HOURLY: "Hourly Earnings", O.PER_PIECE: "Per Piece Earnings"}[section]
piece_pay = types.ModuleType("hrms_addon.hrms_addon.piece_pay")
piece_pay.ARREARS_BEFORE = "Arrears"
piece_pay.arrears_components = lambda: ("Arrear", "Arrears Deductions")
advances = types.ModuleType("hrms_addon.hrms_addon.advances")
advances.DEFAULT_COMPONENT = "Advance Recovery"
app.weekly_pay, app.output_pay, app.piece_pay, app.advances = weekly_pay, output_pay, piece_pay, advances
sys.modules.update({"hrms_addon.hrms_addon.weekly_pay": weekly_pay, "hrms_addon.hrms_addon.output_pay": output_pay,
                    "hrms_addon.hrms_addon.piece_pay": piece_pay, "hrms_addon.hrms_addon.advances": advances})


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
# a weekly payroll: the register is the casuals' master payroll, read from the payroll's own slips
WEEKLY = {
    "Salary Slip": [dict(slip, start_date="2026-11-05", end_date="2026-11-11") for slip in CASUAL_SLIPS],
    "Salary Detail": [dict(line, additional_salary="AS-1" if line["parent"] == "S2" else None)
                      for line in CASUAL_LINES if line["parent"] != "S9"],
    "Employee": [{"name": "C1", "custom_tin": "T1", "custom_nssf_no": "N1"},
                 {"name": "C3", "custom_tin": "T3", "custom_nssf_no": None}],
    "Output Rate": [{"name": "PIECE RATE 1", "salary_component": None}, {"name": "PIECE RATE 2", "salary_component": None}],
    "Additional Salary": [{"name": "AS-1", "employee": "C2", "ref_doctype": "Output Pay Run", "ref_docname": "OPR-1"}],
    "Output Pay Line": [{"parent": "OPR-1", "employee": "C2", "size": "PIECE RATE 1", "amount": 33200},
                        {"parent": "OPR-1", "employee": "C2", "size": "PIECE RATE 2", "amount": 4140},
                        {"parent": "OPR-1", "employee": "C7", "size": "PIECE RATE 1", "amount": 999}]}
week = Site(frequency="Weekly", tables=WEEKLY)
week_columns, week_rows = run(week)
read_of = {call[1]: call for call in week.calls if call[0] == "get_all"}
check("a weekly payroll's register is the casuals' master payroll: Frappe HR's register is not run for it",
      [column["label"] for column in week_columns] == labels and not [call for call in week.calls if call[0] == "report"]
      and [row["employee"] for row in week_rows] == ["C3", "C2", "C1", "C4"],
      ([column["label"] for column in week_columns], [row["employee"] for row in week_rows]))
check("read from the payroll's own slips: the hours, the rate and the overtime hours each keeps",
      read_of["Salary Slip"][2] == {"name": ["in", ["S1", "S2", "S3", "S4"]]}
      and all(field in read_of["Salary Slip"][3] for field in (
          "custom_weekly_hours as hours", "custom_weekly_rate as rate", "custom_weekly_overtime_hours as overtime_hours",
          "gross_pay", "net_pay", "department", "currency", "total_loan_repayment")), read_of["Salary Slip"])
check("their earnings and deductions, each employee's TIN and NSSF, and the pieces by category from the run that "
      "wrote the pay",
      read_of["Salary Detail"][2] == {"parenttype": "Salary Slip", "parent": ["in", ["S1", "S2", "S3", "S4"]],
                                      "parentfield": ["in", ["earnings", "deductions"]]}
      and read_of["Employee"][3] == ["name", "custom_tin", "custom_nssf_no"]
      and read_of["Additional Salary"][2] == {"name": ["in", ["AS-1"]],
                                              "ref_doctype": ["in", ["Output Pay Run", "Daily Production Report"]]}
      and read_of["Output Pay Line"][2] == {"parenttype": "Output Pay Run", "parent": ["in", ["OPR-1"]]}
      and {row["salary_slip_id"]: (row["piece_1"], row["piece_2"]) for row in week_rows}["S2"] == (33200.0, 4140.0)
      and ("cached", "Company", "Luuka Plastics Limited", "abbr") in week.calls,
      (read_of.get("Salary Detail"), read_of.get("Additional Salary"), read_of.get("Output Pay Line")))
check("whoever may not open the Salary Register is refused a weekly payroll's too",
      str(run(Site(frequency="Weekly", tables=WEEKLY, report_roles=False))).startswith("refused")
      and str(run(Site(frequency="Weekly", tables=WEEKLY, may_read=False))).startswith("refused"))
week = Site(frequency="Weekly", tables=WEEKLY)
run(week, "download_salary_register")
sent = next(call[1] for call in week.calls if call[0] == "xlsx")
check("its Excel file ends with the totals, as the team's own sheet does; a monthly payroll's does not",
      sent[0] == labels and sent[-1][labels.index("Employee Name")] == "Total"
      and sent[-1][labels.index("Gross Amount")] == 187459.5 and len(sent) == 6, sent[-1])
# arrears: added under the earning in use now or under Arrears, as earlier runs paid them; taken back as a deduction
OWED = dict(WEEKLY, **{"Salary Detail": WEEKLY["Salary Detail"] + [
    {"parent": "S1", "parentfield": "earnings", "salary_component": "Arrear", "amount": 300, "additional_salary": None},
    {"parent": "S1", "parentfield": "deductions", "salary_component": "Arrears Deductions", "amount": 200,
     "additional_salary": None}]})
owed_columns, owed_rows = run(Site(frequency="Weekly", tables=OWED))
owed_labels = [column["label"] for column in owed_columns]
check("arrears added are one Arrears column, under the earning the site adds them under now and under Arrears, as "
      "earlier runs paid them; arrears taken back are a deduction, in a column of its own after Salary Advance",
      {row["employee"]: row["arrears"] for row in owed_rows} == {"C1": 300.0, "C2": 0.0, "C3": 11141.0, "C4": 0.0}
      and owed_labels.count("Arrears") == 1 and "Arrear" not in owed_labels
      and owed_labels[owed_labels.index("Salary Advance") + 1] == "Arrears Deductions"
      and {row["employee"]: row["deduction_1"] for row in owed_rows} == {"C1": 200.0, "C2": 0.0, "C3": 0.0, "C4": 0.0},
      (owed_labels, [(row["employee"], row["arrears"]) for row in owed_rows]))
piece_pay.arrears_components = lambda: ("Back Pay", "Overpaid")
chosen_columns, chosen_rows = run(Site(frequency="Weekly", tables=dict(WEEKLY, **{"Salary Detail": WEEKLY[
    "Salary Detail"] + [{"parent": "S1", "parentfield": "earnings", "salary_component": "Back Pay", "amount": 300,
                         "additional_salary": None}]})))
piece_pay.arrears_components = lambda: ("Arrear", "Arrears Deductions")
check("where Output Pay Settings name another earning for arrears, that one is read",
      {row["employee"]: row["arrears"] for row in chosen_rows} == {"C1": 300.0, "C2": 0.0, "C3": 11141.0, "C4": 0.0}
      and "Back Pay" not in [column["label"] for column in chosen_columns],
      [column["label"] for column in chosen_columns])
for name, needle in (("weekly_pay.py", 'HOURS = "custom_weekly_hours"'), ("weekly_pay.py", 'RATE = "custom_weekly_rate"'),
                     ("weekly_pay.py", 'OVERTIME_HOURS = "custom_weekly_overtime_hours"'),
                     ("weekly_pay.py", 'OVERTIME_COMPONENT = ("Casual Overtime", "COT")'),
                     ("output_pay.py", 'SIZE = "Output Rate"'),
                     ("advances.py", 'DEFAULT_COMPONENT = "Advance Recovery"'),
                     ("output_pay.py", 'RUN = "Output Pay Run"'), ("output_pay.py", 'REPORT_LINE = "Daily Production Line"'),
                     ("output_pay.py", "def _component_name(section):")):
    check("%s still has what the weekly register reads of it: %s" % (name, needle),
          needle in read("hrms_addon", "hrms_addon", name))
check("piece_pay.py still has what the weekly register reads of the arrears: the earning they are added under, "
      "Output Pay Settings' or the site's, and the one earlier runs paid them under",
      "\ndef arrears_components():\n" in read("hrms_addon", "hrms_addon", "piece_pay.py")
      and '\nARREARS_BEFORE = "Arrears"\n' in read("hrms_addon", "hrms_addon", "piece_pay.py")
      and '"arrears": {piece_pay.arrears_components()[0], piece_pay.ARREARS_BEFORE},'
      in read("hrms_addon", "hrms_addon", "payroll_register.py"))
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
      re.search(r"refresh\(frm\) \{\s*ha_payroll_recreate_button\(frm\);\s*ha_payroll_share_buttons\(frm\);\s*(ha_payroll_bank_file_button\(frm\);\s*)?ha_payroll_register\(frm\);\s*(ha_payroll_ugx\(frm\);\s*)?ha_payroll_period\(frm\);\s*ha_weekly\(frm\);\s*(ha_weekly_pieces_button\(frm\);\s*)?(ha_payroll_attendance\(frm\);\s*)?(ha_payroll_hours_column\(frm\);\s*)?\}", script)
      and re.search(r"on_tab_change\(frm\) \{\s*ha_payroll_register\(frm\);\s*(ha_payroll_ugx\(frm\);\s*)?\}", script)
      and "tab.df.fieldname !== HA_PAYROLL_REGISTER_TAB) return;" in script)
check("with fetch, so a register that cannot load says so in the tab, not in a dialog",
      'fetch("/api/method/" + HA_PAYROLL_REGISTER_METHOD' in script and ".call({" not in script.split(
          "function ha_payroll_register(")[1])
check("the total row says Total under the first column of whichever register it is, and gives none to a serial "
      "number or a rate",
      "const first = shown.length ? shown[0].fieldname : null;" in script
      and "shown.map((column) => ha_payroll_register_column(column, rows, first));" in script
      and "if (df.id === first) return `<b>${__(\"Total\")}</b>`;" in script
      and "if (df.no_total || !frappe.model.is_numeric_field(df.fieldtype)) return \"\";" in script)
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
                      "custom_absent_amount": 30769.23, "custom_basic_salary": 800000, "custom_hours_worked": 0},
      shown["E1"])
check("half days as they are, and the Basic with an Additional Salary on it whole", shown["E2"] == {
    "custom_working_days": 31, "custom_paid_days": 30.5, "custom_absent_days": 0.5, "custom_absent_amount": 5769.23,
    "custom_basic_salary": 350000, "custom_hours_worked": 0}, shown["E2"])
check("a row with no slip and nothing expected shows nothing of an earlier one", shown["E3"] == R.NO_FIGURES, shown["E3"])
check("only those with no slip are worked out", ("expected", "HR-PRUN-2026-00016", ["E3"]) in site.calls, site.calls)
asked = [call for call in site.calls if call[0] == "get_all"]
check("the slips read are the payroll's, cancelled ones left out, all of them",
      asked[0] == ("get_all", "Salary Slip", {"payroll_entry": "HR-PRUN-2026-00016", "docstatus": ["<", 2]},
                   ["name", "employee", "custom_days_in_period", "custom_days_paid", "absent_days",
                    "custom_absent_amount", "custom_weekly_hours"], 0),
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
        ("custom_basic_salary", "Basic Salary", "Currency", 2, "custom_absent_amount"),
        # a weekly casual's hours (Luuka, 12 Nov 2026: "add hours worked on the weekly payroll")
        ("custom_hours_worked", "Hours Worked", "Float", 1, "custom_basic_salary"))
for fieldname, label, fieldtype, columns, after in LOOK:
    field = fields.get("Payroll Employee Detail-%s" % fieldname) or {}
    check("the Employees table's %s: in that order, a column of its own" % label,
          (field.get("fieldname"), field.get("label"), field.get("fieldtype"), field.get("columns"),
           field.get("insert_after"), field.get("in_list_view")) == (fieldname, label, fieldtype, columns, after, 1), field)
    check("and nobody types in it; a submitted payroll saved with it shown is not refused",
          field.get("read_only") == 1 and field.get("allow_on_submit") == 1 and field.get("no_copy") == 1, field)
    check("and it reads as days with their halves, or in the payroll's currency",
          field.get("precision") == ("2" if fieldname == "custom_hours_worked" else "1") if fieldtype == "Float"
          else field.get("options") == "currency", field)
    check("and it is in the fixtures the app ships", '"Payroll Employee Detail-%s",' % fieldname in hooks_src)
check("every figure the rules give has its field", set(R.NO_FIGURES) == {one[0] for one in LOOK})
check("a slip's hours are its week's", R.SLIP_FIGURES["custom_hours_worked"] == "custom_weekly_hours")
check("the Hours Worked column shows on a weekly payroll only, as it opens and as its dates or frequency change; a "
      "Frappe without the grid's own switch shows it always",
      "\t\tha_payroll_attendance(frm);\n\t\tha_payroll_hours_column(frm);\n\t}," in script
      and "\tha_weekly_changed(frm);\n\tha_payroll_hours_column(frm);\n}" in script
      and "const hide = ha_weekly_on(frm) ? 0 : 1;" in script
      and 'grid.set_column_disp_in_list_view("custom_hours_worked", !hide);' in script
      and "if (!grid || !grid.set_column_disp_in_list_view) return;" in script)
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
