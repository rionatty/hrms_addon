# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Frappe HR's Salary Slip, printed as Luuka's pay slip, and the period a
monthly payroll runs for. The rules are in payslip_rules.py.

  pay_slip         the Pay Slip print format's figures (a jinja method)
  period_validate  Payroll Entry and Salary Slip validate: a monthly
                   payroll runs for the 26th to the 25th
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms_addon.hrms_addon import payslip_rules as rules

SLIP = "Salary Slip"
OVERTIME_SLIP = "Overtime Slip"


def pay_slip(doc):
    """What the Pay Slip prints for a Salary Slip (the document or its
    name): who it is for, the payments and deductions that are money, the
    totals and the days."""
    if isinstance(doc, str):
        doc = frappe.get_doc(SLIP, doc)
    doc.check_permission("read")
    employee = frappe.db.get_value("Employee", doc.employee, _employee_fields(), as_dict=True) or frappe._dict()
    earnings = [row.as_dict() for row in doc.get("earnings") or []]
    deductions = [row.as_dict() for row in doc.get("deductions") or []]
    leave, absent = rules.day_counts(_attendance(doc))
    net = flt(doc.get("net_pay"))
    return frappe._dict({
        "employee_name": doc.get("employee_name"),
        "department": _department(doc.get("department")),
        "payroll_no": doc.get("employee"),
        "slip_for": rules.slip_for(doc.get("end_date")),
        "designation": doc.get("designation"),
        "category": employee.get("custom_pay_category") or employee.get("employment_type"),
        "plant": doc.get("branch"),
        "payments": rules.lines(earnings, _overtime_hours(earnings)),
        "gross": flt(doc.get("gross_pay")),
        "deductions": rules.lines(deductions),
        "total_deductions": flt(doc.get("total_deduction")),
        "net": net,
        "rounded": flt(doc.get("rounded_total")) or flt(round(net)),
        "payment_by": _payment_by(doc, employee),
        "paid_days": flt(doc.get("payment_days")),
        "working_days": flt(doc.get("total_working_days")),
        "holidays": _holidays(doc),
        "absent_amount": rules.absent_amount(earnings),
        "leave_taken": leave,
        "absent_days": flt(doc.get("absent_days")) or absent,
    })


def _employee_fields():
    fields = ["employment_type", "salary_mode", "bank_name", "bank_ac_no"]
    if frappe.get_meta("Employee").has_field("custom_pay_category"):
        fields.append("custom_pay_category")
    return fields


def _department(name):
    """The department as it is called, without the company's abbreviation."""
    return (frappe.db.get_value("Department", name, "department_name") or name) if name else None


def _payment_by(doc, employee):
    how = doc.get("mode_of_payment") or employee.get("salary_mode")
    bank = doc.get("bank_name") or employee.get("bank_name")
    account = doc.get("bank_account_no") or employee.get("bank_ac_no")
    return " ".join(str(part) for part in (how, bank, account) if part) or None


def _attendance(doc):
    return frappe.get_all("Attendance", filters={"employee": doc.employee, "docstatus": 1,
                                                 "attendance_date": ["between", [doc.start_date, doc.end_date]]},
                          fields=["status", "leave_type"], limit_page_length=0)


def _holidays(doc):
    """The public holidays in the period; the weekly day off is not one."""
    from hrms.hr.utils import get_holidays_for_employee

    return len(get_holidays_for_employee(doc.employee, doc.start_date, doc.end_date, raise_exception=False,
                                         only_non_weekly=True))


def _overtime_hours(earnings):
    """{Additional Salary: hours} for the earnings an Overtime Slip pays: the
    hours of its overtime types that are paid through that component."""
    hours = {}
    for row in earnings:
        name = row.get("additional_salary")
        if not name:
            continue
        ref = frappe.db.get_value("Additional Salary", name, ["ref_doctype", "ref_docname"], as_dict=True)
        if not ref or ref.ref_doctype != OVERTIME_SLIP or not ref.ref_docname:
            continue
        total = 0.0
        for detail in frappe.get_all("Overtime Details", filters={"parent": ref.ref_docname,
                                                                  "parenttype": OVERTIME_SLIP},
                                     fields=["overtime_type", "overtime_duration"], limit_page_length=0):
            component = frappe.db.get_value("Overtime Type", detail.overtime_type, "overtime_salary_component")
            if component == row.get("salary_component"):
                total += flt(detail.overtime_duration)
        if total:
            hours[name] = total
    return hours


def period_validate(doc, method=None):
    """A monthly payroll, and a monthly slip, run for the 26th to the 25th."""
    if doc.get("salary_slip_based_on_timesheet"):
        return
    errors = rules.period_errors(doc.get("payroll_frequency"), doc.get("start_date"), doc.get("end_date"))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_("Payroll Period"))
