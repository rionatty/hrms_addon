# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The Salary Register tab on a Payroll Entry, and each employee's figures on
its Employees tab (rules: payroll_register_rules.py; the tab:
public/js/payroll_entry.js; scripts/verify_payroll_register.py).

  salary_register            the register of the payroll's own salary slips,
                             drafts or submitted, for the tab. A weekly
                             payroll's is laid out as the team's Casual
                             Master Payroll (casual_register)
  download_salary_register   the same as an Excel file
  employee_figures           Payroll Entry onload: each row of the Employees
                             table given the working days and paid days its
                             slip shows, its absent days, absent amount and
                             Basic; until there is a slip, what it will show
                             (slip_figures.py)

The first two run Frappe HR's own Salary Register, with the Absent Amount the
app adds to it (report_extensions.SalaryRegisterColumns), over the payroll's
period, company and currency, and keep the rows of the payroll's slips.
Whoever may not open the Salary Register is refused here as the report
refuses them, and is not shown the figures.
"""

import frappe
from frappe import _

from hrms_addon.hrms_addon import pay_days_rules, payroll_register_rules as rules, slip_figures, weekly_pay_rules

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
    # a weekly payroll's ends with its totals, as the team's own sheet does
    weekly = any(column.get("fieldname") == rules.OVERTIME_HOURS for column in columns)
    content = make_xlsx(rules.sheet(columns, rows, total=weekly), _(REGISTER)).getvalue()
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
    if weekly_pay_rules.on_weekly_pay(run):
        return casual_register(run, [slip.name for slip in slips])
    # no Document Status: the register then lists drafts and submitted slips alike
    result = report.execute_module({"company": run.company, "currency": run.currency,
                                    "from_date": min(slip.start_date for slip in slips),
                                    "to_date": max(slip.end_date for slip in slips)}) or ([], [])
    return rules.register_of(result[0], result[1] if len(result) > 1 else [], [slip.name for slip in slips])


def casual_register(run, names):
    """(columns, rows) of a weekly payroll's register, laid out as the team's Casual Master Payroll (Luuka, 12 Nov
    2026): each casual's hours, rate, basic, pieces by their category, overtime hours and pay, arrears, gross,
    what was taken off, net, TIN and NSSF, read from the payroll's own slips."""
    from hrms_addon.hrms_addon import advances, output_pay, output_rules, piece_pay, weekly_pay

    slips = frappe.get_all(SLIP, filters={"name": ["in", names]}, limit_page_length=0, fields=[
        "name", "employee", "employee_name", "department", "currency", "gross_pay", "net_pay", "total_loan_repayment",
        "%s as hours" % weekly_pay.HOURS, "%s as rate" % weekly_pay.RATE,
        "%s as overtime_hours" % weekly_pay.OVERTIME_HOURS])
    lines = frappe.get_all(DETAIL, filters={"parenttype": SLIP, "parent": ["in", names],
                                            "parentfield": ["in", ["earnings", "deductions"]]},
                           fields=["parent", "parentfield", "salary_component", "amount", "do_not_include_in_total",
                                   "additional_salary"], limit_page_length=0)
    employees = sorted({slip.employee for slip in slips if slip.employee})
    people = {row.name: {"tin": row.custom_tin, "nssf": row.custom_nssf_no} for row in frappe.get_all(
        "Employee", filters={"name": ["in", employees]}, fields=["name", "custom_tin", "custom_nssf_no"],
        limit_page_length=0)} if employees else {}
    sizes = frappe.get_all(output_pay.SIZE, filters={"section": output_rules.PER_PIECE},
                           fields=["name", "salary_component"], limit_page_length=0)
    named = {"basic": output_pay._component_name(output_rules.HOURLY), "overtime": weekly_pay.OVERTIME_COMPONENT[0],
             # arrears under the earning they are added under now, Output Pay Settings' or the site's, and under
             # the one earlier runs paid them under; arrears taken back are a deduction, with its own column
             "arrears": {piece_pay.arrears_components()[0], piece_pay.ARREARS_BEFORE},
             "advance": advances.DEFAULT_COMPONENT,
             "pieces": {output_pay._component_name(output_rules.PER_PIECE)}
             | {row.salary_component for row in sizes if row.salary_component}}
    return rules.casual_register(slips, lines, people, _pieces(slips, lines), named,
                                 frappe.get_cached_value("Company", run.company, "abbr"))


def _pieces(slips, lines):
    """{slip: {size: what its pieces came to}}: from the runs, and the reports from before a run paid Per Piece,
    that wrote the slips' Additional Salaries (rules.pieces_by_size)."""
    from hrms_addon.hrms_addon import output_pay

    linked = sorted({line.additional_salary for line in lines if line.get("additional_salary")})
    if not linked:
        return {}
    written = {row.name: row for row in frappe.get_all(
        "Additional Salary", filters={"name": ["in", linked], "ref_doctype": ["in", [output_pay.RUN, output_pay.REPORT]]},
        fields=["name", "employee", "ref_doctype", "ref_docname"], limit_page_length=0)}
    paid = [{"slip": line.parent, "source": written[line.additional_salary].ref_docname,
             "employee": written[line.additional_salary].employee}
            for line in lines if line.get("additional_salary") in written]
    found = []
    for doctype, child in ((output_pay.RUN, "Output Pay Line"), (output_pay.REPORT, output_pay.REPORT_LINE)):
        sources = sorted({row.ref_docname for row in written.values() if row.ref_doctype == doctype and row.ref_docname})
        if sources:
            found += [dict(row, source=row.parent) for row in frappe.get_all(
                child, filters={"parenttype": doctype, "parent": ["in", sources]},
                fields=["parent", "employee", "size", "amount"], limit_page_length=0)]
    return rules.pieces_by_size(paid, found)


def employee_figures(doc, method=None):
    """Payroll Entry onload, which also runs on the save Get Employees ends with. The figures are read from the slips
    as the form opens, as Frappe HR's own onload sets the Overtime Step, and are not kept: a slip made again or changed
    while a draft shows as it now is. A row with no slip yet shows what its slip will. If they cannot be read the
    payroll still opens."""
    figures = {}
    try:
        if _report_if_permitted():
            figures = _figures(doc.name)
            figures.update(slip_figures.expected(doc, [row.employee for row in doc.get("employees") or []
                                                       if row.employee not in figures]))
    except Exception:
        frappe.log_error(title="HRMS Addon: employee figures on %s" % doc.name, defer_insert=True)
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
