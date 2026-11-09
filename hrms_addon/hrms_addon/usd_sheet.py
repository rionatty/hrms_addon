# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The UGX Payroll tab of a payroll in another currency: its slips in shillings, laid out as Luuka's own expatriate
payroll sheet, and its Excel file (Luuka, 10 Nov 2026: "where the UGX values for USD payroll").

Each slip's figures are worked out by the USD structure's own formulas in shillings (currency_payroll_rules.
gross_up_amounts), from what the slip's formulas are given (its get_data_for_eval, the USD pay among them), before any
cent is rounded. The layout and the sums are in usd_sheet_rules.py.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import currency_payroll, currency_payroll_rules, usd_sheet_rules as rules

try:  # the evaluator Frappe HR v16 works a slip's formulas out with
    from hrms.payroll.utils import _safe_eval as _evaluate
except ImportError:  # pragma: no cover
    _evaluate = frappe.safe_eval

SLIP = "Salary Slip"
AMOUNTS = currency_payroll_rules.gross_up_amounts()
WORKED = ("gross", "lst", "paye_exact", "employee_exact", "employer_exact")


@frappe.whitelist()
def ugx_payroll(payroll_entry):
    """The tab: {on, columns, rows (the total row last), title, company}; on is 0 on a payroll in shillings."""
    run, home = _run(payroll_entry)
    if not run:
        return {"on": 0}
    return {"on": 1, "columns": rules.columns(), "rows": rules.shown(rows_of(run, home)),
            "title": rules.sheet_title(run.end_date), "company": run.company}


@frappe.whitelist()
def download_ugx_payroll(payroll_entry):
    """The tab as an Excel file."""
    from frappe.desk.utils import provide_binary_file

    run, home = _run(payroll_entry)
    if not run:
        frappe.throw(_("This payroll is paid in {0}, so it has no UGX Payroll.").format(home))
    content = rules.workbook(run.company, rules.sheet_title(run.end_date), rows_of(run, home))
    provide_binary_file("%s %s" % (_("UGX Payroll"), run.name), "xlsx", content)


def _run(payroll_entry):
    run = frappe.get_doc("Payroll Entry", payroll_entry)
    run.check_permission("read")
    home = currency_payroll.company_currency(run.company)
    if not currency_payroll_rules.foreign(run.currency, home):
        return None, home
    frappe.has_permission(SLIP, "read", throw=True)
    return run, home


def rows_of(run, home):
    """A row a slip of the payroll, drafts or submitted, none cancelled, by name."""
    abbr = frappe.get_cached_value("Company", run.company, "abbr")
    names = frappe.get_all(SLIP, filters={"payroll_entry": run.name, "docstatus": ["<", 2]},
                           order_by="employee_name asc, name asc", pluck="name")
    rows = []
    for name in names:
        slip = frappe.get_doc(SLIP, name)
        data, _default = slip.get_data_for_eval()
        worked = {key: _evaluate(AMOUNTS[key], dict(slip.whitelisted_globals), data) for key in WORKED}
        rate = flt(slip.get(currency_payroll_rules.RATE_FIELD) or slip.exchange_rate)
        person = {"employee": slip.employee, "employee_name": slip.employee_name,
                  "department": rules.department_label(slip.department, abbr)}
        rows.append(rules.sheet_row(len(rows) + 1, person, {
            "usd": data.get(currency_payroll_rules.PAY_ABBR), "rate": rate,
            "allowance": data.get(currency_payroll_rules.ALLOWANCES), "gross": worked["gross"], "lst": worked["lst"],
            "paye": worked["paye_exact"], "employee": worked["employee_exact"], "employer": worked["employer_exact"],
            "advance": _recovered(slip, home, rate)}))
    return rows


def _recovered(slip, home, rate):
    """ADVANCE: what the slip takes back through Additional Salary, in shillings as recorded; one recorded in the
    slip's currency at the slip's rate."""
    names = [row.additional_salary for row in slip.deductions if row.get("additional_salary")]
    if not names:
        return 0.0
    total = 0.0
    for record in frappe.get_all("Additional Salary", filters={"name": ["in", names]}, fields=["amount", "currency"]):
        amount = flt(record.amount)
        if (record.currency or home) != home:
            amount *= rate
        total += amount
    return total
