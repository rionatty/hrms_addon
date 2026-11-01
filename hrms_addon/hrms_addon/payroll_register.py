# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Salary Register tab on a Payroll Entry (rules: payroll_register_rules.py;
the tab: public/js/payroll_entry.js; scripts/verify_payroll_register.py).

  salary_register            the register of the payroll's own salary slips,
                             drafts or submitted, for the tab
  download_salary_register   the same as an Excel file

Both run Frappe HR's own Salary Register, with the Absent Amount the app adds
to it (report_extensions.SalaryRegisterColumns), over the payroll's period,
company and currency, and keep the rows of the payroll's slips. Whoever may
not open the Salary Register is refused here as the report refuses them.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import payroll_register_rules as rules

DOCTYPE = "Payroll Entry"
SLIP = "Salary Slip"
REGISTER = "Salary Register"


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
    # as frappe.desk.query_report.get_report_doc checks it before the report runs
    report = frappe.get_doc("Report", REGISTER)
    if not report.is_permitted() or not frappe.has_permission(report.ref_doctype, "report"):
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
