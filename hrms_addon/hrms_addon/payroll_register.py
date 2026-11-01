# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Salary Register tab on a Payroll Entry, and each employee's figures on
its Employees tab (rules: payroll_register_rules.py; the tab:
public/js/payroll_entry.js; scripts/verify_payroll_register.py).

  salary_register            the register of the payroll's own salary slips,
                             drafts or submitted, for the tab
  download_salary_register   the same as an Excel file
  employee_figures           Payroll Entry onload: each row of the Employees
                             table given the working days and paid days its
                             slip shows, its absent days, absent amount and
                             Basic

The first two run Frappe HR's own Salary Register, with the Absent Amount the
app adds to it (report_extensions.SalaryRegisterColumns), over the payroll's
period, company and currency, and keep the rows of the payroll's slips.
Whoever may not open the Salary Register is refused here as the report
refuses them, and is not shown the figures.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import pay_days_rules, payroll_register_rules as rules

DOCTYPE = "Payroll Entry"
SLIP = "Salary Slip"
DETAIL = "Salary Detail"
REGISTER = "Salary Register"
BASIC = "Basic"


@frappe.whitelist()
def salary_register(payroll_entry):
    """The payroll's register for its tab: {"columns": [...], "rows": [...]}."""
    columns, rows = register(payroll_entry)
    return {"columns": columns, "rows": rows}


@frappe.whitelist()
def download_salary_register(payroll_entry):
    """The payroll's register as an Excel file."""
    from frappe.desk.utils import provide_binary_file
    from frappe.utils.xlsxutils import make_xlsx

    columns, rows = register(payroll_entry)
    content = make_xlsx(rules.sheet(columns, rows), _(REGISTER)).getvalue()
    provide_binary_file("%s %s" % (_(REGISTER), payroll_entry), "xlsx", content)


def register(payroll_entry):
    """(columns, rows) of Frappe HR's Salary Register for the payroll's own slips; cancelled ones left out."""
    run = frappe.get_doc(DOCTYPE, payroll_entry)
    run.check_permission("read")
    report = _report_if_permitted()
    if not report:
        frappe.throw(_("You don't have access to Report: {0}").format(_(REGISTER)), frappe.PermissionError)
    slips = frappe.get_all(SLIP, filters={"payroll_entry": run.name, "docstatus": ["<", 2]},
                           fields=["name", "start_date", "end_date"], limit_page_length=0)
    if not slips:
        return [], []
    # no Document Status: the register then lists drafts and submitted slips alike
    result = report.execute_module({"company": run.company, "currency": run.currency,
                                    "from_date": min(slip.start_date for slip in slips),
                                    "to_date": max(slip.end_date for slip in slips)}) or ([], [])
    return rules.register_of(result[0], result[1] if len(result) > 1 else [], [slip.name for slip in slips])


def employee_figures(doc, method=None):
    """Payroll Entry onload. The figures are read from the slips as the form opens, as Frappe HR's own onload sets the
    Overtime Step, and are not kept: a slip made again or changed while a draft shows as it now is. If they cannot be
    read the payroll still opens."""
    try:
        figures = _figures(doc.name) if _report_if_permitted() else {}
    except Exception:
        frappe.log_error(title="HRMS Addon: employee figures on %s" % doc.name, defer_insert=True)
        figures = {}
    for row in doc.get("employees") or []:
        row.update(figures.get(row.employee) or rules.NO_FIGURES)


def _figures(payroll_entry):
    """{employee: the figures for their row}, from the payroll's slips; cancelled ones left out."""
    slips = frappe.get_all(SLIP, filters={"payroll_entry": payroll_entry, "docstatus": ["<", 2]},
                           fields=["name", "employee", *rules.SLIP_FIGURES.values()], limit_page_length=0)
    if not slips:
        return {}
    basics = {}
    for row in frappe.get_all(DETAIL, filters={"parenttype": SLIP, "parentfield": "earnings", "salary_component": BASIC,
                                               "parent": ["in", [slip.name for slip in slips]]},
                              fields=["parent", "default_amount", "additional_amount"], limit_page_length=0):
        basics[row.parent] = basics.get(row.parent, 0) + pay_days_rules.full_amount(row)
    return rules.figures_of(slips, basics)


def _report_if_permitted():
    """The Salary Register, for whoever may open it, as frappe.desk.query_report.get_report_doc checks it."""
    report = frappe.get_doc("Report", REGISTER)
    if report.is_permitted() and frappe.has_permission(report.ref_doctype, "report"):
        return report
    return None
