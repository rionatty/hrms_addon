# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The payroll's bank file: the Bank File button on a Payroll Entry whose
slips are submitted (Payroll Processing chart, step 7: the Finance Officer
shares the file with the bank). What is in it, and what stops it, is
bank_file_rules.py; the leave advance run's file is made the same way
(leave_advances.bank_file).

Each person's bank details are read from their employee record as it is
now, not from the slip: a bank account changed since the slips were made
is the one paid into.

The file carries every account number on the payroll, so it is made only
for those who may see bank details at all: the roles granted the Employee's
salary and bank fields (security_rules.PRIVILEGED_ROLES).

A bank's code is set once on the bank in the Bank list, which ERPNext opens
to the System Manager alone. setup_on_migrate opens it to those who run the
payroll.
"""

import frappe
from frappe import _
from frappe.utils import cint

from hrms_addon.hrms_addon import bank_file_rules as rules

PAYROLL = "Payroll Entry"
SLIP = "Salary Slip"
EMPLOYEE = "Employee"
BANK = "Bank"
CODE = "custom_bank_code"
BRANCH = "custom_bank_branch"
WEEKLY = "Weekly"
TITLE = "Bank File"
# the level the Employee's bank fields are at (security_rules.PROTECTED_LEVEL)
BANK_DETAILS_LEVEL = 1
# who sets a bank's code, and who may read the Bank list
BANK_GRANTS = {
    "HR Manager": ("read", "write", "create"),
    "Payroll Officer": ("read", "write", "create"),
    "HR User": ("read",),
}


def setup_on_migrate():
    """after_migrate: the Bank list for those who run the payroll."""
    try:
        from hrms_addon.hrms_addon import security

        if frappe.db.exists("DocType", BANK):
            security.grant({BANK: dict(BANK_GRANTS)})
            frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="HRMS Addon: Bank list for payroll failed")
        print("HRMS Addon: Bank list for payroll FAILED, see Error Log")


@frappe.whitelist()
def check(payroll_entry):
    """How many the payroll's bank file pays, what it leaves blank, and who it leaves out. One paid by bank with no
    account number, bank or bank code is in it with that left blank and said (Luuka, 13 Nov 2026: "if moble phone/
    bank account ist should be blank on that employee"). Refuses only an empty file."""
    lines = lines_of(payroll(payroll_entry))
    refuse_empty(lines)
    other, unknown = rules.not_by_bank(lines)
    return {"rows": len(rules.to_pay(lines)), "other": len(other), "unknown_count": len(unknown),
            "unknown": rules.people(unknown) if unknown else "",
            "blank": rules.problem_lines(rules.problems(lines), heading=rules.BLANK)}


@frappe.whitelist()
def download(payroll_entry):
    """The payroll's bank file, as Excel."""
    from frappe.desk.utils import provide_binary_file

    run = payroll(payroll_entry)
    lines = lines_of(run)
    refuse_empty(lines)
    provide_binary_file(file_name(run), "xlsx", rules.workbook(rules.rows(lines)))


def payroll(payroll_entry):
    """The payroll, once it is clear the user may have its bank file and
    there is one to have."""
    run = frappe.get_doc(PAYROLL, payroll_entry)
    run.check_permission("read")
    may_see_bank_details()
    if run.docstatus != 1 or not cint(run.salary_slips_submitted):
        frappe.throw(_("Submit the salary slips first. The bank file pays the submitted slips."), title=_(TITLE))
    return run


def file_name(run):
    from hrms_addon.hrms_addon import payslip_rules

    period = payslip_rules.slip_for(run.end_date, run.start_date if run.payroll_frequency == WEEKLY else None)
    return " ".join(part for part in (TITLE, period, run.name) if part)


def lines_of(run):
    """One line for each submitted slip of the payroll: who, what they are
    paid, and their bank details as they now stand."""
    slips = frappe.get_all(SLIP, filters={"payroll_entry": run.name, "docstatus": 1},
                           fields=["employee", "employee_name", "net_pay"], order_by="employee asc",
                           limit_page_length=0)
    if not slips:
        frappe.throw(_("This payroll has no submitted salary slips."), title=_(TITLE))
    details = employee_details([slip.employee for slip in slips])
    codes = bank_codes({person.bank_name for person in details.values() if person.bank_name})
    lines = []
    for slip in slips:
        person = details.get(slip.employee) or frappe._dict()
        lines.append({
            "employee": slip.employee,
            "employee_name": slip.employee_name,
            "salary_mode": person.salary_mode,
            "bank_name": person.bank_name,
            "bank_branch": person.get(BRANCH),
            "bank_code": rules.bank_code(person.get(CODE), codes.get(rules.clean(person.bank_name).lower())),
            "bank_ac_no": person.bank_ac_no,
            "amount": slip.net_pay,
        })
    return lines


def may_see_bank_details():
    """Only those who may see the Employee's bank fields get everyone's."""
    if BANK_DETAILS_LEVEL not in frappe.get_meta(EMPLOYEE).get_permlevel_access("read"):
        frappe.throw(_("Only HR and Payroll may see bank details."), frappe.PermissionError, title=_(TITLE))


def employee_details(employees):
    """{employee: their salary mode and bank details}."""
    if not employees:
        return {}
    meta = frappe.get_meta(EMPLOYEE)
    fields = ["name", "salary_mode", "bank_name", "bank_ac_no"] + [
        field for field in (BRANCH, CODE) if meta.has_field(field)]
    return {row.name: row for row in frappe.get_all(EMPLOYEE, filters={"name": ["in", sorted(set(employees))]},
                                                     fields=fields, limit_page_length=0)}


def bank_codes(bank_names):
    """{bank name in lower case: the code set on that bank in the Bank list}."""
    names = sorted({rules.clean(name) for name in bank_names or () if rules.clean(name)})
    if not names or not frappe.db.exists("DocType", BANK) or not frappe.get_meta(BANK).has_field(CODE):
        return {}
    found = frappe.get_all(BANK, filters={"name": ["in", names]}, fields=["name", CODE], limit_page_length=0)
    return {rules.clean(row.name).lower(): row.get(CODE) for row in found if row.get(CODE)}


def add_bank_details(lines):
    """An advance run's lines (leave_advances.py, salary_advances.py), each with its employee's bank branch and,
    where the line has no bank code, the employee's own, else their bank's. The rest of the line is the run's."""
    details = employee_details([line.get("employee") for line in lines if line.get("employee")])
    codes = bank_codes({line.get("bank_name") for line in lines if line.get("bank_name")})
    for line in lines:
        person = details.get(line.get("employee")) or frappe._dict()
        line["bank_branch"] = person.get(BRANCH)
        if not rules.compact(line.get("bank_code")):
            line["bank_code"] = rules.bank_code(person.get(CODE), codes.get(rules.clean(line.get("bank_name")).lower()))
    return lines


def code_of(employee, bank_name):
    """One employee's bank code: their own, else their bank's."""
    own = frappe.db.get_value(EMPLOYEE, employee, CODE) if frappe.get_meta(EMPLOYEE).has_field(CODE) else None
    banks = bank_codes({bank_name}) if bank_name else {}
    return rules.bank_code(own, banks.get(rules.clean(bank_name).lower())) or None


def refuse_problems(lines):
    """An advance run's file: none the bank cannot pay in full, and no empty file. A payroll's is made with what is
    missing left blank (check, download)."""
    said = rules.problem_lines(rules.problems(lines))
    if said:
        from frappe.utils import escape_html


        frappe.throw("<br>".join(escape_html(line) for line in said), title=_(TITLE))
    refuse_empty(lines)


def refuse_empty(lines):
    """No empty file."""
    if not rules.to_pay(lines):
        frappe.throw(_("Nobody here is paid by bank, so there is no bank file. Those paid in cash through mobile "
                       "money are in the Mobile Money File."), title=_(TITLE))
