# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The staff loans book: each loan, what was lent, recovered and is still
owed, the monthly instalment, when the next one falls, how many months
are left and how many the payroll missed."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from hrms_addon.hrms_addon import loan_rules as rules, loans

LOAN, ROW = "Employee Loan", "Loan Repayment"
ALL = "All"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    status = filters.get("status") or rules.RUNNING
    conditions = {"docstatus": 1}
    conditions["status"] = ["not in", [rules.REJECTED, rules.CANCELLED]] if status == ALL else status
    for key in ("company", "branch", "department", "employee", "loan_type"):
        if filters.get(key):
            conditions[key] = filters[key]
    rows = frappe.get_all(LOAN, filters=conditions,
                          fields=["name", "employee", "employee_name", "department", "loan_type", "approved_amount",
                                  "loan_amount", "total_interest", "recovered_amount", "outstanding",
                                  "monthly_instalment", "status", "disbursed_on"],
                          order_by="employee_name asc")
    schedule = {}
    if rows:
        for line in frappe.get_all(ROW, filters={"parenttype": LOAN, "parent": ["in", [row.name for row in rows]],
                                                 "recovered": ["!=", 1]},
                                   fields=["parent", "payroll_date", "recovered"]):
            schedule.setdefault(line.parent, []).append(line)
    grace = loans.settings()["missed_grace_days"]
    now = getdate(today())
    data = []
    for row in rows:
        to_come = schedule.get(row.name, [])
        ahead = sorted(getdate(line.payroll_date) for line in to_come if getdate(line.payroll_date) >= now)
        missed = rules.missed([{"payroll_date": line.payroll_date, "recovered": 0} for line in to_come], now, grace)
        data.append({
            "loan": row.name, "employee": row.employee, "employee_name": row.employee_name,
            "department": row.department, "loan_type": row.loan_type,
            "lent": flt(row.approved_amount or row.loan_amount), "interest": flt(row.total_interest),
            "recovered": flt(row.recovered_amount), "outstanding": flt(row.outstanding),
            "monthly": flt(row.monthly_instalment), "next_due": ahead[0] if ahead else None,
            "months_left": len(to_come), "missed": len(missed), "status": row.status,
            "paid_out_on": row.disbursed_on,
        })
    return columns(), data


def columns():
    return [
        {"fieldname": "loan", "label": _("Loan"), "fieldtype": "Link", "options": "Employee Loan", "width": 150},
        {"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
        {"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 150},
        {"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department",
         "width": 140},
        {"fieldname": "loan_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
        {"fieldname": "lent", "label": _("Lent"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "interest", "label": _("Interest"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "recovered", "label": _("Recovered"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "monthly", "label": _("Monthly"), "fieldtype": "Currency", "width": 110},
        {"fieldname": "next_due", "label": _("Next Due"), "fieldtype": "Date", "width": 100},
        {"fieldname": "months_left", "label": _("Months Left"), "fieldtype": "Int", "width": 90},
        {"fieldname": "missed", "label": _("Missed"), "fieldtype": "Int", "width": 70},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
        {"fieldname": "paid_out_on", "label": _("Paid Out On"), "fieldtype": "Date", "width": 100},
    ]
