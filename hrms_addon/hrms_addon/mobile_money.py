# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The payroll's mobile money file: the Mobile Money File button on a Payroll Entry whose slips are submitted, beside
the Bank File. What is in it and how it is laid out is mobile_money_rules.py.

Luuka, 13 Nov 2026: "some employee have cash paymebt through mobile moneny ist necessary that the bank file should be
only bank account employee. on the payroll this bank file for casuals as attached". The bank file stays the bank
accounts' (a bank pays an account); those paid in cash through mobile money have this one, laid out as the team's
TO BANK REPORT: each one's Wages Phone Number as the bank takes it, their net pay, and the name the phone is
registered in, from the Mobile Money section of their employee record.

Each person's number is read from their employee record as it is now, not from the slip: a number changed since the
slips were made is the one paid. The file carries everyone's phone number, so it is made only for those who may see
bank details (bank_file.may_see_bank_details), as the bank file is.
"""

import frappe
from frappe import _
from frappe.utils import cint

from hrms_addon.hrms_addon import mobile_money_rules as rules

PAYROLL = "Payroll Entry"
SLIP = "Salary Slip"
EMPLOYEE = "Employee"
WEEKLY = "Weekly"
TITLE = "Mobile Money File"
PHONE = "custom_wages_phone"
REGISTERED = "custom_wages_phone_names"


@frappe.whitelist()
def check(payroll_entry):
    """How many the payroll's mobile money file pays, whose phone it leaves blank, and who it leaves out and why.
    Refuses only an empty file."""
    lines = lines_of(payroll(payroll_entry))
    refuse_empty(lines)
    out = rules.left_out(lines)
    return {"rows": len(rules.lines_to_pay(lines)), "bank": len(out["bank"]), "cheque": len(out["cheque"]),
            "blank": rules.blank_lines(rules.blanks(lines))}


@frappe.whitelist()
def download(payroll_entry):
    """The payroll's mobile money file, as Excel."""
    from frappe.desk.utils import provide_binary_file

    run = payroll(payroll_entry)
    lines = lines_of(run)
    refuse_empty(lines)
    weekly = run.get("payroll_frequency") == WEEKLY
    provide_binary_file(file_name(run), "xlsx", rules.workbook(rules.title(run.start_date, run.end_date, weekly),
                                                               rules.rows(lines)))


def payroll(payroll_entry):
    """The payroll, once it is clear the user may have its file and its slips are submitted."""
    from hrms_addon.hrms_addon import bank_file

    run = frappe.get_doc(PAYROLL, payroll_entry)
    run.check_permission("read")
    bank_file.may_see_bank_details()
    if run.docstatus != 1 or not cint(run.salary_slips_submitted):
        frappe.throw(_("Submit the salary slips first. The mobile money file pays the submitted slips."),
                     title=_(TITLE))
    return run


def file_name(run):
    from hrms_addon.hrms_addon import payslip_rules

    period = payslip_rules.slip_for(run.end_date, run.start_date if run.payroll_frequency == WEEKLY else None)
    return " ".join(part for part in (_(TITLE), period, run.name) if part)


def lines_of(run):
    """One line for each submitted slip of the payroll: who, what they are paid, and how, as their employee record
    now says."""
    slips = frappe.get_all(SLIP, filters={"payroll_entry": run.name, "docstatus": 1},
                           fields=["employee", "employee_name", "net_pay"], order_by="employee asc",
                           limit_page_length=0)
    if not slips:
        frappe.throw(_("This payroll has no submitted salary slips."), title=_(TITLE))
    meta = frappe.get_meta(EMPLOYEE)
    fields = ["name", "salary_mode", "bank_ac_no", "first_name", "middle_name", "last_name"] + [
        field for field in (PHONE, REGISTERED) if meta.has_field(field)]
    people = {row.name: row for row in frappe.get_all(
        EMPLOYEE, filters={"name": ["in", sorted({slip.employee for slip in slips})]}, fields=fields,
        limit_page_length=0)}
    lines = []
    for slip in slips:
        person = people.get(slip.employee) or frappe._dict()
        lines.append({
            "employee": slip.employee, "employee_name": slip.employee_name, "amount": slip.net_pay,
            "salary_mode": person.get("salary_mode"), "bank_ac_no": person.get("bank_ac_no"),
            "phone": person.get(PHONE), "registered_name": person.get(REGISTERED),
            "first_name": person.get("first_name"), "middle_name": person.get("middle_name"),
            "last_name": person.get("last_name"),
        })
    return lines


def refuse_empty(lines):
    """No empty file. One with no phone number to give is in it with the phone blank (rules.blanks; Luuka, 13 Nov
    2026: "if moble phone/ bank account ist should be blank on that employee")."""
    if not rules.lines_to_pay(lines):
        frappe.throw(_("Nobody here is paid in cash or by mobile money, so there is no mobile money file."),
                     title=_(TITLE))
