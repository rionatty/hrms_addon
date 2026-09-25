# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""A staff loan's statement: what was lent, each month the payroll took,
anything paid directly or taken in the final settlement, what was written
off, the balance after each, and the months still to come. HR, Accounts
and the Payroll Officer see any loan; an employee their own."""

import frappe
from frappe import _
from frappe.utils import flt, today

from hrms_addon.hrms_addon import loan_rules as rules, loans

LOAN = "Employee Loan"
SEES_ALL = {"HR User", "HR Manager", "System Manager", "Accounts User", "Accounts Manager", "Payroll Officer"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    conditions = {"docstatus": 1, "status": ["not in", [rules.REJECTED, rules.CANCELLED]]}
    if filters.get("loan"):
        conditions["name"] = filters.loan
    if filters.get("employee"):
        conditions["employee"] = filters.employee
    if not SEES_ALL & set(frappe.get_roles()):
        mine = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        if not mine:
            return columns(), []
        conditions["employee"] = mine
    elif not (filters.get("loan") or filters.get("employee")):
        return columns(), [], _("Pick a loan or an employee.")
    data = []
    grace = loans.settings()["missed_grace_days"]
    for name in frappe.get_all(LOAN, filters=conditions, pluck="name", order_by="posting_date asc"):
        data += lines(frappe.get_doc(LOAN, name), grace)
    return columns(), data


def lines(loan, grace=rules.DEFAULTS["missed_grace_days"]):
    """One loan's statement, as rows."""
    base = {"loan": loan.name, "employee": loan.employee, "employee_name": loan.employee_name}
    lent = flt(loan.approved_amount or loan.loan_amount)
    balance = lent
    out = [dict(base, date=loan.disbursed_on or loan.posting_date, description=_("Lent") + (
        " ({0})".format(loan.disbursement_entry) if loan.get("disbursement_entry") else ""),
        lent=lent, repaid=0, due=0, balance=balance, state=_("Paid out") if loan.disbursed_on else "")]
    if flt(loan.total_interest):
        balance = round(balance + flt(loan.total_interest), 2)
        out.append(dict(base, date=loan.disbursed_on or loan.posting_date,
                        description=_("Interest, {0}% a year flat").format("%g" % flt(loan.interest_rate)),
                        lent=flt(loan.total_interest), repaid=0, due=0, balance=balance, state=""))
    rows = sorted(loan.repayments, key=lambda row: (str(row.payroll_date), -int(row.recovered or 0)))
    for row in rows:
        if row.recovered:
            balance = round(balance - flt(row.total), 2)
            what = row.remarks if row.get("reference_name") else _("Payroll deduction")
            reference = row.get("reference_name") or row.get("additional_salary") or ""
            out.append(dict(base, date=row.payroll_date, description=what + (" ({0})".format(reference)
                                                                               if reference else ""),
                            lent=0, repaid=flt(row.total), due=0, balance=balance, state=_("Taken")))
        else:
            missed = rules.missed([{"payroll_date": row.payroll_date, "recovered": 0}], today(), grace)
            out.append(dict(base, date=row.payroll_date, description=_("Instalment"), lent=0, repaid=0,
                            due=flt(row.total), balance=balance, state=_("Missed") if missed else _("Due")))
    if loan.get("written_off"):
        balance = round(balance - flt(loan.written_off_amount), 2)
        out.append(dict(base, date=loan.written_off_on, description=_("Written off") + (
            " ({0})".format(loan.write_off_entry) if loan.get("write_off_entry") else ""),
            lent=0, repaid=flt(loan.written_off_amount), due=0, balance=balance, state=_("Written off")))
    return out


def columns():
    return [
        {"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 150},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 260},
        {"fieldname": "lent", "label": _("Lent"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "repaid", "label": _("Repaid"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "due", "label": _("Due"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "state", "label": _("State"), "fieldtype": "Data", "width": 90},
    ]
