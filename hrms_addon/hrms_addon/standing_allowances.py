# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The allowances an employee is paid every month, managed from their
Salary Structure Assignment without cancelling it. The rules are in
standing_allowance_rules.py.

Each allowance is one of Frappe HR's recurring Additional Salaries, made,
ended and disabled here under the user's own permissions on that DocType:

  allowances  what the panel on the assignment shows
  add         a new allowance
  change      a new amount from a day
  end         a last day, or none again
  remove      one entered by mistake and never paid
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from hrms_addon.hrms_addon import pay, standing_allowance_rules as rules

RECORD = "Additional Salary"
ASSIGNMENT = "Salary Structure Assignment"
TITLE = "Allowance"


# ── what the panel shows ────────────────────────────────────────────────
@frappe.whitelist()
def allowances(employee):
    """The employee's allowances, what they add up to a month, and the
    monthly gross with them."""
    _may("read", employee)
    records = _records(employee)
    rows = rules.view(records, getdate(today()), _paid([record.name for record in records]))
    return {
        "rows": rows,
        "running": rules.total_running(rows),
        "gross": pay.monthly_gross(employee),
        "assigned": bool(_assigned_from(employee)),
        "can_change": bool(frappe.has_permission(RECORD, "create") and frappe.has_permission(RECORD, "write")),
        "currency": _currency(employee),
    }


def _may(ptype, employee):
    if not employee or not frappe.db.exists("Employee", employee):
        frappe.throw(_("Choose the employee."), title=_(TITLE))
    frappe.has_permission(RECORD, ptype, throw=True)
    frappe.has_permission("Employee", "read", employee, throw=True)


def _records(employee):
    """The employee's allowances on record: submitted, recurring earnings
    that have not been disabled."""
    return frappe.get_all(RECORD, filters={"employee": employee, "docstatus": 1, "is_recurring": 1,
                                           "type": rules.EARNING, "disabled": 0},
                          fields=["name", "salary_component", "amount", "from_date", "to_date"],
                          order_by="from_date asc", limit_page_length=0)


def _paid(names):
    """Those a submitted salary slip has paid."""
    if not names:
        return set()
    return set(frappe.get_all("Salary Detail", filters={"parenttype": "Salary Slip", "docstatus": 1,
                                                        "additional_salary": ["in", list(names)]},
                              pluck="additional_salary", limit_page_length=0))


def _assigned_from(employee):
    """The first day the employee has a salary structure: Frappe HR takes no
    Additional Salary from before it."""
    days = frappe.get_all(ASSIGNMENT, filters={"employee": employee, "docstatus": 1}, pluck="from_date",
                          order_by="from_date asc", limit=1)
    return days[0] if days else None


def _currency(employee):
    assignment = pay.assignment_on(employee)
    currency = frappe.db.get_value(ASSIGNMENT, assignment, "currency") if assignment else None
    if not currency:
        company = frappe.db.get_value("Employee", employee, "company")
        currency = frappe.db.get_value("Company", company, "default_currency") if company else None
    return currency


# ── changing them ───────────────────────────────────────────────────────
@frappe.whitelist(methods=["POST"])
def add(employee, salary_component, amount, from_date, to_date=None):
    _may("create", employee)
    person = frappe.db.get_value("Employee", employee, ["date_of_joining", "relieving_date"], as_dict=True)
    component = frappe.db.get_value("Salary Component", salary_component, ["type", "disabled"], as_dict=True) \
        if salary_component else None
    errors = rules.add_errors({
        "salary_component": salary_component, "component": component, "amount": amount, "from_date": from_date,
        "to_date": to_date, "joined": person.date_of_joining, "relieving": person.relieving_date,
        "assigned_from": _assigned_from(employee), "others": _records(employee)})
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
    return _new(employee, salary_component, amount, from_date, to_date).name


@frappe.whitelist(methods=["POST"])
def change(name, amount, from_date):
    """A new amount from a day. What was paid keeps the amount it was paid
    at: the allowance as it was ends the day before."""
    doc = _record(name)
    plan = rules.change_plan(doc.as_dict(), amount, from_date, paid=name in _paid([name]))
    if plan.get("errors"):
        frappe.throw("<br>".join(_(message) for message in plan["errors"]), title=_(TITLE))
    until = None if rules.is_open(doc.to_date) else doc.to_date
    if plan["kind"] == rules.CORRECT:
        _disable(doc)
        return _new(doc.employee, doc.salary_component, amount, doc.from_date, until).name
    _end(doc, plan["end_on"])
    return _new(doc.employee, doc.salary_component, amount, from_date, until).name


@frappe.whitelist(methods=["POST"])
def end(name, to_date=None):
    """A last day for the allowance; none lets it run on."""
    doc = _record(name)
    errors = rules.end_errors(doc.as_dict(), to_date, _records(doc.employee))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
    relieving = frappe.db.get_value("Employee", doc.employee, "relieving_date")
    _end(doc, rules.last_day(to_date, relieving))
    return doc.name


@frappe.whitelist(methods=["POST"])
def remove(name):
    """One entered by mistake, while no slip has paid it."""
    doc = _record(name)
    errors = rules.remove_errors(doc.as_dict(), paid=name in _paid([name]))
    if errors:
        frappe.throw("<br>".join(_(message) for message in errors), title=_(TITLE))
    _disable(doc)
    return doc.name


def _record(name):
    doc = frappe.get_doc(RECORD, name)
    doc.check_permission("write")
    frappe.has_permission("Employee", "read", doc.employee, throw=True)
    if doc.docstatus != 1 or not cint(doc.is_recurring) or cint(doc.disabled) \
            or (doc.get("type") or rules.EARNING) != rules.EARNING:
        frappe.throw(_("{0} is not an allowance on record.").format(name), title=_(TITLE))
    return doc


def _new(employee, salary_component, amount, from_date, to_date=None):
    company, relieving = frappe.db.get_value("Employee", employee, ["company", "relieving_date"])
    doc = frappe.get_doc({
        "doctype": RECORD, "employee": employee, "company": company, "salary_component": salary_component,
        "amount": flt(amount), "is_recurring": 1, "disabled": 0, "from_date": getdate(from_date),
        "to_date": rules.last_day(to_date, relieving), "currency": _currency(employee),
        # paid beside whatever the structure pays, never in its place
        "overwrite_salary_structure_amount": 0,
    })
    doc.insert()
    doc.submit()
    return doc


def _end(doc, day):
    """The last day, set on the submitted record (To Date is allowed after
    submit by this app's property setter)."""
    doc.to_date = getdate(day)
    doc.save()


def _disable(doc):
    """Frappe HR's own way to stop a recurring Additional Salary: payroll and
    the overlap check both leave a disabled one out."""
    doc.disabled = 1
    doc.save()
