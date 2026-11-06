"""Checks the employer's own share of pay (Luuka's NSSF 10%) booked with the payroll, without a bench:

    python scripts/verify_employer_costs.py

The user, 6 Nov 2026, of the accrual entry booking the 10% with Payroll Payable left at the net pay: "istn this being
already hadled by the standard system? if no please proceed". It is not: Frappe HR v16's accrual entry posts only earnings
and deductions.

  1  the rules: which slip lines are the employer's share, and what a Cost Account must be
  2  Frappe HR's own accrual entry, its methods lifted from the source, with the app's on top: the UGX deduction left out
     of the total (posted, or not), the USD employer contribution at the month's rate, cost centres, employee-wise
     accounting, a share with no Cost Account
  3  reads that do not grow with the slips
  4  wiring: the field, the hooks, the form
  5  upstream: what it stands on in Frappe HR
"""
import ast
import importlib.util
import json
import os
import re
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(REPO, "hrms_addon")
APP = os.path.join(PACKAGE, "hrms_addon")
APPS_ROOT = os.environ.get("FRAPPE_APPS_ROOT", os.path.join(os.path.dirname(REPO), "ERPNext"))
ENTRY_SOURCE = os.path.join(APPS_ROOT, "hrms", "hrms", "payroll", "doctype", "payroll_entry", "payroll_entry.py")
fail = []


def check(condition, label, detail=""):
    print("ok  " if condition else "FAIL", label, "" if condition else detail)
    if not condition:
        fail.append(label)


def read(*parts):
    return open(os.path.join(REPO, *parts), encoding="utf-8").read()


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(APP, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["hrms_addon.hrms_addon." + name] = module
    return module


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


package = types.ModuleType("hrms_addon")
package.__path__ = []
app = types.ModuleType("hrms_addon.hrms_addon")
app.__path__ = []
sys.modules.update({"hrms_addon": package, "hrms_addon.hrms_addon": app})
R = load("employer_costs_rules")  # proves it has no Frappe import
print("loaded employer_costs_rules.py without Frappe")

# ── 1. The rules ─────────────────────────────────────────
ROWS = [
    {"parentfield": "deductions", "salary_component": "NSSF Employer 10%", "amount": 100000, "do_not_include_in_total": 1,
     "do_not_include_in_accounts": 0, "employee": "E1", "salary_structure": "S"},
    {"parentfield": "deductions", "salary_component": "NSSF Employer 10%", "amount": 80000, "do_not_include_in_total": 1,
     "do_not_include_in_accounts": 1, "employee": "E2", "salary_structure": "S"},
    {"parentfield": "employer_contributions", "salary_component": "NSSF Employer Contribution", "amount": 100, "employee": "U1",
     "salary_structure": "USD"},
    {"parentfield": "deductions", "salary_component": "NSSF Employee", "amount": 50000, "do_not_include_in_total": 0,
     "employee": "E1", "salary_structure": "S"},
    {"parentfield": "deductions", "salary_component": "Statistic", "amount": 9, "do_not_include_in_total": 1,
     "employee": "E1", "salary_structure": "S"},
    {"parentfield": "deductions", "salary_component": "NSSF Employer 10%", "amount": 0, "do_not_include_in_total": 1,
     "employee": "E3", "salary_structure": "S"},
]
COSTS = {"NSSF Employer 10%": "5236", "NSSF Employer Contribution": "5236", "NSSF Employee": "5236"}
lines, missing = R.employer_lines(ROWS, COSTS)
check([(line["employee"], line["amount"], line["posted"]) for line in lines] == [("E1", 100000.0, True), ("E2", 80000.0, False),
                                                                                ("U1", 100.0, False)] and missing == [],
      "the employer's share: an Employer Contribution line, and a deduction left out of the total with a Cost Account; "
      "posted where Frappe HR's entry has it in the accounts", lines)
check(not [line for line in lines if line["component"] in ("NSSF Employee", "Statistic")],
      "a deduction in the total is the employee's own, whatever its account says; one with no Cost Account is left to Frappe HR")
lines, missing = R.employer_lines(ROWS, {"NSSF Employer 10%": "5236"})
check(missing == ["NSSF Employer Contribution"] and len(lines) == 2, "an Employer Contribution line with no Cost Account is named", missing)
check("NSSF Employer Contribution" in R.missing_message(["NSSF Employer Contribution"], "LPT") and "Cost Account" in
      R.missing_message(["X"], "LPT"), "and the message says where to set it")
check(R.cost_account_errors("LPT", {"name": "5236", "company": "LPT", "is_group": 0, "root_type": "Expense"}) == []
      and len(R.cost_account_errors("LPT", {"name": "A", "company": "OC", "is_group": 1, "root_type": "Liability"})) == 3
      and R.cost_account_errors("LPT", None) == [],
      "a Cost Account is an expense ledger of the row's company")
print("rules: which lines are the employer's share")

# ── 2. Frappe HR's own accrual entry, with the app's on top ──
THROWN = []


class Thrown(Exception):
    pass


def throw(message, title=None, *args, **kwargs):
    THROWN.append(message)
    raise Thrown(message)


SITE = Row(rows=[], slips=[], employee_wise=0, has_field=True, accounts={}, costs={}, calls=[])
ACCOUNT_CURRENCY = {"2121 - Payroll Payable USD": "USD"}


def get_all(doctype, filters=None, fields=None, limit_page_length=None, pluck=None, **kwargs):
    SITE.calls.append(doctype)
    if doctype == "Salary Slip":
        return [Row(name=slip.name, employee=slip.employee, salary_structure=slip.salary_structure) for slip in SITE.slips
                if slip.name in filters["name"][1]]
    if doctype == "Salary Detail":
        return [Row(row) for row in SITE.rows if row["parent"] in filters["parent"][1] and row["parentfield"] in filters["parentfield"][1]]
    if doctype == "Salary Component Account":
        # each company's own row, and another company's after it, as a component has one per company
        rows = [Row(parent=name, company="LPT", custom_cost_account=account) for name, account in SITE.costs.items()]
        rows += [Row(parent=name, company="OTHER CO", custom_cost_account="9999 - Another Company's Cost") for name in SITE.costs]
        return [row for row in rows if row.parent in filters["parent"][1]
                and ("company" not in filters or row.company == filters["company"])]
    raise AssertionError(doctype)


frappe = types.ModuleType("frappe")
frappe._ = lambda text, *args, **kwargs: text
frappe.throw = throw
frappe.get_all = get_all
frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda field: SITE.has_field)
frappe.get_precision = lambda doctype, field: 2
frappe.db = types.SimpleNamespace(get_single_value=lambda doctype, field: SITE.employee_wise,
                                  get_value=lambda doctype, name, field, *args, **kwargs: ACCOUNT_CURRENCY.get(name, "UGX"))
