# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A payroll in another currency in shillings, laid out as Luuka's own expatriate payroll sheet: its UGX Payroll tab
and Excel file (Luuka, 10 Nov 2026: "where the UGX values for USD payroll"), and each slip's UGX pay slip ("the salary
slip should be in two").

Each slip's figures are worked out by the USD structure's own formulas in shillings (currency_payroll_rules.
gross_up_amounts), from what the slip's formulas are given (its get_data_for_eval, the USD pay among them), before any
cent is rounded. The layout and the sums are in usd_sheet_rules.py.

  ugx_payroll           the tab
  download_ugx_payroll  its Excel file
  slip_sheet            one slip's row, for its UGX pay slip (payslip.pay_slip)
  worked_out            what the formulas give in shillings for a slip (usd_posting.py too)
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
# the whole-shilling amounts the slip's lines are put in dollars from, and the same before they are rounded
WORKED = ("gross", "lst", "paye", "employee", "employer", "cover", "paye_exact", "employee_exact", "employer_exact")


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
        rows.append(row_of(frappe.get_doc(SLIP, name), home, abbr, len(rows) + 1))
    return rows


def slip_sheet(slip):
    """One slip's row in shillings, for its UGX pay slip: the sheet's figures, and what the slip pays in its own
    currency. None on a slip in the company's currency."""
    home = currency_payroll.company_currency(slip.company)
    if not currency_payroll_rules.foreign(slip.currency, home):
        return None
    abbr = frappe.get_cached_value("Company", slip.company, "abbr")
    row = row_of(slip, home, abbr, 1)
    row.pop("exact", None)
    row.update(currency=slip.currency, paid=flt(slip.net_pay),
               basic_label=rules.basic_label(slip.currency, row["basic_usd"], row["rate"]))
    return frappe._dict(row)


def row_of(slip, home, company_abbr, idx):
    data, worked = worked_out(slip)
    rate = flt(slip.get(currency_payroll_rules.RATE_FIELD) or slip.exchange_rate)
    person = {"employee": slip.employee, "employee_name": slip.employee_name,
              "department": rules.department_label(slip.department, company_abbr)}
    return rules.sheet_row(idx, person, {
        "usd": data.get(currency_payroll_rules.PAY_ABBR), "rate": rate,
        "allowance": data.get(currency_payroll_rules.ALLOWANCES), "gross": worked["gross"], "lst": worked["lst"],
        "paye": worked["paye_exact"], "employee": worked["employee_exact"], "employer": worked["employer_exact"],
        "advance": _recovered(slip, home, rate)})


def worked_out(slip):
    """What the USD structure's formulas give in shillings for a slip, from what its formulas are given:
    (data, {key: amount}) for the keys in WORKED."""
    data, _default = slip.get_data_for_eval()
    return data, {key: _evaluate(AMOUNTS[key], dict(slip.whitelisted_globals), data) for key in WORKED}


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