utils = types.ModuleType("frappe.utils")
utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
sys.modules.update({"frappe": frappe, "frappe.utils": utils})
C = load("employer_costs")

if os.path.exists(ENTRY_SOURCE):
    source = open(ENTRY_SOURCE, encoding="utf-8").read()
    LIFTED = ("make_accrual_jv_entry", "get_salary_component_total", "get_account", "get_payable_amount_for_earnings_and_deductions",
              "set_payable_amount_against_payroll_payable_account", "get_accounting_entries_and_payable_amount",
              "update_accounting_dimensions", "get_amount_and_exchange_rate_for_journal_entry",
              "set_accounting_entries_for_advance_deductions", "set_employee_based_payroll_payable_entries",
              "get_advance_deduction", "add_advance_deduction_entry")
    bodies = []
    for name in LIFTED:
        found = re.search(r"^\tdef %s\(.*?(?=^\tdef |^\t@|^def |^@|\Z)" % name, source, re.S | re.M)
        assert found, name
        bodies.append(found.group(0))
    namespace = {"frappe": frappe, "_": frappe._, "flt": utils.flt,
                 "erpnext": types.SimpleNamespace(get_company_currency=lambda company: "UGX"),
                 "get_accounting_dimensions": lambda: []}
    exec("class LiftedEntry:\n" + "".join(bodies), namespace)

    class FrappeEntry(namespace["LiftedEntry"]):
        """Frappe HR's Payroll Entry as far as its accrual entry goes; what reads the database, as it reads."""

        def __init__(self, exchange_rate=1, payable="2120 - Payroll Payable"):
            self.company, self.cost_center, self.project = "LPT", "Main", None
            self.exchange_rate, self.payroll_payable_account = exchange_rate, payable
            self.start_date, self.end_date, self.name = "2026-08-26", "2026-09-25", "HR-PRUN-1"
            self.doctype = "Payroll Entry"
            self.journal = None

        def get(self, key, default=None):
            return getattr(self, key, default)

        def check_permission(self, ptype):
            pass

        def get_sal_slip_list(self, ss_status, as_dict=False):
            return [Row(name=slip.name, salary_structure=slip.salary_structure) for slip in SITE.slips]

        def get_salary_components(self, component_type):
            # Frappe HR's own filter: in the total, or out of it but in the accounts
            return [Row(salary_component=row["salary_component"], amount=row["amount"], parentfield=row["parentfield"],
                        additional_salary=None, salary_structure=slip.salary_structure, employee=slip.employee)
                    for row in SITE.rows for slip in SITE.slips if row["parent"] == slip.name and row["parentfield"] == component_type
                    and (not row.get("do_not_include_in_total") or not row.get("do_not_include_in_accounts"))]

        def get_salary_component_account(self, component):
            if component not in SITE.accounts:
                throw("Please set account in Salary Component %s" % component)
            return SITE.accounts[component]

        def get_payroll_cost_centers_for_employee(self, employee, salary_structure):
            return SITE.get("centres", {}).get(employee, {"Main": 100})

        def make_journal_entry(self, accounts, currencies, payroll_payable_account=None, **kwargs):
            self.journal = Row(accounts=accounts, currencies=list(currencies), kwargs=kwargs)
            return self.journal

    class Entry(C.PayrollEntryEmployerCosts, FrappeEntry):
        pass

    def posted(entry):
        """{account: debit - credit in shillings} and {account: credit in the account's own currency} of the entry."""
        net, own = {}, {}
        for row in entry.journal.accounts:
            debit, credit = row.get("debit_in_account_currency") or 0, row.get("credit_in_account_currency") or 0
            rate = row.get("exchange_rate") or 1
            net[row["account"]] = round(net.get(row["account"], 0) + (debit - credit) * rate, 2)
            own[row["account"]] = round(own.get(row["account"], 0) + credit - debit, 2)
        return net, own

    def ugx_site(posted_in_accounts=True):
        SITE.update(slips=[Row(name="SS-1", employee="E1", salary_structure="Luuka Salaried")], employee_wise=0, has_field=True,
                    accounts={"Basic": "5213 - Salary", "PAYEE": "2320 - PAYE Payable", "NSSF Employee": "2330 - NSSF Payable",
                              "NSSF Employer 10%": "2330 - NSSF Payable"},
                    costs={"NSSF Employer 10%": "5236 - NSSF Employer Contribution"}, centres={})
        SITE.rows = [
            {"parent": "SS-1", "parentfield": "earnings", "salary_component": "Basic", "amount": 1000000},
            {"parent": "SS-1", "parentfield": "deductions", "salary_component": "PAYEE", "amount": 200000},
            {"parent": "SS-1", "parentfield": "deductions", "salary_component": "NSSF Employee", "amount": 50000},
            {"parent": "SS-1", "parentfield": "deductions", "salary_component": "NSSF Employer 10%", "amount": 100000,
             "do_not_include_in_total": 1, "do_not_include_in_accounts": 0 if posted_in_accounts else 1},
        ]

    for in_accounts in (True, False):
        ugx_site(in_accounts)
        alone = FrappeEntry()
        alone.make_accrual_jv_entry([])
        net_alone, own_alone = posted(alone)
        entry = Entry()
        entry.make_accrual_jv_entry([])
        net, own = posted(entry)
        how = "kept in the accounts" if in_accounts else "left out of them"
        if in_accounts:
            check(own_alone["2120 - Payroll Payable"] == 650000, "Frappe HR alone: the 10% taken off Payroll Payable, 650,000 owed for "
                  "750,000 of net pay, and no cost booked", net_alone)
        else:
            check(own_alone.get("2120 - Payroll Payable") == 750000 and net_alone.get("2330 - NSSF Payable") == -50000,
                  "Frappe HR alone, the line out of the accounts: the 10% never reaches NSSF Payable", net_alone)
        check(sum(net.values()) == 0, "UGX, the 10%% %s: the entry balances" % how, net)
        check(own["2120 - Payroll Payable"] == 750000, "UGX, the 10%% %s: Payroll Payable is the net pay, 750,000" % how, own)
        check(own["2330 - NSSF Payable"] == 150000 and net["5236 - NSSF Employer Contribution"] == 100000,
              "UGX, the 10%% %s: NSSF Payable owes the 5%% and the 10%%, and the 10%% is a cost" % how, net)

    # the USD payroll: an employer contribution line, at the month's rate
    SITE.update(slips=[Row(name="SS-U", employee="U1", salary_structure="Luuka USD Net Pay")], employee_wise=0, centres={},
                accounts={"Basic Salary": "5213 - Salary", "Tax Paid by Company": "5237 - Staff Tax Paid by Company",
                          "PAYE": "2320 - PAYE Payable", "NSSF Employee": "2330 - NSSF Payable",
                          "Local Service Tax": "2340 - Local Service Tax Payable", "NSSF Employer Contribution": "2330 - NSSF Payable"},
                costs={"NSSF Employer Contribution": "5236 - NSSF Employer Contribution"})
    SITE.rows = [
        {"parent": "SS-U", "parentfield": "earnings", "salary_component": "Basic Salary", "amount": 1000},
        {"parent": "SS-U", "parentfield": "earnings", "salary_component": "Tax Paid by Company", "amount": 324.66},
        {"parent": "SS-U", "parentfield": "deductions", "salary_component": "PAYE", "amount": 267.94},
        {"parent": "SS-U", "parentfield": "deductions", "salary_component": "NSSF Employee", "amount": 50},
        {"parent": "SS-U", "parentfield": "deductions", "salary_component": "Local Service Tax", "amount": 6.72},
        {"parent": "SS-U", "parentfield": "employer_contributions", "salary_component": "NSSF Employer Contribution", "amount": 100},
    ]
    entry = Entry(exchange_rate=3720, payable="2121 - Payroll Payable USD")
    entry.make_accrual_jv_entry([])
    net, own = posted(entry)
    check(abs(sum(net.values())) < 0.01, "USD: the entry balances in shillings", net)
    check(own["2121 - Payroll Payable USD"] == 1000.0, "USD: Payroll Payable USD is the net pay, 1,000", own)
    check(own["2330 - NSSF Payable"] == round(150 * 3720, 2) and net["5236 - NSSF Employer Contribution"] == round(100 * 3720, 2),
          "USD: the employer's 10%, never posted by Frappe HR, is a cost and owed to NSSF, in shillings at the month's rate", net)
    check(sorted(entry.journal.currencies) == ["UGX", "USD"], "and the entry stays in two currencies", entry.journal.currencies)

    # two employees, one split between cost centres
    ugx_site(True)
    SITE.slips.append(Row(name="SS-2", employee="E2", salary_structure="Luuka Salaried"))
    SITE.rows += [dict(row, parent="SS-2") for row in SITE.rows]
    SITE.centres = {"E2": {"Factory": 60, "Office": 40}}
    entry = Entry()
    entry.make_accrual_jv_entry([])
    by_centre = {}
    for row in entry.journal.accounts:
        if row["account"] == "5236 - NSSF Employer Contribution":
            by_centre[row["cost_center"]] = by_centre.get(row["cost_center"], 0) + row["debit_in_account_currency"]
    check(by_centre == {"Main": 100000, "Factory": 60000, "Office": 40000}, "the cost follows each employee's cost centres", by_centre)
    net, own = posted(entry)
    check(own["2120 - Payroll Payable"] == 1500000 and sum(net.values()) == 0, "and Payroll Payable is both net pays", own)

    # employee-wise accounting: each employee's payable is their own net pay
    ugx_site(True)
    SITE.employee_wise = 1
    entry = Entry()
    entry.make_accrual_jv_entry([])
    payable = [row for row in entry.journal.accounts if row["account"] == "2120 - Payroll Payable"]
    check([(row.get("party"), row["credit_in_account_currency"]) for row in payable] == [("E1", 750000)],
          "employee-wise accounting: the employee's own payable is their net pay", payable)
    check(sum(posted(entry)[0].values()) == 0, "and the entry balances")

    # a share with no Cost Account stops the payroll, saying where to set it
    ugx_site(True)
    SITE.rows.append({"parent": "SS-1", "parentfield": "employer_contributions", "salary_component": "NSSF Employer Contribution",
                      "amount": 100000})
    THROWN.clear()
    try:
        Entry().make_accrual_jv_entry([])
        check(False, "an Employer Contribution line with no Cost Account stops the payroll")
    except Thrown:
        check(THROWN and "NSSF Employer Contribution" in THROWN[-1] and "Cost Account" in THROWN[-1],
              "an Employer Contribution line with no Cost Account stops the payroll, saying where to set it", THROWN)

    # before the migrate there is no Cost Account field: Frappe HR's entry as it was
    ugx_site(True)
    SITE.has_field = False
    entry = Entry()
    entry.make_accrual_jv_entry([])
    alone = FrappeEntry()
    alone.make_accrual_jv_entry([])
    check(entry.journal.accounts == alone.journal.accounts, "with no Cost Account field yet, the entry is Frappe HR's own")
    SITE.has_field = True
    print("the accrual entry: the employer's share booked, Payroll Payable at the net pay")

    # ── 3. Reads ──
    def reads(count):
        SITE.update(slips=[Row(name="SS-%d" % n, employee="E%d" % n, salary_structure="S") for n in range(count)], calls=[])
        SITE.rows = [{"parent": "SS-%d" % n, "parentfield": "deductions", "salary_component": "NSSF Employer 10%", "amount": 1000,
                      "do_not_include_in_total": 1, "do_not_include_in_accounts": 1} for n in range(count)]
        C.employer_lines(Entry())
        return len(SITE.calls)

    check(reads(3) == reads(2000) == 3, "2,000 slips take three reads, as 3 do")
else:
    print("Frappe HR's source not found here: its accrual entry not lifted")

# ── 4. Wiring ────────────────────────────────────────────
custom = {row["name"]: row for row in json.load(open(os.path.join(PACKAGE, "fixtures", "custom_field.json"), encoding="utf-8"))}
field = custom.get("Salary Component Account-custom_cost_account") or {}
check(field.get("fieldtype") == "Link" and field.get("options") == "Account" and field.get("insert_after") == "account"
      and field.get("in_list_view") == 1, "a component's account row has its Cost Account, beside the account", field)
hooks_source = read("hrms_addon", "hooks.py")
hooks = {}
for node in ast.parse(hooks_source).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        try:
            hooks[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            pass
check("hrms_addon.hrms_addon.employer_costs.PayrollEntryEmployerCosts" in hooks["extend_doctype_class"]["Payroll Entry"],
      "the Payroll Entry takes the app's accrual entry")
check(hooks["doc_events"]["Salary Component"]["validate"] == "hrms_addon.hrms_addon.employer_costs.component_validate"
      and hooks["doctype_js"]["Salary Component"] == "public/js/salary_component.js"
      and '"Salary Component Account-custom_cost_account"' in hooks_source,
      "the component checks its Cost Account, its form picks one, and the field is in the fixtures")
script = read("hrms_addon", "public", "js", "salary_component.js")
check('frm.set_query("custom_cost_account", "accounts"' in script and 'root_type: "Expense"' in script,
      "the form offers only an expense of the row's company")

# ── 5. Upstream ──────────────────────────────────────────
if os.path.exists(ENTRY_SOURCE):
    signature = re.search(r"\tdef get_payable_amount_for_earnings_and_deductions\(\s*self,(.*?)\):", source, re.S).group(1)
    names = [part.strip() for part in signature.split(",") if part.strip()]
    check(names == ["accounts", "earnings", "deductions", "currencies", "company_currency", "accounting_dimensions", "precision",
                    "payable_amount", "employee_wise_accounting_enabled"],
          "upstream: the method the app builds on takes what the app passes, in order", names)
    accrual = re.search(r"^\tdef make_accrual_jv_entry\(.*?(?=^\tdef )", source, re.S | re.M).group(0)
    check("employer_contributions" not in accrual and "self.get_payable_amount_for_earnings_and_deductions(" in accrual
          and accrual.index("get_payable_amount_for_earnings_and_deductions(") < accrual.index("set_payable_amount_against_payroll_payable_account("),
          "upstream: the accrual entry never posts an employer contribution, and works the payable out after the method")
    components = re.search(r"^\tdef get_salary_components\(.*?(?=^\tdef )", source, re.S | re.M).group(0)
    check("(ssd.do_not_include_in_total == 1) & (ssd.do_not_include_in_accounts == 0)" in components,
          "upstream: a line left out of the total but in the accounts is posted, as the app expects")
    check("def get_sal_slip_list(self, ss_status, as_dict=False):" in source
          and "def get_payroll_cost_centers_for_employee(self, employee, salary_structure):" in source
          and "def set_employee_based_payroll_payable_entries(" in source and "def get_salary_component_account(self, salary_component):" in source,
          "upstream: the Payroll Entry methods the app calls")

print()
print("FAILED: %d" % len(fail) if fail else "ALL EMPLOYER'S SHARE CHECKS PASSED")
sys.exit(1 if fail else 0)
